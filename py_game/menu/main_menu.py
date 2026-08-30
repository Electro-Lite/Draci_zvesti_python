import pygame as pg
from typing import TYPE_CHECKING
from enum import Enum

from py_game.menu.base_menu import Menu
from py_game.menu.options_menu import OptionsMenu
from py_game.menu.basic_play_menu import BasicPlayMenu
from py_game.menu.deck_menu import DeckMenu
from py_game.menu.training_menu import TrainingMenu

if TYPE_CHECKING:
    from py_game.game import Game


class MainMenuStates(Enum):
    START = 1
    DECKS = 2
    TRAIN = 3
    OPTIONS = 4
    CREDITS = 5
    QUIT = 6


class MainMenu(Menu):
    def __init__(self, game: "Game"):
        Menu.__init__(self, game)
        self.state = MainMenuStates.START

        self.startx, self.starty = (
            self.mid_w,
            self.mid_h + 10 + self.TEXT_NORMAL,
        )
        self.decksx, self.decksy = (
            self.mid_w,
            self.mid_h + 10 + self.TEXT_NORMAL * 2,
        )
        self.trainx, self.trainy = (
            self.mid_w,
            self.mid_h + 10 + self.TEXT_NORMAL * 3,
        )
        self.optionsx, self.optionsy = (
            self.mid_w,
            self.mid_h + 10 + self.TEXT_NORMAL * 4,
        )
        self.creditsx, self.creditsy = (
            self.mid_w,
            self.mid_h + 10 + self.TEXT_NORMAL * 5,
        )
        self.quitx, self.quity = (
            self.mid_w,
            self.mid_h + 10 + self.TEXT_NORMAL * 6,
        )
        self.cursor_rect.midtop = (self.startx + self.offset, self.starty)

    def display_menu(self):
        self.run_display = True
        while self.run_display:
            self.game.check_events()
            self.check_input()
            self.move_cursor()

            self.game.display.fill(self.game.BLACK)
            self.game.draw_text(
                "Main Menu",
                self.TEXT_LARGE,
                self.game.DISPLAY_W / 2,
                self.game.DISPLAY_H / 2 - 40,
            )
            self.game.draw_text("Start Game", self.TEXT_NORMAL, self.startx, self.starty)
            self.game.draw_text("Manage Decks", self.TEXT_NORMAL, self.decksx, self.decksy)
            self.game.draw_text("Train AI", self.TEXT_NORMAL, self.trainx, self.trainy)
            self.game.draw_text("Options", self.TEXT_NORMAL, self.optionsx, self.optionsy)
            self.game.draw_text("Credits", self.TEXT_NORMAL, self.creditsx, self.creditsy)
            self.game.draw_text("Quit", self.TEXT_NORMAL, self.quitx, self.quity)
            self.draw_cursor()
            self.blit_screen()

    def move_cursor(self):
        if self.game.DOWN_KEY:
            if self.state == MainMenuStates.START:
                self.state = MainMenuStates.DECKS
                position = (self.decksx, self.decksy)
            elif self.state == MainMenuStates.DECKS:
                self.state = MainMenuStates.TRAIN
                position = (self.trainx, self.trainy)
            elif self.state == MainMenuStates.TRAIN:
                self.state = MainMenuStates.OPTIONS
                position = (self.optionsx, self.optionsy)
            elif self.state == MainMenuStates.OPTIONS:
                self.state = MainMenuStates.CREDITS
                position = (self.creditsx, self.creditsy)
            elif self.state == MainMenuStates.CREDITS:
                self.state = MainMenuStates.QUIT
                position = (self.quitx, self.quity)
            else:
                self.state = MainMenuStates.START
                position = (self.startx, self.starty)
            self.cursor_rect.midtop = (position[0] + self.offset, position[1])

        if self.game.UP_KEY:
            if self.state == MainMenuStates.START:
                self.state = MainMenuStates.QUIT
                position = (self.quitx, self.quity)
            elif self.state == MainMenuStates.DECKS:
                self.state = MainMenuStates.START
                position = (self.startx, self.starty)
            elif self.state == MainMenuStates.TRAIN:
                self.state = MainMenuStates.DECKS
                position = (self.decksx, self.decksy)
            elif self.state == MainMenuStates.OPTIONS:
                self.state = MainMenuStates.TRAIN
                position = (self.trainx, self.trainy)
            elif self.state == MainMenuStates.CREDITS:
                self.state = MainMenuStates.OPTIONS
                position = (self.optionsx, self.optionsy)
            else:
                self.state = MainMenuStates.CREDITS
                position = (self.creditsx, self.creditsy)
            self.cursor_rect.midtop = (position[0] + self.offset, position[1])

    def _open_menu(self, menu_class):
        self.run_display = False
        menu = menu_class(self.game)
        self.game.curr_menu = menu
        menu.previous_menu = self
        menu.display_menu()

    def check_input(self):
        if not self.game.START_KEY:
            return
        if self.state == MainMenuStates.START:
            self._open_menu(BasicPlayMenu)
        elif self.state == MainMenuStates.DECKS:
            self._open_menu(DeckMenu)
        elif self.state == MainMenuStates.TRAIN:
            self._open_menu(TrainingMenu)
        elif self.state == MainMenuStates.OPTIONS:
            self._open_menu(OptionsMenu)
        elif self.state == MainMenuStates.QUIT:
            self.run_display = False
            self.game.playing = False
            self.game.running = False
