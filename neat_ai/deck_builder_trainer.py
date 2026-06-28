import datetime

from utils.database_utils       import DBUtil
from neat_ai.ai_training_logger import AITrainingLogger as logger, Training, Genome, MatchDBT
from cards.deck                 import Deck
from neat_ai.deck_builder       import build_deck
from neat_ai.deck_evaluator     import train_deck
from neat_ai.player_trainer     import train_deck as test_deck

import neat
import pickle

from concurrent.futures import ProcessPoolExecutor
from time import sleep, time, ctime
import sys
import io
import os
from pathlib import Path

training_row = None
db_util = DBUtil()
train_logger = logger()

def eval_match(deck1: Deck, deck2: Deck, match_guid: str):
    deck1.neat_fitness, deck2.neat_fitness = train_deck(deck1, deck2, match_guid)

    deck1.cards.sort(key=lambda card: card.name)
    deck2.cards.sort(key=lambda card: card.name)

    deck1.cards.sort(key=lambda card: card.name)
    deck2.cards.sort(key=lambda card: card.name)

    print(f"deck 1: fitness: {str(deck1.neat_fitness).ljust(3)} | cards: ", end="")
    for card in deck1.cards:
        print(f"{card.name.ljust(10)} |", end="")
    print()

    print(f"deck 2: fitness: {str(deck2.neat_fitness).ljust(3)} | cards: ", end="")
    for card in deck2.cards:
        print(f"{card.name.ljust(10)} |", end="")
    print()

def _evaluate_pair(i, j, genome_id1, deck1, genome_id2, deck2, match_guid):
    if genome_id1 != genome_id2:
        eval_match(deck1, deck2, match_guid)
    else:
        deck1.neat_fitness = 0
        deck2.neat_fitness = 0

    return i, j, genome_id1, deck1.neat_fitness, genome_id2, deck2.neat_fitness, match_guid

