from cards.mana import ManaColor
from config import Config
from core.board import Board
from core.player import Player


CARD_FEATURE_COUNT = 8
BOARD_POSITION_COUNT = 6
HAND_SLOT_COUNT = 12
GAME_INFO_INPUT_COUNT = 158


class GameInfo:
    def __init__(self, _game_board: Board = None, _opposing_player: Player = None):
        self.game_board = _game_board
        self.player_on_turn = _game_board.player_on_turn
        self.opponent = _opposing_player

    @staticmethod
    def _scale(value, maximum):
        return float(value) / float(maximum) if maximum else 0.0

    def get_game_info(self):
        player = self.player_on_turn
        board = self.game_board
        mana = board.mana_pool[0].color

        info = [
            1.0 if mana == ManaColor.RED else 0.0,
            1.0 if mana == ManaColor.BLACK else 0.0,
            1.0 if mana == ManaColor.BLUE else 0.0,
        ]

        dragon_colors = [dragon.color for dragon in board.dragons]
        info.extend(
            1.0 if color in dragon_colors else 0.0
            for color in (
                ManaColor.BLUE,
                ManaColor.RED,
                ManaColor.BLACK,
                ManaColor.GREEN,
            )
        )

        info.extend(
            [
                self._scale(board.round, Config.max_rounds),
                self._scale(player.score, 2),
                self._scale(self.opponent.score, 2),
                1.0 if self.opponent.passed else 0.0,
                self._scale(len(self.opponent.hand.cards), HAND_SLOT_COUNT),
                self._scale(len(self.opponent.deck.cards), HAND_SLOT_COUNT),
                self._scale(len(player.deck.cards), HAND_SLOT_COUNT),
            ]
        )

        for card in board.positions:
            info.extend(self._get_card_neat_ids(card))

        for index in range(HAND_SLOT_COUNT):
            card = player.hand.cards[index] if index < len(player.hand.cards) else None
            info.extend(self._get_card_neat_ids(card))

        if len(info) != GAME_INFO_INPUT_COUNT:
            raise RuntimeError(
                f"Expected {GAME_INFO_INPUT_COUNT} NEAT inputs, got {len(info)}"
            )
        return info

    def _get_card_neat_ids(self, card):
        if card is None:
            return [0.0] * CARD_FEATURE_COUNT

        features = card.get_neat_ids()
        owner = 0.0
        if card.owner is not None:
            owner = 1.0 if card.owner == self.player_on_turn else -1.0

        return [
            self._scale(features[0], 2),
            self._scale(features[1], 4),
            self._scale(features[2], 3),
            self._scale(features[3], 3),
            self._scale(features[4], 9),
            self._scale(features[5], 9),
            self._scale(features[6], 32),
            owner,
        ]
