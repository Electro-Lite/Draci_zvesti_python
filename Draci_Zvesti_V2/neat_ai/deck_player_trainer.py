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
from display_strategies.display_strategy_CLI    import DisplayStrategyCLI
from display_strategies.display_strategy_none   import DisplayStrategyNone

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
    print(f"generation: {generation}")

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
                print(f"generation: {generation} |  trainning round: {i}/{len(genomes1)*len(genomes2)} |  top_fitness_g1: {best_genome1[1].fitness}  | top_fitness_g2: {best_genome2[1].fitness} | time: {ctime(time())}")

    print(f"generation {generation}/{generation_count} completed")

def match_corordinator(genomes, config):
    global GENOME_2_WINNER
    global generation_count
    global genomes1
    global generation
    generation += 1

    genomes1    = genomes
    if generation > 1:
        print(f"loading g1_checkpoit-{generation-1}")
        p = neat.Checkpointer.restore_checkpoint(f"g1_checkpoint_gen{generation -1}-0")
    else:
        p           = neat.Population(config)
    stats       = neat.StatisticsReporter()
    p.add_reporter(stats)
    p.add_reporter(neat.Checkpointer(generation_interval=0,filename_prefix=f"g1_checkpoint_gen{generation}-"))

    winner = p.run(eval_genomes_parallel, 1)

    if generation == generation_count:
        GENOME_2_WINNER = winner
        file_path = Path("./neat_ai/trained_ai/")
        file_path = file_path / "best_g2.pickle"
        print(file_path.absolute())
        with open(file_path.absolute(), "wb") as f:
            pickle.dump(winner, f)



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
            
            
def train_deck(deck1, deck2) -> list: #deck1 fitness, deck2 fitness
    global GENOME_2_WINNER
    global DECK_1
    global DECK_2
    global generation
    global generation_count
    DECK_1 = deck1
    DECK_2 = deck2

    local_dir   = os.path.dirname(__file__)
    config_path = os.path.join(local_dir, 'neat_config_player.txt')
    config      = neat.Config(neat.DefaultGenome, neat.DefaultReproduction,
                         neat.DefaultSpeciesSet, neat.DefaultStagnation,
                         config_path)

    p       = neat.Population(config)
    stats   = neat.StatisticsReporter()
    p.add_reporter(stats)
    p.add_reporter(neat.Checkpointer(generation_interval=10,filename_prefix="checkpoit-"))

    report      = ""
    timeTaken   = time()
    generation = 0

    generation_count = 25
    eval_function = match_corordinator

    winner = p.run(eval_function, generation_count)
    print(f"best fitness overall: {max(winner.fitness, GENOME_2_WINNER.fitness)}")
    

    # _test_pickle_vs_rnd(config, winner)
    # _test_pickle_vs_rnd(config, GENOME_2_WINNER)

    
    timeTaken = time() - timeTaken
    print(f"training time: {round(timeTaken)/60/60} hours")
    
    # file_path = Path("./neat_ai/trained_ai/")
    # file_path = file_path / "best_g1.pickle"
    # print(file_path.absolute())
    # with open(file_path.absolute(), "wb") as f:
    #     pickle.dump(winner, f)

    return [winner.fitness, GENOME_2_WINNER.fitness]
        


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Train a specific deck by ID")
    parser.add_argument("deck_id", type=str, help="The ID of the deck to train")
    args = parser.parse_args()
    
    train_deck(DBUtil().load_deck(args.deck_id))

