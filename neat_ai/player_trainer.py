"""CLI entry point for persistent counter-deck training.

The historical two-fixed-deck experiment now lives in
``neat_ai.matchup_trainer``. Imports are re-exported here where useful so old
analysis code can still obtain the shared checkpoint schedule.
"""

from neat_ai.counter_deck_trainer import (
    CounterDeckTrainerSettings,
    build_summary,
    controller_generation_targets,
    parse_args,
    train_counter_decks,
)
from neat_ai.training_plan import evaluation_checkpoints
from utils.database_utils import DBUtil


PlayerTrainerSettings = CounterDeckTrainerSettings
train_deck = train_counter_decks


if __name__ == "__main__":
    arguments = parse_args()
    train_counter_decks(
        DBUtil().load_deck(arguments.deck_id),
        CounterDeckTrainerSettings(
            counter_generations=arguments.counter_generations,
            controller_generations=arguments.controller_generations,
            workers=arguments.workers,
            evaluation_games=arguments.evaluation_games,
            seed=arguments.seed,
            run_label=arguments.run_label,
        ),
    )


__all__ = (
    "CounterDeckTrainerSettings",
    "PlayerTrainerSettings",
    "build_summary",
    "controller_generation_targets",
    "evaluation_checkpoints",
    "train_counter_decks",
    "train_deck",
)
