import unittest
from types import SimpleNamespace

from cards.ability.abilities import (
    AttackFrontOnDragonReveal,
    BlueManaOn,
    ChooseManaOn,
    EatHighestHp,
    EatFront,
    HealEaterDragon,
    Immovable,
    InvertReductions,
    NoAbility,
    OccupyTwo,
    PlaceSecondBeside,
    PlaceBlackBeside,
    ResurrectStronger,
    ReturnAlliesAtRoundEnd,
    SideWay2DmgOnDeath,
    SidewaysMinus1,
    SidewaysMinusResurrect,
    ShootOneHp,
    ShuffleChosenSide,
    StayOnBoard,
    Minus1AllBlack,
)
from cards.card import Card
from cards.card_type import CardType
from cards.mana import Mana, ManaColor
from cards.power import Power
from core.board import Board
from core.game_loop import play_card
from utils.database_utils import DBUtil


def owner(player_id=1):
    return SimpleNamespace(
        id=player_id,
        hand=SimpleNamespace(cards=[]),
        deck=SimpleNamespace(cards=[]),
        graveyard=[],
    )


def card(
    name,
    ability=None,
    *,
    player=None,
    hp=2,
    damage=2,
    color=ManaColor.GREEN,
    secondary_color=None,
):
    return Card(
        owner=player,
        id=f"{name}_test",
        name=name,
        power=Power.NORMAL,
        color=color,
        hp=hp,
        dmg=damage,
        color_buf=(0, 0),
        secondary_color=secondary_color,
        ability=ability or NoAbility(),
        type=CardType.PLAYER,
    )


class CatalogueTests(unittest.TestCase):
    def test_all_supplied_cards_are_registered_and_loadable(self):
        expected = {
            "Johan_Johanit_1",
            "Giovanni_Luppino_1",
            "Alchymista_Berig_1",
            "Kulturni_trol_1",
            "Paseracka_Emilie_1",
            "Karavanik_Macromir_1",
            "Inkvizitor_Illbebad_1",
            "Gustav_Silak_1",
            "Erzika_1",
            "Don_Carlos_1",
            "Slon_1",
            "Silak_1",
            "Sasek_1",
            "Principal_1",
            "Hloupe_Lojzek_1",
            "Cikanka_modra_1",
            "Cikanka_cervena_1",
            "Don_Juan_1",
            "Goblini_saman_1",
            "Medved_1",
            "Inkvizitor_Elsenhorn_1",
            "Roderik_von_Gumpoldov_1",
            "Sieglinde_von_Gumpoldov_1",
            "Cikanka_cerna_1",
        }
        loaded = {item.id: item for item in DBUtil().get_all_player_cards()}
        self.assertTrue(expected.issubset(loaded))
        self.assertTrue(all(loaded[item].ability is not None for item in expected))

    def test_dual_color_card_receives_each_colors_independent_bonus(self):
        elephant = DBUtil().load_card("Slon_1")
        source = card("Blue source", BlueManaOn())
        board = Board(dragons=[])
        board.positions[0] = elephant
        board.positions[2] = source
        board.mana_pool = [Mana(ManaColor.RED)]

        board.recalculate()

        self.assertEqual((elephant.dmg, elephant.hp), (2, 4))

    def test_dual_color_card_applies_only_bonuses_for_active_mana(self):
        scenarios = (
            (ManaColor.RED, False, (2, 2)),
            (ManaColor.BLUE, False, (1, 4)),
            (ManaColor.RED, True, (2, 4)),
            (ManaColor.BLACK, False, (1, 2)),
        )
        for real_mana, add_blue, expected in scenarios:
            with self.subTest(real_mana=real_mana, add_blue=add_blue):
                elephant = DBUtil().load_card("Slon_1")
                board = Board(dragons=[])
                board.positions[0] = elephant
                if add_blue:
                    board.positions[2] = card("Blue source", BlueManaOn())
                board.mana_pool = [Mana(real_mana)]

                board.recalculate()

                self.assertEqual((elephant.dmg, elephant.hp), expected)


