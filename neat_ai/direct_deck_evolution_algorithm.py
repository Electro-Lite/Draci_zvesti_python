"""Direct genetic evolution of legal deck compositions.

The player controllers are still evolved by NEAT.  This module deliberately
keeps the outer deck search small and domain-specific: a genome is the sorted
multiset of card IDs that makes up one deck.
"""

from __future__ import annotations

import hashlib
import random
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from cards.card_type import CardType
from cards.deck import Deck
from cards.deck_rules import card_copy_limit
from cards.power import Power
from core.config import MAX_DECK_SIZE, MIN_DECK_SIZE


def available_cards(
    _cards: Iterable,
    max_power: Power = Power.LEGENDARY,
    banned_card_ids: Iterable[str] = (),
) -> dict[str, object]:
    """Return a deterministic ID-to-card pool suitable for evolution."""
    banned_card_ids = {str(card_id) for card_id in banned_card_ids}
    cards = []
    for card in _cards:
        if str(card.id) in banned_card_ids:
            continue
        elif not card.power <= max_power:
            continue
        elif card.type != CardType.PLAYER:
            continue
        cards.append(card)
    cards.sort(key=lambda item: str(item.id))  # Sort by card ID.
    return {str(card.id): card for card in cards}



@dataclass(frozen=True, order=True)
class DeckGenome:
    """Deck genome = deck composition"""

    cards: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, "cards", tuple(sorted(str(card) for card in self.cards)))

    @property
    def signature(self) -> str:
        """deck signature, used for finding duplicates"""
        return hashlib.md5(",".join(self.cards).encode("utf-8")).hexdigest()

    def to_deck(self, card_pool: Mapping[str, object], name: str = "") -> Deck:
        """Convert this genome to a validated Deck instance."""
        deck = Deck()
        deck.name = name
        for card_id in self.cards:
            card = card_pool.get(card_id)
            if card is None:
                raise ValueError(f"Deck genome contains unknown card {card_id}")
            deck.add_card(card)
        deck.validate()
        return deck


