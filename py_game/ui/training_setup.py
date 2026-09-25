"""Pure training-setup models used by the Pygame menu and tests."""

from __future__ import annotations

from dataclasses import dataclass

from neat_ai.training_plan import evaluation_checkpoints
from py_game.training_service import TrainingKind, TrainingRequest


@dataclass(frozen=True)
class TrainingPreset:
    key: str
    label: str
    generations: int
    workers: int
    evaluation_games: int
    outer_generations: int = 1
    matches_per_genome: int = 12
    holdout_seed_pairs: int = 20
    seed_set_index: int = 0


PLAYER_PRESETS = (
    TrainingPreset("quick", "Quick check", 10, 4, 20),
    TrainingPreset("balanced", "Balanced", 40, 8, 100),
    TrainingPreset("deep", "Deep study", 65, 12, 300),
)

BUILDER_PRESETS = (
    TrainingPreset("quick", "Quick check", 35, 4, 20, 1, 4, 5, 0),
    TrainingPreset("balanced", "Balanced", 50, 8, 100, 1, 12, 20, 0),
    TrainingPreset("deep", "Deep study", 65, 12, 300, 10, 12, 20, 2),
)


@dataclass(frozen=True)
class TrainingWorkload:
    headline: str
    details: tuple[str, ...]


def presets_for(kind: TrainingKind) -> tuple[TrainingPreset, ...]:
    return PLAYER_PRESETS if kind == TrainingKind.PLAYER_DECK else BUILDER_PRESETS


def training_workload(request: TrainingRequest) -> TrainingWorkload:
    """Describe scheduled work without pretending to predict wall-clock cost."""
    if request.kind == TrainingKind.PLAYER_DECK:
        checkpoints = evaluation_checkpoints(request.evaluator_generations)
        checkpoint_games = len(checkpoints) * request.evaluation_games
        # The player trainer currently uses an all-vs-all population of 15.
        training_games = request.evaluator_generations * (15 * 14 // 2)
        total_games = training_games + checkpoint_games
        return TrainingWorkload(
            headline=f"About {total_games:,} simulated games",
            details=(
                f"{request.evaluator_generations} controller generations · {training_games:,} training games",
                f"{len(checkpoints)} maturity checkpoints · {checkpoint_games:,} evaluation games total",
                f"{request.workers} workers · checkpoints at generations {', '.join(map(str, checkpoints))}",
                "Duration depends on CPU speed and game length; this is workload, not an ETA.",
            ),
        )

    outer_matchups = (
        len(request.seeds)
        * request.outer_generations
        * 20
        * request.matches_per_genome
        // 2
    )
    return TrainingWorkload(
        headline=f"{outer_matchups:,} outer matchups plus nested controller training",
        details=(
            f"{len(request.seeds)} seed run(s) · {request.outer_generations} outer generations",
            f"{request.evaluator_generations} inner generations per candidate evaluation",
            f"{request.matches_per_genome} rivals per candidate · {request.holdout_seed_pairs} holdout pairs",
            "Deck evolution is substantially more expensive than player-controller training.",
        ),
    )


def wilson_interval(wins: int, games: int, z: float = 1.96) -> tuple[float, float]:
    """Return a 95% Wilson interval for the observed win proportion."""
    if games <= 0:
        return 0.0, 0.0
    proportion = wins / games
    denominator = 1 + z * z / games
    center = (proportion + z * z / (2 * games)) / denominator
    margin = (
        z
        * ((proportion * (1 - proportion) / games + z * z / (4 * games * games)) ** 0.5)
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)
