import unittest
import datetime as dt
import json
import queue
import threading
import time
import tempfile
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, Mock, patch

import pygame as pg

from cards.ability.ability_target import AbilityTarget
from cards.power import Power
from choice_strategies.choice_strategy_human_pygame import (
    PASS_SELECTION,
    ChoiceType,
    PygameChoiceStrategy,
)
from choice_strategies.choice_strategy_ai_random import ChoiceStrategyAIRandom
from py_game.deck_advisor import DeckAdvisor
from py_game.game import Game
from py_game.menu.training_menu import TrainingMenu
from py_game.theme import PALETTE
from py_game.match_setup import (
    ControllerKind,
    ControllerSpec,
    PacedRandomStrategy,
    create_player,
    validate_match_setup,
)
from py_game.training_service import (
    TrainingJob,
    TrainingInsights,
    TrainingKind,
    TrainingRequest,
    TrainingRunSummary,
    TrainingService,
    build_command,
    select_diverse_matchups,
    shared_card_count,
)
from py_game.ui.training_setup import (
    MATCHUP_PRESETS,
    PLAYER_PRESETS,
    training_workload,
    wilson_interval,
)
from py_game.ui.training_cockpit import TrainingCockpitState
from py_game.ui.training_runs import (
    RunFilters,
    combined_runs,
    paginate_runs,
    query_runs,
)
from neat_ai.player_trainer import evaluation_checkpoints
from utils.database_utils import DBUtil


