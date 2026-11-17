from collections import Counter

from cards.card_type import CardType
from cards.deck import Deck
from cards.deck_rules import card_copy_limit
from cards.power import Power
from core.config import MAX_DECK_SIZE, MIN_DECK_SIZE
from neat import nn
from utils.database_utils import DBUtil


def build_deck(
    net: nn.FeedForwardNetwork,
    max_power=Power.NORMAL,
    banned_card_ids=(),
) -> Deck:
    deck = Deck()
    banned = {str(card_id) for card_id in banned_card_ids}
    cards = [ # list of allowed cards
        card
        for card in DBUtil().get_all_cards()
        if card.power <= max_power
        and card.type == CardType.PLAYER
        and str(card.id) not in banned
    ]
    cards.sort(key=lambda card: str(card.id))

    for _ in range(MAX_DECK_SIZE):
        counts = Counter(str(card.id) for card in deck.cards)
        cards = [ card for card in cards if counts[str(card.id)] < card_copy_limit(card) ] # occurence limit
        if not cards:
            break

        deck_info = deck.get_neat_cards_ids()
        evaluations = [
            (card, net.activate(deck_info + card.get_neat_ids()))
            for card in cards
        ]
        best_card, outputs = evaluations[0]
        best_score = outputs[0]
        best_card_count = counts[str(best_card.id)]

        for card, card_outputs in evaluations[1:]:
            card_score = card_outputs[0]
            card_count = counts[str(card.id)]

            if card_score > best_score or (
                card_score == best_score and card_count < best_card_count
            ):
                best_card = card
                outputs = card_outputs
                best_score = card_score
                best_card_count = card_count

        if len(deck.cards) >= MIN_DECK_SIZE and outputs[1] < 0.5:
            break

        deck.add_card(best_card)

    return deck
