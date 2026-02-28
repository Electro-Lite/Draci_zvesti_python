from random import shuffle
from choice_strategies.choice_strategy import PlayerChoiceStrategy

class PlayerChoiceStrategyNeat(PlayerChoiceStrategy):
    def __init__(self, _player):
        self.this_player    = _player
        self.info           = None

    def get_choice_pos(self) -> int:
            game_board  = self.info.game_board
            player      = self.this_player

            choice = player.net.activate(self.info.get_game_info())[0] % 6
            choice = int(choice)
            if game_board.positions[choice] != None: # if failed to pick empty pos, return first empty
                player.fitness -=1
                for i in range(0, 6):
                    if game_board.positions[i] == None:
                        return i
            else:
                return choice 
            raise Exception()
    
    def get_choice_card(self): # Card
        player = self.this_player
        choice = player.net.activate(self.info.get_game_info())[1]
        if(choice >= len(player.hand.cards)):
            player.fitness-=1
        choice = choice % len(player.hand.cards)
        choice = int(choice)
        Player_choice_card = player.hand.cards.pop(choice)
        return Player_choice_card

    def get_choice_use_ability(self) -> bool:
        player = self.this_player
        choice = player.net.activate(self.info.get_game_info())[2]
        if(choice > 1):
            player.fitness-=1
        choice = int( choice % 1)
        return choice

    def get_choice_pass(self) -> bool:
        player = self.this_player
        choice = player.net.activate(self.info.get_game_info())[3]
        if(choice > 1):
            player.fitness-=1
        choice = choice
        return int( choice % 1)
    
    def get_choice_ability_target(self) -> int:
        game_board  = self.info.game_board
        player      = self.this_player
        
        choice = player.net.activate(self.info.get_game_info())[4] % 6
        choice = int(choice)
        return choice 
