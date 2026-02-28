from utils.database_utils   import DBUtil
from cards.deck             import Deck
from neat_ai.deck_builder   import build_deck
from neat_ai.deck_evaluator import train_deck
from neat_ai.player_trainer import train_deck as test_deck

import neat
import pickle

from concurrent.futures import ProcessPoolExecutor
from   time import sleep, time,ctime
import sys
import io
import os
from pathlib import Path

def eval_match(deck1:Deck, deck2:Deck):
    #stdout
    # original_stdout = sys.stdout
    # sys.stdout = io.StringIO()
    
    deck1.neat_fitness, deck2.neat_fitness = train_deck(deck1, deck2)

    #stdout
    # sys.stdout = original_stdout

    deck1.cards.sort(key=lambda card: card.name)
    deck2.cards.sort(key=lambda card: card.name)

    print(f"deck 1: fitness: {str(deck1.neat_fitness).ljust(3)} | cards: ",end="")
    for card in deck1.cards:
        print(f"{card.name.ljust(10)} |",end="")
    print()

    print(f"deck 2: fitness: {str(deck2.neat_fitness).ljust(3)} | cards: ",end="")
    for card in deck2.cards:
        print(f"{card.name.ljust(10)} |",end="")
    print()


def _evaluate_pair(i, j, genome_id1, genome1, genome_id2, genome2, config):
    """
    Run a single pair evaluation in a worker process and return
    the outer/inner indices (i,j), genome ids and resulting fitnesses.
    """
    if genome_id1 != genome_id2:
        net1 = neat.nn.FeedForwardNetwork.create(genome1, config)
        net2 = neat.nn.FeedForwardNetwork.create(genome2, config)
        deck1 = build_deck(net1)
        deck2 = build_deck(net2)
        deck1.name = genome_id1
        deck2.name = genome_id2
        eval_match(deck1, deck2)
    else:
        deck1 = Deck()
        deck2 = Deck()
        deck1.neat_fitness = 0
        deck2.neat_fitness = 0
    return i, j, genome_id1, deck1.neat_fitness, genome_id2, deck2.neat_fitness


