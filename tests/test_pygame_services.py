import unittest
from types import SimpleNamespace

from cards.ability.ability_target import AbilityTarget
from cards.power import Power
from choice_strategies.choice_strategy_human_pygame import (
    ChoiceType,
    PygameChoiceStrategy,
)
from py_game.deck_advisor import DeckAdvisor
from py_game.match_setup import (
    ControllerKind,
    ControllerSpec,
    PacedRandomStrategy,
    create_player,
    validate_match_setup,
)
from py_game.training_service import (
    TrainingKind,
    TrainingRequest,
    build_command,
)
from utils.database_utils import DBUtil


class PygameServiceTests(unittest.TestCase):
    def test_deck_advisor_scores_the_builder_card_pool(self):
        class FixedAdvisorNetwork:
            def activate(self, values):
                self.last_input_length = len(values)
                return [float(values[-7]), 0.75]

        advisor = DeckAdvisor.__new__(DeckAdvisor)
        advisor.net = FixedAdvisorNetwork()
        cards = DBUtil().get_all_player_cards()
        advice = advisor.score_cards([], cards)

        self.assertEqual(advisor.net.last_input_length, 91)
        eligible_count = sum(card.power <= Power.NORMAL for card in cards)
        self.assertEqual(len(advice), eligible_count)
        self.assertEqual(
            sorted(value.rank for value in advice.values()),
            list(range(1, eligible_count + 1)),
        )

    def test_match_factory_builds_human_and_random_players(self):
        deck = DBUtil().load_deck("Starter Blue_1")
        human = create_player(
            1,
            deck,
            ControllerSpec(ControllerKind.HUMAN),
        )
        random_ai = create_player(
            2,
            deck,
            ControllerSpec(ControllerKind.RANDOM_AI),
        )

        self.assertIsInstance(human.choice_strategy, PygameChoiceStrategy)
        self.assertIsInstance(random_ai.choice_strategy, PacedRandomStrategy)
        self.assertIsNot(human.deck, deck)
        self.assertIsNot(random_ai.deck, deck)

    def test_match_validation_requires_two_valid_decks(self):
        deck = DBUtil().load_deck("Starter Blue_1")
        with self.assertRaisesRegex(ValueError, "both players"):
            validate_match_setup(
                deck,
                None,
                ControllerSpec(ControllerKind.HUMAN),
                ControllerSpec(ControllerKind.RANDOM_AI),
            )

    def test_human_strategy_masks_enemy_targets(self):
        player = SimpleNamespace()
        player.hand = SimpleNamespace(cards=[])
        strategy = PygameChoiceStrategy(player)
        player.choice_strategy = strategy
        enemy_owner = object()
        strategy.selected_card = SimpleNamespace(
            ability=SimpleNamespace(
                is_active=True,
                target_owner=AbilityTarget.ENEMY,
            )
        )
        strategy.selected_position = 2
        strategy.info = SimpleNamespace(
            game_board=SimpleNamespace(
                positions=[
                    SimpleNamespace(owner=player),
                    SimpleNamespace(owner=enemy_owner),
                    None,
                    None,
                    None,
                    None,
                ]
            )
        )

        self.assertEqual(strategy.legal_targets(), [1])
        strategy.waiting_for = ChoiceType.PASS
        self.assertTrue(strategy.set_choice(ChoiceType.PASS, False))
        self.assertFalse(strategy.set_choice(ChoiceType.CARD, object()))

    def test_player_training_command_contains_ui_configuration(self):
        request = TrainingRequest(
            kind=TrainingKind.PLAYER_DECK,
            deck_id="Starter Blue_1",
            evaluator_generations=35,
            workers=8,
            evaluation_games=20,
            run_label="professor-demo",
        )
        command = build_command(request)

        self.assertIn("neat_ai.player_trainer", command)
        self.assertEqual(command[command.index("--generations") + 1], "35")
        self.assertEqual(command[command.index("--workers") + 1], "8")
        self.assertEqual(command[command.index("--evaluation-games") + 1], "20")

    def test_builder_training_command_uses_selected_final_configuration(self):
        request = TrainingRequest(
            kind=TrainingKind.DECK_BUILDER,
            evaluator_generations=50,
            seeds=(400009, 450001),
            matches_per_genome=12,
        )
        command = build_command(request)
        seeds_at = command.index("--seeds")
        self.assertEqual(command[seeds_at + 1 : seeds_at + 3], ["400009", "450001"])
        self.assertEqual(
            command[command.index("--evaluator-generations") + 1],
            "50",
        )


if __name__ == "__main__":
    unittest.main()
