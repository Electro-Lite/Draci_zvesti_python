from __future__ import annotations

import queue
import socket
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import urlsplit

from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.sync.client import ClientConnection, connect as websocket_connect

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


class ConnectionState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    CLOSED = "closed"


@dataclass(frozen=True)
class NetworkEvent:
    kind: str
    message: ProtocolMessage | None = None
    detail: str = ""


class SocketPeer:
    """A single framed JSON socket connection with queue-based I/O."""

    def __init__(
        self,
        sock: socket.socket,
        address: tuple[Any, ...],
        *,
        heartbeat_interval: float = 3.0,
        idle_timeout: float = 15.0,
    ):
        self.socket = sock
        self.address = address
        # Keep queued gameplay actions responsive without busy-spinning.
        self.socket.settimeout(0.01)
        self.state = ConnectionState.CONNECTED
        self.events: queue.Queue[NetworkEvent] = queue.Queue()
        self._outgoing: queue.Queue[bytes] = queue.Queue()
        self._decoder = FrameDecoder()
        self._incoming_sequence = SequenceGuard()
        self._sequence = 0
        self._send_lock = threading.Lock()
        self._last_received = time.monotonic()
        self._last_heartbeat = time.monotonic()
        self.latency_ms: float | None = None
        self.heartbeat_interval = float(heartbeat_interval)
        self.idle_timeout = float(idle_timeout)
        if self.heartbeat_interval <= 0 or self.idle_timeout <= 0:
            raise ValueError("Heartbeat and idle timeout must be positive")
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="lan-socket-peer",
            daemon=True,
        )
        self._thread.start()

    @property
    def alive(self) -> bool:
        return self._thread.is_alive() and not self._stop.is_set()

    def send(
        self,
        message_type: MessageType | str,
        payload: dict[str, Any] | None = None,
        *,
        request_id: str | None = None,
        match_id: str | None = None,
    ) -> ProtocolMessage:
        if self.state != ConnectionState.CONNECTED:
            raise ConnectionError("LAN peer is not connected")
        with self._send_lock:
            message = ProtocolMessage(
                type=(message_type.value if isinstance(message_type, MessageType) else message_type),
                sequence=self._sequence,
                request_id=request_id,
                match_id=match_id,
                payload=payload,
            )
            self._sequence += 1
            self._outgoing.put(encode_message(message))
        return message

    def poll(self, limit: int = 100) -> list[NetworkEvent]:
        result = []
        for _ in range(limit):
            try:
                result.append(self.events.get_nowait())
            except queue.Empty:
                break
        return result

    def _emit(self, kind: str, message=None, detail: str = "") -> None:
        self.events.put(NetworkEvent(kind, message, detail))

    def _flush_outgoing(self) -> None:
        while True:
            try:
                data = self._outgoing.get_nowait()
            except queue.Empty:
                return
            self.socket.sendall(data)

    def _run(self) -> None:
        disconnect_detail = "Peer disconnected"
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                if now - self._last_heartbeat >= self.heartbeat_interval:
                    self.send(MessageType.PING, {"sent_at": now})
                    self._last_heartbeat = now
                if now - self._last_received >= self.idle_timeout:
                    raise TimeoutError("LAN peer timed out")
                self._flush_outgoing()
                try:
                    data = self.socket.recv(64 * 1024)
                except socket.timeout:
                    continue
                if not data:
                    break
                self._last_received = time.monotonic()
                for message in self._decoder.feed(data):
                    if not self._incoming_sequence.accept(message.sequence):
                        self._emit(
                            "protocol_error",
                            detail=f"Duplicate or out-of-order sequence {message.sequence}",
                        )
                        continue
                    if message.type == MessageType.PING.value:
                        self.send(MessageType.PONG, message.payload or {})
                        continue
                    if message.type == MessageType.PONG.value:
                        sent_at = (message.payload or {}).get("sent_at")
                        if isinstance(sent_at, (int, float)) and sent_at <= time.monotonic():
                            measured = max(0.0, (time.monotonic() - sent_at) * 1000.0)
                            self.latency_ms = (
                                measured
                                if self.latency_ms is None
                                else self.latency_ms * 0.75 + measured * 0.25
                            )
                        continue
                    self._emit("message", message=message)
        except (OSError, ProtocolError, ConnectionError, TimeoutError) as error:
            disconnect_detail = str(error)
            if not self._stop.is_set():
                self.state = ConnectionState.ERROR
                self._emit("error", detail=disconnect_detail)
        finally:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.socket.close()
            if self.state != ConnectionState.ERROR:
                self.state = ConnectionState.DISCONNECTED
            self._emit("disconnected", detail=disconnect_detail)

    def close(self, reason: str = "Connection closed") -> None:
        if self._stop.is_set():
            return
        try:
            if self.state == ConnectionState.CONNECTED:
                self.send(MessageType.DISCONNECT, {"reason": reason})
                deadline = time.monotonic() + 0.15
                while not self._outgoing.empty() and time.monotonic() < deadline:
                    time.sleep(0.005)
        except (ConnectionError, OSError):
            pass
        self._stop.set()
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._thread.join(timeout=1.0)
        self.state = ConnectionState.CLOSED


