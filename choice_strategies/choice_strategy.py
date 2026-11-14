from cards.card import Card 

class PlayerChoiceStrategy:
    def __init__(self, _player):
        self.this_player = _player
        self.info = None
        self.selected_card = None

    def get_choice_pos(self, game_board) -> int:
        raise NotImplementedError

    def get_choice_card(self) -> Card:
        raise NotImplementedError

    def get_choice_use_ability(self) -> bool:
        raise NotImplementedError

    def get_choice_pass(self) -> bool:
        raise NotImplementedError
    
    def get_choice_ability_target(self) -> int:
        raise NotADirectoryError

    def get_choice_ability_card(self):
        raise NotImplementedError

    def get_choice_zone_card(self, cards, *, zone, board, source_card=None):
        """Choose one card from a non-hand zone during triggered resolution."""
        candidates = list(cards)
        return candidates[0] if candidates else None

    def legal_play_card_indices(self):
        hand = self.this_player.hand.cards
        board = self.info.game_board if self.info else None
        if board is None or not hasattr(board, "can_stage_card"):
            return list(range(len(hand)))
        return [
            index
            for index, card in enumerate(hand)
            if board.can_stage_card(card, self.this_player)
            and bool(board.legal_placement_positions(card, self.this_player))
        ]

    def legal_placement_positions(self, card=None):
        board = self.info.game_board if self.info else None
        if board is None:
            return []
        selected = card or self.selected_card
        if selected is None or not hasattr(board, "legal_placement_positions"):
            return [
                index
                for index, occupant in enumerate(board.positions)
                if occupant is None
            ]
        return board.legal_placement_positions(selected, self.this_player)
