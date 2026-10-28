from cards.ability.ability_target import AbilityTarget
from cards.ability.abilities import can_use_on_play
from choice_strategies.choice_strategy import PlayerChoiceStrategy
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from cards.card import Card
    from core.board import Board
    from core.player import Player


class ChoiceStrategyPygame(PlayerChoiceStrategy):
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
        legal_positions = self.legal_placement_positions()
        print("\n📍 Choose position (0–{}):".format(len(positions) - 1))
        for i, card in enumerate(positions):
            if i in legal_positions and card is None:
                print(f"  [{i}] EMPTY")
            elif i in legal_positions:
                print(f"  [{i}] Player_{card.owner.id} - {card.name} (DMG:{card.dmg}, HP:{card.hp})")

        # Find first empty slot for fallback (do not mutate anything)
        def fallback_fn():
            if legal_positions:
                return legal_positions[0]
            # no empty slot
            raise IndexError("No empty space on board")

        def validate(user_in: str) -> int:
            try:
                pos = int(user_in)
            except ValueError:
                raise ValueError("Please enter a valid integer index.")
            if pos < 0 or pos >= len(positions):
                raise ValueError("Invalid index.")
            if pos not in legal_positions:
                raise ValueError("Position is not legal for this card.")
            return pos

        # If board is full, match AI behavior and raise
        if not legal_positions:
            raise IndexError("No legal space on board")

        return self._retry_input("▶ Enter position index: ", validate, fallback_fn)

    def get_choice_card(self) -> "Card":
        cards = self.this_player.hand.cards
        legal = self.legal_play_card_indices()
        if not legal:
            raise IndexError("No legal cards in hand")

        print("\n🃏 Your hand:")
        for i in legal:
            card = cards[i]
            print(f"  [{i}] {card.name} (DMG:{card.dmg}, HP:{card.hp})")

        # fallback pops the first card but only when actually used
        def fallback_fn():
            if not legal:
                raise IndexError("No cards in hand to fallback to.")
            return self.this_player.hand.cards.pop(legal[0])

        def validate(user_in: str):
            try:
                idx = int(user_in)
            except ValueError:
                raise ValueError("Please enter a valid integer index.")
            if idx not in legal:
                raise ValueError("Invalid card index.")
            # pop and return the selected card
            return self.this_player.hand.cards.pop(idx)

        self.selected_card = self._retry_input(
            "▶ Choose a card index: ", validate, fallback_fn
        )
        return self.selected_card

    def get_choice_use_ability(self) -> bool:
        card = getattr(self, "selected_card", None)
        if card is None or not can_use_on_play(card.ability):
            return False
        board = self.info.game_board
        if not card.ability.can_activate(card, board):
            return False

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
        if not self.legal_play_card_indices():
            return True
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
        source = getattr(self, "selected_card", None)
        if source is None:
            return None
        custom = source.ability.legal_target_positions(source, game_board)
        if custom is not None:
            legal_positions = list(custom)
        else:
            target_owner = getattr(source.ability, "target_owner", AbilityTarget.ANY)
            legal_positions = []
            for index, candidate in enumerate(positions):
                if candidate is None:
                    continue
                if target_owner == AbilityTarget.ANY:
                    legal_positions.append(index)
                elif target_owner == AbilityTarget.ALLY and candidate.owner is self.this_player:
                    legal_positions.append(index)
                elif target_owner == AbilityTarget.ENEMY and candidate.owner is not self.this_player:
                    legal_positions.append(index)

        print("\n🎯 Choose ability target:")
        option_labels = getattr(source.ability, "option_labels", ())
        for i, card in enumerate(positions):
            if i in legal_positions and i < len(option_labels):
                print(f"  [{i}] {option_labels[i]}")
            elif i in legal_positions and card is None:
                print(f"  [{i}] EMPTY")
            elif i in legal_positions:
                print(f"  [{i}] Player_{card.owner.id} - {card.name} (DMG:{card.dmg}, HP:{card.hp})")

        def fallback_fn():
            if not legal_positions:
                raise IndexError("No valid ability targets available.")
            return legal_positions[0]

        def validate(user_in: str) -> int:
            try:
                pos = int(user_in)
            except ValueError:
                raise ValueError("Please enter a valid integer index.")
            if pos < 0 or pos >= len(positions):
                raise ValueError("Invalid index.")
            if pos not in legal_positions:
                raise ValueError("That is not a legal target for this ability.")
            return pos

        if not legal_positions:
            return None

        return self._retry_input("▶ Enter target position index: ", validate, fallback_fn)

    def get_choice_ability_card(self):
        source = getattr(self, "selected_card", None)
        if source is None:
            return None
        legal = source.ability.legal_hand_card_indices(source, self.info.game_board)
        if not legal:
            return None
        cards = self.this_player.hand.cards
        for index in legal:
            print(f"  [{index}] {cards[index].name}")

        def validate(user_in):
            index = int(user_in)
            if index not in legal:
                raise ValueError("That card is not legal for this ability")
            return cards[index]

        return self._retry_input(
            "▶ Choose the second card: ",
            validate,
            lambda: cards[legal[0]],
        )

    def get_choice_zone_card(self, cards, *, zone, board, source_card=None):
        candidates = list(cards)
        if not candidates:
            return None
        print(f"\nChoose a card from your {zone}:")
        for index, candidate in enumerate(candidates):
            print(f"  [{index}] {candidate.name}")

        def validate(user_in):
            index = int(user_in)
            if not 0 <= index < len(candidates):
                raise ValueError("That card is not available")
            return candidates[index]

        return self._retry_input(
            "▶ Choose card: ",
            validate,
            lambda: candidates[0],
        )
