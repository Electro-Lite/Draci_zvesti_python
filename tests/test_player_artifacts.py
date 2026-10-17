import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from neat_ai.player_artifacts import (
    composition_signature,
    discover_player_artifacts,
    export_player_artifact,
    safe_artifact_segment,
)
from py_game.match_setup import ControllerKind, ControllerSpec, validate_match_setup
from neat_ai.deck_builder_trainer import _remember_best_controller


def _deck(deck_id="deck-a", card_ids=None):
    values = card_ids or ["archer"] * 2 + [f"card-{index}" for index in range(8)]
    return SimpleNamespace(
        id=deck_id,
        name="Azure Guard",
        cards=[SimpleNamespace(id=card_id) for card_id in values],
        validate=lambda: True,
    )


class PlayerArtifactTests(unittest.TestCase):
    def test_artifact_segments_are_bounded_and_keep_a_stable_identity(self):
        value = "custom-deck-" + "x" * 200
        first = safe_artifact_segment(value, "deck")
        second = safe_artifact_segment(value, "deck")
        other = safe_artifact_segment(value + "y", "deck")

        self.assertLessEqual(len(first), 32)
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)

    def test_evolution_retains_the_best_observed_controller_for_each_deck(self):
        retained = {}
        _remember_best_controller(retained, 7, 2.0, "first")
        _remember_best_controller(retained, 7, 1.0, "worse")
        _remember_best_controller(retained, 7, 3.0, "best")
        self.assertEqual(retained[7], (3.0, "best"))

    def test_discovery_requires_the_exact_card_multiset_not_the_deck_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _deck()
            exported = export_player_artifact(
                root,
                {"genome": "test"},
                source,
                mission="matchup",
                role="deck-a",
                run_label="exact-study",
                generation=40,
            )

            reordered = _deck("renamed-id", list(reversed([card.id for card in source.cards])))
            changed = _deck(
                "deck-a",
                [card.id for card in source.cards[:-1]] + ["different-card"],
            )

            self.assertEqual(discover_player_artifacts([root], reordered), [exported])
            self.assertEqual(discover_player_artifacts([root], changed), [])
            self.assertEqual(
                exported.manifest.deck_signature,
                composition_signature(source),
            )

    def test_legacy_pickle_and_invalid_manifest_are_not_assumed_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "best_legacy.pickle").write_bytes(b"legacy")
            (root / "invalid.player.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "artifact_type": "player_controller",
                        "display_name": "Unproven model",
                        "deck_signature": "claimed-without-composition",
                        "card_ids": [],
                        "config_profile": "evaluator-v1",
                        "artifact_file": "best_legacy.pickle",
                    }
                )
            )

            self.assertEqual(discover_player_artifacts([root], _deck()), [])

    def test_match_validation_rejects_a_controller_for_another_composition(self):
        first = _deck()
        second = _deck(card_ids=["other"] * 10)
        controller = ControllerSpec(
            ControllerKind.TRAINED_AI,
            "model.pickle",
            composition_signature(first),
        )

        with self.assertRaisesRegex(ValueError, "exact deck composition"):
            validate_match_setup(
                second,
                first,
                controller,
                ControllerSpec(ControllerKind.HUMAN),
            )


if __name__ == "__main__":
    unittest.main()