def eval_genomes(genomes, config, max_concurrent_games: int = 2):
    global Training
    global generation
    generation += 1
    n = len(genomes)

    with open("training_progress.txt", "a") as f:
        f.write(f"generation: {generation} |  training round: 0/{len(genomes) ** 2} | time: {ctime(time())}\n")

    # ---------------------------------------------------------
    # 1. PRE-BUILD DECKS AND SAVE GENOMES TO LOGGER
    # ---------------------------------------------------------
    decks_by_genome = {}
    for genome_id, genome in genomes:
        net = neat.nn.FeedForwardNetwork.create(genome, config)
        deck = build_deck(net)
        deck.name = f"Gen{generation}_ID{genome_id}"

        # Save to decks.db
        db_util.save_deck(deck)
        decks_by_genome[genome_id] = deck

        # Create unique GUID for this genome in this training session
        genome_guid = f"{training_row.id}-{genome_id}"

        genome_row = Genome(
            guid=genome_guid,
            gen=generation,
            deck_id=deck.id,
            training_id=training_row.id,
            score=0.0 # Initial score, updated later
        )

        # Save to train.db
        train_logger.save_genome(genome_row)

    # initialize fitness exactly as original
    for i, (genome_id1, genome1) in enumerate(genomes):
        genome1.fitness = 0
        j = 0
        for genome_id2, genome2 in genomes[min(i+1, n - 1):]:
            j += 1
            genome2.fitness = 0 if genome2.fitness is None else genome2.fitness
            print(f"{genome_id1} vs {genome_id2}")

    # build matches using the pre-built decks mapped from our dictionary
    matches = []
    for i, (genome_id1, genome1) in enumerate(genomes):
        j = 0
        for genome_id2, genome2 in genomes[min(i+1, n - 1):]:
            j += 1

            # GENERATE AND SAVE BEFORE THE MATCH RUNS
            match_guid = f"T{training_row.id}:{genome_id1}-vs-{genome_id2}:gen{generation}"

            match_row = MatchDBT(
                guid=match_guid,
                genome_1=f"{training_row.id}-{genome_id1}",
                genome_2=f"{training_row.id}-{genome_id2}",
                deck_1=decks_by_genome[genome_id1].id,
                deck_2=decks_by_genome[genome_id2].id,
                gen=generation,
                result=0.0 # Placeholder
            )
            train_logger.save_match_dbt(match_row)

            # Pass match_guid into the tuple
            matches.append((i, j, genome_id1, decks_by_genome[genome_id1], genome_id2, decks_by_genome[genome_id2], match_guid))
    total_matches = len(matches)
    if total_matches == 0:
        return

    max_concurrent = max(1, int(max_concurrent_games))
    dict_genomes = dict(genomes)

    # ---------------------------------------------------------
    # 2. RUN MATCHES AND LOG MATCH DATA
    # ---------------------------------------------------------
    with ProcessPoolExecutor(max_workers=max_concurrent) as executor:
        for start in range(0, total_matches, max_concurrent):
            batch = matches[start:start + max_concurrent]
            futures = [executor.submit(_evaluate_pair, *m) for m in batch]

            for fut in futures:
                # Unpack the 7 variables, including the match_guid
                i, j, g1_id, g1_fit, g2_id, g2_fit, returned_match_guid = fut.result()

                genome1 = dict_genomes[g1_id]
                genome2 = dict_genomes[g2_id]

                genome1.fitness += g1_fit
                genome2.fitness += g2_fit

                # UPDATE Match data in train.db with the final fitness result
                saved_match = train_logger.get_match_dbt(returned_match_guid)
                if saved_match:
                    saved_match.result = g1_fit
                    train_logger.save_match_dbt(saved_match)

                # compute top genome for printing
                best_genome = max(genomes, key=lambda g: g[1].fitness if g[1].fitness is not None else float("-inf"))
                progress_idx = i * len(genomes) + j
                print(f"generation: {generation} |  training round: {progress_idx}/{len(genomes) ** 2} |  top_fitness: {best_genome[1].fitness}  | time: {ctime(time())}")

    # ---------------------------------------------------------
    # 3. POST-GENERATION: UPDATE FINAL GENOME SCORES
    # ---------------------------------------------------------
    for genome_id, genome in genomes:
        genome_guid = f"{training_row.id}-{genome_id}"
        # Fetch the row we created earlier
        saved_genome = train_logger.get_genome(genome_guid)
        if saved_genome:
            saved_genome.score = genome.fitness
            train_logger.save_genome(saved_genome) # UPSERT takes care of the update

def test_genome(genome, config):
    net  = neat.nn.FeedForwardNetwork.create(genome, config)
    deck = build_deck(net)
    deck.cards.sort(key=lambda card: card.name)
    for card in deck.cards:
        print(f"{card.name.ljust(10)} |", end="")
    print()

def train_deck_builder():
    file_prefix = "20-06-26"
    local_dir   = os.path.dirname(__file__)
    config_path = os.path.join(local_dir, 'configs/neat_config_builder.txt')
    config      = neat.Config(neat.DefaultGenome, neat.DefaultReproduction,
                              neat.DefaultSpeciesSet, neat.DefaultStagnation,
                              config_path)

    p = neat.Population(config)

    stats = neat.StatisticsReporter()
    p.add_reporter(stats)
    p.add_reporter(neat.Checkpointer(generation_interval=0, filename_prefix=f"neat_ai/checkpoints/deck_builder_trainer/deck_builder_checkpoint_{file_prefix}_gen-"))

    timeTaken = time()
    global generation
    generation = 0
    generation_count = 1 + 1
    eval_function = eval_genomes

    global training_row
    training_row = Training(str(datetime.datetime.now())) # Cast datetime to string for your dataclass
    training_row.config = open(config_path).read()

    # Save training session to DB to generate the training ID
    training_row = train_logger.save_training(training_row)

    winner = p.run(eval_function, generation_count)
    print(f"best fitness overall: {winner.fitness}")

    # Update training row with end date
    training_row.end_date = str(datetime.datetime.now())
    train_logger.save_training(training_row)

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