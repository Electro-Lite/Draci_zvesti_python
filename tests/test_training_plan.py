import copy
import math
import os
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, Mock, patch

import neat


class ActiveAbilityStub(SimpleNamespace):
    def activate(self, card, board, args=None):
        pass

from cards.ability.ability_target import AbilityTarget
from cards.card import Card
from cards.card_type import CardType
from cards.deck import Deck
from cards.mana import ManaColor
from cards.power import Power
from config import Config
from choice_strategies.choice_strategy import PlayerChoiceStrategy
from choice_strategies.choice_strategy_ai_neat import (
    ACTION_OUTPUT_COUNT,
    PlayerChoiceStrategyNeat,
)
from core.board import Board
from core.game_info import (
    BOARD_POSITION_COUNT,
    CARD_FEATURE_COUNT,
    GAME_INFO_INPUT_COUNT,
    HAND_SLOT_COUNT,
    SCALAR_FEATURE_COUNT,
    ZONE_SLOT_COUNT,
    GameInfo,
)
from core.game_loop import GameResult, _shuffle_deck, battle_dragon, run
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
    checkpoint_completed_generation,
    train_deck_builder,
)
from neat_ai.deck_builder import build_deck
from neat_ai.deck_evaluator import (
    EvaluatorSettings,
    _pc_match_row,
    _play_training_game,
    deck_evaluation_seed_key,
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


class NeverPassStrategy(PlayerChoiceStrategy):
    pass_checks = 0

    def get_choice_pass(self):
        type(self).pass_checks += 1
        return False


class TrainingPlanTests(unittest.TestCase):
    def test_ai_deck_builder_includes_legendary_cards_but_keeps_copy_limit(self):
        normal = Card(
            id="normal",
            name="Normal",
            power=Power.NORMAL,
            color=SimpleNamespace(value=0),
            ability=SimpleNamespace(id=SimpleNamespace(value=0)),
            type=CardType.PLAYER,
        )
        legendary = Card(
            id="legendary",
            name="Legendary",
            power=Power.LEGENDARY,
            color=SimpleNamespace(value=0),
            ability=SimpleNamespace(id=SimpleNamespace(value=0)),
            type=CardType.PLAYER,
        )
        network = SimpleNamespace(
            activate=lambda values: [float(values[-6]), 1.0]
        )

        with patch(
            "neat_ai.deck_builder.DBUtil.get_all_cards",
            return_value=[normal, legendary],
        ):
            deck = build_deck(network, max_power=Power.LEGENDARY)

        self.assertIn(legendary, deck.cards)
        self.assertEqual(deck.cards.count(legendary), 1)

    def test_ai_deck_builder_excludes_banned_cards(self):
        normal = Card(
            id="normal",
            name="Normal",
            power=Power.NORMAL,
            color=SimpleNamespace(value=0),
            ability=SimpleNamespace(id=SimpleNamespace(value=0)),
            type=CardType.PLAYER,
        )
        banned = Card(
            id="banned",
            name="Banned",
            power=Power.NORMAL,
            color=SimpleNamespace(value=0),
            ability=SimpleNamespace(id=SimpleNamespace(value=0)),
            type=CardType.PLAYER,
        )
        network = SimpleNamespace(activate=lambda values: [1.0, 1.0])

        with patch(
            "neat_ai.deck_builder.DBUtil.get_all_cards",
            return_value=[banned, normal],
        ):
            deck = build_deck(
                network,
                max_power=Power.LEGENDARY,
                banned_card_ids=("banned",),
            )

        self.assertNotIn(banned, deck.cards)
        self.assertTrue(deck.cards)

    def test_deck_evolution_checkpoint_names_map_to_completed_outer_generations(self):
        self.assertEqual(
            checkpoint_completed_generation(
                "checkpoints/training_17_seed_104729_gen-3"
            ),
            4,
        )
        with self.assertRaisesRegex(ValueError, "generation"):
            checkpoint_completed_generation("checkpoint-without-counter")

    def test_deck_evolution_resume_reuses_run_and_executes_only_remaining_generations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            builder_config = root / "builder.txt"
            evaluator_config = root / "evaluator.txt"
            builder_config.write_text("builder")
            evaluator_config.write_text("evaluator")
            checkpoint = root / "training_17_seed_104729_gen-3"
            checkpoint.write_bytes(b"checkpoint")
            population = SimpleNamespace(
                generation=3,
                species=SimpleNamespace(species={}),
                add_reporter=Mock(),
                run=Mock(return_value=SimpleNamespace(fitness=12.5)),
            )
            training = Training(
                id=17,
                start_date="earlier",
                metadata='{"observed_populations":[]}',
            )
            logger = SimpleNamespace(
                get_training=Mock(return_value=training),
                save_training=Mock(return_value=training),
            )
            fake_checkpointer = SimpleNamespace(
                restore_checkpoint=Mock(return_value=population),
            )

            with (
                patch.dict(
                    os.environ,
                    {"TRAINING_ARTIFACT_DIR": str(root)},
                    clear=False,
                ),
                patch(
                    "neat_ai.deck_builder_trainer.shutil.disk_usage",
                    return_value=SimpleNamespace(free=2 << 30),
                ),
                patch(
                    "neat_ai.deck_builder_trainer.config_path",
                    side_effect=(builder_config, evaluator_config),
                ),
                patch("neat_ai.deck_builder_trainer.neat.Config"),
                patch(
                    "neat_ai.deck_builder_trainer.neat.Checkpointer",
                    return_value=fake_checkpointer,
                ) as checkpointer_type,
                patch(
                    "neat_ai.deck_builder_trainer.AITrainingLogger",
                    return_value=logger,
                ),
                patch("neat_ai.deck_builder_trainer.emit_training_event"),
                patch("builtins.print"),
            ):
                checkpointer_type.restore_checkpoint = fake_checkpointer.restore_checkpoint
                train_deck_builder(
                    BuilderSettings(
                        seed=104729,
                        outer_generations=10,
                        checkpoint_path=str(checkpoint),
                        resume_training_id=17,
                    )
                )

        self.assertEqual(population.generation, 4)
        population.run.assert_called_once_with(ANY, 6)
        logger.get_training.assert_called_once_with(17)
        self.assertIsNotNone(training.end_date)

    def test_round_turn_limit_forces_pass_and_resets_each_round(self):
        first_deck = Deck()
        second_deck = Deck()
        first_deck.cards = [SimpleNamespace(name="Loop one")]
        second_deck.cards = [SimpleNamespace(name="Loop two")]
        first = Player(1, first_deck, NeverPassStrategy)
        second = Player(2, second_deck, NeverPassStrategy)
        board = Board(dragons=[])
        NeverPassStrategy.pass_checks = 0

        with (
            patch("core.game_loop.play_card"),
            patch("core.game_loop.battle_dragon", return_value=None),
            patch.object(Config, "max_rounds", 1),
            patch.object(Config, "turn_count_limit", 50),
        ):
            run(
                first,
                second,
                DisplayStrategyNone,
                board=board,
                starting_player_id=1,
            )

        self.assertEqual(NeverPassStrategy.pass_checks, 100)
        self.assertEqual(board.round, 2)
        self.assertTrue(first.passed)
        self.assertTrue(second.passed)

    def test_zero_damage_battle_resolves_as_dragon_surviving(self):
        owner = object()
        card = SimpleNamespace(hp=2, dmg=0, owner=owner)
        dragon = SimpleNamespace(
            hp=3,
            dmg=0,
            slain_by=None,
            ability=SimpleNamespace(is_active=False),
            restore=Mock(),
        )

        class BattleBoard:
            def __init__(self):
                self.game_state = None
                self.positions = [card, None, None, None, None, None]
                self.dragons = [dragon]
                self.dragon = None

            def recalculate(self, *_args, **_kwargs):
                return None

            def remove_card(self, removed):
                self.positions[self.positions.index(removed)] = None

        result_events = []
        display = SimpleNamespace(
            dragon=None,
            display_dragon=lambda: None,
            display_board=lambda: None,
            display_dragon_vs_card=lambda: None,
            display_battle_result=lambda: result_events.append(
                dict(board.battle_event)
            ),
        )
        board = BattleBoard()

        self.assertIsNone(battle_dragon(board, display))
        self.assertIs(board.positions[0], card)
        self.assertEqual(board.dragons, [dragon])
        self.assertEqual(result_events[0]["phase"], "dragon_survived")
        self.assertIsNone(result_events[0]["point_for"])
        dragon.restore.assert_called_once_with()

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

    def test_game_info_has_expected_shape_and_finite_values(self):
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
        self.assertTrue(all(math.isfinite(value) for value in values))

    def test_game_info_includes_real_and_active_mana_without_card_power(self):
        deck1 = DBUtil().load_deck("Starter Blue_1")
        deck2 = DBUtil().load_deck("Starter Blue_1")
        player1 = Player(1, deck1, FirstLegalStrategy)
        player2 = Player(2, deck2, FirstLegalStrategy)
        board = Board()
        board.player_on_turn = player1
        board.round = 1
        board.mana_pool[0].color = ManaColor.RED
        board.active_mana_colors = lambda: {ManaColor.RED, ManaColor.BLUE}

        info = GameInfo(board, player2)
        values = info.get_game_info()

        self.assertEqual(values[:4], [1 / 3, 1.0, 0.0, 1.0])
        card = deck1.cards[0]
        encoded = info._get_card_neat_ids(card, player1)
        original_power = card.power
        card.power = Power.LEGENDARY
        self.assertEqual(info._get_card_neat_ids(card, player1), encoded)
        card.power = original_power

    def test_game_info_contains_known_deck_and_graveyard_compositions(self):
        deck1 = DBUtil().load_deck("Starter Blue_1")
        deck2 = DBUtil().load_deck("Starter Blue_1")
        player1 = Player(1, deck1, FirstLegalStrategy)
        player2 = Player(2, deck2, FirstLegalStrategy)
        player1.graveyard.append(player1.deck.cards.pop())
        player2.graveyard.append(player2.deck.cards.pop())
        board = Board()
        board.player_on_turn = player1
        board.round = 1

        values = GameInfo(board, player2).get_game_info()
        own_deck = SCALAR_FEATURE_COUNT + CARD_FEATURE_COUNT * (
            BOARD_POSITION_COUNT + HAND_SLOT_COUNT
        )
        own_graveyard = own_deck + CARD_FEATURE_COUNT * ZONE_SLOT_COUNT
        opponent_graveyard = own_graveyard + CARD_FEATURE_COUNT * ZONE_SLOT_COUNT

        self.assertEqual(values[own_deck + CARD_FEATURE_COUNT - 1], 1.0)
        self.assertEqual(values[own_graveyard + CARD_FEATURE_COUNT - 1], 1.0)
        self.assertEqual(values[opponent_graveyard + CARD_FEATURE_COUNT - 1], -1.0)

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
            ability=ActiveAbilityStub(
                target_owner=AbilityTarget.ENEMY,
                requires_target=True,
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

    def test_neat_strategy_targets_automatic_ability_without_use_prompt(self):
        outputs = [0.0] * ACTION_OUTPUT_COUNT
        outputs[2] = 1.0
        outputs[16] = 1.0
        outputs[23] = 10.0

        player = SimpleNamespace()
        player.net = FixedNetwork(outputs)
        selected_card = SimpleNamespace(
            ability=ActiveAbilityStub(
                auto_activate_on_play=True,
                requires_target=True,
                legal_target_positions=lambda card, board: [1],
            )
        )
        player.hand = SimpleNamespace(cards=[selected_card])
        strategy = PlayerChoiceStrategyNeat(player)
        strategy.info = SimpleNamespace(
            get_game_info=lambda: [0.0] * GAME_INFO_INPUT_COUNT,
            game_board=SimpleNamespace(
                positions=[None, SimpleNamespace(owner=player), None, None, None, None]
            ),
        )

        strategy.begin_turn_choices()
        strategy.get_choice_card()
        self.assertEqual(strategy.get_choice_pos(), 2)
        self.assertEqual(strategy.get_choice_ability_target(), 1)

    def test_outcome_fitness_is_normalized(self):
        result = GameResult(2, 1, 1, 3, 1, 123)
        self.assertEqual(fitness_from_result(result, 1), 110.0)
        self.assertEqual(fitness_from_result(result, 2), -110.0)

    def test_training_seat_swap_preserves_original_deck_perspectives(self):
        deck_a = SimpleNamespace(id="deck-a", cards=[])
        deck_b = SimpleNamespace(id="deck-b", cards=[])
        result = GameResult(3, 1, 1, 4, 1, 987)

        with (
            patch("neat_ai.deck_evaluator.neat.nn.FeedForwardNetwork.create")
            as create_network,
            patch("neat_ai.deck_evaluator.run_game", return_value=result) as play,
        ):
            outcome = _play_training_game(
                (11, "genome-a"),
                (22, "genome-b"),
                "config",
                deck_a,
                deck_b,
                seed=987,
                starting_player_id=1,
                seat_swap=True,
            )

        player_1, player_2 = play.call_args.args[:2]
        self.assertEqual((player_1.deck.id, player_2.deck.id), ("deck-b", "deck-a"))
        self.assertEqual(create_network.call_args_list[0].args[0], "genome-b")
        self.assertEqual(create_network.call_args_list[1].args[0], "genome-a")
        self.assertEqual(outcome[:4], (11, -120.0, 22, 120.0))
        self.assertTrue(outcome[-1])

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

    def test_evaluation_seed_key_uses_composition_not_deck_identity_or_order(self):
        first = DBUtil().load_deck("Starter Blue_1")
        same_composition = copy.deepcopy(first)
        same_composition.id = "different-genome-deck-id"
        same_composition.cards.reverse()
        opponent = DBUtil().load_deck("Killer Queen_1")

        key = deck_evaluation_seed_key(first, opponent)
        self.assertEqual(
            key,
            deck_evaluation_seed_key(same_composition, opponent),
        )
        self.assertEqual(key, deck_evaluation_seed_key(opponent, first))

    def test_evaluation_seed_key_changes_with_composition(self):
        first = DBUtil().load_deck("Starter Blue_1")
        opponent = DBUtil().load_deck("Killer Queen_1")
        changed = copy.deepcopy(first)
        changed.cards[-1] = opponent.cards[0]

        self.assertNotEqual(
            deck_evaluation_seed_key(first, opponent),
            deck_evaluation_seed_key(changed, opponent),
        )

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
