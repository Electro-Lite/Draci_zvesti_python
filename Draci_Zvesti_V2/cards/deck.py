from collections import Counter
import sqlite3
from utils.database_utils import DBUtil
from cards.card import Card
class Deck():
    
    def __init__(self):
        self.id              = 0 # hopefully this can be set by db
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
    def validate(self):
        """
        Validates the deck according to the rules:
        - Deck must have 10-12 cards.
        - Max 4 duplicates for normal cards.
        - Max 1 duplicate for legendary cards.
        """
        if not (10 <= len(self.cards) <= 12):
            raise ValueError("Deck must have between 10 and 12 cards.")

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
