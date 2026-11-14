from cards.ability.ability_target   import AbilityTarget
from cards.ability.ability_id       import AbilityId
from cards.mana                     import ManaColor
from core.enums.battle_phase         import BattlePhase
from core.enums.card_death_type      import CardDeathType
import random
from typing                         import TYPE_CHECKING

if TYPE_CHECKING:
    from cards.card     import Card
    from core.board     import Board
    from core.player    import Player


def can_use_on_play(ability) -> bool:
    """Return whether this ability implements an on-play activation."""
    if ability is None:
        return False
    try:
        return type(ability).activate is not Ability.activate
    except AttributeError:
        return False


def is_goblin(card) -> bool:
    """Goblins are cards carrying the goblin-summon ability."""
    ability = getattr(card, "ability", None)
    return getattr(ability, "id", None) == AbilityId.GOBLIN_FILL


class Ability():
    def __init__(
        self,
        name,
        description,
        target_owner: AbilityTarget,
        id: AbilityId = 0,
        requires_target=False,
        requires_hand_card=False,
        additional_mana_colors=(),
        blocks_mana_effects=False,
        auto_activate_on_play=False,
        survives_round=False,
    ):
        self.name           = name  #TODO change primary key to id!
        self.id             = id    # Currently used only for neat 
        self.description    = description
        self.target_owner   = target_owner # must be of type AbilityTarget
        self.requires_target = requires_target
        self.requires_hand_card = requires_hand_card
        self.additional_mana_colors = frozenset(additional_mana_colors)
        self.blocks_mana_effects = blocks_mana_effects
        self.auto_activate_on_play = auto_activate_on_play
        self.survives_round = survives_round
    def activate(self, card:"Card", board:"Board", args=None):
        pass

    def apply_passive(self, card:"Card", board:"Board", args=None):
        pass

    def apply_onDeath(self, card:"Card", board:"Board", args=None):
        pass

    def apply_onDragonReveal(self, card:"Card", board:"Board", dragon:"Card"):
        pass

    def apply_onDragonMove(self, card:"Card", board:"Board", dragon:"Card"):
        pass

    def apply_onRoundEnd(self, card:"Card", board:"Board", args=None):
        pass

    def can_activate(self, card:"Card", board:"Board") -> bool:
        return True

    def can_enter(
        self,
        card:"Card",
        board:"Board",
        owner:"Player" = None,
    ) -> bool:
        return True

    def legal_hand_card_indices(self, card:"Card", board:"Board") -> list[int]:
        return []

    def legal_target_positions(self, card:"Card", board:"Board"):
        """Return custom targets, or None to use owner-based targeting."""
        return None

    def legal_placement_positions(
        self,
        card:"Card",
        board:"Board",
        owner:"Player" = None,
    ):
        return [
            index
            for index, occupant in enumerate(board.positions)
            if occupant is None
        ]

    def place_on_occupied_position(self, card:"Card", board:"Board", position:int):
        """Handle a legal occupied placement slot and return whether handled."""
        return False

    def after_staged(self, card:"Card", board:"Board", position:int):
        pass

class NoAbility(Ability):
    def __init__(self):
        super().__init__(
            name            = "no Ability",
            description     = "",
            id              = AbilityId.NOTHING,
            target_owner    = None,
        )


class BlackManaOn(Ability):
    def __init__(self):
        super().__init__(
            name="Black mana is also active",
            description=(
                "While this card is in play, all cards behave as though black "
                "mana were also active."
            ),
            id=AbilityId.BLACK_MANA_ON,
            target_owner=AbilityTarget.ANY,
            additional_mana_colors=(ManaColor.BLACK,),
        )

    def apply_passive(self, card, board, args=None):
        # Board.active_mana_colors applies this continuous board-wide effect
        # before color bonuses and other passive abilities are evaluated.
        pass


class BlueManaOn(Ability):
    def __init__(self):
        super().__init__(
            name="Blue mana is also active",
            description=(
                "While this card is in play, all cards behave as though blue "
                "mana were also active."
            ),
            id=AbilityId.BLUE_MANA_ON,
            target_owner=AbilityTarget.ANY,
            additional_mana_colors=(ManaColor.BLUE,),
        )

    def apply_passive(self, card, board, args=None):
        pass


class RedManaOn(Ability):
    def __init__(self):
        super().__init__(
            name="Red mana is also active",
            description=(
                "While this card is in play, all cards behave as though red "
                "mana were also active."
            ),
            id=AbilityId.RED_MANA_ON,
            target_owner=AbilityTarget.ANY,
            additional_mana_colors=(ManaColor.RED,),
        )

    def apply_passive(self, card, board, args=None):
        pass


