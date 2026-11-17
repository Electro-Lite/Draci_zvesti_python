from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

import pygame as pg

from cards.deck import Deck
from cards.power import Power
from core.config import MAX_DECK_SIZE, MIN_DECK_SIZE
from py_game.deck_editor import DeckBuilderMenu
from py_game.menu.deck_menu import DeckMenu
from py_game.ui.deck_management import CardDetailOverlay, deck_validation


def card(card_id, power=Power.NORMAL):
    return SimpleNamespace(id=card_id, name=card_id, power=power)


class DeckManagementTests(TestCase):
    def test_validation_groups_copies_by_stable_card_id(self):
        deck = Deck()
        deck.cards = [card("same") for _ in range(5)] + [
            card(f"other-{i}") for i in range(MIN_DECK_SIZE - 5)
        ]

        with self.assertRaisesRegex(ValueError, "at most 4"):
            deck.validate()

    def test_validation_uses_authoritative_legendary_power(self):
        cards = [card("legend", Power.LEGENDARY), card("legend", Power.LEGENDARY)]
        cards.extend(card(f"normal-{index}") for index in range(MIN_DECK_SIZE - 2))

        valid, message = deck_validation(cards)

        self.assertFalse(valid)
        self.assertIn("Legendary", message)

    def test_capped_and_full_deck_cards_remain_in_catalog(self):
        menu = DeckBuilderMenu.__new__(DeckBuilderMenu)
        capped = card("capped")
        menu.all_cards = [capped, card("other")]
        menu.deck_cards = [capped] * 4 + [
            card(f"fill-{index}") for index in range(MAX_DECK_SIZE - 4)
        ]

        self.assertEqual(menu._available_cards(), menu.all_cards)

    def test_new_save_uses_fresh_identity(self):
        menu = DeckBuilderMenu.__new__(DeckBuilderMenu)
        menu.deck_cards = [card(f"card-{index}") for index in range(MIN_DECK_SIZE)]
        menu.deck_name = "Independent copy"
        menu.deck_description = "kept"
        menu.deck_power = 0
        menu.deck_fitness = 0
        menu.current_deck_id = None
        menu.unsaved_copy = False
        menu.db = SimpleNamespace(save_deck=Mock())
        menu._original = ("", "", ())
        menu.dirty = True
        menu.message = ""
        menu.message_error = False

        self.assertTrue(menu._save())

        saved = menu.db.save_deck.call_args.args[0]
        self.assertTrue(saved.id.startswith("user_"))
        self.assertEqual(menu.current_deck_id, saved.id)
        self.assertEqual(saved.description, "kept")

    def test_save_failure_preserves_unsaved_edits_for_retry(self):
        menu = DeckBuilderMenu.__new__(DeckBuilderMenu)
        menu.deck_cards = [card(f"card-{index}") for index in range(MIN_DECK_SIZE)]
        menu.deck_name = "Retry me"
        menu.deck_description = "still here"
        menu.deck_power = 0
        menu.deck_fitness = 0
        menu.current_deck_id = None
        menu.unsaved_copy = False
        menu.db = SimpleNamespace(save_deck=Mock(side_effect=OSError("disk busy")))
        menu._original = ("", "", ())
        menu.dirty = True
        menu.message = ""
        menu.message_error = False

        self.assertFalse(menu._save())

        self.assertTrue(menu.dirty)
        self.assertIsNone(menu.current_deck_id)
        self.assertEqual(menu.deck_name, "Retry me")
        self.assertIn("disk busy", menu.message)

    def test_unsaved_duplicate_stays_dirty_even_at_source_composition(self):
        menu = DeckBuilderMenu.__new__(DeckBuilderMenu)
        menu.deck_name = "Source copy"
        menu.deck_description = "description"
        menu.deck_cards = [card(f"card-{index}") for index in range(MIN_DECK_SIZE)]
        menu._original = menu._snapshot()
        menu.unsaved_copy = True
        menu.dirty = False

        menu._sync_dirty()

        self.assertTrue(menu.dirty)

    def test_card_detail_requires_a_later_click_and_consumes_close(self):
        overlay = CardDetailOverlay()
        overlay.open(card("detail"))
        opening_events = (
            pg.event.Event(pg.MOUSEBUTTONDOWN, button=3, pos=(10, 10)),
            pg.event.Event(pg.MOUSEBUTTONUP, button=3, pos=(10, 10)),
        )

        self.assertTrue(overlay.consume_events(opening_events))
        self.assertTrue(overlay.active)
        overlay.finish_frame()
        self.assertTrue(
            overlay.consume_events(
                (pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=(500, 500)),)
            )
        )
        self.assertFalse(overlay.active)
        self.assertTrue(overlay.captures_input)
        self.assertTrue(
            overlay.consume_events(
                (pg.event.Event(pg.MOUSEBUTTONUP, button=1, pos=(500, 500)),)
            )
        )
        self.assertFalse(overlay.captures_input)

    def test_release_only_context_click_can_open_then_close_detail(self):
        overlay = CardDetailOverlay()
        overlay.open(card("detail"), opened_on_release=True)
        overlay.finish_frame()

        self.assertTrue(
            overlay.consume_events(
                (pg.event.Event(pg.MOUSEBUTTONUP, button=3, pos=(10, 10)),)
            )
        )
        self.assertFalse(overlay.active)

    def test_complete_context_click_close_consumes_press_and_release(self):
        overlay = CardDetailOverlay()
        overlay.open(card("detail"), opened_on_release=True)
        overlay.finish_frame()

        self.assertTrue(
            overlay.consume_events(
                (
                    pg.event.Event(pg.MOUSEBUTTONDOWN, button=3, pos=(10, 10)),
                    pg.event.Event(pg.MOUSEBUTTONUP, button=3, pos=(10, 10)),
                )
            )
        )
        self.assertFalse(overlay.captures_input)

    def test_detail_close_does_not_click_through_or_close_parent_overlay(self):
        menu = DeckMenu.__new__(DeckMenu)
        menu.detail = CardDetailOverlay()
        menu.detail.open(card("detail"))
        menu.detail.finish_frame()
        menu.composition = object()
        menu.game = SimpleNamespace(
            events=(pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=(50, 50)),)
        )
        menu._handle_pointer = Mock()

        menu._handle_events()

        self.assertFalse(menu.detail.active)
        self.assertIsNotNone(menu.composition)
        menu._handle_pointer.assert_not_called()
