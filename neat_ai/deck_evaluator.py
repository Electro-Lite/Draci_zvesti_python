import argparse
import copy
import hashlib
import json
import os
import random
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass

import neat

from choice_strategies.choice_strategy_ai_neat import PlayerChoiceStrategyNeat
from core.game_loop import GameResult, run as run_game
from core.player import Player
from display_strategies.display_strategy_none import DisplayStrategyNone
from neat_ai.ai_training_logger import AITrainingLogger, PCMatch
from utils.database_utils import DBUtil


DEFAULT_EVALUATOR_GENERATIONS = 50
DEFAULT_DIAGNOSTIC_HOLDOUT_GENERATIONS = (
    5,
    20,
    35,
)
DEFAULT_CROSSPLAY_REFERENCE_GENERATION = None


@dataclass(frozen=True)
class EvaluatorSettings:
    generations: int = DEFAULT_EVALUATOR_GENERATIONS
    workers: int = 12
    holdout_seed_pairs: int = 20
    early_holdout_generation: int = 5
    diagnostic_holdout_generations: tuple[int, ...] = (
        DEFAULT_DIAGNOSTIC_HOLDOUT_GENERATIONS
    )
    crossplay_reference_generation: int | None = None
    seed: int = 104729
    log_training_games: bool = True

    def __post_init__(self):
        if self.generations < 1:
            raise ValueError("Evaluator generations must be positive")
        if self.workers < 1:
            raise ValueError("Evaluator workers must be positive")
        if self.holdout_seed_pairs < 1:
            raise ValueError("Holdout seed pairs must be positive")
        if not 1 <= self.early_holdout_generation < self.generations:
            raise ValueError(
                "Early holdout generation must be positive and lower than "
                "the final generation"
            )
        invalid_diagnostics = [
            generation
            for generation in self.diagnostic_holdout_generations
            if generation < 1
        ]
        if invalid_diagnostics:
            raise ValueError(
                "Diagnostic holdout generations must be positive: "
                f"{invalid_diagnostics}"
            )
        if (
            self.crossplay_reference_generation is not None
            and not 1
            <= self.crossplay_reference_generation
            < self.generations
        ):
            raise ValueError(
                "Cross-play reference generation must be positive and lower "
                "than the final generation"
            )

    def holdout_checkpoint_generations(self) -> tuple[int, ...]:
        checkpoints = (
            set(self.diagnostic_holdout_generations)
            | {self.early_holdout_generation}
        )
        if self.crossplay_reference_generation is not None:
            checkpoints.add(self.crossplay_reference_generation)
        return tuple(
            generation
            for generation in sorted(checkpoints)
            if generation < self.generations
        )


def _stable_seed(*parts) -> int:
    value = ":".join(str(part) for part in parts)
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def holdout_game_seeds(settings: EvaluatorSettings) -> tuple[int, ...]:
    """Return the common random-number schedule used by every deck matchup."""
    return tuple(
        _stable_seed(settings.seed, "holdout", seed_index)
        for seed_index in range(settings.holdout_seed_pairs)
    )


def fitness_from_result(result: GameResult, perspective_player_id: int) -> float:
    if perspective_player_id == 1:
        own_score = result.player_1_score
        opponent_score = result.player_2_score
    elif perspective_player_id == 2:
        own_score = result.player_2_score
        opponent_score = result.player_1_score
    else:
        raise ValueError(f"Unknown player id: {perspective_player_id}")

    score_difference = own_score - opponent_score
    outcome = 1 if score_difference > 0 else -1 if score_difference < 0 else 0
    return float(100 * outcome + 10 * score_difference)


def _play_training_game(
        genome1_data,
        genome2_data,
        config,
        deck_1,
        deck_2,
        seed: int,
        starting_player_id: int,
):
    genome_id1, genome1 = genome1_data
    genome_id2, genome2 = genome2_data

    player_1 = Player(1, copy.deepcopy(deck_1), PlayerChoiceStrategyNeat)
    player_2 = Player(2, copy.deepcopy(deck_2), PlayerChoiceStrategyNeat)
    player_1.net = neat.nn.FeedForwardNetwork.create(genome1, config)
    player_2.net = neat.nn.FeedForwardNetwork.create(genome2, config)

    result = run_game(
        player_1,
        player_2,
        DisplayStrategyNone,
        seed=seed,
        starting_player_id=starting_player_id,
    )
    return (
        genome_id1,
        fitness_from_result(result, 1),
        genome_id2,
        fitness_from_result(result, 2),
        result,
    )


