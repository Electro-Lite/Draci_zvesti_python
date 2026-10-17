import json
import socket
import time
import unittest
import threading
from types import SimpleNamespace

from choice_strategies.choice_strategy_ai_random import ChoiceStrategyAIRandom
from core.board import Board
from core.game_loop import run as run_game
from core.player import Player
from py_game.network.gameplay import (
    HostMatchChannel,
    RemoteChoiceStrategy,
    network_display_strategy,
    serialize_game_state,
)
from py_game.network.decks import reconstruct_remote_deck, serialize_deck_selection
from py_game.network.lobby import HostLobbyController
from py_game.network.protocol import (
    HEADER,
    MAX_MESSAGE_SIZE,
    FrameDecoder,
    MessageType,
    ProtocolError,
    ProtocolMessage,
    SequenceGuard,
    encode_message,
)
from py_game.network.session import (
    LanClient,
    LanHost,
    SocketPeer,
    explain_connection_error,
    hello_payload,
    parse_join_target,
)
from utils.database_utils import DBUtil


class LanProtocolTests(unittest.TestCase):
    def test_socket_errors_are_translated_to_actionable_messages(self):
        self.assertIn("host lobby", explain_connection_error("Connection refused"))
        self.assertIn("same LAN", explain_connection_error("Network is unreachable"))
        self.assertNotIn("Errno", explain_connection_error("[Errno 99] mystery"))

    def test_join_target_supports_hostname_ipv4_and_bracketed_ipv6(self):
        self.assertEqual(parse_join_target("game.local", 47777), ("game.local", 47777))
        self.assertEqual(parse_join_target("192.168.1.8:48888", 47777), ("192.168.1.8", 48888))
        self.assertEqual(parse_join_target("[::1]:49999", 47777), ("::1", 49999))

    def test_join_target_rejects_invalid_port(self):
        with self.assertRaisesRegex(ValueError, "LAN port"):
            parse_join_target("host:80", 47777)

    def test_round_trip_with_fragmented_input(self):
        message = ProtocolMessage(
            type=MessageType.HELLO.value,
            sequence=0,
            request_id="request-1",
            payload={"name": "Player 2"},
        )
        encoded = encode_message(message)
        decoder = FrameDecoder()

        self.assertEqual(decoder.feed(encoded[:2]), [])
        self.assertEqual(decoder.feed(encoded[2:7]), [])
        self.assertEqual(decoder.feed(encoded[7:]), [message])

    def test_multiple_frames_can_share_packet(self):
        first = ProtocolMessage(type=MessageType.PING.value, sequence=1)
        second = ProtocolMessage(type=MessageType.PONG.value, sequence=2)
        self.assertEqual(
            FrameDecoder().feed(encode_message(first) + encode_message(second)),
            [first, second],
        )

    def test_unknown_message_type_is_rejected(self):
        with self.assertRaisesRegex(ProtocolError, "Unknown message"):
            encode_message(ProtocolMessage(type="unsafe", sequence=0))

    def test_protocol_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ProtocolError, "Protocol mismatch"):
            encode_message(
                ProtocolMessage(
                    type=MessageType.HELLO.value,
                    sequence=0,
                    protocol_version=999,
                )
            )

    def test_invalid_and_oversized_frames_are_rejected(self):
        decoder = FrameDecoder()
        with self.assertRaisesRegex(ProtocolError, "frame size"):
            decoder.feed(HEADER.pack(MAX_MESSAGE_SIZE + 1))

        with self.assertRaisesRegex(ProtocolError, "maximum allowed size"):
            encode_message(
                ProtocolMessage(
                    type=MessageType.ERROR.value,
                    sequence=0,
                    payload={"message": "x" * MAX_MESSAGE_SIZE},
                )
            )

    def test_unknown_fields_and_malformed_json_are_rejected(self):
        unknown = b'{"type":"ping","sequence":0,"unexpected":true}'
        with self.assertRaisesRegex(ProtocolError, "unknown fields"):
            FrameDecoder().feed(HEADER.pack(len(unknown)) + unknown)
        malformed = b"{not-json}"
        with self.assertRaisesRegex(ProtocolError, "UTF-8 JSON"):
            FrameDecoder().feed(HEADER.pack(len(malformed)) + malformed)

    def test_sequence_guard_rejects_duplicates_and_old_messages(self):
        guard = SequenceGuard()
        self.assertTrue(guard.accept(1))
        self.assertFalse(guard.accept(1))
        self.assertFalse(guard.accept(0))
        self.assertTrue(guard.accept(2))


