from config import Config
from core.player_type import PlayerType
# import decks  as     decks_lib
# from player_choice import player_choice
from core.hand import Hand

class Player:
    
    def __init__(self, _id, _type:PlayerType = Config.default_player_type):
        if not isinstance(_type, PlayerType):
            raise ValueError(f"Invalid player type: {_type}")
        
        self.id         = _id
        self.type       = _type
        # self.choice     = player_choice(self)
        
        # self.deck       = decks_lib.deck()
        self.hand       = Hand()
        self.graveyard  = []
        
        
        self.net        = None #nn.FeedForwardNetwork
        self.fitness    = 10
        
        self.score      = 0
        self.passed     = False
    
    def draw_hand(self):
        self.draw_cards(5)
        
    def draw_cards(self,num):
        
        if len(self.deck.cards)<num:
            num = len(self.deck.cards)
            
        for x in range(num):
            card_tmp = self.deck.cards.pop()
            self.hand.cards.append(card_tmp)