import threading
import pygame
from py_game.menu.main_menu import MainMenu

# left pos nav is broken, can place on pos 1

from core.game_loop         import run as run_game
from choice_strategies.choice_strategy_human_pygame     import PygameChoiceStrategy, ChoiceType
from choice_strategies.choice_strategy_ai_random        import ChoiceStrategyAIRandom
from display_strategies.display_strategy_pygame         import DisplayStrategyPygame
from display_strategies.display_strategy_none           import DisplayStrategyNone
from cards.mana import ManaColor
from core.player import Player
from utils.database_utils import DBUtil
from cards.card import Card
from core.board import Board
from core.enums.game_state  import GameState

class Game():
    def __init__(self):
        pygame.init()
        self.UP_KEY, self.DOWN_KEY, self.LEFT_KEY, self.RIGHT_KEY = False, False, False, False
        self.START_KEY, self.BACK_KEY = False, False
        self.running, self.playing      = True, False
        self.DISPLAY_W, self.DISPLAY_H  = 800, 600
        pygame.display.set_mode((self.DISPLAY_W, self.DISPLAY_H))
        self.BLACK, self.WHITE, self.ORANGE, self.DARK_GREY          = (0,0,0), (255,255,255), (255, 215, 0), (30, 30, 30)
        self.TEXT_SMALL  = self.DISPLAY_H // 80
        self.TEXT_NORMAL = self.DISPLAY_H // 40
        self.TEXT_LARGE  = self.DISPLAY_H // 20

        self.p1_deck_id = None
        self.p2_deck_id = None
        self.p1_type    = None
        self.p2_type    = None
        self.selected_card      = None
        self.selected_position  = None
        self.changing_player    = False
        self.changing_to_battle = False
        self.previous_game_state = None

        self.card_bg                    = pygame.image.load("py_game/resources/card_background.png")
        self.mana_map                   = {}
        self.mana_map[ManaColor.RED]    = pygame.image.load("py_game/resources/mana_cervena.png")
        self.mana_map[ManaColor.BLACK]  = pygame.image.load("py_game/resources/mana_cerna.png")
        self.mana_map[ManaColor.BLUE]   = pygame.image.load("py_game/resources/mana_modra.png")

        self.display        = pygame.Surface((self.DISPLAY_W,self.DISPLAY_H))
        self.window         = pygame.display.set_mode(((self.DISPLAY_W,self.DISPLAY_H)))
        self.font_name      = pygame.font.get_default_font()
    
        self.curr_menu      = MainMenu(self)

    def check_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running, self.playing = False, False
                self.curr_menu.run_display = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN or event.type == pygame.K_SPACE:
                    self.START_KEY      = True
                elif event.key == pygame.K_BACKSPACE:
                    self.BACK_KEY       = True
                elif event.key == pygame.K_DOWN:
                    self.DOWN_KEY       = True
                elif event.key == pygame.K_UP:
                    self.UP_KEY         = True
                elif event.key == pygame.K_LEFT:
                    self.LEFT_KEY       = True
                elif event.key == pygame.K_RIGHT:
                    self.RIGHT_KEY      = True

    def reset_keys(self):
        self.UP_KEY, self.DOWN_KEY    = False, False
        self.LEFT_KEY, self.RIGHT_KEY = False, False
        self.START_KEY, self.BACK_KEY = False, False

    def navigate_hand(self):
        cards = self.p1.hand.cards
        if self.selected_card == None and len(cards)>0 :
            self.selected_card = cards[0]
        if self.LEFT_KEY:
            try:
                pos = cards.index(self.selected_card)
                pos = (pos - 1) if pos > 0 else len(cards) - 1
                self.selected_card = cards[pos]
            except ValueError:
                self.selected_card = cards[len(cards)-1] if len(cards)>0 else None
        elif self.RIGHT_KEY:
            try:
                pos = cards.index(self.selected_card)
                pos = (pos + 1) % len(cards)
                self.selected_card = cards[pos]
            except ValueError:
                self.selected_card = cards[0] if len(cards)>0 else None
    
    def navigate_board(self):
        # cards = self.board.positions
        empty_positions = []
        for i in range(len(self.board.positions)):
            empty_positions.append(i) if self.board.positions[i] == None else None
        if self.selected_position == None and len(empty_positions)>0 :
            self.selected_position = empty_positions[0]
        if self.LEFT_KEY:
            try:
                pos_index = empty_positions.index(self.selected_position)
                self.selected_position  = empty_positions[pos_index - 1] if pos_index > 0 else empty_positions[len(empty_positions) - 1]
            except ValueError:
                self.selected_position = empty_positions[len(empty_positions)-1] if len(empty_positions)>0 else None
        elif self.RIGHT_KEY:
            try:
                pos_index = (empty_positions.index(self.selected_position) + 1) % len(empty_positions)
                self.selected_position = empty_positions[pos_index]
            except ValueError:
                self.selected_position = empty_positions[0] if len(empty_positions)>0 else None

    def pass_choice(self):
        choice_type = self.p1.choice_strategy.waiting_for
        if isinstance(self.p1.choice_strategy, PygameChoiceStrategy) and choice_type != ChoiceType.NONE:
            if (choice_type == ChoiceType.CARD):
                if self.START_KEY and self.selected_card:
                    self.p1.choice_strategy.set_choice(ChoiceType.CARD, self.selected_card)
            if (choice_type == ChoiceType.POSITION) and self.START_KEY and self.selected_position != None:
                    self.p1.choice_strategy.set_choice(ChoiceType.POSITION, self.selected_position)
            


    def handle_choice(self):
        if isinstance(self.p1.choice_strategy, PygameChoiceStrategy):
            if self.p1.choice_strategy.waiting_for == ChoiceType.CARD:
                self.navigate_hand()
                if self.START_KEY and self.selected_position != None:
                    self.p1.choice_strategy.set_choice(ChoiceType.POSITION, self.selected_position)
            else:
                self.selected_card = None
            if self.p1.choice_strategy.waiting_for == ChoiceType.POSITION:
                self.navigate_board()
            else:
                self.selected_position = None
            self.pass_choice()



            
             
    def draw_game(self):
        H = self.DISPLAY_H
        W = self.DISPLAY_W

        if self.changing_player:
            self.draw_text(f"Player_{self.p1.id}´s turn ",self.TEXT_LARGE, W//2, H//2)
            self.draw_text(f"Press start to continue",self.TEXT_LARGE, W//2, (H + self.TEXT_LARGE * 2) // 2)
            return
        elif self.changing_to_battle:
            self.draw_text(f"Time to battle the {self.board.dragon.name}!",self.TEXT_LARGE, W//2, H//2)
            self.draw_text(f"Both players should be pressent for this",self.TEXT_NORMAL, W//2, (H + self.TEXT_LARGE * 2) // 2)
            self.draw_text(f"Press start to continue",self.TEXT_LARGE, W//2, (H + self.TEXT_LARGE * 4) // 2)
            return
        
        # === Horizontal separators ===
        info_h          = self.TEXT_LARGE
        game_board_h    = ((H - info_h) // 3)+info_h
        p1_h            = ((H - info_h)*(2/3))+info_h

        pygame.draw.line(self.display, self.WHITE, (0, info_h), (W, info_h))
        pygame.draw.line(self.display, self.WHITE, (0, game_board_h), (W, game_board_h))
        pygame.draw.line(self.display, self.WHITE, (0, p1_h), (W, p1_h))

        card_w  = W // 10
        gap     = (2 * card_w) // 15
        card_h  = game_board_h - info_h - 2 * gap

        # === Vertical separators ===
        lef_panel_hr_w     = 4*gap+card_w
        right_panel_hr_w   = W - (4*gap+card_w)
        pygame.draw.line(self.display, self.WHITE, (lef_panel_hr_w, 0), (lef_panel_hr_w, H))
        pygame.draw.line(self.display, self.WHITE, (right_panel_hr_w, 0), (right_panel_hr_w, H))

        # === info ===
        self.draw_text(" score: " + str(self.p1.score - self.p2.score),self.TEXT_NORMAL, lef_panel_hr_w//2, info_h//2)
        self.draw_text(f"Player on turn: P_{self.p1.id}",self.TEXT_NORMAL, W//2, info_h//2)
        if not self.board.game_running:
            winner = "Player_" + str(self.board.winner.id) if self.board.winner else "None"
            self.draw_text("winner: " + winner, self.TEXT_NORMAL, W//2, info_h//2)
            
        self.draw_text("round: " + str(self.board.round),self.TEXT_NORMAL, right_panel_hr_w + (W - right_panel_hr_w)//2, info_h//2)

        # === Cards ===
        self.card_bg        = pygame.transform.scale(self.card_bg,(card_w,card_h))

        # P2
        self.draw_image_with_center_text(str(len(self.p2.deck.cards)), self.card_bg, (gap), (info_h + gap)) # deck
        self.draw_image_with_center_text("0", self.card_bg, (right_panel_hr_w + gap), (info_h + gap)) # gy
        for i in range(len(self.p2.hand.cards)):
            card = self.p2.hand.cards[i]
            card_offset = (gap + card_w) * i
            if self.selected_card == card:
                pygame.draw.rect(self.display, self.ORANGE, ((lef_panel_hr_w + gap//2 + card_offset),(info_h + gap//2), card_w + gap ,card_h + gap))
            # card.image = pygame.transform.scale(pygame.image.load(card.image), (card_w,card_h)) if  isinstance(card.image, str) else card.image
            self.display.blit(self.card_bg , (lef_panel_hr_w + gap + card_offset, (info_h + gap)))
        

        # mid
        if self.board.dragon:
            if  isinstance(self.board.dragon.image, str):
                    self.board.dragon.image = pygame.transform.scale(pygame.image.load(self.board.dragon.image), (card_w,card_h)) 
            self.draw_image_with_center_text(str(self.board.dragon.hp), self.board.dragon.image, gap, (game_board_h + gap),self.TEXT_NORMAL)
        else:
            self.draw_image_with_center_text(str(len(self.board.dragons)), self.card_bg, (gap), (game_board_h + gap)) # deck

        self.display.blit(pygame.transform.scale(self.mana_map[self.board.mana_pool[0].color], (card_w,card_h)), ((right_panel_hr_w + gap), (game_board_h + gap)))

        for i in range(len(self.board.positions)):
            card_offset = (gap + card_w) * i
            card = self.board.positions[i]
            if self.selected_position == i:
                pygame.draw.rect(self.display, self.ORANGE, ((lef_panel_hr_w + gap//2 + card_offset),(game_board_h + gap//2), card_w + gap ,card_h + gap))
            if card:
                if  isinstance(card.image, str):
                    card.image = pygame.transform.scale(pygame.image.load(card.image), (card_w,card_h))
                if card.owner == self.p2:
                    pygame.draw.rect(self.display, self.WHITE, ((lef_panel_hr_w + gap + card_offset + card_w//4),(game_board_h + gap//4), card_w//2, gap//2))
                else:
                    pygame.draw.rect(self.display, self.ORANGE, ((lef_panel_hr_w + gap + card_offset + card_w//4),(game_board_h + gap + gap//4 + card_h), card_w//2, gap//2))
                self.display.blit(card.image , (lef_panel_hr_w + gap + card_offset, (game_board_h + gap)))
            else:
                pygame.draw.rect(self.display, self.WHITE, ((lef_panel_hr_w + gap + card_offset),(game_board_h + gap), card_w,card_h))

        # P1
        self.draw_image_with_center_text(str(len(self.p1.deck.cards)), self.card_bg, (gap), (p1_h + gap)) # deck
        self.draw_image_with_center_text("0", self.card_bg, (right_panel_hr_w + gap), (p1_h + gap)) # gy
        for i in range(len(self.p1.hand.cards)):
            card_offset = (gap + card_w) * i
            card = self.p1.hand.cards[i]
            if self.selected_card == card:
                pygame.draw.rect(self.display, self.ORANGE, ((lef_panel_hr_w + gap//2 + card_offset),(p1_h + gap//2), card_w + gap ,card_h + gap))
            if self.board.game_state == GameState.PLAY:
                card.image = pygame.transform.scale(pygame.image.load(card.image), (card_w,card_h)) if  isinstance(card.image, str) else card.image
                self.display.blit(card.image , (lef_panel_hr_w + gap + card_offset, (p1_h + gap)))
            else:
                self.display.blit(self.card_bg, (lef_panel_hr_w + gap + card_offset, (p1_h + gap)))






    def game_loop(self):
        self.p1=Player(1,DBUtil().load_deck("Starter Blue_1"), PygameChoiceStrategy)
        self.p2=Player(2,DBUtil().load_deck("Starter Blue_1"), PygameChoiceStrategy)
        self.board = Board()
        logic_thread = threading.Thread(
            target=run_game, 
            args=(self.p1, self.p2, DisplayStrategyNone, self.board ),
        )
        logic_thread.start()

        while self.playing:
                    
            if (self.board.player_on_turn == self.p2) and (isinstance(self.p1.choice_strategy,PygameChoiceStrategy) and isinstance(self.p2.choice_strategy,PygameChoiceStrategy)):
                self.changing_player = True
                tmp     = self.p1
                self.p1 = self.p2
                self.p2 = tmp

            self.check_events()
            if self.previous_game_state != self.board.game_state:
                if self.board.game_state == GameState.BATTLE:
                    self.changing_to_battle = True
                self.previous_game_state = self.board.game_state
            elif self.START_KEY and (self.changing_player or self.changing_to_battle):
                self.changing_player    = False
                self.changing_to_battle = False
            elif self.BACK_KEY:
                self.playing   = False
                self.p1.choice_strategy.exit_thread()
                self.curr_menu = MainMenu(self)
                self.curr_menu.display_menu()
            else:
                self.handle_choice()
            self.display.fill(self.DARK_GREY)
            self.draw_game()
            self.window.blit(self.display, (0,0))
            pygame.display.update()
            self.reset_keys()

    def draw_text(self, text, size, x, y):
        font = pygame.font.Font(self.font_name, int(size))
        text_surface = font.render(text, True, self.WHITE)
        text_rect = text_surface.get_rect()
        text_rect.center = (x,y)
        self.display.blit(text_surface, text_rect)

    def draw_text_bg(self, text, size, x, y):
        font = pygame.font.Font(self.font_name, int(size))
        text_surface = font.render(text, True, self.WHITE)
        text_rect = text_surface.get_rect()
        text_rect.center = (x,y)
        pygame.draw.rect(self.display, self.BLACK, ((x - size), (y - size), size*2, size*2)) # deck card count bg
        self.display.blit(text_surface, text_rect)

    def draw_image_with_center_text(self, text, image:pygame.Surface, x, y, size = None):
        w,h = image.get_size()
        self.display.blit(image, (x, y))
        if not size:
            size = self.TEXT_LARGE #TODO calculate size automaticaly
        self.draw_text_bg(text, size, x + w//2, y + h//2)