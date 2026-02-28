from choice_strategies.choice_strategy import PlayerChoiceStrategy
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from cards.card import Card
    from core.board import Board
    from core.player import Player


class ChoiceStrategyCLI(PlayerChoiceStrategy):
    """Human player strategy via CLI with retries and safe fallbacks.
    Input prompts and logs follow the DisplayStrategyCLI style.
    """

    MAX_RETRIES = 3  # configurable

    def _retry_input(self, prompt: str, validate_fn: Callable[[str], object], fallback_fn: Callable[[], object] = None):
        """Generic retry loop with validation and an optional fallback callable.

        - validate_fn(user_input) should return the validated value OR raise Exception on invalid input.
        - fallback_fn() is called if retries are exhausted; if None, IndexError is raised.
        """
        retries = 0
        while retries < self.MAX_RETRIES:
            user_in = input(prompt)
            try:
                value = validate_fn(user_in)
                return value
            except Exception as e:
                print("⚠️ " + str(e))
                retries += 1

        # retries exhausted
        if fallback_fn is None:
            raise IndexError("No valid input and no fallback available.")
        print("⚠️ Too many invalid attempts. Falling back to a safe choice.")
        return fallback_fn()

    def get_choice_pos(self) -> int:
        game_board = self.info.game_board
        positions = game_board.positions
        print("\n📍 Choose position (0–{}):".format(len(positions) - 1))
        for i, card in enumerate(positions):
            if card is None:
                print(f"  [{i}] EMPTY")
            else:
                print(f"  [{i}] Player_{card.owner.id} - {card.name} (DMG:{card.dmg}, HP:{card.hp})")

        # Find first empty slot for fallback (do not mutate anything)
        def fallback_fn():
            for i, c in enumerate(positions):
                if c is None:
                    return i
            # no empty slot
            raise IndexError("No empty space on board")

        def validate(user_in: str) -> int:
            try:
                pos = int(user_in)
            except ValueError:
                raise ValueError("Please enter a valid integer index.")
            if pos < 0 or pos >= len(positions):
                raise ValueError("Invalid index.")
            if positions[pos] is not None:
                raise ValueError("Position already occupied.")
            return pos

        # If board is full, match AI behavior and raise
        if not any(p is None for p in positions):
            raise IndexError("No empty space on board")

        return self._retry_input("▶ Enter position index: ", validate, fallback_fn)

    def get_choice_card(self) -> "Card":
        cards = self.this_player.hand.cards
        if not cards:
            raise IndexError("No cards in hand")

        print("\n🃏 Your hand:")
        for i, card in enumerate(cards):
            print(f"  [{i}] {card.name} (DMG:{card.dmg}, HP:{card.hp})")

        # fallback pops the first card but only when actually used
        def fallback_fn():
            if not self.this_player.hand.cards:
                raise IndexError("No cards in hand to fallback to.")
            return self.this_player.hand.cards.pop(0)

        def validate(user_in: str):
            try:
                idx = int(user_in)
            except ValueError:
                raise ValueError("Please enter a valid integer index.")
            if idx < 0 or idx >= len(self.this_player.hand.cards):
                raise ValueError("Invalid card index.")
            # pop and return the selected card
            return self.this_player.hand.cards.pop(idx)

        return self._retry_input("▶ Choose a card index: ", validate, fallback_fn)

    def get_choice_use_ability(self) -> bool:
        def validate(user_in: str) -> bool:
            s = user_in.strip().lower()
            if s in ("y", "yes"):
                return True
            if s in ("n", "no"):
                return False
            raise ValueError("Please enter 'y' or 'n'.")

        # fallback = False (do not use ability)
        return self._retry_input("✨ Use ability? (y/n): ", validate, lambda: False)

    def get_choice_pass(self) -> bool:
        def validate(user_in: str) -> bool:
            s = user_in.strip().lower()
            if s in ("y", "yes"):
                return True
            if s in ("n", "no"):
                return False
            raise ValueError("Please enter 'y' or 'n'.")

        # fallback = False (don't pass)
        return self._retry_input("⏸️ Do you want to pass your turn? (y/n): ", validate, lambda: False)

    def get_choice_ability_target(self) -> int:
        game_board = self.info.game_board
        positions = game_board.positions
        print("\n🎯 Choose ability target (cannot target your own cards):")
        for i, card in enumerate(positions):
            if card is None:
                print(f"  [{i}] EMPTY")
            else:
                print(f"  [{i}] Player_{card.owner.id} - {card.name} (DMG:{card.dmg}, HP:{card.hp})")

        # build list of enemy targets for fallback
        enemy_positions = [i for i, c in enumerate(positions) if c is not None and c.owner.id != self.this_player.id]

        def fallback_fn():
            if not enemy_positions:
                raise IndexError("No valid enemy targets available.")
            return enemy_positions[0]

        def validate(user_in: str) -> int:
            try:
                pos = int(user_in)
            except ValueError:
                raise ValueError("Please enter a valid integer index.")
            if pos < 0 or pos >= len(positions):
                raise ValueError("Invalid index.")
            if positions[pos] is None:
                raise ValueError("That position is empty.")
            if positions[pos].owner.id == self.this_player.id:
                raise ValueError("You cannot target your own card.")
            return pos

        if not enemy_positions:
            raise IndexError("No valid enemy targets available.")

        return self._retry_input("▶ Enter target position index: ", validate, fallback_fn)
