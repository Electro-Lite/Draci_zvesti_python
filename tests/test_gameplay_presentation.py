import unittest
import threading
import time
from types import SimpleNamespace

from cards.ability.ability_target import AbilityTarget
from core.game_loop import battle_dragon, play_card
from py_game.game import Game
from py_game.battle_presentation import local_battle_display_strategy
from py_game.network.gameplay import serialize_game_state


class GameplayFlowTests(unittest.TestCase):
    def _play_fixture(self, *, requires_target):
        player = SimpleNamespace()
        player.recorded = []
        player.record_card_play = lambda card, used: player.recorded.append((card, used))
        ability = SimpleNamespace(
            is_active=True,
            requires_target=requires_target,
            target_owner=AbilityTarget.ENEMY,
        )
        card = SimpleNamespace(name="Scout", ability=ability, owner=None)
        board = SimpleNamespace(positions=[None] * 6, staged=[], resolved=[])

        def stage(selected, position):
            board.positions[position] = selected
            board.staged.append((selected, position))

        board.stage_card = stage
        board.resolve_staged_card = lambda selected, used, target: board.resolved.append(
            (selected, used, target)
        )
        events = []

        class Choice:
            def get_choice_card(self):
                events.append("card")
                return card

            def get_choice_pos(self):
                events.append("position")
                return 2

            def get_choice_use_ability(self):
                self.testcase.assertIs(board.positions[2], card)
                self.testcase.assertIs(card.owner, player)
                events.append("ability")
                return True

            def get_choice_ability_target(self):
                self.testcase.assertIs(board.positions[2], card)
                events.append("target")
                return 4

        choice = Choice()
        choice.testcase = self
        display = SimpleNamespace(
            display_choice=lambda *_args: events.append("display_choice"),
            display_board=lambda: events.append("display_board"),
        )
        return player, card, board, choice, display, events

    def test_untargeted_active_card_is_staged_and_bypasses_target_selection(self):
        player, card, board, choice, display, events = self._play_fixture(
            requires_target=False
        )

        play_card(player, choice, board, display)

        self.assertEqual(board.staged, [(card, 2)])
        self.assertEqual(board.resolved, [(card, True, None)])
        self.assertNotIn("target", events)
        self.assertLess(events.index("display_board"), events.index("ability"))

    def test_targeted_active_card_remains_staged_during_target_selection(self):
        player, card, board, choice, display, events = self._play_fixture(
            requires_target=True
        )

        play_card(player, choice, board, display)

        self.assertEqual(board.resolved, [(card, True, 4)])
        self.assertEqual(events.count("target"), 1)


