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

    def _return(self):
        self.run_display = False
        self.game.curr_menu = self.previous_menu
        if self.previous_menu is not None:
            self.previous_menu.__init__(self.game)
            self.previous_menu.run_display = True

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
        if not self.game.START_KEY:
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
        while self.run_display:
            self.game.check_events()
            self.check_input()
            if not self.run_display:
                break
            self.game.display.fill(self.game.BLACK)
            self.game.draw_text(
                "Deck Menu",
                self.TEXT_LARGE,
                self.mid_w,
                self.mid_h - 40,
            )
            return_y = self.mid_h + 25
            create_y = return_y + self.TEXT_NORMAL
            deck_start_y = create_y + self.TEXT_NORMAL * 2
            self.game.draw_text("Return", self.TEXT_NORMAL, self.mid_w, return_y)
            self.game.draw_text(
                "Create deck",
                self.TEXT_NORMAL,
                self.mid_w,
                create_y,
            )

            deck_selected = max(0, self.selected - 2)
            deck_offset = max(
                0,
                min(
                    deck_selected - self.PAGE_SIZE + 1,
                    len(self.deck_ids) - self.PAGE_SIZE,
                ),
            )
            for row, deck_id in enumerate(
                self.deck_ids[deck_offset : deck_offset + self.PAGE_SIZE]
            ):
                self.game.draw_text(
                    deck_id,
                    self.TEXT_NORMAL,
                    self.mid_w,
                    deck_start_y + row * self.TEXT_NORMAL,
                )

            if self.selected == 0:
                cursor_y = return_y
            elif self.selected == 1:
                cursor_y = create_y
            else:
                cursor_y = (
                    deck_start_y
                    + (deck_selected - deck_offset) * self.TEXT_NORMAL
                )
            self.cursor_rect.midtop = (
                self.mid_w + self.offset,
                cursor_y,
            )
            self.draw_cursor()
            if self.selected >= 2:
                deck = DBUtil().load_deck(self.items[self.selected])
                if deck:
                    self.game.draw_text(
                        f"{len(deck.cards)} cards",
                        self.TEXT_NORMAL,
                        self.mid_w,
                        555,
                    )
            self.blit_screen()
