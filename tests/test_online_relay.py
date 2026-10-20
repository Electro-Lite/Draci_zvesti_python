import asyncio
import socket
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from websockets.asyncio.client import connect as websocket_connect
from websockets.asyncio.server import serve as websocket_serve

from py_game.network.online_server import LobbyDirectory, OnlineRelayServer
from py_game.network.protocol import (
    APPLICATION_VERSION,
    FrameDecoder,
    MessageType,
    ProtocolMessage,
    encode_message,
)
from py_game.network.session import NetworkEvent, OnlineClient, SocketPeer


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
    def __init__(self, client_id, player_name):
        self.client_id = client_id
        self.player_name = player_name
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
