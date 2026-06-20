# https://neat-python.readthedocs.io/en/latest/xor_example.html
import os
import sys
from   time import time,ctime
import copy
import argparse
from pathlib import Path
from random import shuffle,sample

from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures import ProcessPoolExecutor, as_completed

import neat
import pickle

from core.game_loop         import run as run_game
from core.player            import Player
from utils.database_utils   import DBUtil
from choice_strategies.choice_strategy_ai_neat      import PlayerChoiceStrategyNeat
from choice_strategies.choice_strategy_ai_random    import ChoiceStrategyAIRandom
from display_strategies.display_strategy_CLI        import DisplayStrategyCLI
from display_strategies.display_strategy_none       import DisplayStrategyNone

GENOME_2_WINNER = None
def evaluate_match(genome1_data, genome2_data, config, deck_1, deck_2):
    genome_id1, genome1 = genome1_data
    genome_id2, genome2 = genome2_data

    player_1 = Player(1, deck_1, PlayerChoiceStrategyNeat)
    player_2 = Player(2, deck_2, PlayerChoiceStrategyNeat)
    player_1.net = neat.nn.FeedForwardNetwork.create(genome1, config)
    player_2.net = neat.nn.FeedForwardNetwork.create(genome2, config)

    run_game(player_1, player_2, DisplayStrategyNone)

    # calculate fitness
    player_1_fitness = 10 * (player_1.score - 1)
    player_2_fitness = 10 * (player_2.score - 1)

    return genome_id1, player_1_fitness, genome_id2, player_2_fitness

def eval_genomes_parallel(genomes2, config):
    global generation
    global genomes1
    global DECK_1
    global DECK_2
    # print(f"generation: {generation}")

    # initialize fitness
    for _, genome in genomes1:
        genome.fitness = 0
    for _, genome in genomes2:
        genome.fitness = 0

    genomes2_shuffled = sample(genomes2, len(genomes2))  # shuffle genomes so match-ups differ each generation
    #matches = [((id1, g1), (id2, g2)) for (id1, g1), (id2, g2) in zip(genomes1, genomes2_shuffled)]
    matches = []
    for _, g1 in enumerate(genomes1):
        for _, g2 in enumerate(genomes2_shuffled):
            matches.append((g1, g2)) 

    with ProcessPoolExecutor() as executor:
        futures = [executor.submit(evaluate_match, g1, g2, config, copy.deepcopy(DECK_1), copy.deepcopy(DECK_2)) for g1, g2 in matches]

        for i, f in enumerate(as_completed(futures), 1):
            g1_id, g1_fit, g2_id, g2_fit = f.result()
            genome1 = dict(genomes1)[g1_id]
            genome2 = dict(genomes2)[g2_id]
            genome1.fitness += g1_fit
            genome2.fitness += g2_fit

            if i % 10 == 0 or i == len(matches):
                best_genome1 = max(genomes1, key=lambda g: g[1].fitness if g[1].fitness is not None else float("-inf"))
                best_genome2 = max(genomes2, key=lambda g: g[1].fitness if g[1].fitness is not None else float("-inf"))
                # print(f"generation: {generation} |  trainning round: {i}/{len(genomes1)*len(genomes2)} |  top_fitness_g1: {best_genome1[1].fitness}  | top_fitness_g2: {best_genome2[1].fitness} | time: {ctime(time())}")

    print(f"\rgeneration {generation}/{generation_count} completed", end="", flush=True)

def match_corordinator(genomes, config):
    global GENOME_2_WINNER
    global generation_count
    global genomes1
    global generation
    generation += 1

    checkpoint_dir = f"neat_ai/checkpoints/deck_evaluator/deck2/ai_{DECK_1.name}_{DECK_2.name}"
    os.makedirs(checkpoint_dir, exist_ok=True)
    genomes1    = genomes
    if generation > 2:
        # print(f"checkpoints/deck_evaluator/deck2/gen_{generation-1}-0")
        p   = neat.Checkpointer.restore_checkpoint(f"{checkpoint_dir}/gen_{generation -1}-0")
    else:
        p   = neat.Population(config)
    stats       = neat.StatisticsReporter()
    p.add_reporter(stats)
    p.add_reporter(neat.Checkpointer(generation_interval=0,filename_prefix = f"{checkpoint_dir}/gen_{generation}-"))

    winner = p.run(eval_genomes_parallel, 1)

    if generation == generation_count:
        GENOME_2_WINNER = winner
        file_path = Path("./neat_ai/trained_ai/")
        file_path = file_path / "best_g2.pickle"
        print(file_path.absolute())
        with open(file_path.absolute(), "wb") as f:
            pickle.dump(winner, f)

    
            
def train_deck(deck1, deck2) -> list: #deck1 fitness, deck2 fitness
    global GENOME_2_WINNER
    global DECK_1
    global DECK_2
    global generation
    global generation_count
    DECK_1 = deck1
    DECK_2 = deck2

    local_dir   = os.path.dirname(__file__)
    config_path = os.path.join(local_dir, 'configs/neat_config_evaluator.txt')
    config      = neat.Config(neat.DefaultGenome, neat.DefaultReproduction,
                         neat.DefaultSpeciesSet, neat.DefaultStagnation,
                         config_path)

    p       = neat.Population(config)
    stats   = neat.StatisticsReporter()
    p.add_reporter(stats)
    # p.add_reporter(neat.Checkpointer(generation_interval=0,filename_prefix=f"neat_ai/checkpoints/deck_evaluator/deck1/gen_"))

    report      = ""
    generation = 0
    timeTaken   = time()

    generation_count = 25
    eval_function = match_corordinator

    winner = p.run(eval_function, generation_count)

    return [winner.fitness, GENOME_2_WINNER.fitness]
        


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Train a specific deck by ID")
    parser.add_argument("deck_id1", type=str, help="The ID of the deck to evaluate")
    parser.add_argument("deck_id2", type=str, help="The ID of the deck to evaluate against")
    args = parser.parse_args()
    print(args.deck_id1)
    print(args.deck_id2)
    train_deck( DBUtil().load_deck(args.deck_id1), DBUtil().load_deck(args.deck_id2) )

