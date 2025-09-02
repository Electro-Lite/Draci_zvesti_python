from cards.dragons  import get_dragons
from cards.card     import Card
from cards.mana     import get_mana_pool_shuffled, Mana
# from os import  system
# clear = lambda: system('cls')

class Board:
    positions = []
    dragons   = []
    mana_pool = []
    def __init__(self):
        self.positions = [None,None,None,None,None,None,] # 6 mist na stole
        self.dragons   = get_dragons() # [] with dragon instances
        self.mana_pool = get_mana_pool_shuffled()

    def cycle_mana(self):
        """Rotate the mana pool by one"""
        mana_pool_new =[]
        mana_pool_new.append( self.mana_pool.pop(0))
        for mana in self.mana_pool:
            mana_pool_new.append( mana)
        self.mana_pool = mana_pool_new

    def recalculate(self,do_display=False):
        ### regenerate cards ###
        for x in range(0,6):
            card = self.positions[x]
            if(card==None):
                continue
            card.restore()
        #regenerate mana bonuses
            if(self.mana_pool[0].color == card.color):
                card.dmg += card.color_buf[0]
                card.hp  += card.color_buf[1]

        #regenerate passive abilities
        for x in range(0,6):
            card = self.positions[x]
            if(card==None):
                continue
            if(card.ability.is_passive):
                card.ability.apply_passive(card,self)

    def display(self):
        raise NotImplementedError("")
        string_print = ""
        for card in self.positions:
            if(card==None):
                string_print+="[]"
                continue
            string_print += "[ " + str(card.owner.id) +": "
            string_print +=  str(card.dmg)
            string_print += " " + str(card.name) + " "
            string_print +=  str(card.hp) +" ] "
        print(string_print)
    def get_empty_pos_arr(self):
        raise NotImplementedError("")
        ret=[]
        for x in range(0,6):
            if(self.positions[x]==None):
                ret.append(x)
        return ret
    def get_card_count(self):
        count =0
        for card in self.positions:
            if(isinstance(card, Card)):
                count+=1
        return count
    def clear_round(self,player_1,player_2):
        for x in range(0,6):
            card =self.positions[x]
            if card==None:
                continue
            if card.owner==player_1:
                player_1.graveyard.append(card)
            else:
                player_2.graveyard.append(card)
            self.positions[x]=None
    def place_card(self, card:Card, pos:int, use_ability:bool, target_pos:int):
        if self.positions[pos] != None:
            raise ValueError("This position is already occupied!")
        self.positions[pos] = card
        #apply mana
        if(self.mana_pool[0].color == card.color):
                card.dmg += card.color_buf[0]
                card.hp  += card.color_buf[1]
        #card ability
        if(card.ability.is_active and use_ability):
                card.ability.activate(card, self)
        #update
        self.recalculate()

    def fight_dragon(self):
        raise NotImplementedError("")
        if (self.print_all):
            print("fight dragon!")
        #reveal dragon
        dragon=self.dragons.pop()
        self.display_dragon(dragon)
        #use dragon ability
        if(dragon.ability != None):
            dragon.ability(self)
            if (self.print_all):
                print(dragon.ability.__name__)
            self.recalculate(False)
        else:
            self.display()

        #fight pos
        for x in range(0,6):

            if(dragon.color == "blue"):
                card = self.positions[5-x]#od konce
            else:
                card = self.positions[x]

            if(card==None):
               continue
            self.display_dragon(dragon)
            if (self.print_all):
                print("vs")
            self.display_card(card)
            self.display()
            dragon.hp -= card.dmg

            if(dragon.hp<=0): #dragon defeated

                if (self.print_all):
                    print("dragon slain by: ","")
                self.display_card(card)
                dragon.slain_by = card.owner
                card.owner.score+=1
                break

            self.remove_card(card)
            self.recalculate(False)

        removed_mana=self.mana_pool.pop(0)

        if(dragon.slain_by==None):
            raise NotImplementedError("")
            #return dragon to
            dragon.hp = 6 if dragon.color=="green" else 5
            self.dragons  .append(dragon)
            self.mana_pool.append(removed_mana)

    def remove_card(self,card:Card):
        card_pos = self.positions.index(card)
        card.owner.graveyard.append(card)
        self.positions[card_pos]=None
        self.recalculate(False)
    def display_dragon(self,dragon):
        raise NotImplementedError("")
        print_str  = ""
        print_str += "[ "
        print_str += str(dragon.dmg)
        print_str += " dragon"
        print_str += " "
        print_str += dragon.color
        print_str += " "
        print_str += str(dragon.hp)
        print_str += " ]"
        print(print_str)
    def display_card(self,card:Card):
        raise NotImplementedError("")
        print_str  = ""
        print_str += str( card.owner.id)
        print_str += ":"
        print_str += "[ "
        print_str += str(card.dmg)
        print_str += " "
        print_str += card.name
        print_str += " "
        print_str += str(card.hp)
        print_str += " ]"
        print(print_str)
