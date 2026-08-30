import copy
import os
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import neat

from cards.ability.ability_target import AbilityTarget
from choice_strategies.choice_strategy import PlayerChoiceStrategy
from choice_strategies.choice_strategy_ai_neat import (
    ACTION_OUTPUT_COUNT,
    PlayerChoiceStrategyNeat,
)
from core.board import Board
from core.game_info import GAME_INFO_INPUT_COUNT, GameInfo
from core.game_loop import GameResult, _shuffle_deck, run
from core.player import Player
from display_strategies.display_strategy_none import DisplayStrategyNone
from neat_ai.ai_training_logger import (
    AITrainingLogger,
    Genome,
    MatchDBT,
    Training,
)
from neat_ai.deck_builder_trainer import (
    DEFAULT_RUN_DESCRIPTION,
    DEFAULT_SEEDS,
    BuilderSettings,
    build_matchups,
)
from neat_ai.deck_evaluator import (
    EvaluatorSettings,
    _pc_match_row,
    fitness_from_result,
    holdout_game_seeds,
)
from utils.database_utils import DBUtil


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FixedNetwork:
    def __init__(self, outputs):
        self.outputs = outputs

    def activate(self, _):
        return self.outputs


class FirstLegalStrategy(PlayerChoiceStrategy):
    def get_choice_pos(self):
        return next(
            index
            for index, card in enumerate(self.info.game_board.positions)
            if card is None
        )

    def get_choice_card(self):
        return self.this_player.hand.cards.pop(0)

    def get_choice_use_ability(self):
        return False

    def get_choice_pass(self):
        return False

    def get_choice_ability_target(self):
        return 0


