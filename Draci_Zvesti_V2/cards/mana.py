from random import shuffle
from enum import Enum

class ManaColor(Enum):
    RED     = 1
    BLACK   = 2
    BLUE    = 3
    GREEN   = 4 # Special, not yet existent in the game. But cards of green color exist.
    def __str__(self):
        return self.name    
    
class mana:
    def __init__ (self ,_color:ManaColor):
        if not isinstance(_color, ManaColor):
            raise ValueError(f"Invalid mana color: {_color}")
        self.color= _color
    def __str__(self):
        return self.color.name
        

def get_mana_pool():
    mana_pool = [mana(ManaColor.RED), mana(ManaColor.BLACK), mana(ManaColor.BLUE)]
    shuffle(mana_pool)
    return mana_pool
