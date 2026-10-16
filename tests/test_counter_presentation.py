import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from py_game.counter_presentation import (
    COMPARISON_TARGET,
    CounterCandidate,
    CounterDeckSnapshot,
    counter_bar_segments,
    load_counter_presentation,
)
from py_game.ui.counter_dashboard import counter_dashboard_layout
from py_game.ui.layout import LayoutMetrics


class CounterPresentationTests(unittest.TestCase):
    @staticmethod
    def _card_loader(card_id):
        values = {
            "archer": ("Current Archer", "BLUE"),
            "guard": ("Guard", "BLACK"),
            "page": ("Page", "RED"),
        }
        value = values.get(card_id)
        if value is None:
            return None
        return SimpleNamespace(
            id=card_id,
            name=value[0],
            color=SimpleNamespace(name=value[1]),
        )

    @staticmethod
    def _job(root, summary=None, **request):
        path = Path(root) / "summary.json"
        if summary is not None:
            path.write_text(json.dumps(summary))
        return SimpleNamespace(
            summary_path=str(path),
            request={
                "deck_id": "subject",
                "outer_generations": 2,
                "evaluator_generations": 10,
                "evaluation_games": 1_000,
                **request,
            },
        )

    @staticmethod
    def _candidate(
        builder_id,
        *,
        wins=16,
        draws=2,
        losses=2,
        fitness=5.0,
        cards=("archer", "archer", "guard"),
    ):
        return {
            "builder_id": builder_id,
            "deck_id": f"counter-{builder_id}",
            "deck_name": f"Counter #{builder_id}",
            "generation": 1,
            "cards": list(cards),
            "card_names": ["Saved Archer", "Saved Archer", "Saved Guard"],
            "games": wins + draws + losses,
            "counter_wins": wins,
            "draws": draws,
            "subject_wins": losses,
            "counter_win_rate": 0.01,
            "counter_fitness": fitness,
            "shared_cards": 2,
        }

    def test_candidate_results_snapshots_and_workload_stay_separate_from_pool(self):
        first = self._candidate(1, fitness=5.0)
        second = self._candidate(2, fitness=9.0)
        summary = {
            "deck_id": "subject",
            "deck_name": "Subject deck",
            "subject_cards": ["archer", "archer", "page"],
            "settings": {
                "counter_generations": 2,
                "controller_generations": 10,
                "evaluation_games": 1_000,
            },
            "counter_matchups": [first, second],
            "top_counter": second,
            "evaluation": {
                "games": 40,
                "subject_wins": 8,
                "draws": 4,
                "counter_wins": 28,
            },
            "skill_evaluations": [
                {"generation": 1, "games": 40},
            ],
        }
        with tempfile.TemporaryDirectory() as root:
            detail = load_counter_presentation(
                self._job(root, summary),
                self._card_loader,
                completed_counter_generations=1,
                builder_population_size=20,
                controller_population_size=15,
            )

        selected = detail.candidate(detail.default_candidate_key)
        self.assertEqual(selected.deck.name, "Counter #2")
        self.assertEqual(selected.counter_win_rate, 0.8)
        self.assertEqual(selected.games, 20)
        self.assertTrue(selected.exploratory)
        self.assertEqual(COMPARISON_TARGET, 1_000)
        self.assertEqual(detail.pooled_counter_wins, 28)
        self.assertEqual(selected.counter_wins, 16)
        self.assertEqual(detail.subject.cards[0].copies, 2)
        self.assertEqual(detail.subject.cards[0].name, "Current Archer")
        self.assertEqual(selected.deck.cards[0].name, "Saved Archer")
        self.assertEqual(selected.shared_cards, 2)
        self.assertEqual(detail.workload.final_candidate_count, 2)
        self.assertEqual(detail.workload.planned_validation_games, 40_000)
        self.assertEqual(detail.workload.recorded_validation_games, 40)
        self.assertEqual(detail.workload.planned_learning_games, 2_250)
        self.assertEqual(detail.workload.completed_learning_games_estimate, 1_125)

    def test_default_falls_back_to_rate_then_fitness_tie_break(self):
        low_fitness = self._candidate(1, fitness=3.0)
        high_fitness = self._candidate(2, fitness=7.0)
        summary = {
            "subject_cards": ["archer", "archer", "page"],
            "counter_matchups": [low_fitness, high_fitness],
        }
        with tempfile.TemporaryDirectory() as root:
            detail = load_counter_presentation(
                self._job(root, summary),
                self._card_loader,
                builder_population_size=20,
                controller_population_size=15,
            )

        self.assertEqual(detail.candidate(detail.default_candidate_key).builder_id, "2")

    def test_actual_candidate_rows_are_never_truncated_to_configured_population(self):
        summary = {
            "subject_cards": ["archer"],
            "counter_matchups": [self._candidate(index) for index in range(21)],
        }
        with tempfile.TemporaryDirectory() as root:
            detail = load_counter_presentation(
                self._job(root, summary, outer_generations=1),
                self._card_loader,
                builder_population_size=20,
                controller_population_size=15,
            )

        self.assertEqual(len(detail.candidates), 21)
        self.assertEqual(detail.workload.final_candidate_count, 21)
        self.assertEqual(detail.workload.planned_validation_games, 20_000)
        self.assertEqual(detail.workload.recorded_validation_games, 420)

    def test_missing_metadata_keeps_saved_name_or_card_id(self):
        row = self._candidate(1, cards=("missing", "missing", "guard"))
        row["card_names"] = ["Saved Missing", "Saved Missing", "Saved Guard"]
        summary = {"subject_cards": ["unknown"], "counter_matchups": [row]}
        with tempfile.TemporaryDirectory() as root:
            detail = load_counter_presentation(
                self._job(root, summary),
                self._card_loader,
                builder_population_size=20,
                controller_population_size=15,
            )

        self.assertEqual(detail.subject.cards[0].name, "unknown")
        self.assertEqual(detail.candidates[0].deck.cards[0].name, "Saved Missing")
        self.assertEqual(detail.candidates[0].deck.cards[0].copies, 2)

    def test_zero_or_malformed_candidate_has_no_rate(self):
        row = self._candidate(1, wins=0, draws=0, losses=0)
        row["games"] = 0
        summary = {"subject_cards": ["archer"], "counter_matchups": [row]}
        with tempfile.TemporaryDirectory() as root:
            detail = load_counter_presentation(
                self._job(root, summary),
                self._card_loader,
                builder_population_size=20,
                controller_population_size=15,
            )

        self.assertFalse(detail.candidates[0].valid)
        self.assertIsNone(detail.candidates[0].counter_win_rate)

    def test_bar_segments_cover_all_games_and_externalize_zero_or_narrow_labels(self):
        candidate = CounterCandidate(
            key="one",
            builder_id="1",
            deck=CounterDeckSnapshot("one", "One"),
            generation=1,
            games=1_000,
            counter_wins=995,
            draws=5,
            subject_wins=0,
            counter_fitness=1.0,
            shared_cards=0,
            valid=True,
        )

        segments = counter_bar_segments(candidate)

        self.assertAlmostEqual(sum(segment.ratio for segment in segments), 1.0)
        self.assertTrue(segments[0].inline_label)
        self.assertFalse(segments[1].inline_label)
        self.assertFalse(segments[2].inline_label)
        self.assertEqual([segment.count for segment in segments], [995, 5, 0])

    def test_no_summary_is_an_honest_empty_state(self):
        with tempfile.TemporaryDirectory() as root:
            detail = load_counter_presentation(
                self._job(root),
                self._card_loader,
                builder_population_size=20,
                controller_population_size=15,
            )

        self.assertFalse(detail.summary_available)
        self.assertEqual(detail.candidates, ())
        self.assertEqual(detail.subject.cards, ())
        self.assertIsNone(detail.default_candidate_key)


