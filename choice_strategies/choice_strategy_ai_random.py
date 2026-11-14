from random import choice, randint

from cards.ability.ability_target import AbilityTarget
from cards.ability.abilities import can_use_on_play
from choice_strategies.choice_strategy import PlayerChoiceStrategy


class ChoiceStrategyAIRandom(PlayerChoiceStrategy):
    def __init__(self, player):
        super().__init__(player)
        self.selected_card = None
        self.selected_position = None

    def get_choice_pos(self):
        legal = self.legal_placement_positions()
        if not legal:
            raise IndexError("No legal space on board")
        self.selected_position = choice(legal)
        return self.selected_position

    def get_choice_card(self):
        legal = self.legal_play_card_indices()
        if not legal:
            raise IndexError("No legal card can be played")
        self.selected_card = self.this_player.hand.cards.pop(choice(legal))
        return self.selected_card

    def get_choice_use_ability(self):
        if self.selected_card is None or not can_use_on_play(self.selected_card.ability):
            return False
        can_activate = getattr(self.selected_card.ability, "can_activate", None)
        if can_activate is not None and not can_activate(
            self.selected_card, self.info.game_board
        ):
            return False
        if not getattr(self.selected_card.ability, "requires_target", False):
            return True
        return bool(self._legal_targets())

    def get_choice_pass(self):
        return not self.legal_play_card_indices()

    def _legal_targets(self):
        if self.selected_card is None:
            return []
        custom_targets = getattr(
            self.selected_card.ability,
            "legal_target_positions",
            None,
        )
        custom = (
            custom_targets(self.selected_card, self.info.game_board)
            if custom_targets is not None
            else None
        )
        if custom is not None:
            return list(custom)
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

    def get_choice_ability_card(self):
        legal = self.selected_card.ability.legal_hand_card_indices(
            self.selected_card,
            self.info.game_board,
        )
        return self.this_player.hand.cards[choice(legal)] if legal else None
