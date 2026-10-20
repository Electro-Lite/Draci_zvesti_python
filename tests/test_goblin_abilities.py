import unittest
from types import SimpleNamespace

from cards.ability.abilities import (
    BuffFromGoblin,
    NoAbility,
    SummonOtherGoblins,
    can_use_on_play,
)
from cards.card import Card
from cards.mana import Mana, ManaColor
from choice_strategies.choice_strategy_human_pygame import PygameChoiceStrategy
from core.board import Board


def make_card(name, ability, *, owner=None, hp=1, damage=1):
    return Card(
        owner=owner,
        id=name.lower().replace(" ", "-"),
        name=name,
        color=ManaColor.GREEN,
        color_buf=[0, 0],
        hp=hp,
        dmg=damage,
        ability=ability,
    )


def make_board():
    board = Board.__new__(Board)
    board.positions = [None] * 6
    board.mana_pool = [Mana(ManaColor.RED)]
    board.dragon = None
    board.dragon_base_dmg = None
    return board


class GoblinAbilityTests(unittest.TestCase):
    def test_summon_is_an_optional_on_play_ability_not_an_active_ability(self):
        ability = SummonOtherGoblins()

        self.assertFalse(ability.is_active)
        self.assertTrue(ability.is_onPlay)
        self.assertTrue(can_use_on_play(ability))

    def test_human_player_is_offered_the_optional_summon_choice(self):
        player = SimpleNamespace(hand=SimpleNamespace(cards=[]))
        strategy = PygameChoiceStrategy(player)
        strategy.selected_card = make_card("Goblin caller", SummonOtherGoblins())
        strategy.choice = True

        self.assertTrue(strategy.get_choice_use_ability())

    def test_human_player_can_skip_the_optional_summon_choice(self):
        player = SimpleNamespace(hand=SimpleNamespace(cards=[]))
        strategy = PygameChoiceStrategy(player)
        strategy.selected_card = make_card("Goblin caller", SummonOtherGoblins())
        strategy.choice = False

        self.assertFalse(strategy.get_choice_use_ability())

    def test_using_summon_fills_empty_slots_left_to_right_and_discards_overflow(self):
        owner = SimpleNamespace(
            deck=SimpleNamespace(cards=[]),
            hand=SimpleNamespace(cards=[]),
            graveyard=[],
        )
        source = make_card("Goblin caller", SummonOtherGoblins(), owner=owner)
        deck_goblins = [
            make_card("Deck goblin one", SummonOtherGoblins()),
            make_card("Deck goblin two", SummonOtherGoblins()),
        ]
        hand_goblin = make_card("Hand goblin", SummonOtherGoblins())
        deck_other = make_card("Deck knight", NoAbility())
        hand_other = make_card("Hand knight", NoAbility())
        owner.deck.cards = [*deck_goblins, deck_other]
        owner.hand.cards = [hand_goblin, hand_other]

        board = make_board()
        board.positions = [
            make_card("Blocker zero", NoAbility(), owner=owner),
            None,
            make_card("Blocker two", NoAbility(), owner=owner),
            source,
            make_card("Blocker four", NoAbility(), owner=owner),
            None,
        ]

        board.resolve_staged_card(source, True)

        self.assertIs(board.positions[1], deck_goblins[0])
        self.assertIs(board.positions[5], deck_goblins[1])
        self.assertEqual(owner.deck.cards, [deck_other])
        self.assertEqual(owner.hand.cards, [hand_other])
        self.assertEqual(owner.graveyard, [hand_goblin])
        self.assertTrue(all(goblin.owner is owner for goblin in [*deck_goblins, hand_goblin]))

    def test_skipping_summon_leaves_deck_and_hand_unchanged(self):
        goblin = make_card("Waiting goblin", SummonOtherGoblins())
        owner = SimpleNamespace(
            deck=SimpleNamespace(cards=[goblin]),
            hand=SimpleNamespace(cards=[]),
            graveyard=[],
        )
        source = make_card("Goblin caller", SummonOtherGoblins(), owner=owner)
        board = make_board()
        board.positions[2] = source

        board.resolve_staged_card(source, False)

        self.assertEqual(owner.deck.cards, [goblin])
        self.assertEqual(board.positions.count(source), 1)
        self.assertEqual(owner.graveyard, [])

    def test_buff_counts_every_goblin_and_does_not_stack_on_recalculation(self):
        owner = SimpleNamespace(graveyard=[])
        first = make_card("Goblin one", SummonOtherGoblins(), owner=owner)
        second = make_card("Goblin two", SummonOtherGoblins(), owner=owner)
        champion = make_card(
            "Goblin champion",
            BuffFromGoblin(),
            owner=owner,
            hp=2,
            damage=3,
        )
        board = make_board()
        board.positions[:3] = [first, champion, second]

        board.recalculate()
        self.assertEqual((champion.dmg, champion.hp), (5, 4))
        board.recalculate()
        self.assertEqual((champion.dmg, champion.hp), (5, 4))


if __name__ == "__main__":
    unittest.main()
