import json
import queue
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pygame as pg

from py_game.settings import AppSettings, SettingsStore
from py_game.menu.lan_menu import LanMenu
from py_game.menu.basic_play_menu import BasicPlayMenu
from py_game.network.lobby import HostLobbyController, LobbyPlayer
from py_game.network.protocol import MessageType, ProtocolMessage
from py_game.network.session import NetworkEvent
from py_game.theme import PALETTE
from py_game.ui.layout import LayoutMetrics, RectSpec
from py_game.ui.training_dashboard import training_dashboard_layout
from py_game.ui.training_cockpit import TrainingCockpitState, training_cockpit_layout
from py_game.ui.widgets import Button, DragController, TextInput
from py_game.training_service import TrainingKind
from utils.database_utils import DBUtil


class LayoutTests(unittest.TestCase):
    def test_metrics_scale_and_keep_usable_minimums(self):
        small = LayoutMetrics.from_size(320, 200)
        large = LayoutMetrics.from_size(1920, 1080)

        self.assertEqual((small.width, small.height), (640, 480))
        self.assertGreaterEqual(small.target_height, 42)
        self.assertGreater(large.font_normal, small.font_normal)

    def test_rows_fit_without_overlap(self):
        metrics = LayoutMetrics.from_size(1280, 720)
        area = RectSpec(100, 100, 500, 420)
        rows = metrics.vertical_rows(6, area)

        self.assertEqual(len(rows), 6)
        for previous, current in zip(rows, rows[1:]):
            self.assertLessEqual(previous.bottom, current.y)
        self.assertLessEqual(rows[-1].bottom, area.bottom)

    def test_columns_cover_available_width(self):
        metrics = LayoutMetrics.from_size(1024, 768)
        area = RectSpec(20, 30, 900, 400)
        columns = metrics.columns(area, (1, 2, 1))

        self.assertEqual(columns[0].x, area.x)
        self.assertEqual(columns[-1].right, area.right)
        self.assertLess(columns[0].right, columns[1].x)

    def test_card_size_respects_height_and_area(self):
        metrics = LayoutMetrics.from_size(800, 600)
        area = RectSpec(20, 20, 760, 150)
        width, height, gap = metrics.card_size(area, 6)

        self.assertLessEqual(height, area.height)
        self.assertLessEqual(width * 6 + gap * 5, area.width)

    def test_training_dashboard_regions_fit_without_overlap_at_supported_sizes(self):
        for size in ((800, 600), (1024, 768), (1280, 720), (1920, 1080)):
            layout = training_dashboard_layout(LayoutMetrics.from_size(*size))
            self.assertLessEqual(layout["tabs"].bottom, layout["content"].y)
            self.assertLessEqual(layout["hero"].right, layout["trail"].x)
            self.assertLessEqual(layout["hero"].bottom, layout["systems"].y)
            self.assertLessEqual(layout["systems"].bottom, layout["footer"].y)
            for key in ("hero", "trail", "systems", "footer"):
                self.assertGreater(layout[key].width, 0)
                self.assertGreater(layout[key].height, 0)

    def test_training_cockpit_uses_wide_columns_and_compact_scrolling(self):
        for size in ((1280, 720), (1600, 900)):
            layout = training_cockpit_layout(
                LayoutMetrics.from_size(*size),
                TrainingKind.PLAYER_DECK,
            )
            self.assertEqual(layout.mode, "wide")
            self.assertLessEqual(layout.panels["rail"].right, layout.panels["config"].x)
            self.assertLessEqual(layout.panels["config"].right, layout.panels["summary"].x)
            self.assertLessEqual(layout.controls["launch"].bottom, layout.panels["summary"].bottom)

        compact = training_cockpit_layout(
            LayoutMetrics.from_size(640, 480),
            TrainingKind.DECK_BUILDER,
        )
        self.assertEqual(compact.mode, "compact")
        self.assertGreater(compact.max_scroll, 0)
        self.assertGreaterEqual(compact.controls["launch"].y, compact.viewport.bottom)
        scrolled = training_cockpit_layout(
            LayoutMetrics.from_size(640, 480),
            TrainingKind.DECK_BUILDER,
            scroll=compact.max_scroll,
        )
        self.assertLess(scrolled.panels["summary"].y, compact.panels["summary"].y)


