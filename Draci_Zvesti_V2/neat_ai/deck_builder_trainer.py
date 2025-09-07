from utils.database_utils   import DBUtil
from cards.deck             import Deck
from neat_ai.deck_builder   import build_deck
from neat_ai.deck_player_trainer import train_deck

import neat
import pickle

from   time import time,ctime
import os
from pathlib import Path

def eval_match():
    train_deck()

def eval_genomes(genomes, config):
    for i, (genome_id1, genome1) in enumerate(genomes):
        best_genome = max(genomes, key=lambda g: g[1].fitness if g[1].fitness is not None else float("-inf"))
        print(f"generation: {generation} |  trainning round: {i}/{len(genomes)} |  top_fitness: {best_genome[1].fitness}  | time: {ctime(time())}")

        genome1.fitness = 0
        for genome_id2, genome2 in genomes[min(i+1, len(genomes) - 1):]:
            genome2.fitness = 0 if genome2.fitness == None else genome2.fitness
            net1  = neat.nn.FeedForwardNetwork.create(genome1, config)
            net2  = neat.nn.FeedForwardNetwork.create(genome2, config)
            deck1 = build_deck(net1)
            deck2 = build_deck(net1)
            eval_match(deck1, deck2)
            genome1.fitness =  deck1.neat_fitness
            genome2.fitness =  deck2.neat_fitness

def test_genome():
    pass

def train_deck_builder():
    local_dir   = os.path.dirname(__file__)
    config_path = os.path.join(local_dir, 'neat_config_builder.txt')
    config      = neat.Config(neat.DefaultGenome, neat.DefaultReproduction,
                         neat.DefaultSpeciesSet, neat.DefaultStagnation,
                         config_path)

    p       = neat.Population(config)
    stats   = neat.StatisticsReporter()
    p.add_reporter(stats)
    p.add_reporter(neat.Checkpointer(generation_interval=10,filename_prefix="checkpoit-"))

    timeTaken   = time()
    global generation
    generation = 0
    
    generation_count = 5
    eval_function = eval_genomes

    winner = p.run(eval_function, generation_count)
    print(f"best fitness overall: {winner.fitness}")
    test_genome(config, winner)

    
    timeTaken = time() - timeTaken
    print(f"training time: {round(timeTaken)/60/60} hours")
    
    file_path = Path("./neat_ai/trained_ai/")
    file_path = file_path / f"best_builder_{eval_function.__name__}_{generation_count}.pickle"
    print(file_path.absolute())
    with open(file_path.absolute(), "wb") as f:
        pickle.dump(winner, f)