class LobbyTests(unittest.TestCase):
    def setUp(self):
        self.lobby = HostLobbyController(
            "Host",
            validate_deck=lambda deck_id: deck_id in {"host-deck", "guest-deck"},
        )

    def test_handshake_deck_selection_and_ready_state(self):
        response, _ = self.lobby.handle(
            ProtocolMessage(
                type=MessageType.HELLO.value,
                sequence=0,
                payload=hello_payload("Guest"),
            )
        )
        self.assertEqual(response, MessageType.HELLO_ACCEPTED)
        self.lobby.select_host_deck("host-deck")
        self.lobby.set_host_ready(True)
        self.lobby.handle(
            ProtocolMessage(
                type=MessageType.SELECT_DECK.value,
                sequence=1,
                payload={"deck_id": "guest-deck"},
            )
        )
        self.lobby.handle(
            ProtocolMessage(
                type=MessageType.READY.value,
                sequence=2,
                payload={"ready": True},
            )
        )
        self.assertTrue(self.lobby.state.can_start)

    def test_guest_cannot_ready_without_valid_deck(self):
        self.lobby.handle(
            ProtocolMessage(
                type=MessageType.HELLO.value,
                sequence=0,
                payload=hello_payload("Guest"),
            )
        )
        with self.assertRaisesRegex(ValueError, "select a valid deck"):
            self.lobby.handle(
                ProtocolMessage(
                    type=MessageType.READY.value,
                    sequence=1,
                    payload={"ready": True},
                )
            )

    def test_application_version_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "version mismatch"):
            self.lobby.handle(
                ProtocolMessage(
                    type=MessageType.HELLO.value,
                    sequence=0,
                    application_version="old",
                    payload=hello_payload("Guest"),
                )
            )

    def test_guest_composition_is_reconstructed_instead_of_looking_up_remote_id(self):
        database = DBUtil()
        source = database.load_deck("Killer Queen_1")
        source.id = "guest-windows-only-id"
        source.name = "Guest custom deck"
        lobby = HostLobbyController(
            "Host",
            validate_deck=lambda deck_id: database.load_deck(deck_id) is not None,
            reconstruct_guest_deck=lambda descriptor: reconstruct_remote_deck(
                descriptor,
                database.load_card,
            ),
        )
        lobby.handle(
            ProtocolMessage(
                type=MessageType.HELLO.value,
                sequence=0,
                payload=hello_payload("Guest"),
            )
        )

        lobby.handle(
            ProtocolMessage(
                type=MessageType.SELECT_DECK.value,
                sequence=1,
                payload={"deck": serialize_deck_selection(source)},
            )
        )

        self.assertEqual(lobby.state.guest.deck_id, "guest-windows-only-id")
        self.assertEqual(lobby.state.guest.deck_name, "Guest custom deck")
        self.assertEqual(
            [str(card.id) for card in lobby.guest_deck.cards],
            [str(card.id) for card in source.cards],
        )

    def test_invalid_reselection_clears_previous_guest_deck_and_ready_state(self):
        database = DBUtil()
        source = database.load_deck("Killer Queen_1")
        lobby = HostLobbyController(
            "Host",
            validate_deck=lambda _deck_id: True,
            reconstruct_guest_deck=lambda descriptor: reconstruct_remote_deck(
                descriptor,
                database.load_card,
            ),
        )
        lobby.handle(
            ProtocolMessage(
                type=MessageType.HELLO.value,
                sequence=0,
                payload=hello_payload("Guest"),
            )
        )
        lobby.handle(
            ProtocolMessage(
                type=MessageType.SELECT_DECK.value,
                sequence=1,
                payload={"deck": serialize_deck_selection(source)},
            )
        )
        lobby.handle(
            ProtocolMessage(
                type=MessageType.READY.value,
                sequence=2,
                payload={"ready": True},
            )
        )

        invalid = serialize_deck_selection(source)
        invalid["card_ids"][0] = "missing-card"
        with self.assertRaisesRegex(ValueError, "unknown card"):
            lobby.handle(
                ProtocolMessage(
                    type=MessageType.SELECT_DECK.value,
                    sequence=3,
                    payload={"deck": invalid},
                )
            )

        self.assertIsNone(lobby.guest_deck)
        self.assertIsNone(lobby.state.guest.deck_id)
        self.assertFalse(lobby.state.guest.ready)


