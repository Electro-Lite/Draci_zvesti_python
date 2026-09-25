from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

import pygame as pg

from py_game.match_setup import (
    ControllerKind,
    ControllerSpec,
    create_player,
    discover_player_artifacts,
    validate_match_setup,
)
from py_game.menu.base_menu import Menu
from utils.database_utils import DBUtil

if TYPE_CHECKING:
    from py_game.game import Game


class PlayMenuState(Enum):
    P1_CONTROLLER = 0
    P1_DECK = 1
    P1_MODEL = 2
    P2_CONTROLLER = 3
    P2_DECK = 4
    P2_MODEL = 5
    START = 6
    BACK = 7


class BasicPlayMenu(Menu):
    def __init__(self, game: "Game"):
        super().__init__(game)
        self.previous_menu = None
        self.state_index = 0
        self.states = list(PlayMenuState)
        self.controller_kinds = list(ControllerKind)
        self.p1_controller_index = 0
        self.p2_controller_index = 1
        self.p1_deck_id = None
        self.p2_deck_id = None
        self.p1_model_index = 0
        self.p2_model_index = 0
        self.artifacts = discover_player_artifacts()
        self.deck_ids = DBUtil().get_all_deck_ids()
        self.message = ""
        self.message_color = self.game.WHITE
        self.row_y = self.mid_h - 70
        self.row_gap = 35
        self.offset = -180

    @property
    def state(self):
        return self.states[self.state_index]

    def _controller(self, player_number: int) -> ControllerKind:
        index = (
            self.p1_controller_index
            if player_number == 1
            else self.p2_controller_index
        )
        return self.controller_kinds[index]

    def _model_path(self, player_number: int) -> str | None:
        if not self.artifacts:
            return None
        index = self.p1_model_index if player_number == 1 else self.p2_model_index
        return str(self.artifacts[index % len(self.artifacts)])

    def _controller_spec(self, player_number: int) -> ControllerSpec:
        kind = self._controller(player_number)
        model = self._model_path(player_number) if kind == ControllerKind.TRAINED_AI else None
        return ControllerSpec(kind, model)

    def _cycle(self, attribute: str, count: int, direction: int):
        if count:
            setattr(self, attribute, (getattr(self, attribute) + direction) % count)

    def _handle_horizontal(self, direction: int):
        if self.state == PlayMenuState.P1_CONTROLLER:
            self._cycle("p1_controller_index", len(self.controller_kinds), direction)
        elif self.state == PlayMenuState.P2_CONTROLLER:
            self._cycle("p2_controller_index", len(self.controller_kinds), direction)
        elif self.state == PlayMenuState.P1_MODEL:
            self._cycle("p1_model_index", len(self.artifacts), direction)
        elif self.state == PlayMenuState.P2_MODEL:
            self._cycle("p2_model_index", len(self.artifacts), direction)

    def _choose_deck(self, player_number: int):
        choice = self.select_deck_dialog(
            f"Choose Player {player_number} Deck",
            self.deck_ids,
        )
        if choice is not None:
            if player_number == 1:
                self.p1_deck_id = choice
            else:
                self.p2_deck_id = choice

    def _start_match(self):
        db = DBUtil()
        deck_1 = db.load_deck(self.p1_deck_id) if self.p1_deck_id else None
        deck_2 = db.load_deck(self.p2_deck_id) if self.p2_deck_id else None
        spec_1 = self._controller_spec(1)
        spec_2 = self._controller_spec(2)
        try:
            validate_match_setup(deck_1, deck_2, spec_1, spec_2)
            if spec_1.kind == ControllerKind.TRAINED_AI:
                create_player(1, deck_1, spec_1)
            if spec_2.kind == ControllerKind.TRAINED_AI:
                create_player(2, deck_2, spec_2)
        except ValueError as error:
            self.message = str(error)
            self.message_color = (235, 105, 105)
            return

        self.game.p1_deck_id = self.p1_deck_id
        self.game.p2_deck_id = self.p2_deck_id
        self.game.p1_controller = spec_1
        self.game.p2_controller = spec_2
        self.run_display = False
        self.game.curr_menu = None
        self.game.playing = True
        self.game.game_loop()
        if self.game.running:
            self.game.curr_menu = self
            self.run_display = True

    def _return(self):
        self.return_to_previous()

    def _activate_current(self):
        if self.state == PlayMenuState.P1_DECK:
            self._choose_deck(1)
        elif self.state == PlayMenuState.P2_DECK:
            self._choose_deck(2)
        elif self.state in (
            PlayMenuState.P1_CONTROLLER,
            PlayMenuState.P2_CONTROLLER,
            PlayMenuState.P1_MODEL,
            PlayMenuState.P2_MODEL,
        ):
            self._handle_horizontal(1)
        elif self.state == PlayMenuState.START:
            self._start_match()
        elif self.state == PlayMenuState.BACK:
            self._return()

    def check_input(self):
        if self.game.LEFT_KEY:
            self._handle_horizontal(-1)
        if self.game.RIGHT_KEY:
            self._handle_horizontal(1)
        if self.game.UP_KEY:
            self.state_index = (self.state_index - 1) % len(self.states)
        if self.game.DOWN_KEY:
            self.state_index = (self.state_index + 1) % len(self.states)
        if self.game.BACK_KEY:
            self._return()
            return
        clicked = self.clicked_button()
        if clicked is not None:
            self.state_index = clicked
            self._activate_current()
        elif self.game.START_KEY:
            self._activate_current()

    def _model_label(self, player_number: int) -> str:
        if self._controller(player_number) != ControllerKind.TRAINED_AI:
            return "Not used"
        if not self.artifacts:
            return "No player models found"
        return self.artifacts[
            self.p1_model_index if player_number == 1 else self.p2_model_index
        ].stem

    def display_menu(self):
        self.run_display = True
        self.game.reset_keys()
        while self.run_display and self.game.running:
            self.begin_frame()
            labels = [
                f"Player 1: {self._controller(1).value}",
                f"Player 1 deck: {self.p1_deck_id or 'Select deck'}",
                f"Player 1 model: {self._model_label(1)}",
                f"Player 2: {self._controller(2).value}",
                f"Player 2 deck: {self.p2_deck_id or 'Select deck'}",
                f"Player 2 model: {self._model_label(2)}",
                "Start match",
                "Back",
            ]
            enabled = [
                True,
                True,
                self._controller(1) == ControllerKind.TRAINED_AI,
                True,
                True,
                self._controller(2) == ControllerKind.TRAINED_AI,
                True,
                True,
            ]
            self.build_menu_buttons(
                labels,
                self.state_index,
                top_ratio=0.20,
                bottom_ratio=0.88,
                width_ratio=0.70,
                enabled=enabled,
            )
            self.check_input()
            if not self.run_display:
                break
            self.draw_background()
            self.draw_title("Local Match", "Choose decks and controllers for both players")
            self.draw_buttons()
            self.draw_message(self.message, self.message_color)
            self.blit_screen()

    def select_deck_dialog(self, title: str, deck_ids: list[str]) -> str | None:
        if not deck_ids:
            self.message = "Create a valid deck before starting a match"
            self.message_color = (235, 105, 105)
            return None

        selected = 0
        offset = 0
        page_size = 8
        while True:
            self.begin_frame()
            for event in self.game.events:
                if event.type == pg.QUIT:
                    self.game.running = False
                    return None
                if event.type == pg.KEYDOWN:
                    if event.key in (pg.K_ESCAPE, pg.K_BACKSPACE):
                        return None
                    if event.key in (pg.K_RETURN, pg.K_SPACE):
                        return deck_ids[selected]
                    if event.key == pg.K_UP:
                        selected = (selected - 1) % len(deck_ids)
                    if event.key == pg.K_DOWN:
                        selected = (selected + 1) % len(deck_ids)
                elif event.type == pg.MOUSEWHEEL:
                    selected = (selected - event.y) % len(deck_ids)

            if selected < offset:
                offset = selected
            elif selected >= offset + page_size:
                offset = selected - page_size + 1

            panel_spec = self.game.layout.centered_panel(0.64, 0.78)
            panel = pg.Rect(panel_spec.x, panel_spec.y, panel_spec.width, panel_spec.height)
            self.game.display.fill(self.game.palette.background)
            pg.draw.rect(self.game.display, (22, 25, 28), panel)
            pg.draw.rect(self.game.display, (105, 115, 125), panel, 2)
            self.game.draw_text(
                title,
                self.TEXT_LARGE,
                self.mid_w,
                panel.y + self.game.layout.margin,
            )
            visible = deck_ids[offset : offset + page_size]
            list_top = panel.y + self.game.layout.font_large + self.game.layout.margin * 2
            row_height = max(34, (panel.bottom - list_top - self.game.layout.margin) // page_size)
            row_rects = []
            for row, deck_id in enumerate(visible):
                absolute_index = offset + row
                rect = pg.Rect(panel.x + self.game.layout.margin, list_top + row * row_height, panel.width - self.game.layout.margin * 2, row_height - 4)
                row_rects.append((absolute_index, rect))
                hovered = rect.collidepoint(self.game.mouse_position)
                pg.draw.rect(
                    self.game.display,
                    self.game.palette.selected if absolute_index == selected else self.game.palette.hover if hovered else self.game.palette.panel_alt,
                    rect,
                    border_radius=6,
                )
                self.game.draw_text_left(
                    deck_id,
                    self.TEXT_NORMAL,
                    rect.x + self.game.layout.gap,
                    rect.centery,
                    self.game.ORANGE if absolute_index == selected else self.game.WHITE,
                    rect.width - self.game.layout.gap * 2,
                )
            if self.game.mouse_clicked:
                for absolute_index, rect in row_rects:
                    if rect.collidepoint(self.game.mouse_position):
                        return deck_ids[absolute_index]
            self.game.window.blit(self.game.display, (0, 0))
            pg.display.update()
            self.game.reset_keys()
            self.game.clock.tick(60)
