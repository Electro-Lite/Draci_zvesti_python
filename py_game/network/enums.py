from enum import StrEnum


class MatchStatus(StrEnum):
    PLAYING = "playing"
    FINISHED = "finished"
    INTERRUPTED = "interrupted"


class LobbyStatus(StrEnum):
    WAITING_FOR_PLAYER = "waiting_for_player"
    CONFIGURING = "configuring"
    READY = "ready"


class LobbyRole(StrEnum):
    HOST = "host"
    GUEST = "guest"


class ClientKind(StrEnum):
    NATIVE = "native"
    WEB = "web"