class BlockManaEffects(Ability):
    def __init__(self):
        super().__init__(
            name="Block mana effects",
            description=(
                "While this card is in play, real and additionally activated "
                "mana colors have no effect."
            ),
            id=AbilityId.BLOCK_MANA_EFFECTS,
            target_owner=AbilityTarget.ANY,
            blocks_mana_effects=True,
        )

    def apply_passive(self, card, board, args=None):
        pass


class PlaceSecondBeside(Ability):
    """Optionally place another legal hand card beside this commander."""

    def __init__(self):
        super().__init__(
            name="Place second beside",
            description=(
                "When this enters play, you may place a second card "
                "beside it. You may have only one commander on the board."
            ),
            id=AbilityId.PLACE_SECOND_BESIDE,
            target_owner=AbilityTarget.ALLY,
            requires_target=True,
            requires_hand_card=True,
        )

    def can_enter(self, card, board, owner=None):
        owner = owner if owner is not None else card.owner
        return not any(
            occupant is not None
            and occupant.owner is owner
            and occupant.ability.id == self.id
            for occupant in board.positions
        )

    def legal_hand_card_indices(self, card, board):
        owner = getattr(card, "owner", None)
        if owner is None:
            return []
        adjacent = set(self._adjacent_positions(card, board))
        return [
            index
            for index, candidate in enumerate(owner.hand.cards)
            if board.can_stage_card(candidate, owner)
            and adjacent.intersection(
                board.legal_placement_positions(candidate, owner)
            )
        ]

    @staticmethod
    def _adjacent_positions(card, board):
        try:
            position = board.positions.index(card)
        except ValueError:
            return []
        return [
            adjacent
            for adjacent in (position - 1, position + 1)
            if 0 <= adjacent < len(board.positions)
        ]

    def legal_target_positions(self, card, board):
        legal = [
            adjacent for adjacent in self._adjacent_positions(card, board)
            if board.positions[adjacent] is None
        ]
        pending = getattr(self, "pending_hand_card", None)
        if pending is not None:
            allowed = set(board.legal_placement_positions(pending, card.owner))
            legal = [position for position in legal if position in allowed]
        return legal

    def can_activate(self, card, board):
        return bool(
            self.legal_hand_card_indices(card, board)
            and self.legal_target_positions(card, board)
        )

    def activate(self, card, board, args=None):
        if not isinstance(args, dict):
            return
        second_card = args.get("hand_card")
        target_pos = args.get("target_pos")
        owner = getattr(card, "owner", None)
        legal_indices = self.legal_hand_card_indices(card, board)
        legal_cards = [owner.hand.cards[index] for index in legal_indices] if owner else []
        if second_card not in legal_cards:
            raise ValueError("The second card must be a legal card in the owner's hand")
        if target_pos not in self.legal_target_positions(card, board):
            raise ValueError("The second card must be placed in an empty adjacent slot")
        owner.hand.cards.remove(second_card)
        second_card.owner = owner
        board.stage_card(second_card, target_pos, nested=True)
        self.pending_hand_card = None


class Replace(Ability):
    """Replace an allied board card and return that card to its owner's hand."""

    def __init__(self):
        super().__init__(
            name="Replace allied card",
            description=(
                "When this enters play, you may replace another allied card "
                "and return that card to your hand."
            ),
            id=AbilityId.REPLACE,
            target_owner=AbilityTarget.ALLY,
        )

    def legal_placement_positions(self, card, board, owner=None):
        owner = owner if owner is not None else getattr(card, "owner", None)
        return [
            index
            for index, candidate in enumerate(board.positions)
            if candidate is None or candidate.owner is owner
        ]

    def place_on_occupied_position(self, card, board, position):
        if position not in self.legal_placement_positions(
            card,
            board,
            getattr(card, "owner", None),
        ):
            raise ValueError("Replace must target another allied card")
        returned_card = board.positions[position]
        if returned_card is None:
            return False
        returned_card.restore()
        returned_card.owner = card.owner
        card.owner.hand.cards.append(returned_card)
        board.positions[position] = card
        return True

class FrontPlus1Attack(Ability):
    def __init__(self):
        super().__init__(
            name            = "Front +1 Attack",
            description     = "Gives +1 attack to all friendly cards in front.",
            id              = AbilityId.PLUS_1_DMG_FRONT,
            target_owner    = AbilityTarget.ALLY,
        )
    def apply_passive(self, card, board, args=None):
        original_pos = board.positions.index(card)
        seen = set()
        for i in range(0, original_pos):
            target = board.positions[i]
            if (
                target is not None
                and target.owner == card.owner
                and id(target) not in seen
            ):
                seen.add(id(target))
                target.dmg += 1

