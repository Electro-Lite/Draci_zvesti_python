"""Read-only presentation data for counter-deck training runs."""

from __future__ import annotations

import configparser
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILDER_CONFIG = PROJECT_ROOT / "neat_ai/configs/neat_config_builder.txt"
EVALUATOR_CONFIG = PROJECT_ROOT / "neat_ai/configs/neat_config_evaluator.txt"
COMPARISON_TARGET = 1_000


@dataclass(frozen=True)
class CounterCardRow:
    card_id: str
    name: str
    color: str
    copies: int


@dataclass(frozen=True)
class CounterDeckSnapshot:
    deck_id: str
    name: str
    cards: tuple[CounterCardRow, ...] = ()

    @property
    def total_cards(self) -> int:
        return sum(card.copies for card in self.cards)

    @property
    def distinct_cards(self) -> int:
        return len(self.cards)


@dataclass(frozen=True)
class CounterCandidate:
    key: str
    builder_id: str
    deck: CounterDeckSnapshot
    generation: int
    games: int
    counter_wins: int
    draws: int
    subject_wins: int
    counter_fitness: float
    shared_cards: int
    valid: bool
    issue: str = ""

    @property
    def rates(self) -> tuple[float, float, float] | None:
        if not self.valid or self.games <= 0:
            return None
        return (
            self.counter_wins / self.games,
            self.draws / self.games,
            self.subject_wins / self.games,
        )

    @property
    def counter_win_rate(self) -> float | None:
        rates = self.rates
        return rates[0] if rates else None

    @property
    def exploratory(self) -> bool:
        return self.games < COMPARISON_TARGET


@dataclass(frozen=True)
class CounterWorkload:
    builder_population_size: int
    controller_population_size: int
    requested_counter_generations: int
    completed_counter_generations: int
    requested_controller_generations: int
    completed_controller_generations_estimate: int
    games_per_candidate: int
    final_candidate_count: int
    planned_validation_games: int
    recorded_validation_games: int
    planned_learning_games: int
    completed_learning_games_estimate: int

    @property
    def planned_total_games(self) -> int:
        return self.planned_validation_games + self.planned_learning_games

    @property
    def completed_total_estimate(self) -> int:
        return self.recorded_validation_games + self.completed_learning_games_estimate


@dataclass(frozen=True)
class CounterPresentation:
    subject: CounterDeckSnapshot
    candidates: tuple[CounterCandidate, ...]
    default_candidate_key: str | None
    workload: CounterWorkload
    pooled_subject_wins: int
    pooled_draws: int
    pooled_counter_wins: int
    summary_available: bool
    issues: tuple[str, ...] = ()

    def candidate(self, key: str | None) -> CounterCandidate | None:
        return next((item for item in self.candidates if item.key == key), None)


@dataclass(frozen=True)
class CounterBarSegment:
    key: str
    count: int
    ratio: float
    inline_label: bool


def counter_bar_segments(
    candidate: CounterCandidate,
    *,
    minimum_inline_ratio: float = 0.09,
) -> tuple[CounterBarSegment, ...]:
    """Describe green/gray/red segments and where their labels can fit."""
    rates = candidate.rates or (0.0, 0.0, 0.0)
    counts = (candidate.counter_wins, candidate.draws, candidate.subject_wins)
    return tuple(
        CounterBarSegment(key, count, ratio, count > 0 and ratio >= minimum_inline_ratio)
        for key, count, ratio in zip(("counter", "draw", "subject"), counts, rates)
    )


