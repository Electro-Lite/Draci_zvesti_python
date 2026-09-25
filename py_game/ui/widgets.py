from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from typing import Callable

import pygame as pg

from .layout import RectSpec


@dataclass
class Button:
    key: str
    label: str
    rect: RectSpec
    enabled: bool = True
    selected: bool = False
    hovered: bool = False
    destructive: bool = False
    detail: str = ""

    def hit_test(self, position: tuple[int, int]) -> bool:
        return self.enabled and self.rect.contains(position)

    def draw(self, surface: pg.Surface, font: pg.font.Font, palette) -> None:
        rect = pg.Rect(self.rect.x, self.rect.y, self.rect.width, self.rect.height)
        if not self.enabled:
            fill = palette.disabled
            text_color = palette.muted
        elif self.selected:
            fill = palette.selected
            text_color = palette.text
        elif self.hovered:
            fill = palette.hover
            text_color = palette.text
        else:
            fill = palette.panel_alt
            text_color = palette.text
        border = palette.danger if self.destructive else palette.border
        pg.draw.rect(surface, fill, rect, border_radius=max(4, rect.height // 8))
        pg.draw.rect(surface, border, rect, 2, border_radius=max(4, rect.height // 8))
        rendered = font.render(self.label, True, text_color)
        surface.blit(rendered, rendered.get_rect(center=rect.center))


@dataclass
class DragController:
    threshold: int = 8
    source_key: str | None = None
    start: tuple[int, int] | None = None
    position: tuple[int, int] | None = None
    dragging: bool = False
    valid_targets: set[str] = field(default_factory=set)

    def begin(
        self,
        source_key: str,
        position: tuple[int, int],
        valid_targets: set[str] | None = None,
    ) -> None:
        self.source_key = source_key
        self.start = position
        self.position = position
        self.dragging = False
        self.valid_targets = set(valid_targets or ())

    def move(self, position: tuple[int, int]) -> bool:
        if self.start is None:
            return False
        self.position = position
        if not self.dragging:
            self.dragging = hypot(
                position[0] - self.start[0],
                position[1] - self.start[1],
            ) >= self.threshold
        return self.dragging

    def release(self, target_key: str | None) -> tuple[str, str] | None:
        result = None
        if (
            self.dragging
            and self.source_key is not None
            and target_key is not None
            and target_key in self.valid_targets
        ):
            result = (self.source_key, target_key)
        self.cancel()
        return result

    def cancel(self) -> None:
        self.source_key = None
        self.start = None
        self.position = None
        self.dragging = False
        self.valid_targets.clear()


@dataclass
class TextInput:
    value: str = ""
    max_length: int = 64
    validator: Callable[[str], bool] | None = None
    focused: bool = False
    error: str = ""

    def handle_event(self, event: pg.event.Event) -> bool:
        if not self.focused or event.type != pg.KEYDOWN:
            return False
        if event.key == pg.K_BACKSPACE:
            self.value = self.value[:-1]
            self.error = ""
            return True
        if event.key in (pg.K_RETURN, pg.K_KP_ENTER, pg.K_ESCAPE, pg.K_TAB):
            return False
        text = event.unicode
        if text and text.isprintable() and len(self.value) < self.max_length:
            proposed = self.value + text
            if self.validator is None or self.validator(proposed):
                self.value = proposed
                self.error = ""
            return True
        return False
