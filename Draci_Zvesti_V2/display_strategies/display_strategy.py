class DisplayStrategy:
    def __init__(self, _player):
        raise NotImplementedError
        self.this_player = _player
        self.info = None

    def display_board(self, card):
        raise NotImplementedError
