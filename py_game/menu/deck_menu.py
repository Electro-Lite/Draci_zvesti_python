from __future__ import annotations

from typing import TYPE_CHECKING

from py_game.deck_editor import DeckBuilderMenu
from py_game.menu.base_menu import Menu
from utils.database_utils import DBUtil

if TYPE_CHECKING:
    from py_game.game import Game


class DeckMenu(Menu):
    PAGE_SIZE = 10

    def __init__(self, game: "Game"):
        super().__init__(game)
        self.previous_menu = None
        self.deck_ids = DBUtil().get_all_deck_ids()
        self.items = ["Back", "Create deck", *self.deck_ids]
        self.selected = 0
        self._visible_offset = 0

    def _return(self):
        self.return_to_previous()

    def _open_editor(self, deck_id=None):
        self.run_display = False
        editor = DeckBuilderMenu(self.game, deck_id)
        self.game.curr_menu = editor
        editor.previous_menu = self
        editor.display_menu()

    def check_input(self):
        if self.game.UP_KEY:
            self.selected = (self.selected - 1) % len(self.items)
        if self.game.DOWN_KEY:
            self.selected = (self.selected + 1) % len(self.items)
        if self.game.BACK_KEY:
            self._return()
            return
        clicked = self.clicked_button()
        if clicked is not None:
            self.selected = self._visible_offset + clicked
        if not (self.game.START_KEY or clicked is not None):
            return
        if self.selected == 0:
            self._return()
        elif self.selected == 1:
            self._open_editor()
        else:
            self._open_editor(self.items[self.selected])

    def display_menu(self):
        self.run_display = True
        self.game.reset_keys()
        while self.run_display and self.game.running:
            self.begin_frame()
            if self.game.mouse_wheel:
                self.selected = (self.selected - self.game.mouse_wheel) % len(self.items)
            page_size = max(4, min(self.PAGE_SIZE, (self.game.DISPLAY_H - 190) // self.game.layout.target_height))
            offset = max(0, min(self.selected - page_size + 1, len(self.items) - page_size))
            self._visible_offset = offset
            visible = self.items[offset : offset + page_size]
            self.build_menu_buttons(
                visible,
                self.selected - offset,
                top_ratio=0.22,
                bottom_ratio=0.86,
                width_ratio=0.64,
            )
            self.check_input()
            if not self.run_display:
                break
            self.draw_background()
            self.draw_title("Deck Management", "Create a deck or select one to edit")
            self.draw_buttons()
            detail = ""
            if self.selected >= 2:
                deck = DBUtil().load_deck(self.items[self.selected])
                if deck:
                    detail = f"{len(deck.cards)} cards  •  {deck.description or 'No description'}"
            self.draw_message(detail, self.game.palette.muted)
            self.blit_screen()
