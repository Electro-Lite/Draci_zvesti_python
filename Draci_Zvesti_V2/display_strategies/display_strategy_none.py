from display_strategies.display_strategy import DisplayStrategy

class DisplayStrategyNone(DisplayStrategy):
    def __init__(self, _player_1, _player_2, _board):
        self.player_1       = _player_1
        self.player_2       = _player_2
        self.board          = _board
        self.info           = None

    def display_board(self):
        pass
    def display_mana(self):
        pass
    def display_dragon(self):
        pass
    def display_dragon_vs_card(self):
        pass
    def diplay_battle_result(self):
        pass
    def display_hand(self):
        pass
    def display_status(self):
        pass
    def display_round(self):
        pass
    def display_game_result(self):
        pass
