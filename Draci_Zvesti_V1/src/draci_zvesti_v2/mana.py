from random import shuffle
from enum import Enum

class ManaColor(Enum):
    RED     = 1
    BLACK   = 2
    BLUE    = 3
    def __str__(self):
        return self.name    
    
class mana:
    def __init__ (self ,_color:ManaColor):
        if not isinstance(_color, ManaColor):
            raise ValueError(f"Invalid mana color: {_color}")
        self.color= _color
    def __str__(self):
        return self.color.name
        
def _get_mana():
    mana_pool = [mana(ManaColor.RED), mana(ManaColor.BLACK), mana(ManaColor.BLUE)]
    return mana_pool

def get_mana_shuffled():
    mana_pool = _get_mana()
    shuffle(mana_pool)
    return mana_pool
