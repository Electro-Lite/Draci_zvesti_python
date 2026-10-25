from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import hmac
import logging
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from config import Config
from cards.card import Card
from cards.card_type import CardType
from cards.mana import ManaColor
from cards.power import Power
import cards.ability.abilities as abilities_module

from .protocol import (
    APPLICATION_VERSION,
    FrameDecoder,
    MAX_MESSAGE_SIZE,
    MessageType,
    ProtocolError,
    ProtocolMessage,
    SequenceGuard,
    encode_message,
)


PASSWORD_ITERATIONS = 120_000
CARDS_DB_PATH = Path(__file__).resolve().parents[2] / "utils" / "cards.db"
LOGGER = logging.getLogger(__name__)
AUTHORITATIVE_DRAGON_IDS = (
    "dragon_blue_1",
    "dragon_red_1",
    "dragon_green_1",
    "dragon_black_1",
)


def load_authoritative_card(card_id: str):
    """Load trusted card definitions without opening the database for writes."""
    connection = sqlite3.connect(f"file:{CARDS_DB_PATH}?mode=ro", uri=True)
    try:
        row = connection.execute(
            """
            SELECT owner, id, name, power, color, hp, dmg, color_dmg_buff,
                   color_hp_buff, ability, image, type
            FROM cards WHERE id = ?
            """,
            (card_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return Card(
        owner=row[0],
        id=row[1],
        name=row[2],
        power=Power(row[3]),
        color=ManaColor[row[4]],
        hp=int(row[5]),
        dmg=int(row[6]),
        color_buf=[int(row[7] or 0), int(row[8] or 0)],
        ability=getattr(abilities_module, row[9])(),
        image=row[10],
        type=CardType[row[11]],
    )


def load_authoritative_dragons():
    dragons = [load_authoritative_card(card_id) for card_id in AUTHORITATIVE_DRAGON_IDS]
    if any(dragon is None for dragon in dragons):
        raise RuntimeError("The authoritative dragon catalogue is incomplete")
    if any(dragon.type != CardType.DRAGON for dragon in dragons):
        raise RuntimeError("The authoritative dragon catalogue contains a non-dragon card")
    return dragons


@dataclass
class OnlineLobby:
    lobby_id: str
    name: str
    host_id: str
    host_name: str
    password_salt: bytes | None = None
    password_digest: bytes | None = None
    guest_id: str | None = None
    guest_name: str | None = None
    active_match: bool = False
    server_authoritative: bool = False
    host_deck: Any = None
    guest_deck: Any = None
    host_ready: bool = False
    guest_ready: bool = False

    @property
    def protected(self) -> bool:
        return self.password_digest is not None

    @property
    def open(self) -> bool:
        return self.guest_id is None

    def accepts_password(self, password: str) -> bool:
        if not self.protected:
            return True
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            self.password_salt,
            PASSWORD_ITERATIONS,
        )
        return hmac.compare_digest(candidate, self.password_digest)

    def listing(self) -> dict[str, Any]:
        return {
            "lobby_id": self.lobby_id,
            "name": self.name,
            "host_name": self.host_name,
            "protected": self.protected,
            "server_authoritative": self.server_authoritative,
        }

    def state(self, role: str) -> dict[str, Any]:
        return {
            **self.listing(),
            "role": role,
            "guest_name": self.guest_name,
        }

    def game_state(self) -> dict[str, Any]:
        return {
            "host": {
                "name": self.host_name,
                "deck_id": getattr(self.host_deck, "id", None),
                "deck_name": getattr(self.host_deck, "name", None),
                "ready": self.host_ready,
            },
            "guest": ({
                "name": self.guest_name,
                "deck_id": getattr(self.guest_deck, "id", None),
                "deck_name": getattr(self.guest_deck, "name", None),
                "ready": self.guest_ready,
            } if self.guest_id else None),
            "status": "ready" if self.can_start else "configuring",
            "server_authoritative": self.server_authoritative,
        }

    @property
    def can_start(self) -> bool:
        return bool(
            self.guest_id
            and self.host_deck is not None
            and self.guest_deck is not None
            and self.host_ready
            and self.guest_ready
            and not self.active_match
        )


class LobbyDirectory:
    """In-memory online lobby state, independent from sockets for testing."""

    def __init__(self, max_lobbies: int = 100):
        self.max_lobbies = max(1, int(max_lobbies))
        self.lobbies: dict[str, OnlineLobby] = {}

    def lobby_for(self, client_id: str) -> OnlineLobby | None:
        return next(
            (
                lobby
                for lobby in self.lobbies.values()
                if client_id in (lobby.host_id, lobby.guest_id)
            ),
            None,
        )

    def create(
        self,
        client_id: str,
        player_name: str,
        lobby_name: str,
        password: str = "",
        *,
        server_authoritative: bool = False,
    ) -> OnlineLobby:
        if self.lobby_for(client_id):
            raise ValueError("Leave the current lobby before creating another")
        if len(self.lobbies) >= self.max_lobbies:
            raise ValueError("The server has reached its lobby capacity")
        lobby_name = str(lobby_name).strip()
        if not 1 <= len(lobby_name) <= 40:
            raise ValueError("Lobby name must contain 1-40 characters")
        password = str(password)
        if len(password) > 64:
            raise ValueError("Lobby password cannot exceed 64 characters")
        salt = secrets.token_bytes(16) if password else None
        digest = (
            hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                PASSWORD_ITERATIONS,
            )
            if password
            else None
        )
        lobby = OnlineLobby(
            lobby_id=secrets.token_hex(5),
            name=lobby_name,
            host_id=client_id,
            host_name=player_name,
            password_salt=salt,
            password_digest=digest,
            server_authoritative=server_authoritative,
        )
        self.lobbies[lobby.lobby_id] = lobby
        return lobby

    def join(
        self,
        client_id: str,
        player_name: str,
        lobby_id: str,
        password: str = "",
    ) -> OnlineLobby:
        if self.lobby_for(client_id):
            raise ValueError("Leave the current lobby before joining another")
        lobby = self.lobbies.get(str(lobby_id))
        if lobby is None or not lobby.open:
            raise ValueError("That lobby is no longer available")
        if not lobby.accepts_password(str(password)):
            raise ValueError("Incorrect lobby password")
        lobby.guest_id = client_id
        lobby.guest_name = player_name
        return lobby

    def leave(self, client_id: str) -> tuple[OnlineLobby | None, str | None]:
        lobby = self.lobby_for(client_id)
        if lobby is None:
            return None, None
        if lobby.host_id == client_id:
            del self.lobbies[lobby.lobby_id]
            return lobby, "host"
        lobby.guest_id = None
        lobby.guest_name = None
        lobby.active_match = False
        lobby.guest_deck = None
        lobby.guest_ready = False
        return lobby, "guest"

    def open_lobbies(self) -> list[dict[str, Any]]:
        return [
            lobby.listing()
            for lobby in sorted(
                self.lobbies.values(),
                key=lambda item: (item.name.casefold(), item.lobby_id),
            )
            if lobby.open
        ]


