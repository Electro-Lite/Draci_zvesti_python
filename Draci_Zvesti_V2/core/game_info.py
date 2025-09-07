from core.board import Board
from core.player import Player
from cards.mana import ManaColor
class GameInfo:
    def __init__(self, _game_board:Board = None, _player_on_turn:Player = None, _opposing_player:Player = None):
        self.game_board     = _game_board
        self.player_on_turn    = _player_on_turn
        self.opponent       = _opposing_player

    def _get_card_neat_ids(self, card): pass
        
    def get_game_info(self):
        info = []
        positions = self.game_board.positions
        # Round number
        # Score
        # Mana color
        info.append(self.game_board.mana_pool[0].color.value)
        # Dragons remaining (Colors, 4 values)
        dragons = self.game_board.dragons
        dragon_colors = [d.color for d in dragons]
        info.append(1 if dragon_colors.count(ManaColor.BLUE)  >0 else 0)   # Blue
        info.append(1 if dragon_colors.count(ManaColor.RED)   >0 else 0)   # Red
        info.append(1 if dragon_colors.count(ManaColor.BLACK) >0 else 0)   # Black
        info.append(1 if dragon_colors.count(ManaColor.GREEN) >0 else 0)   # Green

        # Card count opponent hand
        info.append( len( self.opponent.hand.cards))
        # Card count opponent deck
        info.append( len( self.opponent.deck.cards))
        # Card count in deck
        info.append( len( self.player_on_turn.deck.cards))
        # Board (card_id + owner on each positopn)
        for pos in positions:
            info.extend(self._get_card_neat_ids(pos))

        # Cards in hand
        player_hand         = self.player_on_turn.hand.cards
        player_card_count   = len(self.player_on_turn.hand.cards)
        for i in range(0, 12):
            if player_card_count > i:
                info.extend( self._get_card_neat_ids( player_hand[i]))
            else:
                info.extend( self._get_card_neat_ids( None))

        return info
    

    def _get_card_neat_ids(self, card):

        neat_ids  = []
        if card is None:
            neat_ids.extend( [0] * 8)
            return neat_ids
        neat_ids = card.get_neat_ids()
        # owner
        neat_ids.append( self.player_on_turn.id if card.owner == None else card.owner.id )
        return neat_ids
    