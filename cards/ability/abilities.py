from cards.ability.ability_target   import AbilityTarget
from cards.ability.ability_id       import AbilityId
from typing                         import TYPE_CHECKING

if TYPE_CHECKING:
    from cards.card     import Card
    from core.board     import Board
    from core.player    import Player


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
        id: AbilityId = 0,
        requires_target=False,
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

        self.requires_target = requires_target
        # ability type # vstup,smrt,passive
    def activate(self, card:"Card", board:"Board", args=None):
        raise NotImplementedError()

    def apply_passive(self, card:"Card", board:"Board", args=None):
        raise NotImplementedError()

    def apply_onDeath(self, card:"Card", board:"Board", args=None):
        raise NotImplementedError()

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