class LanHost:
    def __init__(self, bind_host: str = "0.0.0.0", port: int = 47777):
        self.bind_host = bind_host
        self.port = int(port)
        self.state = ConnectionState.IDLE
        self.events: queue.Queue[NetworkEvent] = queue.Queue()
        self.peer: SocketPeer | None = None
        self._listener: socket.socket | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self.state not in (ConnectionState.IDLE, ConnectionState.CLOSED):
            raise RuntimeError("Host is already running")
        self._stop.clear()
        family = socket.AF_INET6 if ":" in self.bind_host else socket.AF_INET
        self._listener = socket.socket(family, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((self.bind_host, self.port))
        self.port = self._listener.getsockname()[1]
        self._listener.listen(1)
        self._listener.settimeout(0.1)
        self.state = ConnectionState.LISTENING
        self._thread = threading.Thread(
            target=self._accept_loop,
            name="lan-host-listener",
            daemon=True,
        )
        self._thread.start()

    def _accept_loop(self) -> None:
        try:
            while not self._stop.is_set():
                if self.peer is not None:
                    time.sleep(0.02)
                    continue
                try:
                    client, address = self._listener.accept()
                except socket.timeout:
                    continue
                self.peer = SocketPeer(client, address)
                self.state = ConnectionState.CONNECTED
                self.events.put(NetworkEvent("connected", detail=str(address[0])))
        except OSError as error:
            if not self._stop.is_set():
                self.state = ConnectionState.ERROR
                self.events.put(NetworkEvent("error", detail=str(error)))

    def poll(self) -> list[NetworkEvent]:
        result = []
        while True:
            try:
                result.append(self.events.get_nowait())
            except queue.Empty:
                break
        if self.peer is not None:
            peer = self.peer
            result.extend(peer.poll())
            if peer.state in (
                ConnectionState.DISCONNECTED,
                ConnectionState.ERROR,
                ConnectionState.CLOSED,
            ) and not peer.alive:
                self.peer = None
                if not self._stop.is_set():
                    self.state = ConnectionState.LISTENING
        return result

    def close(self) -> None:
        self._stop.set()
        if self.peer is not None:
            self.peer.close("Host closed the LAN session")
            self.peer = None
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
            self._listener = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self.state = ConnectionState.CLOSED


class LanClient:
    def __init__(self):
        self.state = ConnectionState.IDLE
        self.events: queue.Queue[NetworkEvent] = queue.Queue()
        self.peer: SocketPeer | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._pending_socket: socket.socket | None = None
        self._pending_lock = threading.Lock()

    def connect(self, host: str, port: int, timeout: float = 5.0) -> None:
        if self.state in (ConnectionState.CONNECTING, ConnectionState.CONNECTED):
            raise RuntimeError("Client is already connecting or connected")
        self.state = ConnectionState.CONNECTING
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._connect,
            args=(host, int(port), timeout),
            name="lan-client-connect",
            daemon=True,
        )
        self._thread.start()

    def _connect(self, host: str, port: int, timeout: float) -> None:
        sock = None
        try:
            addresses = socket.getaddrinfo(
                host,
                port,
                type=socket.SOCK_STREAM,
            )
            if not addresses:
                raise OSError("Host address did not resolve")
            last_error = None
            for family, sock_type, protocol, _, address in addresses:
                if self._stop.is_set():
                    return
                candidate = socket.socket(family, sock_type, protocol)
                candidate.settimeout(timeout)
                with self._pending_lock:
                    self._pending_socket = candidate
                try:
                    candidate.connect(address)
                    sock = candidate
                    break
                except OSError as error:
                    last_error = error
                    candidate.close()
                finally:
                    with self._pending_lock:
                        if self._pending_socket is candidate:
                            self._pending_socket = None
            if sock is None:
                raise last_error or OSError("Could not connect to the host")
            if self._stop.is_set():
                sock.close()
                return
            self.peer = SocketPeer(sock, sock.getpeername())
            self.state = ConnectionState.CONNECTED
            self.events.put(NetworkEvent("connected", detail=host))
        except OSError as error:
            if not self._stop.is_set():
                self.state = ConnectionState.ERROR
                self.events.put(NetworkEvent("error", detail=str(error)))

    def poll(self) -> list[NetworkEvent]:
        result = []
        while True:
            try:
                result.append(self.events.get_nowait())
            except queue.Empty:
                break
        if self.peer is not None:
            result.extend(self.peer.poll())
        return result

    def close(self) -> None:
        self._stop.set()
        with self._pending_lock:
            if self._pending_socket is not None:
                try:
                    self._pending_socket.close()
                except OSError:
                    pass
                self._pending_socket = None
        if self.peer is not None:
            self.peer.close("Client left the LAN session")
            self.peer = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self.state = ConnectionState.CLOSED