class PygameServiceTests(unittest.TestCase):
    def test_training_about_guide_covers_every_configurable_setting(self):
        headings = {
            heading
            for _title, _subtitle, entries in TrainingMenu.ABOUT_PAGES
            for heading, _description in entries
        }
        self.assertTrue(
            {
                "Training type",
                "Run label",
                "Deck under test",
                "Deck A and Deck B",
                "Counter generations",
                "Controller generations",
                "Workers",
                "Games per counter",
                "Games per checkpoint",
                "Seeds",
                "Outer generations",
                "Inner generations",
                "Rival decks per candidate",
                "Evaluator workers",
                "Holdout seed pairs",
            }.issubset(headings)
        )
        self.assertIn("Balanced counter lab", headings)
        self.assertIn("Arena sections", headings)

    def test_training_presets_and_workload_expose_real_checkpoint_cost(self):
        balanced = PLAYER_PRESETS[1]
        request = TrainingRequest(
            kind=TrainingKind.PLAYER_DECK,
            deck_id="Killer Queen_1",
            opponent_deck_id="Iron Choir_1",
            evaluator_generations=balanced.generations,
            outer_generations=balanced.outer_generations,
            workers=balanced.workers,
            evaluation_games=balanced.evaluation_games,
        )

        workload = training_workload(request)

        self.assertEqual(balanced.label, "Balanced")
        self.assertIn("13,000 simulated games", workload.headline)
        self.assertTrue(any("persistent controller generations" in line for line in workload.details))

        matchup = MATCHUP_PRESETS[1]
        matchup_workload = training_workload(
            TrainingRequest(
                kind=TrainingKind.MATCHUP_EVALUATION,
                deck_id="Killer Queen_1",
                opponent_deck_id="Iron Choir_1",
                evaluator_generations=matchup.generations,
                workers=matchup.workers,
                evaluation_games=matchup.evaluation_games,
            )
        )
        self.assertIn("9,400 simulated games", matchup_workload.headline)

    @staticmethod
    def _cockpit_menu(service):
        menu = TrainingMenu.__new__(TrainingMenu)
        menu.cockpit = TrainingCockpitState(("Blue", "Queen"))
        menu.service = service
        menu.game = SimpleNamespace(
            palette=PALETTE,
            events=[],
            BACK_KEY=False,
            START_KEY=False,
            mouse_clicked=False,
        )
        menu._launch_thread = None
        menu._launch_results = queue.Queue()
        menu.setup_review_open = False
        menu.setup_review_request = None
        menu.setup_review_selected = 0
        menu.setup_starting = False
        menu.setup_edit_original_preset = None
        menu.message = ""
        menu.message_color = PALETTE.text
        return menu

    def test_cockpit_requires_review_before_service_start(self):
        service = SimpleNamespace(start=Mock())
        menu = self._cockpit_menu(service)

        menu._launch()

        self.assertTrue(menu.setup_review_open)
        self.assertEqual(menu.setup_review_request.deck_id, "Blue")
        service.start.assert_not_called()

    def test_cockpit_starts_exact_reviewed_request_only_once(self):
        entered = threading.Event()
        release = threading.Event()

        def start(request):
            entered.set()
            release.wait(1)
            return SimpleNamespace(job_id="one-job")

        service = SimpleNamespace(start=Mock(side_effect=start))
        menu = self._cockpit_menu(service)
        request = menu.cockpit.validate().request

        menu._start_training(request)
        self.assertTrue(entered.wait(0.5))
        menu._start_training(request)
        release.set()
        menu._launch_thread.join(1)

        service.start.assert_called_once_with(request)
        self.assertIn("already", menu.message)

    def test_cockpit_launch_failure_keeps_draft(self):
        menu = self._cockpit_menu(SimpleNamespace(start=Mock()))
        menu.cockpit.set_value("run_label", "keep-this-draft")
        menu.setup_review_open = True
        menu.setup_starting = True
        menu._launch_results.put(("error", "trainer unavailable"))

        menu._consume_launch_result()

        self.assertEqual(menu.cockpit.value("run_label"), "keep-this-draft")
        self.assertFalse(menu.setup_review_open)
        self.assertEqual(menu.message, "trainer unavailable")

    def test_cockpit_editor_keeps_invalid_text_and_escape_restores_value(self):
        menu = self._cockpit_menu(SimpleNamespace(start=Mock()))
        menu.setup_edit_key = "workers"
        menu.setup_edit_original = "8"
        menu.cockpit.set_value("workers", "invalid")
        menu.game.events = [
            SimpleNamespace(type=pg.KEYDOWN, key=pg.K_RETURN, unicode="", mod=0)
        ]

        menu._handle_setup_editor()

        self.assertEqual(menu.setup_edit_key, "workers")
        self.assertEqual(menu.cockpit.value("workers"), "invalid")
        self.assertIn("integer", menu.message)

        menu.game.events = [
            SimpleNamespace(type=pg.KEYDOWN, key=pg.K_ESCAPE, unicode="", mod=0)
        ]
        menu._handle_setup_editor()

        self.assertIsNone(menu.setup_edit_key)
        self.assertEqual(menu.cockpit.value("workers"), "8")

    def test_wilson_interval_is_bounded_and_reflects_sample_size(self):
        small = wilson_interval(6, 10)
        large = wilson_interval(60, 100)

        self.assertLessEqual(0.0, small[0])
        self.assertLessEqual(small[1], 1.0)
        self.assertLess(large[1] - large[0], small[1] - small[0])

    @staticmethod
    def _run_summary(
        index,
        *,
        status="completed",
        kind=TrainingKind.DECK_BUILDER,
        generation=40,
    ):
        return TrainingRunSummary(
            run_id=f"DB {index}",
            title=f"Run {index:02d}",
            status=status,
            started=f"2026-09-{index:02d}T10:00:00",
            detail="test run",
            generation=generation,
            run_kind=kind.value,
        )

    def test_run_library_deduplicates_linked_ui_and_database_records(self):
        job = TrainingJob(
            job_id="ui-run",
            request={"run_label": "Run 12", "kind": TrainingKind.DECK_BUILDER.value},
            command=["trainer"],
            created_at="2026-09-12T10:00:00",
            status="completed",
            pid=None,
            log_path="training.log",
            progress_path="progress.log",
            summary_path="summary.json",
        )
        service = SimpleNamespace(job_database_run_id=Mock(return_value=12))

        runs = combined_runs(
            service,
            [job],
            [self._run_summary(12), self._run_summary(11)],
        )

        self.assertEqual(runs, [job, self._run_summary(11)])

    def test_run_library_search_filters_sorting_and_ten_item_pages(self):
        runs = [self._run_summary(index) for index in range(1, 24)]
        runs[4] = self._run_summary(
            5,
            status="failed",
            kind=TrainingKind.PLAYER_DECK,
        )

        attention = query_runs(
            runs,
            search="run 05",
            sort_field="Name",
            descending=False,
            filters=RunFilters("Needs attention", "Counter-deck training"),
        )
        second_page, page, page_count = paginate_runs(runs, 1)

        self.assertEqual(attention, [runs[4]])
        self.assertEqual(len(second_page), 10)
        self.assertEqual((page, page_count), (1, 3))

    def test_run_library_searches_names_only_and_supports_extended_filters(self):
        runs = [self._run_summary(index) for index in range(1, 24)]
        filters = RunFilters(
            mission="General deck evolution",
            origin="Database history",
            started="Last 7 days",
            generations="25+ generations",
        )

        matching = query_runs(
            runs,
            search="run 23",
            filters=filters,
            now=dt.datetime(2026, 9, 25, 10, 0, 0),
        )
        id_search = query_runs(runs, search="DB 23")

        self.assertEqual(matching, [runs[22]])
        self.assertEqual(id_search, [])

    def test_training_runs_back_returns_to_configuration(self):
        menu = TrainingMenu.__new__(TrainingMenu)
        menu.view = "runs"
        menu.selected = 0

        menu._activate_run("back")

        self.assertEqual(menu.view, "setup")
        self.assertEqual(menu.selected, 1)

    def test_human_turn_opens_as_card_or_pass_and_preselects_the_card(self):
        card = object()
        player = SimpleNamespace(hand=SimpleNamespace(cards=[card]))
        strategy = PygameChoiceStrategy(player)
        result = []

        worker = threading.Thread(target=lambda: result.append(strategy.get_choice_pass()))
        worker.start()
        deadline = time.monotonic() + 0.5
        while strategy.waiting_for != ChoiceType.PLAY_OR_PASS and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(strategy.waiting_for, ChoiceType.PLAY_OR_PASS)
        self.assertTrue(strategy.set_choice(ChoiceType.PLAY_OR_PASS, card))
        worker.join(timeout=0.5)

        self.assertEqual(result, [False])
        self.assertIs(strategy.get_choice_card(), card)
        self.assertEqual(player.hand.cards, [])

    def test_human_pass_is_the_only_explicit_non_play_choice(self):
        player = SimpleNamespace(hand=SimpleNamespace(cards=[object()]))
        strategy = PygameChoiceStrategy(player)
        result = []

        worker = threading.Thread(target=lambda: result.append(strategy.get_choice_pass()))
        worker.start()
        deadline = time.monotonic() + 0.5
        while strategy.waiting_for != ChoiceType.PLAY_OR_PASS and time.monotonic() < deadline:
            time.sleep(0.005)
        strategy.set_choice(ChoiceType.PLAY_OR_PASS, PASS_SELECTION)
        worker.join(timeout=0.5)

        self.assertEqual(result, [True])

    @staticmethod
    def _keyboard_game(player, **pressed):
        game = Game.__new__(Game)
        game.board = SimpleNamespace(player_on_turn=player, positions=[None] * 6)
        game.selected_card = None
        game.selected_position = None
        game.binary_choice = False
        game.previous_choice_type = None
        for name in (
            "LEFT_KEY",
            "RIGHT_KEY",
            "START_KEY",
            "PASS_KEY",
            "USE_ABILITY_KEY",
            "SKIP_ABILITY_KEY",
        ):
            setattr(game, name, bool(pressed.get(name, False)))
        return game

    def test_p_key_passes_directly_from_card_selection(self):
        card = object()
        player = SimpleNamespace(hand=SimpleNamespace(cards=[card]))
        strategy = PygameChoiceStrategy(player)
        strategy.waiting_for = ChoiceType.PLAY_OR_PASS
        player.choice_strategy = strategy
        game = self._keyboard_game(player, PASS_KEY=True)

        game.handle_choice()

        self.assertIs(strategy.choice, PASS_SELECTION)

    def test_ability_prompt_defaults_enter_to_use_with_direct_skip_key(self):
        player = SimpleNamespace(hand=SimpleNamespace(cards=[]))
        strategy = PygameChoiceStrategy(player)
        strategy.waiting_for = ChoiceType.USE_ABILITY
        player.choice_strategy = strategy
        game = self._keyboard_game(player, START_KEY=True)

        game.handle_choice()
        self.assertIs(strategy.choice, True)

        strategy.choice = None
        game.START_KEY = False
        game.SKIP_ABILITY_KEY = True
        game.handle_choice()
        self.assertIs(strategy.choice, False)

    def test_drag_destination_does_not_depend_on_stale_rendered_legal_slots(self):
        player = SimpleNamespace(hand=SimpleNamespace(cards=[]))
        strategy = PygameChoiceStrategy(player)
        strategy.waiting_for = ChoiceType.POSITION
        player.choice_strategy = strategy
        game = Game.__new__(Game)
        game.board = SimpleNamespace(
            player_on_turn=player,
            positions=[None, None, None, None, None, None],
        )
        game.pending_drop_position = 3
        game.current_legal_indices = []
        game.events = []
        game.mouse_clicked = False
        game.interaction_message = ""

        game._handle_local_mouse_choice()

        self.assertEqual(strategy.choice, 3)
        self.assertIsNone(game.pending_drop_position)
        self.assertEqual(game.interaction_message, "Card placed")

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

    def test_paced_ai_delay_can_be_cancelled_immediately(self):
        player = SimpleNamespace()
        strategy = PacedRandomStrategy(player)
        strategy.delay_seconds = 5
        exited = []

        def wait_for_turn():
            try:
                strategy.begin_turn_choices()
            except SystemExit:
                exited.append(True)

        worker = threading.Thread(target=wait_for_turn)
        started = time.monotonic()
        worker.start()
        strategy.exit_thread()
        worker.join(timeout=0.5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(exited, [True])
        self.assertLess(time.monotonic() - started, 0.5)

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
                requires_target=True,
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

    def test_human_strategy_skips_target_prompt_when_no_target_is_legal(self):
        player = SimpleNamespace()
        player.hand = SimpleNamespace(cards=[])
        strategy = PygameChoiceStrategy(player)
        player.choice_strategy = strategy
        strategy.selected_card = SimpleNamespace(
            ability=SimpleNamespace(
                is_active=True,
                target_owner=AbilityTarget.ENEMY,
                requires_target=True,
            )
        )
        strategy.selected_position = 0
        strategy.info = SimpleNamespace(
            game_board=SimpleNamespace(positions=[None] * 6)
        )

        self.assertFalse(strategy.get_choice_use_ability())
        self.assertIsNone(strategy.get_choice_ability_target())

    def test_random_strategy_respects_ability_target_owner(self):
        player = SimpleNamespace()
        strategy = ChoiceStrategyAIRandom(player)
        player.choice_strategy = strategy
        enemy = object()
        strategy.selected_card = SimpleNamespace(
            ability=SimpleNamespace(
                is_active=True,
                target_owner=AbilityTarget.ENEMY,
                requires_target=True,
            )
        )
        strategy.selected_position = 2
        strategy.info = SimpleNamespace(
            game_board=SimpleNamespace(
                positions=[
                    SimpleNamespace(owner=player),
                    SimpleNamespace(owner=enemy),
                    None,
                    None,
                    None,
                    None,
                ]
            )
        )

        self.assertTrue(strategy.get_choice_use_ability())
        self.assertEqual(strategy.get_choice_ability_target(), 1)

    def test_counter_training_command_contains_ui_configuration(self):
        request = TrainingRequest(
            kind=TrainingKind.PLAYER_DECK,
            deck_id="Starter Blue_1",
            outer_generations=6,
            evaluator_generations=35,
            workers=8,
            evaluation_games=20,
            run_label="professor-demo",
        )
        command = build_command(request)

        self.assertIn("neat_ai.player_trainer", command)
        self.assertEqual(command[command.index("--counter-generations") + 1], "6")
        self.assertEqual(command[command.index("--controller-generations") + 1], "35")
        self.assertEqual(command[command.index("--workers") + 1], "8")
        self.assertEqual(command[command.index("--evaluation-games") + 1], "20")

    def test_matchup_training_command_contains_both_decks(self):
        request = TrainingRequest(
            kind=TrainingKind.MATCHUP_EVALUATION,
            deck_id="Starter Blue_1",
            opponent_deck_id="Killer Queen_1",
            evaluator_generations=40,
            workers=8,
            evaluation_games=100,
        )

        command = build_command(request)

        self.assertIn("neat_ai.matchup_trainer", command)
        self.assertIn("Starter Blue_1", command)
        self.assertIn("Killer Queen_1", command)
        self.assertEqual(command[command.index("--generations") + 1], "40")

    def test_player_training_uses_low_mid_high_checkpoint_schedule(self):
        self.assertEqual(evaluation_checkpoints(10), (10,))
        self.assertEqual(evaluation_checkpoints(25), (10, 25))
        self.assertEqual(evaluation_checkpoints(40), (10, 25, 40))
        self.assertEqual(evaluation_checkpoints(65), (10, 25, 40, 65))

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

    def test_training_validation_rejects_unsafe_ranges(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 128"):
            TrainingRequest(workers=0).validate()
        with self.assertRaisesRegex(ValueError, "even number"):
            TrainingRequest(
                kind=TrainingKind.DECK_BUILDER,
                matches_per_genome=3,
            ).validate()

    def test_training_service_does_not_block_on_stale_database_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            process = SimpleNamespace(pid=123, poll=lambda: None)
            with (
                patch("py_game.training_service.JOB_ROOT", Path(directory)),
                patch("py_game.training_service.subprocess.Popen", return_value=process) as popen,
            ):
                service = TrainingService()
                job = service.start(
                    TrainingRequest(
                        kind=TrainingKind.PLAYER_DECK,
                        deck_id="Starter Blue_1",
                    )
                )

        self.assertEqual(job.status, "running")
        popen.assert_called_once()

    def test_training_service_stops_only_processes_owned_by_this_ui(self):
        process = SimpleNamespace(
            pid=4321,
            poll=lambda: None,
            wait=Mock(return_value=-2),
            terminate=Mock(),
            kill=Mock(),
        )
        job = TrainingJob(
            job_id="owned-job",
            request={},
            command=["trainer"],
            created_at="now",
            status="running",
            pid=4321,
            log_path="training.log",
            progress_path="progress.log",
            summary_path="summary.json",
        )
        service = TrainingService.__new__(TrainingService)
        service._processes = {job.job_id: process}
        service._load_job = Mock(return_value=job)
        service._save_job = Mock()

        with patch("py_game.training_service.os.killpg") as kill_group:
            stopped = service.stop_owned_jobs()

        self.assertEqual(stopped, [job])
        self.assertEqual(job.status, "cancelled")
        kill_group.assert_called_once_with(4321, ANY)
        service._save_job.assert_called_once_with(job)

    def test_quit_requires_confirmation_and_stops_owned_training(self):
        job = SimpleNamespace(job_id="ui-job")
        service = SimpleNamespace(
            owned_running_jobs=Mock(return_value=[job]),
            stop_owned_jobs=Mock(),
        )
        menu = SimpleNamespace(
            run_display=True,
            confirm_action=Mock(return_value=True),
        )
        game = Game.__new__(Game)
        game.training_service = service
        game.curr_menu = menu
        game.running = True
        game.playing = True
        game._quit_prompt_open = False
        game.reset_keys = Mock()

        self.assertTrue(game.request_quit())

        menu.confirm_action.assert_called_once()
        service.stop_owned_jobs.assert_called_once()
        self.assertFalse(game.running)
        self.assertFalse(menu.run_display)

    def test_cancelled_quit_keeps_training_and_pygame_alive(self):
        service = SimpleNamespace(
            owned_running_jobs=Mock(return_value=[SimpleNamespace(job_id="ui-job")]),
            stop_owned_jobs=Mock(),
        )
        menu = SimpleNamespace(
            run_display=True,
            confirm_action=Mock(return_value=False),
        )
        game = Game.__new__(Game)
        game.training_service = service
        game.curr_menu = menu
        game.running = True
        game.playing = False
        game._quit_prompt_open = False
        game.reset_keys = Mock()

        self.assertFalse(game.request_quit())

        service.stop_owned_jobs.assert_not_called()
        self.assertTrue(game.running)

    def test_matchup_selection_counts_duplicates_and_rejects_near_clones(self):
        decks = {
            "clone-a": tuple(["Archer"] * 8 + ["Page"] * 4),
            "clone-b": tuple(["Archer"] * 8 + ["Knight"] * 4),
            "varied-a": ("Archer", "Archer", "Page", "Knight"),
            "varied-b": ("Archer", "Smith", "Seer", "Guard"),
            "varied-c": ("Priest", "Scout", "Guard", "Smith"),
        }
        candidates = (
            ("clone-a", "clone-b", 4, 99.0),
            ("varied-a", "varied-b", 4, 18.0),
            ("varied-b", "varied-c", 4, -7.0),
        )

        favorable, difficult, eligible = select_diverse_matchups(
            candidates, decks, limit=1
        )

        self.assertEqual(shared_card_count(decks["clone-a"], decks["clone-b"]), 8)
        self.assertEqual(eligible, 2)
        self.assertEqual(favorable[0].score, 18.0)
        self.assertEqual(difficult[0].score, -7.0)
        self.assertLessEqual(favorable[0].shared_cards, 7)

    def test_training_service_surfaces_failed_process(self):
        service = TrainingService.__new__(TrainingService)
        service._processes = {"job-1": SimpleNamespace(poll=lambda: 2)}
        service._save_job = Mock()
        job = TrainingJob(
            job_id="job-1",
            request={},
            command=["trainer"],
            created_at="now",
            status="running",
            pid=123,
            log_path="training.log",
            progress_path="progress.log",
            summary_path="summary.json",
        )

        self.assertEqual(service.refresh(job).status, "failed")
        self.assertEqual(job.return_code, 2)
        service._save_job.assert_called_once_with(job)

    def test_failed_player_run_explains_missing_statistics(self):
        service = TrainingService.__new__(TrainingService)
        service._processes = {}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "training.log"
            log.write_text("Traceback (most recent call last):\nValueError: invalid deck\n")
            job = TrainingJob(
                job_id="failed-player",
                request={"kind": TrainingKind.PLAYER_DECK.value},
                command=["trainer"],
                created_at="2026-09-02T10:00:00",
                status="failed",
                pid=None,
                log_path=str(log),
                progress_path=str(root / "progress.log"),
                summary_path=str(root / "summary.json"),
            )

            insights = service.job_insights(job)

        self.assertIn("failed", insights.conclusions[0])
        self.assertIn("ValueError: invalid deck", insights.conclusions[1])

    def test_unfinished_database_rows_are_historical_not_active_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "train.db"
            connection = sqlite3.connect(database)
            connection.executescript(
                """
                CREATE TABLE training (
                    id INTEGER PRIMARY KEY,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    metadata TEXT
                );
                CREATE TABLE genome (
                    guid TEXT PRIMARY KEY,
                    gen INTEGER,
                    deck_id TEXT,
                    score REAL,
                    training_id INTEGER
                );
                INSERT INTO training VALUES (10, '2026-07-14', NULL, '{}');
                """
            )
            connection.commit()
            connection.close()
            with patch("py_game.training_service.TRAIN_DB_PATH", database):
                runs = TrainingService().recent_database_runs()

        self.assertEqual(runs[0].run_id, "DB 10")
        self.assertEqual(runs[0].status, "incomplete")

    def test_training_telemetry_parses_live_generation_battle_and_power_signals(self):
        service = TrainingService.__new__(TrainingService)
        service._processes = {}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "training.log"
            progress = root / "progress.log"
            summary = root / "summary.json"
            log.write_text(
                "generation: 1 | trainning round: 4/10 | top_fitness: 8.5\n"
                "generation: 2 | trainning round: 3/10 | top_fitness: 12.25\n"
            )
            job = TrainingJob(
                job_id="job-telemetry",
                request={
                    "kind": TrainingKind.PLAYER_DECK.value,
                    "evaluator_generations": 20,
                    "workers": 8,
                },
                command=["trainer"],
                created_at="now",
                status="running",
                pid=None,
                log_path=str(log),
                progress_path=str(progress),
                summary_path=str(summary),
            )

            telemetry = service.job_telemetry(job)

        self.assertEqual(telemetry.generation, 2)
        self.assertEqual(telemetry.total_generations, 20)
        self.assertEqual((telemetry.round_completed, telemetry.round_total), (3, 10))
        self.assertEqual(telemetry.best_score, 12.25)
        self.assertEqual(telemetry.fitness_history, ((1, 8.5), (2, 12.25)))
        self.assertEqual(telemetry.workers, 8)

    def test_training_telemetry_prefers_structured_phase_and_eta_events(self):
        service = TrainingService.__new__(TrainingService)
        service._processes = {}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            telemetry_path = root / "telemetry.jsonl"
            telemetry_path.write_text(
                "\n".join(
                    (
                        json.dumps(
                            {
                                "schema_version": 1,
                                "event": "phase_started",
                                "phase": "checkpoint_evaluation",
                                "phase_progress": 0.0,
                                "checkpoint_total": 3,
                            }
                        ),
                        json.dumps(
                            {
                                "schema_version": 1,
                                "event": "phase_progress",
                                "phase": "checkpoint_evaluation",
                                "generation": 40,
                                "total_generations": 40,
                                "checkpoint_generation": 25,
                                "completed": 150,
                                "total": 300,
                                "phase_progress": 0.5,
                                "eta_seconds": 42.0,
                                "best_score": 88.5,
                            }
                        ),
                    )
                )
            )
            log = root / "training.log"
            log.write_text("generation: 40 | trainning round: 105/105 | top_fitness: 88.5\n")
            job = TrainingJob(
                job_id="structured-job",
                request={
                    "kind": TrainingKind.PLAYER_DECK.value,
                    "evaluator_generations": 40,
                    "workers": 8,
                },
                command=["trainer"],
                created_at="2026-09-02T10:00:00",
                status="running",
                pid=None,
                log_path=str(log),
                progress_path=str(root / "progress.log"),
                summary_path=str(root / "summary.json"),
                telemetry_path=str(telemetry_path),
            )

            telemetry = service.job_telemetry(job)

        self.assertEqual(telemetry.phase, "checkpoint_evaluation")
        self.assertEqual(telemetry.phase_progress, 0.5)
        self.assertEqual(telemetry.eta_seconds, 42.0)
        self.assertEqual(telemetry.checkpoint_generation, 25)
        self.assertEqual((telemetry.round_completed, telemetry.round_total), (150, 300))

    def test_completed_builder_job_loads_its_database_analytics(self):
        service = TrainingService.__new__(TrainingService)
        service._processes = {}
        expected = TrainingInsights(
            run_kind=TrainingKind.DECK_BUILDER.value,
            total_matches=40,
        )
        service.database_insights = Mock(return_value=expected)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            progress = root / "progress.log"
            log = root / "training.log"
            progress.write_text(
                "training_id: 70 | generation: 1 | training round: 0/40\n"
            )
            log.write_text(
                "generation: 1 | training round: 40/40\n"
                "best fitness: 93.5\n"
            )
            job = TrainingJob(
                job_id="builder-job",
                request={
                    "kind": TrainingKind.DECK_BUILDER.value,
                    "run_label": "pygame",
                    "outer_generations": 1,
                    "workers": 12,
                },
                command=["trainer"],
                created_at="now",
                status="completed",
                pid=None,
                log_path=str(log),
                progress_path=str(progress),
                summary_path=str(root / "missing-summary.json"),
            )

            telemetry = service.job_telemetry(job)
            insights = service.job_insights(job)
            database_run_id = service.job_database_run_id(job)

        self.assertEqual(database_run_id, 70)
        self.assertEqual(telemetry.best_score, 93.5)
        self.assertEqual(telemetry.fitness_history, ((1, 93.5),))
        service.database_insights.assert_called_once()
        database_run = service.database_insights.call_args.args[0]
        self.assertEqual(database_run.run_id, "DB 70")
        self.assertEqual(insights.total_matches, 40)
        self.assertEqual(insights.subject, "pygame · DB 70")

    def test_player_training_uses_evaluation_specific_report_sections(self):
        service = TrainingService.__new__(TrainingService)
        service._processes = {}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "summary.json"
            summary.write_text(
                json.dumps(
                    {
                        "deck_name": "Killer Queen",
                        "opponent_deck_name": "Iron Choir",
                        "elapsed_seconds": 180,
                        "best_fitness": 44.0,
                        "evaluation": {
                            "games": 20,
                            "ai_wins": 12,
                            "draws": 3,
                            "random_wins": 5,
                            "ai_win_rate": 0.6,
                        },
                        "skill_evaluations": [
                            {"generation": 10, "ai_wins": 8, "draws": 2, "random_wins": 10},
                            {"generation": 25, "ai_wins": 10, "draws": 3, "random_wins": 7},
                            {"generation": 40, "ai_wins": 12, "draws": 3, "random_wins": 5},
                        ],
                    }
                )
            )
            log = root / "training.log"
            log.write_text("generation: 1 | top_fitness: 44.0\n")
            job = TrainingJob(
                job_id="matchup-job",
                request={"kind": TrainingKind.MATCHUP_EVALUATION.value},
                command=["trainer"],
                created_at="now",
                status="completed",
                pid=None,
                log_path=str(log),
                progress_path=str(root / "progress.log"),
                summary_path=str(summary),
            )
            insights = service.job_insights(job)

        menu = TrainingMenu.__new__(TrainingMenu)
        menu.dashboard_item = job
        menu.dashboard_insights = insights
        self.assertEqual(insights.evaluation, (12, 3, 5))
        self.assertEqual(insights.subject, "Killer Queen")
        self.assertEqual(insights.opponent, "Iron Choir")
        self.assertEqual(
            insights.skill_evaluations,
            ((10, 8, 2, 10), (25, 10, 3, 7), (40, 12, 3, 5)),
        )
        self.assertEqual(insights.elapsed_seconds, 180.0)
        self.assertEqual(insights.total_evaluation_games, 60)
        self.assertEqual(
            menu._dashboard_pages(),
            ("Overview", "Learning", "Evaluation", "Conclusions"),
        )


if __name__ == "__main__":
    unittest.main()
