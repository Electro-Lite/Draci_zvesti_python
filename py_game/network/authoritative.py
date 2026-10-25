"""Server-owned online matches shared by browser and native clients."""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from dataclasses import asdict
from uuid import uuid4

from choice_strategies.choice_strategy import PlayerChoiceStrategy
from core.board import Board
from core.game_loop import run as run_game
from core.player import Player
from display_strategies.display_strategy_none import DisplayStrategyNone
from py_game.network.gameplay import RemoteChoiceStrategy, serialize_game_state
from py_game.network.protocol import MessageType


_CANCELLED = object()


class ServerMatchChannel:
    """Synchronous game-thread choices bridged to an asyncio WebSocket."""

    def __init__(self, match, client, local_player, opponent):
        self.match = match
        self.client_id = client.client_id
        self.client = client
        self.local_player = local_player
        self.opponent = opponent
        self._actions: queue.Queue = queue.Queue()
        self._pending_request_id: str | None = None
        self._pending_payload: dict | None = None
        self._pending_lock = threading.Lock()
        self._client_lock = threading.Lock()

    @property
    def connected(self):
        with self._client_lock:
            return self.client is not None

    def attach(self, client):
        with self._client_lock:
            self.client = client

    def detach(self, client=None):
        with self._client_lock:
            if client is None or self.client is client:
                self.client = None

    def snapshot(self, status="playing"):
        return serialize_game_state(
            self.match.board,
            self.local_player,
            self.opponent,
            status=status,
        )

    def send(self, message_type, payload=None, *, request_id=None):
        if self.match.cancelled.is_set():
            raise SystemExit("Match cancelled")
        with self._client_lock:
            client = self.client
        if client is None:
            return False
        future = asyncio.run_coroutine_threadsafe(
            client.send(
                message_type,
                payload or {},
                request_id=request_id,
                match_id=self.match.match_id,
            ),
            self.match.loop,
        )
        try:
            future.result(timeout=10)
            return True
        except Exception:
            self.detach(client)
            return False

    def send_snapshot(self, status="playing"):
        self.send(MessageType.STATE_SNAPSHOT, self.snapshot(status))

    def request_action(self, choice_type, extra=None, timeout=120.0):
        request_id = uuid4().hex
        payload = {"choice_type": choice_type, "state": self.snapshot()}
        payload.update(extra or {})
        with self._pending_lock:
            self._pending_request_id = request_id
            self._pending_payload = payload
        self.send(MessageType.CHOICE_REQUEST, payload, request_id=request_id)
        try:
            connected_wait = 0.0
            while True:
                started = time.monotonic()
                try:
                    value = self._actions.get(timeout=1.0)
                    break
                except queue.Empty:
                    if self.match.all_connected:
                        connected_wait += time.monotonic() - started
                    if connected_wait >= timeout:
                        self.match.cancel("Player action timed out")
                        raise TimeoutError("Player action timed out")
        finally:
            with self._pending_lock:
                self._pending_request_id = None
                self._pending_payload = None
        if value is _CANCELLED:
            raise SystemExit(self.match.cancel_reason or "Match cancelled")
        return value

    def accept_action(self, request_id, value):
        with self._pending_lock:
            if request_id != self._pending_request_id:
                return False
        self._actions.put(value)
        return True

    def reject(self, request_id, reason):
        self.send(
            MessageType.ERROR,
            {"message": str(reason), "recoverable": True},
            request_id=request_id,
        )

    def cancel(self):
        self._actions.put(_CANCELLED)

    async def resume(self, start_payload):
        with self._client_lock:
            client = self.client
        if client is None:
            return
        await client.send(
            MessageType.START_MATCH,
            {**start_payload, "resumed": True},
            match_id=self.match.match_id,
        )
        await client.send(
            MessageType.STATE_SNAPSHOT,
            self.snapshot(),
            match_id=self.match.match_id,
        )
        with self._pending_lock:
            request_id = self._pending_request_id
            payload = self._pending_payload
        if request_id and payload:
            await client.send(
                MessageType.CHOICE_REQUEST,
                payload,
                request_id=request_id,
                match_id=self.match.match_id,
            )

    async def replay_pending(self):
        with self._client_lock:
            client = self.client
        with self._pending_lock:
            request_id = self._pending_request_id
            payload = self._pending_payload
        if client and request_id and payload:
            await client.send(
                MessageType.CHOICE_REQUEST,
                payload,
                request_id=request_id,
                match_id=self.match.match_id,
            )