class RelayConnection:
    def __init__(self, websocket: ServerConnection):
        self.websocket = websocket
        self.entry_path = getattr(getattr(websocket, "request", None), "path", "/game")
        self.client_id = secrets.token_hex(12)
        self.player_name = ""
        self.client_kind = "native"
        self.resume_token: str | None = None
        self.decoder = FrameDecoder()
        self.incoming_sequence = SequenceGuard()
        self.outgoing_sequence = 0
        self.write_lock = asyncio.Lock()

    async def send(
        self,
        message_type: MessageType | str,
        payload: dict | None = None,
        *,
        request_id: str | None = None,
        match_id: str | None = None,
    ) -> None:
        message = ProtocolMessage(
            type=(message_type.value if isinstance(message_type, MessageType) else message_type),
            sequence=self.outgoing_sequence,
            request_id=request_id,
            match_id=match_id,
            payload=payload,
        )
        self.outgoing_sequence += 1
        async with self.write_lock:
            await self.websocket.send(encode_message(message))

    async def close(self) -> None:
        try:
            await self.websocket.close()
        except ConnectionClosed:
            pass


class OnlineRelayServer:
    def __init__(
        self,
        *,
        max_clients: int = 200,
        max_lobbies: int = 100,
        disconnect_grace_seconds: float = 10.0,
    ):
        self.max_clients = max(2, int(max_clients))
        self.directory = LobbyDirectory(max_lobbies)
        self.clients: dict[str, RelayConnection] = {}
        self.matches = {}
        self.loop = None
        self.disconnect_grace_seconds = max(0.0, float(disconnect_grace_seconds))
        self.resume_tokens: dict[str, str] = {}
        self.client_tokens: dict[str, str] = {}
        self.disconnect_tasks: dict[str, asyncio.Task] = {}
        self.disconnect_notified: set[str] = set()

    def status_payload(self) -> dict[str, Any]:
        connected = len(self.clients)
        active_matches = sum(
            1 for lobby in self.directory.lobbies.values() if lobby.active_match
        )
        utilization = connected / self.max_clients
        return {
            "connected_players": connected,
            "max_players": self.max_clients,
            "open_lobbies": len(self.directory.open_lobbies()),
            "active_matches": active_matches,
            "load": (
                "high" if utilization >= 0.8 else "medium" if utilization >= 0.5 else "low"
            ),
        }

    async def _send_error(
        self,
        client: RelayConnection,
        message: str,
        request_id: str | None = None,
    ) -> None:
        await self._try_send(
            client,
            MessageType.ERROR,
            {"message": str(message), "recoverable": True},
            request_id=request_id,
        )

    @staticmethod
    async def _try_send(
        client: RelayConnection,
        message_type: MessageType | str,
        payload: dict | None = None,
        **metadata,
    ) -> bool:
        try:
            await client.send(message_type, payload, **metadata)
            return True
        except (ConnectionClosed, ConnectionError, OSError):
            return False

    async def _broadcast_directory(self) -> None:
        listing = {"lobbies": self.directory.open_lobbies()}
        status = self.status_payload()
        for client in tuple(self.clients.values()):
            if not client.player_name:
                continue
            try:
                await self._try_send(client, MessageType.LOBBY_LIST, listing)
                await self._try_send(client, MessageType.SERVER_STATUS, status)
            except RuntimeError:
                # A transport may already be closing while a broadcast snapshot
                # is being assembled. Its connection cleanup owns removal.
                continue

    async def _send_lobby_state(self, lobby: OnlineLobby) -> None:
        host = self.clients.get(lobby.host_id)
        guest = self.clients.get(lobby.guest_id or "")
        if host:
            await self._try_send(host, MessageType.ONLINE_LOBBY, lobby.state("host"))
        if guest:
            await self._try_send(guest, MessageType.ONLINE_LOBBY, lobby.state("guest"))

    async def _send_authoritative_state(
        self,
        lobby: OnlineLobby,
        *,
        accepted_client: RelayConnection | None = None,
        request_id: str | None = None,
    ) -> None:
        payload = lobby.game_state()
        if accepted_client is not None:
            await self._try_send(
                accepted_client,
                MessageType.HELLO_ACCEPTED,
                payload,
                request_id=request_id,
            )
        for client_id in (lobby.host_id, lobby.guest_id):
            client = self.clients.get(client_id or "")
            if client:
                await self._try_send(client, MessageType.LOBBY_STATE, payload)

    def _match_for_client(self, client_id: str):
        return next(
            (match for match in self.matches.values() if match.has_client(client_id)),
            None,
        )

    async def _match_completed(self, match, error) -> None:
        self.matches.pop(match.match_id, None)
        lobby = self.directory.lobby_for(match.host_id)
        if lobby:
            lobby.active_match = False
            lobby.host_ready = False
            lobby.guest_ready = False
            await self._send_authoritative_state(lobby)
        await self._broadcast_directory()

    def _forget_session(self, client_id: str) -> None:
        token = self.client_tokens.pop(client_id, None)
        if token:
            self.resume_tokens.pop(token, None)

    async def _notify_peer_connection(
        self,
        match,
        client_id: str,
        status: str,
    ) -> None:
        peer_id = match.peer_id(client_id)
        peer = self.clients.get(peer_id or "")
        if peer:
            await self._try_send(
                peer,
                MessageType.PEER_CONNECTION_STATUS,
                {
                    "status": status,
                    "reconnectable": status == "disconnected",
                    "grace_seconds": self.disconnect_grace_seconds,
                },
                match_id=match.match_id,
            )

    async def _disconnect_grace_elapsed(
        self,
        client: RelayConnection,
    ) -> None:
        client_id = client.client_id
        try:
            await asyncio.sleep(self.disconnect_grace_seconds)
            if client_id in self.clients:
                return
            match = self._match_for_client(client_id)
            if match:
                self.disconnect_notified.add(client_id)
                await self._notify_peer_connection(match, client_id, "disconnected")
                return
            await self._leave_lobby(client, "The other player disconnected")
            self._forget_session(client_id)
        finally:
            current = self.disconnect_tasks.get(client_id)
            if current is asyncio.current_task():
                self.disconnect_tasks.pop(client_id, None)

    async def _resume_browser_connection(
        self,
        client: RelayConnection,
        token: str,
        player_name: str,
        request_id: str | None,
    ) -> bool:
        client_id = self.resume_tokens.get(token)
        if not client_id or client_id in self.clients:
            return False
        lobby = self.directory.lobby_for(client_id)
        match = self._match_for_client(client_id)
        if lobby is None and match is None:
            self._forget_session(client_id)
            return False

        self.clients.pop(client.client_id, None)
        client.client_id = client_id
        client.player_name = player_name
        client.client_kind = "web"
        client.resume_token = token
        self.clients[client_id] = client
        task = self.disconnect_tasks.pop(client_id, None)
        if task:
            task.cancel()
        peer_was_notified = client_id in self.disconnect_notified
        self.disconnect_notified.discard(client_id)
        if match:
            match.replace_client(client_id, client)

        await client.send(
            MessageType.ONLINE_WELCOME,
            {
                "client_id": client_id,
                "resume_token": token,
                "resumed": True,
            },
            request_id=request_id,
        )
        await client.send(MessageType.SERVER_STATUS, self.status_payload())
        await client.send(
            MessageType.LOBBY_LIST,
            {"lobbies": self.directory.open_lobbies()},
        )
        if lobby:
            role = "host" if lobby.host_id == client_id else "guest"
            await client.send(
                MessageType.ONLINE_LOBBY,
                {**lobby.state(role), "resumed": True},
            )
            if lobby.server_authoritative:
                await self._send_authoritative_state(lobby)
        if match:
            await match.resume_client(client_id)
            if peer_was_notified:
                await self._notify_peer_connection(match, client_id, "connected")
        return True

    async def _start_authoritative_match(self, lobby: OnlineLobby) -> None:
        if not lobby.can_start:
            raise ValueError("Both players must select valid decks and become ready")
        host = self.clients.get(lobby.host_id)
        guest = self.clients.get(lobby.guest_id or "")
        if host is None or guest is None:
            raise ValueError("Both players must be connected")
        from py_game.network.authoritative import AuthoritativeMatch

        seed = secrets.randbits(31)
        match_id = uuid4().hex
        match = AuthoritativeMatch(
            loop=self.loop or asyncio.get_running_loop(),
            match_id=match_id,
            host_client=host,
            guest_client=guest,
            host_deck=copy.deepcopy(lobby.host_deck),
            guest_deck=copy.deepcopy(lobby.guest_deck),
            dragons=load_authoritative_dragons(),
            seed=seed,
            starting_player_id=1 + seed % 2,
            completed=self._match_completed,
        )
        self.matches[match_id] = match
        lobby.active_match = True
        await match.start()
        await self._broadcast_directory()

    async def _handle_authoritative_lobby_message(
        self,
        client: RelayConnection,
        lobby: OnlineLobby,
        message: ProtocolMessage,
    ) -> bool:
        message_type = MessageType(message.type)
        payload = message.payload or {}
        role = "host" if lobby.host_id == client.client_id else "guest"
        if message_type == MessageType.HELLO:
            if role != "guest":
                raise ValueError("Only the joining player completes the lobby handshake")
            await self._send_authoritative_state(
                lobby,
                accepted_client=client,
                request_id=message.request_id,
            )
            return True
        if message_type == MessageType.SELECT_DECK:
            from py_game.network.decks import reconstruct_remote_deck

            deck = reconstruct_remote_deck(
                payload.get("deck"),
                load_authoritative_card,
            )
            if role == "host":
                lobby.host_deck = deck
                lobby.host_ready = False
            else:
                lobby.guest_deck = deck
                lobby.guest_ready = False
            await self._send_authoritative_state(lobby)
            return True
        if message_type == MessageType.READY:
            ready = payload.get("ready")
            if not isinstance(ready, bool):
                raise ValueError("Ready state must be a boolean")
            selected = lobby.host_deck if role == "host" else lobby.guest_deck
            if ready and selected is None:
                raise ValueError("Select a valid deck before becoming ready")
            if role == "host":
                lobby.host_ready = ready
            else:
                lobby.guest_ready = ready
            await self._send_authoritative_state(lobby)
            return True
        if message_type == MessageType.START_MATCH:
            if role != "host":
                raise ValueError("Only the lobby host can start a match")
            await self._start_authoritative_match(lobby)
            return True
        if message_type == MessageType.PLAYER_ACTION:
            match = self._match_for_client(client.client_id)
            if match is None or message.match_id != match.match_id:
                raise ValueError("That match is no longer active")
            if not match.accept_action(
                client.client_id,
                message.request_id,
                payload.get("value"),
            ):
                raise ValueError("Action does not match the active request")
            return True
        if message_type == MessageType.RETURN_TO_LOBBY:
            return True
        if message_type == MessageType.DISCONNECT:
            match = self._match_for_client(client.client_id)
            if match:
                match.cancel(str(payload.get("reason", "Player left the match")))
            return True
        if message_type in {
            MessageType.HELLO_ACCEPTED,
            MessageType.LOBBY_STATE,
            MessageType.STATE_SNAPSHOT,
            MessageType.CHOICE_REQUEST,
            MessageType.MATCH_RESULT,
        }:
            raise ValueError("That message type is reserved for the authoritative server")
        return False

    async def _leave_lobby(self, client: RelayConnection, reason: str) -> None:
        match = self._match_for_client(client.client_id)
        if match:
            match.cancel(reason)
        lobby, role = self.directory.leave(client.client_id)
        if lobby is None:
            return
        if role == "host" and lobby.guest_id:
            guest = self.clients.get(lobby.guest_id)
            if guest:
                await self._try_send(
                    guest,
                    MessageType.ONLINE_LOBBY_CLOSED,
                    {"reason": reason},
                )
                await self._try_send(guest, MessageType.DISCONNECT, {"reason": reason})
        elif role == "guest":
            host = self.clients.get(lobby.host_id)
            if host:
                await self._try_send(host, MessageType.DISCONNECT, {"reason": reason})
                await self._send_lobby_state(lobby)
        await self._broadcast_directory()

    async def _relay(self, sender: RelayConnection, message: ProtocolMessage) -> None:
        lobby = self.directory.lobby_for(sender.client_id)
        if lobby is None or lobby.guest_id is None:
            await self._send_error(sender, "Join a complete lobby before sending match traffic")
            return
        target_id = (
            lobby.guest_id if sender.client_id == lobby.host_id else lobby.host_id
        )
        target = self.clients.get(target_id)
        if target is None:
            await self._send_error(sender, "The other player is no longer connected")
            return
        message_type = MessageType(message.type)
        if message_type == MessageType.START_MATCH:
            if sender.client_id != lobby.host_id:
                await self._send_error(sender, "Only the lobby host can start a match")
                return
            lobby.active_match = True
        elif message_type in (MessageType.MATCH_RESULT, MessageType.RETURN_TO_LOBBY):
            lobby.active_match = False
        await self._try_send(
            target,
            message.type,
            message.payload,
            request_id=message.request_id,
            match_id=message.match_id,
        )
        if message_type in (
            MessageType.START_MATCH,
            MessageType.MATCH_RESULT,
            MessageType.RETURN_TO_LOBBY,
        ):
            await self._broadcast_directory()

    async def _handle_message(
        self,
        client: RelayConnection,
        message: ProtocolMessage,
    ) -> None:
        message_type = MessageType(message.type)
        payload = message.payload or {}
        if message_type == MessageType.PING:
            await client.send(MessageType.PONG, payload)
            return
        if message_type == MessageType.PONG:
            return
        if message_type == MessageType.ONLINE_HELLO:
            name = str(payload.get("player_name", "")).strip()
            version = str(payload.get("application_version", ""))
            if version != APPLICATION_VERSION:
                raise ValueError("Application version mismatch")
            if not 1 <= len(name) <= 24:
                raise ValueError("Player name must contain 1-24 characters")
            client_kind = str(payload.get("client_kind", "native"))
            if client_kind not in {"native", "web"}:
                raise ValueError("Unsupported online client kind")
            if client_kind == "web" and not self._is_browser_entry_path(
                client.entry_path
            ):
                raise ValueError("Browser clients must use the protected browser endpoint")
            resume_token = str(payload.get("resume_token", ""))
            if client_kind == "web" and resume_token and await self._resume_browser_connection(
                client,
                resume_token,
                name,
                message.request_id,
            ):
                return
            client.player_name = name
            client.client_kind = client_kind
            if client_kind == "web":
                client.resume_token = secrets.token_urlsafe(32)
                self.resume_tokens[client.resume_token] = client.client_id
                self.client_tokens[client.client_id] = client.resume_token
            await client.send(
                MessageType.ONLINE_WELCOME,
                {
                    "client_id": client.client_id,
                    "resume_token": client.resume_token,
                    "resumed": False,
                },
                request_id=message.request_id,
            )
            await client.send(MessageType.SERVER_STATUS, self.status_payload())
            await client.send(
                MessageType.LOBBY_LIST,
                {"lobbies": self.directory.open_lobbies()},
            )
            return
        if not client.player_name:
            raise ValueError("Complete the online handshake first")
        if message_type in {
            MessageType.ONLINE_WELCOME,
            MessageType.LOBBY_LIST,
            MessageType.ONLINE_LOBBY,
            MessageType.ONLINE_LOBBY_CLOSED,
            MessageType.SERVER_STATUS,
            MessageType.PEER_CONNECTION_STATUS,
        }:
            raise ValueError("That message type is reserved for the server")
        if message_type == MessageType.LIST_LOBBIES:
            await client.send(
                MessageType.LOBBY_LIST,
                {"lobbies": self.directory.open_lobbies()},
                request_id=message.request_id,
            )
        elif message_type == MessageType.CREATE_ONLINE_LOBBY:
            lobby = self.directory.create(
                client.client_id,
                client.player_name,
                payload.get("name", ""),
                payload.get("password", ""),
                server_authoritative=client.client_kind == "web",
            )
            await self._send_lobby_state(lobby)
            await self._broadcast_directory()
        elif message_type == MessageType.JOIN_ONLINE_LOBBY:
            lobby = self.directory.join(
                client.client_id,
                client.player_name,
                payload.get("lobby_id", ""),
                payload.get("password", ""),
            )
            await self._send_lobby_state(lobby)
            await self._broadcast_directory()
        elif message_type == MessageType.LEAVE_ONLINE_LOBBY:
            await self._leave_lobby(client, "The other player left the lobby")
            await client.send(MessageType.LOBBY_LIST, {"lobbies": self.directory.open_lobbies()})
        else:
            lobby = self.directory.lobby_for(client.client_id)
            if (
                lobby is not None
                and lobby.server_authoritative
                and await self._handle_authoritative_lobby_message(
                    client,
                    lobby,
                    message,
                )
            ):
                return
            await self._relay(client, message)

    @staticmethod
    def _is_browser_entry_path(path: str) -> bool:
        return str(path).split("?", 1)[0].rstrip("/") == "/browser-game"

    async def handle_connection(
        self,
        websocket: ServerConnection,
    ) -> None:
        client = RelayConnection(websocket)
        if len(self.clients) >= self.max_clients:
            await client.send(MessageType.ERROR, {"message": "Server is full"})
            await client.close()
            return
        self.clients[client.client_id] = client
        try:
            async for data in websocket:
                if isinstance(data, str):
                    raise ProtocolError("Online messages must use binary WebSocket frames")
                for message in client.decoder.feed(data):
                    if not client.incoming_sequence.accept(message.sequence):
                        raise ProtocolError("Duplicate or out-of-order sequence")
                    try:
                        await self._handle_message(client, message)
                    except ValueError as error:
                        await self._send_error(client, str(error), message.request_id)
                    except Exception:
                        LOGGER.exception(
                            "Online message handling failed for %s",
                            message.type,
                        )
                        await self._send_error(
                            client,
                            "The server could not process that request",
                            message.request_id,
                        )
        except (
            ConnectionClosed,
            ConnectionError,
            OSError,
            ProtocolError,
            asyncio.CancelledError,
        ):
            pass
        finally:
            # A resumed session may have replaced this transport while its close
            # callback was still pending. Only detach the currently registered one.
            if self.clients.get(client.client_id) is client:
                self.clients.pop(client.client_id, None)
                match = self._match_for_client(client.client_id)
                lobby = self.directory.lobby_for(client.client_id)
                resumable = bool(
                    client.client_kind == "web"
                    and client.resume_token
                    and (match or lobby)
                )
                if resumable:
                    if match:
                        match.detach_client(client.client_id, client)
                    prior = self.disconnect_tasks.pop(client.client_id, None)
                    if prior:
                        prior.cancel()
                    self.disconnect_tasks[client.client_id] = asyncio.create_task(
                        self._disconnect_grace_elapsed(client)
                    )
                else:
                    await self._leave_lobby(client, "The other player disconnected")
                    self._forget_session(client.client_id)
            await client.close()

    async def serve(self, host: str, port: int) -> None:
        self.loop = asyncio.get_running_loop()
        async with serve(
            self.handle_connection,
            host,
            port,
            max_size=MAX_MESSAGE_SIZE + 4,
            ping_interval=5,
            ping_timeout=5,
        ) as server:
            addresses = ", ".join(
                str(sock.getsockname()) for sock in server.sockets or ()
            )
            print(f"Online WebSocket lobby relay listening on {addresses}")
            await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Draci Zvesti online lobby relay")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=Config.lobby_server_port)
    parser.add_argument("--max-clients", type=int, default=200)
    parser.add_argument("--max-lobbies", type=int, default=100)
    args = parser.parse_args()
    relay = OnlineRelayServer(
        max_clients=args.max_clients,
        max_lobbies=args.max_lobbies,
    )
    try:
        asyncio.run(relay.serve(args.host, args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
