from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import uuid4

import pygame as pg

from cards.deck import Deck
from cards.power import Power
from py_game.deck_advisor import DeckAdvisor, discover_advisors
from py_game.menu.base_menu import Menu
from py_game.ui.deck_management import (
    CardDetailOverlay,
    card_key,
    copy_limit,
    deck_validation,
    ellipsize,
    sorted_groups,
)
from py_game.ui.layout import RectSpec
from py_game.ui.widgets import Button, TextInput
from utils.database_utils import DBUtil

if TYPE_CHECKING:
    from py_game.game import Game


class ActivePane(Enum):
    AVAILABLE = 0
    ACTIONS = 1
    DECK = 2


class DeckBuilderMenu(Menu):
    PAGE_SIZE = 12

    def __init__(self, game: "Game", deck_id=None, *, source_deck=None):
        super().__init__(game)
        self.db = DBUtil()
        self.previous_menu = None
        loaded = source_deck or (self.db.load_deck(deck_id) if deck_id else None)
        self.load_error = bool(deck_id and loaded is None)
        self.current_deck_id = None if source_deck else deck_id
        self.unsaved_copy = source_deck is not None
        self.deck_name = (f"{loaded.name} copy" if source_deck else loaded.name) if loaded else ""
        self.deck_description = loaded.description if loaded else ""
        self.deck_power = getattr(loaded, "power", 0) if loaded else 0
        self.deck_fitness = getattr(loaded, "neat_fitness", 0) if loaded else 0
        self.deck_cards = list(loaded.cards) if loaded else []
        self.all_cards = sorted(self.db.get_all_player_cards(), key=lambda card: (card.name.casefold(), card_key(card)))
        self.search = TextInput(max_length=64)
        self.color_filter = None
        self.power_filter = None
        self.in_deck_only = False
        self.catalog_scroll = 0
        self.deck_scroll = 0
        self.narrow_tab = ActivePane.AVAILABLE
        self.active_pane = ActivePane.AVAILABLE
        self.indices = {pane: 0 for pane in ActivePane}
        self.available_page = 0
        self.available_page_size = self.PAGE_SIZE
        self.selected_card_id = card_key(self.all_cards[0]) if self.all_cards else None
        self.focused_card = None
        self.detail = CardDetailOverlay()
        self.dirty = bool(source_deck)
        self.message = "Could not load this deck" if self.load_error else ""
        self.message_error = self.load_error
        self.advisor_options = discover_advisors()
        self.advisor_index = 0
        self.advisor = None
        self.advice = {}
        self.advisor_open = False
        self.controls = {}
        self.catalog_targets = []
        self.deck_targets = []
        self.search_rect = RectSpec(0, 0, 0, 0)
        self.catalog_rect = RectSpec(0, 0, 0, 0)
        self.sidebar_rect = RectSpec(0, 0, 0, 0)
        self._original = self._snapshot()

    def _snapshot(self):
        return self.deck_name, self.deck_description, tuple(card_key(card) for card in self.deck_cards)

    def _sync_dirty(self):
        self.dirty = self.unsaved_copy or self._snapshot() != self._original

    def _copy_count(self, card) -> int:
        key = card_key(card)
        return sum(card_key(deck_card) == key for deck_card in self.deck_cards)

    @staticmethod
    def _copy_limit(card) -> int:
        return copy_limit(card)

    def _colors(self):
        values = {getattr(card, "color", None) for card in self.all_cards}
        return sorted((value for value in values if value is not None), key=lambda value: str(getattr(value, "name", value)))

    def _powers(self):
        values = {getattr(card, "power", None) for card in self.all_cards}
        return sorted((value for value in values if value is not None), key=lambda value: getattr(value, "value", 0))

    def _available_cards(self):
        cards = list(getattr(self, "all_cards", ()))
        query = getattr(getattr(self, "search", None), "value", "").strip().casefold()
        color_filter = getattr(self, "color_filter", None)
        power_filter = getattr(self, "power_filter", None)
        in_deck_only = getattr(self, "in_deck_only", False)
        result = []
        for card in cards:
            if query and query not in str(getattr(card, "name", "")).casefold():
                continue
            if color_filter is not None and not getattr(card, "has_color", lambda value: getattr(card, "color", None) == value)(color_filter):
                continue
            if power_filter is not None and getattr(card, "power", None) != power_filter:
                continue
            if in_deck_only and self._copy_count(card) == 0:
                continue
            result.append(card)
        return result

    def _items(self, pane):
        if pane == ActivePane.AVAILABLE:
            return self._available_cards()
        if pane == ActivePane.DECK:
            return [card for card, _count in sorted_groups(self.deck_cards)]
        return []

    def _available_page_count(self, page_size=None):
        page_size = max(1, page_size or getattr(self, "available_page_size", self.PAGE_SIZE))
        return max(1, (len(self._available_cards()) + page_size - 1) // page_size)

    def _clamp_available_page(self, page_size=None):
        page_size = max(1, page_size or self.available_page_size)
        self.available_page = min(max(0, self.available_page), self._available_page_count(page_size) - 1)
        selected = self.indices[ActivePane.AVAILABLE]
        first = self.available_page * page_size
        if selected < first or selected >= first + page_size:
            self.available_page = selected // page_size

    def _change_available_page(self, direction, page_size=None):
        cards = self._available_cards()
        if not cards:
            self.available_page = 0
            self.indices[ActivePane.AVAILABLE] = 0
            return
        page_size = max(1, page_size or self.available_page_size)
        current = min(max(0, self.available_page), self._available_page_count(page_size) - 1)
        target = min(max(0, current + direction), self._available_page_count(page_size) - 1)
        row = min(max(0, self.indices[ActivePane.AVAILABLE] - current * page_size), page_size - 1)
        self.available_page = target
        self.indices[ActivePane.AVAILABLE] = min(target * page_size + row, len(cards) - 1)

    def _selected_card(self):
        if self.selected_card_id:
            return next((card for card in self.all_cards if card_key(card) == self.selected_card_id), None)
        return None

    def _set_message(self, message, error=False):
        self.message, self.message_error = str(message), bool(error)

    def _blocked_reason(self, card):
        if card is None:
            return self.tr("editor_select_card")
        if len(self.deck_cards) >= 12:
            return self.tr("editor_full")
        limit = copy_limit(card)
        if self._copy_count(card) >= limit:
            return self.tr("editor_legendary_limit") if limit == 1 else self.tr("editor_copy_limit")
        return ""

    def _validation_label(self, valid, reason):
        if valid:
            return self.tr("editor_ready")
        if reason.startswith("Add "):
            return self.tr("editor_add_cards", count=max(0, 10 - len(self.deck_cards)))
        if reason.startswith("Remove "):
            return self.tr("editor_remove_cards", count=max(0, len(self.deck_cards) - 12))
        return reason

    def _change_count(self, card, delta):
        if delta > 0:
            reason = self._blocked_reason(card)
            if reason:
                self._set_message(reason, True)
                return False
            self.deck_cards.append(card)
        else:
            key = card_key(card)
            index = next((index for index in range(len(self.deck_cards) - 1, -1, -1) if card_key(self.deck_cards[index]) == key), None)
            if index is None:
                return False
            self.deck_cards.pop(index)
        self.selected_card_id = card_key(card)
        self._sync_dirty()
        self._set_message(deck_validation(self.deck_cards)[1])
        if self.advisor is not None:
            self._refresh_advice()
        return True

    def _add_selected(self):
        cards = self._available_cards()
        if cards:
            index = min(self.indices[ActivePane.AVAILABLE], len(cards) - 1)
            self._change_count(cards[index], 1)

    def _remove_selected(self):
        card = self._selected_card()
        if card is not None:
            self._change_count(card, -1)

    def _deck_from_state(self, *, fresh_id=None):
        deck = Deck()
        deck.id = fresh_id if fresh_id is not None else (self.current_deck_id or "")
        deck.name = self.deck_name
        deck.description = self.deck_description
        deck.power = self.deck_power
        deck.neat_fitness = self.deck_fitness
        deck.cards = list(self.deck_cards)
        return deck

    def _save(self):
        valid, reason = deck_validation(self.deck_cards)
        if not valid:
            self._set_message(reason, True)
            return False
        if not self.deck_name.strip():
            name = self.prompt_text(self.tr("editor_deck_name"), "", max_length=64)
            if name is None:
                return False
            self.deck_name = name.strip()
        else:
            self.deck_name = self.deck_name.strip()
        if not self.deck_name:
            self._set_message("Deck name cannot be blank", True)
            return False
        fresh_id = self.current_deck_id or f"user_{uuid4().hex}"
        deck = self._deck_from_state(fresh_id=fresh_id)
        try:
            self.db.save_deck(deck, is_ai=False)
        except Exception as error:
            self._set_message(f"Save failed: {error}", True)
            return False
        self.current_deck_id = deck.id
        self.unsaved_copy = False
        self._original = self._snapshot()
        self.dirty = False
        self._set_message(self.tr("editor_saved"))
        return True

    def _rename(self):
        name = self.prompt_text(self.tr("editor_deck_name"), self.deck_name, max_length=64)
        if name is not None and name.strip():
            self.deck_name = name.strip()
            self._sync_dirty()

    def _refresh_advice(self):
        self.advice = {}
        option = self.advisor_options[self.advisor_index]
        if option.path is None:
            self.advisor = None
            return
        try:
            self.advisor = DeckAdvisor(option.path)
            self.advice = self.advisor.score_cards(self.deck_cards, self._available_cards())
            self._set_message(f"Advisor: {option.path.stem}")
        except Exception as error:
            self.advisor = None
            self.advisor_index = 0
            self._set_message(f"Advisor unavailable: {error}", True)

    def _cycle_advisor(self):
        self.advisor_index = (self.advisor_index + 1) % len(self.advisor_options)
        self._refresh_advice()

    def _unsaved_choice(self):
        selected = 2
        while self.game.running:
            self.begin_frame()
            for event in self.game.events:
                if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                    return "cancel"
                if event.type == pg.KEYDOWN and event.key in (pg.K_LEFT, pg.K_RIGHT):
                    selected = (selected + (-1 if event.key == pg.K_LEFT else 1)) % 3
                if event.type == pg.KEYDOWN and event.key in (pg.K_RETURN, pg.K_KP_ENTER):
                    return ("discard", "save", "cancel")[selected]
                if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                    for index, button in enumerate(self._unsaved_buttons(selected)):
                        if button.hit_test(event.pos):
                            return ("discard", "save", "cancel")[index]
            self.draw_background()
            panel = self.game.layout.centered_panel(0.72, 0.42)
            rect = pg.Rect(panel.x, panel.y, panel.width, panel.height)
            pg.draw.rect(self.game.display, self.game.palette.panel, rect, border_radius=12)
            pg.draw.rect(self.game.display, self.game.palette.border, rect, 2, border_radius=12)
            self.game.draw_text(self.tr("editor_unsaved"), self.game.layout.font_large, panel.center[0], panel.y + self.game.layout.margin * 2)
            self.draw_buttons(self._unsaved_buttons(selected))
            self.blit_screen()
        return "cancel"

    def _unsaved_buttons(self, selected=2):
        panel = self.game.layout.centered_panel(0.72, 0.42)
        m = self.game.layout
        width = (panel.width - m.margin * 2 - m.gap * 2) // 3
        labels = (("discard", self.tr("editor_discard")), ("save", self.tr("editor_save")), ("cancel", self.tr("cancel")))
        return [Button(key, label, RectSpec(panel.x + m.margin + index * (width + m.gap), panel.bottom - m.margin - m.target_height, width, m.target_height), selected=index == selected, destructive=key == "discard") for index, (key, label) in enumerate(labels)]

    def _return(self):
        if self.dirty:
            choice = self._unsaved_choice()
            if choice == "cancel":
                return
            if choice == "save" and not self._save():
                return
        self.return_to_previous()

    def _layout(self):
        m = self.game.layout
        header = RectSpec(m.margin, m.margin, self.game.DISPLAY_W - m.margin * 2, m.target_height)
        body = RectSpec(m.margin, header.bottom + m.gap, header.width, self.game.DISPLAY_H - header.bottom - m.margin - m.gap)
        narrow = self.game.DISPLAY_W < 900
        if narrow:
            return header, body, body, narrow
        catalog, sidebar = m.columns(body, (2.0, 1.0))
        return header, catalog, sidebar, narrow

    def _build_controls(self):
        m = self.game.layout
        header, catalog, sidebar, narrow = self._layout()
        back = RectSpec(header.x, header.y, max(80, header.width // 9), header.height)
        save = RectSpec(header.right - max(110, header.width // 8), header.y, max(110, header.width // 8), header.height)
        advisor = RectSpec(save.x - m.gap - max(90, header.width // 10), header.y, max(90, header.width // 10), header.height)
        name = RectSpec(back.right + m.gap, header.y, max(80, advisor.x - back.right - m.gap * 2), header.height)
        valid, _reason = deck_validation(self.deck_cards)
        name_label = ellipsize(pg.font.Font(self.game.font_name, m.font_normal), self.deck_name or self.tr("editor_name_deck"), name.width - 12)
        self.controls = {
            "back": Button("back", "< " + self.tr("back"), back),
            "name": Button("name", name_label, name, selected=self.dirty),
            "retry" if self.load_error else "advisor": Button("retry" if self.load_error else "advisor", self.tr("editor_retry") if self.load_error else self.tr("editor_advisor"), advisor, selected=self.advisor_open and not self.load_error),
            "save": Button("save", self.tr("editor_save_deck"), save, enabled=valid and self.dirty and not self.load_error),
        }
        if narrow:
            tab_w = (catalog.width - m.gap) // 2
            self.controls["collection_tab"] = Button("collection_tab", self.tr("editor_collection"), RectSpec(catalog.x, catalog.y, tab_w, m.target_height), selected=self.narrow_tab == ActivePane.AVAILABLE)
            self.controls["deck_tab"] = Button("deck_tab", self.tr("editor_deck", count=len(self.deck_cards)), RectSpec(catalog.x + tab_w + m.gap, catalog.y, tab_w, m.target_height), selected=self.narrow_tab == ActivePane.DECK)
        for button in self.controls.values():
            button.hovered = button.rect.contains(self.game.mouse_position)

    def _catalog_layout(self, area, narrow):
        m = self.game.layout
        top = area.y + (m.target_height + m.gap if narrow else 0)
        self.search_rect = RectSpec(area.x, top, area.width, m.target_height)
        filter_y = self.search_rect.bottom + m.gap
        has_filters = bool(self.search.value or self.color_filter is not None or self.power_filter is not None or self.in_deck_only)
        filter_count = 4 if has_filters else 3
        filter_w = max(64, (area.width - m.gap * (filter_count - 1)) // filter_count)
        filters = {
            "color": RectSpec(area.x, filter_y, filter_w, m.target_height),
            "power": RectSpec(area.x + filter_w + m.gap, filter_y, filter_w, m.target_height),
            "in_deck": RectSpec(area.x + (filter_w + m.gap) * 2, filter_y, filter_w, m.target_height),
        }
        if has_filters:
            filters["clear"] = RectSpec(area.x + (filter_w + m.gap) * 3, filter_y, filter_w, m.target_height)
        cards = RectSpec(area.x, filter_y + m.target_height + m.gap, area.width, area.bottom - filter_y - m.target_height - m.gap)
        return filters, cards

    def _handle_events(self):
        if self.detail.captures_input:
            self.detail.consume_events(self.game.events)
            return
        for event in self.game.events:
            if event.type == pg.KEYDOWN and self.search.focused:
                before = self.search.value
                if event.key in (pg.K_RETURN, pg.K_KP_ENTER, pg.K_ESCAPE):
                    self.search.focused = False
                else:
                    self.search.handle_event(event)
                if before != self.search.value:
                    self.catalog_scroll = 0
                continue
            if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                if self.advisor_open:
                    self.advisor_open = False
                else:
                    self._return()
                return
            if event.type == pg.KEYDOWN and event.key == pg.K_TAB:
                cards = self._items(self.narrow_tab if self.game.DISPLAY_W < 900 else ActivePane.AVAILABLE)
                if cards:
                    try:
                        index = [card_key(card) for card in cards].index(card_key(self.focused_card))
                    except (ValueError, TypeError):
                        index = -1
                    self.focused_card = cards[(index + 1) % len(cards)]
                    self.selected_card_id = card_key(self.focused_card)
                return
            if event.type == pg.KEYDOWN and event.key in (pg.K_RETURN, pg.K_KP_ENTER) and self.focused_card is not None:
                self.detail.open(self.focused_card)
                return
            if event.type == pg.MOUSEWHEEL:
                if self.sidebar_rect.contains(self.game.mouse_position):
                    self.deck_scroll = max(0, self.deck_scroll - event.y)
                elif self.catalog_rect.contains(self.game.mouse_position):
                    self.catalog_scroll = max(0, self.catalog_scroll - event.y)
            if (
                event.type == pg.MOUSEBUTTONDOWN and event.button in (1, 3)
            ) or (event.type == pg.MOUSEBUTTONUP and event.button == 3):
                self._handle_pointer(event)
                return

    def _handle_pointer(self, event):
        point = event.pos
        if event.button == 1 and self.search_rect.contains(point):
            self.search.focused = True
            return
        self.search.focused = False
        if event.button == 1:
            for key, button in self.controls.items():
                if not button.hit_test(point):
                    continue
                if key == "back": self._return()
                elif key == "name": self._rename()
                elif key == "advisor": self.advisor_open = not self.advisor_open
                elif key == "retry": self._retry_load()
                elif key == "save": self._save()
                elif key == "collection_tab": self.narrow_tab = ActivePane.AVAILABLE
                elif key == "deck_tab": self.narrow_tab = ActivePane.DECK
                return
        for key, card, rect, enabled in self.catalog_targets + self.deck_targets:
            if not rect.contains(point):
                continue
            if key == "image":
                self.selected_card_id = card_key(card)
                self.focused_card = card
                if event.button == 3:
                    self.detail.open(card, opened_on_release=event.type == pg.MOUSEBUTTONUP)
                return
            if event.button != 1:
                return
            if not enabled:
                self._set_message(self._blocked_reason(card), True)
            elif key == "plus": self._change_count(card, 1)
            elif key == "minus": self._change_count(card, -1)
            elif key == "inspect": self.detail.open(card)
            elif key == "clear": self._clear_filters()
            elif key == "color": self._cycle_color()
            elif key == "power": self._cycle_power()
            elif key == "in_deck":
                self.in_deck_only = not self.in_deck_only
                self.catalog_scroll = 0
            elif key == "advisor_cycle": self._cycle_advisor()
            return

    def _cycle_color(self):
        values = [None] + self._colors()
        self.color_filter = values[(values.index(self.color_filter) + 1) % len(values)]
        self.catalog_scroll = 0

    def _cycle_power(self):
        values = [None] + self._powers()
        self.power_filter = values[(values.index(self.power_filter) + 1) % len(values)]
        self.catalog_scroll = 0

    def _clear_filters(self):
        self.search.value = ""
        self.color_filter = self.power_filter = None
        self.in_deck_only = False
        self.catalog_scroll = 0

    def _retry_load(self):
        try:
            loaded = self.db.load_deck(self.current_deck_id)
        except Exception as error:
            self._set_message(f"Load failed: {error}", True)
            return
        if loaded is None:
            self._set_message("Could not load this deck", True)
            return
        self.deck_name = loaded.name
        self.deck_description = loaded.description
        self.deck_power = getattr(loaded, "power", 0)
        self.deck_fitness = getattr(loaded, "neat_fitness", 0)
        self.deck_cards = list(loaded.cards)
        self.load_error = False
        self._original = self._snapshot()
        self.dirty = False
        self._set_message("Deck loaded")

    def _draw_search(self):
        rect = pg.Rect(self.search_rect.x, self.search_rect.y, self.search_rect.width, self.search_rect.height)
        pg.draw.rect(self.game.display, self.game.palette.panel_alt, rect, border_radius=8)
        pg.draw.rect(self.game.display, self.game.palette.accent if self.search.focused else self.game.palette.border, rect, 2, border_radius=8)
        self.game.draw_text_left(self.search.value or self.tr("editor_search_cards"), self.game.layout.font_small, rect.x + self.game.layout.gap, rect.centery, self.game.palette.text if self.search.value else self.game.palette.muted, rect.width - self.game.layout.gap * 2)

    def _draw_catalog(self, area, narrow):
        m = self.game.layout
        filters, cards_area = self._catalog_layout(area, narrow)
        self.catalog_rect = cards_area
        self._draw_search()
        font = pg.font.Font(self.game.font_name, m.font_small)
        color_name = self.tr("editor_all_colors") if self.color_filter is None else getattr(self.color_filter, "name", str(self.color_filter)).title()
        power_name = self.tr("editor_all_powers") if self.power_filter is None else getattr(self.power_filter, "name", str(self.power_filter)).title()
        self.catalog_targets = []
        for key, label, rect, selected in (("color", color_name, filters["color"], self.color_filter is not None), ("power", power_name, filters["power"], self.power_filter is not None), ("in_deck", self.tr("editor_in_deck"), filters["in_deck"], self.in_deck_only)):
            Button(key, label, rect, selected=selected, hovered=rect.contains(self.game.mouse_position)).draw(self.game.display, font, self.game.palette)
            self.catalog_targets.append((key, None, rect, True))
        if "clear" in filters:
            clear = filters["clear"]
            Button("clear", self.tr("editor_clear"), clear, hovered=clear.contains(self.game.mouse_position)).draw(self.game.display, font, self.game.palette)
            self.catalog_targets.append(("clear", None, clear, True))
        cards = self._available_cards()
        if not cards:
            self.game.draw_text(self.tr("editor_no_cards"), m.font_normal, cards_area.center[0], cards_area.center[1] - m.target_height, self.game.palette.muted)
            return
        columns = max(1, min(5, cards_area.width // 150))
        gap = m.gap
        cell_w = (cards_area.width - gap * (columns - 1)) // columns
        art_w = min(cell_w, 150)
        art_h = round(art_w * 7 / 5)
        control_h = max(40, m.target_height - 6)
        cell_h = art_h + control_h + gap
        visible_rows = max(1, cards_area.height // cell_h + 1)
        max_scroll = max(0, (len(cards) + columns - 1) // columns - visible_rows + 1)
        self.catalog_scroll = min(self.catalog_scroll, max_scroll)
        start = self.catalog_scroll * columns
        for visible_index, card in enumerate(cards[start:start + columns * visible_rows]):
            row, col = divmod(visible_index, columns)
            x = cards_area.x + col * (cell_w + gap) + (cell_w - art_w) // 2
            y = cards_area.y + row * cell_h
            if y + art_h > cards_area.bottom:
                continue
            image_rect = RectSpec(x, y, art_w, art_h)
            self.game.display.blit(self.game.assets.image(getattr(card, "image", None), (art_w, art_h)), (x, y))
            if card_key(card) == self.selected_card_id:
                pg.draw.rect(self.game.display, self.game.palette.accent, pg.Rect(x, y, art_w, art_h), 3, border_radius=5)
            self.catalog_targets.append(("image", card, image_rect, True))
            count = self._copy_count(card)
            control = RectSpec(x, y + art_h + 4, art_w, control_h)
            minus_w = control.width // 3
            minus = RectSpec(control.x, control.y, minus_w, control.height)
            plus = RectSpec(control.right - minus_w, control.y, minus_w, control.height)
            count_rect = RectSpec(minus.right, control.y, control.width - minus_w * 2, control.height)
            Button("minus", "−", minus, enabled=count > 0).draw(self.game.display, font, self.game.palette)
            Button("plus", "+" if count else self.tr("editor_add"), plus if count else RectSpec(count_rect.x, control.y, count_rect.width + plus.width, control.height), enabled=not self._blocked_reason(card)).draw(self.game.display, font, self.game.palette)
            self.catalog_targets.append(("minus", card, minus, count > 0))
            plus_target = plus if count else RectSpec(count_rect.x, control.y, count_rect.width + plus.width, control.height)
            self.catalog_targets.append(("plus", card, plus_target, not bool(self._blocked_reason(card))))
            if count:
                self.game.draw_text(str(count), m.font_small, count_rect.center[0], count_rect.center[1])

    def _draw_sidebar(self, area, narrow):
        m = self.game.layout
        top = area.y + (m.target_height + m.gap if narrow else 0)
        panel = RectSpec(area.x, top, area.width, area.bottom - top)
        self.sidebar_rect = panel
        target = pg.Rect(panel.x, panel.y, panel.width, panel.height)
        pg.draw.rect(self.game.display, self.game.palette.panel, target, border_radius=10)
        pg.draw.rect(self.game.display, self.game.palette.border, target, 2, border_radius=10)
        valid, reason = deck_validation(self.deck_cards)
        self.game.draw_text_left(self.tr("editor_your_deck"), m.font_normal, panel.x + m.gap, panel.y + m.target_height // 2, max_width=panel.width - 120)
        self.game.draw_text(f"{len(self.deck_cards)} / 12", m.font_normal, panel.right - 55, panel.y + m.target_height // 2, self.game.palette.accent)
        self.game.draw_text_left(self._validation_label(valid, reason), m.font_small, panel.x + m.gap, panel.y + m.target_height, self.game.palette.success if valid else self.game.palette.muted, panel.width - m.gap * 2)
        row_top = panel.y + m.target_height + m.font_small + m.gap
        inspect_h = m.target_height
        row_bottom = panel.bottom - inspect_h - m.gap * 2
        row_h = max(62, m.target_height + m.gap)
        groups = sorted_groups(self.deck_cards)
        visible = max(1, (row_bottom - row_top) // row_h)
        self.deck_scroll = min(self.deck_scroll, max(0, len(groups) - visible))
        self.deck_targets = []
        font = pg.font.Font(self.game.font_name, m.font_small)
        for row, (card, count) in enumerate(groups[self.deck_scroll:self.deck_scroll + visible]):
            y = row_top + row * row_h
            image_h = row_h - 8
            image_w = round(image_h * 5 / 7)
            image = RectSpec(panel.x + m.gap, y, image_w, image_h)
            self.game.display.blit(self.game.assets.image(getattr(card, "image", None), (image_w, image_h)), (image.x, image.y))
            self.deck_targets.append(("image", card, image, True))
            controls_w = min(120, panel.width // 3)
            minus = RectSpec(panel.right - controls_w - m.gap, y + (image_h - 40) // 2, 40, 40)
            plus = RectSpec(panel.right - 40 - m.gap, minus.y, 40, 40)
            self.game.draw_text_left(ellipsize(font, card.name, max(30, minus.x - image.right - m.gap * 2)), m.font_small, image.right + m.gap, y + image_h // 2, max_width=max(30, minus.x - image.right - m.gap * 2))
            Button("minus", "−", minus).draw(self.game.display, font, self.game.palette)
            Button("plus", "+", plus, enabled=not self._blocked_reason(card)).draw(self.game.display, font, self.game.palette)
            self.game.draw_text(str(count), m.font_small, (minus.right + plus.x) // 2, plus.y + plus.height // 2)
            self.deck_targets.extend((("minus", card, minus, True), ("plus", card, plus, not bool(self._blocked_reason(card)))))
        selected = self._selected_card()
        inspect = RectSpec(panel.x + m.gap, panel.bottom - inspect_h - m.gap, panel.width - m.gap * 2, inspect_h)
        Button("inspect", self.tr("editor_inspect"), inspect, enabled=selected is not None).draw(self.game.display, font, self.game.palette)
        self.deck_targets.append(("inspect", selected, inspect, selected is not None))

    def _draw_advisor(self):
        if not self.advisor_open:
            return
        m = self.game.layout
        panel = self.game.layout.centered_panel(0.62, 0.68)
        target = pg.Rect(panel.x, panel.y, panel.width, panel.height)
        pg.draw.rect(self.game.display, self.game.palette.panel, target, border_radius=12)
        pg.draw.rect(self.game.display, self.game.palette.accent, target, 2, border_radius=12)
        self.game.draw_text(self.tr("editor_deck_advisor"), m.font_large, panel.center[0], panel.y + m.margin)
        label = self.tr("editor_off") if self.advisor_index == 0 else self.advisor_options[self.advisor_index].path.stem
        cycle = RectSpec(panel.x + m.margin, panel.y + m.margin * 2 + m.font_large, panel.width - m.margin * 2, m.target_height)
        Button("advisor_cycle", self.tr("editor_advisor_label", name=label), cycle).draw(self.game.display, pg.font.Font(self.game.font_name, m.font_small), self.game.palette)
        self.catalog_targets.append(("advisor_cycle", None, cycle, True))
        ranked = sorted(self.advice.items(), key=lambda item: item[1].rank)[:8]
        for index, (card_id, advice) in enumerate(ranked):
            card = next((card for card in self.all_cards if card_key(card) == card_id), None)
            if card:
                self.game.draw_text_left(f"#{advice.rank} {card.name} · {advice.score:.2f}", m.font_small, panel.x + m.margin, cycle.bottom + m.gap + index * (m.font_small + 8), max_width=panel.width - m.margin * 2)

    def _draw_responsive_editor(self):
        header, catalog, sidebar, narrow = self._layout()
        if narrow:
            if self.narrow_tab == ActivePane.AVAILABLE:
                self._draw_catalog(catalog, True)
                self.sidebar_rect = RectSpec(0, 0, 0, 0)
            else:
                self._draw_sidebar(sidebar, True)
                self.catalog_rect = RectSpec(0, 0, 0, 0)
        else:
            self._draw_catalog(catalog, False)
            self._draw_sidebar(sidebar, False)
        self._draw_advisor()

    def _draw(self):
        self.draw_background()
        self._build_controls()
        self.draw_buttons(list(self.controls.values()))
        self._draw_responsive_editor()
        if self.message:
            self.draw_message(self.message, self.game.palette.danger if self.message_error else self.game.palette.muted)
        self.detail.draw(self.game)

    def check_input(self):
        self._handle_events()

    def _handle_mouse(self):
        self._handle_events()

    def display_menu(self):
        self.run_display = True
        self.game.reset_keys()
        while self.run_display and self.game.running:
            self.begin_frame()
            self._build_controls()
            self._handle_events()
            if not self.run_display:
                break
            self._draw()
            self.detail.finish_frame()
            self.blit_screen()