class WebSocketPeer:
    """Threaded WebSocket transport exposing the same interface as SocketPeer."""

    def __init__(
        self,
        websocket: ClientConnection,
        address: str,
        *,
        heartbeat_interval: float = 3.0,
        idle_timeout: float = 15.0,
    ):
        self.websocket = websocket
        self.address = address
        self.state = ConnectionState.CONNECTED
        self.events: queue.Queue[NetworkEvent] = queue.Queue()
        self._outgoing: queue.Queue[bytes] = queue.Queue()
        self._decoder = FrameDecoder()
        self._incoming_sequence = SequenceGuard()
        self._sequence = 0
        self._send_lock = threading.Lock()
        self._last_received = time.monotonic()
        self._last_heartbeat = time.monotonic()
        self.latency_ms: float | None = None
        self.heartbeat_interval = float(heartbeat_interval)
        self.idle_timeout = float(idle_timeout)
        if self.heartbeat_interval <= 0 or self.idle_timeout <= 0:
            raise ValueError("Heartbeat and idle timeout must be positive")
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="online-websocket-peer",
            daemon=True,
        )
        self._thread.start()

    @property
    def alive(self) -> bool:
        return self._thread.is_alive() and not self._stop.is_set()

    def send(
        self,
        message_type: MessageType | str,
        payload: dict[str, Any] | None = None,
        *,
        request_id: str | None = None,
        match_id: str | None = None,
    ) -> ProtocolMessage:
        if self.state != ConnectionState.CONNECTED:
            raise ConnectionError("Online server is not connected")
        with self._send_lock:
            message = ProtocolMessage(
                type=(message_type.value if isinstance(message_type, MessageType) else message_type),
                sequence=self._sequence,
                request_id=request_id,
                match_id=match_id,
                payload=payload,
            )
            self._sequence += 1
            self._outgoing.put(encode_message(message))
        return message

    def poll(self, limit: int = 100) -> list[NetworkEvent]:
        result = []
        for _ in range(limit):
            try:
                result.append(self.events.get_nowait())
            except queue.Empty:
                break
        return result

    def _emit(self, kind: str, message=None, detail: str = "") -> None:
        self.events.put(NetworkEvent(kind, message, detail))

    def _flush_outgoing(self) -> None:
        while True:
            try:
                data = self._outgoing.get_nowait()
            except queue.Empty:
                return
            self.websocket.send(data)

    def _handle_data(self, data: bytes | str) -> None:
        if isinstance(data, str):
            raise ProtocolError("Online messages must use binary WebSocket frames")
        self._last_received = time.monotonic()
        for message in self._decoder.feed(data):
            if not self._incoming_sequence.accept(message.sequence):
                self._emit(
                    "protocol_error",
                    detail=f"Duplicate or out-of-order sequence {message.sequence}",
                )
                continue
            if message.type == MessageType.PING.value:
                self.send(MessageType.PONG, message.payload or {})
                continue
            if message.type == MessageType.PONG.value:
                sent_at = (message.payload or {}).get("sent_at")
                if isinstance(sent_at, (int, float)) and sent_at <= time.monotonic():
                    measured = max(0.0, (time.monotonic() - sent_at) * 1000.0)
                    self.latency_ms = (
                        measured
                        if self.latency_ms is None
                        else self.latency_ms * 0.75 + measured * 0.25
                    )
                continue
            self._emit("message", message=message)

    def _run(self) -> None:
        disconnect_detail = "Online server disconnected"
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                if now - self._last_heartbeat >= self.heartbeat_interval:
                    self.send(MessageType.PING, {"sent_at": now})
                    self._last_heartbeat = now
                if now - self._last_received >= self.idle_timeout:
                    raise TimeoutError("Online server timed out")
                self._flush_outgoing()
                try:
                    data = self.websocket.recv(timeout=0.01)
                except TimeoutError:
                    continue
                self._handle_data(data)
        except (OSError, ProtocolError, ConnectionError, ConnectionClosed, TimeoutError) as error:
            disconnect_detail = str(error)
            if not self._stop.is_set():
                self.state = ConnectionState.ERROR
                self._emit("error", detail=disconnect_detail)
        finally:
            try:
                self.websocket.close()
            except (OSError, ConnectionClosed):
                pass
            if self.state != ConnectionState.ERROR:
                self.state = ConnectionState.DISCONNECTED
            self._emit("disconnected", detail=disconnect_detail)

    def close(self, reason: str = "Connection closed") -> None:
        if self._stop.is_set():
            return
        try:
            if self.state == ConnectionState.CONNECTED:
                self.send(MessageType.DISCONNECT, {"reason": reason})
                deadline = time.monotonic() + 0.15
                while not self._outgoing.empty() and time.monotonic() < deadline:
                    time.sleep(0.005)
        except (ConnectionError, OSError, ConnectionClosed):
            pass
        self._stop.set()
        try:
            self.websocket.close()
        except (OSError, ConnectionClosed):
            pass
        self._thread.join(timeout=1.0)
        self.state = ConnectionState.CLOSED


