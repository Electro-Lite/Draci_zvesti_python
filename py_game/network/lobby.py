from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .protocol import APPLICATION_VERSION, MessageType, ProtocolMessage


@dataclass
class LobbyPlayer:
    name: str
    deck_id: str | None = None
    ready: bool = False
    deck_name: str | None = None


@dataclass
class LobbyState:
    host: LobbyPlayer
    guest: LobbyPlayer | None = None
    status: str = "waiting_for_player"
    error: str = ""

    def public_payload(self) -> dict:
        return {
            "host": vars(self.host).copy(),
            "guest": vars(self.guest).copy() if self.guest else None,
            "status": self.status,
            "error": self.error,
        }

    @property
    def can_start(self) -> bool:
        return bool(
            self.guest
            and self.host.deck_id
            and self.guest.deck_id
            and self.host.ready
            and self.guest.ready
        )


@dataclass
class HostLobbyController:
    host_name: str
    validate_deck: Callable[[str], bool]
    reconstruct_guest_deck: Callable[[dict], object] | None = None
    state: LobbyState = field(init=False)
    guest_deck: object | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.state = LobbyState(host=LobbyPlayer(self.host_name))

    def select_host_deck(self, deck_id: str) -> None:
        if not self.validate_deck(deck_id):
            raise ValueError("The selected host deck is invalid")
        self.state.host.deck_id = deck_id
        self.state.host.ready = False

    def set_host_ready(self, ready: bool) -> None:
        if ready and not self.state.host.deck_id:
            raise ValueError("Select a valid deck before becoming ready")
        self.state.host.ready = bool(ready)
        self._update_status()

    def handle(self, message: ProtocolMessage) -> tuple[MessageType, dict]:
        message_type = MessageType(message.type)
        payload = message.payload or {}
        if message_type == MessageType.HELLO:
            if (
                message.application_version != APPLICATION_VERSION
                or payload.get("application_version") != APPLICATION_VERSION
            ):
                raise ValueError("Application version mismatch")
            name = str(payload.get("player_name", "")).strip()
            if not name or len(name) > 24:
                raise ValueError("Guest name must contain 1-24 characters")
            self.state.guest = LobbyPlayer(name=name)
            self.guest_deck = None
            self.state.status = "configuring"
            return MessageType.HELLO_ACCEPTED, self.state.public_payload()
        if self.state.guest is None:
            raise ValueError("Guest must complete the handshake first")
        if message_type == MessageType.SELECT_DECK:
            self.state.guest.ready = False
            if self.reconstruct_guest_deck is not None:
                self.guest_deck = None
                self.state.guest.deck_id = None
                self.state.guest.deck_name = None
                reconstructed = self.reconstruct_guest_deck(payload.get("deck"))
                deck_id = str(getattr(reconstructed, "id", ""))
                deck_name = str(getattr(reconstructed, "name", ""))
                self.guest_deck = reconstructed
            else:
                # Compatibility path for non-network callers and older focused tests.
                deck_id = str(payload.get("deck_id", ""))
                if not self.validate_deck(deck_id):
                    raise ValueError("The selected guest deck is invalid")
                deck_name = None
            self.state.guest.deck_id = deck_id
            self.state.guest.deck_name = deck_name
        elif message_type == MessageType.READY:
            ready = payload.get("ready")
            if not isinstance(ready, bool):
                raise ValueError("Ready state must be a boolean")
            if ready and not self.state.guest.deck_id:
                raise ValueError("Guest must select a valid deck before becoming ready")
            self.state.guest.ready = ready
        elif message_type == MessageType.RETURN_TO_LOBBY:
            self.state.host.ready = False
            self.state.guest.ready = False
        elif message_type == MessageType.PING:
            return MessageType.PONG, {}
        elif message_type == MessageType.DISCONNECT:
            self.state.guest = None
            self.guest_deck = None
            self.state.status = "waiting_for_player"
        else:
            raise ValueError(f"Message {message_type.value} is not valid in the lobby")
        self._update_status()
        return MessageType.LOBBY_STATE, self.state.public_payload()

    def _update_status(self) -> None:
        self.state.status = "ready" if self.state.can_start else "configuring"
