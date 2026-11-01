from cards.card import Card
from cards.power import Power
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
            raise ValueError("Deck may contain at most 12 cards.")
        if validate_min_cards and len(self.cards) < 10:
            raise ValueError("Deck must contain at least 10 cards.")

        card_counts = {}
        representatives = {}
        for card in self.cards:
            card_id = str(getattr(card, "id", card))
            card_counts[card_id] = card_counts.get(card_id, 0) + 1
            representatives.setdefault(card_id, card)

        for card_id, count in card_counts.items():
            card = representatives[card_id]
            name = getattr(card, "name", card_id)
            limit = 1 if getattr(card, "power", None) == Power.LEGENDARY else 4
            if count > limit:
                if limit == 1:
                    raise ValueError(f"Legendary card '{name}' may appear only once.")
                raise ValueError(f"Card '{name}' may appear at most 4 times.")
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
