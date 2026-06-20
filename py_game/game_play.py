import pygame as pg

class MainGame():
    def __init__(self):
        pg.init()
        self.UP_KEY, self.DOWN_KEY, self.START_KEY, self.BACK_KEY = False, False, False, False
        self.running, self.playing      = True, False
        self.DISPLAY_W, self.DISPLAY_H  = 800, 600
        self.BLACK, self.WHITE          = (0,0,0), (255,255,255)

        self.display        = pg.Surface((self.DISPLAY_W,self.DISPLAY_H))
        self.window         = pg.display.set_mode(((self.DISPLAY_W,self.DISPLAY_H)))
        self.font_name      = pg.font.get_default_font()
    