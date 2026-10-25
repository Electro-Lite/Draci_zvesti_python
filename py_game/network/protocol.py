from __future__ import annotations

import json
import struct
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


PROTOCOL_VERSION = 2
APPLICATION_VERSION = "1.0"
MAX_MESSAGE_SIZE = 256 * 1024
HEADER = struct.Struct("!I")


class ProtocolError(ValueError):
    pass


class MessageType(str, Enum):
    ONLINE_HELLO = "online_hello"
    ONLINE_WELCOME = "online_welcome"
    LIST_LOBBIES = "list_lobbies"
    LOBBY_LIST = "lobby_list"
    CREATE_ONLINE_LOBBY = "create_online_lobby"
    JOIN_ONLINE_LOBBY = "join_online_lobby"
    LEAVE_ONLINE_LOBBY = "leave_online_lobby"
    ONLINE_LOBBY = "online_lobby"
    ONLINE_LOBBY_CLOSED = "online_lobby_closed"
    SERVER_STATUS = "server_status"
    HELLO = "hello"
    HELLO_ACCEPTED = "hello_accepted"
    ERROR = "error"
    LOBBY_STATE = "lobby_state"
    SELECT_DECK = "select_deck"
    READY = "ready"
    START_MATCH = "start_match"
    STATE_SNAPSHOT = "state_snapshot"
    CHOICE_REQUEST = "choice_request"
    PLAYER_ACTION = "player_action"
    MATCH_RESULT = "match_result"
    RETURN_TO_LOBBY = "return_to_lobby"
    PING = "ping"
    PONG = "pong"
    DISCONNECT = "disconnect"
    PEER_CONNECTION_STATUS = "peer_connection_status"


@dataclass(frozen=True)
class ProtocolMessage:
    type: str
    sequence: int
    request_id: str | None = None
    match_id: str | None = None
    payload: dict[str, Any] | None = None
    protocol_version: int = PROTOCOL_VERSION
    application_version: str = APPLICATION_VERSION

    def validate(self) -> None:
        try:
            MessageType(self.type)
        except ValueError as error:
            raise ProtocolError(f"Unknown message type: {self.type}") from error
        if self.protocol_version != PROTOCOL_VERSION:
            raise ProtocolError(
                f"Protocol mismatch: expected {PROTOCOL_VERSION}, got {self.protocol_version}"
            )
        if (
            not isinstance(self.application_version, str)
            or not self.application_version
            or len(self.application_version) > 32
        ):
            raise ProtocolError(
                "Application version must be a string of at most 32 characters"
            )
        if not isinstance(self.sequence, int) or self.sequence < 0:
            raise ProtocolError("Message sequence must be a non-negative integer")
        if self.payload is not None and not isinstance(self.payload, dict):
            raise ProtocolError("Message payload must be an object")
        for name, value in (("request_id", self.request_id), ("match_id", self.match_id)):
            if value is not None and (not isinstance(value, str) or len(value) > 128):
                raise ProtocolError(f"{name} must be a string of at most 128 characters")


def encode_message(message: ProtocolMessage) -> bytes:
    message.validate()
    body = json.dumps(
        asdict(message),
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if len(body) > MAX_MESSAGE_SIZE:
        raise ProtocolError("Message exceeds the maximum allowed size")
    return HEADER.pack(len(body)) + body


def decode_body(body: bytes) -> ProtocolMessage:
    if len(body) > MAX_MESSAGE_SIZE:
        raise ProtocolError("Message exceeds the maximum allowed size")
    try:
        raw = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError("Message is not valid UTF-8 JSON") from error
    if not isinstance(raw, dict):
        raise ProtocolError("Message root must be an object")
    required = {"type", "sequence"}
    if not required.issubset(raw):
        raise ProtocolError("Message is missing required fields")
    allowed = {
        "type",
        "sequence",
        "request_id",
        "match_id",
        "payload",
        "protocol_version",
        "application_version",
    }
    if set(raw) - allowed:
        raise ProtocolError("Message contains unknown fields")
    try:
        message = ProtocolMessage(**raw)
    except TypeError as error:
        raise ProtocolError("Message fields are invalid") from error
    message.validate()
    return message


class FrameDecoder:
    def __init__(self):
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[ProtocolMessage]:
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("Frame data must be bytes")
        self._buffer.extend(data)
        messages = []
        while len(self._buffer) >= HEADER.size:
            (size,) = HEADER.unpack(self._buffer[: HEADER.size])
            if size <= 0 or size > MAX_MESSAGE_SIZE:
                self._buffer.clear()
                raise ProtocolError("Invalid frame size")
            frame_end = HEADER.size + size
            if len(self._buffer) < frame_end:
                break
            body = bytes(self._buffer[HEADER.size:frame_end])
            del self._buffer[:frame_end]
            messages.append(decode_body(body))
        return messages


class SequenceGuard:
    def __init__(self):
        self.last_sequence = -1

    def accept(self, sequence: int) -> bool:
        if sequence <= self.last_sequence:
            return False
        self.last_sequence = sequence
        return True
