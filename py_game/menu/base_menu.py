import pygame as pg
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py_game.game import Game

class Menu():
    def __init__(self, game: 'Game'):
        self.game = game
        self.mid_w, self.mid_h = self.game.DISPLAY_W / 2, self.game.DISPLAY_H / 2
        self.run_display = True
        self.cursor_rect = pg.Rect(0, 0, 20, 20)
        self.offset = -100

        self.TEXT_SMALL  = self.game.TEXT_SMALL
        self.TEXT_NORMAL = self.game.TEXT_NORMAL
        self.TEXT_LARGE  = self.game.TEXT_LARGE

    def draw_cursor(self):
        self.game.draw_text("*", self.TEXT_LARGE, self.cursor_rect.x, self.cursor_rect.y + 5)

    def blit_screen(self):
        self.game.window.blit(self.game.display, (0, 0))
        pg.display.update()
        self.game.reset_keys()

    def display_menu(self):
        raise NotImplementedError()
