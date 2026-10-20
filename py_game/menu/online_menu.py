from __future__ import annotations

from math import ceil
from typing import TYPE_CHECKING
from uuid import uuid4

from config import Config
from py_game.menu.base_menu import Menu
from py_game.network.decks import reconstruct_remote_deck, serialize_deck_selection
from py_game.network.lobby import HostLobbyController
from py_game.network.protocol import MessageType
from py_game.network.session import ConnectionState, OnlineClient, hello_payload
from utils.database_utils import DBUtil

if TYPE_CHECKING:
    from py_game.game import Game


class OnlineMenu(Menu):
    """Public relay lobby browser and authoritative two-player lobby."""

    def __init__(self, game: "Game"):
        super().__init__(game)
        self.mode = "connecting"
        self.selected = 0
        self.message = "Connecting to the online lobby server…"
        self.message_color = self.game.palette.muted
        self.session = OnlineClient()
        self.connected = False
        self.role: str | None = None
        self.online_lobby: dict | None = None
        self.lobbies: list[dict] = []
        self.browser_page = 0
        self.server_status: dict = {}
        self.lobby: HostLobbyController | None = None
        self.remote_lobby: dict | None = None
        self.guest_ready = False
        self.deck_options = DBUtil().get_all_deck_options()
        self.deck_ids = [deck_id for deck_id, _name in self.deck_options]
        self.deck_index = 0
        self._match_started = False
        self._guest_handshake_sent = False
        try:
            self.session.connect(Config.lobby_server_url)
        except (OSError, RuntimeError) as error:
            self.mode = "error"
            self._set_error(str(error))

    def _valid_deck(self, deck_id: str) -> bool:
        try:
            deck = DBUtil().load_deck(deck_id)
            return bool(deck and deck.validate())
        except (ValueError, RuntimeError):
            return False

    def _local_deck_descriptor(self, deck_id: str) -> dict:
        return serialize_deck_selection(DBUtil().load_deck(deck_id))

    @staticmethod
    def _reconstruct_guest_deck(descriptor: dict):
        return reconstruct_remote_deck(descriptor, DBUtil().load_card)

    def _deck_label(self, deck_id: str | None) -> str:
        if not deck_id:
            return "No valid decks"
        return next(
            (name for current_id, name in self.deck_options if current_id == deck_id),
            deck_id,
        )

    def _set_error(self, value: str) -> None:
        self.message = value
        self.message_color = self.game.palette.danger

    def _send(self, message_type, payload=None, **metadata) -> bool:
        if not self.session.peer:
            self._set_error("The online server is not connected")
            return False
        try:
            self.session.peer.send(message_type, payload or {}, **metadata)
            return True
        except ConnectionError:
            self._set_error("The online server connection was lost")
            return False

    def _browser_page_size(self) -> int:
        metrics = self.game.layout
        available = int(self.game.DISPLAY_H * 0.55)
        return max(2, min(8, available // metrics.target_height - 3))

    def _browser_page_count(self) -> int:
        return max(1, ceil(len(self.lobbies) / self._browser_page_size()))

    def _visible_lobbies(self) -> list[dict]:
        self.browser_page = min(self.browser_page, self._browser_page_count() - 1)
        size = self._browser_page_size()
        start = self.browser_page * size
        return self.lobbies[start : start + size]

    def _rows(self) -> list[str]:
        if self.mode == "connecting":
            return ["Connecting…", "Back"]
        if self.mode == "error":
            return ["Retry connection", "Back"]
        if self.mode == "browser":
            rows = ["Create lobby", "Refresh lobby list"]
            for item in self._visible_lobbies():
                name = str(item.get("name", "Lobby"))
                host = str(item.get("host_name", "Host"))
                if self.game.DISPLAY_W < 900:
                    name = name[:20]
                    host = host[:12]
                rows.append(
                    f"{'[Locked]' if item.get('protected') else '[Open]'} "
                    f"{name} — {host}"
                )
            if self._browser_page_count() > 1:
                rows.extend(
                    (
                        f"Previous page ({self.browser_page + 1}/{self._browser_page_count()})",
                        f"Next page ({self.browser_page + 1}/{self._browser_page_count()})",
                    )
                )
            rows.append("Back")
            return rows
        if self.mode == "host_lobby":
            state = self.lobby.state
            deck = self._deck_label(self.deck_ids[self.deck_index] if self.deck_ids else None)
            guest = (
                f"{state.guest.name} — {'Ready' if state.guest.ready else 'Not ready'}"
                if state.guest
                else "Waiting for player…"
            )
            return [
                f"Host deck: {deck}",
                f"Host ready: {'Yes' if state.host.ready else 'No'}",
                f"Guest: {guest}",
                "Start match" if state.can_start else "Waiting for both players",
                "Close lobby",
            ]
        if self.mode == "guest_lobby":
            deck = self._deck_label(self.deck_ids[self.deck_index] if self.deck_ids else None)
            host = (self.remote_lobby or {}).get("host") or {}
            return [
                f"Guest deck: {deck}",
                f"Guest ready: {'Yes' if self.guest_ready else 'No'}",
                f"Host: {host.get('name', (self.online_lobby or {}).get('host_name', 'Host'))}",
                f"Host ready: {'Yes' if host.get('ready') else 'No'}",
                "Waiting for host to start",
                "Leave lobby",
            ]
        return ["Back"]

    def _enabled(self) -> list[bool]:
        enabled = [True] * len(self._rows())
        if self.mode == "connecting":
            enabled[0] = False
        elif self.mode == "host_lobby":
            enabled[0] = bool(self.deck_ids)
            enabled[1] = bool(self.deck_ids)
            enabled[2] = False
            enabled[3] = self.lobby.state.can_start
        elif self.mode == "guest_lobby":
            enabled[0] = bool(self.deck_ids)
            enabled[1] = bool(self.deck_ids)
            enabled[2:5] = [False, False, False]
        return enabled

    def _request_lobbies(self) -> None:
        self._send(MessageType.LIST_LOBBIES, {}, request_id=uuid4().hex)

    def _handle_control(self, message) -> None:
        payload = message.payload or {}
        message_type = MessageType(message.type)
        if message_type == MessageType.ONLINE_WELCOME:
            self.connected = True
            self.mode = "browser"
            self.selected = 0
            self.message = "Connected to the lobby server"
            self.message_color = self.game.palette.success
            self._request_lobbies()
        elif message_type == MessageType.LOBBY_LIST:
            self.lobbies = list(payload.get("lobbies") or [])
            self.browser_page = min(self.browser_page, self._browser_page_count() - 1)
        elif message_type == MessageType.SERVER_STATUS:
            self.server_status = payload
        elif message_type == MessageType.ONLINE_LOBBY:
            self.online_lobby = payload
            self.role = payload.get("role")
            self.selected = 0
            if self.role == "host":
                self.mode = "host_lobby"
                if self.lobby is None:
                    self.lobby = HostLobbyController(
                        self.game.settings.player_name,
                        self._valid_deck,
                        self._reconstruct_guest_deck,
                    )
                    if self.deck_ids:
                        try:
                            self.lobby.select_host_deck(self.deck_ids[self.deck_index])
                        except ValueError as error:
                            self._set_error(str(error))
                            return
                if not payload.get("guest_name") and self.lobby.state.guest:
                    self.lobby.state.guest = None
                    self.lobby.guest_deck = None
                    self.lobby.state.status = "waiting_for_player"
                self.message = "Lobby created; waiting for another player"
            else:
                self.mode = "guest_lobby"
                if not self._guest_handshake_sent:
                    self._send(
                        MessageType.HELLO,
                        hello_payload(self.game.settings.player_name),
                        request_id=uuid4().hex,
                    )
                    self._guest_handshake_sent = True
                self.message = "Joined lobby; completing player handshake…"
            self.message_color = self.game.palette.success
        elif message_type == MessageType.ONLINE_LOBBY_CLOSED:
            self._reset_to_browser()
            self._set_error(str(payload.get("reason", "The lobby was closed")))

    def _handle_relay_message(self, message) -> None:
        payload = message.payload or {}
        message_type = MessageType(message.type)
        if message_type == MessageType.ERROR:
            self._set_error(str(payload.get("message", "Online request failed")))
            return
        if self.role == "host" and self.lobby:
            if message_type == MessageType.START_MATCH:
                return
            try:
                response, response_payload = self.lobby.handle(message)
                self._send(
                    response,
                    response_payload,
                    request_id=message.request_id,
                )
            except ValueError as error:
                self._set_error(str(error))
                self._send(
                    MessageType.ERROR,
                    {"message": str(error)},
                    request_id=message.request_id,
                )
            return
        if self.role == "guest":
            if message_type in (MessageType.HELLO_ACCEPTED, MessageType.LOBBY_STATE):
                self.remote_lobby = payload
                self.guest_ready = bool((payload.get("guest") or {}).get("ready"))
                self.mode = "guest_lobby"
                if (
                    message_type == MessageType.HELLO_ACCEPTED
                    and not (payload.get("guest") or {}).get("deck_id")
                    and self.deck_ids
                ):
                    try:
                        descriptor = self._local_deck_descriptor(
                            self.deck_ids[self.deck_index]
                        )
                        self._send(MessageType.SELECT_DECK, {"deck": descriptor})
                        self.message = "Lobby connected; sharing selected deck…"
                    except (ValueError, RuntimeError) as error:
                        self._set_error(str(error))
                        return
                else:
                    self.message = "Online lobby ready"
                self.message_color = self.game.palette.success
            elif message_type == MessageType.START_MATCH:
                self._match_started = True
                self.game.lan_client_game_loop(
                    self.session,
                    payload,
                    network_label="Online",
                    show_latency=True,
                )
                self._match_started = False
            elif message_type == MessageType.DISCONNECT:
                self._reset_to_browser()
                self._set_error(str(payload.get("reason", "The host disconnected")))

    def _poll_network(self) -> None:
        for event in self.session.poll_control():
            if event.message:
                self._handle_control(event.message)
        relay_events = self.session.poll()
        for index, event in enumerate(relay_events):
            if event.kind == "connected" and self.session.peer:
                self._send(
                    MessageType.ONLINE_HELLO,
                    hello_payload(self.game.settings.player_name),
                    request_id=uuid4().hex,
                )
            elif event.kind == "message" and event.message:
                if event.message.type == MessageType.START_MATCH.value and self.role == "guest":
                    for pending in relay_events[index + 1 :]:
                        self.session._relay_events.put(pending)
                    self._handle_relay_message(event.message)
                    break
                self._handle_relay_message(event.message)
            elif event.kind in ("error", "protocol_error", "disconnected"):
                if self.run_display:
                    self.mode = "error"
                    self.selected = 0
                    self._set_error(event.detail or "The online server disconnected")
                break

    def _create_lobby(self) -> None:
        default_name = f"{self.game.settings.player_name}'s lobby"
        name = self._text_dialog("Lobby name", default_name, 40)
        if name is None or not name.strip():
            return
        password = self._text_dialog(
            "Password (empty creates a public lobby)",
            "",
            64,
            masked=True,
        )
        if password is None:
            return
        self._send(
            MessageType.CREATE_ONLINE_LOBBY,
            {"name": name.strip(), "password": password},
            request_id=uuid4().hex,
        )
        self.message = "Creating lobby…"
        self.message_color = self.game.palette.muted

    def _join_lobby(self, lobby: dict) -> None:
        password = ""
        if lobby.get("protected"):
            password = self._text_dialog("Lobby password", "", 64, masked=True)
            if password is None:
                return
        self._guest_handshake_sent = False
        self._send(
            MessageType.JOIN_ONLINE_LOBBY,
            {"lobby_id": lobby.get("lobby_id"), "password": password},
            request_id=uuid4().hex,
        )
        self.message = "Joining lobby…"
        self.message_color = self.game.palette.muted

    def _cycle_deck(self, direction=1) -> None:
        if not self.deck_ids:
            self._set_error("Create a valid deck before playing online")
            return
        self.deck_index = (self.deck_index + direction) % len(self.deck_ids)
        deck_id = self.deck_ids[self.deck_index]
        if self.role == "host":
            try:
                self.lobby.select_host_deck(deck_id)
                self._send(MessageType.LOBBY_STATE, self.lobby.state.public_payload())
            except ValueError as error:
                self._set_error(str(error))
        else:
            try:
                descriptor = self._local_deck_descriptor(deck_id)
            except (ValueError, RuntimeError) as error:
                self._set_error(str(error))
                return
            self.guest_ready = False
            self._send(MessageType.SELECT_DECK, {"deck": descriptor})

    def _start_host_match(self) -> None:
        if not self.session.peer or not self.lobby or not self.lobby.state.can_start:
            return
        if self.lobby.guest_deck is None:
            self.lobby.state.guest.ready = False
            self.lobby._update_status()
            self._set_error("The guest deck composition is unavailable; select it again")
            self._send(MessageType.LOBBY_STATE, self.lobby.state.public_payload())
            return
        import pygame as pg

        seed = pg.time.get_ticks()
        payload = {
            "match_id": uuid4().hex,
            "seed": seed,
            "starting_player_id": 1 + seed % 2,
            "host_deck_id": self.lobby.state.host.deck_id,
            "guest_deck_id": self.lobby.state.guest.deck_id,
        }
        if not self._send(MessageType.START_MATCH, payload, match_id=payload["match_id"]):
            return
        self._match_started = True
        self.game.lan_host_game_loop(
            self.session,
            self.lobby,
            payload,
            network_label="Online",
            show_latency=True,
        )
        self._match_started = False
        self.lobby.state.host.ready = False
        if self.lobby.state.guest:
            self.lobby.state.guest.ready = False
        self._send(MessageType.LOBBY_STATE, self.lobby.state.public_payload())

    def _leave_lobby(self) -> None:
        self._send(MessageType.LEAVE_ONLINE_LOBBY, {})
        self._reset_to_browser()
        self._request_lobbies()

    def _reset_to_browser(self) -> None:
        self.role = None
        self.online_lobby = None
        self.lobby = None
        self.remote_lobby = None
        self.guest_ready = False
        self._guest_handshake_sent = False
        self.mode = "browser" if self.connected else "connecting"
        self.selected = 0

    def _activate_browser(self) -> None:
        visible = self._visible_lobbies()
        if self.selected == 0:
            self._create_lobby()
        elif self.selected == 1:
            self._request_lobbies()
            self.message = "Refreshing lobby list…"
        elif 2 <= self.selected < 2 + len(visible):
            self._join_lobby(visible[self.selected - 2])
        else:
            cursor = 2 + len(visible)
            if self._browser_page_count() > 1:
                if self.selected == cursor:
                    self.browser_page = max(0, self.browser_page - 1)
                    self.selected = 0
                    return
                if self.selected == cursor + 1:
                    self.browser_page = min(
                        self._browser_page_count() - 1,
                        self.browser_page + 1,
                    )
                    self.selected = 0
                    return
            self._leave_menu()

    def _activate(self, direction=1) -> None:
        if self.mode == "browser":
            self._activate_browser()
        elif self.mode == "host_lobby":
            if self.selected == 0:
                self._cycle_deck(direction)
            elif self.selected == 1:
                try:
                    if not self.lobby.state.host.deck_id and self.deck_ids:
                        self.lobby.select_host_deck(self.deck_ids[self.deck_index])
                    self.lobby.set_host_ready(not self.lobby.state.host.ready)
                    self._send(MessageType.LOBBY_STATE, self.lobby.state.public_payload())
                except ValueError as error:
                    self._set_error(str(error))
            elif self.selected == 3:
                self._start_host_match()
            elif self.selected == 4:
                self._leave_lobby()
        elif self.mode == "guest_lobby":
            if self.selected == 0:
                self._cycle_deck(direction)
            elif self.selected == 1:
                if not ((self.remote_lobby or {}).get("guest") or {}).get("deck_id"):
                    self._set_error("Select a valid deck before becoming ready")
                    return
                self.guest_ready = not self.guest_ready
                self._send(MessageType.READY, {"ready": self.guest_ready})
            elif self.selected == 5:
                self._leave_lobby()
        elif self.mode == "error" and self.selected == 0:
            self.session.close()
            self.session = OnlineClient()
            self.mode = "connecting"
            self.session.connect(Config.lobby_server_url)
        elif self.selected == len(self._rows()) - 1:
            self._leave_menu()

    def check_input(self) -> None:
        rows = self._rows()
        if self.game.BACK_KEY:
            if self.mode in ("host_lobby", "guest_lobby"):
                self._leave_lobby()
            else:
                self._leave_menu()
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
            self._activate()
        elif self.game.START_KEY:
            self._activate()

    def _draw_server_status(self) -> None:
        if not self.server_status:
            return
        load = self.server_status.get("load", "low")
        color = {
            "low": self.game.palette.success,
            "medium": self.game.palette.accent,
            "high": self.game.palette.danger,
        }.get(load, self.game.palette.muted)
        connected = self.server_status.get("connected_players", 0)
        maximum = self.server_status.get("max_players", "?")
        matches = self.server_status.get("active_matches", 0)
        label = (
            f"Server: {load}"
            if self.game.DISPLAY_W < 900
            else f"Server {load} • {connected}/{maximum} players • {matches} matches"
        )
        self.game.draw_text_left(
            label,
            max(11, self.game.layout.font_small - 2),
            self.game.layout.margin,
            self.game.DISPLAY_H - self.game.layout.margin,
            color,
        )

    def _leave_menu(self) -> None:
        if self.role:
            self._send(MessageType.LEAVE_ONLINE_LOBBY, {})
        self.run_display = False
        self.session.close()
        self.game.curr_menu = self.previous_menu
        if self.previous_menu is not None:
            self.previous_menu.run_display = True

    def display_menu(self) -> None:
        self.run_display = True
        while self.run_display and self.game.running:
            self.begin_frame()
            self._poll_network()
            rows = self._rows()
            self.selected = min(self.selected, len(rows) - 1)
            self.build_menu_buttons(
                rows,
                self.selected,
                top_ratio=0.25,
                bottom_ratio=0.80,
                width_ratio=0.72,
                enabled=self._enabled(),
            )
            self.check_input()
            if not self.run_display:
                break
            self.draw_background()
            subtitle = {
                "connecting": f"Connecting to {Config.lobby_server_url}",
                "error": "The server could not be reached",
                "browser": "Create a lobby or join an open match",
                "host_lobby": (self.online_lobby or {}).get("name", "Online lobby"),
                "guest_lobby": (self.online_lobby or {}).get("name", "Online lobby"),
            }.get(self.mode, "")
            self.draw_title("Online Match", subtitle)
            self.draw_buttons()
            self.draw_message(self.message, self.message_color)
            self._draw_server_status()
            self.blit_screen()
        if not self._match_started and self.session.state != ConnectionState.CLOSED:
            self.session.close()

    def _text_dialog(self, title, initial, max_length, *, masked=False):
        return self.prompt_text(
            title,
            initial,
            max_length=max_length,
            masked=masked,
        )
