import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from py_game.matchup_presentation import load_matchup_presentation
from py_game.ui.layout import LayoutMetrics
from py_game.ui.matchup_dashboard import matchup_dashboard_layout


def _deck(deck_id, name, cards):
    return SimpleNamespace(
        id=deck_id,
        name=name,
        cards=[
            SimpleNamespace(id=card_id, name=card_name, color=SimpleNamespace(name=color))
            for card_id, card_name, color in cards
        ],
    )


class MatchupPresentationTests(unittest.TestCase):
    def _job(self, root, summary=None, **request):
        path = Path(root) / "summary.json"
        if summary is not None:
            path.write_text(json.dumps(summary))
        return SimpleNamespace(
            summary_path=str(path),
            request={
                "deck_id": "a",
                "opponent_deck_id": "b",
                "evaluator_generations": 40,
                "evaluation_games": 100,
                **request,
            },
        )

    @staticmethod
    def _loader(deck_id):
        decks = {
            "a": _deck(
                "a",
                "Azure Guard",
                (("archer", "Archer", "BLUE"), ("archer", "Archer", "BLUE"), ("page", "Page", "RED")),
            ),
            "b": _deck("b", "Red Choir", (("guard", "Guard", "BLACK"),)),
        }
        return decks.get(deck_id)

    def test_parses_explicit_perspectives_rates_and_configuration_workload(self):
        summary = {
            "deck_id": "a",
            "deck_name": "Old A name",
            "opponent_deck_id": "b",
            "opponent_deck_name": "Old B name",
            "skill_evaluations": [
                {
                    "generation": 40,
                    "games": 100,
                    "deck_1_wins": 53,
                    "draws": 14,
                    "deck_2_wins": 33,
                    "ai_wins": 1,
                    "random_wins": 99,
                },
                {
                    "generation": 1,
                    "games": 100,
                    "deck_1_wins": 38,
                    "draws": 12,
                    "deck_2_wins": 50,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as root:
            detail = load_matchup_presentation(
                self._job(root, summary), self._loader, population_size=15
            )

        self.assertEqual([row.generation for row in detail.checkpoints], [1, 40])
        self.assertEqual(detail.final_checkpoint.rates, (0.53, 0.14, 0.33))
        self.assertEqual(detail.deck_a.name, "Azure Guard")
        self.assertEqual(detail.deck_a.cards[0].copies, 2)
        self.assertEqual(detail.workload.games_per_genome_per_generation, 15)
        self.assertEqual(detail.workload.learning_games_per_generation, 225)
        self.assertEqual(detail.workload.planned_learning_games, 9000)
        self.assertEqual(detail.workload.planned_evaluation_games, 400)
        self.assertEqual(detail.workload.planned_total_games, 9400)

    def test_malformed_and_zero_game_rows_never_create_percentages_or_final(self):
        summary = {
            "skill_evaluations": [
                {"generation": 1, "games": 0, "deck_1_wins": 0, "draws": 0, "deck_2_wins": 0},
                {"generation": 40, "games": 20, "deck_1_wins": 12, "draws": 3, "deck_2_wins": 4},
            ]
        }
        with tempfile.TemporaryDirectory() as root:
            detail = load_matchup_presentation(
                self._job(root, summary), self._loader, population_size=15
            )

        self.assertIsNone(detail.checkpoints[0].rates)
        self.assertIsNone(detail.checkpoints[1].rates)
        self.assertIsNone(detail.final_checkpoint)
        self.assertTrue(any("final checkpoint" in issue for issue in detail.issues))

    def test_missing_summary_and_deck_lookup_have_explicit_empty_states(self):
        with tempfile.TemporaryDirectory() as root:
            detail = load_matchup_presentation(
                self._job(root), lambda _deck_id: None, population_size=15
            )

        self.assertFalse(detail.summary_available)
        self.assertFalse(detail.deck_a.composition_available)
        self.assertFalse(detail.deck_b.composition_available)
        self.assertEqual(detail.checkpoints, ())
        self.assertEqual(detail.next_checkpoint_generation, 1)

    def test_incomplete_card_metadata_does_not_show_a_partial_composition(self):
        incomplete = _deck("a", "Incomplete deck", (("known", "Known", "BLUE"),))
        with tempfile.TemporaryDirectory() as root:
            detail = load_matchup_presentation(
                self._job(root, {}),
                lambda deck_id: incomplete if deck_id == "a" else self._loader(deck_id),
                population_size=15,
                expected_card_count=lambda deck_id: 2 if deck_id == "a" else 1,
            )

        self.assertFalse(detail.deck_a.composition_available)
        self.assertEqual(detail.deck_a.cards, ())

    def test_identical_deck_ids_keep_separate_a_and_b_perspectives(self):
        calls = []

        def loader(deck_id):
            calls.append(deck_id)
            return self._loader("a")

        with tempfile.TemporaryDirectory() as root:
            job = self._job(root, {}, opponent_deck_id="a")
            detail = load_matchup_presentation(job, loader, population_size=15)

        self.assertEqual(calls, ["a", "a"])
        self.assertEqual(detail.deck_a.deck_id, detail.deck_b.deck_id)
        self.assertIsNot(detail.deck_a, detail.deck_b)

    def test_saved_compositions_take_precedence_over_a_changed_live_deck(self):
        summary = {
            "deck_id": "a",
            "deck_name": "Snapshot A",
            "opponent_deck_id": "b",
            "opponent_deck_name": "Snapshot B",
            "deck_1_cards": [
                {"id": "old", "name": "Saved card", "color": "Blue"}
            ] * 10,
            "deck_2_cards": [
                {"id": "rival", "name": "Saved rival", "color": "Red"}
            ] * 10,
        }
        with tempfile.TemporaryDirectory() as root:
            detail = load_matchup_presentation(
                self._job(root, summary), self._loader, population_size=15
            )

        self.assertEqual(detail.deck_a.name, "Snapshot A")
        self.assertEqual(detail.deck_a.cards[0].card_id, "old")
        self.assertEqual(detail.deck_a.cards[0].copies, 10)
        self.assertEqual(detail.deck_b.cards[0].card_id, "rival")


class MatchupDashboardLayoutTests(unittest.TestCase):
    def test_wide_layout_uses_nonoverlapping_columns_and_scrolls_all_evidence(self):
        for size in ((1600, 900), (1280, 720)):
            layout = matchup_dashboard_layout(
                LayoutMetrics.from_size(*size), deck_rows=24, checkpoint_rows=8
            )
            self.assertEqual(layout.mode, "wide")
            self.assertLessEqual(layout.decks.right, layout.checkpoints.x)
            self.assertLessEqual(layout.checkpoints.right, layout.reading.x)
            self.assertLessEqual(layout.viewport.bottom, layout.footer.y)
            self.assertGreater(layout.max_scroll, 0)

    def test_compact_layout_stacks_sections_and_reaches_the_last_section(self):
        metrics = LayoutMetrics.from_size(640, 480)
        initial = matchup_dashboard_layout(
            metrics, deck_rows=12, checkpoint_rows=4
        )
        scrolled = matchup_dashboard_layout(
            metrics,
            deck_rows=12,
            checkpoint_rows=4,
            scroll=initial.max_scroll,
        )

        self.assertEqual(initial.mode, "compact")
        self.assertLessEqual(initial.decks.bottom, initial.checkpoints.y)
        self.assertLessEqual(initial.checkpoints.bottom, initial.reading.y)
        self.assertGreater(initial.max_scroll, 0)
        self.assertLessEqual(scrolled.reading.bottom, scrolled.viewport.bottom)


if __name__ == "__main__":
    unittest.main()