class SidewaysPlus1(Ability):
    def __init__(self):
        super().__init__(
            name="Sideways +1",
            description="Gives +1 attack and +1 hp to adjacent friendly cards.",
            id              = AbilityId.PLUS_1_1_SIDEWAYS,
            target_owner=AbilityTarget.ALLY,
        )
    def apply_passive(self, card, board, args=None):
        original_pos = board.positions.index(card)
        #apply left
        if (
            original_pos > 0
            and board.positions[original_pos - 1] != None
            and card.owner is board.positions[original_pos - 1].owner
        ):
            board.positions[original_pos - 1].dmg += 1
            board.positions[original_pos - 1].hp  += 1
        #apply right
        if (
            original_pos < 5 
            and board.positions[original_pos + 1] != None
            and card.owner is board.positions[original_pos + 1].owner 
        ):
            board.positions[original_pos + 1].dmg += 1
            board.positions[original_pos + 1].hp  += 1

class SidewaysMinus1(Ability):
    def __init__(self):
        super().__init__(
            name="Sideways -1",
            description="Gives -1 attack and -1 hp to adjacent cards. -2 on black mana",
            id              = AbilityId.MINUS_1_1_SIDEWAYS_2_2_ON_BLACK,
            target_owner=AbilityTarget.ANY,
        )
    def apply_passive(self, card, board, args=None):
        original_pos = board.positions.index(card)
        value = 2 if board.is_mana_active(ManaColor.BLACK) else 1

        for position in (original_pos - 1, original_pos + 1):
            if not 0 <= position < len(board.positions):
                continue
            target = board.positions[position]
            if target is None:
                continue
            board.apply_stat_reduction(
                target,
                damage=value,
                health=value,
                source=card,
            )



class GoFirst(Ability):
    def __init__(self):
        super().__init__(
            name="Go First",
            description="Moves this card to the first position.",
            id              = AbilityId.GO_FIRST,
            target_owner=AbilityTarget.ANY,
        )
    def activate(self, card, board, args=None):
        board.move_toward_front(card)



class GoBefore1(Ability):
    def __init__(self):
        super().__init__(
            name="Go Before 1",
            description="Moves this card before the previous card.",
            id              = AbilityId.SWAP_BEFORE,
            target_owner=AbilityTarget.ANY,
        )
    def activate(self, card, board, args=None):
        original_pos                            = board.positions.index(card)
        if original_pos != 0 and board.can_swap_positions(original_pos, original_pos - 1):
            board.swap_positions(original_pos, original_pos - 1)

class AttackFront(Ability):
    def __init__(self):
        super().__init__(
            name            = "Attack Next",
            description     = "Atacks card directly in front of him",
            id              = AbilityId.ATTACK_FRONT,
            target_owner    = AbilityTarget.ANY,
        )
    def activate(self, card, board, args=None):
        original_pos = board.positions.index(card)
        if original_pos != 0:
            target                                 = board.positions[ original_pos - 1 ]
            if target and target.hp <= card.dmg:
                target.hp = target.hp - card.dmg
                board.remove_card(target)

class SideWay2DmgOnDeath(Ability):
    def __init__(self):
        super().__init__(
            name            = "Explode on death",
            description     = "When hp goes bellow 0, direct neighbors take 2 dmg",
            id              = AbilityId.DMG_2_SIDEWAYS_ON_DEATH,
            target_owner    = AbilityTarget.ANY,
        )
    def apply_onDeath(self, card, board, args=None):
        original_pos = args["position"]
        neighbors = []
        if original_pos > 0:
            neighbors.append(board.positions[original_pos - 1])
        if original_pos < len(board.positions) - 1:
            neighbors.append(board.positions[original_pos + 1])

        # The dragon is only hit if he is before explosion
        if board.dragon is not None and board.dragon_position == original_pos-1:
            board.dragon.hp -= 2

        victims = [neighbor for neighbor in neighbors if neighbor and neighbor.hp <= 2]
        for victim in victims:
            if victim in board.positions:
                board.remove_card(victim)


class DragonFanaticDrawWin(Ability):
    def __init__(self):
        super().__init__(
            name="First dragon-eaten fanatic wins a draw",
            description=(
                "If the round would be a draw, the owner of the first Dragon "
                "Fanatic defeated directly in dragon combat wins the round."
            ),
            id=AbilityId.DRAGON_FANATIC_DRAW_WIN,
            target_owner=AbilityTarget.ANY,
        )

    def apply_onDeath(self, card, board, args=None):
        args = args or {}
        if args.get("cause") != CardDeathType.DRAGON_COMBAT:
            return
        board.claim_round_win(
            winner=card.owner,
            card=card,
            slot=args.get("position"),
            phase=BattlePhase.FANATIC_TIEBREAK,
            message=(
                "The dragon survived — Player "
                f"{getattr(card.owner, 'id', '?')} wins the draw because "
                "their Dragon Fanatic was defeated first"
            ),
        )


