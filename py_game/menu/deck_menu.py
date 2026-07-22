import pygame as pg
from typing import TYPE_CHECKING
from enum import Enum
from py_game.menu.base_menu import Menu
from py_game.menu.options_menu import OptionsMenu
from py_game.menu.basic_play_menu import BasicPlayMenu
from utils.database_utils import DBUtil
from py_game.deck_editor import DeckBuilderMenu

if TYPE_CHECKING:
    from py_game.game import Game

class DeckMenuStates(Enum):
    RETURN   = 1
    NEW      = 2
    DECK     = 3

class DeckMenu(Menu):
    def __init__(self, game: 'Game'):
        Menu.__init__(self, game)
        self.state = DeckMenuStates.RETURN

        # Define coordinates for menu items
        self.return_x, self.return_y = self.mid_w, self.mid_h + 10 + self.TEXT_NORMAL * 1
        self.new_x, self.new_y       = self.mid_w, self.mid_h + 10 + self.TEXT_NORMAL * 2

        self.DECK_LIST = DBUtil().get_all_deck_ids()
        self.deck_pos = []
        for i in range(len(self.DECK_LIST)):
            self.deck_pos.append({
                'x': self.mid_w,
                'y': self.mid_h + 10 + self.TEXT_NORMAL * (4 + i)
            })

        self.cursor_rect.midtop = (self.return_x + self.offset, self.return_y)

    def display_menu(self):
        self.run_display = True

        self.game.START_KEY = False
        self.game.DOWN_KEY = False
        self.game.UP_KEY = False

        while self.run_display:
            self.game.check_events()
            self.check_input()
            self.move_cursor()

            self.game.display.fill(self.game.BLACK)

            # Draw Title
            self.game.draw_text('Deck Menu', self.TEXT_LARGE, self.game.DISPLAY_W / 2, self.game.DISPLAY_H / 2 - 40)

            # Draw Options
            self.game.draw_text("Return", self.TEXT_NORMAL, self.return_x, self.return_y)
            self.game.draw_text("Create deck", self.TEXT_NORMAL, self.new_x, self.new_y)
            for i in range(len(self.DECK_LIST)):
                self.game.draw_text(
                    self.DECK_LIST[i],
                    self.TEXT_NORMAL,
                    self.deck_pos[i]['x'],
                    self.deck_pos[i]['y']
                )

            self.draw_cursor()
            self.blit_screen()

    def move_cursor(self):
        # DOWN KEY LOGIC
        if self.game.DOWN_KEY:
            self.game.DOWN_KEY = False # Consume the input
            if self.state == DeckMenuStates.RETURN:
                self.cursor_rect.midtop = (self.new_x + self.offset, self.new_y)
                self.state = DeckMenuStates.NEW
            elif self.state == DeckMenuStates.NEW:
                # Adding a safety check in case the database returns 0 decks
                if len(self.DECK_LIST) > 0:
                    self.cursor_rect.midtop = (self.deck_pos[0]['x'] + self.offset, self.deck_pos[0]['y'])
                    self.CUR_DECK = 0
                    self.state = DeckMenuStates.DECK
                else:
                    self.cursor_rect.midtop = (self.return_x + self.offset, self.return_y)
                    self.state = DeckMenuStates.RETURN

            elif self.state == DeckMenuStates.DECK:
                if self.CUR_DECK < len(self.DECK_LIST) - 1:
                    self.CUR_DECK += 1
                    self.cursor_rect.midtop = (self.deck_pos[self.CUR_DECK]['x'] + self.offset, self.deck_pos[self.CUR_DECK]['y'])
                else:
                    self.state = DeckMenuStates.RETURN
                    self.cursor_rect.midtop = (self.return_x + self.offset, self.return_y)

        # UP KEY LOGIC
        if self.game.UP_KEY:
            self.game.UP_KEY = False # Consume the input
            if self.state == DeckMenuStates.RETURN:
                # Wrap around to the bottom of the list (last deck)
                if len(self.DECK_LIST) > 0:
                    self.CUR_DECK = len(self.DECK_LIST) - 1
                    self.state = DeckMenuStates.DECK
                    self.cursor_rect.midtop = (self.deck_pos[self.CUR_DECK]['x'] + self.offset, self.deck_pos[self.CUR_DECK]['y'])
                else:
                    # If there are no decks, wrap around to NEW instead
                    self.state = DeckMenuStates.NEW
                    self.cursor_rect.midtop = (self.new_x + self.offset, self.new_y)

            elif self.state == DeckMenuStates.NEW:
                # Move up to RETURN
                self.state = DeckMenuStates.RETURN
                self.cursor_rect.midtop = (self.return_x + self.offset, self.return_y)

            elif self.state == DeckMenuStates.DECK:
                # If we are at the first deck, move up to NEW
                if self.CUR_DECK > 0:
                    self.CUR_DECK -= 1
                    self.cursor_rect.midtop = (self.deck_pos[self.CUR_DECK]['x'] + self.offset, self.deck_pos[self.CUR_DECK]['y'])
                else:
                    self.state = DeckMenuStates.NEW
                    self.cursor_rect.midtop = (self.new_x + self.offset, self.new_y)

    def check_input(self):
        if self.game.START_KEY:
            self.game.START_KEY = False
            if self.state == DeckMenuStates.RETURN:
                self.run_display = False
                self.game.curr_menu = self.previous_menu
                self.previous_menu.__init__(self.game)
                self.previous_menu.run_display = True
            else:
                self.run_display = False

                if self.state == DeckMenuStates.NEW:
                    deck_builder_menu = DeckBuilderMenu(self.game)
                elif self.state == DeckMenuStates.DECK:
                    deck_builder_menu = DeckBuilderMenu(self.game, self.DECK_LIST[self.CUR_DECK])

                self.game.curr_menu = deck_builder_menu
                deck_builder_menu.previous_menu = self

                deck_builder_menu.run_display = True
                deck_builder_menu.display_menu()
