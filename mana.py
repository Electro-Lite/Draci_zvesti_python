from random import shuffle
class mana:
    def __init__ (self ,_color):
        self.color= _color
def get_mana():
    mana_pool = [mana("red"), mana("blue"), mana("black")]
    return mana_pool
def get_mana_shuffled():
    mana_pool = get_mana()
    shuffle(mana_pool)
    return mana_pool

