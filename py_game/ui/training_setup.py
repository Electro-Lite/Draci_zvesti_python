"""Pure training-setup models used by the Pygame menu and tests."""

from __future__ import annotations

from dataclasses import dataclass

from neat_ai.training_plan import matchup_checkpoints
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
    TrainingPreset("quick", "Quick exploratory", 10, 4, 100, outer_generations=1),
    TrainingPreset("balanced", "Balanced", 40, 8, 1_000, outer_generations=5),
    TrainingPreset("deep", "Deep study", 65, 12, 2_000, outer_generations=10),
)

MATCHUP_PRESETS = (
    TrainingPreset("quick", "Quick exploratory", 10, 4, 100),
    TrainingPreset("balanced", "Balanced", 40, 8, 1_000),
    TrainingPreset("deep", "Deep study", 65, 12, 2_000),
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
    if kind in {TrainingKind.PLAYER_DECK, TrainingKind.COUNTER_V2}:
        return PLAYER_PRESETS
    if kind == TrainingKind.MATCHUP_EVALUATION:
        return MATCHUP_PRESETS
    return BUILDER_PRESETS


def training_workload(request: TrainingRequest) -> TrainingWorkload:
    """Describe scheduled work without pretending to predict wall-clock cost."""
    comparison_prefix = (
        "Exploratory · " if request.evaluation_games < 1_000 else ""
    )
    if request.kind in {TrainingKind.PLAYER_DECK, TrainingKind.COUNTER_V2}:
        controller_games = request.evaluator_generations * (15 * 15)
        candidate_games = (
            request.outer_generations * 20 * request.evaluation_games
        )
        total_games = controller_games + candidate_games
        return TrainingWorkload(
            headline=f"{comparison_prefix}About {total_games:,} simulated games",
            details=(
                (
                    f"{request.outer_generations} persistent counter-deck generations · "
                    + (
                        "20 direct composition candidates each"
                        if request.kind == TrainingKind.COUNTER_V2
                        else "up to 20 NEAT-built legal candidates each"
                    )
                ),
                f"{request.evaluator_generations} persistent controller generations · about {controller_games:,} learning games",
                f"{request.evaluation_games} validation games per candidate · {candidate_games:,} counter tests",
                "Planned validation assumes all 20 generated decks are legal; 1,000 games per candidate is the comparison target.",
            ),
        )

    if request.kind == TrainingKind.MATCHUP_EVALUATION:
        checkpoints = matchup_checkpoints(request.evaluator_generations)
        checkpoint_games = len(checkpoints) * request.evaluation_games
        # Matchup controller learning evaluates every genome pairing from
        # both seat/player-ID perspectives using the same game seed.
        training_games = request.evaluator_generations * (15 * 15) * 2
        total_games = training_games + checkpoint_games
        return TrainingWorkload(
            headline=f"{comparison_prefix}About {total_games:,} simulated games",
            details=(
                f"Two controller populations coevolve for {request.evaluator_generations} generations · about {training_games:,} paired-seat learning games",
                f"{len(checkpoints)} win-rate checkpoints · {checkpoint_games:,} seat-balanced evaluation games",
                f"{request.workers} workers · checkpoints at generations {', '.join(map(str, checkpoints))}",
                "1,000 games per checkpoint is the comparison target; workload is not an ETA or certainty guarantee.",
            ),
        )

    outer_matchups = (
        len(request.seeds)
        * request.outer_generations
        * 20
        * request.matches_per_genome
        // 2
    )
    evolution_details = (
        (
            f"20 unique legal compositions per generation · direct crossover and mutation",
            f"{request.evaluator_generations} controller generations per distinct deck matchup",
            f"Each composition faces up to {request.matches_per_genome} rivals · {request.holdout_seed_pairs} holdout pairs",
        )
        if request.kind == TrainingKind.DECK_POOL_V2
        else (
            "20 NEAT deck-builder genomes construct candidate decks per generation",
            f"{request.evaluator_generations} controller generations per generated-deck matchup",
            f"Each builder faces up to {request.matches_per_genome} rivals · {request.holdout_seed_pairs} holdout pairs",
        )
    )
    return TrainingWorkload(
        headline=f"{outer_matchups:,} outer matchups plus nested controller training",
        details=(
            f"{len(request.seeds)} seed run(s) · {request.outer_generations} outer generations",
            *evolution_details,
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