class OnlineClient(LanClient):
    """WebSocket client for the public lobby relay.

    The relay deliberately exposes the same peer/poll interface as LAN so the
    authoritative match channel and remote choice strategy can be reused.
    """

    CONTROL_MESSAGES = {
        MessageType.ONLINE_WELCOME.value,
        MessageType.LOBBY_LIST.value,
        MessageType.ONLINE_LOBBY.value,
        MessageType.ONLINE_LOBBY_CLOSED.value,
        MessageType.SERVER_STATUS.value,
    }

    def __init__(self):
        super().__init__()
        self.peer: WebSocketPeer | None = None
        self._control_events: queue.Queue[NetworkEvent] = queue.Queue()
        self._relay_events: queue.Queue[NetworkEvent] = queue.Queue()

    def connect(self, url: str, port: int | None = None, timeout: float = 5.0) -> None:
        if self.state in (ConnectionState.CONNECTING, ConnectionState.CONNECTED):
            raise RuntimeError("Client is already connecting or connected")
        if port is not None:
            url = f"ws://{url}:{int(port)}/game"
        parsed = urlsplit(url)
        if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
            raise ValueError("Online server URL must start with ws:// or wss://")
        self.state = ConnectionState.CONNECTING
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._connect_websocket,
            args=(url, timeout),
            name="online-websocket-connect",
            daemon=True,
        )
        self._thread.start()

    def _connect_websocket(self, url: str, timeout: float) -> None:
        websocket = None
        try:
            websocket = websocket_connect(
                url,
                open_timeout=timeout,
                close_timeout=1,
                max_size=MAX_MESSAGE_SIZE + 4,
            )
            if self._stop.is_set():
                websocket.close()
                return
            self.peer = WebSocketPeer(websocket, url)
            self.state = ConnectionState.CONNECTED
            self.events.put(NetworkEvent("connected", detail=url))
        except (OSError, TimeoutError, WebSocketException, ValueError) as error:
            if websocket is not None:
                websocket.close()
            if not self._stop.is_set():
                self.state = ConnectionState.ERROR
                self.events.put(NetworkEvent("error", detail=str(error)))

    @staticmethod
    def _drain(source: queue.Queue, limit=100) -> list[NetworkEvent]:
        events = []
        for _ in range(limit):
            try:
                events.append(source.get_nowait())
            except queue.Empty:
                break
        return events

    def _harvest(self) -> None:
        for event in super().poll():
            if (
                event.kind == "message"
                and event.message
                and event.message.type in self.CONTROL_MESSAGES
            ):
                self._control_events.put(event)
            else:
                self._relay_events.put(event)

    def poll(self) -> list[NetworkEvent]:
        self._harvest()
        return self._drain(self._relay_events)

    def poll_control(self) -> list[NetworkEvent]:
        self._harvest()
        return self._drain(self._control_events)


