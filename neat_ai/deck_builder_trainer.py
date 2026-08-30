import argparse
import datetime
import hashlib
import json
import math
import os
import pickle
import random
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from time import ctime, time

import neat

from neat_ai.ai_training_logger import AITrainingLogger, Genome, MatchDBT, Training
from neat_ai.deck_builder import build_deck
from neat_ai.deck_evaluator import (
    DEFAULT_CROSSPLAY_REFERENCE_GENERATION,
    DEFAULT_DIAGNOSTIC_HOLDOUT_GENERATIONS,
    DEFAULT_EVALUATOR_GENERATIONS,
    EvaluatorSettings,
    train_deck,
)


DEFAULT_SEEDS = (
    667615478,
    2069633686,
    915632071,
    274633778,
)
DEFAULT_RUN_LABEL = "final-meta-evolution"
DEFAULT_RUN_DESCRIPTION = (
    "Final multi-generation metagame experiment: four independent "
    "10-generation builder populations evaluated by 50-generation player "
    "controllers; measures card-frequency shifts, archetype survival, "
    "composition-aware diversity, and matchup distributions."
)
DEFAULT_OUTER_GENERATIONS = 10
MIN_EFFECTIVE_POPULATION = 18
MAX_EFFECTIVE_POPULATION = 24
MIN_SPECIES = 2
MAX_SPECIES = 6
MIN_FREE_DISK_BYTES = 1 << 30


@dataclass(frozen=True)
class BuilderSettings:
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
    checkpoint_path: str | None = None
    enforce_population_guard: bool = True

    def __post_init__(self):
        if self.outer_generations < 1:
            raise ValueError("Outer generations must be positive")
        if self.max_matches_per_genome < 1:
            raise ValueError("Matches per genome must be positive")
        if self.max_matches_per_genome % 2:
            raise ValueError("Matches per genome must be even for seat balance")
        if self.outer_workers < 1:
            raise ValueError("Outer workers must be positive")
        self.evaluator_settings()

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


def _genome_guid(training_id: int, generation: int, genome_id: int) -> str:
    return f"{training_id}-gen{generation}-{genome_id}"


