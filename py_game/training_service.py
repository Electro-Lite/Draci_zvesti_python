from __future__ import annotations

import datetime as dt
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
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
    opponent_deck_id: str | None = None
    seeds: tuple[int, ...] = (104729,)
    outer_generations: int = 1
    matches_per_genome: int = 12
    evaluator_generations: int = 50
    workers: int = 12
    holdout_seed_pairs: int = 20
    evaluation_games: int = 100

    def validate(self) -> None:
        if not isinstance(self.run_label, str) or not self.run_label.strip():
            raise ValueError("Run label cannot be empty")
        if len(self.run_label.strip()) > 64:
            raise ValueError("Run label must contain at most 64 characters")
        if not isinstance(self.workers, int) or not 1 <= self.workers <= 128:
            raise ValueError("Workers must be between 1 and 128")
        if (
            not isinstance(self.evaluator_generations, int)
            or not 1 <= self.evaluator_generations <= 10_000
        ):
            raise ValueError("Generations must be between 1 and 10000")
        if self.kind == TrainingKind.PLAYER_DECK and not self.deck_id:
            raise ValueError("Select the player deck to analyze")
        if self.kind == TrainingKind.DECK_BUILDER:
            if not self.seeds:
                raise ValueError("At least one seed is required")
            if any(not isinstance(seed, int) for seed in self.seeds):
                raise ValueError("Every seed must be an integer")
            if not isinstance(self.outer_generations, int) or not 1 <= self.outer_generations <= 1_000:
                raise ValueError("Outer generations must be between 1 and 1000")
            if (
                not isinstance(self.matches_per_genome, int)
                or not 2 <= self.matches_per_genome <= 10_000
                or self.matches_per_genome % 2
            ):
                raise ValueError(
                    "Matches per genome must be an even number between 2 and 10000"
                )
            if (
                not isinstance(self.holdout_seed_pairs, int)
                or not 1 <= self.holdout_seed_pairs <= 10_000
            ):
                raise ValueError("Holdout seed pairs must be between 1 and 10000")
        elif (
            not isinstance(self.evaluation_games, int)
            or not 1 <= self.evaluation_games <= 100_000
        ):
            raise ValueError("Evaluation games must be between 1 and 100000")


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
    telemetry_path: str = ""
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
    generation: int = 0
    total_generations: int = 0
    genome_count: int = 0
    workers: int = 0
    fitness_history: tuple[tuple[int, float], ...] = ()
    run_kind: str = TrainingKind.DECK_BUILDER.value


@dataclass(frozen=True)
class TrainingTelemetry:
    status: str
    phase: str = ""
    generation: int = 0
    total_generations: int = 0
    round_completed: int = 0
    round_total: int = 0
    best_score: float | None = None
    win_rate: float | None = None
    workers: int = 0
    genome_count: int = 0
    fitness_history: tuple[tuple[int, float], ...] = ()
    phase_progress: float | None = None
    eta_seconds: float | None = None
    elapsed_seconds: float | None = None
    checkpoint_generation: int = 0


@dataclass(frozen=True)
class MatchupInsight:
    deck_1: str
    deck_2: str
    score: float
    generation: int
    shared_cards: int
    deck_1_cards: tuple[str, ...] = ()
    deck_2_cards: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrainingInsights:
    run_kind: str = ""
    subject: str = ""
    opponent: str = ""
    generation_scores: tuple[tuple[int, float, float, float, int], ...] = ()
    favorable_matchups: tuple[MatchupInsight, ...] = ()
    difficult_matchups: tuple[MatchupInsight, ...] = ()
    top_cards: tuple[tuple[str, float, int], ...] = ()
    evaluation: tuple[int, int, int] = (0, 0, 0)
    skill_evaluations: tuple[tuple[int, int, int, int], ...] = ()
    total_evaluation_games: int = 0
    total_matches: int = 0
    distinct_decks: int = 0
    eligible_matchups: int = 0
    elapsed_seconds: float | None = None
    conclusions: tuple[str, ...] = ()