class ReturnByDeath(Ability):
    def __init__(self):
        super().__init__(
            name            = "Return on death",
            description     = "When this card dies, it returns to owners hand",
            id              = AbilityId.RETURN_BY_DEATH,
            target_owner    = AbilityTarget.ALLY,
        )
    def apply_onDeath(self, card, board, args=None):
        card.restore()
        card.owner.hand.cards.append(card)

class HitDragon2Dmg(Ability):
    def __init__(self):
        super().__init__(
            name            = "Hit entering dragon for 2 dmg",
            description     = "When dragon is revealed, he immediately suffers 2 dmg",
            id              = AbilityId.HIT_DRAGON_2_DMG,
            target_owner    = AbilityTarget.DRAGON,
        )
    def apply_onDragonReveal(self, card, board, dragon):
        dragon.hp -= 2
        dragon_name = str(getattr(dragon, "name", "Dragon"))
        slot = board.positions.index(card)
        defeated = dragon.hp <= 0
        if defeated:
            dragon.slain_by = card.owner
        board.battle_event = {
            "phase": BattlePhase.DRAGON_DEFEATED if defeated else BattlePhase.DRAGON_REVEAL_ABILITY,
            "card": card,
            "slot": -1,
            "dragon_damage": 2,
            "point_for": dragon.slain_by if defeated else None,
            "message": (
                f"{dragon_name} was defeated by {getattr(card, 'name', 'Card')} "
                f"— Player {getattr(card.owner, 'id', '?')} earns the point"
                if defeated
                else f"{getattr(card, 'name', 'Card')} hits {dragon_name} for 2 damage"
            ),
        }


class HitDragonBlueInfrontDmg(Ability):
    def __init__(self):
        super().__init__(
            name="Blue cards in front hit dragon",
            description=(
                "When a dragon enters play, it loses 1 hp for each blue card "
                "positioned before this card."
            ),
            id=AbilityId.HIT_DRAGON_BLUE_INFRONT_DMG,
            target_owner=AbilityTarget.DRAGON,
        )

    def apply_onDragonReveal(self, card, board, dragon):
        source_position = board.positions.index(card)
        seen = set()
        damage = 0
        for candidate in board.positions[:source_position]:
            if candidate is None or id(candidate) in seen:
                continue
            seen.add(id(candidate))
            if candidate.has_color(ManaColor.BLUE):
                damage += 1
        if damage <= 0:
            return
        dragon.hp -= damage
        defeated = dragon.hp <= 0
        if defeated:
            dragon.slain_by = card.owner
        dragon_name = str(getattr(dragon, "name", "Dragon"))
        board.battle_event = {
            "phase": BattlePhase.DRAGON_DEFEATED if defeated else BattlePhase.DRAGON_REVEAL_ABILITY,
            "card": card,
            "slot": -1,
            "source_slot": source_position,
            "dragon_damage": damage,
            "point_for": dragon.slain_by if defeated else None,
            "message": (
                f"{getattr(card, 'name', 'Card')} deals {damage} damage to "
                f"{dragon_name} from blue cards in front"
            ),
        }

class HealDragon1(Ability):
    def __init__(self):
        super().__init__(
            name            = "Heal dragon by 1",
            description     = "Heal dragon 1 hp after each round of combat",
            id              = AbilityId.HEAL_DRAGON_1_HP,
            target_owner    = AbilityTarget.DRAGON,
        )

    def apply_onDragonMove(self, card, board, dragon):
        initial = getattr(dragon, "init_args", None)
        max_hp = int(initial[5]) if isinstance(initial, (list, tuple)) and len(initial) > 5 else int(dragon.hp)
        previous_hp = int(dragon.hp)
        dragon.hp = min(max_hp, previous_hp + 1)
        healing = max(0, dragon.hp - previous_hp)
        board.battle_event = {
            "phase": BattlePhase.DRAGON_MOVE_ABILITY,
            "card": card,
            # Keep the dragon marker at its actual position. The source card
            # may be elsewhere on the board.
            "slot": board.dragon_position,
            "source_slot": board.positions.index(card),
            "dragon_healing": healing,
            "message": (
                f"{getattr(card, 'name', 'Card')} heals "
                f"{getattr(dragon, 'name', 'Dragon')} by 1"
                if healing
                else f"{getattr(dragon, 'name', 'Dragon')} is already at full health"
            ),
        }

class WeakenDragon1Dmg(Ability):
    def __init__(self):
        super().__init__(
            name            = "Decrease dragon attack",
            description     = "Decrease dragon damage by 1, or by 2 on blue mana, while this card is alive",
            id              = AbilityId.NERF_DRAGON_DMG,
            target_owner    = AbilityTarget.DRAGON,
        )

    def apply_passive(self, card, board, args=None):
        dragon = getattr(board, "dragon", None)
        if dragon is None:
            return
        reduction = 2 if board.is_mana_active(ManaColor.BLUE) else 1
        dragon.dmg = max(0, dragon.dmg - reduction)

