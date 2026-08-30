import threading
from pathlib import Path

import pygame

from py_game.menu.main_menu import MainMenu

from core.game_loop         import run as run_game
from choice_strategies.choice_strategy_human_pygame     import PygameChoiceStrategy, ChoiceType
from display_strategies.display_strategy_none           import DisplayStrategyNone
from py_game.match_setup import ControllerKind, ControllerSpec, create_player
from cards.mana import ManaColor
from utils.database_utils import DBUtil
from core.board import Board
from core.enums.game_state  import GameState

class Game():
    def __init__(self):
        pygame.init()
        self.UP_KEY, self.DOWN_KEY, self.LEFT_KEY, self.RIGHT_KEY = False, False, False, False
        self.START_KEY, self.BACK_KEY = False, False
        self.running, self.playing      = True, False
        self.DISPLAY_W, self.DISPLAY_H  = 800, 600
        self.BLACK, self.WHITE, self.ORANGE, self.DARK_GREY          = (0,0,0), (255,255,255), (255, 215, 0), (30, 30, 30)
        self.TEXT_SMALL  = self.DISPLAY_H // 80
        self.TEXT_NORMAL = self.DISPLAY_H // 40
        self.TEXT_LARGE  = self.DISPLAY_H // 20

        self.p1_deck_id = None
        self.p2_deck_id = None
        self.p1_controller = ControllerSpec(ControllerKind.HUMAN)
        self.p2_controller = ControllerSpec(ControllerKind.RANDOM_AI)
        self.selected_card      = None
        self.selected_position  = None
        self.binary_choice = False
        self.changing_player    = False
        self.changing_to_battle = False
        self.previous_game_state = None

        resource_dir = Path(__file__).resolve().parent / "resources"
        self.card_bg = pygame.image.load(resource_dir / "card_background.png")
        self.mana_map                   = {}
        self.mana_map[ManaColor.RED] = pygame.image.load(resource_dir / "mana_cervena.png")
        self.mana_map[ManaColor.BLACK] = pygame.image.load(resource_dir / "mana_cerna.png")
        self.mana_map[ManaColor.BLUE] = pygame.image.load(resource_dir / "mana_modra.png")

        self.display        = pygame.Surface((self.DISPLAY_W,self.DISPLAY_H))
        self.window         = pygame.display.set_mode(((self.DISPLAY_W,self.DISPLAY_H)))
        pygame.display.set_caption("Draci zvesti")
        self.font_name      = pygame.font.get_default_font()
        self.clock = pygame.time.Clock()
        self.logic_error = None
        self.game_result = None
    
        self.curr_menu      = MainMenu(self)

    def check_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running, self.playing = False, False
                if self.curr_menu is not None:
                    self.curr_menu.run_display = False
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.START_KEY      = True
                elif event.key in (pygame.K_BACKSPACE, pygame.K_ESCAPE):
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

    def navigate_hand(self, player):
        cards = player.hand.cards
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
    
    def navigate_board(self, allowed_positions=None):
        empty_positions = (
            list(allowed_positions)
            if allowed_positions is not None
            else [
                index
                for index, card in enumerate(self.board.positions)
                if card is None
            ]
        )
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

    def handle_choice(self):
        player = self.board.player_on_turn
        if player is None or not isinstance(
            player.choice_strategy,
            PygameChoiceStrategy,
        ):
            self.selected_card = None
            self.selected_position = None
            return

        strategy = player.choice_strategy
        choice_type = strategy.waiting_for
        if choice_type == ChoiceType.CARD:
            self.navigate_hand(player)
            self.selected_position = None
            if self.START_KEY and self.selected_card is not None:
                strategy.set_choice(ChoiceType.CARD, self.selected_card)
        elif choice_type == ChoiceType.POSITION:
            self.selected_card = None
            self.navigate_board()
            if self.START_KEY and self.selected_position is not None:
                strategy.set_choice(ChoiceType.POSITION, self.selected_position)
        elif choice_type in (ChoiceType.PASS, ChoiceType.USE_ABILITY):
            self.selected_card = None
            self.selected_position = None
            if self.LEFT_KEY or self.RIGHT_KEY:
                self.binary_choice = not self.binary_choice
            if self.START_KEY:
                strategy.set_choice(choice_type, self.binary_choice)
                self.binary_choice = False
        elif choice_type == ChoiceType.TARGET:
            self.selected_card = None
            legal_targets = strategy.legal_targets()
            self.navigate_board(legal_targets)
            if self.START_KEY and self.selected_position in legal_targets:
                strategy.set_choice(ChoiceType.TARGET, self.selected_position)
        else:
            self.selected_card = None
            self.selected_position = None



            
             
    def draw_game(self):
        H = self.DISPLAY_H
        W = self.DISPLAY_W

        if self.changing_player:
            self.draw_text(
                f"Player_{self.p1.id}´s turn ",
                self.TEXT_LARGE,
                W // 2,
                H // 2,
            )
            self.draw_text(
                "Press start to continue",
                self.TEXT_LARGE,
                W // 2,
                (H + self.TEXT_LARGE * 2) // 2,
            )
            return
        elif self.changing_to_battle:
            dragon_name = self.board.dragon.name if self.board.dragon else "dragon"
            self.draw_text(
                f"Time to battle the {dragon_name}!",
                self.TEXT_LARGE,
                W // 2,
                H // 2,
            )
            self.draw_text(
                "Both players should be pressent for this",
                self.TEXT_NORMAL,
                W // 2,
                (H + self.TEXT_LARGE * 2) // 2,
            )
            self.draw_text(
                "Press start to continue",
                self.TEXT_LARGE,
                W // 2,
                (H + self.TEXT_LARGE * 4) // 2,
            )
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
        self.draw_text(
            " score: " + str(self.p1.score - self.p2.score),
            self.TEXT_NORMAL,
            lef_panel_hr_w // 2,
            info_h // 2,
        )
        turn_id = self.board.player_on_turn.id if self.board.player_on_turn else self.p1.id
        center_status = f"Player on turn: P_{turn_id}"
        player_on_turn = self.board.player_on_turn
        if player_on_turn and isinstance(
            player_on_turn.choice_strategy,
            PygameChoiceStrategy,
        ):
            choice_type = player_on_turn.choice_strategy.waiting_for
            if choice_type == ChoiceType.PASS:
                center_status = "Pass" if self.binary_choice else "Play a card"
            elif choice_type == ChoiceType.USE_ABILITY:
                center_status = (
                    "Use active ability"
                    if self.binary_choice
                    else "Skip active ability"
                )
            elif choice_type == ChoiceType.TARGET:
                center_status = "Choose ability target"
        self.draw_text(center_status, self.TEXT_NORMAL, W // 2, info_h // 2)
        if not self.board.game_running:
            winner = "Player_" + str(self.board.winner.id) if self.board.winner else "None"
            self.draw_text("winner: " + winner, self.TEXT_NORMAL, W // 2, info_h // 2)

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
        deck_1 = DBUtil().load_deck(self.p1_deck_id)
        deck_2 = DBUtil().load_deck(self.p2_deck_id)
        try:
            logic_p1 = create_player(1, deck_1, self.p1_controller)
            logic_p2 = create_player(2, deck_2, self.p2_controller)
        except ValueError as error:
            self.logic_error = str(error)
            self.playing = False
            self.curr_menu = MainMenu(self)
            self.curr_menu.display_menu()
            return

        self.p1 = logic_p1
        self.p2 = logic_p2
        self.board = Board()
        self.logic_error = None
        self.game_result = None

        def run_logic():
            try:
                self.game_result = run_game(
                    logic_p1,
                    logic_p2,
                    DisplayStrategyNone,
                    self.board,
                )
            except SystemExit:
                self.board.game_running = False
            except Exception as error:
                self.logic_error = f"{type(error).__name__}: {error}"
                self.board.game_running = False

        logic_thread = threading.Thread(
            target=run_logic,
            daemon=True,
        )
        logic_thread.start()
        human_players = [
            player
            for player in (logic_p1, logic_p2)
            if isinstance(player.choice_strategy, PygameChoiceStrategy)
        ]
        if len(human_players) == 1:
            self.p1 = human_players[0]
            self.p2 = logic_p2 if self.p1 is logic_p1 else logic_p1
        previous_turn = None

        while self.playing:
            self.check_events()
            current_turn = self.board.player_on_turn
            if current_turn is not None and current_turn is not previous_turn:
                if len(human_players) == 2:
                    self.p1 = current_turn
                    self.p2 = logic_p2 if current_turn is logic_p1 else logic_p1
                    if previous_turn is not None:
                        self.changing_player = True
                previous_turn = current_turn

            if self.previous_game_state != self.board.game_state:
                if self.board.game_state == GameState.BATTLE and human_players:
                    self.changing_to_battle = True
                self.previous_game_state = self.board.game_state
            elif self.START_KEY and (self.changing_player or self.changing_to_battle):
                self.changing_player    = False
                self.changing_to_battle = False
            elif self.BACK_KEY:
                self._leave_match(logic_thread, human_players)
                return
            elif not self.board.game_running and self.START_KEY:
                self._leave_match(logic_thread, human_players)
                return
            else:
                self.handle_choice()
            self.display.fill(self.DARK_GREY)
            if self.logic_error:
                self.draw_text("Match could not continue", self.TEXT_LARGE, self.DISPLAY_W // 2, 250)
                self.draw_text(self.logic_error, self.TEXT_NORMAL, self.DISPLAY_W // 2, 310)
                self.draw_text("Back", self.TEXT_NORMAL, self.DISPLAY_W // 2, 365)
            else:
                self.draw_game()
            self.window.blit(self.display, (0,0))
            pygame.display.update()
            self.reset_keys()
            self.clock.tick(60)

    def _leave_match(self, logic_thread, human_players):
        self.playing = False
        for player in human_players:
            player.choice_strategy.exit_thread()
        logic_thread.join(timeout=0.5)
        self.curr_menu = MainMenu(self)
        self.curr_menu.display_menu()

    def draw_text(self, text, size, x, y, color=None):
        font = pygame.font.Font(self.font_name, int(size))
        text_surface = font.render(str(text), True, color or self.WHITE)
        text_rect = text_surface.get_rect()
        text_rect.center = (x,y)
        self.display.blit(text_surface, text_rect)

    def draw_text_left(self, text, size, x, y, color=None, max_width=None):
        font = pygame.font.Font(self.font_name, int(size))
        value = str(text)
        if max_width is not None:
            while value and font.size(value)[0] > max_width:
                value = value[:-1]
            if value != str(text) and len(value) > 3:
                value = value[:-3] + "..."
        text_surface = font.render(value, True, color or self.WHITE)
        self.display.blit(text_surface, (int(x), int(y - text_surface.get_height() / 2)))

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

    def draw_image(self, image_path, x, y, width, height):
        image = pygame.image.load(image_path)
        # FIX: Assign the scaled surface back to the 'image' variable
        image = pygame.transform.scale(image, (int(width), int(height)))
        self.display.blit(image, (x, y))