class BoardMechanicTests(unittest.TestCase):
    def test_reductions_strengthen_giovanni(self):
        first = owner(1)
        second = owner(2)
        giovanni = card("Giovanni", InvertReductions(), player=first, hp=1, damage=1)
        vampire = card("Vampire", SidewaysMinus1(), player=second, hp=2, damage=2)
        board = Board(dragons=[])
        board.positions[:2] = [giovanni, vampire]
        board.mana_pool = [Mana(ManaColor.RED)]

        board.recalculate()

        self.assertEqual((giovanni.dmg, giovanni.hp), (2, 2))

    def test_database_giovanni_inverts_sieglindes_neighbour_weakening(self):
        first = owner(1)
        second = owner(2)
        giovanni = DBUtil().load_card("Giovanni_Luppino_1")
        sieglinde = DBUtil().load_card("Sieglinde_von_Gumpoldov_1")
        giovanni.owner = first
        sieglinde.owner = second
        board = Board(dragons=[])
        board.mana_pool = [Mana(ManaColor.RED)]
        board.positions[:2] = [giovanni, sieglinde]

        board.recalculate()

        self.assertEqual((giovanni.dmg, giovanni.hp), (2, 2))

    def test_troll_eats_all_other_cards_tied_for_highest_health(self):
        player = owner()
        troll = card("Troll", EatHighestHp(), player=player, hp=3)
        low = card("Low", player=player, hp=2)
        high_a = card("High A", player=player, hp=4)
        high_b = card("High B", player=player, hp=4)
        board = Board(dragons=[])
        board.positions[:4] = [low, troll, high_a, high_b]

        troll.ability.activate(troll, board)

        self.assertIn(low, board.positions)
        self.assertNotIn(high_a, board.positions)
        self.assertNotIn(high_b, board.positions)

    def test_elephant_occupies_and_releases_two_slots(self):
        player = owner()
        elephant = card("Elephant", OccupyTwo(), player=player)
        board = Board(dragons=[])

        board.stage_card(elephant, 2)
        self.assertIs(board.positions[2], elephant)
        self.assertIs(board.positions[3], elephant)
        self.assertEqual(board.get_card_count(), 2)

        board.remove_card(elephant)
        self.assertNotIn(elephant, board.positions)
        self.assertEqual(player.graveyard, [elephant])

    def test_immovable_ability_is_explicitly_unsupported(self):
        player = owner()
        locked = card("Locked", Immovable(), player=player)
        board = Board(dragons=[])

        with self.assertRaisesRegex(NotImplementedError, "Immovable ability"):
            board.stage_card(locked, 1)

    def test_erzika_adds_the_selected_mana_color(self):
        player = owner()
        erzika = card("Erzika", ChooseManaOn(), player=player)
        red = card("Red", player=player, color=ManaColor.RED)
        red.color_buf = (1, 1)
        red.init_args[4] = (1, 1)
        board = Board(dragons=[])
        board.positions[:2] = [erzika, red]
        board.mana_pool = [Mana(ManaColor.BLACK)]

        erzika.ability.activate(erzika, board, 0)
        board.recalculate()

        self.assertIn(ManaColor.RED, board.active_mana_colors())
        self.assertEqual((red.dmg, red.hp), (3, 3))

    def test_multi_slot_card_references_can_split_when_swapped(self):
        player = owner()
        single = card("Single", player=player)
        elephant = card("Elephant", OccupyTwo(), player=player)
        board = Board(dragons=[])
        board.positions[:3] = [single, elephant, elephant]

        board.swap_positions(0, 1)

        self.assertEqual(board.positions[:3], [elephant, single, elephant])

    def test_principal_returns_all_surviving_allies(self):
        player = owner()
        principal = card("Principal", ReturnAlliesAtRoundEnd(), player=player)
        ally = card("Ally", player=player)
        enemy = card("Enemy", player=owner(2))
        board = Board(dragons=[])
        board.positions[:3] = [ally, enemy, principal]

        principal.ability.apply_onRoundEnd(principal, board)

        self.assertCountEqual(player.hand.cards, [ally, principal])
        self.assertIn(enemy, board.positions)

    def test_loyzek_survives_round_cleanup(self):
        first = owner(1)
        second = owner(2)
        loyzek = card("Loyzek", StayOnBoard(), player=first)
        other = card("Other", player=second)
        board = Board(dragons=[])
        board.positions[:2] = [loyzek, other]

        board.clear_round(first, second)

        self.assertIn(loyzek, board.positions)
        self.assertNotIn(other, board.positions)
        self.assertEqual(second.graveyard, [other])


