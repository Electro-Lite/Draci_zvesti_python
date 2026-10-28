import unittest
import threading
import time
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
    ReturnDiscardOnDeath,
    ReturnAlliesAtRoundEnd,
    SidewaysMinus1,
    SidewaysMinusResurrect,
    ShootOneHp,
    StayOnBoard,
    SummonElsenhornBlockBlack,
)
from cards.card import Card
from cards.card_type import CardType
from cards.mana import Mana, ManaColor
from cards.power import Power
from core.board import Board
from core.game_loop import play_card
from choice_strategies.choice_strategy_human_pygame import (
    ChoiceType,
    PygameChoiceStrategy,
)
from py_game.network.gameplay import RemoteChoiceStrategy
from utils.database_utils import DBUtil


def owner(player_id=1):
    return SimpleNamespace(
        id=player_id,
        hand=SimpleNamespace(cards=[]),
        deck=SimpleNamespace(cards=[]),
        graveyard=[],
    )


def card(name, ability=None, *, player=None, hp=2, damage=2, color=ManaColor.GREEN):
    return Card(
        owner=player,
        id=f"{name}_test",
        name=name,
        power=Power.NORMAL,
        color=color,
        hp=hp,
        dmg=damage,
        color_buf=(0, 0),
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
            "Karetni_mistr_1",
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

    def test_immovable_card_splits_board_reversal(self):
        player = owner()
        a = card("A", player=player)
        locked = card("Locked", Immovable(), player=player)
        b = card("B", player=player)
        c = card("C", player=player)
        board = Board(dragons=[])
        board.positions[:4] = [a, locked, b, c]

        board.reverse_movable_positions()

        self.assertEqual(board.positions, [a, locked, None, None, c, b])

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

    def test_multi_slot_card_shifts_as_one_tile_when_swapped(self):
        player = owner()
        single = card("Single", player=player)
        elephant = card("Elephant", OccupyTwo(), player=player)
        board = Board(dragons=[])
        board.positions[:3] = [single, elephant, elephant]

        board.swap_positions(0, 1)

        self.assertEqual(board.positions[:3], [elephant, elephant, single])

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

    def test_illebead_summons_elsenhorn_and_blocks_black_effects(self):
        first = owner(1)
        second = owner(2)
        illebead = card("Illeb", SummonElsenhornBlockBlack(), player=first)
        elsenhorn = card("Inkvizitor Elsenhorn", player=first)
        black_debuffer = card(
            "Black debuffer",
            SidewaysMinus1(),
            player=second,
            color=ManaColor.BLACK,
        )
        target = card("Target", player=first, hp=2, damage=2)
        first.deck.cards.append(elsenhorn)
        board = Board(dragons=[])
        board.positions[0] = target
        board.positions[1] = black_debuffer
        board.positions[3] = illebead

        illebead.ability.activate(illebead, board, 2)
        board.recalculate()

        self.assertIs(board.positions[2], elsenhorn)
        self.assertEqual((target.dmg, target.hp), (2, 2))

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

    def test_card_master_offers_every_graveyard_card_including_itself(self):
        player = owner()
        old = card("Old", player=player)
        recent = card("Recent", player=player)
        master = card("Master", ReturnDiscardOnDeath(), player=player)
        player.graveyard[:] = [old, recent]
        offered = []

        class Strategy:
            def get_choice_zone_card(self, cards, **kwargs):
                offered.extend(cards)
                return old

        player.choice_strategy = Strategy()
        board = Board(dragons=[])
        board.positions[0] = master

        board.remove_card(master, cause="ability_damage")

        self.assertCountEqual(offered, [old, recent, master])
        self.assertIn(old, player.hand.cards)
        self.assertIn(recent, player.graveyard)
        self.assertIn(master, player.graveyard)

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

    def test_illebead_summoned_elsenhorn_resolves_its_shot(self):
        illebead = card("Illeb", SummonElsenhornBlockBlack())
        elsenhorn = card("Inkvizitor Elsenhorn", ShootOneHp())
        victim = card("Victim", player=owner(2), hp=1)
        player = self._player([illebead])
        illebead.owner = player
        elsenhorn.owner = player
        player.deck.cards.append(elsenhorn)
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

            def get_choice_ability_target(self):
                return 3 if self.selected_card is illebead else 0

        strategy = Strategy()
        player.choice_strategy = strategy

        play_card(player, strategy, board, self.Display())

        self.assertNotIn(victim, board.positions)
        self.assertIs(board.positions[3], elsenhorn)
        self.assertEqual(player.card_plays[elsenhorn.id], 1)


class ZoneChoiceTests(unittest.TestCase):
    def test_pygame_graveyard_choice_exposes_candidates_and_returns_selection(self):
        player = owner(1)
        strategy = PygameChoiceStrategy(player)
        player.choice_strategy = strategy
        first = card("First", player=player)
        second = card("Second", player=player)
        board = Board(dragons=[])
        result = []

        thread = threading.Thread(
            target=lambda: result.append(
                strategy.get_choice_zone_card(
                    [first, second],
                    zone="graveyard",
                    board=board,
                )
            )
        )
        thread.start()
        deadline = time.monotonic() + 1
        while strategy.waiting_for != ChoiceType.GRAVEYARD_CARD:
            if time.monotonic() > deadline:
                self.fail("Pygame strategy did not request a graveyard choice")
            time.sleep(0.001)

        self.assertIs(board.pending_choice_player, player)
        self.assertEqual(board.pending_zone_cards, [first, second])
        self.assertTrue(strategy.set_choice(ChoiceType.GRAVEYARD_CARD, second))
        thread.join(timeout=1)

        self.assertEqual(result, [second])
        self.assertIsNone(board.pending_choice_player)
        self.assertEqual(board.pending_zone_cards, [])

    def test_remote_graveyard_choice_sends_visible_candidates_and_validates_index(self):
        player = owner(1)
        strategy = RemoteChoiceStrategy(player)
        first = card("First", player=player)
        second = card("Second", player=player)

        class Channel:
            def request_action(self, choice_type, extra=None):
                self.choice_type = choice_type
                self.extra = extra
                return 1

            def reject(self, request_id, reason):
                raise AssertionError(reason)

        channel = Channel()
        strategy.channel = channel

        selected = strategy.get_choice_zone_card(
            [first, second],
            zone="graveyard",
            board=Board(dragons=[]),
        )

        self.assertIs(selected, second)
        self.assertEqual(channel.choice_type, "graveyard_card")
        self.assertEqual(channel.extra["legal_indices"], [0, 1])
        self.assertEqual(
            [item["name"] for item in channel.extra["cards"]],
            ["First", "Second"],
        )


if __name__ == "__main__":
    unittest.main()