class TrainingPlanTests(unittest.TestCase):
    def test_neat_configs_parse(self):
        for config_path in (PROJECT_ROOT / "neat_ai" / "configs").glob(
                "neat_config_*.txt"
        ):
            neat.Config(
                neat.DefaultGenome,
                neat.DefaultReproduction,
                neat.DefaultSpeciesSet,
                neat.DefaultStagnation,
                str(config_path),
            )

    def test_matchups_are_regular_and_balanced(self):
        genomes = [(index, object()) for index in range(20)]
        matches = build_matchups(genomes, 12, random.Random(104729))
        self.assertEqual(len(matches), 120)

        opponents = {index: set() for index in range(20)}
        as_first = {index: 0 for index in range(20)}
        as_second = {index: 0 for index in range(20)}
        for (first, _), (second, _) in matches:
            opponents[first].add(second)
            opponents[second].add(first)
            as_first[first] += 1
            as_second[second] += 1

        self.assertTrue(all(len(values) == 12 for values in opponents.values()))
        self.assertTrue(all(count == 6 for count in as_first.values()))
        self.assertTrue(all(count == 6 for count in as_second.values()))

    def test_final_meta_evolution_defaults(self):
        settings = BuilderSettings(seed=DEFAULT_SEEDS[0])
        self.assertEqual(
            DEFAULT_SEEDS,
            (667615478, 2069633686, 915632071, 274633778),
        )
        self.assertEqual(settings.run_label, "final-meta-evolution")
        self.assertEqual(settings.description, DEFAULT_RUN_DESCRIPTION)
        self.assertEqual(settings.outer_generations, 10)
        self.assertEqual(settings.evaluator_generations, 50)
        self.assertEqual(
            settings.diagnostic_holdout_generations,
            (5, 20, 35),
        )
        self.assertIsNone(settings.crossplay_reference_generation)
        self.assertFalse(settings.log_training_games)
        self.assertEqual(settings.max_matches_per_genome, 12)
        self.assertEqual(settings.holdout_seed_pairs, 20)

    def test_game_info_has_normalized_expected_shape(self):
        deck1 = DBUtil().load_deck("Starter Blue_1")
        deck2 = DBUtil().load_deck("Starter Blue_1")
        player1 = Player(1, deck1, FirstLegalStrategy)
        player2 = Player(2, deck2, FirstLegalStrategy)
        board = Board()
        board.player_on_turn = player1
        board.round = 1
        info = GameInfo(board, player2)
        info.player_on_turn = player1

        values = info.get_game_info()
        self.assertEqual(len(values), GAME_INFO_INPUT_COUNT)
        self.assertTrue(all(-1.0 <= value <= 1.0 for value in values))

    def test_neat_strategy_masks_illegal_card_and_position(self):
        outputs = [0.0] * ACTION_OUTPUT_COUNT
        outputs[0] = 1.0  # play
        outputs[2] = 1.0  # first hand card
        outputs[14] = 100.0  # occupied position
        outputs[16] = 10.0  # legal position 2

        card = SimpleNamespace(ability=SimpleNamespace(is_active=False))
        player = SimpleNamespace(
            net=FixedNetwork(outputs),
            hand=SimpleNamespace(cards=[card]),
        )
        strategy = PlayerChoiceStrategyNeat(player)
        strategy.info = SimpleNamespace(
            get_game_info=lambda: [0.0] * GAME_INFO_INPUT_COUNT,
            game_board=SimpleNamespace(
                positions=[object(), None, None, None, None, None]
            ),
        )

        strategy.begin_turn_choices()
        self.assertFalse(strategy.get_choice_pass())
        self.assertIs(strategy.get_choice_card(), card)
        self.assertEqual(strategy.get_choice_pos(), 2)
        self.assertFalse(strategy.get_choice_use_ability())

    def test_neat_strategy_masks_ability_target_owner(self):
        outputs = [0.0] * ACTION_OUTPUT_COUNT
        outputs[2] = 1.0
        outputs[16] = 1.0
        outputs[21] = 1.0
        outputs[22] = 100.0  # Own card, illegal for an enemy-target ability.
        outputs[23] = 10.0

        player = SimpleNamespace()
        player.net = FixedNetwork(outputs)
        selected_card = SimpleNamespace(
            ability=SimpleNamespace(
                is_active=True,
                target_owner=AbilityTarget.ENEMY,
            )
        )
        player.hand = SimpleNamespace(cards=[selected_card])
        enemy = SimpleNamespace(owner=object())
        own = SimpleNamespace(owner=player)
        strategy = PlayerChoiceStrategyNeat(player)
        strategy.info = SimpleNamespace(
            get_game_info=lambda: [0.0] * GAME_INFO_INPUT_COUNT,
            game_board=SimpleNamespace(
                positions=[own, enemy, None, None, None, None]
            ),
        )

        strategy.begin_turn_choices()
        strategy.get_choice_card()
        self.assertEqual(strategy.get_choice_pos(), 2)
        self.assertTrue(strategy.get_choice_use_ability())
        self.assertEqual(strategy.get_choice_ability_target(), 1)

    def test_outcome_fitness_is_normalized(self):
        result = GameResult(2, 1, 1, 3, 1, 123)
        self.assertEqual(fitness_from_result(result, 1), 110.0)
        self.assertEqual(fitness_from_result(result, 2), -110.0)

    def test_seeded_games_repeat(self):
        original1 = DBUtil().load_deck("Starter Blue_1")
        original2 = DBUtil().load_deck("Killer Queen_1")

        def play_once():
            return run(
                Player(1, copy.deepcopy(original1), FirstLegalStrategy),
                Player(2, copy.deepcopy(original2), FirstLegalStrategy),
                DisplayStrategyNone,
                seed=987654,
                starting_player_id=1,
            )

        self.assertEqual(play_once(), play_once())

    def test_seeded_shuffle_uses_composition_not_deck_id_or_order(self):
        first = DBUtil().load_deck("Starter Blue_1")
        second = copy.deepcopy(first)
        second.id = "a-different-id"
        second.cards.reverse()

        _shuffle_deck(first, 12345, "deck")
        _shuffle_deck(second, 12345, "deck")

        self.assertEqual(
            [card.id for card in first.cards],
            [card.id for card in second.cards],
        )

    def test_holdout_seed_schedule_is_common_and_unique(self):
        settings = EvaluatorSettings(seed=104729)
        seeds = holdout_game_seeds(settings)
        self.assertEqual(len(seeds), 20)
        self.assertEqual(len(set(seeds)), 20)

    def test_diagnostic_holdouts_stop_before_final_generation(self):
        settings = EvaluatorSettings(generations=20)
        self.assertEqual(
            settings.holdout_checkpoint_generations(),
            (5,),
        )

    def test_training_schema_records_outcomes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            train_path = Path(temp_dir) / "train.db"
            old_path = os.environ.get("TRAIN_DB_PATH")
            os.environ["TRAIN_DB_PATH"] = str(train_path)
            try:
                logger = AITrainingLogger()
                columns = {
                    row[1]
                    for row in logger.conn_train.execute(
                        "PRAGMA table_info(pc_match)"
                    ).fetchall()
                }
                training_columns = {
                    row[1]
                    for row in logger.conn_train.execute(
                        "PRAGMA table_info(training)"
                    ).fetchall()
                }
                self.assertIn("description", training_columns)
                training = logger.save_training(
                    Training(start_date="test", description="schema test")
                )
                self.assertEqual(
                    logger.get_training(training.id).description,
                    "schema test",
                )
                logger.save_genome(Genome("g1", 1, "deck-1", training.id))
                logger.save_genome(Genome("g2", 1, "deck-2", training.id))
                logger.save_match_dbt(MatchDBT("match-1", "g1", "g2"))
                row = _pc_match_row(
                    "match-1",
                    20,
                    110.0,
                    -110.0,
                    GameResult(
                        player_1_score=2,
                        player_2_score=1,
                        winner_id=1,
                        rounds=3,
                        starting_player_id=1,
                        seed=12345,
                        player_1_card_plays={"Paladin_1": 2},
                        player_2_card_plays={"Zabijak_1": 1},
                        player_1_active_ability_uses={"Paladin_1": 1},
                        player_2_active_ability_uses={},
                    ),
                    phase="holdout_checkpoint",
                    seat_swap=False,
                    deck1_controller_generation=65,
                    deck2_controller_generation=50,
                )
                saved = logger.save_pc_match(row)
                loaded = logger.get_pc_match(saved.id)
            finally:
                if old_path is None:
                    os.environ.pop("TRAIN_DB_PATH", None)
                else:
                    os.environ["TRAIN_DB_PATH"] = old_path

        self.assertTrue(
            {
                "phase",
                "seed",
                "seat_swap",
                "p1_game_score",
                "p2_game_score",
                "winner_id",
                "rounds",
                "starting_player_id",
                "deck1_controller_gen",
                "deck2_controller_gen",
                "p1_card_plays",
                "p2_card_plays",
                "p1_active_ability_uses",
                "p2_active_ability_uses",
            }.issubset(columns)
        )
        self.assertEqual(loaded.phase, "holdout_checkpoint")
        self.assertEqual(loaded.deck1_controller_gen, 65)
        self.assertEqual(loaded.deck2_controller_gen, 50)
        self.assertEqual(loaded.p1_card_plays, '{"Paladin_1": 2}')
        self.assertEqual(loaded.p2_card_plays, '{"Zabijak_1": 1}')
        self.assertEqual(loaded.p1_active_ability_uses, '{"Paladin_1": 1}')
        self.assertEqual(loaded.p2_active_ability_uses, "{}")


if __name__ == "__main__":
    unittest.main()