def _pc_match_row(
        match_guid: str,
        inner_generation: int,
        g1_fitness: float,
        g2_fitness: float,
        result: GameResult,
    phase: str,
    seat_swap: bool,
    deck1_controller_generation: int | None = None,
    deck2_controller_generation: int | None = None,
) -> PCMatch:
    include_action_stats = phase != "training"
    return PCMatch(
        match_dbt_guid=match_guid,
        gen=inner_generation,
        g1_score=g1_fitness,
        g2_score=g2_fitness,
        phase=phase,
        seed=result.seed,
        seat_swap=seat_swap,
        p1_game_score=result.player_1_score,
        p2_game_score=result.player_2_score,
        winner_id=result.winner_id,
        rounds=result.rounds,
        starting_player_id=result.starting_player_id,
        deck1_controller_gen=deck1_controller_generation,
        deck2_controller_gen=deck2_controller_generation,
        p1_card_plays=(
            json.dumps(result.player_1_card_plays, sort_keys=True)
            if include_action_stats else None
        ),
        p2_card_plays=(
            json.dumps(result.player_2_card_plays, sort_keys=True)
            if include_action_stats else None
        ),
        p1_active_ability_uses=(
            json.dumps(result.player_1_active_ability_uses, sort_keys=True)
            if include_action_stats else None
        ),
        p2_active_ability_uses=(
            json.dumps(result.player_2_active_ability_uses, sort_keys=True)
            if include_action_stats else None
        ),
    )


def _evaluate_populations(
        genomes1,
        genomes2,
        config,
        deck_1,
        deck_2,
        match_guid: str | None,
        inner_generation: int,
        settings: EvaluatorSettings,
) -> None:
    genomes1_by_id = dict(genomes1)
    genomes2_by_id = dict(genomes2)
    totals1 = {genome_id: 0.0 for genome_id in genomes1_by_id}
    totals2 = {genome_id: 0.0 for genome_id in genomes2_by_id}
    counts1 = {genome_id: 0 for genome_id in genomes1_by_id}
    counts2 = {genome_id: 0 for genome_id in genomes2_by_id}

    jobs = []
    for genome_id1, genome1 in genomes1:
        for genome_id2, genome2 in genomes2:
            game_seed = _stable_seed(
                settings.seed,
                match_guid or "standalone",
                inner_generation,
                genome_id1,
                genome_id2,
            )
            starting_player_id = 1 if game_seed % 2 == 0 else 2
            jobs.append(
                (
                    (genome_id1, genome1),
                    (genome_id2, genome2),
                    game_seed,
                    starting_player_id,
                )
            )

    logged_games = []
    with ProcessPoolExecutor(max_workers=max(1, settings.workers)) as executor:
        futures = [
            executor.submit(
                _play_training_game,
                genome1_data,
                genome2_data,
                config,
                deck_1,
                deck_2,
                game_seed,
                starting_player_id,
            )
            for genome1_data, genome2_data, game_seed, starting_player_id in jobs
        ]
        for future in as_completed(futures):
            genome_id1, fit1, genome_id2, fit2, result = future.result()
            totals1[genome_id1] += fit1
            totals2[genome_id2] += fit2
            counts1[genome_id1] += 1
            counts2[genome_id2] += 1
            if match_guid and settings.log_training_games:
                logged_games.append(
                    _pc_match_row(
                        match_guid,
                        inner_generation,
                        fit1,
                        fit2,
                        result,
                        phase="training",
                        seat_swap=False,
                    )
                )

    for genome_id, genome in genomes1:
        genome.fitness = totals1[genome_id] / counts1[genome_id]
    for genome_id, genome in genomes2:
        genome.fitness = totals2[genome_id] / counts2[genome_id]

    if logged_games:
        AITrainingLogger().save_pc_matches(logged_games)


