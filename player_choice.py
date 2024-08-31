from random import randint,shuffle
from multiprocessing import Process, Queue
class player_choice:
    info   = None
    this_player = None
    def __init__(self,_player):
        self.this_player = _player
    def display_card(self,card):
        print_str  = ""   
        print_str += "[ "
        print_str += str(card.dmg)
        print_str += " "
        print_str += card.name
        print_str += " "
        print_str += str(card.hp)
        print_str += " ]"
        print(print_str,end=" ")    
    def get_choice_pos(self,game_board):  #1
        player = self.this_player
        if (player.type == "ai"):
            choice = self.this_player.net.activate(self.info.get_game_info())[0] % 6
            choice = int(choice)
            if self.info.game_board.positions[choice] != None:
                player.fitness -=1
                pos = game_board.get_empty_pos_arr()
                shuffle(pos)
                return pos[0]
            else:
                return choice
        elif (player.type == "rnd"):
            pos = game_board.get_empty_pos_arr()
            shuffle(pos)
            return pos[0]
        elif (player.type == "pl"):
            return (int(input("pick position to place card (1-6): "))-1)%6 #TODO bad placement  err ?
    def get_choice_card(self):   #2
        player = self.this_player
        if (player.type == "ai"):
            choice = player.net.activate(self.info.get_game_info())[1]
            if(choice >= len(player.hand.cards)):
                player.fitness-=1
            choice = choice % len(player.hand.cards)
            choice = int(choice)
            Player_choice_card = player.hand.cards.pop(choice)
            return Player_choice_card
        elif (player.type == "rnd"):
            Player_choice_card_num = randint(0,len(player.hand.cards)-1)
            Player_choice_card = player.hand.cards.pop(Player_choice_card_num)
            return Player_choice_card
        elif (player.type == "pl"):
            print("your hand:")
            for i,card in enumerate(player.hand.cards):
                print(str(i)+":",end="")
                self.display_card(card)
                max=i
            pos = int(input("choose card number: "))%max
            return player.hand.cards[pos]
    def get_choice_use_ability(self):   #3
        player = self.this_player
        if (player.type == "ai"):
            choice = player.net.activate(self.info.get_game_info())[2]
            if(choice > 1):
                player.fitness-=1
            choice = int( choice % 1)
            return choice
        elif (player.type == "rnd"):
            return 1
        elif (player.type == "pl"):
            return int(input("use card ability? (1/0): "))%1
    def get_choice_pass(self):  #4
        player = self.this_player
        if (player.type == "ai"):
            choice = player.net.activate(self.info.get_game_info())[3]
            if(choice > 1):
                player.fitness-=1
            choice = choice
            return int( choice % 1)
        elif (player.type == "rnd"):
            return False
        elif (player.type == "pl"):
            return int(input("pass? (1/0): "))%1
