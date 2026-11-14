from dataclasses import dataclass

from cards.card             import Card
from cards.mana             import get_mana_pool_shuffled, Mana
from cards.ability.abilities import can_use_on_play
from core.enums.card_death_type import CardDeathType
from core.enums.battle_phase import BattlePhase
from core.enums.game_state  import GameState

# from os import  system
# clear = lambda: system('cls')


@dataclass(frozen=True)
class RoundWinClaim:
    """An ability-provided fallback winner when combat has no normal winner."""

    winner: object
    card: Card
    slot: int | None
    phase: BattlePhase
    message: str

    def battle_event(self):
        return {
            "phase": self.phase,
            "card": self.card,
            "slot": self.slot,
            "point_for": self.winner,
            "message": self.message,
        }


class Board:
    def __init__(self, dragons=None):
        self.positions  = [None,None,None,None,None,None,] # 6 mist na stole
        if dragons is None:
            # Keep database-backed dragon loading for native games, but import
            # it only when needed. Dedicated servers inject trusted read-only
            # dragon definitions and never need the writable DB utility.
            from cards.dragons import get_dragons
            dragons = get_dragons()
        self.dragons    = list(dragons) # [] with dragon instances
        self.mana_pool  = get_mana_pool_shuffled()
        self.winner         = None  # for pygame, #TODO move to display strategy pygame
        self.game_running   = True  # for pygame, #TODO move to display strategy pygame
        self.player_on_turn = None
        self.game_state = GameState.PREP
        self.dragon     = None # for pygame
        self.dragon_base_dmg = None
        self.dragon_position = None # current slot during a dragon battle
        self.round_win_claim = None
        self.round      = 0    # for pygame
        self.battle_event = None
        self._recalculating = False
        self._recalculate_requested = False
        self.pending_entry_cards = []

    def claim_round_win(self, *, winner, card, slot, phase: BattlePhase, message):
        """Record the first ability claim without overriding an earlier claim."""
        if self.round_win_claim is None:
            self.round_win_claim = RoundWinClaim(
                winner=winner,
                card=card,
                slot=slot,
                phase=phase,
                message=message,
            )

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
            card.dmg += int(getattr(card, "persistent_dmg_bonus", 0))
            card.hp += int(getattr(card, "persistent_hp_bonus", 0))
        #regenerate mana bonuses
            for color, bonus in card.mana_bonuses.items():
                if self.is_mana_active(color):
                    card.dmg += bonus[0]
                    card.hp  += bonus[1]

        #regenerate passive abilities
        for x in range(0,6):
            card = self.positions[x]
            if(card==None):
                continue
            card.ability.apply_passive(card,self)

    def get_card_count(self):
        count =0
        for card in self.positions:
            if(isinstance(card, Card)):
                count+=1
        return count

    def can_swap_positions(self, first, second):
        return (
            0 <= first < len(self.positions)
            and 0 <= second < len(self.positions)
        )

    def swap_positions(self, first, second):
        if not self.can_swap_positions(first, second):
            raise ValueError("These board positions cannot be swapped")
        self.positions[first], self.positions[second] = (
            self.positions[second], self.positions[first]
        )

    def reverse_positions(self):
        self.positions.reverse()

    def move_toward_front(self, card):
        current = self.positions.index(card)
        self.positions.insert(0, self.positions.pop(current))

    def apply_stat_reduction(self, target, *, damage=0, health=0, source=None):
        inverted = getattr(target.ability, "inverts_stat_reductions", False)
        direction = 1 if inverted else -1
        target.dmg = max(0, target.dmg + direction * int(damage))
        target.hp += direction * int(health)
        if target.hp < 1 and target in self.positions:
            self.remove_card(target, cause=CardDeathType.ABILITY_DAMAGE, source=source)
    def clear_round(self,player_1,player_2):
        for position, card in enumerate(self.positions):
            if card is None:
                continue
            if getattr(card.ability, "survives_round", False):
                continue
            graveyard = player_1.graveyard if card.owner == player_1 else player_2.graveyard
            if card not in graveyard:
                graveyard.append(card)
            self.positions[position] = None
    def stage_card(self, card: Card, pos: int, *, nested=False):
        """Put a selected card on the board before optional choices resolve."""
        if not card.ability.can_enter(card, self, card.owner):
            raise ValueError("This card cannot enter the board")
        if pos not in self.legal_placement_positions(card, card.owner):
            raise ValueError("This position is not legal for the selected card")
        if self.positions[pos] is None:
            self.positions[pos] = card
        elif not card.ability.place_on_occupied_position(card, self, pos):
            raise ValueError("This position is already occupied!")
        card.ability.after_staged(card, self, pos)
        if nested:
            if not hasattr(self, "pending_entry_cards"):
                self.pending_entry_cards = []
            self.pending_entry_cards.append((card, pos))
        self.recalculate()

    def legal_placement_positions(self, card: Card, owner=None) -> list[int]:
        """Return board slots where the selected card may initially be placed."""
        return list(card.ability.legal_placement_positions(card, self, owner))

    def can_stage_card(self, card: Card, owner=None) -> bool:
        """Return whether card-specific board limits permit normal placement."""
        return card.ability.can_enter(card, self, owner)

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
        if card in self.positions:
            self.resolve_staged_card(card, use_ability, target_pos)

    def remove_card(self,card:Card, *, cause: CardDeathType | None = None, source=None):
        if cause is not None:
            cause = CardDeathType(cause)
        card_pos = self.positions.index(card)
        self.positions[card_pos] = None
        if card not in card.owner.graveyard:
            card.owner.graveyard.append(card)
        card.ability.apply_onDeath(
            card,
            self,
            {"position": card_pos, "cause": cause, "source": source},
        )
        self.recalculate(False)