class SummonOtherGoblins(Ability):
    def __init__(self):
        super().__init__(
            name            = "Fill board with goblins",
            description     = "Take all goblins from your deck and hand. Place as many as possible on game board left to right. Remaining goblins are discarded.",
            id              = AbilityId.GOBLIN_FILL,
            target_owner    = AbilityTarget.ALLY,
        )

    def can_activate(self, card, board):
        owner = getattr(card, "owner", None)
        return bool(
            owner is not None
            and any(
                is_goblin(candidate)
                for collection in (owner.deck.cards, owner.hand.cards)
                for candidate in collection
            )
            and any(position is None for position in board.positions)
        )

    def activate(self, card, board, args=None):
        owner = getattr(card, "owner", None)
        if owner is None:
            return

        goblins = []
        for cards in (owner.deck.cards, owner.hand.cards):
            goblins.extend(card for card in cards if is_goblin(card))
            cards[:] = [card for card in cards if not is_goblin(card)]

        empty_positions = [
            position
            for position, occupant in enumerate(board.positions)
            if occupant is None
        ]
        placed_count = min(len(goblins), len(empty_positions))
        for goblin, position in zip(goblins[:placed_count], empty_positions):
            goblin.owner = owner
            board.stage_card(goblin, position, nested=True)

        for goblin in goblins[placed_count:]:
            goblin.owner = owner
            owner.graveyard.append(goblin)

class BuffFromGoblin(Ability):
    def __init__(self):
        super().__init__(
            name            = "Get buff from goblins",
            description     = "Get +1/1 for each goblin on board.",
            id              = AbilityId.BOOST_FROM_GOBLIN_1_1,
            target_owner    = AbilityTarget.ANY,
        )

    def apply_passive(self, card, board, args=None):
        goblin_count = sum(1 for candidate in board.positions if is_goblin(candidate))
        card.dmg += goblin_count
        card.hp += goblin_count


class Plus1_1FromRed(Ability):
    def __init__(self):
        super().__init__(
            name="+1/+1 from red cards",
            description="Gets +1 attack and +1 hp for every other red card in play.",
            id=AbilityId.PLUS_1_1_FROM_RED,
            target_owner=AbilityTarget.ANY,
        )

    def apply_passive(self, card, board, args=None):
        other_red_cards = sum(
            1
            for candidate in board.positions
            if candidate is not None
            if candidate is not card and candidate.has_color(ManaColor.RED)
        )
        card.dmg += other_red_cards
        card.hp += other_red_cards


class InvertReductions(Ability):
    """Marks this card so attack/health reductions strengthen it instead."""

    def __init__(self):
        super().__init__(
            name="Invert reductions",
            description="Attack and health reductions increase those stats instead.",
            id=AbilityId.INVERT_REDUCTIONS,
            target_owner=AbilityTarget.ANY,
        )
        self.inverts_stat_reductions = True

    def apply_passive(self, card, board, args=None):
        pass


class InvertBoardOnPlay(Ability):
    def __init__(self):
        super().__init__(
            name="Reverse the row",
            description="When this enters play, reverse the entire row.",
            id=AbilityId.INVERT_BOARD_ON_PLAY,
            target_owner=AbilityTarget.ANY,
            auto_activate_on_play=True,
        )

    def activate(self, card, board, args=None):
        board.reverse_positions()


class EatHighestHp(Ability):
    def __init__(self):
        super().__init__(
            name="Eat the healthiest characters",
            description=(
                "When this enters play, eat every other character tied for "
                "the highest health in the row."
            ),
            id=AbilityId.EAT_HIGHEST_HP,
            target_owner=AbilityTarget.ANY,
            auto_activate_on_play=True,
        )

    def activate(self, card, board, args=None):
        candidates = [
            candidate for candidate in board.positions
            if candidate is not None and candidate is not card
        ]
        if not candidates:
            return
        highest = max(candidate.hp for candidate in candidates)
        for victim in [candidate for candidate in candidates if candidate.hp == highest]:
            if victim in board.positions:
                board.remove_card(victim, cause=CardDeathType.EATEN, source=card)


