import cards  as     cards_lib
import decks  as     decks_lib
from    Player      import player,PlayerType
from    GameInfo    import GameInfo
from    board       import board
from    neat        import nn
from    random      import randint,shuffle

conn = None

def random_player(player_1,player_2):
    if(randint(1,2)==1):
        player_on_Turn = player_1
    else:
        player_on_Turn = player_2
    return player_on_Turn

def get_winner(player_1,player_2):
    if(player_1.score>player_2.score):
        winner=player_1
    elif (player_2.score>player_1.score):
        winner=player_2
    else:
        winner = None
    if(winner):
        print("Player_" + str(winner.id) + " won with score: " +str(winner.score))
    else:
        print("The game resulted in a draw")
        
    return winner
    
def run(player_1:player = player(1) ,player_2:player = player(2), _conection = None):
    print("run")
    if(_conection):
        global conn
        conn = _conection
    
    print_all = True
    round = 0
    run=True
    game_board = board()
    game_board.print_all = print_all
    info = GameInfo()
    info.game_board = game_board
    
    player_1.choice.info = info
    player_2.choice.info = info
    
    player_1.deck=decks_lib.get_base_blue_deck()
    player_2.deck=decks_lib.get_base_blue_deck()
    
    shuffle(player_1.deck.cards)
    shuffle(player_2.deck.cards)
    
    player_1.draw_hand()
    player_2.draw_hand()
    
    player_1.hand.sort()
    player_2.hand.sort()
    
    player_on_Turn = random_player(player_1, player_2)
    if conn:
        conn.send(player_1.type)
        conn.close()
    # return
    while(run==True):#Rounds
        if round>100:
            player_1.score-=10
            player_2.score-=10
            return
        run_turns = True
        round+=1
        if (print_all):
            print("\nround: " + str(round))
        #cleanup + prep
        
        if round != 1:
            game_board.clear_round(player_1,player_2)
            player_1.draw_cards(3)
            player_2.draw_cards(3)
        player_1.hand.sort()
        player_2.hand.sort()
        
        #if players have no cards
        if((len(player_1.hand.cards)+len(player_2.hand.cards))<=0): 
            break
        # reveal mana
        if (print_all):
            print(f"mana: {game_board.mana_pool[0].color}")
        while(run and run_turns):#turns
            if(player_1.passed and player_2.passed):
                break
            #change player on turn
            if(player_on_Turn==player_1):
                player_on_Turn=player_2
            else:
                player_on_Turn=player_1
            
            if(len(player_on_Turn.hand.cards)<=0): #if player has no cards
                player_on_Turn.passed=True
                
            if(player_on_Turn.passed):
                continue
            info.player_on_turn = player_on_Turn
            
            #play
            Player_choice_pass = player_on_Turn.choice.get_choice_pass()
            if(Player_choice_pass):
                player_on_Turn.passed=True
                continue
            game_board.display()
            Player_choice_card        = player_on_Turn.choice.get_choice_card()
            Player_choice_position    = player_on_Turn.choice.get_choice_pos(game_board)
            Player_choice_use_ability = player_on_Turn.choice.get_choice_use_ability()
            Player_choice_card.owner  = player_on_Turn
            #place card
            game_board.place_card(Player_choice_card, Player_choice_position, Player_choice_use_ability )
            
            if game_board.get_card_count()>=6: #end player actions, goto finish round
                game_board.fight_dragon()
                run_turns=False
            
            if(player_1.score>=2):
                    get_winner(player_1,player_2)
                    return #end match
            if(player_2.score>=2):
                    get_winner(player_1,player_2)
                    return #end match
    
        #Check if any player still has cards
        cards_still_playebale =  0
        cards_still_playebale += len(player_1.deck.cards)
        cards_still_playebale += len(player_1.hand.cards)
        cards_still_playebale += len(player_2.deck.cards)
        cards_still_playebale += len(player_2.hand.cards)
        if(cards_still_playebale<=0):
            get_winner(player_1,player_2)
            return
    
run(player_1=player(1,PlayerType.RND),player_2=player(2,PlayerType.RND))
    
    