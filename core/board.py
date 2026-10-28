from cards.card             import Card
from cards.mana             import get_mana_pool_shuffled, Mana
from cards.ability.abilities import can_use_on_play, is_commander
from core.enums.game_state  import GameState

# from os import  system
# clear = lambda: system('cls')

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
        self.round      = 0    # for pygame
        self.battle_event = None
        self._recalculating = False
        self._recalculate_requested = False
        self.pending_entry_cards = []
        self.pending_choice_player = None
        self.pending_zone_cards = []
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
            if self.card_effects_blocked(card):
                continue
            colors.update(
                getattr(card.ability, "additional_mana_colors", ())
            )
        return frozenset(colors)

    def is_mana_active(self, color) -> bool:
        return color in self.active_mana_colors()

    def card_effects_blocked(self, card) -> bool:
        """Return whether another board card suppresses this card's effects."""
        for blocker in self.positions:
            if blocker is None or blocker is card:
                continue
            blocked_colors = getattr(
                getattr(blocker, "ability", None),
                "blocked_card_colors",
                (),
            )
            if any(getattr(card, "has_color", lambda value: card.color == value)(color)
                   for color in blocked_colors):
                return True
        return False

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
            if not self.card_effects_blocked(card):
                for color, bonus in card.mana_bonuses.items():
                    if self.is_mana_active(color):
                        card.dmg += bonus[0]
                        card.hp  += bonus[1]

        #regenerate passive abilities
        for x in range(0,6):
            card = self.positions[x]
            if(card==None):
                continue
            if card.ability.is_passive and not self.card_effects_blocked(card):
                card.ability.apply_passive(card,self)

    def get_card_count(self):
        count =0
        for card in self.positions:
            if(isinstance(card, Card)):
                count+=1
        return count

    def unique_cards(self):
        """Return board cards once even when a card occupies multiple slots."""
        result = []
        seen = set()
        for card in self.positions:
            if card is None or id(card) in seen:
                continue
            seen.add(id(card))
            result.append(card)
        return result

    def remove_from_board(self, card):
        """Remove every footprint slot for a card without resolving death."""
        for position, occupant in enumerate(self.positions):
            if occupant is card:
                self.positions[position] = None

    @staticmethod
    def _is_immovable(card):
        return bool(card and getattr(card.ability, "immovable", False))

    def can_swap_positions(self, first, second):
        if not (0 <= first < len(self.positions) and 0 <= second < len(self.positions)):
            return False
        if (
            self._is_immovable(self.positions[first])
            or self._is_immovable(self.positions[second])
        ):
            return False
        first_card = self.positions[first]
        second_card = self.positions[second]
        first_slots = (
            [first]
            if first_card is None
            else [i for i, item in enumerate(self.positions) if item is first_card]
        )
        second_slots = (
            [second]
            if second_card is None
            else [i for i, item in enumerate(self.positions) if item is second_card]
        )
        if len(first_slots) > 1 and len(second_slots) > 1:
            return False
        if len(first_slots) > 1 or len(second_slots) > 1:
            multi_slots = first_slots if len(first_slots) > 1 else second_slots
            single_position = second if len(first_slots) > 1 else first
            return (
                len(multi_slots) == 2
                and multi_slots[1] == multi_slots[0] + 1
                and single_position in (multi_slots[0] - 1, multi_slots[1] + 1)
            )
        return True

    def swap_positions(self, first, second):
        if not self.can_swap_positions(first, second):
            raise ValueError("An immovable character cannot move or be overtaken")
        first_card = self.positions[first]
        second_card = self.positions[second]
        first_slots = (
            [first]
            if first_card is None
            else [i for i, item in enumerate(self.positions) if item is first_card]
        )
        second_slots = (
            [second]
            if second_card is None
            else [i for i, item in enumerate(self.positions) if item is second_card]
        )
        if len(first_slots) > 1 or len(second_slots) > 1:
            multi_card, multi_slots, single_card, single_position = (
                (first_card, first_slots, second_card, second)
                if len(first_slots) > 1
                else (second_card, second_slots, first_card, first)
            )
            left, right = multi_slots
            if single_position == left - 1:
                self.positions[single_position] = multi_card
                self.positions[left] = multi_card
                self.positions[right] = single_card
            else:
                self.positions[left] = single_card
                self.positions[right] = multi_card
                self.positions[single_position] = multi_card
            return
        self.positions[first], self.positions[second] = (
            self.positions[second], self.positions[first]
        )

    def reverse_movable_positions(self):
        """Reverse each row segment without moving/overtaking locked cards."""
        segment_start = 0
        for position in range(len(self.positions) + 1):
            boundary = (
                position == len(self.positions)
                or self._is_immovable(self.positions[position])
            )
            if not boundary:
                continue
            self.positions[segment_start:position] = reversed(
                self.positions[segment_start:position]
            )
            segment_start = position + 1

    def move_toward_front(self, card):
        current = self.positions.index(card)
        locked_before = [
            index for index in range(current)
            if self._is_immovable(self.positions[index])
        ]
        destination = max(locked_before) + 1 if locked_before else 0
        self.positions.pop(current)
        self.positions.insert(destination, card)

    def apply_stat_reduction(self, target, *, damage=0, health=0, source=None):
        inverted = getattr(target.ability, "inverts_stat_reductions", False)
        direction = 1 if inverted else -1
        target.dmg = max(0, target.dmg + direction * int(damage))
        target.hp += direction * int(health)
        if target.hp < 1 and target in self.positions:
            self.remove_card(target, cause="ability_damage", source=source)
    def clear_round(self,player_1,player_2):
        handled = set()
        for x in range(0,6):
            card =self.positions[x]
            if card==None:
                continue
            if id(card) in handled:
                self.positions[x] = None
                continue
            handled.add(id(card))
            if getattr(card.ability, "survives_round", False):
                continue
            if card.owner==player_1:
                player_1.graveyard.append(card)
            else:
                player_2.graveyard.append(card)
            self.positions[x]=None
    def stage_card(self, card: Card, pos: int, *, nested=False):
        """Put a selected card on the board before optional choices resolve."""
        if not self.can_stage_card(card, card.owner):
            raise ValueError("A player may have only one commander on the board")
        if pos not in self.legal_placement_positions(card, card.owner):
            raise ValueError("This position is not legal for the selected card")
        if self.positions[pos] is None:
            self.positions[pos] = card
        elif not card.ability.place_on_occupied_position(card, self, pos):
            raise ValueError("This position is already occupied!")
        after_staged = getattr(card.ability, "after_staged", None)
        if after_staged is not None:
            after_staged(card, self, pos)
        if nested:
            if not hasattr(self, "pending_entry_cards"):
                self.pending_entry_cards = []
            self.pending_entry_cards.append((card, pos))
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
            and not self.card_effects_blocked(card)
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

    def remove_card(self,card:Card, *, cause=None, source=None):
        card_pos = self.positions.index(card)
        self.remove_from_board(card)
        if card not in card.owner.graveyard:
            card.owner.graveyard.append(card)
        if card.ability.is_onDeath and not self.card_effects_blocked(card):
            card.ability.apply_onDeath(
                card,
                self,
                {"position": card_pos, "cause": cause, "source": source},
            )
        self.recalculate(False)

