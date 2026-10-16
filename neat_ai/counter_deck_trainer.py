"""Persistently coevolve counter decks and controllers against one fixed deck."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import pickle
import random
import re
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time

import neat

from choice_strategies.choice_strategy_ai_neat import PlayerChoiceStrategyNeat
from core.game_loop import run as run_game
from core.player import Player
from display_strategies.display_strategy_none import DisplayStrategyNone
from neat_ai.deck_builder import build_deck
from neat_ai.deck_evaluator import fitness_from_result
from neat_ai.player_artifacts import export_player_artifact
from neat_ai.training_telemetry import emit_training_event
from utils.database_utils import DBUtil


@dataclass(frozen=True)
class CounterDeckTrainerSettings:
    counter_generations: int = 5
    controller_generations: int = 40
    workers: int = 8
    evaluation_games: int = 1_000
    seed: int = 104729
    run_label: str = "counter-deck-lab"

    def __post_init__(self):
        if not 1 <= self.counter_generations <= 1_000:
            raise ValueError("Counter generations must be between 1 and 1000")
        if not 1 <= self.controller_generations <= 10_000:
            raise ValueError("Controller generations must be between 1 and 10000")
        if not 1 <= self.workers <= 128:
            raise ValueError("Workers must be between 1 and 128")
        if not 2 <= self.evaluation_games <= 100_000 or self.evaluation_games % 2:
            raise ValueError(
                "Evaluation games must be an even number between 2 and 100000"
            )


def controller_generation_targets(
    counter_generations: int,
    controller_generations: int,
) -> tuple[int, ...]:
    """Distribute one persistent controller run across counter generations."""
    if counter_generations < 1 or controller_generations < 1:
        raise ValueError("Generation counts must be positive")
    return tuple(
        min(
            controller_generations,
            math.ceil(controller_generations * generation / counter_generations),
        )
        for generation in range(1, counter_generations + 1)
    )


def _stable_seed(*parts) -> int:
    digest = hashlib.sha256(":".join(map(str, parts)).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def _bounded_results(function, jobs, workers):
    """Yield process results without materializing very large job lists."""
    iterator = iter(jobs)
    limit = max(1, workers) * 4
    with ProcessPoolExecutor(max_workers=max(1, workers)) as executor:
        pending = set()
        for _ in range(limit):
            try:
                pending.add(executor.submit(function, *next(iterator)))
            except StopIteration:
                break
        while pending:
            completed, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                yield future.result()
                try:
                    pending.add(executor.submit(function, *next(iterator)))
                except StopIteration:
                    pass


def _play_controller_game(
    subject_genome_data,
    counter_genome_data,
    controller_config,
    subject_deck,
    counter_deck,
    seed,
    seat_swap,
):
    subject_id, subject_genome = subject_genome_data
    counter_id, counter_genome = counter_genome_data
    if seat_swap:
        player_1 = Player(1, copy.deepcopy(counter_deck), PlayerChoiceStrategyNeat)
        player_2 = Player(2, copy.deepcopy(subject_deck), PlayerChoiceStrategyNeat)
        player_1.net = neat.nn.FeedForwardNetwork.create(counter_genome, controller_config)
        player_2.net = neat.nn.FeedForwardNetwork.create(subject_genome, controller_config)
        subject_player_id = 2
        counter_player_id = 1
    else:
        player_1 = Player(1, copy.deepcopy(subject_deck), PlayerChoiceStrategyNeat)
        player_2 = Player(2, copy.deepcopy(counter_deck), PlayerChoiceStrategyNeat)
        player_1.net = neat.nn.FeedForwardNetwork.create(subject_genome, controller_config)
        player_2.net = neat.nn.FeedForwardNetwork.create(counter_genome, controller_config)
        subject_player_id = 1
        counter_player_id = 2
    result = run_game(
        player_1,
        player_2,
        DisplayStrategyNone,
        seed=seed,
        starting_player_id=1,
    )
    return (
        subject_id,
        fitness_from_result(result, subject_player_id),
        counter_id,
        fitness_from_result(result, counter_player_id),
    )


def _controller_jobs(
    subject_genomes,
    counter_genomes,
    controller_config,
    subject_deck,
    counter_decks,
    seed,
    counter_generation,
    controller_generation,
):
    for subject_index, subject_genome in enumerate(subject_genomes):
        for counter_index, counter_genome in enumerate(counter_genomes):
            deck = counter_decks[
                (subject_index * len(counter_genomes) + counter_index)
                % len(counter_decks)
            ]
            game_seed = _stable_seed(
                seed,
                "controller",
                counter_generation,
                controller_generation,
                subject_genome[0],
                counter_genome[0],
                deck.id,
            )
            yield (
                subject_genome,
                counter_genome,
                controller_config,
                subject_deck,
                deck,
                game_seed,
                bool(game_seed % 2),
            )


def _evaluate_controllers(
    subject_genomes,
    counter_genomes,
    controller_config,
    subject_deck,
    counter_decks,
    settings,
    counter_generation,
    controller_generation,
):
    subject_by_id = dict(subject_genomes)
    counter_by_id = dict(counter_genomes)
    subject_totals = {genome_id: 0.0 for genome_id in subject_by_id}
    counter_totals = {genome_id: 0.0 for genome_id in counter_by_id}
    subject_counts = {genome_id: 0 for genome_id in subject_by_id}
    counter_counts = {genome_id: 0 for genome_id in counter_by_id}
    jobs = _controller_jobs(
        subject_genomes,
        counter_genomes,
        controller_config,
        subject_deck,
        counter_decks,
        settings.seed,
        counter_generation,
        controller_generation,
    )
    for subject_id, subject_fitness, counter_id, counter_fitness in _bounded_results(
        _play_controller_game,
        jobs,
        settings.workers,
    ):
        subject_totals[subject_id] += subject_fitness
        counter_totals[counter_id] += counter_fitness
        subject_counts[subject_id] += 1
        counter_counts[counter_id] += 1
    for genome_id, genome in subject_genomes:
        genome.fitness = subject_totals[genome_id] / subject_counts[genome_id]
    for genome_id, genome in counter_genomes:
        genome.fitness = counter_totals[genome_id] / counter_counts[genome_id]


def _play_candidate_game(
    builder_id,
    counter_deck,
    subject_deck,
    subject_controller,
    counter_controller,
    controller_config,
    seed,
    seat_swap,
):
    if seat_swap:
        player_1 = Player(1, copy.deepcopy(counter_deck), PlayerChoiceStrategyNeat)
        player_2 = Player(2, copy.deepcopy(subject_deck), PlayerChoiceStrategyNeat)
        player_1.net = neat.nn.FeedForwardNetwork.create(counter_controller, controller_config)
        player_2.net = neat.nn.FeedForwardNetwork.create(subject_controller, controller_config)
        subject_player_id = 2
        counter_player_id = 1
    else:
        player_1 = Player(1, copy.deepcopy(subject_deck), PlayerChoiceStrategyNeat)
        player_2 = Player(2, copy.deepcopy(counter_deck), PlayerChoiceStrategyNeat)
        player_1.net = neat.nn.FeedForwardNetwork.create(subject_controller, controller_config)
        player_2.net = neat.nn.FeedForwardNetwork.create(counter_controller, controller_config)
        subject_player_id = 1
        counter_player_id = 2
    result = run_game(
        player_1,
        player_2,
        DisplayStrategyNone,
        seed=seed,
        starting_player_id=1,
    )
    subject_score = (
        result.player_1_score if subject_player_id == 1 else result.player_2_score
    )
    counter_score = (
        result.player_1_score if counter_player_id == 1 else result.player_2_score
    )
    outcome = "subject_win" if subject_score > counter_score else "counter_win" if counter_score > subject_score else "draw"
    return (
        builder_id,
        fitness_from_result(result, counter_player_id),
        outcome,
    )


def _candidate_jobs(
    decks_by_id,
    subject_deck,
    subject_controller,
    counter_controller,
    controller_config,
    settings,
    generation,
):
    for builder_id, deck in decks_by_id.items():
        for game_index in range(settings.evaluation_games):
            yield (
                builder_id,
                deck,
                subject_deck,
                subject_controller,
                counter_controller,
                controller_config,
                _stable_seed(settings.seed, "candidate", generation, builder_id, game_index),
                bool(game_index % 2),
            )


def _card_ids(deck) -> tuple[str, ...]:
    return tuple(str(card.id) for card in deck.cards)


def _candidate_row(builder_id, deck, stats, subject_cards, generation):
    games = stats["subject_wins"] + stats["draws"] + stats["counter_wins"]
    counter_rate = stats["counter_wins"] / games if games else 0.0
    cards = _card_ids(deck)
    return {
        "builder_id": builder_id,
        "deck_id": deck.id,
        "deck_name": deck.name,
        "generation": generation,
        "cards": list(cards),
        "card_names": [str(getattr(card, "name", card.id)) for card in deck.cards],
        "shared_cards": sum((Counter(subject_cards) & Counter(cards)).values()),
        "games": games,
        "subject_wins": stats["subject_wins"],
        "draws": stats["draws"],
        "counter_wins": stats["counter_wins"],
        "counter_win_rate": counter_rate,
        "counter_fitness": stats["fitness"] / games if games else -1_000_000.0,
    }


def build_summary(
    subject_deck,
    settings,
    history,
    elapsed_seconds,
    artifact_path=None,
    player_artifacts=(),
):
    final_rows = history[-1]["candidates"] if history else []
    subject_wins = sum(row["subject_wins"] for row in final_rows)
    draws = sum(row["draws"] for row in final_rows)
    counter_wins = sum(row["counter_wins"] for row in final_rows)
    games = subject_wins + draws + counter_wins
    top_counter = (
        max(
            final_rows,
            key=lambda row: (row["counter_win_rate"], row["counter_fitness"]),
        )
        if final_rows
        else None
    )
    skill_evaluations = [
        {
            "generation": item["generation"],
            "ai_wins": item["subject_wins"],
            "draws": item["draws"],
            "random_wins": item["counter_wins"],
            "subject_wins": item["subject_wins"],
            "counter_wins": item["counter_wins"],
            "games": item["subject_wins"] + item["draws"] + item["counter_wins"],
        }
        for item in history
    ]
    return {
        "kind": "counter_deck_training",
        "deck_id": subject_deck.id,
        "deck_name": subject_deck.name,
        "subject_cards": list(_card_ids(subject_deck)),
        "settings": asdict(settings),
        "best_fitness": top_counter["counter_fitness"] if top_counter else None,
        "elapsed_seconds": elapsed_seconds,
        "artifact_path": str(artifact_path) if artifact_path else None,
        "evaluation": {
            "games": games,
            "ai_wins": subject_wins,
            "draws": draws,
            "random_wins": counter_wins,
            "subject_wins": subject_wins,
            "counter_wins": counter_wins,
            "ai_win_rate": subject_wins / games if games else 0.0,
        },
        "skill_evaluations": skill_evaluations,
        "top_counter": top_counter,
        "counter_matchups": final_rows,
        "player_artifacts": [str(path) for path in player_artifacts],
    }


def train_counter_decks(subject_deck, settings: CounterDeckTrainerSettings | None = None):
    if subject_deck is None:
        raise ValueError("Selected deck does not exist")
    subject_deck.validate()
    settings = settings or CounterDeckTrainerSettings()
    local_dir = Path(__file__).resolve().parent
    artifact_root = Path(os.environ.get("TRAINING_ARTIFACT_DIR", local_dir))
    builder_config = neat.Config(
        neat.DefaultGenome,
        neat.DefaultReproduction,
        neat.DefaultSpeciesSet,
        neat.DefaultStagnation,
        str(local_dir / "configs" / "neat_config_builder.txt"),
    )
    controller_config = neat.Config(
        neat.DefaultGenome,
        neat.DefaultReproduction,
        neat.DefaultSpeciesSet,
        neat.DefaultStagnation,
        str(local_dir / "configs" / "neat_config_evaluator.txt"),
    )
    random.seed(settings.seed)
    builder_population = neat.Population(builder_config)
    subject_population = neat.Population(controller_config)
    counter_population = neat.Population(controller_config)
    targets = controller_generation_targets(
        settings.counter_generations,
        settings.controller_generations,
    )
    history = []
    controller_generation = 0
    best_subject_controller = None
    best_counter_controller = None
    started_at = time()
    summary_path = os.environ.get("PLAYER_TRAINING_SUMMARY_PATH")
    emit_training_event(
        "run_started",
        phase="counter_evolution",
        generation=0,
        total_generations=settings.counter_generations,
        phase_progress=0.0,
        deck_id=subject_deck.id,
    )

    def evaluate_counter_generation(builder_genomes, neat_builder_config):
        nonlocal controller_generation
        nonlocal best_subject_controller, best_counter_controller
        outer_generation = len(history) + 1
        decks_by_id = {}
        valid_genomes = {}
        for builder_id, genome in builder_genomes:
            deck = build_deck(
                neat.nn.FeedForwardNetwork.create(genome, neat_builder_config)
            )
            deck.id = f"counter-g{outer_generation}-{builder_id}"
            deck.name = f"Counter G{outer_generation} #{builder_id}"
            genome.fitness = -1_000_000.0
            if len(deck.cards) >= 10:
                decks_by_id[builder_id] = deck
                valid_genomes[builder_id] = genome
        if not decks_by_id:
            raise RuntimeError("Counter evolution produced no legal candidate decks")

        target_generation = targets[outer_generation - 1]
        generations_this_cycle = target_generation - controller_generation

        def evaluate_subject_population(subject_genomes, neat_controller_config):
            nonlocal controller_generation, best_counter_controller

            def evaluate_counter_population(counter_genomes, _):
                _evaluate_controllers(
                    subject_genomes,
                    counter_genomes,
                    neat_controller_config,
                    subject_deck,
                    tuple(decks_by_id.values()),
                    settings,
                    outer_generation,
                    controller_generation + 1,
                )

            best_counter_controller = copy.deepcopy(
                counter_population.run(evaluate_counter_population, 1)
            )
            controller_generation += 1
            emit_training_event(
                "phase_progress",
                phase="counter_controller_training",
                generation=outer_generation,
                total_generations=settings.counter_generations,
                completed=controller_generation,
                total=settings.controller_generations,
                phase_progress=(
                    controller_generation / settings.controller_generations
                ),
            )

        if generations_this_cycle:
            best_subject_controller = copy.deepcopy(
                subject_population.run(
                    evaluate_subject_population,
                    generations_this_cycle,
                )
            )
        if best_subject_controller is None or best_counter_controller is None:
            raise RuntimeError("Persistent controller evolution produced no controllers")

        stats = {
            builder_id: {
                "fitness": 0.0,
                "subject_wins": 0,
                "draws": 0,
                "counter_wins": 0,
            }
            for builder_id in decks_by_id
        }
        jobs = _candidate_jobs(
            decks_by_id,
            subject_deck,
            best_subject_controller,
            best_counter_controller,
            controller_config,
            settings,
            outer_generation,
        )
        completed = 0
        total = len(decks_by_id) * settings.evaluation_games
        for builder_id, counter_fitness, outcome in _bounded_results(
            _play_candidate_game,
            jobs,
            settings.workers,
        ):
            stats[builder_id]["fitness"] += counter_fitness
            stats[builder_id][
                "subject_wins" if outcome == "subject_win" else "counter_wins" if outcome == "counter_win" else "draws"
            ] += 1
            completed += 1
            if completed % max(1, total // 20) == 0 or completed == total:
                emit_training_event(
                    "phase_progress",
                    phase="counter_evolution",
                    generation=outer_generation,
                    total_generations=settings.counter_generations,
                    completed=completed,
                    total=total,
                    phase_progress=((outer_generation - 1) + completed / total)
                    / settings.counter_generations,
                )
        rows = []
        subject_cards = _card_ids(subject_deck)
        for builder_id, deck in decks_by_id.items():
            row = _candidate_row(
                builder_id,
                deck,
                stats[builder_id],
                subject_cards,
                outer_generation,
            )
            valid_genomes[builder_id].fitness = row["counter_fitness"]
            rows.append(row)
        aggregate = {
            "generation": outer_generation,
            "controller_generation": controller_generation,
            "subject_wins": sum(row["subject_wins"] for row in rows),
            "draws": sum(row["draws"] for row in rows),
            "counter_wins": sum(row["counter_wins"] for row in rows),
            "candidates": rows,
        }
        history.append(aggregate)
        partial = build_summary(subject_deck, settings, history, time() - started_at)
        if summary_path:
            Path(summary_path).write_text(json.dumps(partial, indent=2, sort_keys=True))
        emit_training_event(
            "generation_completed",
            phase="counter_evolution",
            generation=outer_generation,
            total_generations=settings.counter_generations,
            phase_progress=outer_generation / settings.counter_generations,
            best_score=max(row["counter_fitness"] for row in rows),
        )

    winner = builder_population.run(
        evaluate_counter_generation,
        settings.counter_generations,
    )
    output_dir = artifact_root / "trained_ai"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "-", settings.run_label).strip("-")
    artifact_path = output_dir / f"counter_{subject_deck.id}_{safe_label or 'run'}.pickle"
    with artifact_path.open("wb") as artifact_file:
        pickle.dump(
            {
                "builder": winner,
                "subject_controller": best_subject_controller,
                "counter_controller": best_counter_controller,
            },
            artifact_file,
        )
    subject_artifact = export_player_artifact(
        output_dir,
        best_subject_controller,
        subject_deck,
        mission="counter",
        role="subject",
        run_label=settings.run_label,
        generation=settings.controller_generations,
        display_name=(
            f"{subject_deck.name} · counter training gen "
            f"{settings.controller_generations}"
        ),
    )
    elapsed = time() - started_at
    summary = build_summary(
        subject_deck,
        settings,
        history,
        elapsed,
        artifact_path,
        (subject_artifact.path,),
    )
    if summary_path:
        Path(summary_path).write_text(json.dumps(summary, indent=2, sort_keys=True))
    emit_training_event(
        "run_completed",
        phase="completed",
        generation=settings.counter_generations,
        total_generations=settings.counter_generations,
        phase_progress=1.0,
        elapsed_seconds=elapsed,
        best_score=summary["best_fitness"],
        evaluation_games=sum(
            row["games"] for generation in history for row in generation["candidates"]
        ),
    )
    return summary


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evolve persistent counter decks and controllers against one deck"
    )
    parser.add_argument("deck_id")
    parser.add_argument("--counter-generations", type=int, default=5)
    parser.add_argument("--controller-generations", type=int, default=40)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--evaluation-games", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=104729)
    parser.add_argument("--run-label", default="counter-deck-lab")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    train_counter_decks(
        DBUtil().load_deck(arguments.deck_id),
        CounterDeckTrainerSettings(
            counter_generations=arguments.counter_generations,
            controller_generations=arguments.controller_generations,
            workers=arguments.workers,
            evaluation_games=arguments.evaluation_games,
            seed=arguments.seed,
            run_label=arguments.run_label,
        ),
    )