def _integer(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _number(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _request_population_size(request, profile: str) -> int | None:
    try:
        value = request["neat_config_overrides"][profile]["NEAT.pop_size"]
    except (KeyError, TypeError):
        return None
    parsed = _integer(value, -1)
    return parsed if parsed > 0 else None


def _population_size(path: Path) -> int:
    parser = configparser.ConfigParser()
    try:
        parser.read(path)
        return max(0, parser.getint("NEAT", "pop_size"))
    except (OSError, ValueError, configparser.Error):
        return 0


def _metadata(card_loader, card_id: str) -> tuple[str, str]:
    try:
        card = card_loader(card_id)
    except Exception:
        card = None
    if card is None:
        return card_id or "Unknown card", "Unknown"
    name = str(getattr(card, "name", "") or card_id or "Unknown card")
    color_value = getattr(card, "color", None)
    color = str(getattr(color_value, "name", color_value) or "Unknown").title()
    return name, color


def _snapshot(
    deck_id: str,
    name: str,
    card_ids,
    saved_names,
    card_loader,
) -> CounterDeckSnapshot:
    ids = [str(value or "") for value in (card_ids or ())]
    names = [str(value or "") for value in (saved_names or ())]
    grouped = Counter(ids)
    rows = []
    seen = set()
    for index, card_id in enumerate(ids):
        if card_id in seen:
            continue
        seen.add(card_id)
        live_name, color = _metadata(card_loader, card_id)
        saved_name = next(
            (
                names[position]
                for position, value in enumerate(ids)
                if value == card_id and position < len(names) and names[position]
            ),
            "",
        )
        rows.append(
            CounterCardRow(
                card_id=card_id,
                name=saved_name or live_name or card_id or "Unknown card",
                color=color,
                copies=grouped[card_id],
            )
        )
    return CounterDeckSnapshot(str(deck_id or ""), str(name or deck_id or "Deck"), tuple(rows))


def _candidate(item, index, subject_ids, card_loader) -> CounterCandidate | None:
    if not isinstance(item, dict):
        return None
    builder_id = str(item.get("builder_id", "") or "")
    deck_id = str(item.get("deck_id", "") or "")
    key = deck_id or (f"builder-{builder_id}" if builder_id else f"candidate-{index}")
    cards = tuple(str(value or "") for value in (item.get("cards") or ()))
    deck = _snapshot(
        deck_id,
        str(item.get("deck_name") or deck_id or f"Counter {index + 1}"),
        cards,
        item.get("card_names") or (),
        card_loader,
    )
    generation = _integer(item.get("generation"), 0)
    games = _integer(item.get("games"), -1)
    counter_wins = _integer(item.get("counter_wins"), -1)
    draws = _integer(item.get("draws"), -1)
    subject_wins = _integer(item.get("subject_wins"), -1)
    values = (games, counter_wins, draws, subject_wins)
    valid = all(value >= 0 for value in values) and games > 0
    issue = ""
    if not valid:
        issue = "Missing, invalid, or zero-game candidate result"
    elif counter_wins + draws + subject_wins != games:
        valid = False
        issue = "W + D + L does not match the candidate game count"
    shared = sum((Counter(subject_ids) & Counter(cards)).values())
    reported_shared = item.get("shared_cards")
    if reported_shared is not None and _integer(reported_shared, shared) != shared:
        issue = f"{issue}; " if issue else ""
        issue += "saved shared-card count disagrees with card snapshots"
    return CounterCandidate(
        key=key,
        builder_id=builder_id,
        deck=deck,
        generation=generation,
        games=max(0, games),
        counter_wins=max(0, counter_wins),
        draws=max(0, draws),
        subject_wins=max(0, subject_wins),
        counter_fitness=_number(item.get("counter_fitness"), float("-inf")),
        shared_cards=shared,
        valid=valid,
        issue=issue,
    )


def _same_candidate(candidate: CounterCandidate, row) -> bool:
    if not isinstance(row, dict):
        return False
    return bool(
        (row.get("deck_id") and str(row.get("deck_id")) == candidate.deck.deck_id)
        or (
            row.get("builder_id") is not None
            and str(row.get("builder_id")) == candidate.builder_id
        )
    )


def load_counter_presentation(
    job,
    card_loader: Callable[[str], object],
    *,
    completed_counter_generations: int = 0,
    builder_population_size: int | None = None,
    controller_population_size: int | None = None,
) -> CounterPresentation:
    """Load one counter run, preserving saved deck identities and real samples."""
    request = getattr(job, "request", None) or {}
    try:
        summary = json.loads(Path(job.summary_path).read_text())
        if not isinstance(summary, dict):
            summary = {}
        summary_available = bool(summary)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        summary = {}
        summary_available = False
    settings = summary.get("settings") if isinstance(summary.get("settings"), dict) else {}
    subject_ids = tuple(str(value or "") for value in (summary.get("subject_cards") or ()))
    subject = _snapshot(
        str(summary.get("deck_id") or request.get("deck_id") or ""),
        str(summary.get("deck_name") or summary.get("deck_id") or request.get("deck_id") or "Selected deck"),
        subject_ids,
        (),
        card_loader,
    )
    candidates = tuple(
        candidate
        for candidate in (
            _candidate(item, index, subject_ids, card_loader)
            for index, item in enumerate(summary.get("counter_matchups") or ())
        )
        if candidate is not None
    )
    candidates = tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.counter_win_rate if item.counter_win_rate is not None else -1.0,
                item.counter_fitness,
                item.deck.name,
            ),
            reverse=True,
        )
    )
    top_row = summary.get("top_counter") or {}
    default = next((item.key for item in candidates if _same_candidate(item, top_row)), None)
    if default is None and candidates:
        default = candidates[0].key

    requested_counter = _integer(
        request.get("outer_generations", settings.get("counter_generations")), 0
    )
    requested_controller = _integer(
        request.get("evaluator_generations", settings.get("controller_generations")), 0
    )
    games_per_candidate = _integer(
        request.get("evaluation_games", settings.get("evaluation_games")), 0
    )
    recorded_generations = [
        _integer(item.get("generation"), 0)
        for item in (summary.get("skill_evaluations") or ())
        if isinstance(item, dict)
    ]
    completed_counter = min(
        requested_counter,
        max([completed_counter_generations, *recorded_generations], default=0),
    )
    completed_controller = (
        min(
            requested_controller,
            math.ceil(requested_controller * completed_counter / requested_counter),
        )
        if requested_counter > 0
        else 0
    )
    builder_size = (
        _request_population_size(request, "builder")
        or _population_size(BUILDER_CONFIG)
        if builder_population_size is None
        else max(0, builder_population_size)
    )
    controller_size = (
        _request_population_size(request, "evaluator")
        or _population_size(EVALUATOR_CONFIG)
        if controller_population_size is None
        else max(0, controller_population_size)
    )
    recorded_validation = sum(
        max(0, _integer(item.get("games"), 0))
        for item in (summary.get("skill_evaluations") or ())
        if isinstance(item, dict)
    ) or sum(item.games for item in candidates if item.valid)
    workload = CounterWorkload(
        builder_population_size=builder_size,
        controller_population_size=controller_size,
        requested_counter_generations=requested_counter,
        completed_counter_generations=completed_counter,
        requested_controller_generations=requested_controller,
        completed_controller_generations_estimate=completed_controller,
        games_per_candidate=games_per_candidate,
        final_candidate_count=len(candidates),
        planned_validation_games=(
            builder_size * requested_counter * games_per_candidate
        ),
        recorded_validation_games=recorded_validation,
        planned_learning_games=(
            controller_size * controller_size * requested_controller
        ),
        completed_learning_games_estimate=(
            controller_size * controller_size * completed_controller
        ),
    )
    evaluation = summary.get("evaluation") if isinstance(summary.get("evaluation"), dict) else {}
    issues = tuple(
        f"{item.deck.name}: {item.issue}" for item in candidates if item.issue
    )
    return CounterPresentation(
        subject=subject,
        candidates=candidates,
        default_candidate_key=default,
        workload=workload,
        pooled_subject_wins=_integer(evaluation.get("subject_wins", evaluation.get("ai_wins")), 0),
        pooled_draws=_integer(evaluation.get("draws"), 0),
        pooled_counter_wins=_integer(evaluation.get("counter_wins", evaluation.get("random_wins")), 0),
        summary_available=summary_available,
        issues=issues,
    )
