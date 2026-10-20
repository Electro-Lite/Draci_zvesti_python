from cards.ability.ability_target   import AbilityTarget
from cards.ability.ability_id       import AbilityId
from cards.mana                     import ManaColor
from typing                         import TYPE_CHECKING

if TYPE_CHECKING:
    from cards.card     import Card
    from core.board     import Board
    from core.player    import Player


def can_use_on_play(ability) -> bool:
    """Return whether placing this card offers an optional ability choice."""
    return bool(
        getattr(ability, "is_active", False)
        or getattr(ability, "is_onPlay", False)
    )


def is_goblin(card) -> bool:
    """Goblins are cards carrying the goblin-summon ability."""
    ability = getattr(card, "ability", None)
    return getattr(ability, "id", None) == AbilityId.GOBLIN_FILL


def is_commander(card) -> bool:
    """Commander cards share the PLACE_SECOND_BESIDE ability."""
    ability = getattr(card, "ability", None)
    return getattr(ability, "id", None) == AbilityId.PLACE_SECOND_BESIDE


class Ability():
    def __init__(
        self,
        name,
        description,
        target_owner: AbilityTarget,
        is_active=False,
        is_passive=False,
        is_onDragonReveal=False,
        is_onDragonMove=False,
        is_onDeath=False,
        is_onPlay=False,
        id: AbilityId = 0,
        requires_target=False,
        requires_hand_card=False,
        additional_mana_colors=(),
        blocks_mana_effects=False,
    ):
        self.name           = name  #TODO change primary key to id!
        self.id             = id    # Currently used only for neat 
        self.description    = description
        self.target_owner   = target_owner # must be of type AbilityTarget
        self.is_active      = is_active
        self.is_passive     = is_passive
        self.is_onDragonReveal      = is_onDragonReveal
        self.is_onDragonMove        = is_onDragonMove
        self.is_onDeath             = is_onDeath
        self.is_onPlay              = is_onPlay

        self.requires_target = requires_target
        self.requires_hand_card = requires_hand_card
        self.additional_mana_colors = frozenset(additional_mana_colors)
        self.blocks_mana_effects = blocks_mana_effects
        # ability type # vstup,smrt,passive
    def activate(self, card:"Card", board:"Board", args=None):
        raise NotImplementedError()

    def apply_passive(self, card:"Card", board:"Board", args=None):
        raise NotImplementedError()

    def apply_onDeath(self, card:"Card", board:"Board", args=None):
        raise NotImplementedError()

    def apply_onDragonMove(self, card:"Card", board:"Board", dragon:"Card"):
        raise NotImplementedError()

    def can_activate(self, card:"Card", board:"Board") -> bool:
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
        """Return custom initial placement slots, or None for empty slots."""
        return None

    def place_on_occupied_position(self, card:"Card", board:"Board", position:int):
        """Handle a legal occupied placement slot and return whether handled."""
        return False

class NoAbility(Ability):
    def __init__(self):
        super().__init__(
            name            = "no Ability",
            description     = "",
            id              = AbilityId.NOTHING,
            target_owner    = None,
            is_active       = False,
            is_passive      = False
        )
    def activate(self, card, board, args=None):
        pass


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
            is_passive=True,
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
            is_passive=True,
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
            is_passive=True,
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
            is_passive=True,
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
            is_onPlay=True,
            requires_target=True,
            requires_hand_card=True,
        )

    def legal_hand_card_indices(self, card, board):
        owner = getattr(card, "owner", None)
        if owner is None:
            return []
        return [
            index
            for index, candidate in enumerate(owner.hand.cards)
            if board.can_stage_card(candidate, owner)
        ]

    def legal_target_positions(self, card, board):
        try:
            position = board.positions.index(card)
        except ValueError:
            return []
        return [
            adjacent
            for adjacent in (position - 1, position + 1)
            if 0 <= adjacent < len(board.positions)
            and board.positions[adjacent] is None
        ]

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
        board.positions[target_pos] = second_card


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
            is_active       = False,
            is_passive      = True
        )
    def apply_passive(self, card, board, args=None):
        original_pos = board.positions.index(card)
        for i in range(0, original_pos):
            if (board.positions[i] != None) and (board.positions[i].owner == card.owner):
                board.positions[i].dmg += 1

