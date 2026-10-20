import unittest
from types import SimpleNamespace

from cards.ability.abilities import (
    HitDragonBlueInfrontDmg,
    NoAbility,
    PlaceSecondBeside,
    Plus1_1FromRed,
    Replace,
    can_use_on_play,
)
from cards.card import Card
from cards.mana import Mana, ManaColor
from choice_strategies.choice_strategy_human_pygame import PygameChoiceStrategy
from core.board import Board


def make_card(name, color, ability=None, *, owner=None, hp=2, damage=2):
    return Card(
        owner=owner,
        id=name.lower().replace(" ", "-"),
        name=name,
        color=color,
        color_buf=[0, 0],
        hp=hp,
        dmg=damage,
        ability=ability or NoAbility(),
    )


def make_board():
    board = Board()
    board.positions = [None] * 6
    board.mana_pool = [Mana(ManaColor.BLACK)]
    board.dragon = None
    board.dragon_base_dmg = None
    return board


class PlaceSecondBesideTests(unittest.TestCase):
    def test_places_chosen_legal_card_of_any_color_in_adjacent_slot(self):
        owner = SimpleNamespace(hand=SimpleNamespace(cards=[]), graveyard=[])
        commander = make_card(
            "Commander", ManaColor.BLUE, PlaceSecondBeside(), owner=owner
        )
        blue = make_card("Blue guard", ManaColor.BLUE)
        red = make_card("Red guard", ManaColor.RED)
        second_commander = make_card(
            "Other commander", ManaColor.BLUE, PlaceSecondBeside()
        )
        owner.hand.cards = [red, blue, second_commander]
        board = make_board()
        board.positions[2] = commander

        self.assertEqual(commander.ability.legal_hand_card_indices(commander, board), [0, 1])
        self.assertEqual(commander.ability.legal_target_positions(commander, board), [1, 3])

        board.resolve_staged_card(
            commander,
            True,
            {"hand_card": blue, "target_pos": 3},
        )

        self.assertIs(board.positions[3], blue)
        self.assertIs(blue.owner, owner)
        self.assertEqual(owner.hand.cards, [red, second_commander])

    def test_ability_is_not_offered_when_both_adjacent_slots_are_occupied(self):
        owner = SimpleNamespace(hand=SimpleNamespace(cards=[]), graveyard=[])
        commander = make_card(
            "Commander", ManaColor.BLUE, PlaceSecondBeside(), owner=owner
        )
        owner.hand.cards = [make_card("Red guard", ManaColor.RED)]
        board = make_board()
        board.positions[:3] = [
            make_card("Left", ManaColor.BLACK, owner=owner),
            commander,
            make_card("Right", ManaColor.BLUE, owner=owner),
        ]
        strategy = PygameChoiceStrategy(owner)
        strategy.selected_card = commander
        strategy.selected_position = 1
        strategy.info = SimpleNamespace(game_board=board)

        self.assertFalse(strategy.get_choice_use_ability())

    def test_skipping_leaves_hand_and_board_unchanged(self):
        owner = SimpleNamespace(hand=SimpleNamespace(cards=[]), graveyard=[])
        commander = make_card(
            "Commander", ManaColor.BLUE, PlaceSecondBeside(), owner=owner
        )
        blue = make_card("Blue guard", ManaColor.BLUE)
        owner.hand.cards = [blue]
        board = make_board()
        board.positions[2] = commander

        board.resolve_staged_card(commander, False)

        self.assertEqual(owner.hand.cards, [blue])
        self.assertEqual(board.positions, [None, None, commander, None, None, None])

    def test_cannot_stage_two_commanders_for_same_player(self):
        owner = SimpleNamespace(hand=SimpleNamespace(cards=[]), graveyard=[])
        first = make_card("First", ManaColor.BLUE, PlaceSecondBeside(), owner=owner)
        second = make_card("Second", ManaColor.BLUE, PlaceSecondBeside(), owner=owner)
        board = make_board()
        board.stage_card(first, 0)

        with self.assertRaisesRegex(ValueError, "only one commander"):
            board.stage_card(second, 1)


