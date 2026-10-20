from __future__ import annotations

import copy
import pickle
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import neat

from choice_strategies.choice_strategy_ai_neat import PlayerChoiceStrategyNeat
from choice_strategies.choice_strategy_ai_random import ChoiceStrategyAIRandom
from choice_strategies.choice_strategy_human_pygame import PygameChoiceStrategy
from core.player import Player
from neat_ai.player_artifacts import (
    PlayerArtifact,
    composition_signature,
    discover_player_artifacts as discover_manifest_artifacts,
    load_player_artifact,
)
from py_game.runtime_paths import data_path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAYER_CONFIG_PATH = PROJECT_ROOT / "neat_ai" / "configs" / "neat_config_player.txt"
EVALUATOR_CONFIG_PATH = PROJECT_ROOT / "neat_ai" / "configs" / "neat_config_evaluator.txt"
TRAINED_AI_DIR = data_path("trained_ai")
BUNDLED_AI_DIR = PROJECT_ROOT / "neat_ai" / "trained_ai"


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

    def __init__(self, player):
        super().__init__(player)
        self._exit = threading.Event()

    def begin_turn_choices(self):
        if self._exit.wait(self.delay_seconds):
            raise SystemExit

    def exit_thread(self):
        self._exit.set()


class PacedNeatStrategy(PlayerChoiceStrategyNeat):
    delay_seconds = 0.35

    def __init__(self, player):
        super().__init__(player)
        self._exit = threading.Event()

    def begin_turn_choices(self):
        if self._exit.wait(self.delay_seconds):
            raise SystemExit
        super().begin_turn_choices()

    def exit_thread(self):
        self._exit.set()


@dataclass(frozen=True)
class ControllerSpec:
    kind: ControllerKind
    artifact_path: str | None = None
    deck_signature: str | None = None

    @property
    def label(self) -> str:
        if self.kind != ControllerKind.TRAINED_AI or not self.artifact_path:
            return self.kind.value
        return f"Trained AI ({Path(self.artifact_path).stem})"


def discover_player_artifacts(deck) -> list[PlayerArtifact]:
    return discover_manifest_artifacts(
        (TRAINED_AI_DIR, BUNDLED_AI_DIR, data_path(".ui_training")),
        deck,
    )


def _player_config(path=PLAYER_CONFIG_PATH) -> neat.Config:
    return neat.Config(
        neat.DefaultGenome,
        neat.DefaultReproduction,
        neat.DefaultSpeciesSet,
        neat.DefaultStagnation,
        str(path),
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

    expected_signature = composition_signature(deck)
    if controller.deck_signature != expected_signature:
        raise ValueError(
            "The selected trained AI was not trained for this exact deck composition"
        )

    artifact = Path(controller.artifact_path)
    if not artifact.is_file():
        raise ValueError(f"Trained AI artifact does not exist: {artifact}")
    with artifact.open("rb") as artifact_file:
        genome = pickle.load(artifact_file)
    manifest = load_player_artifact(artifact.with_suffix(".player.json"))
    if manifest is None or manifest.manifest.deck_signature != expected_signature:
        raise ValueError(
            "The trained AI artifact has no valid matching deck evidence"
        )
    player = Player(player_id, player_deck, PacedNeatStrategy)
    try:
        player.net = neat.nn.FeedForwardNetwork.create(
            genome,
            _player_config(EVALUATOR_CONFIG_PATH),
        )
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
    for deck, controller in ((deck_1, controller_1), (deck_2, controller_2)):
        if (
            controller.kind == ControllerKind.TRAINED_AI
            and controller.deck_signature != composition_signature(deck)
        ):
            raise ValueError(
                "The selected trained AI does not match this exact deck composition"
            )
