from core.board import board
from core.player import Player
from cards.mana import ManaColor
class GameInfo:
    def __init__(self, _game_board:board = None, _player_on_turn:Player = None):
        self.game_board = _game_board
        self.player_on_turn = _player_on_turn
        
    def get_game_info(self):
        info=[]
        
        info.append(len( self.player_on_turn.deck.cards)) #0
        
        player_hand = self.player_on_turn.hand.cards
        for card in  player_hand:
            info.append(card.id)       #1 12 hand card position
        i = len(player_hand) 
        while i<12:
            i+=1
            info.append(0)
            
        # num of cards in deck !
        if (self.game_board.positions[0] != None):
            info.append( self.game_board.positions[0].id)       #2.1.1
            info.append( self.game_board.positions[0].owner.id) #2.1.2
        else:
            info.append(0)
            info.append(0)
        if (self.game_board.positions[1] != None):
            info.append( self.game_board.positions[1].id)     #2.2.1
            info.append( self.game_board.positions[1].owner.id) #2.2.2
        else:
            info.append(0)
            info.append(0)
        if (self.game_board.positions[2] != None):
            info.append( self.game_board.positions[2].id)     #2.3.1
            info.append( self.game_board.positions[2].owner.id) #2.3.2
        else:
            info.append(0)
            info.append(0)
        if (self.game_board.positions[3] != None):
            info.append( self.game_board.positions[3].id)     #2.4.1
            info.append( self.game_board.positions[3].owner.id) #2.5.2
        else:
            info.append(0)
            info.append(0)
        if (self.game_board.positions[4] != None):
            info.append( self.game_board.positions[4].id)     #2.5.1
            info.append( self.game_board.positions[4].owner.id) #2.5.2
        else:
            info.append(0)
            info.append(0)
        if (self.game_board.positions[5] != None):
            info.append( self.game_board.positions[5].id)     #2.6.1
            info.append( self.game_board.positions[5].owner.id) #2.6.2
        else:
            info.append(0)
            info.append(0)
        
        color    = self.game_board.mana_pool[0].color
        color_id = 0
        if color == ManaColor.RED:
            color_id = 1
        if color == ManaColor.BLUE:
            color_id = 2
        if color == ManaColor.BLACK:
            color_id = 3
        info.append( color_id) #3
        #25 inputs
        return info