import asyncio
import socket
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from websockets.asyncio.client import connect as websocket_connect
from websockets.asyncio.server import serve as websocket_serve

from py_game.network.online_server import (
    LobbyDirectory,
    OnlineRelayServer,
    load_authoritative_dragons,
)
from py_game.network.decks import serialize_deck_selection
from py_game.network.protocol import (
    APPLICATION_VERSION,
    FrameDecoder,
    MessageType,
    ProtocolMessage,
    encode_message,
)
from py_game.network.session import NetworkEvent, OnlineClient, SocketPeer
from utils.database_utils import DBUtil


class LobbyDirectoryTests(unittest.TestCase):
    def test_public_and_protected_lobbies_are_listed_without_password_data(self):
        directory = LobbyDirectory()
        public = directory.create("host-a", "Alice", "Open table")
        protected = directory.create("host-b", "Bob", "Friends", "swordfish")

        listings = directory.open_lobbies()

        self.assertEqual([item["name"] for item in listings], ["Friends", "Open table"])
        self.assertFalse(public.protected)
        self.assertTrue(protected.protected)
        self.assertNotIn("password", listings[0])
        self.assertNotIn("password_digest", listings[0])
        self.assertNotIn("password_salt", listings[0])

    def test_protected_lobby_rejects_wrong_password_and_accepts_correct_one(self):
        directory = LobbyDirectory()
        lobby = directory.create("host", "Alice", "Locked", "correct horse")

        with self.assertRaisesRegex(ValueError, "Incorrect lobby password"):
            directory.join("guest", "Bob", lobby.lobby_id, "wrong")

        joined = directory.join("guest", "Bob", lobby.lobby_id, "correct horse")
        self.assertEqual(joined.guest_id, "guest")
        self.assertEqual(directory.open_lobbies(), [])

    def test_guest_leave_reopens_lobby_but_host_leave_removes_it(self):
        directory = LobbyDirectory()
        lobby = directory.create("host", "Alice", "Table")
        directory.join("guest", "Bob", lobby.lobby_id)

        left, role = directory.leave("guest")

        self.assertEqual(role, "guest")
        self.assertTrue(left.open)
        self.assertEqual(len(directory.open_lobbies()), 1)

        _left, role = directory.leave("host")
        self.assertEqual(role, "host")
        self.assertEqual(directory.open_lobbies(), [])


class FakeRelayConnection:
    def __init__(self, client_id, player_name, client_kind="native"):
        self.client_id = client_id
        self.player_name = player_name
        self.client_kind = client_kind
        self.sent = []

    async def send(self, message_type, payload=None, **metadata):
        self.sent.append(
            (
                message_type.value if isinstance(message_type, MessageType) else message_type,
                payload or {},
                metadata,
            )
        )


class OnlineRelayRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_authoritative_dragons_load_without_general_database_utility(self):
        dragons = load_authoritative_dragons()

        self.assertEqual(len(dragons), 4)
        self.assertEqual(
            {dragon.id for dragon in dragons},
            {"dragon_blue_1", "dragon_red_1", "dragon_green_1", "dragon_black_1"},
        )

    async def test_browser_clients_require_the_protected_entry_path(self):
        self.assertTrue(
            OnlineRelayServer._is_browser_entry_path("/browser-game")
        )
        self.assertTrue(
            OnlineRelayServer._is_browser_entry_path("/browser-game/?ticket=ignored")
        )
        self.assertFalse(OnlineRelayServer._is_browser_entry_path("/game"))

    async def test_browser_host_lobby_keeps_decks_and_readiness_on_server(self):
        server = OnlineRelayServer(max_clients=10)
        host = FakeRelayConnection("host", "Alice", "web")
        guest = FakeRelayConnection("guest", "Bob", "web")
        server.clients = {host.client_id: host, guest.client_id: guest}
        lobby = server.directory.create(
            host.client_id,
            host.player_name,
            "Browser duel",
            server_authoritative=True,
        )
        server.directory.join(guest.client_id, guest.player_name, lobby.lobby_id)
        deck = SimpleNamespace(id="web-deck", name="Web deck")

        with patch(
            "py_game.network.decks.reconstruct_remote_deck",
            return_value=deck,
        ):
            for connection in (host, guest):
                await server._handle_authoritative_lobby_message(
                    connection,
                    lobby,
                    ProtocolMessage(
                        type=MessageType.SELECT_DECK.value,
                        sequence=1,
                        payload={"deck": {"deck_id": "web-deck"}},
                    ),
                )
                await server._handle_authoritative_lobby_message(
                    connection,
                    lobby,
                    ProtocolMessage(
                        type=MessageType.READY.value,
                        sequence=2,
                        payload={"ready": True},
                    ),
                )

        self.assertTrue(lobby.can_start)
        self.assertIs(lobby.host_deck, deck)
        self.assertIs(lobby.guest_deck, deck)
        self.assertEqual(host.sent[-1][0], MessageType.LOBBY_STATE.value)
        self.assertEqual(guest.sent[-1][0], MessageType.LOBBY_STATE.value)

    async def test_native_lobby_remains_relay_backed(self):
        directory = LobbyDirectory()
        native = directory.create("host", "Alice", "Native")
        browser = directory.create(
            "web-host",
            "Browser",
            "Browser",
            server_authoritative=True,
        )

        self.assertFalse(native.server_authoritative)
        self.assertTrue(browser.server_authoritative)
        self.assertTrue(browser.listing()["server_authoritative"])

    async def test_relay_preserves_gameplay_request_and_match_identity(self):
        server = OnlineRelayServer(max_clients=10)
        host = FakeRelayConnection("host", "Alice")
        guest = FakeRelayConnection("guest", "Bob")
        server.clients = {host.client_id: host, guest.client_id: guest}
        lobby = server.directory.create(host.client_id, host.player_name, "Duel")
        server.directory.join(guest.client_id, guest.player_name, lobby.lobby_id)
        message = ProtocolMessage(
            type=MessageType.PLAYER_ACTION.value,
            sequence=7,
            request_id="choice-9",
            match_id="match-4",
            payload={"value": 3},
        )

        await server._relay(guest, message)

        relayed = host.sent[-1]
        self.assertEqual(relayed[0], MessageType.PLAYER_ACTION.value)
        self.assertEqual(relayed[1], {"value": 3})
        self.assertEqual(relayed[2]["request_id"], "choice-9")
        self.assertEqual(relayed[2]["match_id"], "match-4")

    async def test_server_status_reports_capacity_and_active_pairings(self):
        server = OnlineRelayServer(max_clients=4)
        host = FakeRelayConnection("host", "Alice")
        guest = FakeRelayConnection("guest", "Bob")
        server.clients = {host.client_id: host, guest.client_id: guest}
        lobby = server.directory.create(host.client_id, host.player_name, "Duel")
        server.directory.join(guest.client_id, guest.player_name, lobby.lobby_id)

        status = server.status_payload()

        self.assertEqual(status["connected_players"], 2)
        self.assertEqual(status["max_players"], 4)
        self.assertEqual(status["active_matches"], 0)
        self.assertEqual(status["load"], "medium")

        await server._relay(
            host,
            ProtocolMessage(
                type=MessageType.START_MATCH.value,
                sequence=1,
                match_id="match-1",
                payload={"match_id": "match-1"},
            ),
        )
        self.assertEqual(server.status_payload()["active_matches"], 1)


class OnlineClientTests(unittest.TestCase):
    def test_server_control_events_are_kept_out_of_gameplay_poll(self):
        client = OnlineClient()
        control = NetworkEvent(
            "message",
            ProtocolMessage(
                type=MessageType.SERVER_STATUS.value,
                sequence=1,
                payload={"load": "low"},
            ),
        )
        gameplay = NetworkEvent(
            "message",
            ProtocolMessage(
                type=MessageType.CHOICE_REQUEST.value,
                sequence=2,
                payload={"choice_type": "pass"},
            ),
        )

        with patch(
            "py_game.network.session.LanClient.poll",
            return_value=[control, gameplay],
        ):
            self.assertEqual(client.poll_control(), [control])

        self.assertEqual(client.poll(), [gameplay])

    def test_socket_heartbeat_records_round_trip_latency(self):
        left, right = socket.socketpair()
        first = SocketPeer(left, ("local", 1), heartbeat_interval=0.02, idle_timeout=1.0)
        second = SocketPeer(right, ("local", 2), heartbeat_interval=0.02, idle_timeout=1.0)
        try:
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline and first.latency_ms is None:
                time.sleep(0.01)
            self.assertIsNotNone(first.latency_ms)
            self.assertGreaterEqual(first.latency_ms, 0)
        finally:
            first.close()
            second.close()


class AsyncProtocolClient:
    def __init__(self, websocket):
        self.websocket = websocket
        self.sequence = 0
        self.decoder = FrameDecoder()
        self.pending = []

    async def send(self, message_type, payload=None, **metadata):
        message = ProtocolMessage(
            type=message_type.value,
            sequence=self.sequence,
            payload=payload or {},
            **metadata,
        )
        self.sequence += 1
        await self.websocket.send(encode_message(message))

    async def receive(self, message_type, timeout=2.0):
        expected = message_type.value
        while True:
            for index, message in enumerate(self.pending):
                if message.type == expected:
                    return self.pending.pop(index)
            data = await asyncio.wait_for(self.websocket.recv(), timeout)
            if isinstance(data, str):
                raise AssertionError("Relay sent a text WebSocket frame")
            self.pending.extend(self.decoder.feed(data))

    async def close(self):
        await self.websocket.close()


class OnlineRelayLoopbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_match_waits_for_grace_and_resumes_same_session(self):
        relay = OnlineRelayServer(
            max_clients=4,
            disconnect_grace_seconds=0.08,
        )
        relay.loop = asyncio.get_running_loop()
        server = await websocket_serve(relay.handle_connection, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        host = AsyncProtocolClient(
            await websocket_connect(f"ws://127.0.0.1:{port}/browser-game")
        )
        guest = AsyncProtocolClient(
            await websocket_connect(f"ws://127.0.0.1:{port}/browser-game")
        )

        class ResumableMatch:
            match_id = "resumable-match"

            def __init__(self, host_id, guest_id):
                self.host_id = host_id
                self.guest_id = guest_id
                self.detached = set()
                self.resumed = []

            def has_client(self, client_id):
                return client_id in {self.host_id, self.guest_id}

            def peer_id(self, client_id):
                return self.guest_id if client_id == self.host_id else self.host_id

            def detach_client(self, client_id, _client=None):
                self.detached.add(client_id)

            def replace_client(self, client_id, _client):
                self.detached.discard(client_id)
                return True

            async def resume_client(self, client_id):
                self.resumed.append(client_id)

        reconnected = None
        try:
            welcomes = []
            for client, name in ((host, "Host"), (guest, "Guest")):
                await client.send(
                    MessageType.ONLINE_HELLO,
                    {
                        "player_name": name,
                        "application_version": APPLICATION_VERSION,
                        "client_kind": "web",
                    },
                )
                welcomes.append(await client.receive(MessageType.ONLINE_WELCOME))
            host_id = welcomes[0].payload["client_id"]
            guest_id = welcomes[1].payload["client_id"]
            guest_token = welcomes[1].payload["resume_token"]

            await host.send(
                MessageType.CREATE_ONLINE_LOBBY,
                {"name": "Reconnect duel", "password": ""},
            )
            hosted = await host.receive(MessageType.ONLINE_LOBBY)
            await guest.send(
                MessageType.JOIN_ONLINE_LOBBY,
                {"lobby_id": hosted.payload["lobby_id"], "password": ""},
            )
            await guest.receive(MessageType.ONLINE_LOBBY)
            lobby = relay.directory.lobbies[hosted.payload["lobby_id"]]
            lobby.active_match = True
            match = ResumableMatch(host_id, guest_id)
            relay.matches[match.match_id] = match

            await guest.close()
            await asyncio.sleep(0.03)
            self.assertIn(guest_id, match.detached)
            with self.assertRaises(asyncio.TimeoutError):
                await host.receive(MessageType.PEER_CONNECTION_STATUS, timeout=0.02)

            lost = await host.receive(MessageType.PEER_CONNECTION_STATUS, timeout=0.3)
            self.assertEqual(lost.payload["status"], "disconnected")
            self.assertIn(match.match_id, relay.matches)

            reconnected = AsyncProtocolClient(
                await websocket_connect(f"ws://127.0.0.1:{port}/browser-game")
            )
            await reconnected.send(
                MessageType.ONLINE_HELLO,
                {
                    "player_name": "Guest",
                    "application_version": APPLICATION_VERSION,
                    "client_kind": "web",
                    "resume_token": guest_token,
                },
            )
            welcome = await reconnected.receive(MessageType.ONLINE_WELCOME)
            self.assertTrue(welcome.payload["resumed"])
            self.assertEqual(welcome.payload["client_id"], guest_id)
            restored = await host.receive(MessageType.PEER_CONNECTION_STATUS)
            self.assertEqual(restored.payload["status"], "connected")
            self.assertEqual(match.resumed, [guest_id])
            self.assertNotIn(guest_id, match.detached)
        finally:
            await host.close()
            if reconnected:
                await reconnected.close()
            server.close()
            await server.wait_closed()

    async def test_browser_host_starts_server_authoritative_match(self):
        relay = OnlineRelayServer(max_clients=4)
        relay.loop = asyncio.get_running_loop()
        server = await websocket_serve(relay.handle_connection, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        host_socket = await websocket_connect(f"ws://127.0.0.1:{port}/browser-game")
        guest_socket = await websocket_connect(f"ws://127.0.0.1:{port}/browser-game")
        host = AsyncProtocolClient(host_socket)
        guest = AsyncProtocolClient(guest_socket)
        descriptor = serialize_deck_selection(DBUtil().load_deck("Starter Blue_1"))
        try:
            for client, name in ((host, "Web host"), (guest, "Web guest")):
                await client.send(
                    MessageType.ONLINE_HELLO,
                    {
                        "player_name": name,
                        "application_version": APPLICATION_VERSION,
                        "client_kind": "web",
                    },
                )
                await client.receive(MessageType.ONLINE_WELCOME)

            await host.send(
                MessageType.CREATE_ONLINE_LOBBY,
                {"name": "Browser duel", "password": ""},
            )
            hosted = await host.receive(MessageType.ONLINE_LOBBY)
            await guest.send(
                MessageType.JOIN_ONLINE_LOBBY,
                {"lobby_id": hosted.payload["lobby_id"], "password": ""},
            )
            await guest.receive(MessageType.ONLINE_LOBBY)
            await guest.send(
                MessageType.HELLO,
                {
                    "player_name": "Web guest",
                    "application_version": APPLICATION_VERSION,
                },
            )
            await guest.receive(MessageType.HELLO_ACCEPTED)
            await host.send(MessageType.SELECT_DECK, {"deck": descriptor})
            await guest.send(MessageType.SELECT_DECK, {"deck": descriptor})
            await host.send(MessageType.READY, {"ready": True})
            await guest.send(MessageType.READY, {"ready": True})

            ready = await host.receive(MessageType.LOBBY_STATE)
            while not (
                ready.payload["host"]["ready"]
                and (ready.payload.get("guest") or {}).get("ready")
            ):
                ready = await host.receive(MessageType.LOBBY_STATE)
            await host.send(MessageType.START_MATCH, {})

            host_start = await host.receive(MessageType.START_MATCH)
            guest_start = await guest.receive(MessageType.START_MATCH)
            self.assertTrue(host_start.payload["authoritative"])
            self.assertEqual(
                host_start.payload["match_id"],
                guest_start.payload["match_id"],
            )
            self.assertEqual(len(relay.matches), 1)
        finally:
            await host.close()
            await guest.close()
            await asyncio.sleep(0.1)
            server.close()
            await server.wait_closed()

    async def test_threaded_online_client_connects_and_receives_control_messages(self):
        relay = OnlineRelayServer(max_clients=2)
        server = await websocket_serve(relay.handle_connection, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        client = OnlineClient()
        try:
            client.connect(f"ws://127.0.0.1:{port}/game")
            deadline = time.monotonic() + 2.0
            connected = False
            while time.monotonic() < deadline and not connected:
                connected = any(event.kind == "connected" for event in client.poll())
                await asyncio.sleep(0.01)
            self.assertTrue(connected)
            self.assertIsNotNone(client.peer)

            client.peer.send(
                MessageType.ONLINE_HELLO,
                {"player_name": "Alice", "application_version": APPLICATION_VERSION},
            )
            welcome = None
            while time.monotonic() < deadline and welcome is None:
                welcome = next(
                    (
                        event.message
                        for event in client.poll_control()
                        if event.message
                        and event.message.type == MessageType.ONLINE_WELCOME.value
                    ),
                    None,
                )
                await asyncio.sleep(0.01)
            self.assertIsNotNone(welcome)
        finally:
            await asyncio.to_thread(client.close)
            server.close()
            await server.wait_closed()

    async def test_two_clients_create_join_and_relay_existing_game_messages(self):
        relay = OnlineRelayServer(max_clients=4)
        server = await websocket_serve(relay.handle_connection, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        host = AsyncProtocolClient(await websocket_connect(f"ws://127.0.0.1:{port}/game"))
        guest = AsyncProtocolClient(await websocket_connect(f"ws://127.0.0.1:{port}/game"))
        try:
            await host.send(
                MessageType.ONLINE_HELLO,
                {"player_name": "Alice", "application_version": APPLICATION_VERSION},
            )
            await guest.send(
                MessageType.ONLINE_HELLO,
                {"player_name": "Bob", "application_version": APPLICATION_VERSION},
            )
            await host.receive(MessageType.ONLINE_WELCOME)
            await guest.receive(MessageType.ONLINE_WELCOME)

            await host.send(
                MessageType.CREATE_ONLINE_LOBBY,
                {"name": "Test duel", "password": "secret"},
            )
            host_lobby = await host.receive(MessageType.ONLINE_LOBBY)
            lobby_id = host_lobby.payload["lobby_id"]

            await guest.send(
                MessageType.JOIN_ONLINE_LOBBY,
                {"lobby_id": lobby_id, "password": "secret"},
            )
            joined = await guest.receive(MessageType.ONLINE_LOBBY)
            self.assertEqual(joined.payload["role"], "guest")
            self.assertEqual(joined.payload["guest_name"], "Bob")

            await guest.send(
                MessageType.HELLO,
                {"player_name": "Bob", "application_version": APPLICATION_VERSION},
                request_id="guest-handshake",
            )
            relayed = await host.receive(MessageType.HELLO)
            self.assertEqual(relayed.request_id, "guest-handshake")
            self.assertEqual(relayed.payload["player_name"], "Bob")
        finally:
            await host.close()
            await guest.close()
            server.close()
            await server.wait_closed()


if __name__ == "__main__":
    unittest.main()
