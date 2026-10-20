import unittest
from types import SimpleNamespace

from cards.ability.abilities import (
    BlackManaOn,
    BlockManaEffects,
    BlueManaOn,
    NoAbility,
    RedManaOn,
    SidewaysMinus1,
)
from cards.card import Card
from cards.mana import Mana, ManaColor
from core.board import Board


def make_card(
    owner,
    name,
    hp,
    damage,
    ability,
    *,
    color=ManaColor.RED,
    color_buf=None,
):
    return Card(
        owner=owner,
        id=name.lower(),
        name=name,
        color=color,
        color_buf=color_buf or [0, 0],
        hp=hp,
        dmg=damage,
        ability=ability,
    )


def make_board(color=ManaColor.RED):
    board = Board.__new__(Board)
    board.positions = [None] * 6
    board.mana_pool = [Mana(color)]
    board.dragon = None
    board.dragon_base_dmg = None
    board._recalculating = False
    board._recalculate_requested = False
    return board


class PassiveRecalculationTests(unittest.TestCase):
    def test_lethal_left_debuff_does_not_apply_twice_to_right_neighbor(self):
        owner = SimpleNamespace(graveyard=[])
        left = make_card(owner, "Left", 1, 1, NoAbility())
        source = make_card(owner, "Vampire", 3, 1, SidewaysMinus1())
        right = make_card(owner, "Right", 3, 3, NoAbility())
        board = make_board()
        board.positions[:3] = [left, source, right]

        board.recalculate()

        self.assertIsNone(board.positions[0])
        self.assertEqual(owner.graveyard, [left])
        self.assertEqual((right.dmg, right.hp), (2, 2))

    def test_black_mana_can_remove_both_neighbors_without_recursive_failure(self):
        owner = SimpleNamespace(graveyard=[])
        left = make_card(owner, "Left", 2, 1, NoAbility())
        source = make_card(owner, "Vampire", 3, 1, SidewaysMinus1())
        right = make_card(owner, "Right", 2, 1, NoAbility())
        board = make_board(ManaColor.BLACK)
        board.positions[:3] = [left, source, right]

        board.recalculate()

        self.assertEqual(board.positions[:3], [None, source, None])
        self.assertEqual(owner.graveyard, [left, right])

    def test_sideways_penalty_never_creates_negative_attack(self):
        owner = SimpleNamespace(graveyard=[])
        source = make_card(owner, "Vampire", 3, 1, SidewaysMinus1())
        target = make_card(owner, "Target", 4, 0, NoAbility())
        board = make_board(ManaColor.BLACK)
        board.positions[:2] = [source, target]

        board.recalculate()

        self.assertEqual(target.dmg, 0)
        self.assertEqual(target.hp, 2)

    def test_black_mana_aura_keeps_real_mana_active_and_adds_black(self):
        owner = SimpleNamespace(graveyard=[])
        aura = make_card(owner, "Aura", 2, 1, BlackManaOn())
        black = make_card(
            owner,
            "Black card",
            2,
            2,
            NoAbility(),
            color=ManaColor.BLACK,
            color_buf=[1, 2],
        )
        red = make_card(
            owner,
            "Red card",
            2,
            2,
            NoAbility(),
            color=ManaColor.RED,
            color_buf=[2, 1],
        )
        board = make_board(ManaColor.RED)
        board.positions[:3] = [aura, black, red]

        board.recalculate()

        self.assertEqual(board.active_mana_colors(), {ManaColor.RED, ManaColor.BLACK})
        self.assertEqual((black.dmg, black.hp), (3, 4))
        self.assertEqual((red.dmg, red.hp), (4, 3))

    def test_black_aura_enables_black_conditional_abilities(self):
        owner = SimpleNamespace(graveyard=[])
        aura = make_card(owner, "Aura", 3, 1, BlackManaOn())
        source = make_card(owner, "Vampire", 3, 1, SidewaysMinus1())
        target = make_card(owner, "Target", 3, 3, NoAbility())
        board = make_board(ManaColor.RED)
        board.positions[:3] = [aura, source, target]

        board.recalculate()

        self.assertEqual((target.dmg, target.hp), (1, 1))

    def test_removing_black_aura_removes_its_continuous_effect(self):
        owner = SimpleNamespace(graveyard=[])
        aura = make_card(owner, "Aura", 2, 1, BlackManaOn())
        black = make_card(
            owner,
            "Black card",
            2,
            2,
            NoAbility(),
            color=ManaColor.BLACK,
            color_buf=[1, 1],
        )
        board = make_board(ManaColor.RED)
        board.positions[:2] = [aura, black]
        board.recalculate()

        board.remove_card(aura)

        self.assertFalse(board.is_mana_active(ManaColor.BLACK))
        self.assertEqual((black.dmg, black.hp), (2, 2))

    def test_blue_and_red_auras_stack_with_real_black_mana(self):
        owner = SimpleNamespace(graveyard=[])
        board = make_board(ManaColor.BLACK)
        board.positions[:2] = [
            make_card(owner, "Blue aura", 2, 1, BlueManaOn()),
            make_card(owner, "Red aura", 2, 1, RedManaOn()),
        ]

        board.recalculate()

        self.assertEqual(
            board.active_mana_colors(),
            {ManaColor.RED, ManaColor.BLACK, ManaColor.BLUE},
        )

    def test_mana_blocker_overrides_real_and_added_mana(self):
        owner = SimpleNamespace(graveyard=[])
        blue = make_card(
            owner,
            "Blue card",
            3,
            2,
            NoAbility(),
            color=ManaColor.BLUE,
            color_buf=[2, 2],
        )
        board = make_board(ManaColor.BLUE)
        conditional = make_card(owner, "Conditional", 4, 1, SidewaysMinus1())
        target = make_card(owner, "Target", 4, 3, NoAbility())
        board.positions = [
            make_card(owner, "Black aura", 4, 1, BlackManaOn()),
            make_card(owner, "Red aura", 4, 1, RedManaOn()),
            make_card(owner, "Blocker", 4, 1, BlockManaEffects()),
            blue,
            conditional,
            target,
        ]

        board.recalculate()

        self.assertEqual(board.active_mana_colors(), set())
        self.assertEqual((blue.dmg, blue.hp), (1, 2))
        self.assertEqual((target.dmg, target.hp), (2, 3))

    def test_removing_blocker_restores_real_and_added_mana(self):
        owner = SimpleNamespace(graveyard=[])
        aura = make_card(owner, "Red aura", 4, 1, RedManaOn())
        blocker = make_card(owner, "Blocker", 4, 1, BlockManaEffects())
        board = make_board(ManaColor.BLUE)
        board.positions[:2] = [aura, blocker]
        board.recalculate()

        board.remove_card(blocker)

        self.assertEqual(
            board.active_mana_colors(),
            {ManaColor.BLUE, ManaColor.RED},
        )


if __name__ == "__main__":
    unittest.main()
