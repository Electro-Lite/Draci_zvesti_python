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
from cards.power import Power
from core.config import MAX_DECK_SIZE, MIN_DECK_SIZE


def card_copy_limit(card) -> int:
    """Return the game copy limit used by deck construction."""
    return 1 if card.power == Power.LEGENDARY else 4


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
        return hashlib.md5(",".join(self.cards).encode("utf-8")).hexdigest()

    def validate(
        self,
        card_pool: Mapping[str, object],
    ) -> None:
        if not MIN_DECK_SIZE <= len(self.cards) <= MAX_DECK_SIZE:
            raise ValueError(
                f"Deck genome must contain {MIN_DECK_SIZE}-{MAX_DECK_SIZE} cards"
            )
        counts = Counter(self.cards)
        for card_id, count in counts.items():
            card = card_pool.get(card_id)
            if card is None:
                raise ValueError(f"Deck genome contains unknown card {card_id}")
            limit = card_copy_limit(card)
            if count > limit:
                raise ValueError(
                    f"Deck genome contains {count} copies of {card_id}; limit is {limit}"
                )

    def to_deck(self, card_pool: Mapping[str, object], name: str = "") -> Deck:
        self.validate(card_pool)
        deck = Deck()
        deck.name = name
        for card_id in self.cards:
            deck.add_card(card_pool[card_id])
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
    card_pool: Mapping[str, object],
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
    genome.validate(card_pool)
    return genome


def mutate_genome(
    genome: DeckGenome,
    card_pool: Mapping[str, object],
    rng: random.Random,
    settings: CompositionEvolutionSettings,
) -> DeckGenome:
    """Apply one local composition edit, with an occasional second edit."""
    cards = list(genome.cards)
    edits = 2 if rng.random() < 0.20 else 1
    for _ in range(edits):
        operations = ["replace"] * 7
        if len(cards) < MAX_DECK_SIZE:
            operations.append("add")
        if len(cards) > MIN_DECK_SIZE:
            operations.append("remove")
        operation = rng.choice(operations)
        if operation == "remove":
            cards.pop(rng.randrange(len(cards)))
            continue
        if operation == "replace":
            removed = cards.pop(rng.randrange(len(cards)))
            legal = [card for card in _legal_additions(cards, card_pool) if card != removed]
            if not legal:
                cards.append(removed)
            else:
                cards.append(rng.choice(legal))
            continue
        legal = _legal_additions(cards, card_pool)
        if legal:
            cards.append(rng.choice(legal))

    child = DeckGenome(tuple(cards))
    child.validate(card_pool)
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
    first_counts = Counter(first.cards)
    second_counts = Counter(second.cards)
    shared = first_counts & second_counts
    cards = list(shared.elements())
    inherited = list((first_counts - shared).elements()) + list(
        (second_counts - shared).elements()
    )
    rng.shuffle(inherited)
    for card_id in inherited:
        if len(cards) >= target_size:
            break
        if card_id in _legal_additions(cards, card_pool):
            cards.append(card_id)
    while len(cards) < target_size:
        legal = _legal_additions(cards, card_pool)
        if not legal:
            raise ValueError("Card pool cannot complete crossover offspring")
        cards.append(rng.choice(legal))
    child = DeckGenome(tuple(cards))
    child.validate(card_pool)
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
    contestants = rng.sample(list(population), settings.tournament_size)
    return max(contestants, key=lambda item: item.fitness).genome


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
    population = [item.genome for item in ranked[: settings.elite_count]]
    seen = set(population)
    attempts = 0
    while len(population) < settings.population_size:
        attempts += 1
        if rng.random() < settings.random_injection_rate:
            child = random_genome(card_pool, rng, settings)
        else:
            first = _tournament(ranked, rng, settings)
            child = first
            if rng.random() < settings.crossover_rate:
                second = _tournament(ranked, rng, settings)
                child = crossover_genomes(first, second, card_pool, rng, settings)
            if rng.random() < settings.mutation_rate:
                child = mutate_genome(child, card_pool, rng, settings)
        if child not in seen:
            seen.add(child)
            population.append(child)
        if attempts >= settings.uniqueness_attempts:
            raise RuntimeError("Could not breed a unique deck population")
    return population
