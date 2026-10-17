import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from py_game.training_lifecycle import (
    ArenaDestination,
    ResultArtifactStatus,
    arena_destination,
    eta_label,
    mission_progress_name,
    mission_result_label,
    overall_progress,
    progress_levels,
)
from py_game.training_service import (
    TrainingJob,
    TrainingKind,
    TrainingService,
    TrainingTelemetry,
)


def _job(root: Path, kind: TrainingKind, *, status="completed", request=None):
    values = {"kind": kind.value}
    values.update(request or {})
    return TrainingJob(
        job_id="test-run",
        request=values,
        command=["trainer"],
        created_at="2026-09-26T10:00:00",
        status=status,
        pid=None,
        log_path=str(root / "training.log"),
        progress_path=str(root / "progress.log"),
        summary_path=str(root / "summary.json"),
    )


class TrainingLifecycleTests(unittest.TestCase):
    def test_active_status_never_routes_to_results_even_at_100_percent(self):
        telemetry = TrainingTelemetry(
            status="running", phase_progress=1.0, generation=10, total_generations=10
        )
        self.assertEqual(overall_progress(telemetry), 0.99)
        self.assertEqual(
            arena_destination(
                "running",
                watched_live=False,
                results_opened=True,
                artifact=ResultArtifactStatus.available(),
            ),
            ArenaDestination.PROGRESS,
        )

    def test_watched_completion_requires_explicit_handoff(self):
        self.assertEqual(
            arena_destination(
                "completed",
                watched_live=True,
                results_opened=False,
                artifact=ResultArtifactStatus.available(),
            ),
            ArenaDestination.COMPLETION_HANDOFF,
        )
        self.assertEqual(
            arena_destination(
                "completed",
                watched_live=True,
                results_opened=True,
                artifact=ResultArtifactStatus.available(),
            ),
            ArenaDestination.RESULTS,
        )

    def test_later_completed_selection_routes_directly_when_artifact_is_ready(self):
        self.assertEqual(
            arena_destination(
                "completed",
                watched_live=False,
                results_opened=False,
                artifact=ResultArtifactStatus.available(),
            ),
            ArenaDestination.RESULTS,
        )

    def test_incomplete_terminal_states_never_route_to_results(self):
        for status in ("failed", "stopped", "cancelled", "interrupted", "incomplete"):
            with self.subTest(status=status):
                self.assertEqual(
                    arena_destination(
                        status,
                        watched_live=False,
                        results_opened=True,
                        artifact=ResultArtifactStatus.available(),
                    ),
                    ArenaDestination.TERMINAL,
                )

    def test_eta_uses_only_fresh_reported_evidence(self):
        self.assertEqual(
            eta_label(
                TrainingTelemetry(status="running", eta_seconds=90, telemetry_age_seconds=10),
                lambda seconds: f"{round(seconds)} sec",
            ),
            "About 90 sec",
        )
        for telemetry in (
            TrainingTelemetry(status="running"),
            TrainingTelemetry(status="running", eta_seconds=90, telemetry_age_seconds=121),
        ):
            self.assertEqual(eta_label(telemetry, str), "Estimating…")

    def test_progress_hierarchy_uses_real_mission_identifiers(self):
        telemetry = TrainingTelemetry(
            status="running",
            phase="counter_evolution",
            generation=2,
            total_generations=5,
            round_completed=300,
            round_total=1000,
        )
        rows = progress_levels(TrainingKind.PLAYER_DECK.value, telemetry)
        self.assertEqual(rows[0][0], "Counter generations")
        self.assertEqual(rows[1][0], "Current candidate validation")
        self.assertEqual(mission_progress_name(TrainingKind.DECK_BUILDER.value), "Deck evolution")
        self.assertEqual(mission_result_label(TrainingKind.MATCHUP_EVALUATION.value), "Duel results")

    def test_counter_artifact_waits_for_file_and_rejects_invalid_evidence(self):
        service = TrainingService.__new__(TrainingService)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = _job(root, TrainingKind.PLAYER_DECK)
            self.assertEqual(service.result_artifact_status(job).state, "preparing")
            Path(job.summary_path).write_text("{")
            self.assertEqual(service.result_artifact_status(job).state, "preparing")
            Path(job.summary_path).write_text(json.dumps({"counter_matchups": []}))
            self.assertEqual(service.result_artifact_status(job).state, "invalid")
            Path(job.summary_path).write_text(
                json.dumps(
                    {
                        "counter_matchups": [
                            {
                                "cards": [f"card-{index}" for index in range(10)],
                                "games": 1000,
                                "counter_wins": 510,
                                "draws": 90,
                                "subject_wins": 400,
                            }
                        ]
                    }
                )
            )
            self.assertTrue(service.result_artifact_status(job).ready)

    def test_matchup_artifact_requires_requested_final_checkpoint(self):
        service = TrainingService.__new__(TrainingService)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = _job(
                root,
                TrainingKind.MATCHUP_EVALUATION,
                request={"evaluator_generations": 40},
            )
            Path(job.summary_path).write_text(
                json.dumps(
                    {
                        "skill_evaluations": [
                            {
                                "generation": 25,
                                "games": 1000,
                                "deck_1_wins": 450,
                                "draws": 100,
                                "deck_2_wins": 450,
                            }
                        ]
                    }
                )
            )
            self.assertEqual(service.result_artifact_status(job).state, "invalid")
            data = json.loads(Path(job.summary_path).read_text())
            data["skill_evaluations"].append(
                {
                    "generation": 40,
                    "games": 1000,
                    "deck_1_wins": 475,
                    "draws": 50,
                    "deck_2_wins": 475,
                }
            )
            Path(job.summary_path).write_text(json.dumps(data))
            self.assertTrue(service.result_artifact_status(job).ready)

    def test_evolution_artifact_waits_for_database_finalization(self):
        service = TrainingService.__new__(TrainingService)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "train.db"
            connection = sqlite3.connect(database_path)
            connection.executescript(
                """
                CREATE TABLE training (id INTEGER PRIMARY KEY, end_date TEXT);
                CREATE TABLE genome (training_id INTEGER);
                CREATE TABLE ai_training_decks (training_id INTEGER);
                INSERT INTO training VALUES (7, NULL);
                """
            )
            connection.commit()
            job = _job(root, TrainingKind.DECK_BUILDER)
            Path(job.progress_path).write_text("training_id: 7\n")
            with patch("py_game.training_service.TRAIN_DB_PATH", database_path):
                self.assertEqual(service.result_artifact_status(job).state, "preparing")
                connection.execute(
                    "UPDATE training SET end_date='2026-09-26' WHERE id=7"
                )
                connection.execute("INSERT INTO genome VALUES (7)")
                connection.execute("INSERT INTO ai_training_decks VALUES (7)")
                connection.commit()
                self.assertTrue(service.result_artifact_status(job).ready)
            connection.close()


if __name__ == "__main__":
    unittest.main()
