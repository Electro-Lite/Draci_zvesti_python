from copy import deepcopy
import abilities

class card:
    owner     = None
    id        = 0
    name      = ""
    color     = ""
    color_buf = []
    hp        = 0
    dmg       = 0
    ability   = ""
    ability_type   = "" #vstup,smrt,passive
    def __init__(self) -> None:
        self.color_buf = [0,0]
def get_all_cards():
    all_cards = []
    all_cards.extend(get_all_blue_cards())
    
    return all_cards

def get_base_blue_cards():

    all_cards = []
    # base blue
    card_new = card()
    card_new.id        = 1
    card_new.name      = "pesak"
    card_new.color     = "blue"
    card_new.color_buf = [1,1]
    card_new.hp        = 2
    card_new.dmg       = 1
    card_new.ability   = ""
    all_cards.append(card_new)
    
    card_new = card()
    card_new.id        = 2
    card_new.name      = "panos"
    card_new.color     = "blue"
    card_new.color_buf = [0, 0]
    card_new.hp        = 1
    card_new.dmg       = 1
    card_new.ability   = abilities.sideways_plus_1
    card_new.ability_type   = "passive"
    
    all_cards.append(card_new)

    card_new = card()
    card_new.id         = 3
    card_new.name       = "lucisnik"
    card_new.color      = "blue"
    card_new.color_buf  = [0, 0]
    card_new.hp         = 1
    card_new.dmg        = 1
    card_new.ability    = abilities.front_plus_1_atack
    card_new.ability_type   = "passive"
    
    all_cards.append(card_new)

    card_new = card()
    card_new.id         = 4
    card_new.name       = "paladin"
    card_new.color      = "blue"
    card_new.color_buf  = [1, 1]
    card_new.hp         = 2
    card_new.dmg        = 2
    card_new.ability    = abilities.go_first
    card_new.ability_type   = "active"
    all_cards.append(card_new)

    card_new = card()
    card_new.id         = 5
    card_new.name       = "strazny"
    card_new.color      = "blue"
    card_new.color_buf  = [1, 1]
    card_new.hp         = 1
    card_new.dmg        = 1
    card_new.ability    = abilities.go_before_1
    card_new.ability_type   = "active"
    all_cards.append(card_new)
    
    return all_cards

def get_all_blue_cards():
    all_cards=[]
    all_cards.extend(get_base_blue_cards())
    
    return all_cards

def get_card_copy_by_name(cards ,name:str):
    for card in cards:
        if(card.name == name):
            return deepcopy(card)
    return False
    
all_cards = get_all_cards()






