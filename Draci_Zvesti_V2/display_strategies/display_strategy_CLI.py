from . import display_strategy as interface
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cards.card import Card
    from core.board import Board
    from core.player import Player


# Display strategy is designed to display to 1 player.
class DisplayStrategyCLI(interface.DisplayStrategy):
    def __init__(self, _player: "Player", _opposing_player: "Player", _board: "Board"):
        self.this_player = _player
        self.opponent = _opposing_player
        self.board = _board
        self.dragon = None

    def _dragon_display_string(self, dragon):
        """Compact dragon summary used by several display methods."""
        dragon_str = ""
        dragon_str += str(dragon.name)
        dragon_str += " (HP: " + str(dragon.hp)
        dragon_str += " | DMG: " + str(dragon.dmg) + ")"
        return dragon_str

    def _card_display_string(self, card):
        """Compact card summary used by several display methods."""
        card_str = ""
        card_str += "[ Player_" + str(card.owner.id) + ": "
        card_str += str(card.dmg)
        card_str += " " + str(card.name) + " "
        card_str += str(card.hp) + " ]"
        return card_str

    def display_board(self):
        """Show board with indices and concise card summaries (player-facing)."""
        # Single-line compact board with indices
        string_print = "BOARD:\n"
        for i, card in enumerate(self.board.positions):
            string_print += "  [" + str(i) + "] "
            if card is None:
                string_print += "EMPTY\n"
            else:
                # Show owner, name and stats
                string_print += (
                    "Player_" + str(card.owner.id) + " - "
                    + str(card.name)
                    + " (DMG:"
                    + str(card.dmg)
                    + ", HP:"
                    + str(card.hp)
                    + ")\n"
                )
        print(string_print)

    def display_mana(self):
        """Player-facing mana display."""
        mana = self.board.mana_pool[0] if self.board.mana_pool else "UNKNOWN"
        string_print = "🌈 Mana this round: "
        string_print += str(mana)
        print(string_print)

    def display_dragon(self):
        """Announce dragon appearance."""
        dragon = self.dragon
        if not dragon:
            return
        string_print = "\n🐉 A dragon appears! "
        string_print += self._dragon_display_string(dragon)
        print(string_print)

    def display_dragon_vs_card(self):
        """
        Show a single dragon vs first non-empty board card line (compact).
        Intended to be called during each step of the battle to show current HP.
        """
        dragon = self.dragon
        if not dragon:
            return

        # find first non-empty card on board (battle target)
        card = None
        for card_tmp in self.board.positions:
            if card_tmp is not None:
                card = card_tmp
                break

        if card is None:
            # nothing to show
            return

        string_print = ""
        string_print += "⚔️  " + self._dragon_display_string(dragon)
        string_print += "  VS  "
        string_print += "Player_" + str(card.owner.id) + " - " + str(card.name)
        string_print += " (DMG:" + str(card.dmg) + ", HP:" + str(card.hp) + ")"
        print(string_print)

    def display_battle_result(self):
        """
        User-friendly battle result. If dragon was slain, show who killed it.
        """
        dragon = self.dragon
        if not dragon:
            return

        # find last non-empty card (the card that battled / killed the dragon)
        card = None
        for card_tmp in self.board.positions:
            if card_tmp is not None:
                card = card_tmp
                break

        string_print = "\n"
        if dragon.slain_by is not None:
            string_print += "🏆 Player_" + str(dragon.slain_by.id) + " slays the dragon and wins the round!\n"
            string_print += dragon.name + " was slain by " + (self._card_display_string(card) if card else "a card")
            print(string_print)
        else:
            # dragon survived
            string_print += "🔥 The dragon survives and returns to the lair: " + self._dragon_display_string(dragon)
            print(string_print)

    def display_hand(self):
        """Show player's hand in a readable, comma-separated list of names."""
        cards = self.this_player.hand.cards
        string_print = "HAND: [ "
        for card in cards:
            # prefer card.name if present
            name = getattr(card, "name", None)
            if name:
                string_print += str(name) + ", "
            else:
                string_print += str(card) + ", "
        string_print += " ]"
        print(string_print)

    def display_status(self):
        """Show compact status for both players (player-facing)."""
        cards_in_hand = len(self.this_player.hand.cards)
        cards_in_deck = len(self.this_player.deck.cards)
        score = self.this_player.score
        passed = self.this_player.passed

        opponent_cards_in_hand = len(self.opponent.hand.cards)
        opponent_cards_in_deck = len(self.opponent.deck.cards)
        opponent_score = self.opponent.score
        opponent_passed = self.opponent.passed

        string_print = ""
        string_print += "[ Player_" + str(self.this_player.id) + ": "
        string_print += "Hand " + str(cards_in_hand)
        string_print += " | Deck " + str(cards_in_deck)
        # show Passed only if True to avoid noise
        if passed:
            string_print += " | Passed"
        string_print += " | Score " + str(score) + " ] "

        string_print += "[ Opponent_" + str(self.opponent.id) + ": "
        string_print += "Hand " + str(opponent_cards_in_hand)
        string_print += " | Deck " + str(opponent_cards_in_deck)
        if opponent_passed:
            string_print += " | Passed"
        string_print += " | Score " + str(opponent_score) + " ]\n"

        print(string_print)

    def display_player_on_turn(self, player_on_turn: "Player"):
        string_print = "\n▶ Player on turn: Player_" + str(player_on_turn.id)
        print(string_print)

    def display_round(self, current_round):
        string_print = "\n\n===== ROUND " + str(current_round) + " ====="
        print(string_print)

    def display_game_result(self, winner: "Player"):
        print("\n\n====================")
        print("🏁  GAME OVER")
        self.display_status()
        if winner is None:
            print("# It's a DRAW #")
        else:
            print("🏆 WINNER: Player_" + str(winner.id) + " 🏆")
            print("Final Score: Player_" + str(self.this_player.id) + " = " + str(self.this_player.score)
                  + " | Player_" + str(self.opponent.id) + " = " + str(self.opponent.score))
        print("====================\n\n")

    def display_choice(self, card: "Card", position: int, use_ability: bool, target: int):
        """Narrative for a card placement (player-facing)."""
        player_id = str(card.owner.id)
        string_print = ""
        string_print += "▶ Player_" + player_id + " plays "
        string_print += str(card.name) + " (DMG:" + str(card.dmg) + ", HP:" + str(card.hp) + ")"
        string_print += " at position " + str(position)
        if getattr(card, "ability", None) and card.ability.is_active:
            string_print += " | Ability used: " + str(use_ability)
            string_print += " | Target: " + str(target)
        print(string_print)
