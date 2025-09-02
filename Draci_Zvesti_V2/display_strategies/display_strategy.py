from typing                         import TYPE_CHECKING

if TYPE_CHECKING:
    from core.board     import Board
    from core.player    import Player
    from cards.card     import Card

class DisplayStrategy:
    def __init__(self, _player:"Player", _opposing_player:"Player", _board:"Board"):
        self.this_player    = _player
        self.board          = _board
        self.opponent       = _opposing_player
        self.dragon         = None # Must be passed at runtime

        raise NotImplementedError()

    def display_board(self):
        raise NotImplementedError()
    def display_mana(self):
        raise NotImplementedError()
    def display_dragon(self):
        raise NotImplementedError()
    def display_choice(self, card: "Card", position: int, use_ability: bool, target: int):
        raise NotImplementedError()
    def display_dragon_vs_card(self):
        raise NotImplementedError()
    def display_battle_result(self):
        raise NotImplementedError()
    def display_hand(self):
        raise NotImplementedError()
    def display_status(self):
        raise NotImplementedError()
    def display_round(self, current_round:int):
        raise NotImplementedError()
    def display_player_on_turn(self, player_on_turn:"Player"):
        raise NotImplementedError()
    def display_game_result(self, winner:"Player"):
        raise NotImplementedError()

