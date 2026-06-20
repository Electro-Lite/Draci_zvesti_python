import pygame as pg
from typing import TYPE_CHECKING
from enum import Enum
from py_game.menu.base_menu import Menu

if TYPE_CHECKING:
    from py_game.game import Game

class OptionsMenuStates(Enum):
    NOTHING     = 0
    FULLSCREEN  = 1
    RESOLUTION  = 2
    BACK        = 3

class OptionsMenu(Menu):
    def __init__(self, game: 'Game'):
        Menu.__init__(self, game)
        self.state = OptionsMenuStates.NOTHING
        
        # Define coordinates
        self.non_x, self.non_y   = self.mid_w, self.mid_h
        self.fs_x, self.fs_y     = self.mid_w, self.mid_h + 20
        self.res_x, self.res_y   = self.mid_w, self.mid_h + 50
        self.back_x, self.back_y = self.mid_w, self.mid_h + 90
        
        # Supported Resolutions
        self.resolutions = [
            (800, 600),
            (1024, 768),
            (1280, 720),
            (1920, 1080)
        ]
        
        # Attempt to match current resolution to list
        current_res = (self.game.DISPLAY_W, self.game.DISPLAY_H)
        try:
            self.current_res_index = self.resolutions.index(current_res)
        except ValueError:
            self.current_res_index = 0

        self.cursor_rect.midtop = (self.non_x + self.offset, self.non_y)

        self.previous_menu = None

    def display_menu(self):
        self.run_display = True
        while self.run_display:
            self.game.check_events()
            self.check_input()
            self.move_cursor()
            
            # Clear screen
            self.game.display.fill(self.game.BLACK)
            
            # Draw Header
            self.game.draw_text('Options', self.TEXT_LARGE, self.game.DISPLAY_W / 2, self.game.DISPLAY_H / 2 - 40)
            
            # Draw Fullscreen Option
            fs_status = "ON" if self.is_fullscreen() else "OFF"
            self.game.draw_text(f"Fullscreen: {fs_status}", self.TEXT_NORMAL, self.fs_x, self.fs_y)
            
            # Draw Resolution Option
            current_w, current_h = self.resolutions[self.current_res_index]
            self.game.draw_text(f"Resolution: {current_w}x{current_h}", self.TEXT_NORMAL, self.res_x, self.res_y)
            
            # Draw Back Button
            self.game.draw_text("Back", 20, self.back_x, self.back_y)
            
            self.draw_cursor()
            self.blit_screen()

    def move_cursor(self):
        if self.game.DOWN_KEY:
            if self.state == OptionsMenuStates.NOTHING:
                self.cursor_rect.midtop = (self.non_x + self.offset, self.non_y)
                self.state = OptionsMenuStates.FULLSCREEN
                self.cursor_rect.midtop = (self.fs_x + self.offset, self.fs_y)
            elif self.state == OptionsMenuStates.FULLSCREEN:
                self.state = OptionsMenuStates.RESOLUTION
                self.cursor_rect.midtop = (self.res_x + self.offset, self.res_y)
            elif self.state == OptionsMenuStates.RESOLUTION:
                self.state = OptionsMenuStates.BACK
                self.cursor_rect.midtop = (self.back_x + self.offset, self.back_y)
            elif self.state == OptionsMenuStates.BACK:
                self.state = OptionsMenuStates.NOTHING
                self.cursor_rect.midtop = (self.non_x + self.offset, self.non_y)
        
        if self.game.UP_KEY:
            if self.state == OptionsMenuStates.NOTHING:
                self.cursor_rect.midtop = (self.back_x + self.offset, self.back_y)
                self.state = OptionsMenuStates.BACK
            elif self.state == OptionsMenuStates.FULLSCREEN:
                self.cursor_rect.midtop = (self.non_x + self.offset, self.non_y)
                self.state = OptionsMenuStates.NOTHING
            elif self.state == OptionsMenuStates.RESOLUTION:
                self.state = OptionsMenuStates.FULLSCREEN
                self.cursor_rect.midtop = (self.fs_x + self.offset, self.fs_y)
            elif self.state == OptionsMenuStates.BACK:
                self.state = OptionsMenuStates.RESOLUTION
                self.cursor_rect.midtop = (self.res_x + self.offset, self.res_y)

    def check_input(self):
        if self.game.START_KEY:
            if self.state == OptionsMenuStates.FULLSCREEN:
                self.toggle_fullscreen()
            elif self.state == OptionsMenuStates.RESOLUTION:
                self.change_resolution()
            elif self.state == OptionsMenuStates.BACK:
                self.run_display = False
                self.game.curr_menu = self.previous_menu
                self.previous_menu.__init__(self.game)
                self.previous_menu.run_display = True
        
    def is_fullscreen(self) -> bool:
        return bool(self.game.window.get_flags() & pg.FULLSCREEN)

    def toggle_fullscreen(self):
        new_flags = 0
        if not self.is_fullscreen():
            new_flags = pg.FULLSCREEN
        
        w, h = self.resolutions[self.current_res_index]
        self.game.window = pg.display.set_mode((w, h), new_flags)

    def change_resolution(self):
        self.current_res_index = (self.current_res_index + 1) % len(self.resolutions)
        new_w, new_h = self.resolutions[self.current_res_index]
        
        flags = pg.FULLSCREEN if self.is_fullscreen() else 0
        
        # Update logic vars
        self.game.DISPLAY_W, self.game.DISPLAY_H = new_w, new_h
        self.game.TEXT_SMALL  = new_h // 80
        self.game.TEXT_NORMAL = new_h // 40
        self.game.TEXT_LARGE  = new_h // 20
        
        # Reset Window
        self.game.window = pg.display.set_mode((new_w, new_h), flags)
        
        # Reset Canvas (Fixes the black screen issue)
        self.game.display = pg.Surface((new_w, new_h))
        
        self.recalculate_layout()

    def recalculate_layout(self):
        self.mid_w, self.mid_h = self.game.DISPLAY_W / 2, self.game.DISPLAY_H / 2
        self.fs_x, self.fs_y     = self.mid_w, self.mid_h + 20
        self.res_x, self.res_y   = self.mid_w, self.mid_h + 50
        self.back_x, self.back_y = self.mid_w, self.mid_h + 90
        
        if self.state == OptionsMenuStates.NOTHING:
            self.cursor_rect.midtop = (self.fs_x + self.offset, self.fs_y)
        elif self.state == OptionsMenuStates.FULLSCREEN:
            self.cursor_rect.midtop = (self.fs_x + self.offset, self.fs_y)
        elif self.state == OptionsMenuStates.RESOLUTION:
            self.cursor_rect.midtop = (self.res_x + self.offset, self.res_y)
        elif self.state == OptionsMenuStates.BACK:
            self.cursor_rect.midtop = (self.back_x + self.offset, self.back_y)