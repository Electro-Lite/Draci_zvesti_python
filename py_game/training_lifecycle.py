"""Pure lifecycle rules for the Training Arena.

Keeping this decision table outside Pygame makes it difficult for a visual
screen to accidentally expose partial analytical results.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


ACTIVE_STATUSES = frozenset({"pending", "running", "stopping"})
TERMINAL_NO_RESULT_STATUSES = frozenset(
    {"failed", "stopped", "cancelled", "interrupted", "incomplete"}
)


class ArenaDestination(str, Enum):
    PROGRESS = "progress"
    COMPLETION_HANDOFF = "completion_handoff"
    RESULTS = "results"
    TERMINAL = "terminal"


@dataclass(frozen=True)
class ResultArtifactStatus:
    ready: bool
    state: str
    message: str

    @classmethod
    def waiting(cls, message: str = "Preparing results…"):
        return cls(False, "preparing", message)

    @classmethod
    def available(cls, message: str = "Result artifact verified"):
        return cls(True, "ready", message)

    @classmethod
    def invalid(cls, message: str):
        return cls(False, "invalid", message)


def arena_destination(
    status: str,
    *,
    watched_live: bool,
    results_opened: bool,
    artifact: ResultArtifactStatus | None,
) -> ArenaDestination:
    """Return the only legal Arena destination for the current run state."""
    normalized = str(status or "pending").lower()
    if normalized in ACTIVE_STATUSES:
        return ArenaDestination.PROGRESS
    if normalized != "completed":
        return ArenaDestination.TERMINAL
    if artifact is None or not artifact.ready:
        return ArenaDestination.COMPLETION_HANDOFF
    if watched_live and not results_opened:
        return ArenaDestination.COMPLETION_HANDOFF
    return ArenaDestination.RESULTS


def overall_progress(telemetry) -> float | None:
    """Calculate progress only from counters explicitly emitted by a trainer."""
    status = str(getattr(telemetry, "status", "")).lower()
    if status == "completed":
        return 1.0
    phase_progress = getattr(telemetry, "phase_progress", None)
    if phase_progress is not None:
        # The last generation can finish before summaries and model artifacts
        # are flushed. Only authoritative process completion may display 100%.
        return max(0.0, min(0.99, float(phase_progress)))
    generation = int(getattr(telemetry, "generation", 0) or 0)
    total = int(getattr(telemetry, "total_generations", 0) or 0)
    if total <= 0 or generation <= 0:
        return None
    # Generation is the currently active unit.  Without a reported nested
    # fraction, only preceding generations are known complete.
    return max(0.0, min(1.0, (generation - 1) / total))


def eta_label(telemetry, duration_formatter) -> str:
    """Present a trainer ETA only while its telemetry is fresh enough."""
    eta = getattr(telemetry, "eta_seconds", None)
    age = getattr(telemetry, "telemetry_age_seconds", None)
    if eta is None or (age is not None and age > 120):
        return "Estimating…"
    return f"About {duration_formatter(max(0.0, float(eta)))}"


def mission_result_label(kind: str) -> str:
    return {
        "player_deck": "Counter results",
        "Counter-deck training": "Counter results",
        "matchup_evaluation": "Duel results",
        "Deck matchup evaluation": "Duel results",
        "deck_builder": "Evolution results",
        "Deck builder experiment": "Evolution results",
    }.get(str(kind), "results")


def mission_progress_name(kind: str) -> str:
    return {
        "player_deck": "Counter finding",
        "Counter-deck training": "Counter finding",
        "matchup_evaluation": "Matchup evaluation",
        "Deck matchup evaluation": "Matchup evaluation",
        "deck_builder": "Deck evolution",
        "Deck builder experiment": "Deck evolution",
    }.get(str(kind), "AI training")


def progress_levels(kind: str, telemetry) -> tuple[tuple[str, str, float | None], ...]:
    """Describe only hierarchy levels represented by current telemetry."""
    generation = int(getattr(telemetry, "generation", 0) or 0)
    total_generations = int(getattr(telemetry, "total_generations", 0) or 0)
    completed = int(getattr(telemetry, "round_completed", 0) or 0)
    total = int(getattr(telemetry, "round_total", 0) or 0)
    phase = str(getattr(telemetry, "phase", "") or "")
    kind = {
        "Counter-deck training": "player_deck",
        "Deck matchup evaluation": "matchup_evaluation",
        "Deck builder experiment": "deck_builder",
    }.get(str(kind), str(kind))
    rows = []
    if total_generations:
        label = {
            "player_deck": "Counter generations",
            "matchup_evaluation": "Controller generations",
            "deck_builder": "Outer generations",
        }.get(str(kind), "Generations")
        rows.append(
            (
                label,
                f"{generation} / {total_generations}",
                overall_progress(telemetry),
            )
        )
    if total:
        if kind == "deck_builder":
            label, unit = "Current deck-pairing queue", "pairings"
        elif kind == "player_deck" and phase == "counter_controller_training":
            label, unit = "Persistent controller training", "generations"
        elif kind == "player_deck":
            label, unit = "Current candidate validation", "games"
        elif kind == "matchup_evaluation" and "checkpoint" in phase:
            label, unit = "Current checkpoint evaluation", "games"
        else:
            label, unit = "Current reported work", "units"
        rows.append(
            (
                label,
                f"{completed:,} / {total:,} {unit}",
                completed / total if total else None,
            )
        )
    elif kind == "deck_builder" and phase == "deck_evolution":
        rows.append(
            (
                "Nested controller learning",
                "Running · exact count unavailable",
                None,
            )
        )
    return tuple(rows)
