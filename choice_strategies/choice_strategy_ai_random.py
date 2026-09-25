from random import choice, randint

from cards.ability.ability_target import AbilityTarget
from choice_strategies.choice_strategy import PlayerChoiceStrategy


class ChoiceStrategyAIRandom(PlayerChoiceStrategy):
    def __init__(self, player):
        super().__init__(player)
        self.selected_card = None
        self.selected_position = None

    def get_choice_pos(self):
        game_board = self.info.game_board
        start_pos = randint(0, 5)
        for offset in range(6):
            pos = (start_pos + offset) % 6
            if game_board.positions[pos] is None:
                self.selected_position = pos
                return pos
        raise IndexError("No empty space on board")

    def get_choice_card(self):
        cards_in_hand = len(self.this_player.hand.cards)
        self.selected_card = self.this_player.hand.cards.pop(
            randint(0, cards_in_hand - 1)
        )
        return self.selected_card

    def get_choice_use_ability(self):
        if self.selected_card is None or not self.selected_card.ability.is_active:
            return False
        if not getattr(self.selected_card.ability, "requires_target", False):
            return True
        return bool(self._legal_targets())

    def get_choice_pass(self):
        return False

    def _legal_targets(self):
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
                owner = self.this_player
            elif card is None:
                continue
            else:
                owner = card.owner
            if target_owner == AbilityTarget.ANY:
                legal.append(index)
            elif target_owner == AbilityTarget.ALLY and owner is self.this_player:
                legal.append(index)
            elif target_owner == AbilityTarget.ENEMY and owner is not self.this_player:
                legal.append(index)
        return legal

    def get_choice_ability_target(self):
        if self.selected_card is None or not getattr(
            self.selected_card.ability,
            "requires_target",
            False,
        ):
            return None
        legal = self._legal_targets()
        return choice(legal) if legal else None
