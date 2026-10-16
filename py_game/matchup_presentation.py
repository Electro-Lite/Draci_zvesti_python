"""Read-only presentation data for fixed-deck matchup training runs."""

from __future__ import annotations

import configparser
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from neat_ai.training_plan import matchup_checkpoints


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVALUATOR_CONFIG = PROJECT_ROOT / "neat_ai/configs/neat_config_evaluator.txt"


@dataclass(frozen=True)
class MatchupCardRow:
    card_id: str
    name: str
    color: str
    copies: int


@dataclass(frozen=True)
class MatchupDeck:
    deck_id: str
    name: str
    cards: tuple[MatchupCardRow, ...] = ()
    composition_available: bool = False


@dataclass(frozen=True)
class MatchupCheckpoint:
    generation: int
    games: int
    deck_a_wins: int
    draws: int
    deck_b_wins: int
    valid: bool
    issue: str = ""

    @property
    def rates(self) -> tuple[float, float, float] | None:
        if not self.valid or self.games <= 0:
            return None
        return (
            self.deck_a_wins / self.games,
            self.draws / self.games,
            self.deck_b_wins / self.games,
        )


@dataclass(frozen=True)
class MatchupWorkload:
    population_size: int
    requested_generations: int
    completed_generations: int
    games_per_genome_per_generation: int
    learning_games_per_generation: int
    planned_learning_games: int
    completed_learning_games_estimate: int
    planned_checkpoint_generations: tuple[int, ...]
    recorded_checkpoints: int
    games_per_checkpoint: int
    planned_evaluation_games: int
    recorded_evaluation_games: int

    @property
    def planned_total_games(self) -> int:
        return self.planned_learning_games + self.planned_evaluation_games

    @property
    def completed_total_estimate(self) -> int:
        return self.completed_learning_games_estimate + self.recorded_evaluation_games


@dataclass(frozen=True)
class MatchupPresentation:
    deck_a: MatchupDeck
    deck_b: MatchupDeck
    checkpoints: tuple[MatchupCheckpoint, ...]
    workload: MatchupWorkload
    requested_final_generation: int
    final_checkpoint: MatchupCheckpoint | None
    next_checkpoint_generation: int | None
    summary_available: bool
    issues: tuple[str, ...] = ()


def evaluator_population_size(config_path: Path = EVALUATOR_CONFIG) -> int:
    """Read the configured genomes in each evaluator population."""
    parser = configparser.ConfigParser()
    try:
        parser.read(config_path)
        value = parser.getint("NEAT", "pop_size")
    except (OSError, ValueError, configparser.Error):
        return 0
    return max(0, value)