def discover_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))
            address = probe.getsockname()[0]
            if address:
                return address
    except OSError:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def hello_payload(player_name: str) -> dict[str, Any]:
    return {
        "player_name": player_name,
        "application_version": APPLICATION_VERSION,
    }


def explain_connection_error(detail: str) -> str:
    """Translate platform socket text into stable, actionable LAN guidance."""
    lowered = str(detail).lower()
    if "timed out" in lowered or "timeout" in lowered:
        return "Connection timed out; verify the address, port, and firewall"
    if "refused" in lowered:
        return "Connection refused; verify that the host lobby is open and the port matches"
    if "name or service" in lowered or "not known" in lowered or "nodename" in lowered:
        return "Host name could not be resolved; check the address spelling"
    if "network is unreachable" in lowered or "no route" in lowered:
        return "Host is unreachable; confirm that both players are on the same LAN"
    if "address already in use" in lowered:
        return "LAN port is already in use; choose another port in Settings"
    if "permission denied" in lowered or "not permitted" in lowered:
        return "The operating system blocked the LAN socket; check firewall permissions"
    return "Connection failed; verify the LAN address, port, and firewall settings"


def parse_join_target(value: str, default_port: int) -> tuple[str, int]:
    """Parse hostname, IPv4, IPv6, and optional port without resolving it."""
    value = value.strip()
    if not value:
        raise ValueError("Host address cannot be empty")
    host = value
    port = int(default_port)
    if value.startswith("["):
        closing = value.find("]")
        if closing < 0:
            raise ValueError("IPv6 addresses with a port must use [address]:port")
        host = value[1:closing]
        remainder = value[closing + 1 :]
        if remainder:
            if not remainder.startswith(":"):
                raise ValueError("Unexpected text after IPv6 address")
            try:
                port = int(remainder[1:])
            except ValueError as error:
                raise ValueError("LAN port must be a number") from error
    elif value.count(":") == 1:
        possible_host, possible_port = value.rsplit(":", 1)
        if possible_port:
            try:
                port = int(possible_port)
                host = possible_host
            except ValueError:
                host = value
    if not host or len(host) > 253:
        raise ValueError("Host address must contain 1-253 characters")
    if not 1024 <= port <= 65535:
        raise ValueError("LAN port must be between 1024 and 65535")
    return host, port