def eval_genomes(genomes, config, max_concurrent_games: int = 2):
    """
    Parallelized eval_genomes with a concurrency limit.
    - max_concurrent_games: how many games may run concurrently (default 4).
    Keeps the original behavior/side-effects and preserves update order.
    """
    global generation
    generation += 1
    n = len(genomes)
    with open("training_progress.txt", "a") as f:
        f.write(f"generation: {generation} |  trainning round: 0/{len(genomes) ** 2} | time: {ctime(time())}\n")


    # initialize fitness exactly as original
    for i, (genome_id1, genome1) in enumerate(genomes):
        genome1.fitness = 0
        j = 0
        for genome_id2, genome2 in genomes[min(i+1, n - 1):]:
            j += 1
            genome2.fitness = 0 if genome2.fitness is None else genome2.fitness
            # print matchup as original printed it (before evaluation)
            print(f"{genome_id1} vs {genome_id2}")

    # build matches in the same order as original nested loops
    matches = []
    for i, (genome_id1, genome1) in enumerate(genomes):
        j = 0
        for genome_id2, genome2 in genomes[min(i+1, n - 1):]:
            j += 1
            matches.append((i, j, genome_id1, genome1, genome_id2, genome2))

    total_matches = len(matches)
    if total_matches == 0:
        return

    # ensure a sensible positive integer for limit
    max_concurrent = max(1, int(max_concurrent_games))

    # Use ProcessPoolExecutor with up to max_concurrent workers.
    # We submit matches in chunks of size <= max_concurrent and then
    # consume results in submission order to preserve overwrite semantics.
    dict_genomes = dict(genomes)  # mapping from id -> genome object
    with ProcessPoolExecutor(max_workers=max_concurrent) as executor:
        # process matches in chunks
        for start in range(0, total_matches, max_concurrent):
            batch = matches[start:start + max_concurrent]
            futures = [executor.submit(_evaluate_pair, *m, config) for m in batch]

            # retrieve results in submission order (preserves original overwrite semantics)
            for fut in futures:
                i, j, g1_id, g1_fit, g2_id, g2_fit = fut.result()

                genome1 = dict_genomes[g1_id]
                genome2 = dict_genomes[g2_id]

                # overwrite fitness exactly like original code
                genome1.fitness = g1_fit
                genome2.fitness = g2_fit

                # compute top genome for printing (same logic as original)
                best_genome = max(genomes, key=lambda g: g[1].fitness if g[1].fitness is not None else float("-inf"))
                # compute progress index consistent with original formula
                progress_idx = i * len(genomes) + j
                print(f"generation: {generation} |  trainning round: {progress_idx}/{len(genomes) ** 2} |  top_fitness: {best_genome[1].fitness}  | time: {ctime(time())}")



    # global generation
    # generation += 1
    # print(f"generation: {generation} |  trainning round: 0/{len(genomes) ** 2} | time: {ctime(time())}")
    # for i, (genome_id1, genome1) in enumerate(genomes):
    #     genome1.fitness = 0
    #     j = 0
    #     for genome_id2, genome2 in genomes[min(i+1, len(genomes) - 1):]:
    #         j += 1
    #         genome2.fitness = 0 if genome2.fitness == None else genome2.fitness
    #         net1  = neat.nn.FeedForwardNetwork.create(genome1, config)
    #         net2  = neat.nn.FeedForwardNetwork.create(genome2, config)
    #         deck1 = build_deck(net1)
    #         deck2 = build_deck(net2)
    #         deck1.name = genome_id1
    #         deck2.name = genome_id2
    #         print(f"{genome_id1} vs {genome_id2}")
    #         eval_match(deck1, deck2)
    #         genome1.fitness =  deck1.neat_fitness
    #         genome2.fitness =  deck2.neat_fitness
    #         best_genome = max(genomes, key=lambda g: g[1].fitness if g[1].fitness is not None else float("-inf"))
    #         print(f"generation: {generation} |  trainning round: {i*len(genomes) + j}/{len(genomes) ** 2} |  top_fitness: {best_genome[1].fitness}  | time: {ctime(time())}")

def test_genome(genome, config):
    # Player(1, DBUtil().load_deck("Starter Blue_1")
    net  = neat.nn.FeedForwardNetwork.create(genome, config)
    deck = build_deck(net)
    deck.cards.sort(key=lambda card: card.name)
    # test_deck(deck) TODO need beter eval
    for card in deck.cards:
        print(f"{card.name.ljust(10)} |",end="")
    print()
    

def train_deck_builder():
    file_prefix = "9-12-25"
    local_dir   = os.path.dirname(__file__)
    config_path = os.path.join(local_dir, 'configs/neat_config_builder.txt')
    config      = neat.Config(neat.DefaultGenome, neat.DefaultReproduction,
                         neat.DefaultSpeciesSet, neat.DefaultStagnation,
                         config_path)

    # p       = neat.Population(config)
    p = neat.Checkpointer.restore_checkpoint("neat_ai/checkpoints/deck_builder_trainer/deck_builder_checkpoint_9-12-25_gen-7")

    stats   = neat.StatisticsReporter()
    p.add_reporter(stats)
    p.add_reporter(neat.Checkpointer(generation_interval=0,filename_prefix=f"neat_ai/checkpoints/deck_builder_trainer/deck_builder_checkpoint_{file_prefix}_gen-"))

    timeTaken   = time()
    global generation
    generation = 0
    
    
    generation_count = 18 #currently one generation takes 45 minutes
    eval_function = eval_genomes

    winner = p.run(eval_function, generation_count)
    print(f"best fitness overall: {winner.fitness}")
    
    timeTaken = time() - timeTaken
    print(f"builder training time: {round(timeTaken)/60/60} hours")
    
    file_path = Path("./neat_ai/trained_ai/")
    file_path = file_path / f"best_builder_{generation}.pickle"
    print(file_path.absolute())
    with open(file_path.absolute(), "wb") as f:
        pickle.dump(winner, f)

    test_genome(winner, config)
if __name__ == '__main__':
    train_deck_builder()