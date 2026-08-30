from __future__ import annotations

import copy
import pickle
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import neat

from choice_strategies.choice_strategy_ai_neat import PlayerChoiceStrategyNeat
from choice_strategies.choice_strategy_ai_random import ChoiceStrategyAIRandom
from choice_strategies.choice_strategy_human_pygame import PygameChoiceStrategy
from core.player import Player


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAYER_CONFIG_PATH = PROJECT_ROOT / "neat_ai" / "configs" / "neat_config_player.txt"
TRAINED_AI_DIR = PROJECT_ROOT / "neat_ai" / "trained_ai"


class ControllerKind(Enum):
    HUMAN = "Human"
    RANDOM_AI = "Random AI"
    TRAINED_AI = "Trained AI"


class PacedRandomStrategy(ChoiceStrategyAIRandom):
    """Random strategy used by pygame matches.

    The core training strategy intentionally runs as fast as possible. A pygame
    match needs a small delay so AI actions remain visible.
    """

    delay_seconds = 0.35

    def begin_turn_choices(self):
        import time

        time.sleep(self.delay_seconds)


class PacedNeatStrategy(PlayerChoiceStrategyNeat):
    delay_seconds = 0.35

    def begin_turn_choices(self):
        import time

        time.sleep(self.delay_seconds)
        super().begin_turn_choices()


@dataclass(frozen=True)
class ControllerSpec:
    kind: ControllerKind
    artifact_path: str | None = None

    @property
    def label(self) -> str:
        if self.kind != ControllerKind.TRAINED_AI or not self.artifact_path:
            return self.kind.value
        return f"Trained AI ({Path(self.artifact_path).stem})"


def discover_player_artifacts() -> list[Path]:
    roots = [TRAINED_AI_DIR, PROJECT_ROOT / ".ui_training"]
    artifacts = []
    for root in roots:
        if not root.exists():
            continue
        pattern = "best_*.pickle" if root == TRAINED_AI_DIR else "*/trained_ai/best_*.pickle"
        artifacts.extend(
            path
            for path in root.glob(pattern)
            if "builder" not in path.name
        )
    return sorted(
        artifacts,
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _player_config() -> neat.Config:
    return neat.Config(
        neat.DefaultGenome,
        neat.DefaultReproduction,
        neat.DefaultSpeciesSet,
        neat.DefaultStagnation,
        str(PLAYER_CONFIG_PATH),
    )


def create_player(
    player_id: int,
    deck,
    controller: ControllerSpec,
) -> Player:
    player_deck = copy.deepcopy(deck)
    if controller.kind == ControllerKind.HUMAN:
        return Player(player_id, player_deck, PygameChoiceStrategy)
    if controller.kind == ControllerKind.RANDOM_AI:
        return Player(player_id, player_deck, PacedRandomStrategy)
    if not controller.artifact_path:
        raise ValueError("A trained AI controller requires a model artifact")

    artifact = Path(controller.artifact_path)
    if not artifact.is_file():
        raise ValueError(f"Trained AI artifact does not exist: {artifact}")
    with artifact.open("rb") as artifact_file:
        genome = pickle.load(artifact_file)
    player = Player(player_id, player_deck, PacedNeatStrategy)
    try:
        player.net = neat.nn.FeedForwardNetwork.create(genome, _player_config())
    except Exception as error:
        raise ValueError(
            f"{artifact.name} is not compatible with the player AI config"
        ) from error
    return player


def validate_match_setup(
    deck_1,
    deck_2,
    controller_1: ControllerSpec,
    controller_2: ControllerSpec,
) -> None:
    if deck_1 is None or deck_2 is None:
        raise ValueError("Select a deck for both players")
    deck_1.validate()
    deck_2.validate()
    for controller in (controller_1, controller_2):
        if (
            controller.kind == ControllerKind.TRAINED_AI
            and not controller.artifact_path
        ):
            raise ValueError("Select a model for each trained AI player")
