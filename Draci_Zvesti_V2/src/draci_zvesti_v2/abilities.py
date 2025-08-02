

def front_plus_1_atack(card,board,player_on_turn,args=None):
    card_pos = board.positions.index(card)
    for x in range(0,card_pos-1):
        if(board.positions[x] == None):
            break
        if(board.positions[x].owner == player_on_turn):
            board.positions[x].dmg+=1
            
def sideways_plus_1(card,board,player_on_turn,args=None):
    card_pos   = board.positions.index(card)
    card_left  = board.positions[card_pos-1] if card_pos != 0   else None
    card_right = board.positions[card_pos+1] if card_pos != 5   else None 
    if(card_left  and card_left.owner  == card.owner):
        card_left.dmg  +=1
        card_left.hp   +=1
    if(card_right and card_right.owner == card.owner):
        card_right.dmg +=1
        card_right.hp  +=1
        
def go_first(placed_card,board,player_on_turn,args=None):
    card_pos   = board.positions.index(placed_card)
    board.positions[card_pos]=None
    
    card_shift = []
    if(board.positions[0]):
        card_shift.append(board.positions[0])
    board.positions[0] = placed_card
    
    x=0
    while(len(card_shift)>0):
        x+=1
        if(board.positions[x]):
            card_shift.append(board.positions[x])
        board.positions[x] = card_shift.pop(0)
        
def go_before_1(placed_card,board,player_on_turn,args=None):
    card_pos   = board.positions.index(placed_card)
    if(board.positions[card_pos-1]):
        card_tmp = board.positions[card_pos-1]
        board.positions[card_pos-1] = placed_card
        board.positions[card_pos]   = card_tmp


#draci
def eat_first(board):
    board.positions[0]=None
def burn_all(board):
    for card in board.positions:
        if(card):
            if(card.hp<=1):
                board.remove_card(card)
    
    
    
            
abilities ={
    "lucisnik":front_plus_1_atack,
    "panos"   :sideways_plus_1,
    "paladin" :go_first,
    "strazny" :go_first
}
dragon_abilities ={
    "cerny"  :eat_first,
    "cerveny":burn_all
}