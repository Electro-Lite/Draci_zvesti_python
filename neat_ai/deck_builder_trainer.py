import datetime
import random

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
train_logger = logger()

def _genome_guid(training_id: int, generation: int, genome_id: int) -> str:
    return f"{training_id}-gen{generation}-{genome_id}"

def eval_match(deck1: Deck, deck2: Deck, match_guid: str):
    deck1.neat_fitness, deck2.neat_fitness = train_deck(deck1, deck2, match_guid)

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

def eval_genomes(genomes, config, max_concurrent_games: int = 2, max_matches_per_genome: int = None):
    global Training
    global generation
    generation += 1
    n = len(genomes)

    # ---------------------------------------------------------
    # 1. DETERMINE MATCH PAIRINGS (EVEN DISTRIBUTION)
    # ---------------------------------------------------------
    matches_to_play = []

    if max_matches_per_genome is None:
        # Fallback to Everyone vs Everyone
        total_possible_matches = n * (n - 1) // 2
        for i, (genome_id1, genome1) in enumerate(genomes):
            for genome_id2, genome2 in genomes[i + 1:]:
                matches_to_play.append((genome_id1, genome1, genome_id2, genome2))
    else:
        # Cap matches to the maximum possible opponents (n - 1)
        x = min(max_matches_per_genome, n - 1)

        # A valid regular graph requires (n * x) to be even.
        # If it's not, we reduce the match count by 1 to make it possible.
        if (n * x) % 2 != 0:
            x -= 1

        if x <= 0:
            total_possible_matches = 0
        else:
            total_possible_matches = (n * x) // 2

            # Randomize nodes to ensure opponents are random despite the strict ring topology
            shuffled_genomes = list(genomes)
            random.shuffle(shuffled_genomes)

            for i in range(n):
                # Connect to x // 2 nodes moving "forward" in the list
                for j in range(1, (x // 2) + 1):
                    target = (i + j) % n
                    matches_to_play.append((shuffled_genomes[i][0], shuffled_genomes[i][1],
                                            shuffled_genomes[target][0], shuffled_genomes[target][1]))

                # If x is odd, also connect to the node exactly opposite in the circle
                if x % 2 != 0:
                    opposite = (i + n // 2) % n
                    if i < n // 2: # Prevents adding the same match twice
                        matches_to_play.append((shuffled_genomes[i][0], shuffled_genomes[i][1],
                                                shuffled_genomes[opposite][0], shuffled_genomes[opposite][1]))

    with open("training_progress.txt", "a") as f:
        f.write(f"generation: {generation} |  training round: 0/{total_possible_matches} | time: {ctime(time())}\n")

    # ---------------------------------------------------------
    # 2. PRE-BUILD DECKS AND SAVE GENOMES TO LOGGER
    # ---------------------------------------------------------
    decks_by_genome = {}
    for genome_id, genome in genomes:
        net = neat.nn.FeedForwardNetwork.create(genome, config)
        deck = build_deck(net)
        deck.name = f"Gen{generation}_ID{genome_id}"

        # Save generated decks with the training data
        train_logger.save_training_deck(deck, training_row.id)
        decks_by_genome[genome_id] = deck

        # Create unique GUID for this genome in this training session
        genome_guid = _genome_guid(training_row.id, generation, genome_id)

        genome_row = Genome(
            guid=genome_guid,
            gen=generation,
            deck_id=deck.id,
            training_id=training_row.id,
            score=0.0
        )
        train_logger.save_genome(genome_row)

    # Initialize fitness uniformly to 0
    for genome_id, genome in genomes:
        genome.fitness = 0

    # Build matches using the pre-built decks mapped from our dictionary
    matches = []
    for idx, (genome_id1, genome1, genome_id2, genome2) in enumerate(matches_to_play):
        # GENERATE AND SAVE BEFORE THE MATCH RUNS
        match_guid = f"T{training_row.id}:{genome_id1}-vs-{genome_id2}:gen{generation}"

        match_row = MatchDBT(
            guid=match_guid,
            genome_1=_genome_guid(training_row.id, generation, genome_id1),
            genome_2=_genome_guid(training_row.id, generation, genome_id2),
            deck_1=decks_by_genome[genome_id1].id,
            deck_2=decks_by_genome[genome_id2].id,
            gen=generation,
            result=0.0 # Placeholder
        )
        train_logger.save_match_dbt(match_row)

        matches.append((idx, 0, genome_id1, decks_by_genome[genome_id1], genome_id2, decks_by_genome[genome_id2], match_guid))

    total_matches = len(matches)
    if total_matches == 0:
        return

    max_concurrent = max(1, int(max_concurrent_games))
    dict_genomes = dict(genomes)

    # ---------------------------------------------------------
    # 3. RUN MATCHES AND LOG MATCH DATA
    # ---------------------------------------------------------
    with ProcessPoolExecutor(max_workers=max_concurrent) as executor:
        completed_matches = 0
        for start in range(0, total_matches, max_concurrent):
            batch = matches[start:start + max_concurrent]
            futures = [executor.submit(_evaluate_pair, *m) for m in batch]

            for fut in futures:
                i, j, g1_id, g1_fit, g2_id, g2_fit, returned_match_guid = fut.result()
                completed_matches += 1

                genome1 = dict_genomes[g1_id]
                genome2 = dict_genomes[g2_id]

                genome1.fitness += g1_fit
                genome2.fitness += g2_fit

                saved_match = train_logger.get_match_dbt(returned_match_guid)
                if saved_match:
                    saved_match.result = g1_fit
                    train_logger.save_match_dbt(saved_match)

                best_genome = max(genomes, key=lambda g: g[1].fitness if g[1].fitness is not None else float("-inf"))
                print(f"generation: {generation} |  training round: {completed_matches}/{total_matches} |  top_fitness: {best_genome[1].fitness}  | time: {ctime(time())}")

    # ---------------------------------------------------------
    # 4. POST-GENERATION: UPDATE FINAL GENOME SCORES
    # ---------------------------------------------------------
    for genome_id, genome in genomes:
        genome_guid = _genome_guid(training_row.id, generation, genome_id)
        saved_genome = train_logger.get_genome(genome_guid)
        if saved_genome:
            saved_genome.score = genome.fitness
            train_logger.save_genome(saved_genome)

def test_genome(genome, config):
    net  = neat.nn.FeedForwardNetwork.create(genome, config)
    deck = build_deck(net)
    deck.cards.sort(key=lambda card: card.name)
    for card in deck.cards:
        print(f"{card.name.ljust(10)} |", end="")
    print()

def train_deck_builder():
    file_prefix = str(datetime.datetime.now().date())
    local_dir   = os.path.dirname(__file__)
    config_path = os.path.join(local_dir, 'configs/neat_config_builder.txt')
    config      = neat.Config(neat.DefaultGenome, neat.DefaultReproduction,
                              neat.DefaultSpeciesSet, neat.DefaultStagnation,
                              config_path)

    checkpoint_path = os.environ.get("DECK_BUILDER_CHECKPOINT")
    if checkpoint_path:
        p = neat.Checkpointer.restore_checkpoint(checkpoint_path)
    else:
        p = neat.Population(config)

    stats = neat.StatisticsReporter()
    p.add_reporter(stats)
    checkpoint_dir = Path(local_dir) / "checkpoints" / "deck_builder_trainer"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    p.add_reporter(neat.Checkpointer(generation_interval=0, filename_prefix=str(checkpoint_dir / f"deck_builder_checkpoint_{file_prefix}_gen-")))

    timeTaken = time()
    global generation
    generation = p.generation
    generation_count = 15

    # ---------------------------------------------------------
    # SET YOUR DESIRED MAXIMUM MATCHES PER GENOME HERE
    # ---------------------------------------------------------
    MAX_MATCHES_PER_GENOME = 15 # None means full => every onve vs everyone

    # Use lambda to inject max_matches_per_genome cleanly into NEAT's expected signature
    eval_function = lambda genomes, conf: eval_genomes(genomes, conf, max_concurrent_games=2, max_matches_per_genome=MAX_MATCHES_PER_GENOME)

    global training_row
    training_row = Training(str(datetime.datetime.now()))
    training_row.config = open(config_path).read()

    training_row = train_logger.save_training(training_row)

    winner = p.run(eval_function, generation_count)
    print(f"best fitness overall: {winner.fitness}")

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