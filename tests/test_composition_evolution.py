import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cards.card_type import CardType
from cards.power import Power
from core.config import MAX_DECK_SIZE, MIN_DECK_SIZE
from neat_ai.direct_deck_evolution_algorithm import (
    CompositionEvolutionSettings,
    DeckGenome,
    EvaluatedDeckGenome,
    available_cards,
    crossover_genomes,
    initial_population,
    mutate_genome,
    next_population,
)
from neat_ai.deck_pool_evolution_v2 import (
    DeckPoolV2Settings,
    _checkpoint_completed_generation,
    _load_checkpoint,
    _save_checkpoint,
)


def card(card_id, power=Power.NORMAL):
    return SimpleNamespace(
        id=card_id,
        name=card_id,
        power=power,
        type=CardType.PLAYER,
    )


class CompositionEvolutionTests(unittest.TestCase):
    def setUp(self):
        self.pool = {
            f"normal-{index}": card(f"normal-{index}")
            for index in range(MAX_DECK_SIZE)
        }
        self.pool["legendary"] = card("legendary", Power.LEGENDARY)
        self.settings = CompositionEvolutionSettings(population_size=20)

    def test_genome_is_canonical_and_order_independent(self):
        first = DeckGenome(("normal-2", "normal-1", "normal-1"))
        second = DeckGenome(("normal-1", "normal-2", "normal-1"))

        self.assertEqual(first, second)
        self.assertEqual(first.signature, second.signature)

    def test_eligible_pool_applies_power_limit_and_card_bans(self):
        cards = [
            card("starter", Power.STARTER),
            card("normal", Power.NORMAL),
            card("banned", Power.NORMAL),
            card("legendary", Power.LEGENDARY),
        ]

        pool = available_cards(cards, max_power=Power.NORMAL, banned_card_ids=("banned",))

        self.assertEqual(set(pool), {"starter", "normal"})
        self.assertEqual(list(pool), ["normal", "starter"])

    def test_validation_enforces_copy_limits(self):
        legal = DeckGenome(
            tuple(
                ["normal-1"] * 4
                + ["normal-2"] * 4
                + ["normal-3"] * (MAX_DECK_SIZE - 8)
            )
        )
        legal.validate(self.pool)

        with self.assertRaisesRegex(ValueError, "limit is 1"):
            DeckGenome(tuple(["legendary"] * 2 + ["normal-1"] * 4 + ["normal-2"] * (MIN_DECK_SIZE - 6))).validate(
                self.pool
            )

    def test_initial_and_next_populations_are_unique_and_legal(self):
        rng = random.Random(104729)
        population = initial_population(self.pool, rng, self.settings)
        evaluated = [
            EvaluatedDeckGenome(genome, float(index))
            for index, genome in enumerate(population)
        ]

        following = next_population(evaluated, self.pool, rng, self.settings)

        self.assertEqual(len(following), self.settings.population_size)
        self.assertEqual(len(set(following)), self.settings.population_size)
        self.assertIn(population[-1], following)  # strongest elite
        self.assertIn(population[-2], following)
        for genome in following:
            genome.validate(self.pool)

    def test_mutation_changes_composition_without_breaking_legality(self):
        genome = DeckGenome(
            tuple(f"normal-{index}" for index in range(MIN_DECK_SIZE))
        )
        mutated = mutate_genome(
            genome,
            self.pool,
            random.Random(7),
            self.settings,
        )

        self.assertNotEqual(mutated, genome)
        mutated.validate(self.pool)

    def test_crossover_uses_only_parent_cards_and_preserves_shared_cards(self):
        offset = MAX_DECK_SIZE - MIN_DECK_SIZE
        first = DeckGenome(
            tuple(f"normal-{index}" for index in range(MIN_DECK_SIZE))
        )
        second = DeckGenome(
            tuple(
                f"normal-{index}"
                for index in range(offset, offset + MIN_DECK_SIZE)
            )
        )

        child = crossover_genomes(
            first,
            second,
            self.pool,
            random.Random(7),
            self.settings,
        )

        child.validate(self.pool)
        self.assertEqual(len(child.cards), MIN_DECK_SIZE)
        self.assertLessEqual(set(child.cards), set(first.cards) | set(second.cards))
        shared = set(first.cards) & set(second.cards)
        self.assertLessEqual(shared, set(child.cards))

    def test_checkpoint_restores_population_and_random_stream(self):
        rng = random.Random(104729)
        population = initial_population(self.pool, rng, self.settings)
        trainer_settings = DeckPoolV2Settings(
            seed=104729,
            population_size=20,
            resume_training_id=17,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "training_17_seed_104729_gen-3"
            _save_checkpoint(path, 17, trainer_settings, 4, population, rng)
            expected_next = rng.random()
            checkpoint, restored_rng = _load_checkpoint(path, trainer_settings)

            self.assertEqual(_checkpoint_completed_generation(path), 4)
            self.assertEqual(checkpoint.population, tuple(population))
            self.assertEqual(restored_rng.random(), expected_next)


if __name__ == "__main__":
    unittest.main()
