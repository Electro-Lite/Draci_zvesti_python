import pygame as pg
from typing import TYPE_CHECKING
from enum import Enum
from py_game.menu.base_menu import Menu
from py_game.menu.options_menu import OptionsMenu
from py_game.menu.basic_play_menu import BasicPlayMenu

if TYPE_CHECKING:
    from py_game.game import Game

class MainMenuStates(Enum):
    START   = 1
    DECKS   = 2
    TRAIN   = 3
    OPTIONS = 4
    CREDITS = 5
    QUIT    = 6

class MainMenu(Menu):
    def __init__(self, game: 'Game'):
        Menu.__init__(self, game)
        self.state = MainMenuStates.START
        
        # Define coordinates for menu items
        self.startx, self.starty     = self.mid_w, self.mid_h + 10 + self.TEXT_NORMAL * 1
        self.decksx, self.decksy     = self.mid_w, self.mid_h + 10 + self.TEXT_NORMAL * 2
        self.trainx, self.trainy     = self.mid_w, self.mid_h + 10 + self.TEXT_NORMAL * 3
        self.optionsx, self.optionsy = self.mid_w, self.mid_h + 10 + self.TEXT_NORMAL * 4
        self.creditsx, self.creditsy = self.mid_w, self.mid_h + 10 + self.TEXT_NORMAL * 5
        self.quitx, self.quity       = self.mid_w, self.mid_h + 10 + self.TEXT_NORMAL * 6
        
        self.cursor_rect.midtop = (self.startx + self.offset, self.starty)

    def display_menu(self):
        self.run_display = True
        while self.run_display:
            self.game.check_events()
            self.check_input()
            self.move_cursor()
            
            self.game.display.fill(self.game.BLACK)
            
            # Draw Title
            self.game.draw_text('Main Menu', self.TEXT_LARGE, self.game.DISPLAY_W / 2, self.game.DISPLAY_H / 2 - 40)
            
            # Draw Options (Fixed coordinates)
            self.game.draw_text("Start Game", self.TEXT_NORMAL, self.startx, self.starty)
            self.game.draw_text("Manage Decks", self.TEXT_NORMAL, self.decksx, self.decksy)
            self.game.draw_text("Train AI", self.TEXT_NORMAL, self.trainx, self.trainy)
            self.game.draw_text("Options", self.TEXT_NORMAL, self.optionsx, self.optionsy)
            self.game.draw_text("Credits", self.TEXT_NORMAL, self.creditsx, self.creditsy)
            self.game.draw_text("Quit", self.TEXT_NORMAL, self.quitx, self.quity)
            
            self.draw_cursor()
            self.blit_screen()

    def move_cursor(self):
        # DOWN KEY LOGIC
        if self.game.DOWN_KEY:
            if self.state == MainMenuStates.START:
                self.cursor_rect.midtop = (self.decksx + self.offset, self.decksy)
                self.state = MainMenuStates.DECKS
            elif self.state == MainMenuStates.DECKS:
                self.cursor_rect.midtop = (self.trainx + self.offset, self.trainy)
                self.state = MainMenuStates.TRAIN
            elif self.state == MainMenuStates.TRAIN:
                self.cursor_rect.midtop = (self.optionsx + self.offset, self.optionsy)
                self.state = MainMenuStates.OPTIONS
            elif self.state == MainMenuStates.OPTIONS:
                self.cursor_rect.midtop = (self.creditsx + self.offset, self.creditsy)
                self.state = MainMenuStates.CREDITS
            elif self.state == MainMenuStates.CREDITS:
                self.cursor_rect.midtop = (self.quitx + self.offset, self.quity)
                self.state = MainMenuStates.QUIT
            elif self.state == MainMenuStates.QUIT:
                self.cursor_rect.midtop = (self.startx + self.offset, self.starty)
                self.state = MainMenuStates.START

        # UP KEY LOGIC
        if self.game.UP_KEY:
            if self.state == MainMenuStates.START:
                self.cursor_rect.midtop = (self.quitx + self.offset, self.quity)
                self.state = MainMenuStates.QUIT
            elif self.state == MainMenuStates.DECKS:
                self.cursor_rect.midtop = (self.startx + self.offset, self.starty)
                self.state = MainMenuStates.START
            elif self.state == MainMenuStates.TRAIN:
                self.cursor_rect.midtop = (self.decksx + self.offset, self.decksy)
                self.state = MainMenuStates.DECKS
            elif self.state == MainMenuStates.OPTIONS:
                self.cursor_rect.midtop = (self.trainx + self.offset, self.trainy)
                self.state = MainMenuStates.TRAIN
            elif self.state == MainMenuStates.CREDITS:
                self.cursor_rect.midtop = (self.optionsx + self.offset, self.optionsy)
                self.state = MainMenuStates.OPTIONS
            elif self.state == MainMenuStates.QUIT:
                self.cursor_rect.midtop = (self.creditsx + self.offset, self.creditsy)
                self.state = MainMenuStates.CREDITS

    def check_input(self):
        # Assuming START_KEY is mapped to Enter/Return
        if self.game.START_KEY:
            if self.state == MainMenuStates.START:
                self.run_display            = False
                
                play_menu                   = BasicPlayMenu(self.game)
                self.game.curr_menu         = play_menu
                play_menu.previous_menu     = self
                play_menu.display_menu()
            elif self.state == MainMenuStates.DECKS:
                pass # Add logic to switch to Decks Menu
            elif self.state == MainMenuStates.TRAIN:
                pass # Add logic to switch to Train Menu
            elif self.state == MainMenuStates.OPTIONS:
                self.run_display            = False

                options_menu                = OptionsMenu(self.game)
                self.game.curr_menu         = options_menu
                options_menu.previous_menu  = self
                options_menu.display_menu()
            elif self.state == MainMenuStates.CREDITS:
                pass # Add logic to switch to Credits Menu
            elif self.state == MainMenuStates.QUIT:
                self.run_display    = False
                self.game.playing   = False
                self.game.running   = False
            