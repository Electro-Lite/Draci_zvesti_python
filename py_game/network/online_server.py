from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Any

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from config import Config

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
        }

    def state(self, role: str) -> dict[str, Any]:
        return {
            **self.listing(),
            "role": role,
            "guest_name": self.guest_name,
        }


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
        self.client_id = secrets.token_hex(12)
        self.player_name = ""
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
    def __init__(self, *, max_clients: int = 200, max_lobbies: int = 100):
        self.max_clients = max(2, int(max_clients))
        self.directory = LobbyDirectory(max_lobbies)
        self.clients: dict[str, RelayConnection] = {}

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

    async def _leave_lobby(self, client: RelayConnection, reason: str) -> None:
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
            client.player_name = name
            await client.send(
                MessageType.ONLINE_WELCOME,
                {"client_id": client.client_id},
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
            await self._relay(client, message)

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
        except (
            ConnectionClosed,
            ConnectionError,
            OSError,
            ProtocolError,
            asyncio.CancelledError,
        ):
            pass
        finally:
            # Remove the dead transport before lobby notifications broadcast;
            # otherwise the closing WebSocket receives one last directory send.
            self.clients.pop(client.client_id, None)
            await self._leave_lobby(client, "The other player disconnected")
            await client.close()

    async def serve(self, host: str, port: int) -> None:
        async with serve(
            self.handle_connection,
            host,
            port,
            max_size=MAX_MESSAGE_SIZE + 4,
            ping_interval=20,
            ping_timeout=20,
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
