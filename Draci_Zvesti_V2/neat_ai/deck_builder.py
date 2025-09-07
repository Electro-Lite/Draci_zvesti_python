from utils.database_utils   import DBUtil
from cards.deck             import Deck
from cards.card             import Card
from cards.power            import Power
from neat import nn

def build_deck(net:nn.FeedForwardNetwork, max_power = Power.NORMAL) -> Deck:
    deck    = Deck()
    cards   = [card for card in DBUtil().get_all_cards() if card.power <= max_power]
            
    deck_info = deck.get_neat_cards_ids()

    best_card       = cards.pop()
    best_card_score = net.activate(deck_info.extend(best_card.get_neat_ids))[0]


    for i in range(12): # Deck can have up to 12 cards
        #this belongs elsewhere -> to outer loop that validates and adds cards
        if len(deck.cards >= 10):
            keep_going = net.activate(deck_info.extend(card.get_neat_ids))[1]
            if round( keep_going ):
                continue
            else:
                break
        for card in cards:
            score = net.activate(deck_info.extend(card.get_neat_ids))[0]
            if score > best_card_score:
                best_card_score = score
                best_card = card

        deck.add_card(best_card)
    
    return deck