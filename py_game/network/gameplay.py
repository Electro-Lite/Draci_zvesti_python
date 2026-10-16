from __future__ import annotations

import queue
import time
from typing import Callable
from uuid import uuid4

from cards.ability.ability_target import AbilityTarget
from choice_strategies.choice_strategy import PlayerChoiceStrategy
from display_strategies.display_strategy_none import DisplayStrategyNone
from py_game.battle_presentation import (
    wait_for_battle_confirmation,
    wait_for_battle_frame,
)

from .protocol import MessageType


def _enum_value(value):
    if value is None:
        return None
    return getattr(value, "name", str(value))


def serialize_card(card, local_player) -> dict | None:
    if card is None:
        return None
    ability = getattr(card, "ability", None)
    initial = getattr(card, "init_args", None)
    max_hp = initial[5] if isinstance(initial, list) and len(initial) > 5 else card.hp
    color_buf = getattr(card, "color_buf", None)
    mana_dmg = int(color_buf[0]) if isinstance(color_buf, (list, tuple)) and len(color_buf) > 0 else 0
    mana_hp = int(color_buf[1]) if isinstance(color_buf, (list, tuple)) and len(color_buf) > 1 else 0
    return {
        "id": str(card.id),
        "name": str(card.name),
        "hp": int(card.hp),
        "max_hp": max(1, int(max_hp)),
        "dmg": int(card.dmg),
        "color": _enum_value(card.color),
        "mana_bonus": {"dmg": mana_dmg, "hp": mana_hp},
        "power": _enum_value(card.power),
        "ability_name": str(getattr(ability, "name", "")),
        "ability_description": str(getattr(ability, "description", "")),
        "ability_active": bool(getattr(ability, "is_active", False)),
        "owner": "local" if getattr(card, "owner", None) is local_player else "opponent",
    }


def serialize_game_state(board, local_player, opponent, *, status: str = "playing") -> dict:
    """Return a guest-safe public state with no opponent hand or deck order."""
    mana = None
    if getattr(board, "mana_pool", None):
        mana = _enum_value(board.mana_pool[0].color)
    dragon = serialize_card(getattr(board, "dragon", None), local_player)
    raw_battle = getattr(board, "battle_event", None)
    battle = None
    if raw_battle:
        battle = {
            key: value
            for key, value in raw_battle.items()
            if key not in {"card", "point_for"}
        }
        battle["card"] = serialize_card(raw_battle.get("card"), local_player)
        point_for = raw_battle.get("point_for")
        battle["point_for"] = (
            "local"
            if point_for is local_player
            else "opponent"
            if point_for is opponent
            else None
        )
    return {
        "status": status,
        "round": int(getattr(board, "round", 0)),
        "game_state": _enum_value(getattr(board, "game_state", None)),
        "mana": mana,
        "turn": (
            "local"
            if getattr(board, "player_on_turn", None) is local_player
            else "opponent"
        ),
        "local": {
            "id": int(local_player.id),
            "score": int(local_player.score),
            "passed": bool(local_player.passed),
            "deck_count": len(local_player.deck.cards),
            "graveyard_count": len(local_player.graveyard),
            "hand": [serialize_card(card, local_player) for card in local_player.hand.cards],
        },
        "opponent": {
            "id": int(opponent.id),
            "score": int(opponent.score),
            "passed": bool(opponent.passed),
            "deck_count": len(opponent.deck.cards),
            "graveyard_count": len(opponent.graveyard),
            "hand_count": len(opponent.hand.cards),
        },
        "board": [serialize_card(card, local_player) for card in board.positions],
        "dragon": dragon,
        "battle": battle,
        "dragon_deck_count": len(getattr(board, "dragons", [])),
        "winner": (
            "local"
            if getattr(board, "winner", None) is local_player
            else "opponent"
            if getattr(board, "winner", None) is opponent
            else None
        ),
    }