class TrainingCockpitStateTests(unittest.TestCase):
    def test_mission_drafts_survive_switching_and_preset_edits_become_custom(self):
        state = TrainingCockpitState(("Blue", "Queen"))
        state.set_value("run_label", "controller-study")
        state.set_value("workers", "17")
        self.assertEqual(state.preset_label, "Custom")

        state.switch(TrainingKind.DECK_BUILDER)
        state.set_value("run_label", "builder-study")
        state.set_value("seeds", "400009, 450001, 400009")
        state.switch(TrainingKind.PLAYER_DECK)

        self.assertEqual(state.value("run_label"), "controller-study")
        self.assertEqual(state.value("workers"), "17")
        state.switch(TrainingKind.DECK_BUILDER)
        self.assertEqual(state.value("run_label"), "builder-study")
        self.assertEqual(state.validate().request.seeds, (400009, 450001, 400009))

    def test_direct_values_map_exactly_to_player_request(self):
        state = TrainingCockpitState(("Blue", "Queen"))
        values = {
            "run_label": "exact-player",
            "deck_id": "Queen",
            "opponent_deck_id": "Blue",
            "evaluator_generations": "9999",
            "workers": "127",
            "evaluation_games": "99999",
        }
        for key, value in values.items():
            state.set_value(key, value)

        validation = state.validate()

        self.assertTrue(validation.valid)
        self.assertEqual(validation.request.run_label, "exact-player")
        self.assertEqual(validation.request.deck_id, "Queen")
        self.assertEqual(validation.request.opponent_deck_id, "Blue")
        self.assertEqual(validation.request.evaluator_generations, 9999)
        self.assertEqual(validation.request.workers, 127)
        self.assertEqual(validation.request.evaluation_games, 99999)

    def test_builder_validation_keeps_bad_text_visible_and_rejects_odd_matches(self):
        state = TrainingCockpitState(("Blue",))
        state.switch(TrainingKind.DECK_BUILDER)
        state.set_value("seeds", "10, nope, 30")
        state.set_value("matches_per_genome", "3")

        validation = state.validate()

        self.assertEqual(state.value("seeds"), "10, nope, 30")
        self.assertIn("seeds", validation.errors)
        self.assertIn("matches_per_genome", validation.errors)
        self.assertIsNone(validation.request)

    def test_empty_deck_database_disables_player_request(self):
        validation = TrainingCockpitState(()).validate()
        self.assertFalse(validation.valid)
        self.assertIn("deck_id", validation.errors)
        self.assertIn("opponent_deck_id", validation.errors)


class WidgetTests(unittest.TestCase):
    def test_button_hit_testing_respects_enabled_state(self):
        button = Button("play", "Play", RectSpec(10, 20, 100, 50))
        self.assertTrue(button.hit_test((20, 30)))
        button.enabled = False
        self.assertFalse(button.hit_test((20, 30)))

    def test_drag_requires_threshold_and_valid_target(self):
        drag = DragController(threshold=8)
        drag.begin("card:1", (10, 10), {"slot:2"})
        self.assertFalse(drag.move((14, 13)))
        self.assertTrue(drag.move((20, 10)))
        self.assertIsNone(drag.release("slot:1"))

        drag.begin("card:1", (10, 10), {"slot:2"})
        drag.move((20, 10))
        self.assertEqual(drag.release("slot:2"), ("card:1", "slot:2"))
        self.assertFalse(drag.dragging)

    def test_text_input_filters_and_edits(self):
        field = TextInput(max_length=3, validator=str.isdigit, focused=True)
        digit = SimpleNamespace(type=pg.KEYDOWN, key=pg.K_1, unicode="1")
        letter = SimpleNamespace(type=pg.KEYDOWN, key=pg.K_a, unicode="a")
        backspace = SimpleNamespace(type=pg.KEYDOWN, key=pg.K_BACKSPACE, unicode="")

        self.assertTrue(field.handle_event(digit))
        self.assertTrue(field.handle_event(letter))
        self.assertEqual(field.value, "1")
        field.handle_event(backspace)
        self.assertEqual(field.value, "")


class SettingsTests(unittest.TestCase):
    def test_settings_round_trip_and_ignore_unknown_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = SettingsStore(path)
            expected = AppSettings(width=1024, height=768, player_name="Lan Hero")
            store.save(expected)
            raw = json.loads(path.read_text())
            raw["future_setting"] = True
            path.write_text(json.dumps(raw))

            actual = store.load()

        self.assertEqual(actual.width, 1024)
        self.assertEqual(actual.player_name, "Lan Hero")

    def test_invalid_settings_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"lan_port": 2}')
            loaded = SettingsStore(path).load()
        self.assertEqual(loaded.lan_port, AppSettings().lan_port)

    def test_malformed_setting_types_fall_back_without_crashing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"player_name": 42, "fullscreen": "yes"}')
            loaded = SettingsStore(path).load()
        self.assertEqual(loaded, AppSettings())

    def test_validation_rejects_invalid_values(self):
        with self.assertRaisesRegex(ValueError, "LAN port"):
            AppSettings(lan_port=80).validate()


