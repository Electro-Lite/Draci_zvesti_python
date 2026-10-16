"""Coevolve controllers for two fixed decks and report matchup win rates."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time

from neat_ai.deck_evaluator import EvaluatorSettings, train_deck
from neat_ai.player_artifacts import export_player_artifact
from neat_ai.training_plan import matchup_checkpoints
from neat_ai.training_telemetry import emit_training_event
from utils.database_utils import DBUtil


@dataclass(frozen=True)
class MatchupTrainerSettings:
    generations: int = 40
    workers: int = 8
    evaluation_games: int = 1_000
    seed: int = 104729
    run_label: str = "matchup-evaluation"

    def __post_init__(self):
        if not 2 <= self.generations <= 10_000:
            raise ValueError("Generations must be between 2 and 10000")
        if not 1 <= self.workers <= 128:
            raise ValueError("Workers must be between 1 and 128")
        if not 2 <= self.evaluation_games <= 100_000 or self.evaluation_games % 2:
            raise ValueError(
                "Evaluation games must be an even number between 2 and 100000"
            )


def evaluator_settings(settings: MatchupTrainerSettings) -> EvaluatorSettings:
    checkpoints = matchup_checkpoints(settings.generations)
    intermediate = tuple(value for value in checkpoints if value < settings.generations)
    early = intermediate[0] if intermediate else 1
    return EvaluatorSettings(
        generations=settings.generations,
        workers=settings.workers,
        holdout_seed_pairs=settings.evaluation_games // 2,
        early_holdout_generation=early,
        diagnostic_holdout_generations=intermediate,
        crossplay_reference_generation=None,
        seed=settings.seed,
        log_training_games=False,
    )


def _deck_snapshot(deck):
    return [
        {
            "id": str(getattr(card, "id", "") or ""),
            "name": str(getattr(card, "name", "") or getattr(card, "id", "") or "Unknown card"),
            "color": str(
                getattr(
                    getattr(card, "color", None),
                    "name",
                    getattr(card, "color", None),
                )
                or "Unknown"
            ).title(),
        }
        for card in getattr(deck, "cards", ())
    ]


def build_summary(
    deck_1,
    deck_2,
    settings,
    checkpoints,
    elapsed_seconds,
    scores=None,
    player_artifacts=(),
):
    """Build a UI-readable report from all completed holdout checkpoints."""
    if not checkpoints:
        raise ValueError("At least one completed matchup checkpoint is required")
    final = checkpoints[-1]
    best_fitness = max(scores) if scores is not None else max(
        final["deck_1_fitness"],
        final["deck_2_fitness"],
    )
    return {
        "kind": "matchup_evaluation",
        "deck_id": deck_1.id,
        "deck_name": deck_1.name,
        "deck_1_cards": _deck_snapshot(deck_1),
        "opponent_deck_id": deck_2.id,
        "opponent_deck_name": deck_2.name,
        "deck_2_cards": _deck_snapshot(deck_2),
        "settings": asdict(settings),
        "best_fitness": best_fitness,
        "elapsed_seconds": elapsed_seconds,
        "evaluation": {
            "games": final["games"],
            "ai_wins": final["deck_1_wins"],
            "draws": final["draws"],
            "random_wins": final["deck_2_wins"],
            "ai_win_rate": final["deck_1_wins"] / final["games"],
        },
        "skill_evaluations": list(checkpoints),
        "player_artifacts": [str(path) for path in player_artifacts],
    }


def evaluate_matchup(deck_1, deck_2, settings: MatchupTrainerSettings | None = None):
    if deck_1 is None or deck_2 is None:
        raise ValueError("Both matchup decks must exist")
    deck_1.validate()
    deck_2.validate()
    settings = settings or MatchupTrainerSettings()
    started_at = time()
    checkpoints = []
    final_controllers = []
    summary_path = os.environ.get("PLAYER_TRAINING_SUMMARY_PATH")
    emit_training_event(
        "run_started",
        phase="matchup_evaluation",
        generation=0,
        total_generations=settings.generations,
        phase_progress=0.0,
        deck_id=deck_1.id,
        opponent_deck_id=deck_2.id,
    )

    def checkpoint_completed(generation, outcome):
        row = {
            "generation": generation,
            "ai_wins": int(outcome["wins"]),
            "draws": int(outcome["draws"]),
            "random_wins": int(outcome["losses"]),
            "deck_1_wins": int(outcome["wins"]),
            "deck_2_wins": int(outcome["losses"]),
            "games": int(outcome["wins"] + outcome["draws"] + outcome["losses"]),
            "deck_1_fitness": float(outcome["scores"][0]),
            "deck_2_fitness": float(outcome["scores"][1]),
        }
        checkpoints.append(row)
        if summary_path:
            partial = build_summary(
                deck_1,
                deck_2,
                settings,
                checkpoints,
                time() - started_at,
            )
            Path(summary_path).write_text(
                json.dumps(partial, indent=2, sort_keys=True)
            )
        emit_training_event(
            "generation_completed",
            phase="matchup_evaluation",
            generation=generation,
            total_generations=settings.generations,
            phase_progress=generation / settings.generations,
            best_score=max(row["deck_1_fitness"], row["deck_2_fitness"]),
            wins=row["deck_1_wins"],
            draws=row["draws"],
            losses=row["deck_2_wins"],
        )

    scores = train_deck(
        deck_1,
        deck_2,
        settings=evaluator_settings(settings),
        checkpoint_callback=checkpoint_completed,
        controller_callback=lambda first, second: final_controllers.extend(
            (first, second)
        ),
    )
    elapsed = time() - started_at
    artifact_paths = []
    if len(final_controllers) == 2:
        output_dir = Path(
            os.environ.get("TRAINING_ARTIFACT_DIR", Path(__file__).resolve().parent)
        ) / "trained_ai"
        first = export_player_artifact(
            output_dir,
            final_controllers[0],
            deck_1,
            mission="matchup",
            role="deck-a",
            run_label=settings.run_label,
            generation=settings.generations,
            display_name=f"{deck_1.name} · matchup gen {settings.generations}",
        )
        second = export_player_artifact(
            output_dir,
            final_controllers[1],
            deck_2,
            mission="matchup",
            role="deck-b",
            run_label=settings.run_label,
            generation=settings.generations,
            display_name=f"{deck_2.name} · matchup gen {settings.generations}",
        )
        artifact_paths.extend((first.path, second.path))
    summary = build_summary(
        deck_1,
        deck_2,
        settings,
        checkpoints,
        elapsed,
        scores,
        artifact_paths,
    )
    if summary_path:
        Path(summary_path).write_text(json.dumps(summary, indent=2, sort_keys=True))
    emit_training_event(
        "run_completed",
        phase="completed",
        generation=settings.generations,
        total_generations=settings.generations,
        phase_progress=1.0,
        elapsed_seconds=elapsed,
        best_score=max(scores),
        evaluation_games=sum(row["games"] for row in checkpoints),
    )
    return summary


def parse_args():
    parser = argparse.ArgumentParser(
        description="Coevolve controllers for two fixed decks and compare win rates"
    )
    parser.add_argument("deck_id")
    parser.add_argument("opponent_deck_id")
    parser.add_argument("--generations", type=int, default=40)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--evaluation-games", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=104729)
    parser.add_argument("--run-label", default="matchup-evaluation")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    evaluate_matchup(
        DBUtil().load_deck(arguments.deck_id),
        DBUtil().load_deck(arguments.opponent_deck_id),
        MatchupTrainerSettings(
            generations=arguments.generations,
            workers=arguments.workers,
            evaluation_games=arguments.evaluation_games,
            seed=arguments.seed,
            run_label=arguments.run_label,
        ),
    )
