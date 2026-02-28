from utils.database_utils   import DBUtil
from cards.deck             import Deck
from cards.card             import Card
from cards.power            import Power
from cards.card_type        import CardType
from random                 import randint
from neat import nn

def build_deck(net:nn.FeedForwardNetwork, max_power = Power.NORMAL) -> Deck:
    deck    = Deck()
    cards   = [card for card in DBUtil().get_all_cards() if card.power <= max_power and card.type == CardType.PLAYER]

    for i in range(12): # Deck can have up to 12 cards
        #init
        deck_not_valid  = True
        deck_info       = deck.get_neat_cards_ids()
        best_card       = cards[0]
        best_card_score = net.activate(deck_info + best_card.get_neat_ids())[0]

        #this belongs elsewhere -> to outer loop that validates and adds cards
        if len(deck.cards) >= 10:
            keep_going = net.activate(deck_info + card.get_neat_ids() )[1]
            if round( keep_going ):
                continue
            else:
                break
        for card in cards[1:]:
            score = net.activate( deck_info + card.get_neat_ids() )[0]
            if score > best_card_score:
                best_card_score = score
                best_card = card
        deck.add_card(best_card)
        #Validate
        while deck_not_valid:
            try:
                deck.validate(validate_min_cards=False)
                deck_not_valid = False
            except:
                deck.remove_card(best_card)
                best_card = cards[ randint( 0, len(cards) - 1)]
                deck.add_card(best_card) # add random card


    return deck