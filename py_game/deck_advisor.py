from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import neat

from cards.deck import Deck
from cards.power import Power


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILDER_CONFIG_PATH = (
    PROJECT_ROOT / "neat_ai" / "configs" / "neat_config_builder.txt"
)
TRAINED_AI_DIR = PROJECT_ROOT / "neat_ai" / "trained_ai"


@dataclass(frozen=True)
class CardAdvice:
    score: float
    continue_score: float
    rank: int
    candidate_count: int


@dataclass(frozen=True)
class AdvisorOption:
    path: Path | None
    label: str


def discover_advisors() -> list[AdvisorOption]:
    options = [AdvisorOption(None, "Advisor: Off")]
    artifacts = list(TRAINED_AI_DIR.glob("best_builder*.pickle"))
    ui_root = PROJECT_ROOT / ".ui_training"
    if ui_root.exists():
        artifacts.extend(
            ui_root.glob("*/trained_ai/best_builder*.pickle")
        )
    artifacts = sorted(
        artifacts,
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    options.extend(
        AdvisorOption(path, f"Advisor: {path.stem}") for path in artifacts
    )
    return options


class DeckAdvisor:
    """Scores candidate cards with the same network input as build_deck()."""

    def __init__(self, artifact_path: Path):
        self.artifact_path = Path(artifact_path)
        config = neat.Config(
            neat.DefaultGenome,
            neat.DefaultReproduction,
            neat.DefaultSpeciesSet,
            neat.DefaultStagnation,
            str(BUILDER_CONFIG_PATH),
        )
        with self.artifact_path.open("rb") as artifact_file:
            genome = pickle.load(artifact_file)
        self.net = neat.nn.FeedForwardNetwork.create(genome, config)

    def score_cards(self, deck_cards, candidates) -> dict[str, CardAdvice]:
        deck = Deck()
        deck.cards = list(deck_cards)
        deck_info = deck.get_neat_cards_ids()
        raw_scores = {}
        for card in candidates:
            # The trained builder's default card pool excludes legendary cards.
            # Reporting a score for them would present an out-of-distribution
            # network output as if it were learned evidence.
            if not card.power <= Power.NORMAL:
                continue
            outputs = self.net.activate(deck_info + card.get_neat_ids())
            raw_scores[str(card.id)] = (float(outputs[0]), float(outputs[1]))

        ordered = sorted(
            raw_scores.items(),
            key=lambda item: (-item[1][0], item[0]),
        )
        ranks = {card_id: index + 1 for index, (card_id, _) in enumerate(ordered)}
        count = len(ordered)
        return {
            card_id: CardAdvice(
                score=values[0],
                continue_score=values[1],
                rank=ranks[card_id],
                candidate_count=count,
            )
            for card_id, values in raw_scores.items()
        }
