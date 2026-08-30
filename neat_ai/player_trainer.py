# https://neat-python.readthedocs.io/en/latest/xor_example.html
import os
from time import time, ctime
import copy
import argparse
import json
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from concurrent.futures import ProcessPoolExecutor, as_completed

import neat
import pickle

from core.game_loop         import run as run_game
from core.player            import Player
from utils.database_utils   import DBUtil
from choice_strategies.choice_strategy_ai_neat      import PlayerChoiceStrategyNeat
from choice_strategies.choice_strategy_ai_random    import ChoiceStrategyAIRandom
from display_strategies.display_strategy_none   import DisplayStrategyNone
from neat_ai.deck_evaluator import DEFAULT_EVALUATOR_GENERATIONS, fitness_from_result


@dataclass(frozen=True)
class PlayerTrainerSettings:
    generations: int = DEFAULT_EVALUATOR_GENERATIONS
    workers: int = 12
    evaluation_games: int = 100
    seed: int = 104729
    run_label: str = "player-deck"

    def __post_init__(self):
        if self.generations < 1:
            raise ValueError("Generations must be positive")
        if self.workers < 1:
            raise ValueError("Workers must be positive")
        if self.evaluation_games < 1:
            raise ValueError("Evaluation games must be positive")


# Worker-local globals (populated by initializer)
_WORKER_DECK = None
_SETTINGS = PlayerTrainerSettings()

def evaluate_match(genome1_data, genome2_data, config, deck_1, deck_2):
    genome_id1, genome1 = genome1_data
    genome_id2, genome2 = genome2_data

    player_1 = Player(1, deck_1, PlayerChoiceStrategyNeat)
    player_2 = Player(2, deck_2, PlayerChoiceStrategyNeat)
    player_1.net = neat.nn.FeedForwardNetwork.create(genome1, config)
    player_2.net = neat.nn.FeedForwardNetwork.create(genome2, config)

    result = run_game(player_1, player_2, DisplayStrategyNone)
    player_1_fitness = fitness_from_result(result, 1)
    player_2_fitness = fitness_from_result(result, 2)

    return genome_id1, player_1_fitness, genome_id2, player_2_fitness

