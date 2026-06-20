from cards.dragons          import get_dragons
from cards.card             import Card
from cards.mana             import get_mana_pool_shuffled, Mana
from core.enums.game_state  import GameState

# from os import  system
# clear = lambda: system('cls')

class Board:
    def __init__(self):
        self.positions  = [None,None,None,None,None,None,] # 6 mist na stole
        self.dragons    = get_dragons() # [] with dragon instances
        self.mana_pool  = get_mana_pool_shuffled()
        self.winner         = None  # for pygame, #TODO move to display strategy pygame
        self.game_running   = True  # for pygame, #TODO move to display strategy pygame
        self.player_on_turn = None
        self.game_state = GameState.PREP
        self.dragon     = None # for pygame
        self.round      = 0    # for pygame
    def cycle_mana(self):
        """Rotate the mana pool left by one"""
        if not self.mana_pool:
            return  

        first = self.mana_pool.pop(0)
        self.mana_pool.append(first)

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

    def remove_card(self,card:Card):
        card_pos = self.positions.index(card)
        card.owner.graveyard.append(card)
        self.positions[card_pos]=None
        self.recalculate(False)

