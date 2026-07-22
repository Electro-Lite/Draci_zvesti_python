import pygame as pg
from typing import TYPE_CHECKING
from enum import Enum
from py_game.menu.base_menu import Menu
from utils.database_utils import DBUtil

if TYPE_CHECKING:
    from py_game.game import Game

class ActivePane(Enum):
    AVAILABLE = 1
    MIDDLE    = 2
    DECK      = 3

class MiddleOptions(Enum):
    SAVE   = 0
    RETURN = 1
    DELETE = 2

class DeckBuilderMenu(Menu):
    def __init__(self, game: 'Game', deck_id=None):
        Menu.__init__(self, game)
        self.db = DBUtil()

        # --- Layout Coordinates ---
        self.col_left_x  = self.game.DISPLAY_W * 0.20
        self.col_mid_x   = self.game.DISPLAY_W * 0.50
        self.col_right_x = self.game.DISPLAY_W * 0.80
        self.start_y     = self.game.DISPLAY_H * 0.20

        # --- Data Lists ---
        self.all_cards          = self.db.get_all_player_cards()
        self.available_cards    = list(self.all_cards)

        self.deck_cards = []

        # If editing an existing deck, load it
        self.current_deck_id = deck_id
        if self.current_deck_id:
            loaded_deck = self.db.load_deck(self.current_deck_id)
            if loaded_deck and hasattr(loaded_deck, 'cards'):
                self.deck_cards = loaded_deck.cards

                # --- FILTER LOADED DECK ---
                for card in list(self.available_cards):
                    if self.deck_cards.count(card) >= 4:
                        self.available_cards.remove(card)

        # --- Nested State Tracking ---
        self.active_pane = ActivePane.AVAILABLE

        # Indices for vertical navigation within each pane
        self.index_available = 0
        self.index_middle    = 0
        self.index_deck      = 0

        self.middle_options = ["Save Deck", "Return", "Delete Deck"]

        self.update_cursor_pos()

    def display_menu(self):
        self.run_display = True

        # Clear ghost inputs from previous menu transitions
        self.game.START_KEY = False
        self.game.DOWN_KEY = False
        self.game.UP_KEY = False
        self.game.LEFT_KEY = False
        self.game.RIGHT_KEY = False

        while self.run_display:
            self.game.check_events()
            self.check_input()
            self.move_cursor()

            self.game.display.fill(self.game.BLACK)

            # Draw Headers
            self.game.draw_text('Deck Builder', self.TEXT_LARGE, self.col_mid_x, 40)
            self.game.draw_text('Available Cards', self.TEXT_NORMAL, self.col_left_x, self.start_y - 40)
            self.game.draw_text('Deck Cards', self.TEXT_NORMAL, self.col_right_x, self.start_y - 40)

            # --- DRAW LEFT PANE (Available Cards) ---
            for i, card in enumerate(self.available_cards):
                y_pos = self.start_y + (i * self.TEXT_NORMAL)
                self.game.draw_text(getattr(card, 'name', 'Unknown'), self.TEXT_NORMAL, self.col_left_x, y_pos)

            # --- DRAW MIDDLE PANE (Top: Options, Bottom: Details) ---
            for i, option in enumerate(self.middle_options):
                y_pos = self.start_y + (i * self.TEXT_NORMAL)
                self.game.draw_text(option, self.TEXT_NORMAL, self.col_mid_x, y_pos)

            # Bottom Details (Based on hovered card)
            self.draw_card_details()

            # --- DRAW RIGHT PANE (Deck) ---
            for i, card in enumerate(self.deck_cards):
                y_pos = self.start_y + (i * self.TEXT_NORMAL)
                self.game.draw_text(getattr(card, 'name', 'Unknown'), self.TEXT_NORMAL, self.col_right_x, y_pos)

            self.draw_cursor()
            self.blit_screen()

    def draw_card_details(self):
        """Draws the selected card details in the mid-bottom section."""
        selected_card = None
        if self.active_pane == ActivePane.AVAILABLE and self.available_cards:
            selected_card = self.available_cards[self.index_available]
        elif self.active_pane == ActivePane.DECK and self.deck_cards:
            selected_card = self.deck_cards[self.index_deck]

        detail_start_y = self.game.DISPLAY_H * 0.55
        self.game.draw_text('--- Card Details ---', self.TEXT_NORMAL, self.col_mid_x, detail_start_y)

        if selected_card:
            name = getattr(selected_card, 'name', 'N/A')
            hp = getattr(selected_card, 'hp', 'N/A')
            dmg = getattr(selected_card, 'dmg', 'N/A')
            image_path = getattr(selected_card, 'image', None)

            # Define Maximum Available Space (Bounding Box)
            max_w = (self.col_right_x - self.col_left_x) * 0.8
            image_start_y = detail_start_y + 30
            text_reserved_space = 80
            max_h = self.game.DISPLAY_H - image_start_y - text_reserved_space

            # Calculate Dynamic Dimensions (Maintaining Aspect Ratio)
            card_aspect_ratio = 5 / 7
            img_w = max_w
            img_h = img_w / card_aspect_ratio

            if img_h > max_h:
                img_h = max_h
                img_w = img_h * card_aspect_ratio

            img_w = int(img_w)
            img_h = int(img_h)

            # Center the Image and Draw
            img_x = self.col_mid_x - (img_w / 2)
            img_y = image_start_y

            if image_path:
                self.game.draw_image(image_path, img_x, img_y, img_w, img_h)

            # Position Text Dynamically Below the Image
            text_y = img_y + img_h + 20
            self.game.draw_text(f"Name: {name}", self.TEXT_NORMAL, self.col_mid_x, text_y)
            self.game.draw_text(f"HP: {hp} | DMG: {dmg}", self.TEXT_NORMAL, self.col_mid_x, text_y + 30)

    def update_cursor_pos(self):
        if self.active_pane == ActivePane.AVAILABLE:
            if len(self.available_cards) > 0:
                x = self.col_left_x
                y = self.start_y + (self.index_available * self.TEXT_NORMAL)
            else:
                x = self.col_left_x
                y = self.start_y
        elif self.active_pane == ActivePane.MIDDLE:
            x = self.col_mid_x
            y = self.start_y + (self.index_middle * self.TEXT_NORMAL)
        elif self.active_pane == ActivePane.DECK:
            if len(self.deck_cards) > 0:
                x = self.col_right_x
                y = self.start_y + (self.index_deck * self.TEXT_NORMAL)
            else:
                x = self.col_right_x
                y = self.start_y

        self.cursor_rect.midtop = (x + self.offset, y)

    def move_cursor(self):
        if self.game.RIGHT_KEY:
            self.game.RIGHT_KEY = False
            if self.active_pane == ActivePane.AVAILABLE:
                self.active_pane = ActivePane.MIDDLE
            elif self.active_pane == ActivePane.MIDDLE:
                self.active_pane = ActivePane.DECK
            self.update_cursor_pos()

        elif self.game.LEFT_KEY:
            self.game.LEFT_KEY = False
            if self.active_pane == ActivePane.DECK:
                self.active_pane = ActivePane.MIDDLE
            elif self.active_pane == ActivePane.MIDDLE:
                self.active_pane = ActivePane.AVAILABLE
            self.update_cursor_pos()

        elif self.game.DOWN_KEY:
            self.game.DOWN_KEY = False
            if self.active_pane == ActivePane.AVAILABLE and self.available_cards:
                self.index_available = (self.index_available + 1) % len(self.available_cards)
            elif self.active_pane == ActivePane.MIDDLE:
                self.index_middle = (self.index_middle + 1) % len(self.middle_options)
            elif self.active_pane == ActivePane.DECK and self.deck_cards:
                self.index_deck = (self.index_deck + 1) % len(self.deck_cards)
            self.update_cursor_pos()

        elif self.game.UP_KEY:
            self.game.UP_KEY = False
            if self.active_pane == ActivePane.AVAILABLE and self.available_cards:
                self.index_available = (self.index_available - 1) % len(self.available_cards)
            elif self.active_pane == ActivePane.MIDDLE:
                self.index_middle = (self.index_middle - 1) % len(self.middle_options)
            elif self.active_pane == ActivePane.DECK and self.deck_cards:
                self.index_deck = (self.index_deck - 1) % len(self.deck_cards)
            self.update_cursor_pos()

    def check_input(self):
        if getattr(self.game, 'START_KEY', False):
            self.game.START_KEY = False

            if self.active_pane == ActivePane.AVAILABLE:
                if self.available_cards and len(self.deck_cards) < 12:
                    card = self.available_cards[self.index_available]
                    self.deck_cards.append(card)

                    if self.deck_cards.count(card) >= 4:
                        self.available_cards.pop(self.index_available)
                        if self.index_available >= len(self.available_cards) and self.index_available > 0:
                            self.index_available -= 1

                    self.update_cursor_pos()

            elif self.active_pane == ActivePane.DECK:
                if self.deck_cards:
                    card = self.deck_cards.pop(self.index_deck)

                    if self.index_deck >= len(self.deck_cards) and self.index_deck > 0:
                        self.index_deck -= 1

                    if card not in self.available_cards:
                        self.available_cards.append(card)

                    self.update_cursor_pos()

            elif self.active_pane == ActivePane.MIDDLE:
                if self.index_middle == MiddleOptions.SAVE.value:
                    self._save_deck_logic()
                elif self.index_middle == MiddleOptions.RETURN.value:
                    self._return_to_previous()
                elif self.index_middle == MiddleOptions.DELETE.value:
                    self._delete_deck_logic()

        if getattr(self.game, 'BACK_KEY', False):
            self.game.BACK_KEY = False
            self._return_to_previous()

    # --- Action Helpers ---
    def _return_to_previous(self):
        self.run_display = False
        if hasattr(self, 'previous_menu'):
            self.game.curr_menu = self.previous_menu
            self.previous_menu.__init__(self.game)
            self.previous_menu.run_display = True

    def _get_deck_name_input(self):
        """Displays a simple overlay to capture text input for a new deck name."""
        input_text = ""
        input_active = True

        # Disable game standard event checking during this mini-loop
        while input_active:
            self.game.display.fill(self.game.BLACK)

            # Draw the prompt overlay
            self.game.draw_text("Enter Deck Name:", self.TEXT_LARGE, self.col_mid_x, self.game.DISPLAY_H / 2 - 50)
            self.game.draw_text(input_text + "_", self.TEXT_NORMAL, self.col_mid_x, self.game.DISPLAY_H / 2)
            self.game.draw_text("Press ENTER to save, ESC to cancel", self.TEXT_SMALL, self.col_mid_x, self.game.DISPLAY_H / 2 + 50)

            self.blit_screen()

            for event in pg.event.get():
                if event.type == pg.QUIT:
                    pg.quit()
                    exit()
                if event.type == pg.KEYDOWN:
                    if event.key == pg.K_RETURN:
                        return input_text.strip()
                    elif event.key == pg.K_ESCAPE:
                        return None
                    elif event.key == pg.K_BACKSPACE:
                        input_text = input_text[:-1]
                    else:
                        # Limit deck name length to avoid rendering issues
                        if len(input_text) < 20:
                            input_text += event.unicode

    def _save_deck_logic(self):
        # Local import to prevent circular dependencies
        from cards.deck import Deck

        # Ensure the deck isn't completely empty before trying to save
        if not self.deck_cards:
            return

        deck = Deck()
        deck.cards = self.deck_cards

        # If we are editing an existing deck, pull its old data
        if self.current_deck_id:
            deck.id = self.current_deck_id
            old_deck = self.db.load_deck(self.current_deck_id)
            if old_deck:
                deck.name = old_deck.name
                deck.description = old_deck.description
        else:
            # If it's a new deck, prompt for a name
            new_name = self._get_deck_name_input()

            # Consume any leftover inputs so they don't trigger menu actions instantly
            self.game.START_KEY = False
            self.game.BACK_KEY = False

            if new_name is None:
                return # User cancelled the save

            deck.name = new_name if new_name else "Custom Deck"

        # Save to DB and update our current state
        self.db.save_deck(deck)
        self.current_deck_id = deck.id

        # Optional UX: Flash a quick "Saved" indicator or just return to previous menu
        self._return_to_previous()

    def _delete_deck_logic(self):
        if self.current_deck_id:
            self.db.delete_deck(self.current_deck_id)

        # Once deleted, this editor session is invalid, so force close it
        self._return_to_previous()