from cards.ability.ability_target import AbilityTarget

class Ability():
    def __init__(self, name, description, target_owner: AbilityTarget, is_active=True, is_passive=False):
        self.name = name
        self.description = description
        self.target_owner = target_owner # must be of type AbilityTarget
        self.is_active = is_active
        self.is_passive = is_passive
        # ability type # vstup,smrt,passive
    def activate(self, card, board, player_on_turn, args=None):
        raise NotImplementedError()

    def apply_passive(self, card, board, player_on_turn, args=None):
        raise NotImplementedError()


class FrontPlus1Attack(Ability):
    def __init__(self):
        super().__init__(
            name="Front +1 Attack",
            description="Gives +1 attack to all friendly cards in front.",
            target_owner=AbilityTarget.ALLY,
            is_active=False,
            is_passive=True
        )

class SidewaysPlus1(Ability):
    def __init__(self):
        super().__init__(
            name="Sideways +1",
            description="Gives +1 attack and +1 hp to adjacent friendly cards.",
            target_owner=AbilityTarget.ALLY,
            is_active=False,
            is_passive=True
        )

class GoFirst(Ability):
    def __init__(self):
        super().__init__(
            name="Go First",
            description="Moves this card to the first position.",
            target_owner=AbilityTarget.ANY,
            is_active=True,
            is_passive=False
        )

class GoBefore1(Ability):
    def __init__(self):
        super().__init__(
            name="Go Before 1",
            description="Moves this card before the previous card.",
            target_owner=AbilityTarget.ANY,
            is_active=True,
            is_passive=False
        )

class EatFirst(Ability):
    def __init__(self):
        super().__init__(
            name="Eat First",
            description="Removes the first card from the board.",
            target_owner=AbilityTarget.ANY,
            is_active=True,
            is_passive=False
        )

class BurnAll(Ability):
    def __init__(self):
        super().__init__(
            name="Burn All",
            description="Removes all cards with 1 or less HP.",
            target_owner=AbilityTarget.ANY,
            is_active=True,
            is_passive=False
        )

# Ability registry
abilities = {
    "lucisnik": FrontPlus1Attack(),
    "panos": SidewaysPlus1(),
    "paladin": GoFirst(),
    "strazny": GoFirst()
}
dragon_abilities = {
    "cerny": EatFirst(),
    "cerveny": BurnAll()
}
