import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pygame as pg

from py_game.game import Game
from py_game.match_setup import ControllerKind, ControllerSpec
from py_game.network.gameplay import serialize_card
from py_game.theme import MANA_COLORS, PALETTE


class CardArtOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.font.init()

    def setUp(self):
        self.game = Game.__new__(Game)
        self.game.display = pg.Surface((240, 260))
        self.game.DISPLAY_W, self.game.DISPLAY_H = self.game.display.get_size()
        self.game.palette = PALETTE
        self.game.font_name = pg.font.get_default_font()
        art = pg.Surface((120, 170))
        art.fill((158, 139, 119))
        self.game.assets = SimpleNamespace(image=lambda *_args: art)
        self.game._card_image_path = lambda _card: "test-card.png"
        self.game.TEXT_SMALL = 17
        self.card = {
            "id": "test-card",
            "name": "Test Card",
            "dmg": 4,
            "hp": 2,
            "color": "BLUE",
            "mana_bonus": {"dmg": 1, "hp": 1},
            "owner": "local",
        }
        self.rect = pg.Rect(20, 20, 120, 170)

    def test_card_art_is_not_covered_by_a_bottom_name_stat_strip(self):
        self.game._draw_card_view(self.card, self.rect)

        self.assertEqual(self.game.display.get_at((80, 170))[:3], (158, 139, 119))
        self.assertNotEqual(self.game.display.get_at((32, 32))[:3], (158, 139, 119))

    def test_match_background_uses_the_active_mana_tint(self):
        transparent = pg.Surface(self.game.display.get_size(), pg.SRCALPHA)
        transparent.fill((0, 0, 0, 0))
        self.game.assets = SimpleNamespace(
            cover=Mock(return_value=transparent.copy()),
            tinted_cover=Mock(return_value=transparent.copy()),
        )

        self.game.draw_background("BLUE", match=True)

        self.game.assets.tinted_cover.assert_called_once_with(
            self.game.MATCH_BACKGROUND_PATH,
            self.game.display.get_size(),
            MANA_COLORS["BLUE"],
        )
        expected = self.game._mix_color(
            PALETTE.background,
            MANA_COLORS["BLUE"],
            self.game.BACKGROUND_MANA_BASE_STRENGTH,
        )
        self.assertEqual(self.game.display.get_at((0, 0))[:3], expected)

    def test_neutral_menu_and_match_backgrounds_use_different_art(self):
        transparent = pg.Surface(self.game.display.get_size(), pg.SRCALPHA)
        transparent.fill((0, 0, 0, 0))
        self.game.assets = SimpleNamespace(
            cover=Mock(return_value=transparent),
            tinted_cover=Mock(return_value=transparent),
        )

        self.game.draw_background()
        self.game.assets.cover.assert_called_with(
            self.game.MENU_BACKGROUND_PATH,
            self.game.display.get_size(),
        )
        self.game.draw_background(match=True)
        self.game.assets.cover.assert_called_with(
            self.game.MATCH_BACKGROUND_PATH,
            self.game.display.get_size(),
        )

    def test_missing_art_still_identifies_the_card(self):
        self.game._card_image_path = lambda _card: None
        self.game.draw_text_left = Mock()

        self.game._draw_card_view(self.card, self.rect)

        self.assertEqual(self.game.draw_text_left.call_args.args[0], "Test Card")

    def test_mana_marker_requires_matching_color_and_nonzero_bonus(self):
        center = (self.rect.centerx, self.rect.y + max(5, self.rect.width // 15) + 3)
        self.game._draw_card_view(self.card, self.rect, active_mana="RED")
        self.assertEqual(self.game.display.get_at(center)[:3], (158, 139, 119))

        self.game._draw_card_view(self.card, self.rect, active_mana="BLUE")
        self.assertNotEqual(self.game.display.get_at(center)[:3], (158, 139, 119))

        self.game.display.fill((0, 0, 0))
        no_bonus = dict(self.card, mana_bonus={"dmg": 0, "hp": 0})
        self.game._draw_card_view(no_bonus, self.rect, active_mana="BLUE")
        self.assertEqual(self.game.display.get_at(center)[:3], (158, 139, 119))

    def test_player_one_marker_switches_to_active_owner_in_hotseat(self):
        state = {
            "local": {"id": 2},
            "opponent": {"id": 1},
            "turn": "local",
        }
        self.assertEqual(Game._marked_board_owner(state, False), ("opponent", 1))
        self.assertEqual(Game._marked_board_owner(state, True), ("local", 2))
        self.assertEqual(
            Game._marked_board_owner({**state, "game_state": "BATTLE"}, True),
            (None, None),
        )

    def test_local_two_human_render_requests_current_player_markers(self):
        game = Game.__new__(Game)
        game.board = SimpleNamespace(player_on_turn=None, positions=[None] * 6)
        game.p1 = object()
        game.p2 = object()
        game.p1_controller = ControllerSpec(ControllerKind.HUMAN)
        game.p2_controller = ControllerSpec(ControllerKind.HUMAN)
        game.selected_card = None

        with patch("py_game.game.serialize_game_state", return_value={}), patch.object(
            game, "draw_match_state"
        ) as draw:
            game.draw_responsive_game()

        self.assertTrue(draw.call_args.kwargs["mark_current_player"])

    def test_visible_card_snapshot_contains_only_its_public_mana_bonus(self):
        owner = object()
        card = SimpleNamespace(
            id="test-card",
            name="Test Card",
            hp=2,
            dmg=4,
            color="BLUE",
            color_buf=(1, 2),
            power="NORMAL",
            ability=SimpleNamespace(name="", description="", is_active=False),
            owner=owner,
        )

        snapshot = serialize_card(card, owner)

        self.assertEqual(snapshot["mana_bonus"], {"dmg": 1, "hp": 2})


if __name__ == "__main__":
    unittest.main()
