from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRAIN_DB_PATH = PROJECT_ROOT / "train.db"
JOB_ROOT = PROJECT_ROOT / ".ui_training"


class TrainingKind(Enum):
    DECK_BUILDER = "Deck builder experiment"
    PLAYER_DECK = "Specific deck player"


@dataclass
class TrainingRequest:
    kind: TrainingKind = TrainingKind.PLAYER_DECK
    run_label: str = "pygame"
    deck_id: str | None = None
    seeds: tuple[int, ...] = (104729,)
    outer_generations: int = 1
    matches_per_genome: int = 12
    evaluator_generations: int = 50
    workers: int = 12
    holdout_seed_pairs: int = 20
    evaluation_games: int = 100

    def validate(self) -> None:
        if not self.run_label.strip():
            raise ValueError("Run label cannot be empty")
        if self.workers < 1:
            raise ValueError("Workers must be positive")
        if self.evaluator_generations < 1:
            raise ValueError("Generations must be positive")
        if self.kind == TrainingKind.PLAYER_DECK and not self.deck_id:
            raise ValueError("Select the player deck to analyze")
        if self.kind == TrainingKind.DECK_BUILDER:
            if not self.seeds:
                raise ValueError("At least one seed is required")
            if self.matches_per_genome < 2 or self.matches_per_genome % 2:
                raise ValueError("Matches per genome must be a positive even number")


@dataclass
class TrainingJob:
    job_id: str
    request: dict
    command: list[str]
    created_at: str
    status: str
    pid: int | None
    log_path: str
    progress_path: str
    summary_path: str
    return_code: int | None = None


@dataclass(frozen=True)
class TrainingRunSummary:
    run_id: str
    title: str
    status: str
    started: str
    detail: str
    best_score: float | None = None
    best_deck_id: str | None = None


