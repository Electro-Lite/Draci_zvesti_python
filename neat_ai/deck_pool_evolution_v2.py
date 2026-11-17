"""Deck Pool Evolution v2: evolve compositions directly, not builder networks."""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import pickle
import random
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from time import ctime, time

from cards.power import Power
from neat_ai.ai_training_logger import AITrainingLogger, Genome, MatchDBT, Training
from neat_ai.direct_deck_evolution_algorithm import (
    CompositionEvolutionSettings,
    DeckGenome,
    EvaluatedDeckGenome,
    available_cards,
    initial_population,
    next_population,
)
from neat_ai.config_profiles import config_path
from neat_ai.deck_builder_trainer import (
    MIN_FREE_DISK_BYTES,
    PAUSE_REQUEST_ENV,
    TrainingPauseRequested,
    _evaluate_pair,
    _file_sha256,
    _genome_guid,
    _git_metadata,
    _remember_best_controller,
    build_matchups,
)
from neat_ai.deck_evaluator import (
    DEFAULT_CROSSPLAY_REFERENCE_GENERATION,
    DEFAULT_DIAGNOSTIC_HOLDOUT_GENERATIONS,
    DEFAULT_EVALUATOR_GENERATIONS,
    EvaluatorSettings,
)
from neat_ai.player_artifacts import export_player_artifact
from neat_ai.training_telemetry import emit_training_event
from utils.database_utils import DBUtil


DEFAULT_SEEDS = (667615478, 2069633686, 915632071, 274633778)
DEFAULT_RUN_LABEL = "deck-pool-evolution-v2"
DEFAULT_RUN_DESCRIPTION = (
    "Direct deck-composition evolution with NEAT-trained player controllers. "
    "The outer population uses legal card multisets, tournament selection, "
    "crossover, mutation, elitism, and strict composition uniqueness."
)
DEFAULT_OUTER_GENERATIONS = 10


@dataclass(frozen=True)
class DeckPoolV2Settings:
    seed: int
    run_label: str = DEFAULT_RUN_LABEL
    description: str = DEFAULT_RUN_DESCRIPTION
    outer_generations: int = DEFAULT_OUTER_GENERATIONS
    max_matches_per_genome: int = 12
    outer_workers: int = 2
    evaluator_generations: int = DEFAULT_EVALUATOR_GENERATIONS
    evaluator_workers: int = 12
    holdout_seed_pairs: int = 20
    early_holdout_generation: int = 5
    diagnostic_holdout_generations: tuple[int, ...] = (
        DEFAULT_DIAGNOSTIC_HOLDOUT_GENERATIONS
    )
    crossplay_reference_generation: int | None = (
        DEFAULT_CROSSPLAY_REFERENCE_GENERATION
    )
    log_training_games: bool = False
    population_size: int = 20
    elite_count: int = 2
    tournament_size: int = 3
    crossover_rate: float = 0.80
    mutation_rate: float = 0.90
    random_injection_rate: float = 0.10
    checkpoint_path: str | None = None
    resume_training_id: int | None = None
    max_card_power: int = Power.LEGENDARY.value
    banned_card_ids: tuple[str, ...] = ()

    def __post_init__(self):
        if self.outer_generations < 1:
            raise ValueError("Outer generations must be positive")
        if self.max_matches_per_genome < 1:
            raise ValueError("Matches per genome must be positive")
        if self.max_matches_per_genome % 2:
            raise ValueError("Matches per genome must be even for seat balance")
        if self.outer_workers < 1:
            raise ValueError("Outer workers must be positive")
        Power(self.max_card_power)
        self.evolution_settings()
        self.evaluator_settings()

    def evolution_settings(self) -> CompositionEvolutionSettings:
        return CompositionEvolutionSettings(
            population_size=self.population_size,
            elite_count=self.elite_count,
            tournament_size=self.tournament_size,
            crossover_rate=self.crossover_rate,
            mutation_rate=self.mutation_rate,
            random_injection_rate=self.random_injection_rate,
        )

    def evaluator_settings(self) -> EvaluatorSettings:
        return EvaluatorSettings(
            generations=self.evaluator_generations,
            workers=self.evaluator_workers,
            holdout_seed_pairs=self.holdout_seed_pairs,
            early_holdout_generation=self.early_holdout_generation,
            diagnostic_holdout_generations=self.diagnostic_holdout_generations,
            crossplay_reference_generation=self.crossplay_reference_generation,
            seed=self.seed,
            log_training_games=self.log_training_games,
        )