def eval_genomes_parallel(genomes, config):
    global generation
    generation += 1
    print(f"generation: {generation}")
    # initialize fitness
    for _, genome in genomes:
        genome.fitness = 0
    matches = []
    matches_count_10_percent = 0
    for i, g1 in enumerate(genomes):
        for g2 in genomes[i+1:]:
            matches.append((g1, g2))
    matches_count_10_percent = max(1, len(matches) // 10)
    match_counts = {genome_id: 0 for genome_id, _ in genomes}
    with ProcessPoolExecutor(max_workers=_SETTINGS.workers) as executor:
        futures = [executor.submit(evaluate_match, g1, g2, config, copy.deepcopy(_WORKER_DECK), copy.deepcopy(_WORKER_DECK)) for g1, g2 in matches]

        for i, f in enumerate(as_completed(futures), 1):
            g1_id, g1_fit, g2_id, g2_fit = f.result()
            genome1 = dict(genomes)[g1_id]
            genome2 = dict(genomes)[g2_id]
            genome1.fitness += g1_fit
            genome2.fitness += g2_fit
            match_counts[g1_id] += 1
            match_counts[g2_id] += 1

            if i % matches_count_10_percent == 0 or i == len(matches):
                best_genome = max(genomes, key=lambda g: g[1].fitness if g[1].fitness is not None else float("-inf"))
                print(f"generation: {generation} |  trainning round: {i}/{len(matches)} |  top_fitness: {best_genome[1].fitness}  | time: {ctime(time())}")

    for genome_id, genome in genomes:
        genome.fitness /= match_counts[genome_id]
    print(f"generation {generation} completed")


def _test_pickle_vs_rnd(config, winner, rounds: int, seed: int):
    print("running evaluation test")
    global _WORKER_DECK
    winner_net = neat.nn.FeedForwardNetwork.create(winner, config)
    score = [0,0,0]
    bar_length = 30
    for i in range(0, rounds):
        if i % max(1, rounds // 100) == 0 or i == rounds - 1:
            progress = i / rounds
            percent = int(progress * 100)
            filled = int(bar_length * progress)
            bar = "#" * filled + "-" * (bar_length - filled)
            print(f"\rTesting progress: |{bar}| {percent}%", end="", flush=True)

        player_1        = Player(1, copy.deepcopy(_WORKER_DECK), PlayerChoiceStrategyNeat)
        player_1.net    = winner_net
        player_2        = Player(2, copy.deepcopy(_WORKER_DECK), ChoiceStrategyAIRandom)

        game_seed = seed + i
        run_game(
            player_1,
            player_2,
            DisplayStrategyNone,
            seed=game_seed,
            starting_player_id=1 if i % 2 == 0 else 2,
        )

        if  (player_1.score > player_2.score):
            score[0]+=1
        elif(player_1.score < player_2.score):
            score[2]+=1
        else:
            score[1]+=1

    print("\nfinal score is:")
    print("ai   :" + str((score[0] / rounds) * 100) + "%")
    print("draws:" + str((score[1] / rounds) * 100) + "%")
    print("rnd  :" + str((score[2] / rounds) * 100) + "%")
    return {
        "games": rounds,
        "ai_wins": score[0],
        "draws": score[1],
        "random_wins": score[2],
        "ai_win_rate": score[0] / rounds,
    }


def train_deck(_deck, settings: PlayerTrainerSettings | None = None):
    if _deck is None:
        raise ValueError("Deck does not exist")
    _deck.validate()
    settings = settings or PlayerTrainerSettings()
    local_dir   = os.path.dirname(__file__)
    config_path = os.path.join(local_dir, 'configs/neat_config_player.txt')
    config      = neat.Config(neat.DefaultGenome, neat.DefaultReproduction,
                         neat.DefaultSpeciesSet, neat.DefaultStagnation,
                         config_path)

    p       = neat.Population(config)
    stats   = neat.StatisticsReporter()
    p.add_reporter(stats)
    # p.add_reporter(neat.Checkpointer(generation_interval=10,filename_prefix="checkpoit-"))

    timeTaken   = time()
    global generation
    generation = 0

    global _WORKER_DECK
    _WORKER_DECK = _deck
    global _SETTINGS
    _SETTINGS = settings
    random.seed(settings.seed)

    generation_count = settings.generations
    #eval_function = eval_genomes_same_deck
    eval_function = eval_genomes_parallel
    # eval_function = eval_genomes_parallel_rnd

    winner = p.run(eval_function, generation_count)
    print(f"best fitness overall: {winner.fitness}")
    evaluation = _test_pickle_vs_rnd(
        config,
        winner,
        settings.evaluation_games,
        settings.seed,
    )


    timeTaken = time() - timeTaken
    print(f"training time: {round(timeTaken)/60/60} hours")

    artifact_root = Path(os.environ.get("TRAINING_ARTIFACT_DIR", local_dir))
    file_path = artifact_root / "trained_ai"
    file_path.mkdir(parents=True, exist_ok=True)
    safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "-", settings.run_label).strip("-")
    file_path = file_path / (
        f"best_{_deck.id}_{safe_label or 'player'}_{generation_count}.pickle"
    )
    print(file_path.absolute())
    with open(file_path.absolute(), "wb") as f:
        pickle.dump(winner, f)
    summary = {
        "kind": "specific_deck_player",
        "deck_id": _deck.id,
        "deck_name": _deck.name,
        "settings": asdict(settings),
        "best_fitness": winner.fitness,
        "elapsed_seconds": timeTaken,
        "artifact_path": str(file_path.absolute()),
        "evaluation": evaluation,
    }
    summary_path = os.environ.get("PLAYER_TRAINING_SUMMARY_PATH")
    if summary_path:
        Path(summary_path).write_text(json.dumps(summary, indent=2, sort_keys=True))
    return summary




if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Train a specific deck by ID")
    parser.add_argument("deck_id", type=str, help="The ID of the deck to train")
    parser.add_argument(
        "--generations",
        type=int,
        default=DEFAULT_EVALUATOR_GENERATIONS,
    )
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--evaluation-games", type=int, default=100)
    parser.add_argument("--seed", type=int, default=104729)
    parser.add_argument("--run-label", default="player-deck")
    args = parser.parse_args()
    train_deck(
        DBUtil().load_deck(args.deck_id),
        PlayerTrainerSettings(
            generations=args.generations,
            workers=args.workers,
            evaluation_games=args.evaluation_games,
            seed=args.seed,
            run_label=args.run_label,
        ),
    )
