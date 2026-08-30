from enum import Enum
from time import sleep

from cards.ability.ability_target import AbilityTarget
from cards.card import Card
from choice_strategies.choice_strategy import PlayerChoiceStrategy


class ChoiceType(Enum):
    NONE = 0
    CARD = 1
    POSITION = 2
    PASS = 3
    USE_ABILITY = 4
    TARGET = 5


class PygameChoiceStrategy(PlayerChoiceStrategy):
    """Blocking human strategy bridged to the pygame event loop."""

    def __init__(self, player):
        super().__init__(player)
        self.choice = None
        self.waiting_for = ChoiceType.NONE
        self.do_exit = False
        self.selected_card = None
        self.selected_position = None

    def _wait_for_input(self, waiting_for: ChoiceType):
        self.waiting_for = waiting_for
        while self.choice is None:
            if self.do_exit:
                self.waiting_for = ChoiceType.NONE
                raise SystemExit
            sleep(0.02)
        self.waiting_for = ChoiceType.NONE
        choice = self.choice
        self.choice = None
        return choice

    def set_choice(self, choice_type: ChoiceType, choice_value):
        if self.waiting_for != choice_type:
            return False
        self.choice = choice_value
        return True

    def get_choice_card(self) -> Card:
        card = self._wait_for_input(ChoiceType.CARD)
        position = self.this_player.hand.cards.index(card)
        self.selected_card = self.this_player.hand.cards.pop(position)
        return self.selected_card

    def get_choice_pos(self) -> int:
        self.selected_position = self._wait_for_input(ChoiceType.POSITION)
        return self.selected_position

    def exit_thread(self):
        self.do_exit = True

    def get_choice_pass(self) -> bool:
        self.selected_card = None
        self.selected_position = None
        return bool(self._wait_for_input(ChoiceType.PASS))

    def get_choice_use_ability(self) -> bool:
        if self.selected_card is None or not self.selected_card.ability.is_active:
            return False
        target_owner = getattr(
            self.selected_card.ability,
            "target_owner",
            AbilityTarget.ANY,
        )
        if target_owner != AbilityTarget.DRAGON and not self.legal_targets():
            return False
        return bool(self._wait_for_input(ChoiceType.USE_ABILITY))

    def legal_targets(self) -> list[int]:
        if self.selected_card is None:
            return []
        target_owner = getattr(
            self.selected_card.ability,
            "target_owner",
            AbilityTarget.ANY,
        )
        if target_owner == AbilityTarget.DRAGON:
            return []

        legal = []
        for index, card in enumerate(self.info.game_board.positions):
            if index == self.selected_position:
                card_owner = self.this_player
            elif card is None:
                continue
            else:
                card_owner = card.owner

            if target_owner == AbilityTarget.ANY:
                legal.append(index)
            elif target_owner == AbilityTarget.ALLY and card_owner == self.this_player:
                legal.append(index)
            elif target_owner == AbilityTarget.ENEMY and card_owner != self.this_player:
                legal.append(index)
        return legal

    def get_choice_ability_target(self) -> int:
        if self.selected_card is None:
            return 0
        if self.selected_card.ability.target_owner == AbilityTarget.DRAGON:
            return 0
        return self._wait_for_input(ChoiceType.TARGET)
