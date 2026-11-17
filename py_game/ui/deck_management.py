from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

import pygame as pg

from cards.deck import Deck
from cards.power import Power
from core.config import MAX_DECK_SIZE, MIN_DECK_SIZE


def card_key(card) -> str:
    return str(getattr(card, "id", card))


def grouped_cards(cards) -> list[tuple[object, int]]:
    groups: OrderedDict[str, list] = OrderedDict()
    for card in cards:
        key = card_key(card)
        if key not in groups:
            groups[key] = [card, 0]
        groups[key][1] += 1
    return [(value[0], value[1]) for value in groups.values()]


def sorted_groups(cards) -> list[tuple[object, int]]:
    return sorted(
        grouped_cards(cards),
        key=lambda item: (str(getattr(item[0], "name", "")).casefold(), card_key(item[0])),
    )


def copy_limit(card) -> int:
    return 1 if getattr(card, "power", None) == Power.LEGENDARY else 4


def deck_validation(cards) -> tuple[bool, str]:
    if len(cards) < MIN_DECK_SIZE:
        missing = MIN_DECK_SIZE - len(cards)
        return False, f"Add {missing} card{'s' if missing != 1 else ''}"
    if len(cards) > MAX_DECK_SIZE:
        excess = len(cards) - MAX_DECK_SIZE
        return False, f"Remove {excess} card{'s' if excess != 1 else ''}"
    deck = Deck()
    deck.cards = list(cards)
    try:
        deck.validate()
    except ValueError as error:
        return False, str(error)
    return True, "Ready to play"


def ellipsize(font: pg.font.Font, text: str, width: int) -> str:
    text = str(text)
    if font.size(text)[0] <= width:
        return text
    suffix = "…"
    while text and font.size(text + suffix)[0] > width:
        text = text[:-1]
    return text + suffix


@dataclass
class CardDetailOverlay:
    """Top-layer card artwork modal with frame-safe click consumption."""

    card: object | None = None
    suppress_current_frame: bool = False
    awaiting_open_release: bool = False
    block_until_release: int | None = None

    @property
    def active(self) -> bool:
        return self.card is not None

    @property
    def captures_input(self) -> bool:
        return self.active or self.block_until_release is not None

    def open(self, card, *, opened_on_release: bool = False) -> None:
        self.card = card
        self.suppress_current_frame = True
        self.awaiting_open_release = not opened_on_release
        self.block_until_release = None

    def close(self, *, pressed_button: int | None = None) -> None:
        self.card = None
        self.suppress_current_frame = False
        self.awaiting_open_release = False
        self.block_until_release = pressed_button

    def consume_events(self, events) -> bool:
        if not self.captures_input:
            return False
        if self.block_until_release is not None:
            for event in events:
                if event.type == pg.MOUSEBUTTONUP and event.button == self.block_until_release:
                    self.block_until_release = None
            return True
        if self.suppress_current_frame:
            return True
        for event in events:
            if self.block_until_release is not None:
                if event.type == pg.MOUSEBUTTONUP and event.button == self.block_until_release:
                    self.block_until_release = None
                continue
            if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                self.close()
                return True
            if self.awaiting_open_release:
                if event.type == pg.MOUSEBUTTONUP and event.button == 3:
                    self.awaiting_open_release = False
                    continue
                if event.type == pg.MOUSEBUTTONDOWN and event.button in (1, 3):
                    self.close(pressed_button=event.button)
                    continue
                continue
            if event.type == pg.MOUSEBUTTONDOWN and event.button in (1, 3):
                self.close(pressed_button=event.button)
                continue
            if event.type == pg.MOUSEBUTTONUP and event.button == 3:
                self.close()
                return True
        return True

    def finish_frame(self) -> None:
        self.suppress_current_frame = False

    def draw(self, game) -> None:
        if not self.active:
            return
        shade = pg.Surface((game.DISPLAY_W, game.DISPLAY_H), pg.SRCALPHA)
        shade.fill((5, 9, 14, 220))
        game.display.blit(shade, (0, 0))
        margin = max(game.layout.margin, 24)
        max_width = game.DISPLAY_W - margin * 2
        max_height = game.DISPLAY_H - margin * 2
        width = min(max_width, round(max_height * 5 / 7))
        height = round(width * 7 / 5)
        if height > max_height:
            height = max_height
            width = round(height * 5 / 7)
        rect = pg.Rect(
            (game.DISPLAY_W - width) // 2,
            (game.DISPLAY_H - height) // 2,
            width,
            height,
        )
        image = game.assets.image(getattr(self.card, "image", None), rect.size)
        game.display.blit(image, rect)
        pg.draw.rect(game.display, game.palette.accent, rect, 3, border_radius=6)