class LanMenuStateTests(unittest.TestCase):
    def _game(self):
        return SimpleNamespace(
            DISPLAY_W=1280,
            DISPLAY_H=720,
            TEXT_SMALL=16,
            TEXT_NORMAL=22,
            TEXT_LARGE=36,
            WHITE=PALETTE.text,
            palette=PALETTE,
            settings=AppSettings(player_name="Host"),
            settings_store=SimpleNamespace(save=lambda _settings: None),
        )

    def _menu(self):
        with (
            patch("py_game.menu.lan_menu.discover_local_ip", return_value="192.168.1.5"),
            patch.object(DBUtil, "get_all_deck_ids", return_value=["deck-1"]),
        ):
            return LanMenu(self._game())

    def test_host_waiting_and_ready_rows_expose_address_and_readiness(self):
        menu = self._menu()
        menu.mode = "host_lobby"
        menu.host = SimpleNamespace(port=47777)
        menu.lobby = HostLobbyController("Host", lambda _deck: True)

        waiting = menu._rows()
        self.assertIn("192.168.1.5:47777", waiting[2])
        self.assertIn("Waiting for player", waiting[3])
        self.assertFalse(menu._enabled()[4])

        menu.lobby.select_host_deck("deck-1")
        menu.lobby.set_host_ready(True)
        menu.lobby.state.guest = LobbyPlayer("Guest", "deck-1", True)
        menu.lobby._update_status()
        ready = menu._rows()
        self.assertIn("Guest — Ready", ready[3])
        self.assertTrue(menu._enabled()[4])

    def test_join_connection_and_error_states_have_usable_escape_actions(self):
        menu = self._menu()
        menu.mode = "join_setup"
        self.assertEqual(menu._rows()[-1], "Back")
        menu.mode = "connecting"
        self.assertEqual(menu._rows(), ["Connecting…", "Cancel"])
        self.assertEqual(menu._enabled(), [False, True])
        menu._set_error("Connection timed out")
        self.assertEqual(menu.message, "Connection timed out")
        self.assertEqual(menu.message_color, PALETTE.danger)

    def test_start_match_preserves_events_from_the_same_network_poll(self):
        menu = self._menu()
        start = NetworkEvent(
            "message",
            ProtocolMessage(
                type=MessageType.START_MATCH.value,
                sequence=1,
                payload={"match_id": "match-1"},
            ),
        )
        snapshot = NetworkEvent(
            "message",
            ProtocolMessage(
                type=MessageType.STATE_SNAPSHOT.value,
                sequence=2,
                payload={"status": "playing"},
            ),
        )

        class BatchedClient:
            def __init__(self):
                self.events = queue.Queue()
                self.peer = object()
                self._first = True

            def poll(self):
                if self._first:
                    self._first = False
                    return [start, snapshot]
                pending = []
                while not self.events.empty():
                    pending.append(self.events.get_nowait())
                return pending

        client = BatchedClient()
        seen = []
        menu.client = client
        menu.game.lan_client_game_loop = lambda active, _payload: seen.extend(
            active.poll()
        )

        menu._poll_network()

        self.assertEqual(seen, [snapshot])


class NavigationStateTests(unittest.TestCase):
    def test_local_match_returns_to_setup_with_selections_preserved(self):
        game = SimpleNamespace(
            DISPLAY_W=1280,
            DISPLAY_H=720,
            TEXT_SMALL=16,
            TEXT_NORMAL=22,
            TEXT_LARGE=36,
            WHITE=PALETTE.text,
            running=True,
            game_loop=Mock(),
        )
        menu = BasicPlayMenu(game)
        menu.p1_deck_id = "Starter Blue_1"
        menu.p2_deck_id = "Killer Queen_1"

        menu._start_match()

        game.game_loop.assert_called_once_with()
        self.assertIs(game.curr_menu, menu)
        self.assertTrue(menu.run_display)
        self.assertEqual(menu.p1_deck_id, "Starter Blue_1")
        self.assertEqual(menu.p2_deck_id, "Killer Queen_1")


if __name__ == "__main__":
    unittest.main()
