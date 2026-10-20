from cards.card import Card 

class PlayerChoiceStrategy:
    def __init__(self, _player):
        self.this_player = _player
        self.info = None

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

    def legal_play_card_indices(self):
        hand = self.this_player.hand.cards
        board = getattr(getattr(self, "info", None), "game_board", None)
        can_stage = getattr(board, "can_stage_card", None) if board is not None else None
        if can_stage is None:
            return list(range(len(hand)))
        return [
            index
            for index, card in enumerate(hand)
            if can_stage(card, self.this_player)
        ]

    def legal_placement_positions(self, card=None):
        board = getattr(getattr(self, "info", None), "game_board", None)
        selected = card or getattr(self, "selected_card", None) or getattr(
            self, "_selected_card", None
        )
        if board is None:
            return []
        placement = getattr(board, "legal_placement_positions", None)
        if selected is None or placement is None:
            return [
                index
                for index, occupant in enumerate(getattr(board, "positions", ()))
                if occupant is None
            ]
        return placement(selected, self.this_player)
