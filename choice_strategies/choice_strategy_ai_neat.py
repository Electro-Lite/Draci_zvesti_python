from choice_strategies.choice_strategy import PlayerChoiceStrategy
from cards.ability.ability_target import AbilityTarget


PLAY_PASS = slice(0, 2)
HAND_CARD = slice(2, 14)
BOARD_POSITION = slice(14, 20)
USE_ABILITY = slice(20, 22)
ABILITY_TARGET = slice(22, 28)
ACTION_OUTPUT_COUNT = 28


class PlayerChoiceStrategyNeat(PlayerChoiceStrategy):
    def __init__(self, _player):
        super().__init__(_player)
        self._turn_outputs = None
        self._selected_card = None
        self._selected_position = None
        self._use_ability = False

    def begin_turn_choices(self):
        outputs = list(self.this_player.net.activate(self.info.get_game_info()))
        if len(outputs) != ACTION_OUTPUT_COUNT:
            raise RuntimeError(
                f"Expected {ACTION_OUTPUT_COUNT} NEAT outputs, got {len(outputs)}"
            )
        self._turn_outputs = outputs
        self._selected_card = None
        self._selected_position = None
        self._use_ability = False

    def end_turn_choices(self):
        self._turn_outputs = None
        self._selected_card = None
        self._selected_position = None
        self._use_ability = False

    def _get_outputs(self):
        if self._turn_outputs is None:
            self.begin_turn_choices()
        return self._turn_outputs

    def _argmax(self, output_slice, legal_indices):
        values = self._get_outputs()[output_slice]
        legal = list(legal_indices)
        if not legal:
            raise RuntimeError("No legal action is available")
        return max(legal, key=lambda index: (values[index], -index))

    def get_choice_pass(self) -> bool:
        # Index 0 means play; index 1 means pass.
        return self._argmax(PLAY_PASS, (0, 1)) == 1

    def get_choice_card(self):
        hand = self.this_player.hand.cards
        choice = self._argmax(HAND_CARD, range(len(hand)))
        self._selected_card = hand.pop(choice)
        return self._selected_card

    def get_choice_pos(self) -> int:
        positions = self.info.game_board.positions
        self._selected_position = self._argmax(
            BOARD_POSITION,
            (index for index, card in enumerate(positions) if card is None),
        )
        return self._selected_position

    def _legal_ability_targets(self):
        ability = self._selected_card.ability
        target_owner = getattr(ability, "target_owner", AbilityTarget.ANY)
        if target_owner == AbilityTarget.DRAGON:
            return []

        legal = []
        for index, card in enumerate(self.info.game_board.positions):
            if index == self._selected_position:
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

    def get_choice_use_ability(self) -> bool:
        if self._selected_card is None or not self._selected_card.ability.is_active:
            return False
        target_owner = getattr(
            self._selected_card.ability,
            "target_owner",
            AbilityTarget.ANY,
        )
        if target_owner != AbilityTarget.DRAGON and not self._legal_ability_targets():
            return False
        # Index 0 means skip; index 1 means use.
        self._use_ability = self._argmax(USE_ABILITY, (0, 1)) == 1
        return self._use_ability

    def get_choice_ability_target(self) -> int:
        if not self._use_ability:
            return 0
        if self._selected_card.ability.target_owner == AbilityTarget.DRAGON:
            return 0
        return self._argmax(ABILITY_TARGET, self._legal_ability_targets())
