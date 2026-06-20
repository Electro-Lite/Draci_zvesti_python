import threading
import queue
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.player import Player
    from core.board import Board
    from cards.card import Card

from display_strategies.display_strategy import DisplayStrategy

class DisplayStrategyPygame(DisplayStrategy):
    def __init__(self, _player: "Player", _opposing_player: "Player", _board: "Board"):
        super().__init__(_player, _opposing_player, _board)
        
        # --- SYNCHRONIZATION TOOLS ---
        # The Lock protects data from being read by Pygame while Logic is writing it
        self.lock = threading.Lock()
        
        # The Queue allows Pygame to send click data to the waiting Logic thread
        self.input_queue = queue.Queue()
        
        # --- UI STATE (Read by Pygame Loop) ---
        self.waiting_for: Optional[str] = None  # e.g., "CARD", "POSITION", "PASS"
        self.status_message: str = "Game Start"
        self.last_battle_result: str = ""
        self.winner: Optional["Player"] = None
        
        # We store these just in case we need to highlight specific cards during animation
        self.active_card: Optional["Card"] = None
        self.active_target: Optional[int] = None

    # --- IMPLEMENTATION OF ABSTRACT METHODS ---
    
    def display_board(self):
        with self.lock:
            # We don't "draw" here. We signal that the board state is ready/changed.
            # Since self.board is a reference, Pygame already sees the changes,
            # but you might want to toggle a flag to trigger a sound or animation.
            pass 

    def display_mana(self):
        with self.lock:
            # Pygame will read self.this_player.mana in its draw loop
            pass

    def display_dragon(self):
        with self.lock:
            # Update state to show the dragon is currently active/attacking
            self.status_message = f"Dragon {self.dragon.name} is attacking!"

    def display_choice(self, card: "Card", position: int, use_ability: bool, target: int):
        with self.lock:
            self.status_message = f"Opponent placed {card.name} at {position}"
            self.active_card = card

    def display_dragon_vs_card(self):
        with self.lock:
            # You might use this to set a 'battle_animation_state' variable
            self.status_message = "Battle in progress..."

    def display_battle_result(self):
        with self.lock:
            self.status_message = "Battle resolved."

    def display_hand(self):
        # Hand is always visible in Pygame usually, so this might be no-op
        # or used to trigger a "deal cards" animation.
        pass

    def display_status(self):
        with self.lock:
            pass # Status is pulled continuously in Pygame

    def display_round(self, current_round: int):
        with self.lock:
            self.status_message = f"--- Round {current_round} ---"

    def display_player_on_turn(self, player_on_turn: "Player"):
        with self.lock:
            self.status_message = f"{player_on_turn.name}'s Turn"

    def display_game_result(self, winner: "Player"):
        with self.lock:
            self.winner = winner
            self.status_message = f"Game Over! Winner: {winner.name if winner else 'Draw'}"