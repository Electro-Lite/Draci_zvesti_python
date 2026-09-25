from __future__ import annotations

from typing import TYPE_CHECKING

import pygame as pg

from py_game.menu.base_menu import Menu
from py_game.menu.basic_play_menu import BasicPlayMenu
from py_game.menu.deck_menu import DeckMenu
from py_game.menu.lan_menu import LanMenu
from py_game.menu.options_menu import OptionsMenu
from py_game.menu.training_menu import TrainingMenu

if TYPE_CHECKING:
    from py_game.game import Game


class MainMenu(Menu):
    ITEMS = (
        "Local Match",
        "LAN Match",
        "Manage Decks",
        "AI Training",
        "Settings",
        "Credits",
        "Quit",
    )

    def __init__(self, game: "Game"):
        super().__init__(game)
        self.selected = 0

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
            self._open_menu(DeckMenu)
        elif self.selected == 3:
            self._open_menu(TrainingMenu)
        elif self.selected == 4:
            self._open_menu(OptionsMenu)
        elif self.selected == 5:
            self._credits_dialog()
        else:
            self.game.request_quit()

    def check_input(self):
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
        while self.run_display and self.game.running:
            self.begin_frame()
            self.build_menu_buttons(
                list(self.ITEMS),
                self.selected,
                top_ratio=0.25,
                bottom_ratio=0.91,
                width_ratio=0.46,
            )
            self.check_input()
            if not self.run_display:
                break
            self.draw_background()
            self.draw_title(
                "Dračí zvěsti",
                "Build a deck, challenge a rival, and face the dragons",
            )
            self.draw_buttons()
            self.game.draw_text(
                "Arrow keys / mouse to navigate  •  Enter to select  •  Esc to go back",
                self.game.layout.font_small,
                self.mid_w,
                self.game.DISPLAY_H - self.game.layout.margin,
                self.game.palette.muted,
            )
            self.blit_screen()

    def _credits_dialog(self):
        self.game.reset_keys()
        while self.game.running:
            self.begin_frame()
            if self.game.BACK_KEY or self.game.START_KEY or self.game.mouse_clicked:
                self.game.reset_keys()
                return
            self.draw_background()
            panel = self.game.layout.centered_panel(0.70, 0.62)
            rect = pg.Rect(panel.x, panel.y, panel.width, panel.height)
            pg.draw.rect(self.game.display, self.game.palette.panel, rect, border_radius=12)
            pg.draw.rect(self.game.display, self.game.palette.border, rect, 2, border_radius=12)
            lines = (
                ("Dračí zvěsti", self.game.layout.font_large, self.game.palette.accent),
                ("Card game and AI training environment", self.game.layout.font_normal, self.game.palette.text),
                ("University project developed at UPOL", self.game.layout.font_normal, self.game.palette.text),
                ("Press Enter, Escape, or click to return", self.game.layout.font_small, self.game.palette.muted),
            )
            spacing = panel.height // (len(lines) + 1)
            for index, (text, size, color) in enumerate(lines, start=1):
                self.game.draw_text(text, size, panel.center[0], panel.y + spacing * index, color)
            self.blit_screen()
