from typing                         import TYPE_CHECKING

if TYPE_CHECKING:
    from core.board     import Board
    from core.player    import Player

class DisplayStrategy:
    def __init__(self, _player:"Player", _opposing_player:"Player", _board:"Board"):
        raise NotImplementedError()
        self.this_player    = _player
        self.board          = _board
        self.opponent       = _opposing_player
        self.dragon         = _dragon # Must be passed at runtime

        self.info           = None

    def display_board(self):
        raise NotImplementedError()
    def display_mana(self):
        raise NotImplementedError()
    def display_dragon(self):
        raise NotImplementedError()
    def display_choice(self):
        raise NotImplementedError()
    def display_dragon_vs_card(self):
        raise NotImplementedError()
    def display_battle_result(self):
        raise NotImplementedError()
    def display_hand(self):
        raise NotImplementedError()
    def display_status(self):
        raise NotImplementedError()
    def display_round(self):
        raise NotImplementedError()
    def display_player_on_turn(self):
        raise NotImplementedError()
    def display_game_result(self):
        raise NotImplementedError()
