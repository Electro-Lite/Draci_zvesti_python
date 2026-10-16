import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from py_game.evolution_presentation import load_evolution_presentation


class EvolutionPresentationTests(unittest.TestCase):
    def _create_databases(self, root: Path):
        training_path = root / "train.db"
        cards_path = root / "cards.db"
        connection = sqlite3.connect(training_path)
        connection.executescript(
            """
            CREATE TABLE training (id INTEGER PRIMARY KEY, end_date TEXT, metadata TEXT);
            CREATE TABLE genome (
                guid TEXT PRIMARY KEY, training_id INTEGER, deck_id TEXT,
                gen INTEGER, score REAL, pickle_path TEXT
            );
            CREATE TABLE ai_training_decks (
                id TEXT PRIMARY KEY, training_id INTEGER, name TEXT, signature TEXT
            );
            CREATE TABLE ai_training_deck_lines (
                deck_id TEXT, card_id TEXT, position INTEGER
            );
            CREATE TABLE match_dbt (
                guid TEXT PRIMARY KEY, genome_1 TEXT, deck_1 TEXT, deck_2 TEXT,
                gen INTEGER, result REAL
            );
            """
        )
        connection.execute(
            "INSERT INTO training VALUES (7, '2026-09-26', ?)",
            (json.dumps({"settings": {"run_label": "Evolution audit", "seed": 11, "outer_generations": 2, "evaluator_generations": 25}}),),
        )
        decks = (
            ("g1-a", 7, "G1 A", "sig-1a", "genome-1a", 1, -2.0),
            ("g1-b", 7, "G1 B", "sig-1b", "genome-1b", 1, 2.0),
            ("g2-a", 7, "G2 A", "sig-2a", "genome-2a", 2, 3.0),
            ("g2-b", 7, "G2 B", "sig-2b", "genome-2b", 2, 7.0),
        )
        for deck_id, training_id, name, signature, guid, generation, score in decks:
            connection.execute(
                "INSERT INTO ai_training_decks VALUES (?, ?, ?, ?)",
                (deck_id, training_id, name, signature),
            )
            connection.execute(
                "INSERT INTO genome VALUES (?, ?, ?, ?, ?, ?)",
                (
                    guid,
                    training_id,
                    deck_id,
                    generation,
                    score,
                    f"/artifacts/{deck_id}.pickle" if deck_id == "g2-b" else None,
                ),
            )
            card_ids = ["shared"] * 2 + [f"{deck_id}-card-{index}" for index in range(8)]
            connection.executemany(
                "INSERT INTO ai_training_deck_lines VALUES (?, ?, ?)",
                ((deck_id, card_id, index) for index, card_id in enumerate(card_ids)),
            )
        connection.executemany(
            "INSERT INTO match_dbt VALUES (?, ?, ?, ?, ?, ?)",
            (
                ("T7:1-vs-2:gen1", "genome-1a", "g1-a", "g1-b", 1, -0.75),
                ("T7:1-vs-2:gen2", "genome-2a", "g2-a", "g2-b", 2, 1.25),
            ),
        )
        connection.commit()
        connection.close()

        cards = sqlite3.connect(cards_path)
        cards.execute("CREATE TABLE cards (id TEXT PRIMARY KEY, name TEXT, color TEXT)")
        cards.execute("INSERT INTO cards VALUES ('shared', 'Shared card', 'RED')")
        cards.commit()
        cards.close()
        return training_path, cards_path

    def test_loads_every_stored_deck_and_keeps_scores_relative(self):
        with tempfile.TemporaryDirectory() as directory:
            training_path, cards_path = self._create_databases(Path(directory))
            result = load_evolution_presentation(training_path, cards_path, 7)

        self.assertEqual(result.run_label, "Evolution audit")
        self.assertEqual(result.requested_outer_generations, 2)
        self.assertEqual(len(result.decks), 4)
        self.assertEqual(result.coverage.stored_compositions, 4)
        self.assertEqual(result.coverage.scored_pairings, 2)
        self.assertEqual(result.default_deck_id, "g2-b")
        self.assertEqual(result.final_generation.average, 5.0)
        self.assertEqual(result.final_generation.spread, 4.0)
        self.assertEqual(result.deck("g2-a").card_ids.count("shared"), 2)
        self.assertEqual(
            result.deck("g2-b").player_artifact_path,
            "/artifacts/g2-b.pickle",
        )

    def test_matchup_perspective_is_reversed_for_the_second_deck(self):
        with tempfile.TemporaryDirectory() as directory:
            training_path, cards_path = self._create_databases(Path(directory))
            result = load_evolution_presentation(training_path, cards_path, 7)

        self.assertEqual(result.deck_matchups("g2-a")[0].relative_score, 1.25)
        self.assertEqual(result.deck_matchups("g2-b")[0].relative_score, -1.25)
        self.assertNotIn("win", result.deck_matchups("g2-a")[0].__dataclass_fields__)

    def test_card_signals_compare_first_and_final_generation_presence(self):
        with tempfile.TemporaryDirectory() as directory:
            training_path, cards_path = self._create_databases(Path(directory))
            result = load_evolution_presentation(training_path, cards_path, 7)

        shared = next(signal for signal in result.card_signals if signal.card_id == "shared")
        self.assertEqual((shared.first_presence, shared.first_total), (2, 2))
        self.assertEqual((shared.final_presence, shared.final_total), (2, 2))
        self.assertEqual(shared.first_mean_copies_when_present, 2.0)
        self.assertEqual(shared.final_mean_copies_when_present, 2.0)

    def test_optional_matchup_evidence_failure_keeps_population_results_available(self):
        with tempfile.TemporaryDirectory() as directory:
            training_path, cards_path = self._create_databases(Path(directory))
            connection = sqlite3.connect(training_path)
            connection.execute("DROP TABLE match_dbt")
            connection.commit()
            connection.close()

            result = load_evolution_presentation(training_path, cards_path, 7)

        self.assertEqual(len(result.generations), 2)
        self.assertEqual(len(result.decks), 4)
        self.assertEqual(result.coverage.scored_pairings, 0)
        self.assertTrue(
            any("matchup evidence is unavailable" in issue for issue in result.issues)
        )


if __name__ == "__main__":
    unittest.main()
