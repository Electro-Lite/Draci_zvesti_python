
from py_game.menu.base_menu import Menu
from typing import TYPE_CHECKING
from enum import Enum
from core.enums.player_type import PlayerType
import pygame as pg
from utils.database_utils import DBUtil

if TYPE_CHECKING:
    from py_game.game import Game

class PlayMenuStates(Enum):
    NOTHING         = 0
    BACK            = 1
    P1_DECK         = 2
    OPPONENT_TYPE   = 3
    P2_DECK         = 4
    START_GAME      = 5


class BasicPlayMenu(Menu):
    def __init__(self, game: 'Game'):
        Menu.__init__(self, game)
        self.state = PlayMenuStates.NOTHING
        
        self.p1_deck_id     = None
        self.p2_deck_id     = None
        self.p1_type        = PlayerType.HUMAN
        self.p2_type        = PlayerType.RANDOM

        # Define coordinates
        self.non_x,     self.non_y      = self.mid_w, self.mid_h  + self.TEXT_LARGE - 100
        self.back_x,    self.back_y     = self.mid_w, self.mid_h  + self.TEXT_LARGE * 1
        self.p1_x,      self.p1_y       = self.mid_w, self.mid_h  + self.TEXT_LARGE * 2
        self.opp_x,     self.opp_y      = self.mid_w, self.mid_h  + self.TEXT_LARGE * 3
        self.p2_x,      self.p2_y       = self.mid_w, self.mid_h  + self.TEXT_LARGE * 4
        self.start_x,   self.start_y    = self.mid_w, self.mid_h  + self.TEXT_LARGE * 6
        
        self.offset = -180
        self.cursor_rect.midtop = (self.non_x + self.offset, self.non_y)

        self.previous_menu = None
        self.decks_ids = DBUtil().get_all_deck_ids()

    def display_menu(self):
        self.run_display = True
        while self.run_display:
            self.game.check_events()
            self.check_input()
            self.move_cursor()

            # 1. Clear Screen
            self.game.display.fill(self.game.BLACK)

            # 2. Draw Header
            self.game.draw_text('Match Setup', self.TEXT_LARGE, self.game.DISPLAY_W / 2, self.game.DISPLAY_H / 2 - 100)

            # 3. Draw Menu Items
            # 'NOTHING' / Mode selection (Top item)
            self.game.draw_text(f"Game Mode: local", self.TEXT_NORMAL, self.non_x, self.non_y)
            # Back Button
            self.game.draw_text("Back to Main", self.TEXT_NORMAL, self.back_x, self.back_y)
            # Player 1 Deck Selector
            # Shows current selection, e.g., "P1 Deck: Fire Deck"
            p1_deck_name = self.p1_deck_id if self.p1_deck_id else "< Please select >"
            self.game.draw_text(f"P1 Deck:  {p1_deck_name} ", self.TEXT_NORMAL, self.p1_x, self.p1_y)
            # Opponent Type Selector
            # Shows current selection, e.g., "Opponent: CPU"
            opp_name = ["Human", "CPU"][self.opponent_index] if hasattr(self, 'opponent_index') else "AI random"
            self.game.draw_text(f"Opponent:  {opp_name} ", self.TEXT_NORMAL, self.opp_x, self.opp_y)
            # Player 2 Deck Selector (only show if necessary, or dim it if single player?)
            p2_deck_name = self.p2_deck_id if self.p2_deck_id else "< Please select >"
            self.game.draw_text(f"P2 Deck:  {p2_deck_name} ", self.TEXT_NORMAL, self.p2_x, self.p2_y)
            # Start Game Button
            self.game.draw_text("START GAME", 25, self.start_x, self.start_y)

            # 4. Draw Cursor and Update Screen
            self.draw_cursor()
            self.blit_screen()

    def move_cursor(self):
        if self.game.DOWN_KEY:
            if self.state == PlayMenuStates.NOTHING:
                self.state = PlayMenuStates.BACK
                self.cursor_rect.midtop = (self.back_x + self.offset, self.back_y)
            elif self.state == PlayMenuStates.BACK:
                self.state = PlayMenuStates.P1_DECK
                self.cursor_rect.midtop = (self.p1_x + self.offset, self.p1_y)    
            elif self.state == PlayMenuStates.P1_DECK:
                self.state = PlayMenuStates.OPPONENT_TYPE
                self.cursor_rect.midtop = (self.opp_x + self.offset, self.opp_y)
            elif self.state == PlayMenuStates.OPPONENT_TYPE:
                self.state = PlayMenuStates.P2_DECK
                self.cursor_rect.midtop = (self.p2_x + self.offset, self.p2_y)
            elif self.state == PlayMenuStates.P2_DECK:
                self.state = PlayMenuStates.START_GAME
                self.cursor_rect.midtop = (self.start_x + self.offset, self.start_y)
            elif self.state == PlayMenuStates.START_GAME:
                self.state = PlayMenuStates.NOTHING
                self.cursor_rect.midtop = (self.non_x + self.offset, self.non_y)
        
        if self.game.UP_KEY:
            if self.state == PlayMenuStates.NOTHING:
                self.state = PlayMenuStates.START_GAME
                self.cursor_rect.midtop = (self.start_x + self.offset, self.start_y)
            elif self.state == PlayMenuStates.BACK:
                self.state = PlayMenuStates.NOTHING
                self.cursor_rect.midtop = (self.non_x + self.offset, self.non_y)
            elif self.state == PlayMenuStates.P1_DECK:
                self.state = PlayMenuStates.BACK
                self.cursor_rect.midtop = (self.back_x + self.offset, self.back_y)
            elif self.state == PlayMenuStates.OPPONENT_TYPE:
                self.state = PlayMenuStates.P1_DECK
                self.cursor_rect.midtop = (self.p1_x + self.offset, self.p1_y)
            elif self.state == PlayMenuStates.P2_DECK:
                self.state = PlayMenuStates.OPPONENT_TYPE
                self.cursor_rect.midtop = (self.opp_x + self.offset, self.opp_y)
            elif self.state == PlayMenuStates.START_GAME:
                self.state = PlayMenuStates.P2_DECK
                self.cursor_rect.midtop = (self.p2_x + self.offset, self.p2_y)

    def check_input(self):
        if self.game.START_KEY:
            if self.state == PlayMenuStates.BACK:
                self.run_display = False
                self.game.curr_menu = self.previous_menu
                self.previous_menu.__init__(self.game)
                self.previous_menu.run_display = True
            elif self.state == PlayMenuStates.P1_DECK:
                deck_list = [(i + 1, f"Deck {deck_id}") for i, deck_id in enumerate(self.decks_ids)]
                choice = self.select_deck_dialog("Choose Player 1 Deck", deck_list)
                if choice is not None:
                    self.p1_deck_id = choice
            elif self.state == PlayMenuStates.P2_DECK:
                deck_list = [(i + 1, f"Deck {deck_id}") for i, deck_id in enumerate(self.decks_ids)]
                choice = self.select_deck_dialog("Choose Player 1 Deck", deck_list)
                if choice is not None:
                    self.p2_deck_id = choice
            elif self.state == PlayMenuStates.START_GAME:
                self.game.p1_type       = self.p1_type
                self.game.p2_type       = self.p2_type
                self.game.p1_deck_id    = self.p1_deck_id
                self.game.p2_deck_id    = self.p2_deck_id

                self.run_display    = False
                self.game.curr_menu = None
                self.game.playing   = True
                self.game.game_loop()


    def select_deck_dialog(self, title, rows) -> str:
        """
        Keyboard-only blocking selector.
        Rows: list of (id, name).
        Returns: chosen deck NAME (str) or None.
        """
        font = pg.font.Font(None, self.TEXT_LARGE) 
        w, h = 400, 350
        x, y = (self.game.DISPLAY_W - w) // 2, (self.game.DISPLAY_H - h) // 2
        
        sel, offset = 0, 0
        items_per_page = 8
        
        # Draw a static background snapshot once
        bg_snapshot = self.game.window.copy()

        while True:
            # 1. Event Handling (Keyboard Only)
            for ev in pg.event.get():
                if ev.type == pg.QUIT: return None
                if ev.type == pg.KEYDOWN:
                    if ev.key == pg.K_ESCAPE: return None
                    
                    # --- CHANGED HERE: Return index 1 (Name) instead of 0 (ID) ---
                    if ev.key == pg.K_RETURN: return rows[sel][1]
                    
                    if ev.key == pg.K_UP:     sel = max(0, sel - 1)
                    if ev.key == pg.K_DOWN:   sel = min(len(rows) - 1, sel + 1)

            # 2. Auto-Scroll Logic
            if sel < offset: 
                offset = sel
            elif sel >= offset + items_per_page: 
                offset = sel - items_per_page + 1

            # 3. Drawing
            self.game.window.blit(bg_snapshot, (0, 0)) # Restore background
            
            # Draw Panel
            pg.draw.rect(self.game.window, (30, 30, 30), (x, y, w, h))       # Dark Grey Box
            pg.draw.rect(self.game.window, (200, 200, 200), (x, y, w, h), 2) # Border
            
            # Draw Title
            title_surf = font.render(title, True, (255, 255, 255))
            self.game.window.blit(title_surf, (x + 20, y + 15))

            # Draw List Items
            for i in range(offset, min(len(rows), offset + items_per_page)):
                # Yellow text for selected, White for others
                color = self.game.ORANGE if i == sel else (255, 255, 255)
                
                text = f"{rows[i][1]}"  # Just show the name
                txt_surf = font.render(text, True, color)
                self.game.window.blit(txt_surf, (x + 30, y + 60 + (i - offset) * 30))

            pg.display.update()