class SwapAndAttack(Ability):
    def __init__(self):
        super().__init__(
            name="Swap and attack",
            description=(
                "When this enters play, it may swap with an adjacent character, "
                "then attack the character in front."
            ),
            id=AbilityId.SWAP_AND_ATTACK,
            target_owner=AbilityTarget.ANY,
            requires_target=True,
        )

    def legal_target_positions(self, card, board):
        position = board.positions.index(card)
        return [
            target for target in (position - 1, position + 1)
            if 0 <= target < len(board.positions)
            and board.positions[target] is not None
            and board.can_swap_positions(position, target)
        ]

    def can_activate(self, card, board):
        return bool(self.legal_target_positions(card, board))

    def activate(self, card, board, args=None):
        target = args
        current = board.positions.index(card)
        if target not in self.legal_target_positions(card, board):
            raise ValueError("Swap target must be an adjacent character")
        board.swap_positions(current, target)
        front = board.positions.index(card) - 1
        if front >= 0:
            victim = board.positions[front]
            if victim is not None and victim is not card and victim.hp <= card.dmg:
                board.remove_card(victim, cause=CardDeathType.ABILITY_DAMAGE, source=card)


class SwapAndBuffSideways(SwapAndAttack):
    def __init__(self):
        Ability.__init__(
            self,
            name="Swap and support adjacent allies",
            description=(
                "When this enters play, it may swap with an adjacent character. "
                "Adjacent allies get +1/+1."
            ),
            id=AbilityId.SWAP_AND_BUFF_SIDEWAYS,
            target_owner=AbilityTarget.ANY,
            requires_target=True,
        )

    def activate(self, card, board, args=None):
        target = args
        current = board.positions.index(card)
        if target not in self.legal_target_positions(card, board):
            raise ValueError("Swap target must be an adjacent character")
        board.swap_positions(current, target)

    def apply_passive(self, card, board, args=None):
        position = board.positions.index(card)
        for target in (position - 1, position + 1):
            if 0 <= target < len(board.positions):
                ally = board.positions[target]
                if ally is not None and ally is not card and ally.owner is card.owner:
                    ally.dmg += 1
                    ally.hp += 1


class ChooseManaOn(Ability):
    COLOR_OPTIONS = (ManaColor.RED, ManaColor.BLACK, ManaColor.BLUE)

    def __init__(self):
        super().__init__(
            name="Choose an additional mana",
            description="Choose red, black, or blue mana when this enters play.",
            id=AbilityId.CHOOSE_MANA_ON,
            target_owner=AbilityTarget.ANY,
            requires_target=True,
            auto_activate_on_play=True,
        )
        self.option_labels = tuple(color.name.title() for color in self.COLOR_OPTIONS)

    def legal_target_positions(self, card, board):
        return list(range(len(self.COLOR_OPTIONS)))

    def activate(self, card, board, args=None):
        if args not in self.legal_target_positions(card, board):
            raise ValueError("Choose red, black, or blue mana")
        self.additional_mana_colors = frozenset((self.COLOR_OPTIONS[args],))

    def apply_passive(self, card, board, args=None):
        pass


class EatFront(Ability):
    def __init__(self):
        super().__init__(
            name="Eat the character in front",
            description="When this enters play, eat the character directly in front.",
            id=AbilityId.EAT_FRONT,
            target_owner=AbilityTarget.ANY,
            auto_activate_on_play=True,
        )

    def activate(self, card, board, args=None):
        position = board.positions.index(card)
        if position > 0:
            victim = board.positions[position - 1]
            if victim is not None and victim is not card:
                board.remove_card(victim, cause=CardDeathType.EATEN, source=card)


class OccupyTwo(Ability):
    def __init__(self):
        super().__init__(
            name="Occupies two spaces",
            description="This card occupies two adjacent board spaces.",
            id=AbilityId.OCCUPY_TWO,
            target_owner=AbilityTarget.ANY,
        )

    def legal_placement_positions(self, card, board, owner=None):
        return [
            position for position in range(len(board.positions) - 1)
            if board.positions[position] is None
            and board.positions[position + 1] is None
        ]

    def after_staged(self, card, board, position):
        board.positions[position + 1] = card

    def apply_onDeath(self, card, board, args=None):
        board.positions[:] = [
            None if occupant is card else occupant
            for occupant in board.positions
        ]


class Immovable(Ability):
    def __init__(self):
        super().__init__(
            name="Cannot be moved or overtaken",
            description="This ability is not implemented.",
            id=AbilityId.IMMUTABLE_POSITION,
            target_owner=AbilityTarget.ANY,
        )
    def apply_passive(self, card, board, args=None):
        raise NotImplementedError("Immovable ability is not implemented")


