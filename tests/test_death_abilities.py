import unittest
from types import SimpleNamespace

from cards.ability.abilities import (
    HealDragon1,
    HitDragon2Dmg,
    NoAbility,
    SideWay2DmgOnDeath,
    WeakenDragon1Dmg,
)
from cards.card import Card
from cards.card_type import CardType
from cards.mana import ManaColor
from core.board import Board
from core.game_loop import battle_dragon


def make_card(owner, name, hp, ability, *, damage=0, card_type=CardType.PLAYER):
    return Card(
        owner=owner,
        name=name,
        color=ManaColor.GREEN,
        hp=hp,
        dmg=damage,
        ability=ability,
        type=card_type,
    )


class DeathAbilityTests(unittest.TestCase):
    class Display:
        dragon = None

        def display_dragon(self):
            pass

        def display_board(self):
            pass

        def display_dragon_vs_card(self):
            pass

        def display_battle_result(self):
            pass

    def test_chained_explosions_hit_dragon_only_at_its_current_slot(self):
        owner = SimpleNamespace(graveyard=[])
        board = Board()
        board.positions = [None] * 6
        first = make_card(owner, "First", 1, SideWay2DmgOnDeath())
        second = make_card(owner, "Second", 1, SideWay2DmgOnDeath())
        board.positions[2:4] = [first, second]
        board.dragon = SimpleNamespace(hp=5)
        board.dragon_position = 2

        board.remove_card(first)

        self.assertEqual(board.dragon.hp, 3)
        self.assertEqual(board.positions, [None] * 6)
        self.assertEqual(owner.graveyard, [first, second])

    def test_explosion_can_defeat_dragon_during_its_current_combat(self):
        owner = SimpleNamespace(graveyard=[], id=1)
        board = Board()
        explosive = make_card(owner, "Bomb", 1, SideWay2DmgOnDeath())
        dragon = make_card(
            None,
            "Dragon",
            2,
            NoAbility(),
            damage=1,
            card_type=CardType.DRAGON,
        )
        board.positions[0] = explosive
        board.dragons = [dragon]

        self.assertIs(battle_dragon(board, self.Display()), owner)
        self.assertIs(dragon.slain_by, owner)

    def test_surviving_dragon_returns_to_bottom_of_stack(self):
        board = Board()
        bottom = make_card(
            None, "Bottom", 5, NoAbility(), card_type=CardType.DRAGON
        )
        survivor = make_card(
            None, "Survivor", 5, NoAbility(), card_type=CardType.DRAGON
        )
        board.dragons = [bottom, survivor]

        self.assertIsNone(battle_dragon(board, self.Display()))
        self.assertEqual(board.dragons, [survivor, bottom])

    def test_reveal_damage_can_defeat_dragon_and_credit_its_card_owner(self):
        owner = SimpleNamespace(graveyard=[], id=1)
        board = Board()
        trigger = make_card(owner, "Dragon hunter", 1, HitDragon2Dmg())
        dragon = make_card(
            None,
            "Dragon",
            2,
            NoAbility(),
            card_type=CardType.DRAGON,
        )
        board.positions[3] = trigger
        board.dragons = [dragon]
        result_event = {}
        display = self.Display()
        display.display_battle_result = lambda: result_event.update(
            board.battle_event
        )

        self.assertIs(battle_dragon(board, display), owner)
        self.assertIs(dragon.slain_by, owner)
        self.assertEqual(dragon.hp, 0)
        self.assertIs(result_event["card"], trigger)
        self.assertEqual(result_event["slot"], 3)
        self.assertIs(result_event["point_for"], owner)

    def test_reveal_dispatch_stops_after_first_lethal_trigger(self):
        first_owner = SimpleNamespace(graveyard=[], id=1)
        second_owner = SimpleNamespace(graveyard=[], id=2)
        board = Board()
        board.positions[1] = make_card(
            first_owner, "First hunter", 1, HitDragon2Dmg()
        )
        board.positions[2] = make_card(
            second_owner, "Second hunter", 1, HitDragon2Dmg()
        )
        dragon = make_card(
            None,
            "Dragon",
            2,
            NoAbility(),
            card_type=CardType.DRAGON,
        )
        board.dragons = [dragon]

        self.assertIs(battle_dragon(board, self.Display()), first_owner)
        self.assertIs(dragon.slain_by, first_owner)
        self.assertEqual(dragon.hp, 0)

    def test_surviving_healer_restores_one_hp_when_dragon_advances(self):
        owner = SimpleNamespace(graveyard=[], id=1)
        board = Board()
        first = make_card(owner, "Guard", 1, NoAbility(), damage=1)
        healer = make_card(owner, "Dragon healer", 1, HealDragon1(), damage=1)
        dragon = make_card(
            None,
            "Dragon",
            2,
            NoAbility(),
            damage=1,
            card_type=CardType.DRAGON,
        )
        board.positions[:2] = [first, healer]
        board.dragons = [dragon]
        events = []
        display = self.Display()
        display.display_dragon_vs_card = lambda: events.append(
            dict(board.battle_event or {})
        )

        self.assertIsNone(battle_dragon(board, display))
        self.assertIn(first, owner.graveyard)
        self.assertIn(healer, owner.graveyard)
        heal_event = next(
            event
            for event in events
            if event.get("phase") == "dragon_move_ability"
            and event.get("card") is healer
        )
        self.assertEqual(heal_event["dragon_healing"], 1)
        self.assertEqual(heal_event["slot"], 0)
        self.assertEqual(heal_event["source_slot"], 1)

    def test_heal_dragon_stops_at_max_hp_without_moving_marker(self):
        owner = SimpleNamespace(graveyard=[], id=1)
        board = Board()
        healer = make_card(owner, "Dragon healer", 1, HealDragon1())
        dragon = make_card(
            None,
            "Dragon",
            2,
            NoAbility(),
            damage=1,
            card_type=CardType.DRAGON,
        )
        board.positions[4] = healer
        board.dragon = dragon
        board.dragon_position = 1

        healer.ability.apply_onDragonMove(healer, board, dragon)

        self.assertEqual(dragon.hp, 2)
        self.assertEqual(board.dragon_position, 1)
        self.assertEqual(board.battle_event["slot"], 1)
        self.assertEqual(board.battle_event["source_slot"], 4)
        self.assertEqual(board.battle_event["dragon_healing"], 0)

    def test_heal_dragon_repairs_an_existing_over_max_hp_value(self):
        owner = SimpleNamespace(graveyard=[], id=1)
        board = Board()
        healer = make_card(owner, "Dragon healer", 1, HealDragon1())
        dragon = make_card(
            None,
            "Dragon",
            5,
            NoAbility(),
            damage=1,
            card_type=CardType.DRAGON,
        )
        dragon.hp = 7
        board.positions[2] = healer
        board.dragon = dragon
        board.dragon_position = 0

        healer.ability.apply_onDragonMove(healer, board, dragon)

        self.assertEqual(dragon.hp, 5)
        self.assertEqual(board.battle_event["dragon_healing"], 0)

    def test_weaken_dragon_passive_is_recalculated_without_stacking(self):
        owner = SimpleNamespace(graveyard=[], id=1)
        board = Board()
        weakener = make_card(owner, "Dragon weakener", 2, WeakenDragon1Dmg())
        dragon = make_card(
            None,
            "Dragon",
            5,
            NoAbility(),
            damage=4,
            card_type=CardType.DRAGON,
        )
        board.positions[2] = weakener
        board.dragon = dragon
        board.dragon_base_dmg = dragon.dmg

        board.mana_pool[0].color = ManaColor.RED
        board.recalculate()
        self.assertEqual(dragon.dmg, 3)
        board.recalculate()
        self.assertEqual(dragon.dmg, 3)

        board.mana_pool[0].color = ManaColor.BLUE
        board.recalculate()
        self.assertEqual(dragon.dmg, 2)

        board.remove_card(weakener)
        self.assertEqual(dragon.dmg, 4)


if __name__ == "__main__":
    unittest.main()
