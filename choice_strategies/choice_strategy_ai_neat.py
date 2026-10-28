from choice_strategies.choice_strategy import PlayerChoiceStrategy
from cards.ability.ability_target import AbilityTarget
from cards.ability.abilities import can_use_on_play


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
        if not self.legal_play_card_indices():
            return True
        # Index 0 means play; index 1 means pass.
        return self._argmax(PLAY_PASS, (0, 1)) == 1

    def get_choice_card(self):
        hand = self.this_player.hand.cards
        choice = self._argmax(HAND_CARD, self.legal_play_card_indices())
        self._selected_card = hand.pop(choice)
        return self._selected_card

    def get_choice_pos(self) -> int:
        self._selected_position = self._argmax(
            BOARD_POSITION,
            self.legal_placement_positions(),
        )
        return self._selected_position

    def _legal_ability_targets(self):
        ability = self._selected_card.ability
        custom_targets = getattr(ability, "legal_target_positions", None)
        custom = (
            custom_targets(self._selected_card, self.info.game_board)
            if custom_targets is not None
            else None
        )
        if custom is not None:
            return list(custom)
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
        if self._selected_card is None or not can_use_on_play(self._selected_card.ability):
            return False
        can_activate = getattr(self._selected_card.ability, "can_activate", None)
        if can_activate is not None and not can_activate(
            self._selected_card, self.info.game_board
        ):
            return False
        if (
            getattr(self._selected_card.ability, "requires_target", False)
            and not self._legal_ability_targets()
        ):
            return False
        # Index 0 means skip; index 1 means use.
        self._use_ability = self._argmax(USE_ABILITY, (0, 1)) == 1
        return self._use_ability

    def get_choice_ability_target(self) -> int:
        if not self._use_ability:
            return None
        if not getattr(self._selected_card.ability, "requires_target", False):
            return None
        return self._argmax(ABILITY_TARGET, self._legal_ability_targets())

    def get_choice_ability_card(self):
        legal = self._selected_card.ability.legal_hand_card_indices(
            self._selected_card,
            self.info.game_board,
        )
        index = self._argmax(HAND_CARD, legal)
        return self.this_player.hand.cards[index]

    def get_choice_zone_card(self, cards, *, zone, board, source_card=None):
        candidates = list(cards)
        if not candidates:
            return None
        previous_turn = self.info.player_on_turn
        self.info.player_on_turn = self.this_player
        try:
            outputs = list(self.this_player.net.activate(self.info.get_game_info()))
        finally:
            self.info.player_on_turn = previous_turn
        values = outputs[HAND_CARD]
        legal = range(min(len(candidates), len(values)))
        index = max(legal, key=lambda item: (values[item], -item))
        return candidates[index]