@dataclass(frozen=True)
class CompositionEvolutionSettings:
    population_size: int = 20
    elite_count: int = 2
    tournament_size: int = 3
    crossover_rate: float = 0.80
    mutation_rate: float = 0.90
    random_injection_rate: float = 0.10
    uniqueness_attempts: int = 2_000

    def __post_init__(self):
        if self.population_size < 2:
            raise ValueError("Composition population must contain at least two decks")
        if not 1 <= self.elite_count < self.population_size:
            raise ValueError("Elite count must be smaller than the population")
        if not 2 <= self.tournament_size <= self.population_size:
            raise ValueError("Tournament size must be between 2 and population size")
        for name in ("crossover_rate", "mutation_rate", "random_injection_rate"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class EvaluatedDeckGenome:
    genome: DeckGenome
    fitness: float


def _legal_additions(
    cards: Sequence[str], card_pool: Mapping[str, object]
) -> list[str]:
    counts = Counter(cards)
    return [
        card_id
        for card_id, card in card_pool.items()
        if counts[card_id] < card_copy_limit(card)
    ]


def random_genome(
    card_pool: Mapping[str, object], # Prefiltered
    rng: random.Random,
    settings: CompositionEvolutionSettings,
) -> DeckGenome:
    target_size = rng.randint(MIN_DECK_SIZE, MAX_DECK_SIZE)
    cards: list[str] = []
    while len(cards) < target_size:
        legal = _legal_additions(cards, card_pool)
        if not legal:
            raise ValueError("Card pool cannot produce a legal deck composition")
        cards.append(rng.choice(legal))
    genome = DeckGenome(tuple(cards))
    genome.to_deck(card_pool)
    return genome


def mutate_genome(
    genome: DeckGenome,
    card_pool: Mapping[str, object],
    rng: random.Random,
    settings: CompositionEvolutionSettings,
) -> DeckGenome:
    """Apply deck composition edit, with 20% chance of second edit."""
    cards = list(genome.cards)
    edits = 2 if rng.random() < 0.20 else 1
    for _ in range(edits):
        operations = ["replace"] * 7 # higher likelyhood
        if len(cards) < MAX_DECK_SIZE:
            operations.append("add")
        if len(cards) > MIN_DECK_SIZE:
            operations.append("remove")

        operation = rng.choice(operations)
        if operation == "remove":
            cards.pop(rng.randrange(len(cards)))
            continue
        elif operation == "replace":
            removed = cards.pop(rng.randrange(len(cards)))
            legal = [card for card in _legal_additions(cards, card_pool) if card != removed]
            if not legal:
                cards.append(removed)
            else:
                cards.append(rng.choice(legal))
            continue
        elif operation == "add":
            legal = _legal_additions(cards, card_pool)
            if legal:
                cards.append(rng.choice(legal))
            continue

    child = DeckGenome(tuple(cards))
    child.to_deck(card_pool)
    return child


def crossover_genomes(
    first: DeckGenome,
    second: DeckGenome,
    card_pool: Mapping[str, object],
    rng: random.Random,
    settings: CompositionEvolutionSettings,
) -> DeckGenome:
    """Preserve shared copies, then inherit remaining slots from both parents."""
    target_size = rng.randint(
        max(MIN_DECK_SIZE, min(len(first.cards), len(second.cards))),
        min(MAX_DECK_SIZE, max(len(first.cards), len(second.cards))),
    )
    first_counts = Counter(first.cards) # Counter creates a Iterable of Item:Occurence_count
    second_counts = Counter(second.cards)
    shared = first_counts & second_counts # & performs intersect, fancy stuff
    cards = list(shared.elements())
    remaining = list(((first_counts | second_counts) - shared).elements()) # | performs join
    rng.shuffle(remaining)  # remaining contains non shared cards
    cards.extend(remaining[: target_size - len(cards)]) # fill in the new deck up to target size with remaining cards
    if len(cards) != target_size:
        raise RuntimeError("Valid parents could not produce a complete child")

    child = DeckGenome(tuple(cards))
    child.to_deck(card_pool)
    return child


def initial_population(
    card_pool: Mapping[str, object],
    rng: random.Random,
    settings: CompositionEvolutionSettings,
) -> list[DeckGenome]:
    population: list[DeckGenome] = []
    seen: set[DeckGenome] = set()
    attempts = 0
    while len(population) < settings.population_size:
        candidate = random_genome(card_pool, rng, settings)
        attempts += 1
        if candidate not in seen:
            seen.add(candidate)
            population.append(candidate)
        if attempts >= settings.uniqueness_attempts:
            raise RuntimeError("Could not create a unique initial deck population")
    return population


def _tournament(
    population: Sequence[EvaluatedDeckGenome],
    rng: random.Random,
    settings: CompositionEvolutionSettings,
) -> DeckGenome:
    # Randomly select the genomes that will compete in this tournament.
    contestants = rng.sample(list(population), settings.tournament_size)

    # Start by treating the first contestant as the current winner.
    winner = contestants[0]

    # Replace the current winner whenever a fitter contestant is found.
    for contestant in contestants[1:]:
        if contestant.fitness > winner.fitness:
            winner = contestant

    return winner.genome


def next_population(
    evaluated: Sequence[EvaluatedDeckGenome],
    card_pool: Mapping[str, object],
    rng: random.Random,
    settings: CompositionEvolutionSettings,
) -> list[DeckGenome]:
    """Breed one unique generation while retaining raw fitness unchanged."""
    if len(evaluated) != settings.population_size:
        raise ValueError("Evaluated population has the wrong size")
    ranked = sorted(evaluated, key=lambda item: item.fitness, reverse=True)
    population = [item.genome for item in ranked[: settings.elite_count]] # keep only elite_count best genomes
    seen = set(population)
    attempts = 0
    while len(population) < settings.population_size: # fill
        attempts += 1
        # new random
        if rng.random() < settings.random_injection_rate:
            new_genome = random_genome(card_pool, rng, settings)
        else:
            first = _tournament(ranked, rng, settings)
            new_genome = first
        # new child
            if rng.random() < settings.crossover_rate:
                second = _tournament(ranked, rng, settings)
                new_genome = crossover_genomes(first, second, card_pool, rng, settings)
        # new mutated
            if rng.random() < settings.mutation_rate:
                new_genome = mutate_genome(new_genome, card_pool, rng, settings)
        if new_genome not in seen:
            seen.add(new_genome)
            population.append(new_genome)
        if attempts >= settings.uniqueness_attempts:
            raise RuntimeError("Could not breed a unique deck population")
    return population