def _safe_label(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", label.strip()).strip("-")
    return cleaned or "pygame"


def build_command(request: TrainingRequest) -> list[str]:
    request.validate()
    if request.kind == TrainingKind.DECK_BUILDER:
        return [
            sys.executable,
            "-m",
            "neat_ai.deck_builder_trainer",
            "--run-label",
            request.run_label,
            "--seeds",
            *[str(seed) for seed in request.seeds],
            "--outer-generations",
            str(request.outer_generations),
            "--max-matches-per-genome",
            str(request.matches_per_genome),
            "--outer-workers",
            "2",
            "--evaluator-generations",
            str(request.evaluator_generations),
            "--evaluator-workers",
            str(request.workers),
            "--holdout-seed-pairs",
            str(request.holdout_seed_pairs),
        ]
    return [
        sys.executable,
        "-m",
        "neat_ai.player_trainer",
        str(request.deck_id),
        "--generations",
        str(request.evaluator_generations),
        "--workers",
        str(request.workers),
        "--evaluation-games",
        str(request.evaluation_games),
        "--run-label",
        request.run_label,
    ]


def unfinished_database_run() -> int | None:
    if not TRAIN_DB_PATH.exists():
        return None
    connection = sqlite3.connect(
        f"file:{TRAIN_DB_PATH}?mode=ro",
        uri=True,
        timeout=1.0,
    )
    try:
        row = connection.execute(
            "SELECT id FROM training WHERE end_date IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return int(row[0]) if row else None
    finally:
        connection.close()


class TrainingService:
    def __init__(self):
        JOB_ROOT.mkdir(parents=True, exist_ok=True)
        self._processes: dict[str, subprocess.Popen] = {}

    def _job_path(self, job_id: str) -> Path:
        return JOB_ROOT / job_id / "job.json"

    def _save_job(self, job: TrainingJob) -> None:
        path = self._job_path(job.job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(job), indent=2, sort_keys=True))

    def start(self, request: TrainingRequest) -> TrainingJob:
        request.validate()
        active_run = unfinished_database_run()
        if active_run is not None:
            raise RuntimeError(
                f"Training database run {active_run} is still active"
            )
        active_jobs = [job for job in self.jobs() if job.status == "running"]
        if active_jobs:
            raise RuntimeError(f"UI training job {active_jobs[0].job_id} is running")

        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        job_id = f"{stamp}-{_safe_label(request.run_label)}"
        job_dir = JOB_ROOT / job_id
        suffix = 2
        while job_dir.exists():
            job_id = f"{stamp}-{_safe_label(request.run_label)}-{suffix}"
            job_dir = JOB_ROOT / job_id
            suffix += 1
        job_dir.mkdir(parents=True)

        command = build_command(request)
        log_path = job_dir / "training.log"
        progress_path = job_dir / "progress.log"
        summary_path = job_dir / "summary.json"
        environment = os.environ.copy()
        environment["TRAINING_PROGRESS_PATH"] = str(progress_path)
        environment["TRAINING_ARTIFACT_DIR"] = str(job_dir)
        environment["PLAYER_TRAINING_SUMMARY_PATH"] = str(summary_path)
        log_file = log_path.open("w")
        try:
            process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                env=environment,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            log_file.close()

        job = TrainingJob(
            job_id=job_id,
            request={
                **asdict(request),
                "kind": request.kind.value,
                "seeds": list(request.seeds),
            },
            command=command,
            created_at=dt.datetime.now().isoformat(timespec="seconds"),
            status="running",
            pid=process.pid,
            log_path=str(log_path),
            progress_path=str(progress_path),
            summary_path=str(summary_path),
        )
        self._processes[job_id] = process
        self._save_job(job)
        return job

    def _load_job(self, path: Path) -> TrainingJob | None:
        try:
            return TrainingJob(**json.loads(path.read_text()))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def refresh(self, job: TrainingJob) -> TrainingJob:
        if job.status != "running":
            return job
        process = self._processes.get(job.job_id)
        if process is not None:
            return_code = process.poll()
            alive = return_code is None
        else:
            return_code = None
            try:
                os.kill(int(job.pid), 0)
                alive = True
            except (OSError, TypeError, ValueError):
                alive = False
        if not alive:
            job.return_code = return_code
            if return_code is None:
                job_dir = self._job_path(job.job_id).parent
                has_artifact = Path(job.summary_path).exists() or any(
                    (job_dir / "trained_ai").glob("*.pickle")
                )
                job.status = "completed" if has_artifact else "failed"
            else:
                job.status = "completed" if return_code == 0 else "failed"
            self._save_job(job)
        return job

    def jobs(self) -> list[TrainingJob]:
        jobs = []
        for path in sorted(JOB_ROOT.glob("*/job.json"), reverse=True):
            job = self._load_job(path)
            if job is not None:
                jobs.append(self.refresh(job))
        return jobs

    def recent_database_runs(self, limit: int = 20) -> list[TrainingRunSummary]:
        if not TRAIN_DB_PATH.exists():
            return []
        connection = sqlite3.connect(
            f"file:{TRAIN_DB_PATH}?mode=ro",
            uri=True,
            timeout=2.0,
        )
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT t.id, t.start_date, t.end_date, t.metadata,
                       MAX(g.score) AS best_score,
                       (SELECT g2.deck_id FROM genome g2
                        WHERE g2.training_id = t.id
                        ORDER BY g2.score DESC LIMIT 1) AS best_deck_id,
                       COUNT(g.guid) AS genome_count,
                       MAX(g.gen) AS max_generation
                FROM training t
                LEFT JOIN genome g ON g.training_id = t.id
                GROUP BY t.id
                ORDER BY t.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()

        summaries = []
        for row in rows:
            settings = {}
            termination = None
            try:
                metadata = json.loads(row["metadata"] or "{}")
                settings = metadata.get("settings", {})
                termination = metadata.get("termination_reason")
            except (TypeError, json.JSONDecodeError):
                pass
            status = "running" if row["end_date"] is None else "completed"
            if termination and str(termination).startswith("failed"):
                status = "failed"
            label = settings.get("run_label") or "deck builder"
            detail = (
                f"{row['genome_count']} genomes, generation "
                f"{row['max_generation'] or 0}"
            )
            summaries.append(
                TrainingRunSummary(
                    run_id=f"DB {row['id']}",
                    title=str(label),
                    status=status,
                    started=str(row["start_date"]),
                    detail=detail,
                    best_score=row["best_score"],
                    best_deck_id=row["best_deck_id"],
                )
            )
        return summaries

    @staticmethod
    def tail(path: str, max_lines: int = 12) -> list[str]:
        try:
            with Path(path).open(errors="replace") as log_file:
                return [line.rstrip() for line in log_file.readlines()[-max_lines:]]
        except OSError:
            return []
