from utils.database_utils   import DBUtil
from cards.deck             import Deck
from cards.card             import Card
from cards.power            import Power
from cards.card_type        import CardType
from neat import nn


SCORE_EPSILON = 1e-12


def _copy_count(deck: Deck, card: Card) -> int:
    return sum(1 for deck_card in deck.cards if getattr(deck_card, "id", None) == card.id)


def _copy_limit(card: Card) -> int:
    if getattr(card, "rarity", None) == "legendary" or card.power == Power.LEGENDARY:
        return 1
    return 4


def _can_add_card(deck: Deck, card: Card) -> bool:
    return len(deck.cards) < 12 and _copy_count(deck, card) < _copy_limit(card)

def build_deck(net:nn.FeedForwardNetwork, max_power = Power.NORMAL) -> Deck:
    deck    = Deck()
    cards   = sorted(
        [card for card in DBUtil().get_all_cards() if card.power <= max_power and card.type == CardType.PLAYER],
        key=lambda card: card.id
    )

    for i in range(12): # Deck can have up to 12 cards
        #init
        deck_info       = deck.get_neat_cards_ids()
        legal_cards     = [card for card in cards if _can_add_card(deck, card)]
        if not legal_cards:
            break

        best_card_score = None
        best_choices    = []
        for card in legal_cards:
            outputs = net.activate( deck_info + card.get_neat_ids() )
            score = outputs[0]
            if best_card_score is None or score > best_card_score + SCORE_EPSILON:
                best_card_score = score
                best_choices = [(card, outputs)]
            elif abs(score - best_card_score) <= SCORE_EPSILON:
                best_choices.append((card, outputs))

        # Equal scores should mean "no preference", not "pick the first DB row".
        best_choices.sort(key=lambda choice: (_copy_count(deck, choice[0]), choice[0].id))
        best_card, best_outputs = best_choices[0]

        if len(deck.cards) >= 10 and best_outputs[1] < 0.5:
            break

        deck.add_card(best_card)


    return deck