class RemoteDeckTransferTests(unittest.TestCase):
    def setUp(self):
        self.database = DBUtil()

    @staticmethod
    def card_ids(deck):
        return [str(card.id) for card in deck.cards]

    def test_remote_id_collision_does_not_substitute_the_hosts_composition(self):
        remote = self.database.load_deck("Killer Queen_1")
        remote.id = "Starter Blue_1"
        remote.name = "Different deck with colliding ID"
        host_deck = self.database.load_deck("Starter Blue_1")

        reconstructed = reconstruct_remote_deck(
            serialize_deck_selection(remote),
            self.database.load_card,
        )

        self.assertEqual(self.card_ids(reconstructed), self.card_ids(remote))
        self.assertNotEqual(self.card_ids(reconstructed), self.card_ids(host_deck))

    def test_unknown_card_is_rejected_without_saving_remote_deck(self):
        remote = self.database.load_deck("Killer Queen_1")
        remote.id = "not-in-host-deck-database"
        descriptor = serialize_deck_selection(remote)
        descriptor["card_ids"][0] = "missing-card"

        with self.assertRaisesRegex(ValueError, "unknown card"):
            reconstruct_remote_deck(descriptor, self.database.load_card)

        self.assertIsNone(self.database.load_deck("not-in-host-deck-database"))

    def test_malformed_and_excessive_duplicate_compositions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing or malformed"):
            reconstruct_remote_deck(None, self.database.load_card)

        remote = self.database.load_deck("Killer Queen_1")
        descriptor = serialize_deck_selection(remote)
        descriptor["card_ids"] = [descriptor["card_ids"][0]] * 10
        with self.assertRaisesRegex(ValueError, "maximum"):
            reconstruct_remote_deck(descriptor, self.database.load_card)


