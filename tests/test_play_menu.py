import unittest
from types import SimpleNamespace

from py_game.menu.basic_play_menu import BasicPlayMenu
from py_game.menu.deck_menu import DeckMenu
from py_game.menu.lan_menu import LanMenu
from py_game.menu.main_menu import MainMenu
from py_game.menu.online_menu import OnlineMenu
from py_game.menu.play_menu import PlayMenu


def fake_game():
    return SimpleNamespace(
        DISPLAY_W=1280,
        DISPLAY_H=720,
        TEXT_SMALL=16,
        TEXT_NORMAL=24,
        TEXT_LARGE=40,
        palette=SimpleNamespace(muted=(0, 0, 0)),
    )


class MainMenuStructureTests(unittest.TestCase):
    def test_main_menu_has_one_play_entry(self):
        self.assertEqual(MainMenu.ITEMS[0], "Play")
        self.assertNotIn("Local Match", MainMenu.ITEMS)
        self.assertNotIn("LAN Match", MainMenu.ITEMS)

    def test_main_menu_routes_play_and_decks_after_restructure(self):
        menu = MainMenu(fake_game())
        opened = []
        menu._open_menu = opened.append

        menu.selected = 0
        menu._activate()
        menu.selected = 1
        menu._activate()

        self.assertEqual(opened, [PlayMenu, DeckMenu])


class PlayMenuStructureTests(unittest.TestCase):
    def test_play_menu_contains_requested_modes(self):
        self.assertEqual(
            PlayMenu.ITEMS[:4],
            (
                "Local Match",
                "LAN",
                "Online",
                "Campaign (Not implemented)",
            ),
        )

    def test_local_and_lan_open_existing_flows(self):
        menu = PlayMenu(fake_game())
        opened = []
        menu._open_menu = opened.append

        menu.selected = 0
        menu._activate()
        menu.selected = 1
        menu._activate()

        self.assertEqual(opened, [BasicPlayMenu, LanMenu])

    def test_online_opens_online_lobby_flow(self):
        menu = PlayMenu(fake_game())
        opened = []
        menu._open_menu = opened.append

        menu.selected = 2
        menu._activate()

        self.assertEqual(opened, [OnlineMenu])

    def test_unimplemented_campaign_stays_in_menu_and_explains_status(self):
        menu = PlayMenu(fake_game())

        menu.selected = 3
        menu._activate()
        self.assertIn("not implemented", menu.message.lower())
        self.assertTrue(menu.run_display)


if __name__ == "__main__":
    unittest.main()
