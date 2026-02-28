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
