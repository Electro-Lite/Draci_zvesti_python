from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

import pygame as pg

from cards.deck import Deck
from cards.power import Power
from py_game.deck_advisor import DeckAdvisor, discover_advisors
from py_game.menu.base_menu import Menu
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
        self.actions = ["Advisor", "Save deck", "Rename deck", "Delete deck", "Back"]

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
            self.previous_menu.__init__(self.game)
            self.previous_menu.run_display = True

    def _activate_action(self):
        action = self.indices[ActivePane.ACTIONS]
        if action == 0:
            self._cycle_advisor()
        elif action == 1:
            self._save()
        elif action == 2:
            self._rename()
        elif action == 3:
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
        while self.run_display:
            self.game.check_events()
            self.check_input()
            if not self.run_display:
                break
            self._clamp_indices()
            self.game.display.fill(self.game.BLACK)
            self.game.draw_text(
                "Deck Builder",
                self.TEXT_LARGE,
                self.game.DISPLAY_W // 2,
                40,
            )
            width = self.game.DISPLAY_W
            start_y = self.game.DISPLAY_H * 0.20
            self.game.draw_text(
                "Available Cards",
                self.TEXT_NORMAL,
                width * 0.20,
                start_y - 40,
            )
            self.game.draw_text(
                "Deck Cards",
                self.TEXT_NORMAL,
                width * 0.80,
                start_y - 40,
            )
            self._draw_list(
                ActivePane.AVAILABLE,
                width * 0.20,
                width * 0.28,
            )
            self._draw_list(
                ActivePane.ACTIONS,
                width * 0.50,
                width * 0.24,
            )
            self._draw_list(
                ActivePane.DECK,
                width * 0.80,
                width * 0.28,
            )
            self._draw_details()
            self._update_cursor()
            self.draw_cursor()
            if self.message:
                self.game.draw_text(
                    self.message,
                    self.TEXT_NORMAL,
                    self.game.DISPLAY_W // 2,
                    565,
                    self.message_color,
                )
            self.blit_screen()

    def _text_dialog(self, title, initial):
        value = initial
        while True:
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    return None
                if event.type != pg.KEYDOWN:
                    continue
                if event.key == pg.K_ESCAPE:
                    return None
                if event.key == pg.K_RETURN:
                    return value
                if event.key == pg.K_BACKSPACE:
                    value = value[:-1]
                elif event.unicode.isprintable() and len(value) < 32:
                    value += event.unicode
            self.game.display.fill(self.game.BLACK)
            self.game.draw_text(title, self.TEXT_LARGE, self.mid_w, 235)
            field = pg.Rect(self.mid_w - 220, 280, 440, 55)
            pg.draw.rect(self.game.display, (20, 22, 24), field)
            pg.draw.rect(self.game.display, self.game.ORANGE, field, 2)
            self.game.draw_text(value, self.TEXT_NORMAL, self.mid_w, 307)
            self.blit_screen()

    def _confirm_dialog(self, title):
        selected = False
        while True:
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    return False
                if event.type != pg.KEYDOWN:
                    continue
                if event.key in (pg.K_ESCAPE, pg.K_BACKSPACE):
                    return False
                if event.key in (pg.K_LEFT, pg.K_RIGHT):
                    selected = not selected
                if event.key in (pg.K_RETURN, pg.K_SPACE):
                    return selected
            self.game.display.fill(self.game.BLACK)
            self.game.draw_text(title, self.TEXT_LARGE, self.mid_w, 245)
            self.game.draw_text(
                "Confirm" if selected else "Cancel",
                self.TEXT_NORMAL,
                self.mid_w,
                320,
                self.game.ORANGE,
            )
            self.blit_screen()
