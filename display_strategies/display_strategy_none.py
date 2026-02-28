from display_strategies.display_strategy import DisplayStrategy

class DisplayStrategyNone(DisplayStrategy):
    def __init__(self, _player, _opposing_player, _board):
        self.this_player    = _player
        self.board          = _board
        self.opponent       = _opposing_player
        self.dragon         = None # Must be passed at runtime


    def display_board(self):
        pass
    def display_mana(self):
        pass
    def display_dragon(self):
        pass
    def display_choice(self, card, position, use_ability, target):
        pass
    def display_dragon_vs_card(self):
        pass
    def display_battle_result(self):
        pass
    def display_hand(self):
        pass
    def display_status(self):
        pass
    def display_round(self, current_round):
        pass
    def display_player_on_turn(self, player_on_turn):
        pass
    def display_game_result(self, winner):
        pass