def _play_holdout_game(
        genome1,
        genome2,
        config,
        deck_1,
        deck_2,
        seed: int,
        seat_swap: bool,
):
    if seat_swap:
        player_1 = Player(1, copy.deepcopy(deck_2), PlayerChoiceStrategyNeat)
        player_2 = Player(2, copy.deepcopy(deck_1), PlayerChoiceStrategyNeat)
        player_1.net = neat.nn.FeedForwardNetwork.create(genome2, config)
        player_2.net = neat.nn.FeedForwardNetwork.create(genome1, config)
        deck_1_player_id = 2
        deck_2_player_id = 1
    else:
        player_1 = Player(1, copy.deepcopy(deck_1), PlayerChoiceStrategyNeat)
        player_2 = Player(2, copy.deepcopy(deck_2), PlayerChoiceStrategyNeat)
        player_1.net = neat.nn.FeedForwardNetwork.create(genome1, config)
        player_2.net = neat.nn.FeedForwardNetwork.create(genome2, config)
        deck_1_player_id = 1
        deck_2_player_id = 2

    result = run_game(
        player_1,
        player_2,
        DisplayStrategyNone,
        seed=seed,
        starting_player_id=1,
    )
    return (
        fitness_from_result(result, deck_1_player_id),
        fitness_from_result(result, deck_2_player_id),
        result,
        seat_swap,
    )


def _evaluate_holdout(
        genome1,
        genome2,
        config,
        deck_1,
    deck_2,
    match_guid: str | None,
    settings: EvaluatorSettings,
    controller_generation_1: int,
    phase: str,
    controller_generation_2: int | None = None,
) -> tuple[float, float]:
    if controller_generation_2 is None:
        controller_generation_2 = controller_generation_1
    jobs = []
    for game_seed in holdout_game_seeds(settings):
        jobs.append((game_seed, False))
        jobs.append((game_seed, True))

    deck1_scores = []
    deck2_scores = []
    logged_games = []
    with ProcessPoolExecutor(max_workers=max(1, settings.workers)) as executor:
        futures = [
            executor.submit(
                _play_holdout_game,
                genome1,
                genome2,
                config,
                deck_1,
                deck_2,
                game_seed,
                seat_swap,
            )
            for game_seed, seat_swap in jobs
        ]
        for future in as_completed(futures):
            fit1, fit2, result, seat_swap = future.result()
            deck1_scores.append(fit1)
            deck2_scores.append(fit2)
            if match_guid:
                logged_games.append(
                    _pc_match_row(
                        match_guid,
                        max(
                            controller_generation_1,
                            controller_generation_2,
                        ),
                        fit1,
                        fit2,
                        result,
                        phase=phase,
                        seat_swap=seat_swap,
                        deck1_controller_generation=controller_generation_1,
                        deck2_controller_generation=controller_generation_2,
                    )
                )

    if logged_games:
        AITrainingLogger().save_pc_matches(logged_games)
    return (
        sum(deck1_scores) / len(deck1_scores),
        sum(deck2_scores) / len(deck2_scores),
    )