class TriggerTests(unittest.TestCase):
    def test_don_juan_heals_only_the_dragon_that_defeats_him(self):
        player = owner()
        don = card("Don", HealEaterDragon(), player=player, hp=1)
        dragon = card("Dragon", player=owner(2), hp=5, damage=2)
        dragon.type = CardType.DRAGON
        dragon.hp = 2
        board = Board(dragons=[])
        board.positions[0] = don

        board.remove_card(don, cause="dragon_combat", source=dragon)

        self.assertEqual(dragon.hp, 5)

    def test_roderik_returns_once_outside_dragon_combat_and_keeps_bonus(self):
        player = owner()
        roderik = card("Roderik", ResurrectStronger(), player=player, hp=1, damage=2)
        board = Board(dragons=[])
        board.positions[2] = roderik

        board.remove_card(roderik, cause="ability_damage")
        self.assertIs(board.positions[2], roderik)
        self.assertEqual((roderik.dmg, roderik.hp), (3, 2))

        board.recalculate()
        self.assertEqual((roderik.dmg, roderik.hp), (3, 2))
        board.remove_card(roderik, cause="ability_damage")
        self.assertNotIn(roderik, board.positions)

    def test_illebead_gives_minus_one_minus_one_to_all_black_cards(self):
        first = owner(1)
        second = owner(2)
        illebead = card("Illeb", Minus1AllBlack(), player=first)
        allied_black = card(
            "Allied black",
            player=first,
            hp=3,
            damage=3,
            color=ManaColor.BLACK,
        )
        enemy_black = card(
            "Enemy black",
            player=second,
            hp=3,
            damage=3,
            color=ManaColor.BLACK,
        )
        dual_color = card(
            "Partly black",
            player=second,
            hp=3,
            damage=3,
            secondary_color=ManaColor.BLACK,
        )
        green = card("Green", player=second, hp=3, damage=3)
        board = Board(dragons=[])
        board.positions[:5] = [
            allied_black,
            illebead,
            enemy_black,
            dual_color,
            green,
        ]

        board.recalculate()

        self.assertEqual((allied_black.dmg, allied_black.hp), (2, 2))
        self.assertEqual((enemy_black.dmg, enemy_black.hp), (2, 2))
        self.assertEqual((dual_color.dmg, dual_color.hp), (2, 2))
        self.assertEqual((green.dmg, green.hp), (3, 3))

    def test_bear_moves_forward_through_every_card_it_can_defeat(self):
        player = owner(1)
        bear = card(
            "Bear",
            AttackFrontOnDragonReveal(),
            player=player,
            hp=2,
            damage=3,
        )
        victim_a = card("A", player=owner(2), hp=2)
        victim_b = card("B", player=owner(2), hp=3)
        survivor = card("C", player=owner(2), hp=4)
        dragon = card("Dragon", player=owner(2), hp=5)
        board = Board(dragons=[])
        board.positions[:4] = [survivor, victim_a, victim_b, bear]

        bear.ability.apply_onDragonReveal(bear, board, dragon)

        self.assertEqual(board.positions.index(bear), 1)
        self.assertIn(survivor, board.positions)
        self.assertNotIn(victim_a, board.positions)
        self.assertNotIn(victim_b, board.positions)

    def test_bear_stops_when_forward_movement_is_not_legal(self):
        player = owner(1)
        bear = card(
            "Bear",
            AttackFrontOnDragonReveal(),
            player=player,
            hp=2,
            damage=3,
        )
        dragon = card("Dragon", player=owner(2), hp=5)
        board = Board(dragons=[])
        board.positions[2] = bear
        board.can_swap_positions = lambda first, second: False

        bear.ability.apply_onDragonReveal(bear, board, dragon)

        self.assertIs(board.positions[2], bear)

    def test_bear_stops_when_defeated_by_victims_death_effect(self):
        first = owner(1)
        second = owner(2)
        bear = card(
            "Bear",
            AttackFrontOnDragonReveal(),
            player=first,
            hp=2,
            damage=3,
        )
        explosive = card(
            "Explosive",
            SideWay2DmgOnDeath(),
            player=second,
            hp=1,
        )
        dragon = card("Dragon", player=second, hp=5)
        board = Board(dragons=[])
        board.positions[:2] = [explosive, bear]

        bear.ability.apply_onDragonReveal(bear, board, dragon)

        self.assertNotIn(explosive, board.positions)
        self.assertNotIn(bear, board.positions)

    def test_goblin_shaman_only_offers_black_cards_that_fit_beside_it(self):
        player = owner()
        shaman = card("Shaman", PlaceBlackBeside(), player=player)
        black = card("Black", player=player, color=ManaColor.BLACK)
        blue = card("Blue", player=player, color=ManaColor.BLUE)
        player.hand.cards[:] = [black, blue]
        board = Board(dragons=[])
        board.positions[2] = shaman

        self.assertEqual(shaman.ability.legal_hand_card_indices(shaman, board), [0])
        shaman.ability.pending_hand_card = black
        shaman.ability.activate(
            shaman,
            board,
            {"hand_card": black, "target_pos": 1},
        )
        self.assertIs(board.positions[1], black)

    def test_elsenhorn_can_destroy_any_one_health_character(self):
        player = owner()
        elsenhorn = card("Elsenhorn", ShootOneHp(), player=player)
        victim = card("Victim", player=owner(2), hp=1)
        sturdy = card("Sturdy", player=owner(2), hp=2)
        board = Board(dragons=[])
        board.positions[:3] = [victim, sturdy, elsenhorn]

        self.assertEqual(elsenhorn.ability.legal_target_positions(elsenhorn, board), [0])
        elsenhorn.ability.activate(elsenhorn, board, 0)
        self.assertNotIn(victim, board.positions)
        self.assertIn(sturdy, board.positions)

    def test_sieglinde_weakens_neighbors_then_resurrects_once(self):
        player = owner()
        neighbor = card("Neighbor", player=owner(2), hp=2, damage=2)
        sieglinde = card(
            "Sieglinde",
            SidewaysMinusResurrect(),
            player=player,
            hp=1,
            damage=1,
        )
        board = Board(dragons=[])
        board.positions[:2] = [neighbor, sieglinde]
        board.mana_pool = [Mana(ManaColor.RED)]

        board.recalculate()
        self.assertEqual((neighbor.dmg, neighbor.hp), (1, 1))
        board.remove_card(sieglinde, cause="ability_damage")
        self.assertIn(sieglinde, board.positions)
        self.assertEqual((sieglinde.dmg, sieglinde.hp), (2, 2))

    def test_don_carlos_eats_the_character_directly_in_front(self):
        player = owner()
        victim = card("Victim", player=owner(2))
        carlos = card("Carlos", EatFront(), player=player)
        board = Board(dragons=[])
        board.positions[:2] = [victim, carlos]

        carlos.ability.activate(carlos, board)

        self.assertNotIn(victim, board.positions)