@dataclass(frozen=True)
class DeckPoolCheckpoint:
    schema_version: int
    optimizer: str
    training_id: int
    seed: int
    completed_generation: int
    population: tuple[DeckGenome, ...]
    random_state: object


def _checkpoint_completed_generation(path: str | Path) -> int:
    with Path(path).open("rb") as handle:
        checkpoint = _checkpoint_from_payload(pickle.load(handle))
    return checkpoint.completed_generation


def _checkpoint_from_payload(payload) -> DeckPoolCheckpoint:
    """Decode a process-independent checkpoint payload.

    The CLI is launched with ``python -m``; pickling a class defined by that
    module would otherwise bind it to ``__main__`` and make external recovery
    unnecessarily fragile.
    """
    if not isinstance(payload, dict):
        raise ValueError("Checkpoint is not a Deck Pool Evolution v2 checkpoint")
    try:
        checkpoint = DeckPoolCheckpoint(
            schema_version=int(payload["schema_version"]),
            optimizer=str(payload["optimizer"]),
            training_id=int(payload["training_id"]),
            seed=int(payload["seed"]),
            completed_generation=int(payload["completed_generation"]),
            population=tuple(DeckGenome(tuple(cards)) for cards in payload["population"]),
            random_state=payload["random_state"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Malformed Deck Pool Evolution v2 checkpoint") from error
    if checkpoint.schema_version != 1 or checkpoint.optimizer != "composition-ga-v2":
        raise ValueError("Unsupported Deck Pool Evolution checkpoint")
    return checkpoint


def _save_checkpoint(
    path: Path,
    training_id: int,
    settings: DeckPoolV2Settings,
    completed_generation: int,
    population: list[DeckGenome],
    rng: random.Random,
) -> None:
    payload = {
        "schema_version": 1,
        "optimizer": "composition-ga-v2",
        "training_id": training_id,
        "seed": settings.seed,
        "completed_generation": completed_generation,
        "population": [genome.cards for genome in population],
        "random_state": rng.getstate(),
    }
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        pickle.dump(payload, handle)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _load_checkpoint(
    path: str | Path,
    settings: DeckPoolV2Settings,
) -> tuple[DeckPoolCheckpoint, random.Random]:
    with Path(path).open("rb") as handle:
        checkpoint = _checkpoint_from_payload(pickle.load(handle))
    if checkpoint.seed != settings.seed:
        raise ValueError("Checkpoint seed does not match the resumed run")
    if settings.resume_training_id not in (None, checkpoint.training_id):
        raise ValueError("Checkpoint training ID does not match the resumed run")
    if len(checkpoint.population) != settings.population_size:
        raise ValueError("Checkpoint population size does not match current settings")
    rng = random.Random()
    rng.setstate(checkpoint.random_state)
    return checkpoint, rng


def _metadata(
    project_root: Path,
    settings: DeckPoolV2Settings,
    evaluator_config: str,
) -> dict:
    return {
        "schema_version": 4,
        "optimizer": "composition-ga-v2",
        "description": settings.description,
        "settings": asdict(settings),
        "composition_evolution": asdict(settings.evolution_settings()),
        "builder_config": json.dumps(
            asdict(settings.evolution_settings()), sort_keys=True
        ),
        "evaluator_config": evaluator_config,
        "git": _git_metadata(project_root),
        "database_hashes": {
            "cards": _file_sha256(project_root / "data" / "cards.db"),
            "decks": _file_sha256(project_root / "data" / "decks.db"),
        },
        "observed_populations": [],
        "termination_reason": None,
    }


def _evaluate_generation(
    population: list[DeckGenome],
    card_pool: dict[str, object],
    settings: DeckPoolV2Settings,
    training_row: Training,
    generation: int,
    metadata: dict,
    artifact_root: Path,
) -> list[EvaluatedDeckGenome]:
    generation_started_at = time()
    if len(set(population)) != len(population):
        raise RuntimeError("Deck Pool Evolution v2 population contains duplicate compositions")
    for genome in population:
        genome.to_deck(card_pool)
    metadata["observed_populations"].append({
        "generation": generation,
        "population": len(population),
        "distinct_compositions": len(set(population)),
        "optimizer": "composition-ga-v2",
    })

    indexed = list(enumerate(population, start=(generation - 1) * len(population)))
    rng = random.Random(f"{settings.seed}:{generation}:matchups")
    matches = build_matchups(indexed, settings.max_matches_per_genome, rng)
    if not matches:
        raise RuntimeError("Composition generation has no legal matchups")
    emit_training_event(
        "phase_progress",
        phase="deck_evolution",
        training_id=training_row.id,
        generation=generation,
        total_generations=settings.outer_generations,
        completed=0,
        total=len(matches),
        phase_progress=max(0.0, (generation - 1) / settings.outer_generations),
    )
    progress_path = os.environ.get("TRAINING_PROGRESS_PATH", "training_progress.txt")
    with open(progress_path, "a", encoding="utf-8") as progress_file:
        progress_file.write(
            f"training_id: {training_row.id} | seed: {settings.seed} | "
            f"generation: {generation} | training round: 0/{len(matches)} "
            f"| time: {ctime(time())}\n"
        )

    logger = AITrainingLogger()
    decks = {}
    scores = {individual_id: 0.0 for individual_id, _ in indexed}
    counts = {individual_id: 0 for individual_id, _ in indexed}
    genomes = dict(indexed)
    for individual_id, genome in indexed:
        deck = genome.to_deck(card_pool, name=f"Gen{generation}_ID{individual_id}")
        logger.save_training_deck(deck, training_row.id)
        decks[individual_id] = deck
        logger.save_genome(Genome(
            guid=_genome_guid(training_row.id, generation, individual_id),
            gen=generation,
            deck_id=deck.id,
            training_id=training_row.id,
            score=0.0,
        ))

    scheduled = []
    for (first_id, _), (second_id, _) in matches:
        if genomes[first_id] == genomes[second_id]:
            raise RuntimeError("Identical deck compositions must not be evaluated")
        match_guid = f"T{training_row.id}:{first_id}-vs-{second_id}:gen{generation}"
        logger.save_match_dbt(MatchDBT(
            guid=match_guid,
            genome_1=_genome_guid(training_row.id, generation, first_id),
            genome_2=_genome_guid(training_row.id, generation, second_id),
            deck_1=decks[first_id].id,
            deck_2=decks[second_id].id,
            gen=generation,
            result=None,
        ))
        scheduled.append((
            first_id,
            decks[first_id],
            second_id,
            decks[second_id],
            match_guid,
            settings.evaluator_settings(),
        ))

    best_controllers = {}
    completed = 0
    with ProcessPoolExecutor(max_workers=max(1, settings.outer_workers)) as executor:
        futures = [executor.submit(_evaluate_pair, *match) for match in scheduled]
        for future in as_completed(futures):
            first_id, fit1, controller1, second_id, fit2, controller2, guid = future.result()
            if not math.isfinite(fit1) or not math.isfinite(fit2):
                raise RuntimeError(f"Deck matchup {guid} produced non-finite fitness")
            scores[first_id] += fit1
            scores[second_id] += fit2
            counts[first_id] += 1
            counts[second_id] += 1
            _remember_best_controller(best_controllers, first_id, fit1, controller1)
            _remember_best_controller(best_controllers, second_id, fit2, controller2)
            completed += 1
            saved_match = logger.get_match_dbt(guid)
            if saved_match is not None:
                saved_match.result = fit1
                logger.save_match_dbt(saved_match)
            generation_progress = completed / len(scheduled)
            elapsed = time() - generation_started_at
            remaining_generation = (
                elapsed * (1.0 - generation_progress) / generation_progress
                if generation_progress >= 0.05 else 0.0
            )
            emit_training_event(
                "phase_progress",
                phase="deck_evolution",
                training_id=training_row.id,
                generation=generation,
                total_generations=settings.outer_generations,
                completed=completed,
                total=len(scheduled),
                phase_progress=((generation - 1) + generation_progress)
                / settings.outer_generations,
                eta_seconds=remaining_generation
                + elapsed * max(0, settings.outer_generations - generation),
            )
            print(
                f"generation: {generation} | training round: "
                f"{completed}/{len(scheduled)} | time: {ctime(time())}"
            )

    expected = min(settings.max_matches_per_genome, len(population) - 1)
    if (len(population) * expected) % 2:
        expected -= 1
    evaluated = []
    for individual_id, genome in indexed:
        if counts[individual_id] != expected:
            raise RuntimeError(
                f"Composition {individual_id} played {counts[individual_id]} opponents; "
                f"expected {expected}"
            )
        fitness = scores[individual_id] / counts[individual_id]
        retained = best_controllers.get(individual_id)
        if retained is None:
            raise RuntimeError(f"Composition {individual_id} has no retained controller")
        deck = decks[individual_id]
        artifact = export_player_artifact(
            artifact_root / "trained_ai",
            retained[1],
            deck,
            mission="deck-evolution",
            role=f"deck-{deck.id}",
            run_label=settings.run_label,
            generation=settings.evaluator_generations,
            display_name=f"{deck.name} · evolution gen {generation} player",
        )
        genome_row = logger.get_genome(
            _genome_guid(training_row.id, generation, individual_id)
        )
        if genome_row is not None:
            genome_row.score = fitness
            genome_row.pickle_path = str(artifact.path.resolve())
            logger.save_genome(genome_row)
        evaluated.append(EvaluatedDeckGenome(genome, fitness))

    best_score = max(item.fitness for item in evaluated)
    emit_training_event(
        "generation_completed",
        phase="deck_evolution",
        training_id=training_row.id,
        generation=generation,
        total_generations=settings.outer_generations,
        phase_progress=generation / settings.outer_generations,
        best_score=best_score,
    )
    return evaluated


def train_deck_pool_v2(settings: DeckPoolV2Settings) -> EvaluatedDeckGenome:
    project_root = Path(__file__).resolve().parents[1]
    if shutil.disk_usage(project_root).free < MIN_FREE_DISK_BYTES:
        raise RuntimeError("At least 1 GiB of free disk space is required")
    artifact_root = Path(os.environ.get("TRAINING_ARTIFACT_DIR", Path(__file__).parent))
    evaluator_config = config_path("evaluator").read_text(encoding="utf-8")
    card_pool = available_cards(DBUtil().get_all_cards(), max_power=Power(settings.max_card_power),
                                banned_card_ids=settings.banned_card_ids)
    if not card_pool:
        raise RuntimeError("No eligible player cards are available for deck evolution")

    completed_generations = 0
    if settings.checkpoint_path:
        checkpoint, rng = _load_checkpoint(settings.checkpoint_path, settings)
        completed_generations = checkpoint.completed_generation
        population = list(checkpoint.population)
        if completed_generations >= settings.outer_generations:
            raise ValueError("Checkpoint already reached requested generation count")
    else:
        rng = random.Random(settings.seed)
        population = initial_population(card_pool, rng, settings.evolution_settings())

    logger = AITrainingLogger()
    if settings.resume_training_id is not None:
        training_row = logger.get_training(settings.resume_training_id)
        if training_row is None:
            raise ValueError(f"Training run {settings.resume_training_id} no longer exists")
        try:
            metadata = json.loads(training_row.metadata or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        if metadata.get("optimizer") != "composition-ga-v2":
            raise ValueError("Only a Deck Pool Evolution v2 run can resume this checkpoint")
        metadata.setdefault("observed_populations", [])
        metadata["settings"] = asdict(settings)
        metadata["termination_reason"] = None
        metadata["resumed_from_generation"] = completed_generations
        training_row.end_date = None
        training_row.metadata = json.dumps(metadata, sort_keys=True)
        training_row.description = settings.description
        logger.save_training(training_row)
    else:
        metadata = _metadata(project_root, settings, evaluator_config)
        training_row = logger.save_training(Training(
            start_date=str(datetime.datetime.now()),
            config=json.dumps(asdict(settings.evolution_settings()), sort_keys=True),
            metadata=json.dumps(metadata, sort_keys=True),
            description=settings.description,
        ))

    print(f"training id: {training_row.id} | seed: {settings.seed} | optimizer: composition-ga-v2")
    emit_training_event(
        "run_resumed" if settings.checkpoint_path else "run_started",
        phase="deck_evolution",
        training_id=training_row.id,
        generation=completed_generations,
        total_generations=settings.outer_generations,
        phase_progress=completed_generations / settings.outer_generations,
        seed=settings.seed,
    )
    checkpoint_dir = artifact_root / "checkpoints" / "deck_builder_trainer"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    started_at = time()
    final_evaluated: list[EvaluatedDeckGenome] = []
    try:
        for generation in range(completed_generations + 1, settings.outer_generations + 1):
            final_evaluated = _evaluate_generation(
                population,
                card_pool,
                settings,
                training_row,
                generation,
                metadata,
                artifact_root,
            )
            population = next_population(
                final_evaluated,
                card_pool,
                rng,
                settings.evolution_settings(),
            )
            checkpoint_path = checkpoint_dir / (
                f"training_{training_row.id}_seed_{settings.seed}_gen-{generation - 1}"
            )
            _save_checkpoint(
                checkpoint_path,
                training_row.id,
                settings,
                generation,
                population,
                rng,
            )
            completed_generations = generation
            training_row.metadata = json.dumps(metadata, sort_keys=True)
            logger.save_training(training_row)
        metadata["termination_reason"] = "completed"
    except BaseException as error:
        pause_path = os.environ.get(PAUSE_REQUEST_ENV)
        if pause_path and Path(pause_path).exists():
            metadata["termination_reason"] = "paused"
            metadata["paused_after_generation"] = completed_generations
            training_row.end_date = None
            training_row.metadata = json.dumps(metadata, sort_keys=True)
            logger.save_training(training_row)
            emit_training_event(
                "run_paused",
                phase="paused",
                training_id=training_row.id,
                generation=completed_generations,
                total_generations=settings.outer_generations,
                elapsed_seconds=time() - started_at,
            )
            raise TrainingPauseRequested() from None
        metadata["termination_reason"] = f"failed: {type(error).__name__}: {error}"
        training_row.end_date = str(datetime.datetime.now())
        training_row.metadata = json.dumps(metadata, sort_keys=True)
        logger.save_training(training_row)
        emit_training_event(
            "run_failed",
            phase="failed",
            training_id=training_row.id,
            error=f"{type(error).__name__}: {error}",
            elapsed_seconds=time() - started_at,
        )
        raise

    winner = max(final_evaluated, key=lambda item: item.fitness)
    training_row.end_date = str(datetime.datetime.now())
    training_row.metadata = json.dumps(metadata, sort_keys=True)
    logger.save_training(training_row)
    output_dir = artifact_root / "trained_ai"
    output_dir.mkdir(parents=True, exist_ok=True)
    winner_path = output_dir / (
        f"best_composition_training_{training_row.id}_seed_{settings.seed}_"
        f"gen_{completed_generations}.pickle"
    )
    with winner_path.open("wb") as handle:
        pickle.dump(winner, handle)
    emit_training_event(
        "run_completed",
        phase="completed",
        training_id=training_row.id,
        generation=completed_generations,
        total_generations=settings.outer_generations,
        phase_progress=1.0,
        elapsed_seconds=time() - started_at,
        best_score=winner.fitness,
        artifact_path=str(winner_path),
    )
    print(f"best fitness: {winner.fitness}")
    print(f"winner: {winner_path}")
    return winner


def parse_args():
    parser = argparse.ArgumentParser(description="Run Deck Pool Evolution v2")
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--run-label", default=DEFAULT_RUN_LABEL)
    parser.add_argument("--description", default=DEFAULT_RUN_DESCRIPTION)
    parser.add_argument("--outer-generations", type=int, default=DEFAULT_OUTER_GENERATIONS)
    parser.add_argument("--max-matches-per-genome", type=int, default=12)
    parser.add_argument("--outer-workers", type=int, default=2)
    parser.add_argument("--evaluator-generations", type=int, default=DEFAULT_EVALUATOR_GENERATIONS)
    parser.add_argument("--evaluator-workers", type=int, default=12)
    parser.add_argument("--holdout-seed-pairs", type=int, default=20)
    parser.add_argument("--early-holdout-generation", type=int, default=5)
    parser.add_argument(
        "--diagnostic-holdout-generations",
        type=int,
        nargs="+",
        default=list(DEFAULT_DIAGNOSTIC_HOLDOUT_GENERATIONS),
    )
    parser.add_argument(
        "--crossplay-reference-generation",
        type=int,
        default=DEFAULT_CROSSPLAY_REFERENCE_GENERATION,
    )
    parser.add_argument("--log-training-games", action="store_true")
    parser.add_argument("--population-size", type=int, default=20)
    parser.add_argument("--elite-count", type=int, default=2)
    parser.add_argument("--tournament-size", type=int, default=3)
    parser.add_argument("--crossover-rate", type=float, default=0.80)
    parser.add_argument("--mutation-rate", type=float, default=0.90)
    parser.add_argument("--random-injection-rate", type=float, default=0.10)
    parser.add_argument("--checkpoint")
    parser.add_argument("--resume-training-id", type=int)
    parser.add_argument("--resume-seed", type=int)
    parser.add_argument("--max-card-power", type=int, choices=range(3), default=2)
    parser.add_argument("--banned-card-id", action="append", default=[])
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    run_seeds = list(arguments.seeds)
    if arguments.checkpoint:
        if arguments.resume_seed is None:
            if len(run_seeds) != 1:
                raise SystemExit("--checkpoint with multiple seeds requires --resume-seed")
            arguments.resume_seed = run_seeds[0]
        if arguments.resume_seed not in run_seeds:
            raise SystemExit("--resume-seed must be present in --seeds")
        run_seeds = run_seeds[run_seeds.index(arguments.resume_seed):]
    try:
        for index, seed in enumerate(run_seeds):
            train_deck_pool_v2(DeckPoolV2Settings(
                seed=seed,
                run_label=arguments.run_label,
                description=arguments.description,
                outer_generations=arguments.outer_generations,
                max_matches_per_genome=arguments.max_matches_per_genome,
                outer_workers=arguments.outer_workers,
                evaluator_generations=arguments.evaluator_generations,
                evaluator_workers=arguments.evaluator_workers,
                holdout_seed_pairs=arguments.holdout_seed_pairs,
                early_holdout_generation=arguments.early_holdout_generation,
                diagnostic_holdout_generations=tuple(arguments.diagnostic_holdout_generations),
                crossplay_reference_generation=arguments.crossplay_reference_generation,
                log_training_games=arguments.log_training_games,
                population_size=arguments.population_size,
                elite_count=arguments.elite_count,
                tournament_size=arguments.tournament_size,
                crossover_rate=arguments.crossover_rate,
                mutation_rate=arguments.mutation_rate,
                random_injection_rate=arguments.random_injection_rate,
                checkpoint_path=arguments.checkpoint if index == 0 else None,
                resume_training_id=arguments.resume_training_id if index == 0 else None,
                max_card_power=arguments.max_card_power,
                banned_card_ids=tuple(arguments.banned_card_id),
            ))
    except TrainingPauseRequested:
        raise SystemExit(75) from None