class ShuffleChosenSide(Ability):
    def __init__(self):
        super().__init__(
            name="Shuffle one side of the row",
            description=(
                "When this enters play, choose either player's characters and "
                "randomly redistribute them among their occupied positions."
            ),
            id=AbilityId.SHUFFLE_SIDE,
            target_owner=AbilityTarget.ANY,
            requires_target=True,
            auto_activate_on_play=True,
        )

    def legal_target_positions(self, card, board):
        return [
            position for position, candidate in enumerate(board.positions)
            if candidate is not None and candidate is not card
        ]

    def can_activate(self, card, board):
        return bool(self.legal_target_positions(card, board))

    def activate(self, card, board, args=None):
        if args not in self.legal_target_positions(card, board):
            raise ValueError("Choose a character belonging to the side to shuffle")
        owner = board.positions[args].owner
        positions = [
            index for index, candidate in enumerate(board.positions)
            if candidate is not None
            and candidate.owner is owner
        ]
        cards = [board.positions[index] for index in positions]
        random.shuffle(cards)
        for position, candidate in zip(positions, cards):
            board.positions[position] = candidate


class ReturnAlliesAtRoundEnd(Ability):
    def __init__(self):
        super().__init__(
            name="Return surviving allies",
            description=(
                "If this survives the round, return every surviving allied "
                "character from the board to its owner's hand."
            ),
            id=AbilityId.RETURN_ALLIES_ROUND_END,
            target_owner=AbilityTarget.ALLY,
        )

    def apply_onRoundEnd(self, card, board, args=None):
        owner = card.owner
        for ally in list(board.positions):
            if ally is None or ally.owner is not owner:
                continue
            board.positions[:] = [
                None if occupant is ally else occupant
                for occupant in board.positions
            ]
            ally.restore()
            ally.owner = owner
            if ally not in owner.hand.cards:
                owner.hand.cards.append(ally)


class StayOnBoard(Ability):
    def __init__(self):
        super().__init__(
            name="Stay on board",
            description="If this survives, it remains on the board next round.",
            id=AbilityId.STAY_ON_BOARD,
            target_owner=AbilityTarget.ALLY,
            survives_round=True,
        )

    def apply_passive(self, card, board, args=None):
        pass


class HealEaterDragon(Ability):
    def __init__(self):
        super().__init__(
            name="Heal the dragon that eats this",
            description="A dragon that defeats this card heals to full health.",
            id=AbilityId.HEAL_EATER_DRAGON,
            target_owner=AbilityTarget.DRAGON,
        )

    def apply_onDeath(self, card, board, args=None):
        args = args or {}
        dragon = args.get("source")
        if args.get("cause") != CardDeathType.DRAGON_COMBAT or dragon is None:
            return
        initial = getattr(dragon, "init_args", ())
        if len(initial) > 5:
            dragon.hp = int(initial[5])


class PlaceBlackBeside(PlaceSecondBeside):
    def __init__(self):
        Ability.__init__(
            self,
            name="Place a black character beside",
            description=(
                "When this enters play, you may place another black-border "
                "character from your hand beside it."
            ),
            id=AbilityId.PLACE_BLACK_BESIDE,
            target_owner=AbilityTarget.ALLY,
            requires_target=True,
            requires_hand_card=True,
        )

    def legal_hand_card_indices(self, card, board):
        owner = card.owner
        adjacent = set(self._adjacent_positions(card, board))
        return [
            index for index, candidate in enumerate(owner.hand.cards)
            if candidate.has_color(ManaColor.BLACK)
            and board.can_stage_card(candidate, owner)
            and adjacent.intersection(
                board.legal_placement_positions(candidate, owner)
            )
        ]


class ReturnDiscardOnDeath(Ability):
    def __init__(self):
        super().__init__(
            name="Return a discarded card",
            description="When this dies, return one card from your discard pile to hand.",
            id=AbilityId.RETURN_DISCARD,
            target_owner=AbilityTarget.ALLY,
        )

    def apply_onDeath(self, card, board, args=None):
        owner = card.owner
        candidates = list(owner.graveyard)
        if not candidates:
            return
        strategy = getattr(owner, "choice_strategy", None)
        returned = (
            strategy.get_choice_zone_card(
                candidates,
                zone="graveyard",
                board=board,
                source_card=card,
            )
            if strategy is not None
            else candidates[-1]
        )
        if returned not in owner.graveyard:
            raise ValueError("Selected card is no longer in the graveyard")
        owner.graveyard.remove(returned)
        returned.restore()
        returned.owner = owner
        owner.hand.cards.append(returned)


class AttackFrontOnDragonReveal(Ability):
    def __init__(self):
        super().__init__(
            name="Attack forward when the dragon appears",
            description=(
                "When a dragon appears, attack the character in front. If it "
                "dies, move forward and continue attacking."
            ),
            id=AbilityId.ATTACK_FRONT_ON_DRAGON,
            target_owner=AbilityTarget.DRAGON,
        )

    def apply_onDragonReveal(self, card, board, dragon):
        position = board.positions.index(card)
        if position <= 0:
            return
        while position > 0:
            victim = board.positions[position - 1]
            if victim is None:
                if not board.can_swap_positions(position, position - 1):
                    break
                board.swap_positions(position, position - 1)
                position -= 1
                continue
            if victim is card or card.dmg < victim.hp:
                break
            board.remove_card(victim, cause=CardDeathType.ABILITY_DAMAGE, source=card)
            if card not in board.positions:
                break
            current = board.positions.index(card)
            if not board.can_swap_positions(current, current - 1):
                break
            board.swap_positions(current, current - 1)
            position = current - 1


