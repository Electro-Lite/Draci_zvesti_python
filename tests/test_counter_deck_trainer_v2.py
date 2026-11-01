import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from neat_ai.composition_evolution import CompositionEvolutionSettings
from neat_ai.counter_deck_trainer import CounterDeckTrainerSettings
from neat_ai.counter_deck_trainer_v2 import train_counter_decks_v2
from utils.database_utils import DBUtil


class _FakeController:
    fitness = 1.0


class _FakePopulation:
    def __init__(self):
        self.controller = _FakeController()

    def run(self, evaluate, generations):
        for _ in range(generations):
            evaluate([(1, self.controller)], object())
        return self.controller


class CounterDeckTrainerV2Tests(unittest.TestCase):
    def test_direct_compositions_keep_counter_result_contract(self):
        subject = DBUtil().load_deck("Starter Blue_1")
        evolution = CompositionEvolutionSettings(
            population_size=4,
            elite_count=1,
            tournament_size=2,
            random_injection_rate=0.25,
        )
        settings = CounterDeckTrainerSettings(
            counter_generations=2,
            controller_generations=2,
            workers=1,
            evaluation_games=2,
            seed=321,
            run_label="counter-v2-test",
        )

        def completed_candidate_games(_function, jobs, _workers):
            for job in jobs:
                yield job[0], 120.0, "counter_win"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary_path = root / "summary.json"
            environment = {
                "TRAINING_ARTIFACT_DIR": str(root),
                "PLAYER_TRAINING_SUMMARY_PATH": str(summary_path),
            }
            with (
                patch.dict(os.environ, environment),
                patch(
                    "neat_ai.counter_deck_trainer_v2.neat.Config",
                    return_value=object(),
                ),
                patch(
                    "neat_ai.counter_deck_trainer_v2.neat.Population",
                    side_effect=(_FakePopulation(), _FakePopulation()),
                ),
                patch(
                    "neat_ai.counter_deck_trainer_v2._evaluate_controllers"
                ),
                patch(
                    "neat_ai.counter_deck_trainer_v2._bounded_results",
                    side_effect=completed_candidate_games,
                ),
                patch(
                    "neat_ai.counter_deck_trainer_v2.export_player_artifact",
                    return_value=SimpleNamespace(path=root / "subject.player.json"),
                ),
            ):
                summary = train_counter_decks_v2(subject, settings, evolution)

            persisted = json.loads(summary_path.read_text())
            artifact = Path(summary["artifact_path"])
            artifact_exists = artifact.exists()

        self.assertEqual(summary["optimizer"], "composition-ga-v2")
        self.assertEqual(persisted["optimizer"], "composition-ga-v2")
        self.assertEqual(len(summary["counter_matchups"]), 4)
        self.assertTrue(all(row["games"] == 2 for row in summary["counter_matchups"]))
        self.assertTrue(all(row["counter_wins"] == 2 for row in summary["counter_matchups"]))
        self.assertEqual(
            len({tuple(row["cards"]) for row in summary["counter_matchups"]}),
            4,
        )
        self.assertTrue(artifact_exists)


if __name__ == "__main__":
    unittest.main()
