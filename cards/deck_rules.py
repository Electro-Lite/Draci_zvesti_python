from cards.power import Power


def card_copy_limit(card) -> int:
    return 1 if card.power == Power.LEGENDARY else 4
