from cards.ability.ability_target   import AbilityTarget
from cards.ability.ability_id       import AbilityId
from typing                         import TYPE_CHECKING

if TYPE_CHECKING:
    from cards.card     import Card
    from core.board     import Board
    from core.player    import Player


class Ability():
    def __init__(self, name, description, target_owner: AbilityTarget, is_active=True, is_passive=False, id:AbilityId = 0):
        self.name           = name  #TODO change primary key to id!
        self.id             = id    # Currently used only for neat 
        self.description    = description
        self.target_owner   = target_owner # must be of type AbilityTarget
        self.is_active      = is_active
        self.is_passive     = is_passive
        # ability type # vstup,smrt,passive
    def activate(self, card:"Card", board:"Board", args=None):
        raise NotImplementedError()

    def apply_passive(self, card:"Card", board:"Board", args=None):
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
            is_active=False,
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
            is_passive=False
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
            is_passive=False
        )
    def activate(self, card, board, args=None):
        original_pos                            = board.positions.index(card)
        if original_pos != 0:
            tmp                                 = board.positions[ original_pos - 1 ]
            board.positions[ original_pos ]     = tmp
            board.positions[ original_pos - 1 ] = card

# Black dragon
class EatFirst(Ability):
    def __init__(self):
        super().__init__(
            name="Eat First",
            description="Removes the first card from the board.",
            id              = AbilityId.EAT_FIRST,
            target_owner=AbilityTarget.ANY,
            is_active=True,
            is_passive=False
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
            is_passive=False
        )
    def activate(self, card, board, args=None):
        for i in range(0,6):
            if ( board.positions[i] != None ) and (board.positions[i].hp <= 1):
                board.positions[i] = None

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

# <### DEPRECATED ###> 
# Ability registry 
# abilities = {
#     "lucisnik": FrontPlus1Attack(),
#     "panos": SidewaysPlus1(),
#     "paladin": GoFirst(),
#     "strazny": GoFirst()
# }
# dragon_abilities = {
#     "cerny": EatFirst(),
#     "cerveny": BurnAll()
# }
