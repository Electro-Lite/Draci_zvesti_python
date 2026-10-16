import json
import tempfile
import unittest
from pathlib import Path

from neat_ai.player_trainer import (
    CounterDeckTrainerSettings,
    build_summary,
    controller_generation_targets,
)
from neat_ai.matchup_trainer import (
    MatchupTrainerSettings,
    build_summary as build_matchup_summary,
    evaluator_settings,
)
from py_game.training_service import (
    TrainingJob,
    TrainingKind,
    TrainingService,
)


class _Card:
    def __init__(self, card_id):
        self.id = card_id


class _Deck:
    id = "subject"
    name = "Subject deck"
    cards = tuple(_Card(f"card-{index}") for index in range(10))


class TrainingMissionTests(unittest.TestCase):
    def test_controller_targets_preserve_one_cumulative_training_run(self):
        self.assertEqual(controller_generation_targets(5, 40), (8, 16, 24, 32, 40))
        self.assertEqual(controller_generation_targets(3, 10), (4, 7, 10))

    def test_counter_settings_require_seat_balanced_evaluations(self):
        with self.assertRaisesRegex(ValueError, "even number"):
            CounterDeckTrainerSettings(evaluation_games=3)

    def test_counter_summary_aggregates_final_population_and_finds_top_counter(self):
        settings = CounterDeckTrainerSettings(evaluation_games=20)
        history = [
            {
                "generation": 1,
                "subject_wins": 8,
                "draws": 2,
                "counter_wins": 10,
                "candidates": [],
            },
            {
                "generation": 2,
                "subject_wins": 17,
                "draws": 3,
                "counter_wins": 20,
                "candidates": [
                    {
                        "deck_name": "Counter A",
                        "subject_wins": 10,
                        "draws": 2,
                        "counter_wins": 8,
                        "counter_win_rate": 0.4,
                        "counter_fitness": 2.0,
                    },
                    {
                        "deck_name": "Counter B",
                        "subject_wins": 7,
                        "draws": 1,
                        "counter_wins": 12,
                        "counter_win_rate": 0.6,
                        "counter_fitness": 4.0,
                    },
                ],
            },
        ]

        result = build_summary(_Deck(), settings, history, 12.5)

        self.assertEqual(result["evaluation"]["ai_wins"], 17)
        self.assertEqual(result["evaluation"]["random_wins"], 20)
        self.assertEqual(result["top_counter"]["deck_name"], "Counter B")
        self.assertEqual(len(result["skill_evaluations"]), 2)

    def test_matchup_settings_include_generation_one_and_final_checkpoints(self):
        settings = MatchupTrainerSettings(generations=40, evaluation_games=20)
        evaluator = evaluator_settings(settings)

        self.assertEqual(evaluator.early_holdout_generation, 1)
        self.assertEqual(evaluator.diagnostic_holdout_generations, (1, 10, 25))
        self.assertEqual(evaluator.holdout_seed_pairs, 10)

    def test_matchup_summary_can_persist_a_partial_checkpoint(self):
        settings = MatchupTrainerSettings(generations=40, evaluation_games=20)
        deck_a = type(
            "Deck", (), {"id": "a", "name": "Deck A", "cards": _Deck.cards}
        )()
        deck_b = type(
            "Deck", (), {"id": "b", "name": "Deck B", "cards": _Deck.cards}
        )()
        checkpoint = {
            "generation": 1,
            "ai_wins": 9,
            "draws": 3,
            "random_wins": 8,
            "deck_1_wins": 9,
            "deck_2_wins": 8,
            "games": 20,
            "deck_1_fitness": 4.0,
            "deck_2_fitness": 3.0,
        }

        result = build_matchup_summary(
            deck_a,
            deck_b,
            settings,
            [checkpoint],
            5.0,
        )

        self.assertEqual(result["evaluation"]["ai_wins"], 9)
        self.assertEqual(result["skill_evaluations"], [checkpoint])
        self.assertEqual(result["best_fitness"], 4.0)
        self.assertEqual(len(result["deck_1_cards"]), 10)
        self.assertEqual(result["deck_1_cards"][0]["id"], "card-0")

    def test_counter_job_insights_expose_top_counter(self):
        service = TrainingService.__new__(TrainingService)
        service._processes = {}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "summary.json"
            summary.write_text(
                json.dumps(
                    {
                        "deck_name": "Subject deck",
                        "evaluation": {
                            "ai_wins": 17,
                            "draws": 3,
                            "random_wins": 20,
                        },
                        "skill_evaluations": [
                            {"generation": 1, "ai_wins": 8, "draws": 2, "random_wins": 10},
                            {"generation": 2, "ai_wins": 17, "draws": 3, "random_wins": 20},
                        ],
                        "top_counter": {
                            "deck_name": "Counter B",
                            "counter_win_rate": 0.6,
                        },
                        "counter_matchups": [{}, {}],
                    }
                )
            )
            job = TrainingJob(
                job_id="counter-job",
                request={"kind": TrainingKind.PLAYER_DECK.value},
                command=["trainer"],
                created_at="now",
                status="completed",
                pid=None,
                log_path=str(root / "training.log"),
                progress_path=str(root / "progress.log"),
                summary_path=str(summary),
            )

            insights = service.job_insights(job)

        self.assertEqual(insights.opponent, "2 evolved counter decks")
        self.assertEqual(insights.top_counter_name, "Counter B")
        self.assertEqual(insights.top_counter_win_rate, 0.6)
        self.assertIsNotNone(insights.counter)
        self.assertEqual(len(insights.counter.candidates), 2)
        self.assertTrue(any("persisted" in line for line in insights.conclusions))


if __name__ == "__main__":
    unittest.main()
