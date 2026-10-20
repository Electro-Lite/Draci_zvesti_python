from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

import pygame as pg

from cards.deck import Deck
from cards.power import Power
from py_game.deck_advisor import DeckAdvisor, discover_advisors
from py_game.menu.base_menu import Menu
from py_game.ui.layout import RectSpec
from py_game.ui.widgets import Button
from utils.database_utils import DBUtil

if TYPE_CHECKING:
    from py_game.game import Game


class ActivePane(Enum):
    AVAILABLE = 0
    ACTIONS = 1
    DECK = 2


class DeckBuilderMenu(Menu):
    PAGE_SIZE = 12

    def __init__(self, game: "Game", deck_id=None):
        super().__init__(game)
        self.db = DBUtil()
        self.previous_menu = None
        self.current_deck_id = deck_id
        loaded = self.db.load_deck(deck_id) if deck_id else None
        self.deck_name = loaded.name if loaded else ""
        self.deck_description = loaded.description if loaded else ""
        self.deck_cards = list(loaded.cards) if loaded else []
        self.all_cards = sorted(
            self.db.get_all_player_cards(),
            key=lambda card: (card.name.lower(), str(card.id)),
        )

        self.active_pane = ActivePane.AVAILABLE
        self.indices = {
            ActivePane.AVAILABLE: 0,
            ActivePane.ACTIONS: 0,
            ActivePane.DECK: 0,
        }
        self.advisor_options = discover_advisors()
        self.advisor_index = 0
        self.advisor = None
        self.advice = {}
        self.dirty = False
        self.message = ""
        self.message_color = self.game.WHITE
        self.image_cache = {}
        self.actions = [
            "Advisor",
            "Add selected to deck",
            "Remove selected",
            "Save deck",
            "Rename deck",
            "Delete deck",
            "Back",
        ]
        self.row_hitboxes = []
        self.pane_rects = {}
        self.available_page = 0
        self.available_page_size = self.PAGE_SIZE
        self.available_page_hitboxes = {}

    def _copy_count(self, card) -> int:
        return sum(
            1
            for deck_card in self.deck_cards
            if str(deck_card.id) == str(card.id)
        )

    @staticmethod
    def _copy_limit(card) -> int:
        return 1 if card.power == Power.LEGENDARY else 4

    def _available_cards(self):
        if len(self.deck_cards) >= 12:
            return []
        return [
            card
            for card in self.all_cards
            if self._copy_count(card) < self._copy_limit(card)
        ]

    def _items(self, pane):
        if pane == ActivePane.AVAILABLE:
            return self._available_cards()
        if pane == ActivePane.ACTIONS:
            return self.actions
        return self.deck_cards

    def _clamp_indices(self):
        for pane in ActivePane:
            items = self._items(pane)
            self.indices[pane] = min(
                self.indices[pane],
                max(0, len(items) - 1),
            )
        self._clamp_available_page()

    def _available_page_count(self, page_size=None):
        page_size = max(1, page_size or self.available_page_size)
        return max(1, (len(self._available_cards()) + page_size - 1) // page_size)

    def _clamp_available_page(self, page_size=None):
        page_size = max(1, page_size or self.available_page_size)
        self.available_page = min(
            max(0, self.available_page),
            self._available_page_count(page_size) - 1,
        )
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
        page_count = self._available_page_count(page_size)
        current = min(max(0, self.available_page), page_count - 1)
        target = min(max(0, current + direction), page_count - 1)
        row = self.indices[ActivePane.AVAILABLE] - current * page_size
        row = min(max(0, row), page_size - 1)
        self.available_page = target
        self.indices[ActivePane.AVAILABLE] = min(
            target * page_size + row,
            len(cards) - 1,
        )

    def _selected_card(self):
        if self.active_pane == ActivePane.ACTIONS:
            return None
        items = self._items(self.active_pane)
        if not items:
            return None
        return items[self.indices[self.active_pane]]

    def _set_message(self, message: str, error: bool = False):
        self.message = message
        self.message_color = (235, 105, 105) if error else self.game.WHITE

    def _refresh_advice(self):
        self.advice = {}
        option = self.advisor_options[self.advisor_index]
        if option.path is None:
            self.advisor = None
            return
        try:
            self.advisor = DeckAdvisor(option.path)
            self.advice = self.advisor.score_cards(
                self.deck_cards,
                self._available_cards(),
            )
            self._set_message(f"Using {option.path.stem}")
        except Exception as error:
            self.advisor = None
            self.advisor_index = 0
            self._set_message(f"Advisor could not load: {error}", error=True)

    def _cycle_advisor(self, direction=1):
        self.advisor_index = (
            self.advisor_index + direction
        ) % len(self.advisor_options)
        self._refresh_advice()

    def _move_vertical(self, direction):
        items = self._items(self.active_pane)
        if items:
            self.indices[self.active_pane] = (
                self.indices[self.active_pane] + direction
            ) % len(items)
            if self.active_pane == ActivePane.AVAILABLE:
                self.available_page = (
                    self.indices[ActivePane.AVAILABLE]
                    // max(1, self.available_page_size)
                )

    def _move_horizontal(self, direction):
        pane_index = list(ActivePane).index(self.active_pane)
        pane_index = max(0, min(len(ActivePane) - 1, pane_index + direction))
        self.active_pane = list(ActivePane)[pane_index]

    def _add_selected(self):
        cards = self._available_cards()
        if not cards:
            self._set_message("The deck is full", error=True)
            return
        card = cards[self.indices[ActivePane.AVAILABLE]]
        self.deck_cards.append(card)
        self.dirty = True
        self._clamp_indices()
        if self.advisor is not None:
            self._refresh_advice()

    def _remove_selected(self):
        if not self.deck_cards:
            return
        self.deck_cards.pop(self.indices[ActivePane.DECK])
        self.dirty = True
        self._clamp_indices()
        if self.advisor is not None:
            self._refresh_advice()

    def _deck_from_state(self):
        deck = Deck()
        deck.id = self.current_deck_id or ""
        deck.name = self.deck_name
        deck.description = self.deck_description
        deck.cards = list(self.deck_cards)
        return deck

    def _save(self):
        try:
            self._deck_from_state().validate()
        except ValueError as error:
            self._set_message(str(error), error=True)
            return
        if not self.deck_name:
            name = self._text_dialog("Deck name", "")
            if name is None:
                return
            self.deck_name = name.strip() or "Custom Deck"
        deck = self._deck_from_state()
        try:
            self.db.save_deck(deck, is_ai=False)
        except (ValueError, OSError) as error:
            self._set_message(str(error), error=True)
            return
        self.current_deck_id = deck.id
        self.dirty = False
        self._set_message(f"Saved {deck.name}")

    def _rename(self):
        name = self._text_dialog("Deck name", self.deck_name)
        if name is not None and name.strip():
            self.deck_name = name.strip()
            self.dirty = True
            self._set_message("Name updated; save to keep changes")

    def _delete(self):
        if not self.current_deck_id:
            self._set_message("This deck has not been saved", error=True)
            return
        if not self._confirm_dialog(f"Delete {self.deck_name}?"):
            return
        self.db.delete_deck(self.current_deck_id)
        self.dirty = False
        self._return()

    def _return(self):
        if self.dirty and not self._confirm_dialog("Discard unsaved changes?"):
            return
        self.run_display = False
        self.game.curr_menu = self.previous_menu
        if self.previous_menu is not None:
            self.previous_menu.run_display = True

    def _activate_action(self):
        action = self.indices[ActivePane.ACTIONS]
        if action == 0:
            self._cycle_advisor()
        elif action == 1:
            self._add_selected()
        elif action == 2:
            self._remove_selected()
        elif action == 3:
            self._save()
        elif action == 4:
            self._rename()
        elif action == 5:
            self._delete()
        else:
            self._return()

    def check_input(self):
        if self.game.BACK_KEY:
            self._return()
            return
        if self.game.UP_KEY:
            self._move_vertical(-1)
        if self.game.DOWN_KEY:
            self._move_vertical(1)
        if self.game.LEFT_KEY:
            if (
                self.active_pane == ActivePane.ACTIONS
                and self.indices[ActivePane.ACTIONS] == 0
            ):
                self._cycle_advisor(-1)
            else:
                self._move_horizontal(-1)
        if self.game.RIGHT_KEY:
            if (
                self.active_pane == ActivePane.ACTIONS
                and self.indices[ActivePane.ACTIONS] == 0
            ):
                self._cycle_advisor(1)
            else:
                self._move_horizontal(1)
        if not self.game.START_KEY:
            return
        if self.active_pane == ActivePane.AVAILABLE:
            self._add_selected()
        elif self.active_pane == ActivePane.DECK:
            self._remove_selected()
        else:
            self._activate_action()

    def _draw_list(self, pane, x, width):
        items = self._items(pane)
        selected = self.indices[pane]
        offset = max(0, min(selected - self.PAGE_SIZE + 1, len(items) - self.PAGE_SIZE))
        for row, item in enumerate(items[offset : offset + self.PAGE_SIZE]):
            index = offset + row
            y = self.game.DISPLAY_H * 0.20 + row * self.TEXT_NORMAL
            if pane == ActivePane.AVAILABLE:
                advice = self.advice.get(str(item.id))
                value = f"  #{advice.rank} {advice.score:.2f}" if advice else ""
                label = f"{item.name}{value}"
            elif pane == ActivePane.DECK:
                label = item.name
            else:
                if index == 0:
                    label = (
                        "Advisor: Off"
                        if self.advisor_index == 0
                        else (
                            f"Advisor: {self.advisor_index}/"
                            f"{len(self.advisor_options) - 1}"
                        )
                    )
                else:
                    label = str(item)
            self.game.draw_text(label, self.TEXT_NORMAL, x, y)

    def _draw_details(self):
        card = self._selected_card()
        detail_y = self.game.DISPLAY_H * 0.55
        x = self.game.DISPLAY_W * 0.50
        self.game.draw_text(
            "--- Card Details ---",
            self.TEXT_NORMAL,
            x,
            detail_y,
        )
        if card is None:
            return

        image_start_y = detail_y + 30
        max_width = self.game.DISPLAY_W * 0.24
        max_height = max(60, self.game.DISPLAY_H - image_start_y - 115)
        image_width = max_width
        image_height = image_width / (5 / 7)
        if image_height > max_height:
            image_height = max_height
            image_width = image_height * (5 / 7)
        if card.image:
            self.game.draw_image(
                card.image,
                x - image_width / 2,
                image_start_y,
                image_width,
                image_height,
            )

        text_y = image_start_y + image_height + 15
        self.game.draw_text(
            f"Name: {card.name}",
            self.TEXT_NORMAL,
            x,
            text_y,
        )
        self.game.draw_text(
            f"HP: {card.hp} | DMG: {card.dmg}",
            self.TEXT_NORMAL,
            x,
            text_y + 25,
        )
        advice = self.advice.get(str(card.id))
        if advice:
            self.game.draw_text(
                (
                    f"Advisor: #{advice.rank}/{advice.candidate_count} "
                    f"value {advice.score:.3f}"
                ),
                self.TEXT_NORMAL,
                x,
                text_y + 50,
            )

    def _update_cursor(self):
        pane_x = {
            ActivePane.AVAILABLE: self.game.DISPLAY_W * 0.20,
            ActivePane.ACTIONS: self.game.DISPLAY_W * 0.50,
            ActivePane.DECK: self.game.DISPLAY_W * 0.80,
        }
        items = self._items(self.active_pane)
        selected = self.indices[self.active_pane]
        offset = max(
            0,
            min(selected - self.PAGE_SIZE + 1, len(items) - self.PAGE_SIZE),
        )
        y = (
            self.game.DISPLAY_H * 0.20
            + (selected - offset) * self.TEXT_NORMAL
        )
        self.cursor_rect.midtop = (
            pane_x[self.active_pane] + self.offset,
            y,
        )

    def display_menu(self):
        self.run_display = True
        self.game.reset_keys()
        while self.run_display and self.game.running:
            self.begin_frame()
            self._handle_mouse()
            self.check_input()
            if not self.run_display:
                break
            self._clamp_indices()
            self.draw_background()
            deck_title = self.deck_name or "New deck"
            self.draw_title(
                "Deck Builder",
                f"{deck_title}  •  {len(self.deck_cards)}/12 cards  •  drag cards between lists",
            )
            self._draw_responsive_editor()
            self.draw_message(self.message, self.message_color)
            self.blit_screen()

    def _draw_responsive_editor(self):
        metrics = self.game.layout
        top = metrics.margin + metrics.font_large + metrics.font_small + metrics.gap * 2
        bottom = self.game.DISPLAY_H - metrics.margin - metrics.font_small - metrics.gap
        area = RectSpec(metrics.margin, top, self.game.DISPLAY_W - metrics.margin * 2, bottom - top)
        columns = metrics.columns(area, (1.15, 0.9, 1.15))
        panes = dict(zip(ActivePane, columns))
        self.pane_rects = panes
        self.row_hitboxes = []
        self.available_page_hitboxes = {}
        titles = {
            ActivePane.AVAILABLE: "Available cards",
            ActivePane.ACTIONS: "Deck actions",
            ActivePane.DECK: "Deck cards",
        }
        for pane, spec in panes.items():
            rect = pg.Rect(spec.x, spec.y, spec.width, spec.height)
            active = pane == self.active_pane
            drop_key = (
                "deck"
                if pane == ActivePane.DECK
                else "available"
                if pane == ActivePane.AVAILABLE
                else None
            )
            valid_drop = (
                self.game.drag.start is not None
                and drop_key in self.game.drag.valid_targets
            )
            pg.draw.rect(self.game.display, self.game.palette.panel, rect, border_radius=10)
            pg.draw.rect(
                self.game.display,
                self.game.palette.success
                if valid_drop
                else self.game.palette.accent
                if active
                else self.game.palette.border,
                rect,
                3 if valid_drop else 2,
                border_radius=10,
            )
            self.game.draw_text(
                titles[pane],
                metrics.font_normal,
                rect.centerx,
                rect.y + metrics.target_height // 2,
                self.game.palette.accent if active else self.game.palette.text,
            )
            self._draw_responsive_list(pane, spec)
        self._draw_responsive_details(panes[ActivePane.ACTIONS])

    def _draw_responsive_list(self, pane, spec):
        metrics = self.game.layout
        items = self._items(pane)
        selected = self.indices[pane]
        details_reserved = int(spec.height * 0.30) if pane == ActivePane.ACTIONS else 0
        pagination_reserved = (
            max(30, metrics.target_height - metrics.gap // 2) + metrics.gap
            if pane == ActivePane.AVAILABLE
            else 0
        )
        list_top = spec.y + metrics.target_height
        available_height = (
            spec.height
            - metrics.target_height
            - details_reserved
            - pagination_reserved
            - metrics.gap
        )
        row_height = max(28, metrics.target_height - metrics.gap // 2)
        page_size = max(1, available_height // row_height)
        if pane == ActivePane.AVAILABLE:
            self.available_page_size = page_size
            self._clamp_available_page(page_size)
            offset = self.available_page * page_size
        else:
            offset = max(0, min(selected - page_size + 1, len(items) - page_size))
        for row, item in enumerate(items[offset : offset + page_size]):
            index = offset + row
            rect = pg.Rect(
                spec.x + metrics.gap,
                list_top + row * row_height,
                spec.width - metrics.gap * 2,
                row_height - 3,
            )
            hovered = rect.collidepoint(self.game.mouse_position)
            fill = (
                self.game.palette.selected
                if pane == self.active_pane and index == selected
                else self.game.palette.hover
                if hovered
                else self.game.palette.panel_alt
            )
            pg.draw.rect(self.game.display, fill, rect, border_radius=5)
            if pane == ActivePane.AVAILABLE:
                advice = self.advice.get(str(item.id))
                value = f"  #{advice.rank} {advice.score:.2f}" if advice else ""
                label = f"{item.name}{value}"
            elif pane == ActivePane.DECK:
                label = item.name
            elif index == 0:
                label = "Advisor: Off" if self.advisor_index == 0 else f"Advisor: {self.advisor_index}/{len(self.advisor_options) - 1}"
            else:
                label = str(item)
            self.game.draw_text_left(
                label,
                metrics.font_small,
                rect.x + metrics.gap,
                rect.centery,
                max_width=rect.width - metrics.gap * 2,
            )
            self.row_hitboxes.append((pane, index, rect))
        if pane == ActivePane.AVAILABLE:
            self._draw_available_pagination(spec, page_size)

    def _draw_available_pagination(self, spec, page_size):
        metrics = self.game.layout
        footer_height = max(30, metrics.target_height - metrics.gap // 2)
        footer_y = spec.bottom - metrics.gap - footer_height
        inner_x = spec.x + metrics.gap
        inner_width = spec.width - metrics.gap * 2
        button_width = max(34, min(74, (inner_width - metrics.gap * 2) // 3))
        previous_rect = RectSpec(inner_x, footer_y, button_width, footer_height)
        next_rect = RectSpec(
            spec.right - metrics.gap - button_width,
            footer_y,
            button_width,
            footer_height,
        )
        page_count = self._available_page_count(page_size)
        self.available_page_hitboxes = {
            "previous": previous_rect,
            "next": next_rect,
        }
        font = pg.font.Font(
            self.game.font_name,
            max(11, metrics.font_small - (2 if spec.width < 260 else 0)),
        )
        compact = spec.width < 300
        for key, label, rect, enabled in (
            (
                "previous",
                "<" if compact else "< Prev",
                previous_rect,
                self.available_page > 0,
            ),
            (
                "next",
                ">" if compact else "Next >",
                next_rect,
                self.available_page < page_count - 1,
            ),
        ):
            Button(
                key,
                label,
                rect,
                enabled=enabled,
                hovered=enabled and rect.contains(self.game.mouse_position),
            ).draw(self.game.display, font, self.game.palette)
        center_x = (previous_rect.right + next_rect.x) // 2
        self.game.draw_text(
            f"{self.available_page + 1}/{page_count}",
            max(11, metrics.font_small - 2),
            center_x,
            footer_y + footer_height // 2,
            self.game.palette.muted,
        )

    def _draw_responsive_details(self, spec):
        card = self._selected_card()
        if card is None:
            return
        metrics = self.game.layout
        max_height = int(spec.height * 0.20)
        image_height = max(50, max_height)
        image_width = int(image_height * 5 / 7)
        x = spec.x + (spec.width - image_width) // 2
        y = spec.bottom - image_height - metrics.font_small * 2 - metrics.gap
        image = self.game.assets.image(card.image, (image_width, image_height))
        self.game.display.blit(image, (x, y))
        self.game.draw_text(
            card.name,
            metrics.font_small,
            spec.center[0],
            y + image_height + metrics.font_small // 2,
        )
        self.game.draw_text(
            f"{card.dmg} attack  •  {card.hp} health",
            metrics.font_small,
            spec.center[0],
            y + image_height + metrics.font_small * 3 // 2,
            self.game.palette.muted,
        )

    def _handle_mouse(self):
        if self.game.mouse_wheel:
            for pane, spec in self.pane_rects.items():
                if spec.contains(self.game.mouse_position):
                    self.active_pane = pane
                    if pane == ActivePane.AVAILABLE:
                        self._change_available_page(-self.game.mouse_wheel)
                    else:
                        self._move_vertical(-self.game.mouse_wheel)
                    break
        for event in self.game.events:
            if event.type == pg.KEYDOWN and event.key in (pg.K_PAGEUP, pg.K_PAGEDOWN):
                if self.active_pane == ActivePane.AVAILABLE:
                    self._change_available_page(
                        -1 if event.key == pg.K_PAGEUP else 1,
                    )
                continue
            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                page_direction = next(
                    (
                        -1 if key == "previous" else 1
                        for key, rect in self.available_page_hitboxes.items()
                        if rect.contains(event.pos)
                    ),
                    None,
                )
                if page_direction is not None:
                    self.active_pane = ActivePane.AVAILABLE
                    self._change_available_page(page_direction)
                    continue
                for pane, index, rect in self.row_hitboxes:
                    if rect.collidepoint(event.pos):
                        self.active_pane = pane
                        self.indices[pane] = index
                        if pane in (ActivePane.AVAILABLE, ActivePane.DECK):
                            target = "deck" if pane == ActivePane.AVAILABLE else "available"
                            self.game.drag.begin(f"{pane.name.lower()}:{index}", event.pos, {target})
                            self.message = "Drag to the highlighted list, or release to cancel"
                            self.message_color = self.game.palette.muted
                        if getattr(event, "clicks", 1) >= 2:
                            self._add_selected() if pane == ActivePane.AVAILABLE else self._remove_selected() if pane == ActivePane.DECK else self._activate_action()
                        break
            elif event.type == pg.MOUSEMOTION and self.game.drag.start is not None:
                self.game.drag.move(event.pos)
            elif event.type == pg.MOUSEBUTTONUP and event.button == 1 and self.game.drag.start is not None:
                target = next(
                    (
                        "deck" if pane == ActivePane.DECK else "available"
                        for pane, spec in self.pane_rects.items()
                        if pane in (ActivePane.AVAILABLE, ActivePane.DECK) and spec.contains(event.pos)
                    ),
                    None,
                )
                was_dragging = self.game.drag.dragging
                result = self.game.drag.release(target)
                if result:
                    if result[0].startswith("available:") and result[1] == "deck":
                        self._add_selected()
                    elif result[0].startswith("deck:") and result[1] == "available":
                        self._remove_selected()
                elif was_dragging:
                    self._set_message(
                        "Drop canceled; use the highlighted list",
                        error=True,
                    )
        if self.game.mouse_clicked:
            for pane, index, rect in self.row_hitboxes:
                if rect.collidepoint(self.game.mouse_position):
                    self.active_pane = pane
                    self.indices[pane] = index
                    if pane == ActivePane.ACTIONS:
                        self._activate_action()
                    break

    def _text_dialog(self, title, initial):
        return self.prompt_text(title, initial, max_length=32)

    def _confirm_dialog(self, title):
        label = "Delete" if title.startswith("Delete") else "Discard"
        return self.confirm_action(title, confirm_label=label)