def _integer(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _deck_composition(
    deck_id: str,
    fallback_name: str,
    deck_loader,
    expected_card_count=None,
) -> MatchupDeck:
    if not deck_id:
        return MatchupDeck("", fallback_name or "Unknown deck")
    try:
        deck = deck_loader(deck_id)
    except Exception:  # A missing/corrupt current DB record must not hide run evidence.
        deck = None
    if deck is None:
        return MatchupDeck(deck_id, fallback_name or deck_id)
    try:
        expected = expected_card_count(deck_id) if expected_card_count else None
    except Exception:
        expected = -1
    if expected is not None and expected != len(getattr(deck, "cards", ())):
        return MatchupDeck(
            deck_id,
            str(getattr(deck, "name", "") or fallback_name or deck_id),
        )

    grouped: dict[tuple[str, str, str], int] = Counter()
    for card in getattr(deck, "cards", ()):
        card_id = str(getattr(card, "id", "") or "")
        name = str(getattr(card, "name", "") or card_id or "Unknown card")
        color_value = getattr(card, "color", None)
        color = str(getattr(color_value, "name", color_value) or "Unknown").title()
        grouped[(card_id, name, color)] += 1
    rows = tuple(
        MatchupCardRow(card_id, name, color, copies)
        for (card_id, name, color), copies in sorted(
            grouped.items(), key=lambda item: (item[0][1].casefold(), item[0][0])
        )
    )
    return MatchupDeck(
        deck_id,
        str(getattr(deck, "name", "") or fallback_name or deck_id),
        rows,
        True,
    )


def _saved_deck_composition(deck_id: str, name: str, values) -> MatchupDeck | None:
    if not isinstance(values, list) or not values:
        return None
    grouped: dict[tuple[str, str, str], int] = Counter()
    for value in values:
        if isinstance(value, dict):
            card_id = str(value.get("id") or "")
            card_name = str(value.get("name") or card_id or "Unknown card")
            color = str(value.get("color") or "Unknown").title()
        else:
            card_id = str(value or "")
            card_name = card_id or "Unknown card"
            color = "Unknown"
        if not card_id:
            return None
        grouped[(card_id, card_name, color)] += 1
    rows = tuple(
        MatchupCardRow(card_id, card_name, color, copies)
        for (card_id, card_name, color), copies in grouped.items()
    )
    return MatchupDeck(deck_id, name or deck_id or "Unknown deck", rows, True)


def _checkpoint(item) -> MatchupCheckpoint | None:
    if not isinstance(item, dict):
        return None
    generation = _integer(item.get("generation"), -1)
    if generation < 0:
        return None
    games = _integer(item.get("games"), -1)
    deck_a_wins = _integer(item.get("deck_1_wins", item.get("ai_wins")), -1)
    draws = _integer(item.get("draws"), -1)
    deck_b_wins = _integer(item.get("deck_2_wins", item.get("random_wins")), -1)
    values = (games, deck_a_wins, draws, deck_b_wins)
    if any(value < 0 for value in values):
        return MatchupCheckpoint(
            generation, max(0, games), max(0, deck_a_wins), max(0, draws),
            max(0, deck_b_wins), False, "Missing or invalid W / D / L data",
        )
    if games == 0:
        return MatchupCheckpoint(
            generation, games, deck_a_wins, draws, deck_b_wins, False,
            "No evaluation games were recorded",
        )
    if deck_a_wins + draws + deck_b_wins != games:
        return MatchupCheckpoint(
            generation, games, deck_a_wins, draws, deck_b_wins, False,
            "W + D + L does not match the recorded game count",
        )
    return MatchupCheckpoint(
        generation, games, deck_a_wins, draws, deck_b_wins, True,
    )


def load_matchup_presentation(
    job,
    deck_loader: Callable[[str], object],
    *,
    population_size: int | None = None,
    completed_generations: int | None = None,
    expected_card_count: Callable[[str], int | None] | None = None,
) -> MatchupPresentation:
    """Load and validate one matchup run without doing work in the draw loop."""
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
    requested_generations = _integer(
        request.get("evaluator_generations", settings.get("generations")), 0
    )
    games_per_checkpoint = _integer(
        request.get("evaluation_games", settings.get("evaluation_games")), 0
    )
    deck_a_id = str(summary.get("deck_id") or request.get("deck_id") or "")
    deck_b_id = str(
        summary.get("opponent_deck_id") or request.get("opponent_deck_id") or ""
    )
    deck_a_name = str(summary.get("deck_name") or deck_a_id or "Deck A")
    deck_b_name = str(
        summary.get("opponent_deck_name") or deck_b_id or "Deck B"
    )
    deck_a = _saved_deck_composition(
        deck_a_id, deck_a_name, summary.get("deck_1_cards")
    ) or _deck_composition(
        deck_a_id, deck_a_name, deck_loader, expected_card_count
    )
    deck_b = _saved_deck_composition(
        deck_b_id, deck_b_name, summary.get("deck_2_cards")
    ) or _deck_composition(
        deck_b_id, deck_b_name, deck_loader, expected_card_count
    )

    parsed = [
        row for row in (_checkpoint(item) for item in summary.get("skill_evaluations", ()))
        if row is not None
    ]
    checkpoints = tuple(sorted(parsed, key=lambda row: row.generation))
    planned = matchup_checkpoints(requested_generations) if requested_generations > 0 else ()
    recorded_generations = {row.generation for row in checkpoints}
    next_generation = next(
        (generation for generation in planned if generation not in recorded_generations), None
    )
    final = next(
        (
            row for row in reversed(checkpoints)
            if row.generation == requested_generations and row.valid
        ),
        None,
    )
    pop_size = evaluator_population_size() if population_size is None else population_size
    completed_generations = max(
        max((row.generation for row in checkpoints), default=0),
        max(0, completed_generations or 0),
    )
    learning_per_generation = pop_size * pop_size
    recorded_games = sum(row.games for row in checkpoints if row.valid)
    workload = MatchupWorkload(
        population_size=pop_size,
        requested_generations=requested_generations,
        completed_generations=min(completed_generations, requested_generations),
        games_per_genome_per_generation=pop_size,
        learning_games_per_generation=learning_per_generation,
        planned_learning_games=learning_per_generation * requested_generations,
        completed_learning_games_estimate=learning_per_generation
        * min(completed_generations, requested_generations),
        planned_checkpoint_generations=planned,
        recorded_checkpoints=len(checkpoints),
        games_per_checkpoint=games_per_checkpoint,
        planned_evaluation_games=len(planned) * games_per_checkpoint,
        recorded_evaluation_games=recorded_games,
    )
    issues = []
    if summary_available and not checkpoints:
        issues.append("The summary contains no readable checkpoint rows.")
    issues.extend(
        f"Generation {row.generation}: {row.issue}" for row in checkpoints if not row.valid
    )
    if requested_generations and any(
        row.generation == requested_generations and not row.valid for row in checkpoints
    ):
        issues.append("The requested final checkpoint is incomplete or malformed.")
    return MatchupPresentation(
        deck_a=deck_a,
        deck_b=deck_b,
        checkpoints=checkpoints,
        workload=workload,
        requested_final_generation=requested_generations,
        final_checkpoint=final,
        next_checkpoint_generation=next_generation,
        summary_available=summary_available,
        issues=tuple(issues),
    )
