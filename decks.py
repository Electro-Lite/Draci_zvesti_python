import cards as cards_lib

class deck:
    cards=None
    
    def __init__(self) -> None:
        self.cards = []
    def add_card(self, card:cards_lib.card ):
        if(len(self.cards) >= 12):
            return False
        if (not self.check_duplicit_card(card)):
            return False
        
        self.cards.append(card)
        return(True)
                
    def check_duplicit_card(self, card:cards_lib.card ):
        duplicit_count=0
        
        for x in self.cards:
            if((x!=None) and (x.name == card.name)):
                duplicit_count+=1
        if (duplicit_count>=3):
            return False
        else:
            return True

def get_base_blue_deck():
    deck_new = deck()
    cards = cards_lib.get_base_blue_cards()
    
    
    for x in range(2):
        card = cards_lib.get_card_copy_by_name(cards,"pesak")
        if(card):
            deck_new.add_card(card)
    for x in range(2):
        card = cards_lib.get_card_copy_by_name(cards,"panos")
        if(card):
            deck_new.add_card(card)
    for x in range(2):
        card = cards_lib.get_card_copy_by_name(cards,"lucisnik")
        if(card):
            deck_new.add_card(card)
    for x in range(2):
        card = cards_lib.get_card_copy_by_name(cards,"paladin")
        if(card):
            deck_new.add_card(card)
    for x in range(2):
        card = cards_lib.get_card_copy_by_name(cards,"strazny")
        if(card):
            deck_new.add_card(card)
    return deck_new