class CounterDashboardLayoutTests(unittest.TestCase):
    def test_wide_layout_has_three_nonoverlapping_columns(self):
        for size in ((1600, 900), (1280, 720)):
            layout = counter_dashboard_layout(
                LayoutMetrics.from_size(*size),
                subject_rows=5,
                counter_rows=8,
            )
            self.assertEqual(layout.mode, "wide")
            self.assertLessEqual(layout.subject.right, layout.result.x)
            self.assertLessEqual(layout.result.right, layout.counter.x)
            self.assertLessEqual(layout.result.bottom, layout.candidates.y)
            self.assertLessEqual(layout.viewport.bottom, layout.footer.y)

    def test_compact_layout_preserves_required_reading_order(self):
        metrics = LayoutMetrics.from_size(640, 480)
        initial = counter_dashboard_layout(
            metrics, subject_rows=10, counter_rows=12
        )
        bottom = counter_dashboard_layout(
            metrics,
            subject_rows=10,
            counter_rows=12,
            scroll=initial.max_scroll,
        )

        self.assertEqual(initial.mode, "compact")
        self.assertLessEqual(initial.subject.bottom, initial.result.y)
        self.assertLessEqual(initial.result.bottom, initial.candidates.y)
        self.assertLessEqual(initial.candidates.bottom, initial.counter.y)
        self.assertGreater(initial.max_scroll, 0)
        self.assertLessEqual(bottom.counter.bottom, bottom.viewport.bottom)


if __name__ == "__main__":
    unittest.main()