class PlusFromRedTests(unittest.TestCase):
    def test_counts_every_other_red_card_regardless_of_owner(self):
        owner = SimpleNamespace(graveyard=[])
        source = make_card("Source", ManaColor.RED, Plus1_1FromRed(), owner=owner)
        ally = make_card("Ally", ManaColor.RED, owner=owner)
        enemy_owner = SimpleNamespace(graveyard=[])
        enemy = make_card("Enemy", ManaColor.RED, owner=enemy_owner)
        blue = make_card("Blue", ManaColor.BLUE, owner=owner)
        board = make_board()
        board.positions[:4] = [ally, source, enemy, blue]

        board.recalculate()

        self.assertEqual((source.dmg, source.hp), (4, 4))


class ReplaceTests(unittest.TestCase):
    def test_placing_over_ally_replaces_it_and_returns_it_restored_to_hand(self):
        owner = SimpleNamespace(hand=SimpleNamespace(cards=[]), graveyard=[])
        ally = make_card("Ally", ManaColor.RED, owner=owner, hp=3, damage=4)
        replacement = make_card(
            "Replacement", ManaColor.BLUE, Replace(), owner=owner
        )
        enemy_owner = SimpleNamespace(hand=SimpleNamespace(cards=[]), graveyard=[])
        enemy = make_card("Enemy", ManaColor.RED, owner=enemy_owner)
        board = make_board()
        board.positions = [ally, enemy, None, None, None, None]
        ally.hp = 1

        self.assertEqual(
            board.legal_placement_positions(replacement, owner),
            [0, 2, 3, 4, 5],
        )
        board.stage_card(replacement, 0)

        self.assertIs(board.positions[0], replacement)
        self.assertEqual(owner.hand.cards, [ally])
        self.assertEqual(ally.hp, 3)

    def test_replace_is_a_placement_rule_not_an_on_play_prompt(self):
        owner = SimpleNamespace(hand=SimpleNamespace(cards=[]), graveyard=[])
        replacement = make_card(
            "Replacement", ManaColor.BLUE, Replace(), owner=owner
        )
        board = make_board()

        self.assertFalse(can_use_on_play(replacement.ability))
        self.assertEqual(
            board.legal_placement_positions(replacement, owner),
            [0, 1, 2, 3, 4, 5],
        )

    def test_pygame_placement_mask_includes_allies_but_not_enemies(self):
        owner = SimpleNamespace(hand=SimpleNamespace(cards=[]), graveyard=[])
        enemy_owner = SimpleNamespace(hand=SimpleNamespace(cards=[]), graveyard=[])
        # Loaded hand cards do not receive their runtime Player owner until
        # after position selection in play_card(). Placement legality must use
        # the acting player supplied by the strategy instead.
        replacement = make_card("Replacement", ManaColor.BLUE, Replace())
        board = make_board()
        board.positions[:3] = [
            make_card("Ally", ManaColor.RED, owner=owner),
            make_card("Enemy", ManaColor.RED, owner=enemy_owner),
            None,
        ]
        strategy = PygameChoiceStrategy(owner)
        strategy.selected_card = replacement
        strategy.info = SimpleNamespace(game_board=board)

        self.assertEqual(strategy.legal_placement_positions(), [0, 2, 3, 4, 5])


class BlueCardsHitDragonTests(unittest.TestCase):
    def test_hits_for_blue_cards_before_source_only(self):
        owner = SimpleNamespace(id=1, graveyard=[])
        source = make_card(
            "Dragon hunter",
            ManaColor.RED,
            HitDragonBlueInfrontDmg(),
            owner=owner,
        )
        board = make_board()
        board.positions = [
            make_card("Blue one", ManaColor.BLUE),
            make_card("Red", ManaColor.RED),
            make_card("Blue two", ManaColor.BLUE),
            source,
            make_card("Blue behind", ManaColor.BLUE),
            None,
        ]
        dragon = SimpleNamespace(name="Dragon", hp=2, slain_by=None)

        source.ability.apply_onDragonReveal(source, board, dragon)

        self.assertEqual(dragon.hp, 0)
        self.assertIs(dragon.slain_by, owner)
        self.assertEqual(board.battle_event["dragon_damage"], 2)


if __name__ == "__main__":
    unittest.main()