class AuthoritativeGameplayTests(unittest.TestCase):
    def test_remote_turn_combines_card_selection_with_the_pass_option(self):
        first, second = object(), object()
        player = SimpleNamespace(hand=SimpleNamespace(cards=[first, second]))
        strategy = RemoteChoiceStrategy(player)

        class FakeChannel:
            def __init__(self):
                self.requests = []

            def request_action(self, choice_type, extra=None):
                self.requests.append((choice_type, extra))
                return 1

            def reject(self, *_args):
                self.fail("A valid card choice must not be rejected")

        channel = FakeChannel()
        strategy.channel = channel

        self.assertFalse(strategy.get_choice_pass())
        self.assertIs(strategy.get_choice_card(), second)
        self.assertEqual(len(channel.requests), 1)
        self.assertEqual(channel.requests[0][0], "play_or_pass")
        self.assertEqual(player.hand.cards, [first])

    def test_snapshot_does_not_include_opponent_hand_or_deck_order(self):
        ability = SimpleNamespace(name="", description="", is_active=False)
        local_card = SimpleNamespace(
            id="local-card",
            name="Local",
            hp=2,
            dmg=1,
            color="BLUE",
            power="NORMAL",
            ability=ability,
            owner=None,
        )
        secret_card = SimpleNamespace(
            id="secret-card",
            name="Secret",
            hp=3,
            dmg=2,
            color="RED",
            power="NORMAL",
            ability=ability,
            owner=None,
        )
        local = SimpleNamespace(
            id=2,
            score=0,
            passed=False,
            deck=SimpleNamespace(cards=[object(), object()]),
            graveyard=[],
            hand=SimpleNamespace(cards=[local_card]),
        )
        opponent = SimpleNamespace(
            id=1,
            score=1,
            passed=False,
            deck=SimpleNamespace(cards=[secret_card]),
            graveyard=[],
            hand=SimpleNamespace(cards=[secret_card]),
        )
        local_card.owner = local
        secret_card.owner = opponent
        board = SimpleNamespace(
            mana_pool=[],
            round=2,
            game_state="PLAY",
            player_on_turn=local,
            positions=[None] * 6,
            dragon=None,
            dragons=[],
            winner=None,
        )

        snapshot = serialize_game_state(board, local, opponent)

        self.assertEqual(snapshot["local"]["hand"][0]["id"], "local-card")
        self.assertEqual(snapshot["opponent"]["hand_count"], 1)
        self.assertNotIn("hand", snapshot["opponent"])
        self.assertNotIn("cards", snapshot["opponent"])
        self.assertNotIn("secret-card", repr(snapshot))

    def test_invalid_card_action_does_not_mutate_hand(self):
        card = object()
        player = SimpleNamespace(hand=SimpleNamespace(cards=[card]))
        strategy = RemoteChoiceStrategy(player)

        class FakeChannel:
            def __init__(self):
                self.values = iter((-1, 0))
                self.rejections = []

            def request_action(self, *_args, **_kwargs):
                return next(self.values)

            def reject(self, _request_id, reason):
                self.rejections.append(reason)

        strategy.channel = FakeChannel()
        selected = strategy.get_choice_card()
        self.assertIs(selected, card)
        self.assertEqual(player.hand.cards, [])
        self.assertEqual(len(strategy.channel.rejections), 1)