def authoritative_display_strategy(channels, cancelled, battle_frame_seconds=1.95):
    class AuthoritativeDisplayStrategy(DisplayStrategyNone):
        def _publish(self):
            for channel in channels:
                channel.send_snapshot()

        def _battle_frame(self):
            self._publish()
            deadline = time.monotonic() + battle_frame_seconds
            while time.monotonic() < deadline:
                if cancelled():
                    raise SystemExit("Match cancelled")
                time.sleep(min(0.03, deadline - time.monotonic()))

        def _battle_result(self):
            self._publish()
            channels[0].request_action(
                "continue",
                {"legal_indices": [True]},
                timeout=300.0,
            )

        display_board = _publish
        display_mana = _publish
        display_hand = _publish
        display_status = _publish
        display_round = lambda self, _round: self._publish()
        display_player_on_turn = lambda self, _player: self._publish()
        display_choice = lambda self, *_args: self._publish()
        display_dragon = _battle_frame
        display_dragon_vs_card = _battle_frame
        display_battle_result = _battle_result
        display_game_result = lambda self, _winner: self._publish()

    return AuthoritativeDisplayStrategy


class AuthoritativeMatch:
    def __init__(
        self,
        *,
        loop,
        match_id,
        host_client,
        guest_client,
        host_deck,
        guest_deck,
        dragons,
        seed,
        starting_player_id,
        completed,
    ):
        self.loop = loop
        self.match_id = match_id
        self.host_client = host_client
        self.guest_client = guest_client
        self.host_id = host_client.client_id
        self.guest_id = guest_client.client_id
        self.board = Board(dragons=dragons)
        self.seed = int(seed)
        self.starting_player_id = int(starting_player_id)
        self.completed = completed
        self.cancelled = threading.Event()
        self.cancel_reason = ""
        self.player_1 = Player(1, host_deck, RemoteChoiceStrategy)
        self.player_2 = Player(2, guest_deck, RemoteChoiceStrategy)
        self.channels = (
            ServerMatchChannel(self, host_client, self.player_1, self.player_2),
            ServerMatchChannel(self, guest_client, self.player_2, self.player_1),
        )
        self.player_1.choice_strategy.channel = self.channels[0]
        self.player_2.choice_strategy.channel = self.channels[1]
        self.thread: threading.Thread | None = None

    async def start(self):
        payload = self.start_payload()
        await asyncio.gather(
            self.host_client.send(MessageType.START_MATCH, payload, match_id=self.match_id),
            self.guest_client.send(MessageType.START_MATCH, payload, match_id=self.match_id),
        )
        self.thread = threading.Thread(
            target=self._run,
            name=f"online-match-{self.match_id[:8]}",
            daemon=True,
        )
        self.thread.start()

    def start_payload(self):
        return {
            "match_id": self.match_id,
            "seed": self.seed,
            "starting_player_id": self.starting_player_id,
            "authoritative": True,
        }

    def _run(self):
        result = None
        error = None
        try:
            result = run_game(
                self.player_1,
                self.player_2,
                authoritative_display_strategy(
                    self.channels,
                    self.cancelled.is_set,
                ),
                self.board,
                seed=self.seed,
                starting_player_id=self.starting_player_id,
            )
        except (SystemExit, TimeoutError) as exc:
            error = str(exc) or self.cancel_reason or "Match interrupted"
        except Exception as exc:  # The server reports, then isolates match failure.
            error = f"{type(exc).__name__}: {exc}"
        future = asyncio.run_coroutine_threadsafe(
            self._finish(result, error),
            self.loop,
        )
        try:
            future.result(timeout=15)
        except Exception:
            pass

    async def _finish(self, result, error):
        status = "interrupted" if error else "finished"
        for channel in self.channels:
            payload = {
                "state": channel.snapshot(status),
                "aborted": bool(error),
            }
            if error:
                payload["reason"] = error
            elif result is not None:
                payload["result"] = asdict(result)
            try:
                await channel.client.send(
                    MessageType.MATCH_RESULT,
                    payload,
                    match_id=self.match_id,
                )
            except Exception:
                pass
        await self.completed(self, error)

    def accept_action(self, client_id, request_id, value):
        if not self.all_connected:
            return False
        channel = next(
            (item for item in self.channels if item.client_id == client_id),
            None,
        )
        return bool(channel and channel.accept_action(request_id, value))

    def has_client(self, client_id):
        return any(channel.client_id == client_id for channel in self.channels)

    @property
    def all_connected(self):
        return all(channel.connected for channel in self.channels)

    def peer_id(self, client_id):
        if client_id == self.host_id:
            return self.guest_id
        if client_id == self.guest_id:
            return self.host_id
        return None

    def detach_client(self, client_id, client=None):
        channel = next((item for item in self.channels if item.client_id == client_id), None)
        if channel:
            channel.detach(client)

    def replace_client(self, client_id, client):
        channel = next((item for item in self.channels if item.client_id == client_id), None)
        if channel is None:
            return False
        channel.attach(client)
        if client_id == self.host_id:
            self.host_client = client
        else:
            self.guest_client = client
        return True

    async def resume_client(self, client_id):
        channel = next((item for item in self.channels if item.client_id == client_id), None)
        if channel:
            await channel.resume(self.start_payload())
        if self.all_connected:
            for other in self.channels:
                if other is not channel:
                    await other.replay_pending()

    def cancel(self, reason="Match cancelled"):
        if self.cancelled.is_set():
            return
        self.cancel_reason = str(reason)
        self.cancelled.set()
        for channel in self.channels:
            channel.cancel()
