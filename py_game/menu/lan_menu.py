from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pygame as pg

from py_game.menu.base_menu import Menu
from py_game.network.lobby import HostLobbyController
from py_game.network.protocol import MessageType
from py_game.network.session import (
    ConnectionState,
    LanClient,
    LanHost,
    discover_local_ip,
    explain_connection_error,
    hello_payload,
    parse_join_target,
)
from utils.database_utils import DBUtil

if TYPE_CHECKING:
    from py_game.game import Game


class LanMenu(Menu):
    """Host/join setup and authoritative LAN lobby."""

    def __init__(self, game: "Game"):
        super().__init__(game)
        self.mode = "root"
        self.selected = 0
        self.message = "LAN play is intended for trusted local networks only"
        self.message_color = self.game.palette.muted
        self.host: LanHost | None = None
        self.client: LanClient | None = None
        self.lobby: HostLobbyController | None = None
        self.remote_lobby: dict | None = None
        self.deck_options = DBUtil().get_all_deck_options()
        self.deck_ids = [deck_id for deck_id, _name in self.deck_options]
        self.deck_index = 0
        self.guest_ready = False
        self.join_host = self.game.settings.last_join_host
        self.local_ip = discover_local_ip()
        self._match_started = False

    def _valid_deck(self, deck_id: str) -> bool:
        try:
            deck = DBUtil().load_deck(deck_id)
            return bool(deck and deck.validate())
        except (ValueError, RuntimeError):
            return False

    def _deck_label(self, deck_id: str | None) -> str:
        if not deck_id:
            return "No valid decks"
        return next(
            (
                name
                for current_id, name in getattr(self, "deck_options", ())
                if current_id == deck_id
            ),
            deck_id,
        )

    def _rows(self):
        if self.mode == "root":
            return ["Host LAN Game", "Join LAN Game", "Back"]
        if self.mode == "join_setup":
            return [
                f"Host address: {self.join_host}",
                f"Port: {self.game.settings.lan_port}",
                "Connect",
                "Back",
            ]
        if self.mode == "host_lobby":
            state = self.lobby.state
            deck = self._deck_label(self.deck_ids[self.deck_index] if self.deck_ids else None)
            ready = state.host.ready
            guest = (
                f"{state.guest.name} — {'Ready' if state.guest.ready else 'Not ready'}"
                if state.guest
                else "Waiting for player…"
            )
            address = f"{self.local_ip}:{self.host.port if self.host else self.game.settings.lan_port}"
            return [
                f"Host deck: {deck}",
                f"Host ready: {'Yes' if ready else 'No'}",
                f"Address: {address} (copy)",
                f"Guest: {guest}",
                "Start match" if state.can_start else "Waiting for both players",
                "Cancel lobby",
            ]
        if self.mode == "guest_lobby":
            deck = self._deck_label(self.deck_ids[self.deck_index] if self.deck_ids else None)
            host = (self.remote_lobby or {}).get("host") or {}
            host_name = host.get("name", "Host")
            return [
                f"Guest deck: {deck}",
                f"Guest ready: {'Yes' if self.guest_ready else 'No'}",
                f"Host: {host_name}",
                f"Host ready: {'Yes' if host.get('ready') else 'No'}",
                "Waiting for host to start",
                "Leave lobby",
            ]
        return ["Connecting…", "Cancel"]

    def _enabled(self):
        rows = self._rows()
        enabled = [True] * len(rows)
        if self.mode == "host_lobby":
            enabled[3] = False
            enabled[4] = self.lobby.state.can_start
            enabled[0] = bool(self.deck_ids)
            enabled[1] = bool(self.deck_ids)
        elif self.mode == "guest_lobby":
            enabled[2] = False
            enabled[3] = False
            enabled[4] = False
            enabled[0] = bool(self.deck_ids)
            enabled[1] = bool(self.deck_ids)
        elif self.mode == "connecting":
            enabled[0] = False
        return enabled

    def _set_error(self, value: str):
        self.message = value
        self.message_color = self.game.palette.danger

    def _send_host(self, message_type, payload, **metadata) -> bool:
        peer = self.host.peer if self.host else None
        if peer is None:
            return False
        try:
            peer.send(message_type, payload, **metadata)
            return True
        except ConnectionError:
            self._set_error("Guest connection was lost; the host lobby remains open")
            return False

    def _send_client(self, message_type, payload, **metadata) -> bool:
        peer = self.client.peer if self.client else None
        if peer is None:
            self._set_error("Not connected to a host")
            return False
        try:
            peer.send(message_type, payload, **metadata)
            return True
        except ConnectionError:
            self._set_error("The host connection was lost; reconnect from the Join screen")
            return False

    def _start_host(self):
        self._close_sessions()
        self.host = LanHost(port=self.game.settings.lan_port)
        self.lobby = HostLobbyController(
            self.game.settings.player_name,
            self._valid_deck,
        )
        try:
            self.host.start()
        except OSError as error:
            self.host = None
            self._set_error(explain_connection_error(str(error)))
            return
        self.mode = "host_lobby"
        self.selected = 0
        self.message = f"Share {self.local_ip}:{self.host.port} with the other player"
        self.message_color = self.game.palette.success

    def _connect(self):
        self._close_sessions()
        self.client = LanClient()
        try:
            host, port = parse_join_target(
                self.join_host,
                self.game.settings.lan_port,
            )
            self.join_host = host
            self.game.settings.lan_port = port
            self.client.connect(host, port)
        except (OSError, RuntimeError, ValueError) as error:
            if isinstance(error, ValueError):
                self._set_error(str(error))
            else:
                self._set_error(explain_connection_error(str(error)))
            self.client = None
            return
        self.mode = "connecting"
        self.selected = 1
        self.message = f"Connecting to {self.join_host}:{self.game.settings.lan_port}…"
        self.message_color = self.game.palette.muted

    def _broadcast_lobby(self):
        if self.lobby:
            self._send_host(MessageType.LOBBY_STATE, self.lobby.state.public_payload())

    def _poll_network(self):
        if self.host:
            for event in self.host.poll():
                if event.kind == "connected":
                    self.message = "Player connected; waiting for handshake"
                    self.message_color = self.game.palette.success
                elif event.kind == "message" and event.message:
                    try:
                        response, payload = self.lobby.handle(event.message)
                        self._send_host(
                            response,
                            payload,
                            request_id=event.message.request_id,
                        )
                    except (ValueError, ConnectionError) as error:
                        self._set_error(str(error))
                        self._send_host(
                            MessageType.ERROR,
                            {"message": str(error)},
                            request_id=event.message.request_id,
                        )
                elif event.kind == "error":
                    self._set_error(explain_connection_error(event.detail))
                elif event.kind == "protocol_error":
                    self._set_error(f"Protocol error: {event.detail}")
                elif event.kind == "disconnected" and self.lobby:
                    self.lobby.state.guest = None
                    self.lobby.state.status = "waiting_for_player"
                    self.message = "Guest disconnected; lobby remains open"
                    self.message_color = self.game.palette.muted
        if self.client:
            client_events = self.client.poll()
            for event_index, event in enumerate(client_events):
                if event.kind == "connected" and self.client.peer:
                    self._send_client(
                        MessageType.HELLO,
                        hello_payload(self.game.settings.player_name),
                        request_id=uuid4().hex,
                    )
                    self.message = "Connected; completing handshake…"
                elif event.kind == "message" and event.message:
                    if event.message.type == MessageType.START_MATCH.value:
                        # The poll may already contain the first snapshots or
                        # choice request. Put them back before entering the
                        # blocking match UI so no valid action is lost.
                        for pending in client_events[event_index + 1 :]:
                            self.client.events.put(pending)
                        self._handle_client_message(event.message)
                        break
                    self._handle_client_message(event.message)
                elif event.kind == "error":
                    self._set_error(explain_connection_error(event.detail))
                    self.mode = "join_setup"
                    self.selected = 2
                    self.client.close()
                    self.client = None
                    break
                elif event.kind == "protocol_error":
                    self._set_error(f"Protocol error: {event.detail}")
                    self.mode = "join_setup"
                    self.selected = 2
                    self.client.close()
                    self.client = None
                    break
                elif event.kind == "disconnected" and self.mode != "root":
                    self._set_error("The host closed the LAN session")
                    self.mode = "join_setup"
                    self.selected = 2
                    self.client.close()
                    self.client = None
                    break

    def _handle_client_message(self, message):
        payload = message.payload or {}
        message_type = MessageType(message.type)
        if message_type in (MessageType.HELLO_ACCEPTED, MessageType.LOBBY_STATE):
            self.remote_lobby = payload
            self.guest_ready = bool((payload.get("guest") or {}).get("ready"))
            self.mode = "guest_lobby"
            self.selected = 0
            self.game.settings.last_join_host = self.join_host
            self.game.settings_store.save(self.game.settings)
            self.message = "Lobby connected"
            self.message_color = self.game.palette.success
        elif message_type == MessageType.ERROR:
            self._set_error(str(payload.get("message", "The host rejected the request")))
        elif message_type == MessageType.START_MATCH:
            self._match_started = True
            self.game.lan_client_game_loop(self.client, payload)
            self._match_started = False
        elif message_type == MessageType.DISCONNECT:
            self._set_error(str(payload.get("reason", "Host disconnected")))
            self.mode = "join_setup"

    def _cycle_deck(self, direction=1):
        if not self.deck_ids:
            self._set_error("Create a valid deck before joining a LAN match")
            return
        self.deck_index = (self.deck_index + direction) % len(self.deck_ids)
        deck_id = self.deck_ids[self.deck_index]
        if self.mode == "host_lobby":
            try:
                self.lobby.select_host_deck(deck_id)
                self._broadcast_lobby()
            except ValueError as error:
                self._set_error(str(error))
        elif self.client and self.client.peer:
            self.guest_ready = False
            self._send_client(MessageType.SELECT_DECK, {"deck_id": deck_id})

    def _copy_host_address(self):
        address = f"{self.local_ip}:{self.host.port if self.host else self.game.settings.lan_port}"
        try:
            if not pg.scrap.get_init():
                pg.scrap.init()
            pg.scrap.put(pg.SCRAP_TEXT, address.encode("utf-8") + b"\0")
            self.message = f"Copied {address}"
            self.message_color = self.game.palette.success
        except pg.error:
            self.message = f"Address: {address}"
            self.message_color = self.game.palette.muted

    def _activate(self, direction=1):
        if self.mode == "root":
            if self.selected == 0:
                self._start_host()
            elif self.selected == 1:
                self.mode = "join_setup"
                self.selected = 0
            else:
                self._leave()
        elif self.mode == "join_setup":
            if self.selected == 0:
                value = self._text_dialog("Host IP address or name", self.join_host, 253)
                if value and value.strip():
                    self.join_host = value.strip()
            elif self.selected == 1:
                value = self._text_dialog(
                    "LAN port",
                    str(self.game.settings.lan_port),
                    5,
                    str.isdigit,
                )
                if value:
                    port = int(value)
                    if 1024 <= port <= 65535:
                        self.game.settings.lan_port = port
                        self.game.settings_store.save(self.game.settings)
                    else:
                        self._set_error("LAN port must be between 1024 and 65535")
            elif self.selected == 2:
                self._connect()
            else:
                self.mode = "root"
                self.selected = 0
        elif self.mode == "connecting":
            if self.selected == 1:
                self._close_sessions()
                self.mode = "join_setup"
                self.selected = 2
        elif self.mode == "host_lobby":
            if self.selected == 0:
                self._cycle_deck(direction)
            elif self.selected == 1:
                try:
                    if not self.lobby.state.host.deck_id and self.deck_ids:
                        self.lobby.select_host_deck(self.deck_ids[self.deck_index])
                    self.lobby.set_host_ready(not self.lobby.state.host.ready)
                    self._broadcast_lobby()
                except ValueError as error:
                    self._set_error(str(error))
            elif self.selected == 2:
                self._copy_host_address()
            elif self.selected == 4 and self.lobby.state.can_start:
                self._start_host_match()
            elif self.selected == 5:
                self._close_sessions()
                self.mode = "root"
                self.selected = 0
        elif self.mode == "guest_lobby":
            if self.selected == 0:
                self._cycle_deck(direction)
            elif self.selected == 1 and self.client and self.client.peer:
                if not ((self.remote_lobby or {}).get("guest") or {}).get("deck_id"):
                    self._set_error("Select a valid deck before becoming ready")
                    return
                self.guest_ready = not self.guest_ready
                self._send_client(MessageType.READY, {"ready": self.guest_ready})
            elif self.selected == 5:
                self._close_sessions()
                self.mode = "root"
                self.selected = 0

    def _start_host_match(self):
        if not self.host or not self.host.peer or not self.lobby.state.can_start:
            return
        seed = pg.time.get_ticks()
        payload = {
            "match_id": uuid4().hex,
            "seed": seed,
            "starting_player_id": 1 + seed % 2,
            "host_deck_id": self.lobby.state.host.deck_id,
            "guest_deck_id": self.lobby.state.guest.deck_id,
        }
        if not self._send_host(
            MessageType.START_MATCH,
            payload,
            match_id=payload["match_id"],
        ):
            return
        self._match_started = True
        self.game.lan_host_game_loop(self.host, self.lobby, payload)
        self._match_started = False
        self.lobby.state.host.ready = False
        if self.lobby.state.guest:
            self.lobby.state.guest.ready = False
        self._broadcast_lobby()

    def check_input(self):
        rows = self._rows()
        if self.game.BACK_KEY:
            if self.mode == "root":
                self._leave()
            else:
                self._close_sessions()
                self.mode = "root"
                self.selected = 0
            return
        if self.game.UP_KEY:
            self.selected = (self.selected - 1) % len(rows)
        if self.game.DOWN_KEY:
            self.selected = (self.selected + 1) % len(rows)
        if self.game.LEFT_KEY:
            self._activate(-1)
        elif self.game.RIGHT_KEY:
            self._activate(1)
        clicked = self.clicked_button()
        if clicked is not None:
            self.selected = clicked
            self._activate(1)
        elif self.game.START_KEY:
            self._activate(1)

    def _leave(self):
        self._close_sessions()
        self.return_to_previous()

    def _close_sessions(self):
        if self.client:
            self.client.close()
            self.client = None
        if self.host:
            self.host.close()
            self.host = None

    def display_menu(self):
        self.run_display = True
        while self.run_display and self.game.running:
            self.begin_frame()
            self._poll_network()
            rows = self._rows()
            self.selected = min(self.selected, len(rows) - 1)
            self.build_menu_buttons(
                rows,
                self.selected,
                top_ratio=0.27,
                bottom_ratio=0.82,
                width_ratio=0.68,
                enabled=self._enabled(),
            )
            self.check_input()
            if not self.run_display:
                break
            self.draw_background()
            subtitles = {
                "root": "Host an authoritative match or join by IP address",
                "join_setup": "Enter the host's LAN address and port",
                "connecting": "The UI remains responsive while connecting",
                "host_lobby": f"Hosting at {self.local_ip}:{self.host.port if self.host else self.game.settings.lan_port}",
                "guest_lobby": f"Connected to {self.join_host}:{self.game.settings.lan_port}",
            }
            self.draw_title("LAN Match", subtitles.get(self.mode, ""))
            self.draw_buttons()
            self.draw_message(self.message, self.message_color)
            self.blit_screen()
        if not self._match_started:
            self._close_sessions()

    def _text_dialog(self, title, initial, max_length, validator=None):
        return self.prompt_text(
            title,
            initial,
            max_length=max_length,
            validator=validator,
        )