class LoopbackTransportTests(unittest.TestCase):
    def _wait_for(self, predicate, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = predicate()
            if result:
                return result
            time.sleep(0.01)
        self.fail("Timed out waiting for loopback LAN event")

    def test_host_and_client_exchange_framed_messages_and_clean_up(self):
        host = LanHost("127.0.0.1", 0)
        client = LanClient()
        try:
            host.start()
            client.connect("127.0.0.1", host.port)
            self._wait_for(lambda: host.peer and client.peer)

            client.peer.send(MessageType.HELLO, hello_payload("Guest"))
            host_message = self._wait_for(
                lambda: next(
                    (event.message for event in host.poll() if event.kind == "message"),
                    None,
                )
            )
            self.assertEqual(host_message.type, MessageType.HELLO.value)

            host.peer.send(MessageType.HELLO_ACCEPTED, {"host": "Host"})
            client_message = self._wait_for(
                lambda: next(
                    (event.message for event in client.poll() if event.kind == "message"),
                    None,
                )
            )
            self.assertEqual(client_message.type, MessageType.HELLO_ACCEPTED.value)
        finally:
            client.close()
            host.close()

        self.assertFalse(host._thread.is_alive())
        self.assertFalse(client._thread.is_alive())

    def test_client_cancellation_notifies_host_and_host_keeps_listening(self):
        host = LanHost("127.0.0.1", 0)
        client = LanClient()
        try:
            host.start()
            client.connect("127.0.0.1", host.port)
            self._wait_for(lambda: host.peer and client.peer)

            client.close()
            events = []

            def disconnected():
                events.extend(host.poll())
                return host.peer is None

            self._wait_for(disconnected)
            self.assertTrue(
                any(
                    event.kind == "disconnected"
                    or (
                        event.message
                        and event.message.type == MessageType.DISCONNECT.value
                    )
                    for event in events
                )
            )
            self.assertEqual(host.state.value, "listening")
        finally:
            client.close()
            host.close()

    def test_idle_peer_times_out_and_worker_stops(self):
        left, right = socket.socketpair()
        peer = SocketPeer(
            left,
            ("local", 0),
            heartbeat_interval=10.0,
            idle_timeout=0.08,
        )
        try:
            event = self._wait_for(
                lambda: next(
                    (item for item in peer.poll() if item.kind == "error"),
                    None,
                )
            )
            self.assertIn("timed out", event.detail)
            self._wait_for(lambda: not peer._thread.is_alive())
        finally:
            peer.close()
            right.close()

    def test_protocol_mismatch_closes_only_the_bad_peer(self):
        host = LanHost("127.0.0.1", 0)
        raw_client = None
        try:
            host.start()
            raw_client = socket.create_connection(("127.0.0.1", host.port), timeout=1)
            self._wait_for(lambda: host.peer)
            body = json.dumps(
                {
                    "type": "hello",
                    "sequence": 0,
                    "protocol_version": 999,
                    "application_version": "1.0",
                    "payload": {"player_name": "Old client"},
                }
            ).encode("utf-8")
            raw_client.sendall(HEADER.pack(len(body)) + body)
            error = self._wait_for(
                lambda: next(
                    (
                        event
                        for event in host.poll()
                        if event.kind == "error" and "Protocol mismatch" in event.detail
                    ),
                    None,
                )
            )
            self.assertIn("expected", error.detail)
            self._wait_for(lambda: host.peer is None or not host.peer.alive)
        finally:
            if raw_client is not None:
                raw_client.close()
            host.close()

    def test_authoritative_host_and_guest_complete_a_match(self):
        host = LanHost("127.0.0.1", 0)
        client = LanClient()
        try:
            host.start()
            client.connect("127.0.0.1", host.port)
            self._wait_for(lambda: host.peer and client.peer)

            lobby = HostLobbyController(
                "Host",
                validate_deck=lambda deck_id: DBUtil().load_deck(deck_id) is not None,
                reconstruct_guest_deck=lambda descriptor: reconstruct_remote_deck(
                    descriptor,
                    DBUtil().load_card,
                ),
            )
            client.peer.send(MessageType.HELLO, hello_payload("Guest"))
            hello = self._wait_for(
                lambda: next(
                    (event.message for event in host.poll() if event.message),
                    None,
                )
            )
            response, lobby_payload = lobby.handle(hello)
            host.peer.send(response, lobby_payload, request_id=hello.request_id)
            accepted = self._wait_for(
                lambda: next(
                    (event.message for event in client.poll() if event.message),
                    None,
                )
            )
            self.assertEqual(accepted.type, MessageType.HELLO_ACCEPTED.value)

            lobby.select_host_deck("Starter Blue_1")
            lobby.set_host_ready(True)
            client.peer.send(
                MessageType.SELECT_DECK,
                {
                    "deck": serialize_deck_selection(
                        DBUtil().load_deck("Killer Queen_1")
                    )
                },
            )
            select_message = self._wait_for(
                lambda: next(
                    (event.message for event in host.poll() if event.message),
                    None,
                )
            )
            response, lobby_payload = lobby.handle(select_message)
            host.peer.send(response, lobby_payload)
            self._wait_for(
                lambda: next(
                    (event.message for event in client.poll() if event.message),
                    None,
                )
            )
            client.peer.send(MessageType.READY, {"ready": True})
            ready_message = self._wait_for(
                lambda: next(
                    (event.message for event in host.poll() if event.message),
                    None,
                )
            )
            response, lobby_payload = lobby.handle(ready_message)
            host.peer.send(response, lobby_payload)
            self.assertTrue(lobby.state.can_start)
            self._wait_for(
                lambda: next(
                    (event.message for event in client.poll() if event.message),
                    None,
                )
            )

            host.peer.send(
                MessageType.START_MATCH,
                {
                    "match_id": "integration-match",
                    "seed": 99173,
                    "starting_player_id": 1,
                    "host_deck_id": "Starter Blue_1",
                    "guest_deck_id": "Killer Queen_1",
                },
                match_id="integration-match",
            )
            start_message = self._wait_for(
                lambda: next(
                    (
                        event.message
                        for event in client.poll()
                        if event.message
                        and event.message.type == MessageType.START_MATCH.value
                    ),
                    None,
                )
            )
            self.assertEqual(start_message.match_id, "integration-match")

            first = Player(1, DBUtil().load_deck("Starter Blue_1"), ChoiceStrategyAIRandom)
            second = Player(2, DBUtil().load_deck("Killer Queen_1"), RemoteChoiceStrategy)
            board = Board()
            channel = HostMatchChannel(
                host,
                "integration-match",
                lambda: serialize_game_state(board, second, first),
            )
            second.choice_strategy.channel = channel
            result_holder = []
            error_holder = []

            def play():
                try:
                    result_holder.append(
                        run_game(
                            first,
                            second,
                            network_display_strategy(channel),
                            board,
                            seed=99173,
                            starting_player_id=1,
                        )
                    )
                except Exception as error:
                    error_holder.append(error)

            game_thread = threading.Thread(target=play, daemon=True)
            game_thread.start()
            deadline = time.monotonic() + 10
            choice_count = 0
            choice_types = {}
            protocol_errors = []
            while game_thread.is_alive() and time.monotonic() < deadline:
                for event in client.poll():
                    if event.kind != "message" or not event.message:
                        continue
                    if event.message.type == MessageType.ERROR.value:
                        protocol_errors.append(event.message.payload)
                        continue
                    if event.message.type != MessageType.CHOICE_REQUEST.value:
                        continue
                    payload = event.message.payload or {}
                    choice_type = payload.get("choice_type")
                    choice_types[choice_type] = choice_types.get(choice_type, 0) + 1
                    legal = payload.get("legal_indices", [])
                    if choice_type in ("pass", "use_ability"):
                        value = False
                    elif legal:
                        value = legal[0]
                    else:
                        value = 0
                    client.peer.send(
                        MessageType.PLAYER_ACTION,
                        {"value": value},
                        request_id=event.message.request_id,
                        match_id=event.message.match_id,
                    )
                    choice_count += 1
                time.sleep(0.002)
            game_thread.join(timeout=1)

            self.assertFalse(
                game_thread.is_alive(),
                (
                    "LAN match did not finish: "
                    f"choices={choice_count}, round={board.round}, "
                    f"state={board.game_state}, disconnected={channel.disconnected}, "
                    f"error={channel.error!r}, types={choice_types}, "
                    f"protocol_errors={protocol_errors[-3:]}"
                ),
            )
            self.assertEqual(error_holder, [])
            self.assertEqual(len(result_holder), 1)
            self.assertGreater(choice_count, 0)
            self.assertGreaterEqual(result_holder[0].rounds, 1)

            host.peer.send(
                MessageType.MATCH_RESULT,
                {"result": vars(result_holder[0])},
                match_id="integration-match",
            )
            result_message = self._wait_for(
                lambda: next(
                    (
                        event.message
                        for event in client.poll()
                        if event.message
                        and event.message.type == MessageType.MATCH_RESULT.value
                    ),
                    None,
                )
            )
            self.assertEqual(result_message.match_id, "integration-match")
            client.peer.send(
                MessageType.RETURN_TO_LOBBY,
                {},
                match_id="integration-match",
            )
            return_message = self._wait_for(
                lambda: next(
                    (event.message for event in host.poll() if event.message),
                    None,
                )
            )
            lobby.handle(return_message)
            self.assertFalse(lobby.state.host.ready)
            self.assertFalse(lobby.state.guest.ready)
        finally:
            client.close()
            host.close()


if __name__ == "__main__":
    unittest.main()
