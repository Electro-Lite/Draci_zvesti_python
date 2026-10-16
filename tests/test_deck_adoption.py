import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cards.card import Card
from neat_ai.player_artifacts import export_player_artifact, load_player_artifact
from py_game.deck_adoption import (
    AdoptableDeck,
    DeckAdoptionConflict,
    DeckAdoptionError,
    DeckAdoptionService,
)


class _AdoptionDatabase:
    def __init__(self, cards):
        self.conn_decks = sqlite3.connect(":memory:")
        self.conn_decks.executescript(
            """
            CREATE TABLE decks (
                id TEXT PRIMARY KEY, name TEXT, description TEXT, power INTEGER,
                fitness INTEGER, is_AI BOOLEAN DEFAULT 0, signature TEXT
            );
            CREATE TABLE deck_lines (deck_id TEXT, card_id TEXT, signature TEXT);
            """
        )
        self.cards = {card.id: card for card in cards}

    @staticmethod
    def _deck_signature(card_ids):
        return hashlib.md5(",".join(card_ids).encode("utf-8")).hexdigest()

    def load_card(self, card_id):
        return self.cards.get(card_id)


def _cards(count=10):
    return tuple(Card(id=f"card-{index}", name=f"Card {index}") for index in range(count))


class DeckAdoptionTests(unittest.TestCase):
    def setUp(self):
        self.cards = _cards()
        self.database = _AdoptionDatabase(self.cards)
        self.service = DeckAdoptionService(self.database)
        self.source = AdoptableDeck(
            "generated-top",
            "Selected candidate",
            tuple(card.id for card in self.cards),
            "Counter run · selected candidate",
        )

    def tearDown(self):
        self.database.conn_decks.close()

    def test_adopts_the_explicitly_selected_source_with_fresh_user_identity(self):
        receipt = self.service.adopt(self.source, "My counter")
        row = self.database.conn_decks.execute(
            "SELECT id, name, is_AI, signature FROM decks"
        ).fetchone()
        persisted = tuple(
            value[0]
            for value in self.database.conn_decks.execute(
                "SELECT card_id FROM deck_lines WHERE signature=? ORDER BY rowid",
                (row[3],),
            )
        )
        self.assertEqual(receipt.source_id, "generated-top")
        self.assertNotEqual(receipt.deck_id, self.source.source_id)
        self.assertTrue(receipt.deck_id.startswith("user_"))
        self.assertEqual(row[1:3], ("My counter", 0))
        self.assertEqual(persisted, self.source.card_ids)

    def test_source_rows_are_never_mutated(self):
        signature = self.database._deck_signature(list(self.source.card_ids))
        self.database.conn_decks.execute(
            "INSERT INTO decks VALUES (?, ?, ?, 0, 7, 1, ?)",
            (self.source.source_id, "Generated", "artifact", signature),
        )
        self.database.conn_decks.executemany(
            "INSERT INTO deck_lines VALUES (?, ?, ?)",
            ((signature, card_id, signature) for card_id in self.source.card_ids),
        )
        self.database.conn_decks.commit()
        self.service.adopt(self.source, "Independent copy")
        source = self.database.conn_decks.execute(
            "SELECT name, description, fitness, is_AI FROM decks WHERE id=?",
            (self.source.source_id,),
        ).fetchone()
        self.assertEqual(source, ("Generated", "artifact", 7, 1))

    def test_duplicate_name_and_composition_are_explicit_conflicts(self):
        self.service.adopt(self.source, "First copy")
        with self.assertRaises(DeckAdoptionConflict) as name_error:
            self.service.adopt(
                AdoptableDeck("other", "Other", tuple(reversed(self.source.card_ids)), "run"),
                "first COPY",
            )
        self.assertIn("name", str(name_error.exception))
        with self.assertRaises(DeckAdoptionConflict) as composition_error:
            self.service.adopt(self.source, "Different name")
        self.assertIn("composition", str(composition_error.exception))
        self.assertEqual(
            self.database.conn_decks.execute("SELECT COUNT(*) FROM decks").fetchone()[0],
            1,
        )

    def test_missing_or_invalid_historical_composition_is_not_repaired(self):
        missing = AdoptableDeck(
            "missing", "Missing", self.source.card_ids[:-1] + ("gone",), "run"
        )
        with self.assertRaisesRegex(DeckAdoptionError, "missing cards"):
            self.service.adopt(missing, "Missing copy")
        short = AdoptableDeck("short", "Short", self.source.card_ids[:9], "run")
        with self.assertRaisesRegex(DeckAdoptionError, "not a valid user deck"):
            self.service.adopt(short, "Short copy")
        self.assertEqual(
            self.database.conn_decks.execute("SELECT COUNT(*) FROM decks").fetchone()[0],
            0,
        )

    def test_legacy_user_composition_without_signature_is_still_a_conflict(self):
        self.database.conn_decks.execute(
            "INSERT INTO decks VALUES ('legacy', 'Legacy deck', '', 0, 0, 0, NULL)"
        )
        self.database.conn_decks.executemany(
            "INSERT INTO deck_lines VALUES ('legacy', ?, NULL)",
            ((card_id,) for card_id in self.source.card_ids),
        )
        self.database.conn_decks.commit()
        with self.assertRaisesRegex(DeckAdoptionConflict, "composition"):
            self.service.adopt(self.source, "Fresh name")
        self.assertEqual(
            self.database.conn_decks.execute("SELECT COUNT(*) FROM decks").fetchone()[0],
            1,
        )

    def test_persistence_failure_rolls_back_metadata_and_lines(self):
        self.database.conn_decks.execute(
            """
            CREATE TRIGGER reject_user_deck BEFORE INSERT ON decks
            WHEN NEW.name = 'Rejected'
            BEGIN SELECT RAISE(ABORT, 'simulated save failure'); END;
            """
        )
        with self.assertRaisesRegex(DeckAdoptionError, "Could not save"):
            self.service.adopt(self.source, "Rejected")
        self.assertEqual(
            self.database.conn_decks.execute("SELECT COUNT(*) FROM decks").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.database.conn_decks.execute("SELECT COUNT(*) FROM deck_lines").fetchone()[0],
            0,
        )

    def test_adopts_a_matching_player_controller_with_the_deck(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_deck = SimpleNamespace(
                id=self.source.source_id,
                name=self.source.source_name,
                cards=self.cards,
            )
            artifact = export_player_artifact(
                root / "source",
                {"controller": "winner"},
                source_deck,
                mission="deck-evolution",
                role="selected-deck",
                run_label="evolution-test",
                generation=40,
            )
            source_bytes = artifact.path.read_bytes()
            paired_source = AdoptableDeck(
                self.source.source_id,
                self.source.source_name,
                self.source.card_ids,
                self.source.source_label,
                str(artifact.manifest_path),
            )

            receipt = DeckAdoptionService(
                self.database, root / "library"
            ).adopt(paired_source, "Paired winner")

            adopted = load_player_artifact(Path(receipt.player_artifact_manifest))
            self.assertIsNotNone(adopted)
            self.assertEqual(adopted.manifest.deck_id, receipt.deck_id)
            self.assertEqual(adopted.manifest.deck_name, "Paired winner")
            self.assertEqual(adopted.manifest.card_ids, tuple(sorted(self.source.card_ids)))
            self.assertEqual(artifact.path.read_bytes(), source_bytes)

    def test_invalid_claimed_player_controller_rolls_back_the_deck(self):
        source = AdoptableDeck(
            self.source.source_id,
            self.source.source_name,
            self.source.card_ids,
            self.source.source_label,
            "/missing/controller.player.json",
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(DeckAdoptionError, "trained AI"):
                DeckAdoptionService(self.database, Path(directory)).adopt(
                    source, "Should roll back"
                )
        self.assertEqual(
            self.database.conn_decks.execute("SELECT COUNT(*) FROM decks").fetchone()[0],
            0,
        )


if __name__ == "__main__":
    unittest.main()
