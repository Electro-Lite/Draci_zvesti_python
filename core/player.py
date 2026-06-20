from config import Config

# import decks  as     decks_lib
from choice_strategies.choice_strategy import PlayerChoiceStrategy
from core.hand import Hand

from typing                         import TYPE_CHECKING

if TYPE_CHECKING:
    from cards.deck         import Deck

class Player:
    
    def __init__(self, _id:int, _deck:"Deck", _choice_strategy:PlayerChoiceStrategy):
        if not issubclass(_choice_strategy, PlayerChoiceStrategy):
            raise ValueError(f"Invalid Choice Strategy: {_choice_strategy}")
        
        if _deck == None:
            raise ValueError("Missing deck")

        self.id         = _id
        self.choice_strategy     = _choice_strategy(self)
        
        self.deck       = _deck # Deck
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
    def get_card_count(self) -> int:
        """ Cards in hand + cards in deck"""
        return len(self.hand.cards) + len(self.deck.cards)