def _file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for block in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_metadata(project_root: Path) -> dict:
    def run_git(*args):
        completed = subprocess.run(
            ["git", *args],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip() if completed.returncode == 0 else None

    return {
        "commit": run_git("rev-parse", "HEAD"),
        "branch": run_git("branch", "--show-current"),
        "dirty": bool(run_git("status", "--porcelain")),
    }


def _training_metadata(
        project_root: Path,
        builder_config: str,
        evaluator_config: str,
        settings: BuilderSettings,
) -> dict:
    return {
        "schema_version": 3,
        "description": settings.description,
        "settings": asdict(settings),
        "builder_config": builder_config,
        "evaluator_config": evaluator_config,
        "git": _git_metadata(project_root),
        "database_hashes": {
            "cards": _file_sha256(project_root / "utils" / "cards.db"),
            "decks": _file_sha256(project_root / "utils" / "decks.db"),
        },
        "observed_populations": [],
        "termination_reason": None,
    }


def build_matchups(genomes, max_matches_per_genome: int, rng: random.Random):
    population = list(genomes)
    size = len(population)
    if size < 2:
        return []

    opponent_count = min(max_matches_per_genome, size - 1)
    if (size * opponent_count) % 2:
        opponent_count -= 1
    if opponent_count <= 0:
        return []

    shuffled = population[:]
    rng.shuffle(shuffled)
    matches = []
    for index in range(size):
        for offset in range(1, opponent_count // 2 + 1):
            target = (index + offset) % size
            matches.append((shuffled[index], shuffled[target]))

        if opponent_count % 2:
            target = (index + size // 2) % size
            if index < size // 2:
                matches.append((shuffled[index], shuffled[target]))
    return matches


def _evaluate_pair(
        genome_id1,
        deck1,
        genome_id2,
        deck2,
        match_guid: str,
        evaluator_settings: EvaluatorSettings,
):
    fitness1, fitness2 = train_deck(
        deck1,
        deck2,
        match_guid,
        settings=evaluator_settings,
    )
    return genome_id1, fitness1, genome_id2, fitness2, match_guid


def eval_genomes(
        genomes,
        config,
        settings: BuilderSettings,
        training_row: Training,
        generation: int,
        species_count: int,
        metadata: dict,
):
    population_size = len(genomes)
    metadata["observed_populations"].append(
        {
            "generation": generation,
            "population": population_size,
            "species": species_count,
        }
    )
    if settings.enforce_population_guard and not (
            MIN_EFFECTIVE_POPULATION <= population_size <= MAX_EFFECTIVE_POPULATION
    ):
        raise RuntimeError(
            "Effective builder population must remain between "
            f"{MIN_EFFECTIVE_POPULATION} and {MAX_EFFECTIVE_POPULATION}; "
            f"generation {generation} has {population_size}"
        )
    if settings.enforce_population_guard and not (
            MIN_SPECIES <= species_count <= MAX_SPECIES
    ):
        raise RuntimeError(
            f"Builder species count must remain between {MIN_SPECIES} and "
            f"{MAX_SPECIES}; generation {generation} has {species_count}"
        )

    rng = random.Random(f"{settings.seed}:{generation}:matchups")
    matches_to_play = build_matchups(
        genomes,
        settings.max_matches_per_genome,
        rng,
    )
    if not matches_to_play:
        raise RuntimeError("Builder generation has no legal matchups")

    progress_path = os.environ.get("TRAINING_PROGRESS_PATH", "training_progress.txt")
    with open(progress_path, "a") as progress_file:
        progress_file.write(
            f"training_id: {training_row.id} | seed: {settings.seed} | "
            f"generation: {generation} | training round: 0/{len(matches_to_play)} "
            f"| time: {ctime(time())}\n"
        )

    logger = AITrainingLogger()
    decks_by_genome = {}
    for genome_id, genome in genomes:
        net = neat.nn.FeedForwardNetwork.create(genome, config)
        deck = build_deck(net)
        deck.name = f"Gen{generation}_ID{genome_id}"
        logger.save_training_deck(deck, training_row.id)
        decks_by_genome[genome_id] = deck
        logger.save_genome(
            Genome(
                guid=_genome_guid(training_row.id, generation, genome_id),
                gen=generation,
                deck_id=deck.id,
                training_id=training_row.id,
                score=0.0,
            )
        )
        genome.fitness = 0.0

    fitness_counts = {genome_id: 0 for genome_id, _ in genomes}
    scheduled_matches = []
    for (genome_id1, _), (genome_id2, _) in matches_to_play:
        match_guid = (
            f"T{training_row.id}:{genome_id1}-vs-{genome_id2}:gen{generation}"
        )
        logger.save_match_dbt(
            MatchDBT(
                guid=match_guid,
                genome_1=_genome_guid(training_row.id, generation, genome_id1),
                genome_2=_genome_guid(training_row.id, generation, genome_id2),
                deck_1=decks_by_genome[genome_id1].id,
                deck_2=decks_by_genome[genome_id2].id,
                gen=generation,
                result=None,
            )
        )
        scheduled_matches.append(
            (
                genome_id1,
                decks_by_genome[genome_id1],
                genome_id2,
                decks_by_genome[genome_id2],
                match_guid,
                settings.evaluator_settings(),
            )
        )

    genomes_by_id = dict(genomes)
    completed_matches = 0
    with ProcessPoolExecutor(max_workers=max(1, settings.outer_workers)) as executor:
        futures = [executor.submit(_evaluate_pair, *match) for match in scheduled_matches]
        for future in as_completed(futures):
            genome_id1, fit1, genome_id2, fit2, match_guid = future.result()
            if not math.isfinite(fit1) or not math.isfinite(fit2):
                raise RuntimeError(
                    f"Deck matchup {match_guid} produced non-finite fitness"
                )
            genomes_by_id[genome_id1].fitness += fit1
            genomes_by_id[genome_id2].fitness += fit2
            fitness_counts[genome_id1] += 1
            fitness_counts[genome_id2] += 1
            completed_matches += 1

            saved_match = logger.get_match_dbt(match_guid)
            if saved_match is not None:
                saved_match.result = fit1
                logger.save_match_dbt(saved_match)

            print(
                f"generation: {generation} | training round: "
                f"{completed_matches}/{len(scheduled_matches)} | "
                f"time: {ctime(time())}"
            )

    expected_opponents = min(settings.max_matches_per_genome, population_size - 1)
    if (population_size * expected_opponents) % 2:
        expected_opponents -= 1
    for genome_id, genome in genomes:
        if fitness_counts[genome_id] != expected_opponents:
            raise RuntimeError(
                f"Genome {genome_id} played {fitness_counts[genome_id]} opponents; "
                f"expected {expected_opponents}"
            )
        genome.fitness /= fitness_counts[genome_id]
        genome_row = logger.get_genome(
            _genome_guid(training_row.id, generation, genome_id)
        )
        if genome_row is not None:
            genome_row.score = genome.fitness
            logger.save_genome(genome_row)

    training_row.metadata = json.dumps(metadata, sort_keys=True)
    logger.save_training(training_row)


def train_deck_builder(settings: BuilderSettings):
    project_root = Path(__file__).resolve().parents[1]
    if shutil.disk_usage(project_root).free < MIN_FREE_DISK_BYTES:
        raise RuntimeError("At least 1 GiB of free disk space is required")

    local_dir = Path(__file__).resolve().parent
    artifact_root = Path(os.environ.get("TRAINING_ARTIFACT_DIR", local_dir))
    builder_config_path = local_dir / "configs" / "neat_config_builder.txt"
    evaluator_config_path = local_dir / "configs" / "neat_config_evaluator.txt"
    builder_config_text = builder_config_path.read_text()
    evaluator_config_text = evaluator_config_path.read_text()
    config = neat.Config(
        neat.DefaultGenome,
        neat.DefaultReproduction,
        neat.DefaultSpeciesSet,
        neat.DefaultStagnation,
        str(builder_config_path),
    )

    random.seed(settings.seed)
    if settings.checkpoint_path:
        population = neat.Checkpointer.restore_checkpoint(settings.checkpoint_path)
    else:
        population = neat.Population(config)

    logger = AITrainingLogger()
    metadata = _training_metadata(
        project_root,
        builder_config_text,
        evaluator_config_text,
        settings,
    )
    training_row = logger.save_training(
        Training(
            start_date=str(datetime.datetime.now()),
            config=builder_config_text,
            metadata=json.dumps(metadata, sort_keys=True),
            description=settings.description,
        )
    )
    print(f"training id: {training_row.id} | seed: {settings.seed}")

    checkpoint_dir = artifact_root / "checkpoints" / "deck_builder_trainer"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_prefix = checkpoint_dir / (
        f"training_{training_row.id}_seed_{settings.seed}_gen-"
    )
    population.add_reporter(neat.StatisticsReporter())
    population.add_reporter(
        neat.Checkpointer(generation_interval=1, filename_prefix=str(checkpoint_prefix))
    )

    generation = population.generation
    started_at = time()

    def evaluate_generation(genomes, neat_config):
        nonlocal generation
        generation += 1
        eval_genomes(
            genomes,
            neat_config,
            settings,
            training_row,
            generation,
            len(population.species.species),
            metadata,
        )

    try:
        winner = population.run(evaluate_generation, settings.outer_generations)
        metadata["termination_reason"] = "completed"
    except BaseException as error:
        metadata["termination_reason"] = f"failed: {type(error).__name__}: {error}"
        training_row.end_date = str(datetime.datetime.now())
        training_row.metadata = json.dumps(metadata, sort_keys=True)
        logger.save_training(training_row)
        raise

    training_row.end_date = str(datetime.datetime.now())
    training_row.metadata = json.dumps(metadata, sort_keys=True)
    logger.save_training(training_row)

    output_dir = artifact_root / "trained_ai"
    output_dir.mkdir(parents=True, exist_ok=True)
    winner_path = output_dir / (
        f"best_builder_training_{training_row.id}_seed_{settings.seed}_gen_{generation}.pickle"
    )
    with winner_path.open("wb") as winner_file:
        pickle.dump(winner, winner_file)

    elapsed_hours = (time() - started_at) / 3600
    print(f"best fitness: {winner.fitness}")
    print(f"training time: {elapsed_hours:.2f} hours")
    print(f"winner: {winner_path}")
    return winner


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the final multi-generation metagame experiment"
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--run-label", default=DEFAULT_RUN_LABEL)
    parser.add_argument(
        "--description",
        default=DEFAULT_RUN_DESCRIPTION,
        help="Human-readable experiment purpose stored with every training run",
    )
    parser.add_argument(
        "--outer-generations",
        type=int,
        default=DEFAULT_OUTER_GENERATIONS,
    )
    parser.add_argument("--max-matches-per-genome", type=int, default=12)
    parser.add_argument("--outer-workers", type=int, default=2)
    parser.add_argument(
        "--evaluator-generations",
        type=int,
        default=DEFAULT_EVALUATOR_GENERATIONS,
    )
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
    parser.add_argument(
        "--log-training-games",
        action="store_true",
        help=(
            "Store raw co-evolution games. Held-out games are always stored; "
            "leave this disabled for the final metagame experiment."
        ),
    )
    parser.add_argument("--checkpoint")
    parser.add_argument(
        "--allow-population-outside-guard",
        action="store_true",
        help="Disable the 18-24 effective population safety check",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    if arguments.checkpoint and len(arguments.seeds) != 1:
        raise SystemExit("--checkpoint requires exactly one --seeds value")
    for run_seed in arguments.seeds:
        train_deck_builder(
            BuilderSettings(
                seed=run_seed,
                run_label=arguments.run_label,
                description=arguments.description,
                outer_generations=arguments.outer_generations,
                max_matches_per_genome=arguments.max_matches_per_genome,
                outer_workers=arguments.outer_workers,
                evaluator_generations=arguments.evaluator_generations,
                evaluator_workers=arguments.evaluator_workers,
                holdout_seed_pairs=arguments.holdout_seed_pairs,
                early_holdout_generation=arguments.early_holdout_generation,
                diagnostic_holdout_generations=tuple(
                    arguments.diagnostic_holdout_generations
                ),
                crossplay_reference_generation=(
                    arguments.crossplay_reference_generation
                ),
                log_training_games=arguments.log_training_games,
                checkpoint_path=arguments.checkpoint,
                enforce_population_guard=not arguments.allow_population_outside_guard,
            )
        )
