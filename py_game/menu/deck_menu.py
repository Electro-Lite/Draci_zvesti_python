from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame as pg

from py_game.deck_editor import DeckBuilderMenu
from py_game.menu.base_menu import Menu
from py_game.ui.deck_management import CardDetailOverlay, ellipsize, sorted_groups
from py_game.ui.layout import RectSpec
from py_game.ui.widgets import Button, TextInput
from utils.database_utils import DBUtil

if TYPE_CHECKING:
    from py_game.game import Game


@dataclass(frozen=True)
class LibraryDeck:
    deck_id: str
    name: str
    deck: object


class DeckMenu(Menu):
    """Compact deck library. Database work is kept outside the draw path."""

    PAGE_SIZE = 10

    def __init__(self, game: "Game"):
        super().__init__(game)
        self.previous_menu = None
        self.db = DBUtil()
        self.search = TextInput(max_length=64)
        self.sort_ascending = True
        self.selected_deck_id: str | None = None
        self.scroll = 0
        self.entries: list[LibraryDeck] = []
        self.deck_options = ()
        self.items = []
        self.message = ""
        self.detail = CardDetailOverlay()
        self.focused_card = None
        self.composition: LibraryDeck | None = None
        self.composition_scroll = 0
        self.overflow_deck_id: str | None = None
        self.search_rect = RectSpec(0, 0, 0, 0)
        self.controls: dict[str, Button] = {}
        self.row_targets = []
        self.composition_targets = []
        self.composition_close_rect = RectSpec(0, 0, 0, 0)
        self._refresh_decks()

    def _refresh_decks(self, selected_deck_id=None):
        selected_deck_id = selected_deck_id or self.selected_deck_id
        entries = []
        try:
            for deck_id, name in self.db.get_all_deck_options():
                deck = self.db.load_deck(deck_id)
                entries.append(LibraryDeck(str(deck_id), str(name), deck))
            self.message = ""
        except Exception as error:
            self.message = f"Could not load decks: {error}"
        self.entries = entries
        self.deck_options = tuple((entry.deck_id, entry.name) for entry in entries)
        self.items = [entry.name for entry in entries]
        ids = {entry.deck_id for entry in entries}
        self.selected_deck_id = selected_deck_id if selected_deck_id in ids else (entries[0].deck_id if entries else None)
        self._clamp_scroll()

    def _filtered_entries(self):
        query = self.search.value.strip().casefold()
        entries = [entry for entry in self.entries if not query or query in entry.name.casefold()]
        return sorted(entries, key=lambda entry: (entry.name.casefold(), entry.deck_id), reverse=not self.sort_ascending)

    def _filtered_decks(self):
        return tuple((entry.deck_id, entry.name) for entry in self._filtered_entries())

    def _page_count(self):
        return max(1, (len(self._filtered_entries()) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

    @property
    def selected(self):
        ids = [entry.deck_id for entry in self._filtered_entries()]
        try:
            return ids.index(self.selected_deck_id)
        except ValueError:
            return 0

    @selected.setter
    def selected(self, index):
        entries = self._filtered_entries() if hasattr(self, "entries") else []
        if entries:
            self.selected_deck_id = entries[min(max(0, index), len(entries) - 1)].deck_id

    def _selected_deck_id(self):
        return self.selected_deck_id

    def _selected_entry(self):
        return next((entry for entry in self.entries if entry.deck_id == self.selected_deck_id), None)

    def _layout(self):
        m = self.game.layout
        header = RectSpec(m.margin, m.margin, self.game.DISPLAY_W - m.margin * 2, m.target_height)
        controls = RectSpec(m.margin, header.bottom + m.gap, header.width, m.target_height)
        body = RectSpec(m.margin, controls.bottom + m.gap + m.font_small, header.width, self.game.DISPLAY_H - controls.bottom - m.margin - m.gap - m.font_small)
        return header, controls, body

    def _visible_row_count(self):
        _header, _controls, body = self._layout()
        return max(1, body.height // max(62, self.game.layout.target_height + self.game.layout.gap))

    def _clamp_scroll(self):
        if not hasattr(self.game, "layout"):
            return
        entries = self._filtered_entries()
        self.scroll = min(max(0, self.scroll), max(0, len(entries) - self._visible_row_count()))
        ids = [entry.deck_id for entry in entries]
        if self.selected_deck_id not in ids:
            self.selected_deck_id = ids[0] if ids else None

    def _build_controls(self):
        m = self.game.layout
        header, controls, _body = self._layout()
        back_w = max(80, min(130, header.width // 6))
        new_w = max(110, min(180, header.width // 5))
        self.controls = {
            "back": Button("back", f"< {self.tr('back')}", RectSpec(header.x, header.y, back_w, header.height)),
            "new": Button("new", self.tr("decks_new"), RectSpec(header.right - new_w, header.y, new_w, header.height)),
        }
        sort_w = max(110, min(200, controls.width // 4))
        self.search_rect = RectSpec(controls.x, controls.y, controls.width - sort_w - m.gap, controls.height)
        sort_rect = RectSpec(self.search_rect.right + m.gap, controls.y, sort_w, controls.height)
        self.controls["sort"] = Button("sort", self.tr("decks_sort_ascending") if self.sort_ascending else self.tr("decks_sort_descending"), sort_rect)
        for button in self.controls.values():
            button.hovered = button.rect.contains(self.game.mouse_position)

    def _open_editor(self, deck_id=None, *, duplicate=None):
        editor = DeckBuilderMenu(self.game, deck_id, source_deck=duplicate)
        editor.previous_menu = self
        self.game.curr_menu = editor
        self.run_display = False
        editor.display_menu()
        self._refresh_decks(editor.current_deck_id or self.selected_deck_id)

    def _rename(self, entry):
        if entry.deck is None:
            self.message = self.tr("decks_load_failed")
            return
        name = self.prompt_text(self.tr("decks_rename_title"), entry.name, max_length=64)
        if name is None:
            return
        name = name.strip()
        if not name:
            self.message = self.tr("decks_blank_name")
            return
        entry.deck.name = name
        try:
            self.db.save_deck(entry.deck, is_ai=False)
        except Exception as error:
            self.message = f"Rename failed: {error}"
            return
        self._refresh_decks(entry.deck_id)
        self.message = self.tr("decks_renamed")

    def _delete(self, entry):
        if not self.confirm_action(self.tr("decks_delete_title", name=entry.name), (self.tr("decks_delete_detail"),), confirm_label=self.tr("decks_delete")):
            return
        try:
            self.db.delete_deck(entry.deck_id)
        except Exception as error:
            self.message = f"Delete failed: {error}"
            return
        self.selected_deck_id = None
        self._refresh_decks()
        self.message = self.tr("decks_deleted")

    def _duplicate(self, entry):
        if entry.deck is None:
            self.message = self.tr("decks_load_failed")
            return
        self._open_editor(duplicate=entry.deck)

    def _handle_composition(self):
        if self.composition is None:
            return False
        for event in self.game.events:
            if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                self.composition = None
                return True
            if event.type == pg.KEYDOWN and event.key == pg.K_TAB and self.composition_targets:
                cards = [card for card, _rect in self.composition_targets]
                try:
                    index = cards.index(self.focused_card)
                except ValueError:
                    index = -1
                self.focused_card = cards[(index + 1) % len(cards)]
                return True
            if event.type == pg.KEYDOWN and event.key in (pg.K_RETURN, pg.K_KP_ENTER) and self.focused_card is not None:
                self.detail.open(self.focused_card)
                return True
            if event.type == pg.MOUSEWHEEL:
                self.composition_scroll = max(0, self.composition_scroll - event.y)
            if event.type in (pg.MOUSEBUTTONDOWN, pg.MOUSEBUTTONUP) and event.button == 3:
                for card, rect in self.composition_targets:
                    if rect.contains(event.pos):
                        self.detail.open(card, opened_on_release=event.type == pg.MOUSEBUTTONUP)
                        return True
            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                for card, rect in self.composition_targets:
                    if rect.contains(event.pos):
                        self.focused_card = card
                        return True
                if self.composition_close_rect.contains(event.pos):
                    self.composition = None
                return True
        return True

    def _handle_events(self):
        if self.detail.captures_input:
            self.detail.consume_events(self.game.events)
            return
        if self._handle_composition():
            return
        entries = self._filtered_entries()
        for event in self.game.events:
            if event.type == pg.KEYDOWN and self.search.focused:
                before = self.search.value
                if event.key in (pg.K_RETURN, pg.K_KP_ENTER, pg.K_ESCAPE):
                    self.search.focused = False
                else:
                    self.search.handle_event(event)
                if self.search.value != before:
                    self.scroll = 0
                    self.selected_deck_id = None
                    self._clamp_scroll()
                continue
            if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                if self.overflow_deck_id:
                    self.overflow_deck_id = None
                else:
                    self.return_to_previous()
                return
            if event.type == pg.KEYDOWN and event.key == pg.K_TAB:
                cards = [payload for key, _entry, payload, _rect in self.row_targets if key == "card"]
                if cards:
                    try:
                        index = cards.index(self.focused_card)
                    except ValueError:
                        index = -1
                    self.focused_card = cards[(index + 1) % len(cards)]
                return
            if event.type == pg.KEYDOWN and event.key in (pg.K_UP, pg.K_DOWN) and entries:
                self.selected = self.selected + (-1 if event.key == pg.K_UP else 1)
                self._ensure_selected_visible()
            if event.type == pg.KEYDOWN and event.key in (pg.K_RETURN, pg.K_KP_ENTER):
                if self.focused_card is not None:
                    self.detail.open(self.focused_card)
                elif self.selected_deck_id:
                    self._open_editor(self.selected_deck_id)
                return
            if event.type == pg.MOUSEWHEEL:
                self.scroll -= event.y
                self._clamp_scroll()
            if (
                event.type == pg.MOUSEBUTTONDOWN and event.button in (1, 3)
            ) or (event.type == pg.MOUSEBUTTONUP and event.button == 3):
                self._handle_pointer(event)
                return

    def _ensure_selected_visible(self):
        index = self.selected
        visible = self._visible_row_count()
        if index < self.scroll:
            self.scroll = index
        elif index >= self.scroll + visible:
            self.scroll = index - visible + 1

    def _handle_pointer(self, event):
        point = event.pos
        if event.button == 1 and self.search_rect.contains(point):
            self.search.focused = True
            self.overflow_deck_id = None
            return
        self.search.focused = False
        if event.button == 1:
            for key, button in self.controls.items():
                if button.hit_test(point):
                    if key == "back": self.return_to_previous()
                    elif key == "new": self._open_editor()
                    elif key == "sort":
                        self.sort_ascending = not self.sort_ascending
                        self.scroll = 0
                        self._ensure_selected_visible()
                    return
        if self.overflow_deck_id:
            for key, entry, _payload, rect in self.row_targets:
                if key.startswith("menu:") and rect.contains(point) and event.button == 1:
                    self.overflow_deck_id = None
                    action = key.split(":", 1)[1]
                    if action == "rename": self._rename(entry)
                    elif action == "duplicate": self._duplicate(entry)
                    else: self._delete(entry)
                    return
        for key, entry, payload, rect in self.row_targets:
            if not rect.contains(point):
                continue
            self.selected_deck_id = entry.deck_id
            if key == "card":
                self.focused_card = payload
                if event.button == 3:
                    self.detail.open(payload, opened_on_release=event.type == pg.MOUSEBUTTONUP)
                return
            if event.button != 1:
                return
            self.focused_card = None
            if key == "more":
                self.composition = entry
                self.composition_scroll = 0
            elif key == "overflow":
                self.overflow_deck_id = None if self.overflow_deck_id == entry.deck_id else entry.deck_id
            elif key in ("edit", "row"):
                self._open_editor(entry.deck_id)
            return

    def _draw_search(self):
        rect = pg.Rect(self.search_rect.x, self.search_rect.y, self.search_rect.width, self.search_rect.height)
        pg.draw.rect(self.game.display, self.game.palette.panel_alt, rect, border_radius=8)
        pg.draw.rect(self.game.display, self.game.palette.accent if self.search.focused else self.game.palette.border, rect, 2, border_radius=8)
        self.game.draw_text_left(self.search.value or self.tr("decks_search"), self.game.layout.font_small, rect.x + self.game.layout.gap, rect.centery, self.game.palette.text if self.search.value else self.game.palette.muted, rect.width - self.game.layout.gap * 2)

    def _draw_rows(self):
        m = self.game.layout
        _header, _controls, body = self._layout()
        entries = self._filtered_entries()
        visible = self._visible_row_count()
        row_h = max(62, body.height // visible)
        self.row_targets = []
        if not entries:
            text = self.tr("decks_none_found") if self.search.value else self.tr("decks_none")
            self.game.draw_text(text, m.font_normal, body.center[0], body.center[1], self.game.palette.muted)
            return
        font = pg.font.Font(self.game.font_name, m.font_normal)
        small = pg.font.Font(self.game.font_name, m.font_small)
        overflow_popup = None
        for row, entry in enumerate(entries[self.scroll:self.scroll + visible]):
            y = body.y + row * row_h
            rect = RectSpec(body.x, y, body.width, row_h - m.gap // 2)
            selected = entry.deck_id == self.selected_deck_id
            target = pg.Rect(rect.x, rect.y, rect.width, rect.height)
            pg.draw.rect(self.game.display, self.game.palette.selected if selected else self.game.palette.panel, target, border_radius=8)
            pg.draw.rect(self.game.display, self.game.palette.accent if selected else self.game.palette.border, target, 2, border_radius=8)
            compact = rect.width < 850
            name_w = max(110, rect.width // (3 if compact else 4))
            edit_w, overflow_w, total_w = (72 if compact else 96), 48, 45
            preview_x = rect.x + name_w
            preview_right = rect.right - edit_w - overflow_w - total_w - m.gap * 3
            name = ellipsize(font, entry.name, name_w - m.gap * 2)
            self.game.draw_text_left(name, m.font_normal, rect.x + m.gap, rect.y + rect.height // 2, max_width=name_w - m.gap * 2)
            cards = getattr(entry.deck, "cards", ())
            groups = sorted_groups(cards)
            thumb_h = max(42, rect.height - 14)
            thumb_w = round(thumb_h * 5 / 7)
            slot_w = thumb_w + (28 if not compact else 18)
            capacity = max(0, (preview_right - preview_x) // max(1, slot_w))
            shown_count = min(len(groups), capacity)
            if len(groups) > capacity and capacity:
                shown_count = max(0, capacity - 1)
            for index, (card, count) in enumerate(groups[:shown_count]):
                image_rect = RectSpec(preview_x + index * slot_w, rect.y + (rect.height - thumb_h) // 2, thumb_w, thumb_h)
                self.game.display.blit(self.game.assets.image(getattr(card, "image", None), (thumb_w, thumb_h)), (image_rect.x, image_rect.y))
                self.game.draw_text(f"×{count}", max(11, m.font_small - 2), image_rect.right + 10, rect.y + rect.height // 2, self.game.palette.muted)
                self.row_targets.append(("card", entry, card, image_rect))
            remaining = len(groups) - shown_count
            if remaining > 0 and capacity:
                more_rect = RectSpec(preview_x + shown_count * slot_w, rect.y + (rect.height - 40) // 2, max(40, slot_w - 4), 40)
                Button("more", f"+{remaining}", more_rect).draw(self.game.display, small, self.game.palette)
                self.row_targets.append(("more", entry, None, more_rect))
            total_x = rect.right - edit_w - overflow_w - total_w - m.gap * 3
            self.game.draw_text("—" if entry.deck is None else str(len(cards)), m.font_normal, total_x + total_w // 2, rect.y + rect.height // 2, self.game.palette.muted)
            edit_rect = RectSpec(rect.right - edit_w - overflow_w - m.gap * 2, rect.y + (rect.height - 42) // 2, edit_w, 42)
            overflow_rect = RectSpec(rect.right - overflow_w - m.gap, rect.y + (rect.height - 42) // 2, overflow_w, 42)
            Button("edit", self.tr("decks_edit"), edit_rect).draw(self.game.display, small, self.game.palette)
            Button("overflow", "•••", overflow_rect).draw(self.game.display, small, self.game.palette)
            self.row_targets.extend((("edit", entry, None, edit_rect), ("overflow", entry, None, overflow_rect), ("row", entry, None, rect)))
            if self.overflow_deck_id == entry.deck_id:
                overflow_popup = (entry, overflow_rect)
        if overflow_popup is not None:
            self._draw_overflow(*overflow_popup)
        if self.scroll > 0:
            self.game.draw_text("▲", m.font_small, body.right - 10, body.y + 8, self.game.palette.accent)
        if self.scroll + visible < len(entries):
            self.game.draw_text("▼", m.font_small, body.right - 10, body.bottom - 8, self.game.palette.accent)

    def _draw_overflow(self, entry, anchor):
        m = self.game.layout
        width, height = max(150, m.target_height * 3), 134
        x = min(anchor.right - width, self.game.DISPLAY_W - m.margin - width)
        y = min(anchor.bottom, self.game.DISPLAY_H - m.margin - height)
        panel = pg.Rect(x, y, width, height)
        pg.draw.rect(self.game.display, self.game.palette.panel_alt, panel, border_radius=8)
        pg.draw.rect(self.game.display, self.game.palette.border, panel, 2, border_radius=8)
        font = pg.font.Font(self.game.font_name, m.font_small)
        for index, (key, label) in enumerate((("rename", self.tr("decks_rename")), ("duplicate", self.tr("decks_duplicate")), ("delete", self.tr("decks_delete")))):
            rect = RectSpec(x + 4, y + 4 + index * 42, width - 8, 38)
            Button(key, label, rect, destructive=key == "delete", hovered=rect.contains(self.game.mouse_position)).draw(self.game.display, font, self.game.palette)
            self.row_targets.append((f"menu:{key}", entry, None, rect))

    def _draw_composition(self):
        if self.composition is None:
            return
        m = self.game.layout
        shade = pg.Surface((self.game.DISPLAY_W, self.game.DISPLAY_H), pg.SRCALPHA)
        shade.fill((5, 9, 14, 210))
        self.game.display.blit(shade, (0, 0))
        panel = self.game.layout.centered_panel(0.86, 0.84)
        panel_rect = pg.Rect(panel.x, panel.y, panel.width, panel.height)
        pg.draw.rect(self.game.display, self.game.palette.panel, panel_rect, border_radius=12)
        pg.draw.rect(self.game.display, self.game.palette.border, panel_rect, 2, border_radius=12)
        self.game.draw_text(self.composition.name, m.font_large, panel.center[0], panel.y + m.margin)
        self.composition_close_rect = RectSpec(panel.right - m.margin - 100, panel.y + m.gap, 100, m.target_height)
        Button("close", self.tr("decks_close"), self.composition_close_rect).draw(self.game.display, pg.font.Font(self.game.font_name, m.font_small), self.game.palette)
        groups = sorted_groups(getattr(self.composition.deck, "cards", ()))
        card_h = max(100, min(190, (panel.height - m.margin * 3 - m.font_large) // 2))
        card_w = round(card_h * 5 / 7)
        columns = max(1, (panel.width - m.margin * 2) // (card_w + m.gap))
        visible_rows = max(1, (panel.height - m.margin * 3 - m.font_large) // (card_h + m.font_small + m.gap))
        max_scroll = max(0, (len(groups) + columns - 1) // columns - visible_rows)
        self.composition_scroll = min(self.composition_scroll, max_scroll)
        start = self.composition_scroll * columns
        self.composition_targets = []
        for visible_index, (card, count) in enumerate(groups[start:start + columns * visible_rows]):
            row, col = divmod(visible_index, columns)
            x = panel.x + m.margin + col * (card_w + m.gap)
            y = panel.y + m.margin * 2 + m.font_large + row * (card_h + m.font_small + m.gap)
            rect = RectSpec(x, y, card_w, card_h)
            self.game.display.blit(self.game.assets.image(getattr(card, "image", None), (card_w, card_h)), (x, y))
            if card is self.focused_card:
                pg.draw.rect(self.game.display, self.game.palette.accent, pg.Rect(x, y, card_w, card_h), 3, border_radius=5)
            self.game.draw_text(f"×{count}", m.font_small, x + card_w // 2, y + card_h + m.font_small // 2)
            self.composition_targets.append((card, rect))

    def _draw(self):
        self.draw_background()
        self._build_controls()
        m = self.game.layout
        header, _controls, body = self._layout()
        self.draw_buttons(list(self.controls.values()))
        self.game.draw_text(self.tr("decks_title"), m.font_large, self.game.DISPLAY_W // 2, header.y + header.height // 2)
        self._draw_search()
        self.game.draw_text_left(self.tr("decks_count", count=len(self._filtered_entries())), m.font_small, body.x + m.gap, body.y - m.font_small, self.game.palette.muted)
        self.game.draw_text(self.tr("decks_cards"), m.font_small, body.right - 220, body.y - m.font_small, self.game.palette.muted)
        self._draw_rows()
        if self.message:
            self.draw_message(self.message, self.game.palette.danger)
        self._draw_composition()
        self.detail.draw(self.game)

    def display_menu(self):
        self.run_display = True
        self.game.reset_keys()
        while self.run_display and self.game.running:
            self.begin_frame()
            self._build_controls()
            self._handle_events()
            if not self.run_display:
                break
            self._clamp_scroll()
            self._draw()
            self.detail.finish_frame()
            self.blit_screen()