class HostMatchChannel:
    def __init__(self, host, match_id: str, snapshot_provider: Callable[[], dict]):
        if not host.peer:
            raise ConnectionError("Guest is not connected")
        self.host = host
        self.peer = host.peer
        self.match_id = match_id
        self.snapshot_provider = snapshot_provider
        self._actions: queue.Queue = queue.Queue()
        self.disconnected = False
        self.error = ""

    def pump(self) -> None:
        for event in self.host.poll():
            if event.kind == "message" and event.message:
                message_type = MessageType(event.message.type)
                if message_type == MessageType.PLAYER_ACTION:
                    self._actions.put(event.message)
                elif message_type == MessageType.PING:
                    self.peer.send(MessageType.PONG, {}, match_id=self.match_id)
                elif message_type == MessageType.DISCONNECT:
                    self.disconnected = True
                    self.error = str((event.message.payload or {}).get("reason", "Guest disconnected"))
            elif event.kind in ("error", "protocol_error", "disconnected"):
                self.disconnected = True
                self.error = event.detail or "Guest disconnected"

    def send_snapshot(self) -> None:
        if not self.disconnected:
            self.peer.send(
                MessageType.STATE_SNAPSHOT,
                self.snapshot_provider(),
                match_id=self.match_id,
            )

    def request_action(self, choice_type: str, extra: dict | None = None, timeout=120.0):
        request_id = uuid4().hex
        payload = {
            "choice_type": choice_type,
            "state": self.snapshot_provider(),
        }
        payload.update(extra or {})
        self.peer.send(
            MessageType.CHOICE_REQUEST,
            payload,
            request_id=request_id,
            match_id=self.match_id,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump()
            if self.disconnected:
                raise SystemExit(self.error or "Guest disconnected")
            try:
                message = self._actions.get(timeout=0.03)
            except queue.Empty:
                continue
            if message.match_id != self.match_id or message.request_id != request_id:
                self.reject(message.request_id, "Action does not match the active request")
                continue
            return (message.payload or {}).get("value")
        raise TimeoutError("Guest did not respond before the action timeout")

    def reject(self, request_id: str | None, reason: str) -> None:
        self.peer.send(
            MessageType.ERROR,
            {"message": reason, "recoverable": True},
            request_id=request_id,
            match_id=self.match_id,
        )


class RemoteChoiceStrategy(PlayerChoiceStrategy):
    """Host-side strategy that accepts only validated guest intentions."""

    def __init__(self, player):
        super().__init__(player)
        self.channel: HostMatchChannel | None = None
        self.selected_card = None
        self.selected_position = None
        self._selected_card_index = None

    def _request_valid(self, choice_type, validator, extra=None):
        if self.channel is None:
            raise RuntimeError("Remote player has no LAN match channel")
        while True:
            value = self.channel.request_action(choice_type, extra)
            try:
                return validator(value)
            except (TypeError, ValueError) as error:
                self.channel.reject(None, str(error))

    def get_choice_pass(self) -> bool:
        hand = self.this_player.hand.cards

        def choose(value):
            if value == "pass":
                self._selected_card_index = None
                return True
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError("Play choice must be a hand index or pass")
            if not 0 <= value < len(hand):
                raise ValueError("Card index is outside the current hand")
            self._selected_card_index = value
            return False

        return self._request_valid(
            "play_or_pass",
            choose,
            {"legal_indices": list(range(len(hand)))},
        )

    def get_choice_card(self):
        hand = self.this_player.hand.cards

        if self._selected_card_index is not None:
            selected_index = self._selected_card_index
            self._selected_card_index = None
            self.selected_card = hand.pop(selected_index)
            return self.selected_card

        def select(value):
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError("Card choice must be a hand index")
            if not 0 <= value < len(hand):
                raise ValueError("Card index is outside the current hand")
            return hand.pop(value)

        self.selected_card = self._request_valid(
            "card",
            select,
            {"legal_indices": list(range(len(hand)))},
        )
        return self.selected_card

    def get_choice_pos(self) -> int:
        legal = [index for index, card in enumerate(self.info.game_board.positions) if card is None]

        def select(value):
            if not isinstance(value, int) or isinstance(value, bool) or value not in legal:
                raise ValueError("Board position is not currently legal")
            return value

        self.selected_position = self._request_valid(
            "position",
            select,
            {"legal_indices": legal},
        )
        return self.selected_position

    def get_choice_use_ability(self) -> bool:
        if self.selected_card is None or not self.selected_card.ability.is_active:
            return False
        if (
            getattr(self.selected_card.ability, "requires_target", False)
            and not self.legal_targets()
        ):
            return False
        return self._request_valid(
            "use_ability",
            lambda value: value if isinstance(value, bool) else _raise("Ability choice must be boolean"),
        )

    def legal_targets(self) -> list[int]:
        if self.selected_card is None:
            return []
        target_owner = getattr(self.selected_card.ability, "target_owner", AbilityTarget.ANY)
        if target_owner == AbilityTarget.DRAGON:
            return []
        legal = []
        for index, card in enumerate(self.info.game_board.positions):
            if index == self.selected_position:
                owner = self.this_player
            elif card is None:
                continue
            else:
                owner = card.owner
            if target_owner == AbilityTarget.ANY:
                legal.append(index)
            elif target_owner == AbilityTarget.ALLY and owner is self.this_player:
                legal.append(index)
            elif target_owner == AbilityTarget.ENEMY and owner is not self.this_player:
                legal.append(index)
        return legal

    def get_choice_ability_target(self) -> int:
        if self.selected_card is None:
            return 0
        if not self.selected_card.ability.is_active:
            return None
        if not getattr(self.selected_card.ability, "requires_target", False):
            return None
        legal = self.legal_targets()
        if not legal:
            return None

        def select(value):
            if not isinstance(value, int) or isinstance(value, bool) or value not in legal:
                raise ValueError("Ability target is not currently legal")
            return value

        return self._request_valid("target", select, {"legal_indices": legal})


def _raise(message):
    raise ValueError(message)


def network_display_strategy(
    channel: HostMatchChannel,
    battle_frame_seconds: float = 0.0,
    cancelled: Callable[[], bool] | None = None,
    continue_requested: Callable[[], bool] | None = None,
    reset_continue: Callable[[], None] | None = None,
):
    class NetworkDisplayStrategy(DisplayStrategyNone):
        def _publish(self):
            channel.send_snapshot()

        def _publish_battle(self):
            channel.send_snapshot()
            wait_for_battle_frame(battle_frame_seconds, cancelled)

        def _publish_battle_result(self):
            channel.send_snapshot()
            if continue_requested is None:
                wait_for_battle_frame(battle_frame_seconds, cancelled)
                return
            wait_for_battle_confirmation(continue_requested, cancelled)
            if reset_continue is not None:
                reset_continue()

        display_board = _publish
        display_mana = _publish
        display_dragon = _publish_battle
        display_battle_result = _publish_battle_result
        display_hand = _publish
        display_status = _publish

        def display_round(self, current_round):
            self._publish()

        def display_player_on_turn(self, player_on_turn):
            self._publish()

        def display_choice(self, card, position, use_ability, target):
            self._publish()

        def display_dragon_vs_card(self):
            self._publish_battle()

        def display_game_result(self, winner):
            self._publish()

    return NetworkDisplayStrategy