def train_deck(
        deck1,
        deck2,
        match_dbt_guid: str = None,
        settings: EvaluatorSettings = None,
) -> list[float]:
    settings = settings or EvaluatorSettings()
    local_dir = os.path.dirname(__file__)
    config_path = os.path.join(local_dir, "configs/neat_config_evaluator.txt")
    config = neat.Config(
        neat.DefaultGenome,
        neat.DefaultReproduction,
        neat.DefaultSpeciesSet,
        neat.DefaultStagnation,
        config_path,
    )

    random.seed(settings.seed)
    population1 = neat.Population(config)
    population2 = neat.Population(config)
    best_genome2 = None
    best_genome2_fitness = float("-inf")
    best_genome1 = None
    best_genome1_fitness = float("-inf")
    checkpoint_controllers = {}
    inner_generation = 0

    def evaluate_population1(genomes1, neat_config):
        nonlocal best_genome1, best_genome1_fitness
        nonlocal best_genome2, best_genome2_fitness
        nonlocal checkpoint_controllers, inner_generation
        inner_generation += 1

        def evaluate_population2(genomes2, _):
            _evaluate_populations(
                genomes1,
                genomes2,
                neat_config,
                deck1,
                deck2,
                match_dbt_guid,
                inner_generation,
                settings,
            )

        generation_winner2 = population2.run(evaluate_population2, 1)
        if generation_winner2.fitness > best_genome2_fitness:
            best_genome2 = copy.deepcopy(generation_winner2)
            best_genome2_fitness = generation_winner2.fitness

        generation_winner1 = max(genomes1, key=lambda item: item[1].fitness)[1]
        if generation_winner1.fitness > best_genome1_fitness:
            best_genome1 = copy.deepcopy(generation_winner1)
            best_genome1_fitness = generation_winner1.fitness

        if inner_generation in settings.holdout_checkpoint_generations():
            checkpoint_controllers[inner_generation] = (
                copy.deepcopy(best_genome1),
                copy.deepcopy(best_genome2),
            )

    winner1 = population1.run(evaluate_population1, settings.generations)
    if best_genome2 is None:
        raise RuntimeError("Evaluator did not produce a second-player controller")

    for checkpoint_generation in settings.holdout_checkpoint_generations():
        controllers = checkpoint_controllers.get(checkpoint_generation)
        if controllers is None:
            raise RuntimeError(
                "Missing controller checkpoint at inner generation "
                f"{checkpoint_generation}"
            )
        _evaluate_holdout(
            controllers[0],
            controllers[1],
            config,
            deck1,
            deck2,
            match_dbt_guid,
            settings,
            controller_generation_1=checkpoint_generation,
            phase=(
                "holdout_early"
                if checkpoint_generation == settings.early_holdout_generation
                else "holdout_checkpoint"
            ),
        )

    score1, score2 = _evaluate_holdout(
        winner1,
        best_genome2,
        config,
        deck1,
        deck2,
        match_dbt_guid,
        settings,
        controller_generation_1=settings.generations,
        phase="holdout",
    )

    reference_generation = settings.crossplay_reference_generation
    if reference_generation is not None:
        reference_controllers = checkpoint_controllers.get(reference_generation)
        if reference_controllers is None:
            raise RuntimeError(
                "Missing cross-play controller checkpoint at inner generation "
                f"{reference_generation}"
            )
        _evaluate_holdout(
            winner1,
            reference_controllers[1],
            config,
            deck1,
            deck2,
            match_dbt_guid,
            settings,
            controller_generation_1=settings.generations,
            controller_generation_2=reference_generation,
            phase="holdout_cross",
        )
        _evaluate_holdout(
            reference_controllers[0],
            best_genome2,
            config,
            deck1,
            deck2,
            match_dbt_guid,
            settings,
            controller_generation_1=reference_generation,
            controller_generation_2=settings.generations,
            phase="holdout_cross",
        )
    return [score1, score2]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate two decks")
    parser.add_argument("deck_id1")
    parser.add_argument("deck_id2")
    parser.add_argument("--seed", type=int, default=104729)
    parser.add_argument(
        "--generations",
        type=int,
        default=DEFAULT_EVALUATOR_GENERATIONS,
    )
    parser.add_argument("--workers", type=int, default=12)
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
    args = parser.parse_args()
    scores = train_deck(
        DBUtil().load_deck(args.deck_id1),
        DBUtil().load_deck(args.deck_id2),
        settings=EvaluatorSettings(
            generations=args.generations,
            workers=args.workers,
            holdout_seed_pairs=args.holdout_seed_pairs,
            early_holdout_generation=args.early_holdout_generation,
            diagnostic_holdout_generations=tuple(
                args.diagnostic_holdout_generations
            ),
            crossplay_reference_generation=(
                args.crossplay_reference_generation or None
            ),
            seed=args.seed,
        ),
    )
    print(f"deck 1 fitness: {scores[0]:.3f}")
    print(f"deck 2 fitness: {scores[1]:.3f}")