class Minus1AllBlack(Ability):
    def __init__(self):
        super().__init__(
            name="-1/-1 to all black cards",
            description="All black cards get -1 attack and -1 health.",
            id=AbilityId.MINUS_1_1_ALL_BLACK,
            target_owner=AbilityTarget.ANY,
        )

    def apply_passive(self, card, board, args=None):
        for target in list(board.positions):
            if target is None:
                continue
            if target.has_color(ManaColor.BLACK):
                board.apply_stat_reduction(
                    target,
                    damage=1,
                    health=1,
                    source=card,
                )


class ShootOneHp(Ability):
    def __init__(self):
        super().__init__(
            name="Shoot a one-health character",
            description="When this enters play, it may destroy any character with 1 health.",
            id=AbilityId.SHOOT_ONE_HP,
            target_owner=AbilityTarget.ANY,
            requires_target=True,
        )

    def legal_target_positions(self, card, board):
        return [
            position for position, candidate in enumerate(board.positions)
            if candidate is not None and candidate is not card and candidate.hp == 1
        ]

    def can_activate(self, card, board):
        return bool(self.legal_target_positions(card, board))

    def activate(self, card, board, args=None):
        if args not in self.legal_target_positions(card, board):
            raise ValueError("Target must be another character with exactly 1 health")
        board.remove_card(board.positions[args], cause=CardDeathType.ABILITY_DAMAGE, source=card)


class ResurrectStronger(Ability):
    def __init__(self):
        super().__init__(
            name="Return as a stronger vampire",
            description=(
                "The first time this dies outside dragon combat, return it to "
                "the same board position with +1/+1."
            ),
            id=AbilityId.RESURRECT_STRONGER,
            target_owner=AbilityTarget.ALLY,
        )

    def apply_onDeath(self, card, board, args=None):
        args = args or {}
        if args.get("cause") == CardDeathType.DRAGON_COMBAT or getattr(card, "_resurrected_once", False):
            return
        position = args.get("position")
        if position is None or board.positions[position] is not None:
            return
        if card in card.owner.graveyard:
            card.owner.graveyard.remove(card)
        card.restore()
        card.persistent_dmg_bonus = 1
        card.persistent_hp_bonus = 1
        card.dmg += 1
        card.hp += 1
        card._resurrected_once = True
        board.positions[position] = card


class SidewaysMinusResurrect(ResurrectStronger):
    def __init__(self):
        Ability.__init__(
            self,
            name="Weaken neighbors and return stronger",
            description=(
                "Adjacent characters get -1/-1. The first time this dies outside "
                "dragon combat, it returns with +1/+1."
            ),
            id=AbilityId.SIDEWAYS_MINUS_RESURRECT,
            target_owner=AbilityTarget.ANY,
        )

    def apply_passive(self, card, board, args=None):
        position = board.positions.index(card)
        for target_pos in (position - 1, position + 1):
            if not 0 <= target_pos < len(board.positions):
                continue
            target = board.positions[target_pos]
            if target is None or target is card:
                continue
            board.apply_stat_reduction(target, damage=1, health=1, source=card)


# Black dragon
class EatFirst(Ability):
    def __init__(self):
        super().__init__(
            name="Eat First",
            description="Removes the first card from the board.",
            id              = AbilityId.EAT_FIRST,
            target_owner=AbilityTarget.ANY,
        )
    def activate(self, card, board, args=None):
        victim = board.positions[0]
        if victim is not None:
            board.remove_card(victim, cause=CardDeathType.DRAGON_COMBAT, source=card)

# Red dragon
class HitAll1Dmg(Ability):
    def __init__(self):
        super().__init__(
            name="Burn All",
            description="Removes all cards with 1 or less HP.",
            id              = AbilityId.HIT_ALL_1_DMG,
            target_owner=AbilityTarget.ANY,
        )
    def activate(self, card, board, args=None):
        for i in range(0,6):
            if ( board.positions[i] != None ) and (board.positions[i] != card) and (board.positions[i].hp <= 1):
                board.remove_card(board.positions[i])

# Blue dragon
class InvertBoard(Ability):
    def __init__(self):
        super().__init__(
            name="Invert board",
            description="First card becomes last, last becomes first, etc..",
            id              = AbilityId.INVERT_BOARD,
            target_owner    = AbilityTarget.ANY,
        )
    def activate(self, card, board, args=None):
        board.positions.reverse()

