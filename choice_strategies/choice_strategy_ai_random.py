from choice_strategies.choice_strategy import PlayerChoiceStrategy
from random import randint
class ChoiceStrategyAIRandom(PlayerChoiceStrategy):

    def get_choice_pos(self):
        game_board  = self.info.game_board
        start_pos = randint(0, 5) # 6 positions
        for i in range(0, 6):
            pos = ( start_pos + i ) % 6 
            if game_board.positions[pos] == None:
                return pos
        raise IndexError("No empty space on board")

    def get_choice_card(self):
        cards_in_hand = len(self.this_player.hand.cards)
        return self.this_player.hand.cards.pop( randint(0,cards_in_hand -1) )

    def get_choice_use_ability(self):
        return True

    def get_choice_pass(self):
        return False
    
    def get_choice_ability_target(self): #TODO should not select self (Nepotrebny_novic)
        game_board  = self.info.game_board
        start_pos = randint(0, 5) # 6 positions
        for i in range(0, 6):
            pos = ( start_pos + i ) % 6 
            if game_board.positions[pos] != None:
                return pos
