# https://neat-python.readthedocs.io/en/latest/xor_example.html
import os
import sys
from   time import time,ctime
import copy
import argparse
from pathlib import Path

from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures import ProcessPoolExecutor, as_completed

import neat
import pickle

from core.game_loop         import run as run_game
from core.player            import Player
from utils.database_utils   import DBUtil
from choice_strategies.choice_strategy_ai_neat      import PlayerChoiceStrategyNeat
from choice_strategies.choice_strategy_ai_random    import ChoiceStrategyAIRandom
from display_strategies.display_strategy_CLI    import DisplayStrategyCLI
from display_strategies.display_strategy_none   import DisplayStrategyNone

# Worker-local globals (populated by initializer)
_WORKER_DECK = None

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

def eval_genomes_parallel(genomes, config):
    global generation
    generation += 1
    print(f"generation: {generation}")
    # initialize fitness
    for _, genome in genomes:
        genome.fitness = 0
    matches = []
    for i, g1 in enumerate(genomes):
        for g2 in genomes[i+1:]:
            matches.append((g1, g2))

    with ProcessPoolExecutor() as executor:
        futures = [executor.submit(evaluate_match, g1, g2, config, copy.deepcopy(_WORKER_DECK), copy.deepcopy(_WORKER_DECK)) for g1, g2 in matches]

        for i, f in enumerate(as_completed(futures), 1):
            g1_id, g1_fit, g2_id, g2_fit = f.result()
            genome1 = dict(genomes)[g1_id]
            genome2 = dict(genomes)[g2_id]
            genome1.fitness += g1_fit
            genome2.fitness += g2_fit

            if i % 10 == 0 or i == len(matches):
                best_genome = max(genomes, key=lambda g: g[1].fitness if g[1].fitness is not None else float("-inf"))
                print(f"generation: {generation} |  trainning round: {i}/{len(genomes)**2} |  top_fitness: {best_genome[1].fitness}  | time: {ctime(time())}")

    print(f"generation {generation} completed")


def eval_genomes_same_deck(genomes, config):
    """
    Run each genome against each-other one time to determine the fitness.
    """
    global _WORKER_DECK
    global generation
    generation += 1

    for i, (genome_id1, genome1) in enumerate(genomes):
        best_genome = max(genomes, key=lambda g: g[1].fitness if g[1].fitness is not None else float("-inf"))
        print(f"generation: {generation} |  trainning round: {i}/{len(genomes)} |  top_fitness: {best_genome[1].fitness}  | time: {ctime(time())}")

        genome1.fitness = 0
        for genome_id2, genome2 in genomes[min(i+1, len(genomes) - 1):]:
            genome2.fitness = 0 if genome2.fitness == None else genome2.fitness

            player_1 = Player(1, copy.deepcopy(_WORKER_DECK), PlayerChoiceStrategyNeat)
            player_2 = Player(2, copy.deepcopy(_WORKER_DECK), PlayerChoiceStrategyNeat)
            player_1.net=neat.nn.FeedForwardNetwork.create(genome1, config)
            player_2.net=neat.nn.FeedForwardNetwork.create(genome2, config)
            run_game(player_1, player_2, DisplayStrategyNone)
            #calculate fitness
            player_1.fitness += 10 * (player_1.score - 1)
            player_2.fitness += 10 * (player_2.score - 1)
            
            genome1.fitness += player_1.fitness
            genome2.fitness += player_2.fitness
            


def _test_pickle_vs_rnd(config, _pickle):
    print("running evaluation test")
    winner_net = neat.nn.FeedForwardNetwork.create(_pickle, config)
    score = [0,0,0]
    rounds = 10000
    bar_length = 30
    for i in range(0, rounds):
        if i % (rounds // 100) == 0 or i == rounds - 1:  # update every 1%
            progress = i / rounds
            percent = int(progress * 100)
            filled = int(bar_length * progress)
            bar = "█" * filled + "-" * (bar_length - filled)
            print(f"\rTesting progress: |{bar}| {percent}%", end="", flush=True)

        player_1        = Player(1, DBUtil().load_deck("Starter Blue_1"), PlayerChoiceStrategyNeat)
        player_1.net    = winner_net
        player_2        = Player(1, DBUtil().load_deck("Starter Blue_1"), ChoiceStrategyAIRandom)

        run_game(player_1, player_2, DisplayStrategyNone)

        if  (player_1.score > player_2.score):
            score[0]+=1
        elif(player_1.score < player_2.score):
            score[2]+=1
        else:
            score[1]+=1

    print("final score is:")
    print("ai   :" + str(int(score[0]/100))+"%")
    print("draws:" + str(int(score[1]/100))+"%")
    print("rnd  :" + str(int(score[2]/100))+"%")
            
            
def train_deck(deck_id):
    local_dir   = os.path.dirname(__file__)
    config_path = os.path.join(local_dir, 'neat_config.txt')
    config      = neat.Config(neat.DefaultGenome, neat.DefaultReproduction,
                         neat.DefaultSpeciesSet, neat.DefaultStagnation,
                         config_path)

    p       = neat.Population(config)
    stats   = neat.StatisticsReporter()
    p.add_reporter(stats)
    p.add_reporter(neat.Checkpointer(generation_interval=10,filename_prefix="checkpoit-"))

    report      = ""
    timeTaken   = time()
    global generation
    generation = 0
    
    global _WORKER_DECK
    _WORKER_DECK = DBUtil().load_deck(deck_id)

    generation_count = 500
    #eval_function = eval_genomes_same_deck
    eval_function = eval_genomes_parallel
    # eval_function = eval_genomes_parallel_rnd

    winner = p.run(eval_function, generation_count)
    print(f"best fitness overall: {winner.fitness}")
    _test_pickle_vs_rnd(config, winner)

    
    timeTaken = time() - timeTaken
    print(f"training time: {round(timeTaken)/60/60} hours")
    
    file_path = Path("./neat_ai/trained_ai/")
    file_path = file_path / f"best_{deck_id}_{eval_function.__name__}_{generation_count}.pickle"
    print(file_path.absolute())
    with open(file_path.absolute(), "wb") as f:
        pickle.dump(winner, f)

        


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Train a specific deck by ID")
    parser.add_argument("deck_id", type=str, help="The ID of the deck to train")
    # args = parser.parse_args()
    # train_deck(args.deck_id)
    train_deck("Starter Blue_1")

