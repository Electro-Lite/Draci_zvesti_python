from random                     import shuffle
from cards.ability.abilities    import HitAll1Dmg, EatFirst, NoAbility, InvertBoard
from cards.mana                 import ManaColor
from utils.database_utils       import DBUtil
from cards.card_type            import CardType

class Dragon:
    #TODO this is temporary, the goal is to use dragon of instance Card later on.
    def __init__(self):
        raise DeprecationWarning()
        self.color       = ""
        self.hp          = 0
        self.dmg         = 0
        self.ability     = ""
        self.slain_by    = None
        self.name        = ""

def _init_dragons_old():
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

def _init_dragons():
    dragons=[]
    dragons.append(DBUtil().load_card("dragon_blue_1" )) # Blue
    dragons.append(DBUtil().load_card("dragon_red_1"  )) # Red
    dragons.append(DBUtil().load_card("dragon_green_1")) # Green
    dragons.append(DBUtil().load_card("dragon_black_1")) # Black
    for dragon in dragons:
        if dragon.type != CardType.DRAGON:
            raise TypeError()
    return dragons


def get_dragons():
    dragons = _init_dragons()
    shuffle(dragons)
    return dragons
    