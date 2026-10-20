from __future__ import annotations

from typing import TYPE_CHECKING

from py_game.menu.base_menu import Menu
from py_game.menu.basic_play_menu import BasicPlayMenu
from py_game.menu.lan_menu import LanMenu
from py_game.menu.online_menu import OnlineMenu

if TYPE_CHECKING:
    from py_game.game import Game


class PlayMenu(Menu):
    """Choose how a match will be created."""

    ITEMS = (
        "Local Match",
        "LAN",
        "Online",
        "Campaign (Not implemented)",
        "Back",
    )

    def __init__(self, game: "Game"):
        super().__init__(game)
        self.selected = 0
        self.message = "Local, LAN, and relay-backed online play are available"

    def _open_menu(self, menu_class):
        self.run_display = False
        menu = menu_class(self.game)
        self.game.curr_menu = menu
        menu.previous_menu = self
        menu.display_menu()

    def _activate(self):
        if self.selected == 0:
            self._open_menu(BasicPlayMenu)
        elif self.selected == 1:
            self._open_menu(LanMenu)
        elif self.selected == 2:
            self._open_menu(OnlineMenu)
        elif self.selected == 3:
            self.message = "Campaign is not implemented yet"
        else:
            self.return_to_previous()

    def check_input(self):
        if self.game.BACK_KEY:
            self.return_to_previous()
            return
        if self.game.DOWN_KEY:
            self.selected = (self.selected + 1) % len(self.ITEMS)
        if self.game.UP_KEY:
            self.selected = (self.selected - 1) % len(self.ITEMS)
        clicked = self.clicked_button()
        if clicked is not None:
            self.selected = clicked
            self._activate()
        elif self.game.START_KEY:
            self._activate()

    def display_menu(self):
        self.run_display = True
        self.game.reset_keys()
        while self.run_display and self.game.running:
            self.begin_frame()
            self.build_menu_buttons(
                list(self.ITEMS),
                self.selected,
                top_ratio=0.25,
                bottom_ratio=0.86,
                width_ratio=0.50,
            )
            self.check_input()
            if not self.run_display:
                break
            self.draw_background()
            self.draw_title("Play", "Choose how you want to play")
            self.draw_buttons()
            self.draw_message(self.message)
            self.blit_screen()