class SequentialEntryTests(unittest.TestCase):
    class Display:
        def display_board(self):
            pass

        def display_choice(self, card, position, use_ability, target):
            pass

    @staticmethod
    def _player(cards):
        result = owner(1)
        result.hand.cards[:] = cards
        result.card_plays = {}
        result.active_ability_uses = {}

        def record(card_value, used):
            card_id = card_value.id
            result.card_plays[card_id] = result.card_plays.get(card_id, 0) + 1
            if used:
                result.active_ability_uses[card_id] = (
                    result.active_ability_uses.get(card_id, 0) + 1
                )

        result.record_card_play = record
        return result

    def test_velitel_second_card_resolves_its_own_targeted_on_play_ability(self):
        commander = card("Commander", PlaceSecondBeside())
        shooter = card("Shooter", ShootOneHp())
        victim = card("Victim", player=owner(2), hp=1)
        player = self._player([commander, shooter])
        commander.owner = player
        shooter.owner = player
        board = Board(dragons=[])
        board.positions[0] = victim

        class Strategy:
            selected_card = None
            selected_position = None

            def get_choice_card(self):
                self.selected_card = player.hand.cards.pop(0)
                return self.selected_card

            def get_choice_pos(self):
                self.selected_position = 2
                return 2

            def get_choice_use_ability(self):
                return True

            def get_choice_ability_card(self):
                return player.hand.cards[0]

            def get_choice_ability_target(self):
                return 3 if self.selected_card is commander else 0

        strategy = Strategy()
        player.choice_strategy = strategy

        play_card(player, strategy, board, self.Display())

        self.assertNotIn(victim, board.positions)
        self.assertIs(board.positions[2], commander)
        self.assertIs(board.positions[3], shooter)
        self.assertEqual(player.card_plays[commander.id], 1)
        self.assertEqual(player.card_plays[shooter.id], 1)

    def test_automatic_targeted_ability_is_skipped_without_legal_targets(self):
        shuffler = card("Shuffler", ShuffleChosenSide())
        player = self._player([shuffler])
        shuffler.owner = player
        board = Board(dragons=[])

        class Strategy:
            selected_card = None
            selected_position = None

            def get_choice_card(self):
                self.selected_card = player.hand.cards.pop(0)
                return self.selected_card

            def get_choice_pos(self):
                self.selected_position = 2
                return 2

            def get_choice_ability_target(self):
                raise AssertionError("No target should be requested")

        strategy = Strategy()
        player.choice_strategy = strategy

        play_card(player, strategy, board, self.Display())

        self.assertIs(board.positions[2], shuffler)
        self.assertNotIn(shuffler.id, player.active_ability_uses)


if __name__ == "__main__":
    unittest.main()
