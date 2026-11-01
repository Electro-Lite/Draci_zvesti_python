"""Evolve counter-deck compositions directly against one fixed user deck.

This mission preserves the persistent subject/counter controller coevolution
and seat-balanced candidate validation from ``counter_deck_trainer``.  Only
the outer optimizer changes: legal card multisets are evolved directly instead
of being emitted by a NEAT deck-builder network.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import pickle
import random
from pathlib import Path
from time import time

import neat

from cards.power import Power
from neat_ai.composition_evolution import (
    CompositionEvolutionSettings,
    EvaluatedDeckGenome,
    eligible_cards,
    initial_population,
    next_population,
)
from neat_ai.config_profiles import config_path
from neat_ai.counter_deck_trainer import (
    CounterDeckTrainerSettings,
    _bounded_results,
    _candidate_jobs,
    _candidate_row,
    _card_ids,
    _evaluate_controllers,
    _play_candidate_game,
    build_summary,
    controller_generation_targets,
)
from neat_ai.player_artifacts import export_player_artifact, safe_artifact_segment
from neat_ai.training_telemetry import emit_training_event
from utils.database_utils import DBUtil


OPTIMIZER_NAME = "composition-ga-v2"


def train_counter_decks_v2(
    subject_deck,
    settings: CounterDeckTrainerSettings | None = None,
    evolution_settings: CompositionEvolutionSettings | None = None,
):
    """Train direct counter compositions and persistent player controllers."""
    if subject_deck is None:
        raise ValueError("Selected deck does not exist")
    subject_deck.validate()
    settings = settings or CounterDeckTrainerSettings()
    evolution_settings = evolution_settings or CompositionEvolutionSettings()
    local_dir = Path(__file__).resolve().parent
    artifact_root = Path(os.environ.get("TRAINING_ARTIFACT_DIR", local_dir))
    controller_config = neat.Config(
        neat.DefaultGenome,
        neat.DefaultReproduction,
        neat.DefaultSpeciesSet,
        neat.DefaultStagnation,
        str(config_path("evaluator")),
    )
    card_pool = eligible_cards(
        DBUtil().get_all_cards(),
        max_power=Power(settings.max_card_power),
        banned_card_ids=settings.banned_card_ids,
    )
    if not card_pool:
        raise RuntimeError("No eligible player cards are available for counter evolution")

    rng = random.Random(settings.seed)
    population = initial_population(card_pool, rng, evolution_settings)
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
    final_evaluated: list[EvaluatedDeckGenome] = []
    started_at = time()
    summary_path = os.environ.get("PLAYER_TRAINING_SUMMARY_PATH")
    emit_training_event(
        "run_started",
        phase="counter_evolution",
        generation=0,
        total_generations=settings.counter_generations,
        phase_progress=0.0,
        deck_id=subject_deck.id,
        optimizer=OPTIMIZER_NAME,
    )

    for outer_generation in range(1, settings.counter_generations + 1):
        decks_by_id = {}
        genomes_by_id = {}
        id_offset = (outer_generation - 1) * evolution_settings.population_size
        for index, genome in enumerate(population):
            candidate_id = id_offset + index
            deck = genome.to_deck(
                card_pool,
                name=f"Counter v2 G{outer_generation} #{candidate_id}",
            )
            deck.id = f"counter-v2-g{outer_generation}-{candidate_id}"
            decks_by_id[candidate_id] = deck
            genomes_by_id[candidate_id] = genome

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
                phase_progress=controller_generation / settings.controller_generations,
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
            candidate_id: {
                "fitness": 0.0,
                "subject_wins": 0,
                "draws": 0,
                "counter_wins": 0,
            }
            for candidate_id in decks_by_id
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
        for candidate_id, counter_fitness, outcome in _bounded_results(
            _play_candidate_game,
            jobs,
            settings.workers,
        ):
            stats[candidate_id]["fitness"] += counter_fitness
            outcome_key = {
                "subject_win": "subject_wins",
                "counter_win": "counter_wins",
                "draw": "draws",
            }[outcome]
            stats[candidate_id][outcome_key] += 1
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
        final_evaluated = []
        for candidate_id, deck in decks_by_id.items():
            row = _candidate_row(
                candidate_id,
                deck,
                stats[candidate_id],
                subject_cards,
                outer_generation,
            )
            rows.append(row)
            final_evaluated.append(
                EvaluatedDeckGenome(
                    genomes_by_id[candidate_id],
                    row["counter_fitness"],
                )
            )
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
        partial["optimizer"] = OPTIMIZER_NAME
        partial["composition_evolution"] = {
            key: value
            for key, value in vars(evolution_settings).items()
        }
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
        if outer_generation < settings.counter_generations:
            population = next_population(
                final_evaluated,
                card_pool,
                rng,
                evolution_settings,
            )

    winner = max(final_evaluated, key=lambda item: item.fitness)
    output_dir = artifact_root / "trained_ai"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_deck = safe_artifact_segment(subject_deck.id, "deck")
    safe_label = safe_artifact_segment(settings.run_label, "run")
    artifact_path = output_dir / f"counter_v2_{safe_deck}_{safe_label}.pickle"
    with artifact_path.open("wb") as artifact_file:
        pickle.dump(
            {
                "optimizer": OPTIMIZER_NAME,
                "composition": winner.genome.cards,
                "fitness": winner.fitness,
                "subject_controller": best_subject_controller,
                "counter_controller": best_counter_controller,
            },
            artifact_file,
        )
    subject_artifact = export_player_artifact(
        output_dir,
        best_subject_controller,
        subject_deck,
        mission="counter-v2",
        role="subject",
        run_label=settings.run_label,
        generation=settings.controller_generations,
        display_name=(
            f"{subject_deck.name} · counter v2 training gen "
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
    summary["optimizer"] = OPTIMIZER_NAME
    summary["composition_evolution"] = {
        key: value for key, value in vars(evolution_settings).items()
    }
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
        optimizer=OPTIMIZER_NAME,
    )
    return summary


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evolve direct counter-deck compositions against one deck"
    )
    parser.add_argument("deck_id")
    parser.add_argument("--counter-generations", type=int, default=5)
    parser.add_argument("--controller-generations", type=int, default=40)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--evaluation-games", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=104729)
    parser.add_argument("--run-label", default="counter-v2")
    parser.add_argument("--max-card-power", type=int, choices=range(3), default=2)
    parser.add_argument("--banned-card-id", action="append", default=[])
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    train_counter_decks_v2(
        DBUtil().load_deck(arguments.deck_id),
        CounterDeckTrainerSettings(
            counter_generations=arguments.counter_generations,
            controller_generations=arguments.controller_generations,
            workers=arguments.workers,
            evaluation_games=arguments.evaluation_games,
            seed=arguments.seed,
            run_label=arguments.run_label,
            max_card_power=arguments.max_card_power,
            banned_card_ids=tuple(arguments.banned_card_id),
        ),
    )


__all__ = ("train_counter_decks_v2", "CounterDeckTrainerSettings")
