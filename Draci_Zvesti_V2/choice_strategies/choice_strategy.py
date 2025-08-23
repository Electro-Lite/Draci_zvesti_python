
class PlayerChoiceStrategy:
    def __init__(self, _player):
        self.this_player = _player
        self.info = None

    # def display_card(self, card):
    #     raise NotImplementedError

    def get_choice_pos(self, game_board):
        raise NotImplementedError

    def get_choice_card(self):
        raise NotImplementedError

    def get_choice_use_ability(self):
        raise NotImplementedError

    def get_choice_pass(self):
        raise NotImplementedError
