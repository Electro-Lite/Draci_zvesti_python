from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Callable

from cards.card_type import CardType
from cards.deck import Deck
from cards.power import Power


MAX_DECK_ID_LENGTH = 128
MAX_DECK_NAME_LENGTH = 80
MIN_DECK_CARDS = 10
MAX_DECK_CARDS = 12


def serialize_deck_selection(deck: Deck) -> dict:
    """Serialize identity and composition, never client-controlled card stats."""
    if deck is None:
        raise ValueError("The selected deck does not exist")
    deck.validate()
    deck_id = str(getattr(deck, "id", "") or "").strip()
    deck_name = str(getattr(deck, "name", "") or "").strip()
    card_ids = [str(getattr(card, "id", "") or "") for card in deck.cards]
    _validate_text(deck_id, "Deck ID", MAX_DECK_ID_LENGTH)
    if len(deck_name) > MAX_DECK_NAME_LENGTH:
        raise ValueError(f"Deck name must be at most {MAX_DECK_NAME_LENGTH} characters")
    for card_id in card_ids:
        _validate_text(card_id, "Card ID", MAX_DECK_ID_LENGTH)
    return {
        "deck_id": deck_id,
        "deck_name": deck_name,
        "card_ids": card_ids,
    }


def reconstruct_remote_deck(
    descriptor: dict,
    load_card: Callable[[str], object | None],
) -> Deck:
    """Build a remote deck from host-authoritative card definitions."""
    if not isinstance(descriptor, dict):
        raise ValueError("Guest deck composition is missing or malformed")
    allowed = {"deck_id", "deck_name", "card_ids"}
    if set(descriptor) - allowed:
        raise ValueError("Guest deck contains unsupported fields")

    deck_id = descriptor.get("deck_id")
    deck_name = descriptor.get("deck_name", "")
    card_ids = descriptor.get("card_ids")
    if not isinstance(deck_id, str):
        raise ValueError("Guest deck ID must be text")
    if not isinstance(deck_name, str):
        raise ValueError("Guest deck name must be text")
    _validate_text(deck_id, "Guest deck ID", MAX_DECK_ID_LENGTH)
    if len(deck_name) > MAX_DECK_NAME_LENGTH:
        raise ValueError(f"Guest deck name must be at most {MAX_DECK_NAME_LENGTH} characters")
    if not isinstance(card_ids, list):
        raise ValueError("Guest deck card IDs must be a list")
    if not MIN_DECK_CARDS <= len(card_ids) <= MAX_DECK_CARDS:
        raise ValueError(
            f"Guest deck must contain {MIN_DECK_CARDS}-{MAX_DECK_CARDS} cards"
        )

    normalized_ids = []
    for card_id in card_ids:
        if not isinstance(card_id, str):
            raise ValueError("Guest deck card IDs must be text")
        _validate_text(card_id, "Guest card ID", MAX_DECK_ID_LENGTH)
        normalized_ids.append(card_id)

    cards_by_id = {}
    for card_id in dict.fromkeys(normalized_ids):
        try:
            card = load_card(card_id)
        except Exception as error:
            raise ValueError(f"Could not validate guest card {card_id}") from error
        if card is None:
            raise ValueError(f"Guest deck uses an unknown card: {card_id}")
        if getattr(card, "type", CardType.PLAYER) != CardType.PLAYER:
            raise ValueError(f"Guest deck contains a non-player card: {card_id}")
        cards_by_id[card_id] = card

    counts = Counter(normalized_ids)
    for card_id, count in counts.items():
        card = cards_by_id[card_id]
        limit = 1 if getattr(card, "power", None) == Power.LEGENDARY else 4
        if count > limit:
            raise ValueError(
                f"Guest deck contains {count} copies of {card_id}; maximum is {limit}"
            )

    deck = Deck()
    deck.id = deck_id
    deck.name = deck_name or "Guest deck"
    deck.cards = [deepcopy(cards_by_id[card_id]) for card_id in normalized_ids]
    deck.validate()
    return deck


def _validate_text(value: str, label: str, maximum: int) -> None:
    if not value or not value.strip():
        raise ValueError(f"{label} must not be empty")
    if len(value) > maximum:
        raise ValueError(f"{label} must be at most {maximum} characters")
