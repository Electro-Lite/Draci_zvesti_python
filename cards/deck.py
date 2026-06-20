from collections import Counter
import sqlite3
from utils.database_utils import DBUtil
from cards.card import Card
class Deck():
    
    def __init__(self):
        self.id              = "" # hopefully this can be set by db
        self.name            = ""
        self.description     = ""
        self.cards           = []
        self.power           = 0 # cards are in three levels -> starter, normal, legendary
        self.neat_fitness    = 0
    def __str__(self):
        return self.name
    def add_card(self, card: Card):
        """
        Adds a card to the deck.
        """
        if not isinstance(card, Card):
            raise TypeError("Only Card instances can be added to the deck. Recieved:" + str(card))
        self.cards.append(card)
    def remove_card(self, card: Card):
        """
        Removes a card from the deck.
        """
        if card in self.cards:
            self.cards.remove(card)
        else:
            raise ValueError("Card not found in deck.")
    def validate(self, validate_min_cards = True):
        """
        Validates the deck according to the rules:
        - Deck must have 10-12 cards.
        - Max 4 duplicates for normal cards.
        - Max 1 duplicate for legendary cards.
        """
        if len(self.cards) > 12:
            raise ValueError("Deck must have less than 12 cards.")
        elif validate_min_cards and len(self.cards) < 10:
            raise ValueError("Deck must have at least 10 cards.")


        card_counts = {}
        for card in self.cards:
            card_counts[card] = card_counts.get(card, 0) + 1

        for card, count in card_counts.items():
            rarity = getattr(card, "rarity", "normal")
            if rarity == "legendary":
                if count > 1:
                    raise ValueError(f"Legendary card '{card}' appears more than once.")
            else:
                if count > 4:
                    raise ValueError(f"Card '{card}' appears more than 4 times.")
        return True
    def evaluate_power(self):
        raise NotImplementedError("")
        # based on cards in deck, determine and assign power.

    def get_neat_cards_ids(self):
        deck_info = []
        for card in self.cards:
            deck_info.extend(card.get_neat_ids())
        unused_deck_space = 12 - len(self.cards) # 12 is max cards in deck TODO move this value to config
        if unused_deck_space > 0:
            deck_info.extend([0] * 7 * unused_deck_space) # one card is represented by vector with 7 dimensions. TODO maybe better to calculate from card.get_neat_ids()
        return deck_info