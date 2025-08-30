from random import shuffle
from cards.ability.abilities import HitAll1Dmg, EatFirst, NoAbility, InvertBoard
from cards.mana import ManaColor

class Dragon:
    #TODO this is temporary, the goal is to use dragon of instance Card later on.
    def __init__(self):
        self.color       = ""
        self.hp          = 0
        self.dmg         = 0
        self.ability     = ""
        self.slain_by    = None
        self.name        = ""

def _init_dragons():
    dragon_red              = Dragon()
    dragon_red.name         = "Red dragon"
    dragon_red.color        = ManaColor.RED
    dragon_red.hp           = 5
    dragon_red.dmg          = 5
    dragon_red.ability      = HitAll1Dmg()
    
    dragon_green            = Dragon()
    dragon_green.name         = "Green dragon"
    dragon_green.color      = ManaColor.GREEN
    dragon_green.hp         = 6
    dragon_green.dmg        = 6
    dragon_green.ability    = NoAbility()

    dragon_blue             = Dragon()
    dragon_blue.name         = "Blue dragon"
    dragon_blue.color       = ManaColor.BLUE
    dragon_blue.hp          = 5
    dragon_blue.dmg         = 5
    dragon_blue.ability     = InvertBoard()

    dragon_black            = Dragon()
    dragon_black.name         = "Black dragon"
    dragon_black.color      = ManaColor.BLACK
    dragon_black.hp         = 5
    dragon_black.dmg        = 5
    dragon_black.ability    = EatFirst()
    
    dragons=[]
    dragons.append(dragon_red)
    dragons.append(dragon_green)
    dragons.append(dragon_blue)
    dragons.append(dragon_black)
    return dragons



def get_dragons():
    dragons = _init_dragons()
    shuffle(dragons)
    return dragons
    