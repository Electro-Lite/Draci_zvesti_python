from random import shuffle
from abilities import burn_all,eat_first

class dragon:
    color=""
    hp=0
    dmg=0
    ability=""
    slain_by=None

def get_dragons():
    dragon_red = dragon()
    dragon_red.color   = "red"
    dragon_red.hp    = 5
    dragon_red.dmg     = 5
    dragon_red.ability = burn_all
    
    dragon_green = dragon()
    dragon_green.color = "green"
    dragon_green.hp = 6
    dragon_green.dmg = 6
    dragon_green.ability = None

    dragon_blue = dragon()
    dragon_blue.color = "blue"
    dragon_blue.hp = 5
    dragon_blue.dmg = 5
    dragon_blue.ability = None

    dragon_black = dragon()
    dragon_black.color = "black"
    dragon_black.hp = 5
    dragon_black.dmg = 5
    dragon_black.ability = eat_first
    
    dragons=[]
    dragons.append(dragon_red)
    dragons.append(dragon_green)
    dragons.append(dragon_blue)
    dragons.append(dragon_black)
    return dragons


def get_dragons_shuffled():
    dragons = get_dragons()
    shuffle(dragons)
    return dragons
    