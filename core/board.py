from cards.dragons          import get_dragons
from cards.card             import Card
from cards.mana             import get_mana_pool_shuffled, Mana
from cards.ability.abilities import can_use_on_play, is_commander
from core.enums.game_state  import GameState

# from os import  system
# clear = lambda: system('cls')

class Board:
    def __init__(self):
        self.positions  = [None,None,None,None,None,None,] # 6 mist na stole
        self.dragons    = get_dragons() # [] with dragon instances
        self.mana_pool  = get_mana_pool_shuffled()
        self.winner         = None  # for pygame, #TODO move to display strategy pygame
        self.game_running   = True  # for pygame, #TODO move to display strategy pygame
        self.player_on_turn = None
        self.game_state = GameState.PREP
        self.dragon     = None # for pygame
        self.dragon_base_dmg = None
        self.dragon_position = None # current slot during a dragon battle
        self.round      = 0    # for pygame
        self.battle_event = None
        self._recalculating = False
        self._recalculate_requested = False
    def cycle_mana(self):
        """Rotate the mana pool left by one"""
        if not self.mana_pool:
            return  

        first = self.mana_pool.pop(0)
        self.mana_pool.append(first)

    def active_mana_colors(self):
        """Return real mana plus continuous additional-mana board effects."""
        if any(
            card is not None
            and getattr(card.ability, "blocks_mana_effects", False)
            for card in self.positions
        ):
            return frozenset()
        colors = {self.mana_pool[0].color} if self.mana_pool else set()
        for card in self.positions:
            if card is None:
                continue
            colors.update(
                getattr(card.ability, "additional_mana_colors", ())
            )
        return frozenset(colors)

    def is_mana_active(self, color) -> bool:
        return color in self.active_mana_colors()

    def recalculate(self,do_display=False):
        # Passive effects may remove cards, and removal requests another
        # recalculation. Defer that request until the current pass finishes so
        # passives cannot recursively apply themselves to the same board.
        if getattr(self, "_recalculating", False):
            self._recalculate_requested = True
            return

        self._recalculating = True
        try:
            while True:
                self._recalculate_requested = False
                self._recalculate_once()
                if not self._recalculate_requested:
                    break
        finally:
            self._recalculating = False

    def _recalculate_once(self):
        # Dragon-targeting passives are rebuilt from a stable combat baseline,
        # just like player-card passives are rebuilt after card.restore().
        if self.dragon is not None and self.dragon_base_dmg is not None:
            self.dragon.dmg = self.dragon_base_dmg
        ### regenerate cards ###
        for x in range(0,6):
            card = self.positions[x]
            if(card==None):
                continue
            card.restore()
        #regenerate mana bonuses
            if self.is_mana_active(card.color):
                card.dmg += card.color_buf[0]
                card.hp  += card.color_buf[1]

        #regenerate passive abilities
        for x in range(0,6):
            card = self.positions[x]
            if(card==None):
                continue
            if(card.ability.is_passive):
                card.ability.apply_passive(card,self)

    def get_card_count(self):
        count =0
        for card in self.positions:
            if(isinstance(card, Card)):
                count+=1
        return count
    def clear_round(self,player_1,player_2):
        for x in range(0,6):
            card =self.positions[x]
            if card==None:
                continue
            if card.owner==player_1:
                player_1.graveyard.append(card)
            else:
                player_2.graveyard.append(card)
            self.positions[x]=None
    def stage_card(self, card: Card, pos: int):
        """Put a selected card on the board before optional choices resolve."""
        if not self.can_stage_card(card, card.owner):
            raise ValueError("A player may have only one commander on the board")
        if pos not in self.legal_placement_positions(card, card.owner):
            raise ValueError("This position is not legal for the selected card")
        if self.positions[pos] is None:
            self.positions[pos] = card
        elif not card.ability.place_on_occupied_position(card, self, pos):
            raise ValueError("This position is already occupied!")
        self.recalculate()

    def legal_placement_positions(self, card: Card, owner=None) -> list[int]:
        """Return board slots where the selected card may initially be placed."""
        custom_placement = getattr(
            card.ability,
            "legal_placement_positions",
            None,
        )
        custom = (
            custom_placement(card, self, owner)
            if custom_placement is not None
            else None
        )
        if custom is not None:
            return list(custom)
        return [
            index
            for index, occupant in enumerate(self.positions)
            if occupant is None
        ]

    def can_stage_card(self, card: Card, owner=None) -> bool:
        """Return whether card-specific board limits permit normal placement."""
        card_owner = owner if owner is not None else getattr(card, "owner", None)
        return not (
            is_commander(card)
            and any(
                is_commander(occupant) and occupant.owner is card_owner
                for occupant in self.positions
                if occupant is not None
            )
        )

    def resolve_staged_card(
        self,
        card: Card,
        use_ability: bool,
        target_pos=None,
    ):
        """Resolve an already visible card's optional active ability."""
        if card not in self.positions:
            raise ValueError("Card must be staged before its ability is resolved!")
        if (
            can_use_on_play(card.ability)
            and use_ability
            and card.ability.can_activate(card, self)
        ):
            card.ability.activate(card, self, target_pos)
        self.recalculate()

    def place_card(
        self,
        card: Card,
        pos: int,
        use_ability: bool,
        target_pos: int | None = None,
    ):
        """Compatibility helper for non-interactive callers."""
        self.stage_card(card, pos)
        self.resolve_staged_card(card, use_ability, target_pos)

    def remove_card(self,card:Card):
        card_pos = self.positions.index(card)
        self.positions[card_pos]=None
        card.owner.graveyard.append(card)
        if card.ability.is_onDeath:
            card.ability.apply_onDeath(card, self, {"position": card_pos})
        self.recalculate(False)