class DragonBattlePresentationTests(unittest.TestCase):
    def test_battle_frames_are_three_times_slower(self):
        self.assertAlmostEqual(Game.BATTLE_FRAME_SECONDS, 1.95)

    def test_final_battle_frame_waits_for_explicit_confirmation(self):
        confirmation = threading.Event()
        strategy = local_battle_display_strategy(
            0.0,
            continue_requested=confirmation.is_set,
            reset_continue=confirmation.clear,
        )(None, None, None)
        completed = threading.Event()
        worker = threading.Thread(
            target=lambda: (strategy.display_battle_result(), completed.set()),
            daemon=True,
        )

        worker.start()
        time.sleep(0.05)
        self.assertFalse(completed.is_set())
        confirmation.set()
        worker.join(timeout=0.5)

        self.assertTrue(completed.is_set())
        self.assertFalse(confirmation.is_set())

    def test_battle_emits_reveal_versus_impact_and_result_frames(self):
        owner = SimpleNamespace(graveyard=[])
        card = SimpleNamespace(name="Knight", hp=2, dmg=2, owner=owner)
        dragon = SimpleNamespace(
            name="Ashwing",
            hp=3,
            dmg=1,
            slain_by=None,
            ability=SimpleNamespace(is_active=False),
            restore=lambda: None,
        )
        board = SimpleNamespace(
            game_state=None,
            dragons=[dragon],
            dragon=None,
            battle_event=None,
            positions=[card, None, None, None, None, None],
            recalculate=lambda *_args, **_kwargs: None,
        )
        board.remove_card = lambda selected: board.positions.__setitem__(
            board.positions.index(selected), None
        )
        phases = []

        class Display:
            this_player = owner
            dragon = None

            def capture(self):
                phases.append(board.battle_event["phase"])

            display_dragon = capture
            display_dragon_vs_card = capture
            display_battle_result = capture
            display_board = lambda self: None

        winner = battle_dragon(board, Display())

        self.assertIs(winner, owner)
        self.assertEqual(phases[0], "reveal")
        self.assertIn("versus", phases)
        self.assertIn("impact", phases)
        self.assertEqual(phases[-1], "dragon_defeated")
        self.assertIsNone(board.battle_event)

    def test_eliminated_card_frame_shows_recalculated_board_before_next_duel(self):
        owner = SimpleNamespace(graveyard=[])
        front_card = SimpleNamespace(name="Front Line", hp=1, dmg=1, owner=owner)
        affected_card = SimpleNamespace(name="Archer", hp=4, dmg=1, owner=owner)
        dragon = SimpleNamespace(
            name="Ashwing",
            hp=4,
            dmg=2,
            slain_by=None,
            ability=SimpleNamespace(is_active=False),
            restore=lambda: None,
        )
        board = SimpleNamespace(
            game_state=None,
            dragons=[dragon],
            dragon=None,
            battle_event=None,
            positions=[front_card, affected_card, None, None, None, None],
        )

        def recalculate(*_args, **_kwargs):
            affected_card.dmg = 3 if board.positions[0] is None else 1

        board.recalculate = recalculate
        board.remove_card = lambda selected: board.positions.__setitem__(
            board.positions.index(selected), None
        )
        eliminated_frames = []

        class Display:
            this_player = owner
            dragon = None

            def capture(self):
                if board.battle_event["phase"] == "card_defeated":
                    eliminated_frames.append(
                        (list(board.positions), affected_card.dmg, board.battle_event["slot"])
                    )

            display_dragon = capture
            display_dragon_vs_card = capture
            display_battle_result = capture
            display_board = lambda self: None

        winner = battle_dragon(board, Display())

        self.assertIs(winner, owner)
        self.assertEqual(len(eliminated_frames), 1)
        positions, affected_damage, eliminated_slot = eliminated_frames[0]
        self.assertIsNone(positions[0])
        self.assertIs(positions[1], affected_card)
        self.assertEqual(affected_damage, 3)
        self.assertEqual(eliminated_slot, 0)

    def test_serialized_battle_frame_contains_only_public_challenger_data(self):
        ability = SimpleNamespace(name="", description="", is_active=False)
        local = SimpleNamespace(
            id=1,
            score=0,
            passed=False,
            deck=SimpleNamespace(cards=[]),
            graveyard=[],
            hand=SimpleNamespace(cards=[]),
        )
        opponent = SimpleNamespace(
            id=2,
            score=0,
            passed=False,
            deck=SimpleNamespace(cards=[]),
            graveyard=[],
            hand=SimpleNamespace(cards=[]),
        )
        card = SimpleNamespace(
            id="public-card",
            name="Knight",
            hp=1,
            dmg=2,
            color="BLUE",
            power="NORMAL",
            ability=ability,
            owner=local,
        )
        dragon = SimpleNamespace(
            id="dragon",
            name="Dragon",
            hp=4,
            dmg=2,
            color="RED",
            power="LEGENDARY",
            ability=ability,
            owner=None,
        )
        board = SimpleNamespace(
            mana_pool=[],
            round=1,
            game_state="BATTLE",
            player_on_turn=local,
            positions=[card, None, None, None, None, None],
            dragon=dragon,
            dragons=[],
            winner=None,
            battle_event={"phase": "impact", "card": card, "slot": 0},
        )

        state = serialize_game_state(board, local, opponent)

        self.assertEqual(state["battle"]["phase"], "impact")
        self.assertEqual(state["battle"]["card"]["id"], "public-card")

    def test_dragon_defeat_frame_identifies_board_slot_and_point_recipient(self):
        ability = SimpleNamespace(name="", description="", is_active=False)
        local = SimpleNamespace(
            id=1,
            score=0,
            passed=False,
            deck=SimpleNamespace(cards=[]),
            graveyard=[],
            hand=SimpleNamespace(cards=[]),
        )
        opponent = SimpleNamespace(
            id=2,
            score=0,
            passed=False,
            deck=SimpleNamespace(cards=[]),
            graveyard=[],
            hand=SimpleNamespace(cards=[]),
        )
        card = SimpleNamespace(
            id="finisher",
            name="Finisher",
            hp=3,
            dmg=5,
            color="BLUE",
            power="NORMAL",
            ability=ability,
            owner=local,
        )
        dragon = SimpleNamespace(
            id="dragon",
            name="Dragon",
            hp=2,
            dmg=1,
            color="RED",
            power="LEGENDARY",
            ability=SimpleNamespace(is_active=False),
            owner=None,
            slain_by=None,
            restore=lambda: None,
        )
        board = SimpleNamespace(
            mana_pool=[],
            round=1,
            game_state=None,
            player_on_turn=local,
            positions=[None, None, card, None, None, None],
            dragon=None,
            dragons=[dragon],
            winner=None,
            battle_event=None,
            recalculate=lambda *_args, **_kwargs: None,
        )
        captured = []

        class Display:
            this_player = local
            dragon = None
            display_dragon = lambda self: None
            display_dragon_vs_card = lambda self: None
            display_board = lambda self: None

            def display_battle_result(self):
                captured.append(serialize_game_state(board, local, opponent)["battle"])

        battle_dragon(board, Display())

        self.assertEqual(captured[0]["slot"], 2)
        self.assertEqual(captured[0]["point_for"], "local")


if __name__ == "__main__":
    unittest.main()