def shared_card_count(first: tuple[str, ...], second: tuple[str, ...]) -> int:
    """Count shared card copies, not merely shared card names."""
    return sum((Counter(first) & Counter(second)).values())


def select_diverse_matchups(
    candidates,
    deck_cards: dict[str, tuple[str, ...]],
    deck_names: dict[str, str] | None = None,
    *,
    max_shared_cards: int = 7,
    limit: int = 2,
) -> tuple[tuple[MatchupInsight, ...], tuple[MatchupInsight, ...], int]:
    """Return strongest and weakest non-near-duplicate deck pairings."""
    deck_names = deck_names or {}
    eligible = []
    for deck_1, deck_2, generation, score in candidates:
        cards_1 = tuple(deck_cards.get(str(deck_1), ()))
        cards_2 = tuple(deck_cards.get(str(deck_2), ()))
        if not cards_1 or not cards_2:
            continue
        shared = shared_card_count(cards_1, cards_2)
        if shared > max_shared_cards:
            continue
        eligible.append(
            MatchupInsight(
                deck_1=deck_names.get(str(deck_1), str(deck_1)),
                deck_2=deck_names.get(str(deck_2), str(deck_2)),
                score=float(score),
                generation=int(generation or 0),
                shared_cards=shared,
                deck_1_cards=cards_1,
                deck_2_cards=cards_2,
            )
        )

    strongest = sorted(eligible, key=lambda item: item.score, reverse=True)[:limit]
    strongest_keys = {
        (item.deck_1, item.deck_2, item.generation, item.score) for item in strongest
    }
    weakest = [
        item
        for item in sorted(eligible, key=lambda item: item.score)
        if (item.deck_1, item.deck_2, item.generation, item.score)
        not in strongest_keys
    ][:limit]
    return tuple(strongest), tuple(weakest), len(eligible)


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
        "--opponent-deck",
        str(request.opponent_deck_id or request.deck_id),
        "--generations",
        str(request.evaluator_generations),
        "--workers",
        str(request.workers),
        "--evaluation-games",
        str(request.evaluation_games),
        "--run-label",
        request.run_label,
    ]


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
        active_jobs = self.owned_running_jobs()
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
        telemetry_path = job_dir / "telemetry.jsonl"
        environment = os.environ.copy()
        environment["TRAINING_PROGRESS_PATH"] = str(progress_path)
        environment["TRAINING_ARTIFACT_DIR"] = str(job_dir)
        environment["PLAYER_TRAINING_SUMMARY_PATH"] = str(summary_path)
        environment["TRAINING_TELEMETRY_PATH"] = str(telemetry_path)
        environment["PYTHONUNBUFFERED"] = "1"
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
            telemetry_path=str(telemetry_path),
        )
        self._processes[job_id] = process
        self._save_job(job)
        return job

    def owned_running_jobs(self) -> list[TrainingJob]:
        """Return live jobs started by this Pygame application instance."""
        running = []
        for job_id, process in list(self._processes.items()):
            if process.poll() is not None:
                continue
            job = self._load_job(self._job_path(job_id))
            if job is not None:
                running.append(job)
        return running

    def stop_owned_jobs(self, timeout: float = 4.0) -> list[TrainingJob]:
        """Stop this UI session's process groups and persist cancelled status."""
        stopped = []
        for job in self.owned_running_jobs():
            stopped_job = self.stop_job(job, timeout=timeout)
            if stopped_job is not None:
                stopped.append(stopped_job)
        return stopped

    def can_stop(self, job: TrainingJob) -> bool:
        process = self._processes.get(job.job_id)
        return process is not None and process.poll() is None

    def stop_job(
        self,
        job: TrainingJob,
        timeout: float = 4.0,
    ) -> TrainingJob | None:
        """Stop one live process owned by this UI session."""
        process = self._processes.get(job.job_id)
        if process is None or process.poll() is not None:
            return None
        try:
            os.killpg(process.pid, signal.SIGINT)
        except (AttributeError, OSError, ProcessLookupError):
            try:
                process.terminate()
            except OSError:
                pass
        try:
            return_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (AttributeError, OSError, ProcessLookupError):
                try:
                    process.kill()
                except OSError:
                    pass
            try:
                return_code = process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                return_code = None
        job.status = "cancelled"
        job.return_code = return_code
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
            # A process not present in this service was not launched by this
            # Pygame session. Do not adopt or block on persisted PID records.
            alive = False
        if not alive:
            job.return_code = return_code
            if return_code is None:
                job_dir = self._job_path(job.job_id).parent
                has_artifact = Path(job.summary_path).exists() or any(
                    (job_dir / "trained_ai").glob("*.pickle")
                )
                job.status = "completed" if has_artifact else "interrupted"
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

    @staticmethod
    def _telemetry_lines(*paths: str) -> list[str]:
        lines = []
        for path in paths:
            try:
                lines.extend(Path(path).read_text(errors="replace").splitlines()[-4000:])
            except OSError:
                continue
        return lines

    @staticmethod
    def _structured_events(path: str) -> list[dict]:
        if not path:
            return []
        events = []
        try:
            lines = Path(path).read_text(errors="replace").splitlines()[-8000:]
        except OSError:
            return []
        for line in lines:
            try:
                event = json.loads(line)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(event, dict) and event.get("schema_version") == 1:
                events.append(event)
        return events

    def job_telemetry(self, job: TrainingJob) -> TrainingTelemetry:
        request = job.request or {}
        kind = request.get("kind")
        total_generations = int(
            request.get(
                "outer_generations"
                if kind == TrainingKind.DECK_BUILDER.value
                else "evaluator_generations",
                0,
            )
            or 0
        )
        generation = 0
        round_completed = 0
        round_total = 0
        best_score = None
        win_rate = None
        history: dict[int, float] = {}
        phase = ""
        phase_progress = None
        eta_seconds = None
        elapsed_seconds = None
        checkpoint_generation = 0

        events = self._structured_events(getattr(job, "telemetry_path", ""))
        for event in events:
            phase = str(event.get("phase") or phase)
            generation = max(generation, int(event.get("generation", 0) or 0))
            total_generations = max(
                total_generations,
                int(event.get("total_generations", 0) or 0),
            )
            if event.get("completed") is not None:
                round_completed = int(event.get("completed", 0) or 0)
            if event.get("total") is not None:
                round_total = int(event.get("total", 0) or 0)
            if event.get("best_score") is not None:
                best_score = float(event["best_score"])
                if generation:
                    history[generation] = max(
                        best_score,
                        history.get(generation, best_score),
                    )
            if event.get("phase_progress") is not None:
                phase_progress = max(0.0, min(1.0, float(event["phase_progress"])))
            if event.get("eta_seconds") is not None:
                eta_seconds = max(0.0, float(event["eta_seconds"]))
            if event.get("elapsed_seconds") is not None:
                elapsed_seconds = max(0.0, float(event["elapsed_seconds"]))
            checkpoint_generation = int(
                event.get("checkpoint_generation", checkpoint_generation) or 0
            )

        generation_pattern = re.compile(r"generation\s*:?\s*(\d+)", re.I)
        round_pattern = re.compile(
            r"train(?:n)?ing round:\s*(\d+)\s*/\s*(\d+)",
            re.I,
        )
        score_pattern = re.compile(
            r"(?:top_fitness|best fitness(?: overall)?)\s*:\s*"
            r"(-?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?)",
            re.I,
        )
        for line in self._telemetry_lines(job.progress_path, job.log_path):
            if not events:
                generations = list(generation_pattern.finditer(line))
                if generations:
                    generation = max(generation, int(generations[-1].group(1)))
                rounds = list(round_pattern.finditer(line))
                if rounds:
                    round_completed = int(rounds[-1].group(1))
                    round_total = int(rounds[-1].group(2))
            if not events:
                scores = list(score_pattern.finditer(line))
                if scores and generation:
                    value = float(scores[-1].group(1))
                    history[generation] = max(value, history.get(generation, value))
                    best_score = value if best_score is None else max(best_score, value)

        try:
            summary = json.loads(Path(job.summary_path).read_text())
            if summary.get("best_fitness") is not None:
                best_score = float(summary["best_fitness"])
                if generation:
                    history[generation] = best_score
            evaluation = summary.get("evaluation") or {}
            if evaluation.get("ai_win_rate") is not None:
                win_rate = float(evaluation["ai_win_rate"])
            generation = max(
                generation,
                int((summary.get("settings") or {}).get("generations", 0) or 0),
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass

        if elapsed_seconds is None:
            try:
                started = dt.datetime.fromisoformat(job.created_at)
                if started.tzinfo is not None:
                    now = dt.datetime.now(started.tzinfo)
                else:
                    now = dt.datetime.now()
                elapsed_seconds = max(0.0, (now - started).total_seconds())
            except (TypeError, ValueError):
                elapsed_seconds = None

        if job.status in {"failed", "cancelled", "interrupted"}:
            phase = job.status
            eta_seconds = None
        elif not phase:
            phase = "completed" if job.status == "completed" else "training"

        return TrainingTelemetry(
            status=job.status,
            phase=phase,
            generation=generation,
            total_generations=total_generations,
            round_completed=round_completed,
            round_total=round_total,
            best_score=best_score,
            win_rate=win_rate,
            workers=int(request.get("workers", 0) or 0),
            fitness_history=tuple(sorted(history.items())),
            phase_progress=phase_progress,
            eta_seconds=eta_seconds,
            elapsed_seconds=elapsed_seconds,
            checkpoint_generation=checkpoint_generation,
        )

    def job_database_run_id(self, job: TrainingJob) -> int | None:
        pattern = re.compile(r"training[_ ]id\s*:\s*(\d+)", re.I)
        for line in reversed(self._telemetry_lines(job.progress_path, job.log_path)):
            match = pattern.search(line)
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def database_telemetry(run: TrainingRunSummary) -> TrainingTelemetry:
        return TrainingTelemetry(
            status=run.status,
            generation=run.generation,
            total_generations=run.total_generations,
            best_score=run.best_score,
            workers=run.workers,
            genome_count=run.genome_count,
            fitness_history=run.fitness_history,
        )

    def recent_database_runs(self, limit: int = 20) -> list[TrainingRunSummary]:
        if not TRAIN_DB_PATH.exists():
            return []
        connection = sqlite3.connect(
            f"file:{TRAIN_DB_PATH}?mode=ro&immutable=1",
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
            run_ids = [int(row["id"]) for row in rows]
            history_rows = []
            if run_ids:
                placeholders = ",".join("?" for _ in run_ids)
                history_rows = connection.execute(
                    f"""
                    SELECT training_id, gen, MAX(score) AS best_score
                    FROM genome
                    WHERE training_id IN ({placeholders})
                    GROUP BY training_id, gen
                    ORDER BY training_id DESC, gen ASC
                    """,
                    run_ids,
                ).fetchall()
        finally:
            connection.close()

        histories: dict[int, list[tuple[int, float]]] = {}
        for history_row in history_rows:
            if history_row["best_score"] is None:
                continue
            histories.setdefault(int(history_row["training_id"]), []).append(
                (int(history_row["gen"] or 0), float(history_row["best_score"]))
            )

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
            status = "incomplete" if row["end_date"] is None else "completed"
            if termination and str(termination).startswith("failed"):
                status = "failed"
            label = settings.get("run_label") or "deck builder"
            total_generations = int(settings.get("outer_generations", 0) or 0)
            workers = int(
                settings.get("outer_workers", settings.get("workers", 0)) or 0
            )
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
                    generation=int(row["max_generation"] or 0),
                    total_generations=total_generations,
                    genome_count=int(row["genome_count"] or 0),
                    workers=workers,
                    fitness_history=tuple(histories.get(int(row["id"]), ())),
                    run_kind=TrainingKind.DECK_BUILDER.value,
                )
            )
        return summaries

    @staticmethod
    def _immutable_connection(path: Path):
        connection = sqlite3.connect(
            f"file:{path}?mode=ro&immutable=1",
            uri=True,
            timeout=3.0,
        )
        connection.row_factory = sqlite3.Row
        return connection

    def _deck_details(self, connection, training_id: int, deck_ids: set[str]):
        deck_cards: dict[str, list[str]] = defaultdict(list)
        deck_names = {}
        for row in connection.execute(
            "SELECT id, COALESCE(NULLIF(name, ''), id) AS name "
            "FROM ai_training_decks WHERE training_id = ?",
            (training_id,),
        ):
            deck_names[str(row["id"])] = str(row["name"])
        for row in connection.execute(
            """
            SELECT l.deck_id, l.card_id
            FROM ai_training_deck_lines l
            JOIN ai_training_decks d ON d.id = l.deck_id
            WHERE d.training_id = ?
            ORDER BY l.deck_id, l.position
            """,
            (training_id,),
        ):
            deck_cards[str(row["deck_id"])].append(str(row["card_id"]))

        missing = deck_ids - set(deck_cards)
        if missing:
            decks_path = PROJECT_ROOT / "utils" / "decks.db"
            if decks_path.exists():
                deck_connection = self._immutable_connection(decks_path)
                try:
                    placeholders = ",".join("?" for _ in missing)
                    rows = deck_connection.execute(
                        f"""
                        SELECT d.id, COALESCE(NULLIF(d.name, ''), d.id) AS name,
                               l.card_id, l.signature
                        FROM decks d
                        JOIN deck_lines l ON l.deck_id = d.id
                        WHERE d.id IN ({placeholders})
                           OR l.signature IN ({placeholders})
                        ORDER BY d.id, l.rowid
                        """,
                        (*missing, *missing),
                    )
                    for row in rows:
                        keys = {str(row["id"])}
                        if row["signature"]:
                            keys.add(str(row["signature"]))
                        for key in keys & missing:
                            deck_names[key] = str(row["name"])
                            deck_cards[key].append(str(row["card_id"]))
                finally:
                    deck_connection.close()

        card_names = {}
        all_card_ids = {card for cards in deck_cards.values() for card in cards}
        cards_path = PROJECT_ROOT / "utils" / "cards.db"
        if all_card_ids and cards_path.exists():
            card_connection = self._immutable_connection(cards_path)
            try:
                placeholders = ",".join("?" for _ in all_card_ids)
                for row in card_connection.execute(
                    f"SELECT id, COALESCE(NULLIF(name, ''), id) AS name "
                    f"FROM cards WHERE id IN ({placeholders})",
                    tuple(all_card_ids),
                ):
                    card_names[str(row["id"])] = str(row["name"])
            finally:
                card_connection.close()
        named_cards = {
            deck_id: tuple(card_names.get(card, card) for card in cards)
            for deck_id, cards in deck_cards.items()
        }
        return named_cards, deck_names

    def database_insights(self, run: TrainingRunSummary) -> TrainingInsights:
        match = re.search(r"(\d+)$", run.run_id)
        if not match or not TRAIN_DB_PATH.exists():
            return TrainingInsights(conclusions=("No database analytics are available.",))
        training_id = int(match.group(1))
        connection = self._immutable_connection(TRAIN_DB_PATH)
        try:
            generation_rows = connection.execute(
                """
                SELECT gen, MIN(score) AS worst, AVG(score) AS average,
                       MAX(score) AS best, COUNT(*) AS contenders
                FROM genome
                WHERE training_id = ? AND score IS NOT NULL
                GROUP BY gen ORDER BY gen
                """,
                (training_id,),
            ).fetchall()
            matchup_rows = connection.execute(
                """
                SELECT m.deck_1, m.deck_2, m.gen, m.result
                FROM match_dbt m
                JOIN genome g1 ON g1.guid = m.genome_1
                JOIN genome g2 ON g2.guid = m.genome_2
                WHERE g1.training_id = ? AND g2.training_id = ?
                  AND m.result IS NOT NULL
                """,
                (training_id, training_id),
            ).fetchall()
            deck_score_rows = connection.execute(
                """
                SELECT deck_id, AVG(score) AS score
                FROM genome WHERE training_id = ? AND score IS NOT NULL
                GROUP BY deck_id
                """,
                (training_id,),
            ).fetchall()
            deck_ids = {
                str(row[key])
                for row in matchup_rows
                for key in ("deck_1", "deck_2")
                if row[key] is not None
            }
            deck_cards, deck_names = self._deck_details(
                connection, training_id, deck_ids
            )
        finally:
            connection.close()

        candidates = [
            (row["deck_1"], row["deck_2"], row["gen"], row["result"])
            for row in matchup_rows
        ]
        favorable, difficult, eligible_count = select_diverse_matchups(
            candidates,
            deck_cards,
            deck_names,
        )
        deck_scores = {
            str(row["deck_id"]): float(row["score"])
            for row in deck_score_rows
            if row["score"] is not None
        }
        card_scores: dict[str, list[float]] = defaultdict(list)
        card_uses = Counter()
        for deck_id, cards in deck_cards.items():
            if deck_id not in deck_scores:
                continue
            for card in cards:
                card_scores[card].append(deck_scores[deck_id])
                card_uses[card] += 1
        top_cards = tuple(
            sorted(
                (
                    (card, sum(scores) / len(scores), card_uses[card])
                    for card, scores in card_scores.items()
                ),
                key=lambda item: (item[1], item[2]),
                reverse=True,
            )[:6]
        )
        generation_scores = tuple(
            (
                int(row["gen"] or 0),
                float(row["worst"]),
                float(row["average"]),
                float(row["best"]),
                int(row["contenders"]),
            )
            for row in generation_rows
        )
        conclusions = []
        if generation_scores:
            first, last = generation_scores[0], generation_scores[-1]
            if len(generation_scores) == 1:
                conclusions.append(
                    f"This single-generation run established champion fitness at {last[3]:.1f}."
                )
            else:
                conclusions.append(
                    f"Champion fitness changed {last[3] - first[3]:+.1f} from generation {first[0]} to {last[0]}."
                )
            conclusions.append(
                f"Final population spread is {last[3] - last[1]:.1f} across {last[4]} contenders."
            )
        if top_cards:
            conclusions.append(
                f"{top_cards[0][0]} has the strongest observed deck-level fitness association ({top_cards[0][1]:.1f}); this is not proof of causation."
            )
        if eligible_count:
            conclusions.append(
                f"{eligible_count} matchup pairs passed the seven-shared-card diversity rule."
            )
        return TrainingInsights(
            run_kind=TrainingKind.DECK_BUILDER.value,
            subject=run.title,
            generation_scores=generation_scores,
            favorable_matchups=favorable,
            difficult_matchups=difficult,
            top_cards=top_cards,
            total_matches=len(matchup_rows),
            distinct_decks=len(deck_cards),
            eligible_matchups=eligible_count,
            conclusions=tuple(conclusions),
        )

    def job_insights(self, job: TrainingJob) -> TrainingInsights:
        kind = str((job.request or {}).get("kind", ""))
        if kind == TrainingKind.DECK_BUILDER.value:
            database_run_id = self.job_database_run_id(job)
            if database_run_id is not None:
                database_run = TrainingRunSummary(
                    run_id=f"DB {database_run_id}",
                    title=str((job.request or {}).get("run_label") or job.job_id),
                    status=job.status,
                    started=job.created_at,
                    detail="UI deck-builder experiment",
                    run_kind=TrainingKind.DECK_BUILDER.value,
                )
                return replace(
                    self.database_insights(database_run),
                    subject=f"{database_run.title} · DB {database_run_id}",
                )
        try:
            summary = json.loads(Path(job.summary_path).read_text())
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            summary = {}
        evaluation = summary.get("evaluation") or {}
        wins = int(evaluation.get("ai_wins", 0) or 0)
        draws = int(evaluation.get("draws", 0) or 0)
        losses = int(evaluation.get("random_wins", 0) or 0)
        skill_evaluations = tuple(
            (
                int(item.get("generation", 0) or 0),
                int(item.get("ai_wins", 0) or 0),
                int(item.get("draws", 0) or 0),
                int(item.get("random_wins", 0) or 0),
            )
            for item in (summary.get("skill_evaluations") or ())
            if isinstance(item, dict)
        )
        telemetry = self.job_telemetry(job)
        generation_scores = tuple(
            (generation, score, score, score, 1)
            for generation, score in telemetry.fitness_history
        )
        conclusions = []
        if job.status in {"failed", "interrupted", "cancelled"}:
            ending = {
                "failed": "failed",
                "interrupted": "was interrupted",
                "cancelled": "was stopped by the user",
            }[job.status]
            conclusions.append(
                f"This run {ending}; partial telemetry is shown where available."
            )
            if job.status in {"failed", "interrupted"}:
                tail = [
                    line.strip()
                    for line in self.tail(job.log_path, 8)
                    if line.strip()
                ]
                if tail:
                    conclusions.append(f"Last trainer message: {tail[-1][:180]}")
        games = wins + draws + losses
        if games:
            conclusions.append(
                f"The trained controller won {wins / games * 100:.1f}% of {games} evaluation games."
            )
            conclusions.append(
                f"Evaluation produced {wins} wins, {draws} draws, and {losses} losses."
            )
        if len(skill_evaluations) > 1:
            first = skill_evaluations[0]
            last = skill_evaluations[-1]
            first_total = sum(first[1:])
            last_total = sum(last[1:])
            if first_total and last_total:
                conclusions.append(
                    f"Controller-maturity win rate changed from {first[1] / first_total * 100:.1f}% at generation {first[0]} "
                    f"to {last[1] / last_total * 100:.1f}% at generation {last[0]}."
                )
        if telemetry.best_score is not None:
            conclusions.append(
                f"The strongest recorded controller fitness was {telemetry.best_score:.1f}."
            )
        opponent_name = str(
            summary.get("opponent_deck_name")
            or summary.get("opponent_deck_id")
            or (job.request or {}).get("opponent_deck_id")
            or "random opponent"
        )
        conclusions.append(
            f"Checkpoint trials use the selected deck against random play with {opponent_name}."
        )
        return TrainingInsights(
            run_kind=kind or TrainingKind.PLAYER_DECK.value,
            subject=str(summary.get("deck_name") or summary.get("deck_id") or "Selected deck"),
            opponent=opponent_name,
            generation_scores=generation_scores,
            evaluation=(wins, draws, losses),
            skill_evaluations=skill_evaluations,
            total_evaluation_games=(
                sum(sum(item[1:]) for item in skill_evaluations)
                or games
            ),
            elapsed_seconds=(
                float(summary["elapsed_seconds"])
                if summary.get("elapsed_seconds") is not None
                else None
            ),
            conclusions=tuple(conclusions),
        )

    @staticmethod
    def tail(path: str, max_lines: int = 12) -> list[str]:
        try:
            with Path(path).open(errors="replace") as log_file:
                return [line.rstrip() for line in log_file.readlines()[-max_lines:]]
        except OSError:
            return []
