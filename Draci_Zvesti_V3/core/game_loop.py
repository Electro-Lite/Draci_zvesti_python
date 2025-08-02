from random import shuffle

from . import game_info as gi
from . import player as p
from config import Config
from core.board import board
from Draci_Zvesti_V3.utils.print_tool import *
from display_strategies import display_strategy
Player      = p.Player
GameInfo    = gi.GameInfo

def run(player_1:Player, player_2:Player, display_strategy:display_strategy = None):
    """run game for players of given type, random if not set"""
    ### Init Game ###
    tprint("initializing game loop",type=InfoType.INFO)
    
    round   = 0
    run     = True
    
    game_board      = board()
    info            = GameInfo()
    info.game_board = game_board
    
    player_1.choice.info = info
    player_2.choice.info = info
    
    # player_1.deck=decks_lib.get_base_blue_deck()    # Will be handled by db later
    # player_2.deck=decks_lib.get_base_blue_deck()
    
    shuffle(player_1.deck.cards)
    shuffle(player_2.deck.cards)
    
    player_1.draw_hand()
    player_2.draw_hand()
    
    player_1.hand.sort()
    player_2.hand.sort()
    ### Game loop ##
    while run:
        round +=1
        # get mana
        ### update game info ###
        
        ### select card or pass###
        ### place card ###
          # if player has no cards to play, he automatically passes
        ### choose ability target (if applickable)###
        ### evaluate ability ###
        ### check for round end condition##
          # is board full
          # have both players passed
        ### battle dragon ###
        ### handle result ###
        ### clean-up board ###
        
        if (round > Config.max_rounds):
             raise MaxRoundsExceededError(f"Exceeded max number of game rounds: {round}") 
    ### Clean-up ##
    return

def battle_dragon(board): # returns if of winner or -1 if dragon survived
    ### activate dragon ability ###
    ### recalculate board ###
    ### battle positions ###
    ### evaluate results ###
        # if slain, return player id of card owner #
        # else put dragon and manna to bottom and return -1 #
    pass


### test run block ###
player_1 = Player(1)
player_2 = Player(2)
run(player_1, player_2)