from collections import Counter
import sqlite3
from cards.database_utils import DBUtil
from card import Card
class Deck():
    
    def __init__(self):
        self.id              = 0 # hopefully this can be set by db
        self.name            = ""
        self.description     = ""
        self.cards           = []
        self.power           = 0 # cards are in three levels -> starter, normal, legendary
        self.neat_fitness    = 0
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
        return True, "Deck is valid."
    def evaluate_power(self):
        raise NotImplementedError("")
        # based on cards in deck, determine and assign power.
@staticmethod
def load_deck(deck_id) -> Deck:
    """
    Loads deck data from the database using the given deck_id.
    """
    with sqlite3.connect(DBUtil.DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute( "SELECT id, name, description, power, neat_fitness FROM decks WHERE id = ?", (deck_id,))
        row = cursor.fetchone()
    if not row:
        raise ValueError(f"Deck with id {deck_id} not found.")
    return row  # or map to a Deck object if you have one


@staticmethod
def store_deck(deck):
    """
    Stores deck data into the database.
    """
    with sqlite3.connect(DBUtil.DB_PATH) as conn:
        cursor = conn.cursor()
        if deck.id == 0:
            cursor.execute(
                "INSERT INTO decks (name, description, power, neat_fitness) VALUES (?, ?, ?, ?)",
                (deck.name, deck.description, deck.power, deck.neat_fitness)
            )
            deck.id = cursor.lastrowid
        else:
            cursor.execute(
                "UPDATE decks SET name = ?, description = ?, power = ?, neat_fitness = ? WHERE id = ?",
                (deck.name, deck.description, deck.power, deck.neat_fitness, deck.id)
            )
        conn.commit()