class SidewaysPlus1(Ability):
    def __init__(self):
        super().__init__(
            name="Sideways +1",
            description="Gives +1 attack and +1 hp to adjacent friendly cards.",
            id              = AbilityId.PLUS_1_1_SIDEWAYS,
            target_owner=AbilityTarget.ALLY,
            is_passive=True
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
            is_passive=True
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
            target.dmg = max(0, target.dmg - value)
            target.hp -= value
            if target.hp < 1 and target in board.positions:
                board.remove_card(target)



class GoFirst(Ability):
    def __init__(self):
        super().__init__(
            name="Go First",
            description="Moves this card to the first position.",
            id              = AbilityId.GO_FIRST,
            target_owner=AbilityTarget.ANY,
            is_active=True,
        )
    def activate(self, card, board, args=None):
        tmp                             = board.positions[0]
        original_pos                    = board.positions.index(card)
        board.positions[ original_pos ] = tmp
        board.positions[0]              = card



class GoBefore1(Ability):
    def __init__(self):
        super().__init__(
            name="Go Before 1",
            description="Moves this card before the previous card.",
            id              = AbilityId.SWAP_BEFORE,
            target_owner=AbilityTarget.ANY,
            is_active=True,
        )
    def activate(self, card, board, args=None):
        original_pos                            = board.positions.index(card)
        if original_pos != 0:
            tmp                                 = board.positions[ original_pos - 1 ]
            board.positions[ original_pos ]     = tmp
            board.positions[ original_pos - 1 ] = card

class AttackFront(Ability):
    def __init__(self):
        super().__init__(
            name            = "Attack Next",
            description     = "Atacks card directly in front of him",
            id              = AbilityId.ATTACK_FRONT,
            target_owner    = AbilityTarget.ANY,
            is_active       = True,
            is_passive      = False
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
            is_onDeath      = True,
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

class ReturnByDeath(Ability):
    def __init__(self):
        super().__init__(
            name            = "Return on death",
            description     = "When this card dies, it returns to owners hand",
            id              = AbilityId.RETURN_BY_DEATH,
            target_owner    = AbilityTarget.ALLY,
            is_onDeath      = True,
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
            is_onDragonReveal      = True,
        )
    def apply_onDragonReveal(self, card, board, dragon):
        dragon.hp -= 2
        dragon_name = str(getattr(dragon, "name", "Dragon"))
        slot = board.positions.index(card)
        defeated = dragon.hp <= 0
        if defeated:
            dragon.slain_by = card.owner
        board.battle_event = {
            "phase": "dragon_defeated" if defeated else "dragon_reveal_ability",
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
            is_onDragonReveal=True,
        )

    def apply_onDragonReveal(self, card, board, dragon):
        source_position = board.positions.index(card)
        damage = sum(
            1
            for candidate in board.positions[:source_position]
            if candidate is not None and candidate.color == ManaColor.BLUE
        )
        if damage <= 0:
            return
        dragon.hp -= damage
        defeated = dragon.hp <= 0
        if defeated:
            dragon.slain_by = card.owner
        dragon_name = str(getattr(dragon, "name", "Dragon"))
        board.battle_event = {
            "phase": "dragon_defeated" if defeated else "dragon_reveal_ability",
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
            is_onDragonMove = True,
        )

    def apply_onDragonMove(self, card, board, dragon):
        initial = getattr(dragon, "init_args", None)
        max_hp = int(initial[5]) if isinstance(initial, (list, tuple)) and len(initial) > 5 else int(dragon.hp)
        previous_hp = int(dragon.hp)
        dragon.hp = min(max_hp, previous_hp + 1)
        healing = max(0, dragon.hp - previous_hp)
        board.battle_event = {
            "phase": "dragon_move_ability",
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
            is_passive      = True,
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
            is_onPlay       = True,
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
            board.positions[position] = goblin

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
            is_passive      = True,
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
            is_passive=True,
        )

    def apply_passive(self, card, board, args=None):
        other_red_cards = sum(
            1
            for candidate in board.positions
            if candidate is not None
            and candidate is not card
            and candidate.color == ManaColor.RED
        )
        card.dmg += other_red_cards
        card.hp += other_red_cards

# Black dragon
class EatFirst(Ability):
    def __init__(self):
        super().__init__(
            name="Eat First",
            description="Removes the first card from the board.",
            id              = AbilityId.EAT_FIRST,
            target_owner=AbilityTarget.ANY,
            is_active=True,
        )
    def activate(self, card, board, args=None):
        board.positions[0] = None

# Red dragon
class HitAll1Dmg(Ability):
    def __init__(self):
        super().__init__(
            name="Burn All",
            description="Removes all cards with 1 or less HP.",
            id              = AbilityId.HIT_ALL_1_DMG,
            target_owner=AbilityTarget.ANY,
            is_active=True,
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
            is_active       = True,
            is_passive      = False
        )
    def activate(self, card, board, args=None):
        board.positions.reverse()

