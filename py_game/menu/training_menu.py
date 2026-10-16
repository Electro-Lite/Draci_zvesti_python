from __future__ import annotations

import json
import math
import queue
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import pygame as pg

from neat_ai.player_artifacts import discover_player_artifacts as discover_manifest_artifacts
from neat_ai.training_plan import matchup_checkpoints
from py_game.counter_presentation import (
    COMPARISON_TARGET,
    CounterCandidate,
    CounterDeckSnapshot,
    CounterPresentation,
    counter_bar_segments,
)
from py_game.deck_editor import DeckBuilderMenu
from py_game.deck_adoption import (
    AdoptableDeck,
    AdoptionReceipt,
    DeckAdoptionConflict,
    DeckAdoptionError,
    DeckAdoptionService,
)
from py_game.evolution_presentation import EvolutionDeck, EvolutionPresentation
from py_game.menu.base_menu import Menu
from py_game.training_service import (
    TrainingKind,
    TrainingInsights,
    TrainingJob,
    TrainingRequest,
    TrainingRunSummary,
    TrainingTelemetry,
    TrainingService,
)
from utils.database_utils import DBUtil
from py_game.ui.layout import RectSpec
from py_game.ui.counter_dashboard import counter_dashboard_layout
from py_game.ui.evolution_dashboard import evolution_dashboard_layout
from py_game.ui.matchup_dashboard import matchup_dashboard_layout
from py_game.ui.training_progress import training_progress_layout
from py_game.ui.training_dashboard import training_dashboard_layout
from py_game.ui.training_cockpit import (
    TrainingCockpitState,
    training_cockpit_layout,
)
from py_game.ui.training_setup import (
    presets_for,
    training_workload,
    wilson_interval,
)
from py_game.ui.training_runs import (
    GENERATION_FILTERS,
    MISSION_FILTERS,
    ORIGIN_FILTERS,
    SORT_FIELDS,
    STARTED_FILTERS,
    STATUS_FILTERS,
    RunFilters,
    combined_runs,
    paginate_runs,
    query_runs,
    run_id,
    run_mission,
    run_started,
    run_status,
    run_title,
)
from py_game.ui.widgets import Button, TextInput
from py_game.training_lifecycle import (
    ACTIVE_STATUSES,
    ArenaDestination,
    ResultArtifactStatus,
    arena_destination,
    eta_label,
    mission_progress_name,
    mission_result_label,
    overall_progress,
    progress_levels,
)

if TYPE_CHECKING:
    from py_game.game import Game


class TrainingMenu(Menu):
    """Professor-facing setup, monitoring, and compact result browser."""

    PLAYER_GENERATIONS = [10, 25, 40, 65]
    BUILDER_GENERATIONS = [35, 50, 65]
    WORKERS = [4, 8, 12]
    MATCH_COUNTS = [4, 8, 12]
    HOLDOUT_COUNTS = [5, 10, 20]
    EVALUATION_GAMES = [100, 1_000, 2_000]
    BUILDER_DASHBOARD_PAGES = ("Overview", "Population", "Matchups", "Conclusions")
    PLAYER_DASHBOARD_PAGES = ("Overview", "Learning", "Evaluation", "Conclusions")
    DASHBOARD_PAGES = BUILDER_DASHBOARD_PAGES
    SEED_SETS = [
        (104729,),
        (400009,),
        (400009, 450001, 500009, 550007),
    ]
    ABOUT_PAGES = (
        (
            "Counter-deck lab",
            "Stress-test one deck against opponents that keep adapting",
            (
                ("Training type", "Choose counter-deck training, a two-deck matchup, or general deck evolution."),
                ("Run label", "Defaults to mission_preset_YYMMDD-HH_deck_run-ID and remains editable."),
                ("Deck under test", "Your selected deck stays fixed while a population evolves decks designed to counter it."),
                ("Counter generations", "How many generations of counter-deck candidates survive, mutate, and improve."),
                ("Controller generations", "Both sides keep the same evolving controller populations across every counter generation; progress is not reset between opponents."),
                ("Games per counter", "Use at least 1,000 seat-balanced games for a comparison run. Smaller diagnostics remain exploratory."),
                ("Results", "Overall deck win rate aggregates the final counter population; Top counter is the opponent deck with the highest win rate against your deck."),
            ),
        ),
        (
            "Matchup evaluation",
            "Coevolve players for two fixed decks",
            (
                ("Deck A and Deck B", "The two fixed decks whose controllers learn directly against each other."),
                ("Controller generations", "Both player populations evolve together; checkpoint results show how the matchup changes as play improves."),
                ("Games per checkpoint", "Use at least 1,000 seat-balanced holdout games for comparison; smaller checkpoints remain exploratory."),
                ("What it answers", "Use this when you want a direct deck-vs-deck win-rate curve rather than new deck construction."),
                ("Workers", "Parallel match processes; 4 is gentle, 8 balanced, and 12 suits a capable machine."),
            ),
        ),
        (
            "General deck evolution",
            "Evolve a broad population without one fixed target deck",
            (
                ("Seeds", "One seed iterates quickly; four seeds give stronger, more reproducible evidence."),
                ("Outer generations", "Deck evolution cycles; use 1 while tuning and 10 for a final study."),
                ("Inner generations", "Controller training per candidate deck; 50 is the recommended balance."),
                ("Rival decks per candidate", "How many other evolved decks each candidate faces in an outer generation. More rivals reduce schedule luck but cost more; the value must be even so seats stay balanced."),
                ("Evaluator workers", "Parallel inner matches; choose 8 normally or 12 with ample CPU and RAM."),
                ("Holdout seed pairs", "Unseen checks against overfitting; keep 20 for reported results."),
            ),
        ),
        (
            "Recommended missions",
            "Choose the cost and confidence level you actually need",
            (
                ("Quick smoke test", "10 player generations, 4 workers, 100 evaluation games; exploratory pipeline check."),
                ("Balanced counter lab", "5 counter generations, 40 persistent controller generations, and 1,000 games per candidate."),
                ("Balanced matchup", "40 generations, 8 workers, and 1,000 seat-balanced games per checkpoint."),
                ("Deck-builder rehearsal", "1 outer generation, 50 inner, 12 matches, one seed; catch setup issues."),
                ("Final deck study", "10 outer, 65 inner, 12 matches, four seeds, 20 holdouts; expect a long run."),
                ("Arena sections", "Overview shows live operation; Learning, Evaluation, and Conclusions explain results."),
            ),
        ),
    )

    def __init__(self, game: "Game"):
        super().__init__(game)
        self.previous_menu = None
        self.service = getattr(game, "training_service", None) or TrainingService()
        self.view = "setup"
        self.selected = 0
        self.deck_options = DBUtil().get_all_deck_options()
        self.deck_ids = [deck_id for deck_id, _name in self.deck_options]
        self.cockpit = TrainingCockpitState(self.deck_ids)
        self.setup_focus_key = "mission_counter"
        self.setup_scroll = 0
        self.setup_layout = None
        self.setup_edit_key = None
        self.setup_edit_original = ""
        self.setup_edit_original_preset = None
        self.setup_edit_original_auto_label = False
        self.setup_picker_key = None
        self.setup_picker_index = 0
        self.setup_review_open = False
        self.setup_review_request = None
        self.setup_review_selected = 0
        self.setup_starting = False
        self.message = ""
        self.message_color = self.game.WHITE
        self.jobs = []
        self.database_runs = []
        self._linked_database_run_ids = set()
        self.last_refresh = 0
        self._refresh_results = queue.Queue()
        self._refresh_thread = None
        self._launch_results = queue.Queue()
        self._launch_thread = None
        self._stop_results = queue.Queue()
        self._stop_thread = None
        self._visible_offset = 0
        self.run_search = TextInput(max_length=64)
        self.run_search_rect = RectSpec(0, 0, 0, 0)
        self.run_sort_index = 0
        self.run_sort_descending = True
        self.run_page = 0
        self.run_selected = 0
        self.run_buttons = []
        self.run_page_items = []
        self.run_filter_status_index = 0
        self.run_filter_mission_index = 0
        self.run_filter_origin_index = 0
        self.run_filter_started_index = 0
        self.run_filter_generations_index = 0
        self.run_filter_open = False
        self.run_filter_selected = 0
        self.run_filter_pending_status = 0
        self.run_filter_pending_mission = 0
        self.run_filter_pending_origin = 0
        self.run_filter_pending_started = 0
        self.run_filter_pending_generations = 0
        self.run_filter_buttons = []
        self.dashboard_item = None
        self.dashboard_action = 0
        self.dashboard_page = 0
        self.dashboard_telemetry = None
        self.dashboard_insights = None
        self.dashboard_buttons = []
        self.dashboard_scroll = 0
        self.dashboard_max_scroll = 0
        self.dashboard_watching_live = False
        self.dashboard_results_opened = False
        self.dashboard_artifact_status = None
        self.counter_candidate_key = None
        self.counter_candidate_scroll = 0
        self.counter_candidate_keys = ()
        self.counter_candidate_rects = []
        self.counter_candidate_viewport = None
        self.counter_candidate_capacity = 1
        self.counter_focus = "candidates"
        self.evolution_selected_deck_id = None
        self.evolution_generation_filter = None
        self.evolution_deck_scroll = 0
        self.evolution_deck_keys = ()
        self.evolution_deck_rects = []
        self.evolution_deck_viewport = None
        self.evolution_focus = "decks"
        self.adoption_source = None
        self.adoption_input = TextInput(max_length=32)
        self.adoption_error = ""
        self.adoption_conflict_id = None
        self.adoption_receipt = None
        self.adoption_buttons = []
        self.adoption_action = 1
        self._insight_results = queue.Queue()
        self._insight_thread = None
        self.about_page = 0
        self.about_buttons = []
        self._dashboard_last_refresh = -1000
        self._refresh_runs(force=True)

    @property
    def kind(self):
        return self.cockpit.kind

    @staticmethod
    def _mission_label(kind):
        if kind == TrainingKind.PLAYER_DECK or kind == TrainingKind.PLAYER_DECK.value:
            return "Train counters against a deck"
        if kind == TrainingKind.MATCHUP_EVALUATION or kind == TrainingKind.MATCHUP_EVALUATION.value:
            return "Evaluate a two-deck matchup"
        if kind == TrainingKind.DECK_BUILDER or kind == TrainingKind.DECK_BUILDER.value:
            return "Evolve and study decks"
        return "AI training"

    def _generation_options(self):
        return self.BUILDER_GENERATIONS if self.kind == TrainingKind.DECK_BUILDER else self.PLAYER_GENERATIONS

    def _generation(self):
        try:
            return int(self.cockpit.value("evaluator_generations"))
        except ValueError:
            return 0

    def _preset_options(self):
        return presets_for(self.kind)

    def _preset_label(self):
        return self.cockpit.preset_label

    def _preset_summary(self):
        if self.kind == TrainingKind.PLAYER_DECK:
            return (
                f"{self.cockpit.value('outer_generations')} counter · "
                f"{self._generation()} controller gen"
            )
        if self.kind == TrainingKind.MATCHUP_EVALUATION:
            return f"{self._generation()} gen · {self.cockpit.value('evaluation_games')}/checkpoint"
        return f"{self.cockpit.value('outer_generations')} outer · {self._generation()} inner gen"

    def _apply_preset(self, index=None):
        if index is None:
            index = self.cockpit.draft.preset_index
        self.cockpit.apply_preset(index)

    def _mark_custom_preset(self):
        self.cockpit.apply_preset(None)

    def _request(self):
        validation = self.cockpit.validate()
        if validation.request is None:
            first = next(iter(validation.errors.values()), "Training request is incomplete")
            raise ValueError(first)
        return validation.request

    def _setup_rows(self):
        """Compatibility summary for non-interactive callers and older tooling."""
        validation = self.cockpit.validate()
        rows = [
            ("Back", "back"),
            ("Run library", "runs"),
            ("Training guide & recommended use", "about"),
            (f"Mission: {self._mission_label(self.kind)}", "mission"),
            (f"Preset: {self._preset_label()}", "preset"),
        ]
        for key in self.cockpit.field_keys:
            value = self.cockpit.value(key)
            if key in {"deck_id", "opponent_deck_id"}:
                value = self._deck_label(value)
            rows.append((f"{key}: {value}", key))
        rows.append(("Review and launch", "launch" if validation.valid else "invalid"))
        return rows

    def _deck_label(self, deck_id: str | None) -> str:
        if not deck_id:
            return "No decks available"
        return next(
            (
                name
                for current_id, name in getattr(self, "deck_options", ())
                if current_id == deck_id
            ),
            deck_id,
        )

    def _run_rows(self):
        return [
            (f"{run_id(item)}  {run_title(item)}  [{run_status(item)}]", item)
            for item in combined_runs(
                self.service,
                self.jobs,
                self.database_runs,
                self._linked_database_run_ids,
            )
        ]

    def _run_filters(self):
        return RunFilters(
            status=STATUS_FILTERS[self.run_filter_status_index],
            mission=MISSION_FILTERS[self.run_filter_mission_index],
            origin=ORIGIN_FILTERS[self.run_filter_origin_index],
            started=STARTED_FILTERS[self.run_filter_started_index],
            generations=GENERATION_FILTERS[self.run_filter_generations_index],
        )

    def _queried_runs(self):
        return query_runs(
            combined_runs(
                self.service,
                self.jobs,
                self.database_runs,
                self._linked_database_run_ids,
            ),
            search=self.run_search.value,
            sort_field=SORT_FIELDS[self.run_sort_index],
            descending=self.run_sort_descending,
            filters=self._run_filters(),
        )

    def _run_library_layout(self):
        metrics = self.game.layout
        width = min(
            self.game.DISPLAY_W - metrics.margin * 2,
            round(1080 * max(1.0, metrics.scale)),
        )
        x = (self.game.DISPLAY_W - width) // 2
        top = metrics.margin + metrics.font_large + metrics.font_small + metrics.gap * 3
        control_height = metrics.target_height
        back = RectSpec(x, top, width, control_height)
        search = RectSpec(x, back.bottom + metrics.gap, width, control_height)
        toolbar = RectSpec(x, search.bottom + metrics.gap, width, control_height)
        list_top = toolbar.bottom + metrics.gap
        listing = RectSpec(
            x,
            list_top,
            width,
            max(1, self.game.DISPLAY_H - metrics.margin - list_top),
        )
        return {"back": back, "search": search, "toolbar": toolbar, "list": listing}

    @staticmethod
    def _run_library_label(item):
        # UI job IDs already contain the run label, so showing both repeats the
        # same long text and forces it to an unreadably small size. Database
        # runs retain their compact "DB N" identity because it is not part of
        # their title.
        identity = "" if isinstance(item, TrainingJob) else f"{run_id(item)}  "
        return f"{identity}{run_title(item)}  [{run_status(item)}]"

    def _fitted_text_size(self, text, preferred_size, max_width, minimum=8):
        """Choose the largest font size whose rendered text fits max_width."""
        size = max(minimum, int(preferred_size))
        while (
            size > minimum
            and pg.font.Font(self.game.font_name, size).size(str(text))[0]
            > max_width
        ):
            size -= 1
        return size

    def _prepare_run_view(self):
        layout = self._run_library_layout()
        queried = self._queried_runs()
        page_items, self.run_page, page_count = paginate_runs(
            queried,
            self.run_page,
            10,
        )
        self.run_page_items = page_items
        self.run_selected = max(
            0,
            min(self.run_selected, max(0, len(page_items) - 1)),
        )
        mouse = self.game.mouse_position
        metrics = self.game.layout
        self.run_search_rect = layout["search"]
        toolbar = layout["toolbar"]
        columns = metrics.columns(toolbar, (0.24, 0.20, 0.20, 0.36))
        pager = metrics.columns(columns[3], (0.20, 0.60, 0.20), gap=max(2, metrics.gap // 2))
        filters = self._run_filters()
        control_specs = (
            ("back", "Back", layout["back"], True),
            (
                "sort",
                f"Sort by: {SORT_FIELDS[self.run_sort_index]}",
                columns[0],
                True,
            ),
            (
                "order",
                "Order: Desc" if self.run_sort_descending else "Order: Asc",
                columns[1],
                True,
            ),
            (
                "filter",
                f"Filter ({filters.active_count})" if filters.active_count else "Filter",
                columns[2],
                True,
            ),
            ("previous_page", "<", pager[0], self.run_page > 0),
            ("page", f"Page {self.run_page + 1}/{page_count}", pager[1], False),
            ("next_page", ">", pager[2], self.run_page + 1 < page_count),
        )
        self.run_buttons = [
            Button(
                key,
                label,
                rect,
                enabled=enabled,
                hovered=rect.contains(mouse),
            )
            for key, label, rect, enabled in control_specs
        ]
        row_gap = max(3, metrics.gap // 3)
        rows = metrics.vertical_rows(
            10,
            layout["list"],
            gap=row_gap,
        )
        for index, (item, rect) in enumerate(zip(page_items, rows)):
            self.run_buttons.append(
                Button(
                    f"run:{index}",
                    self._run_library_label(item),
                    rect,
                    selected=index == self.run_selected,
                    hovered=rect.contains(mouse),
                )
            )
        self._prepare_filter_buttons()
        return layout, queried, page_count

    def _prepare_filter_buttons(self):
        metrics = self.game.layout
        panel = metrics.centered_panel(0.72, 0.82, max_width=820)
        top = panel.y + metrics.margin + metrics.font_large + metrics.gap * 2
        area = RectSpec(
            panel.x + metrics.margin,
            top,
            panel.width - metrics.margin * 2,
            panel.bottom - metrics.margin - top,
        )
        rows = metrics.vertical_rows(8, area, gap=max(4, metrics.gap // 2))
        labels = (
            ("filter_status", f"Status: {STATUS_FILTERS[self.run_filter_pending_status]}"),
            ("filter_mission", f"Mission: {MISSION_FILTERS[self.run_filter_pending_mission]}"),
            ("filter_origin", f"Origin: {ORIGIN_FILTERS[self.run_filter_pending_origin]}"),
            ("filter_started", f"Started: {STARTED_FILTERS[self.run_filter_pending_started]}"),
            (
                "filter_generations",
                f"Generations: {GENERATION_FILTERS[self.run_filter_pending_generations]}",
            ),
            ("filter_clear", "Clear filters"),
            ("filter_cancel", "Cancel"),
            ("filter_apply", "Apply filters"),
        )
        self.run_filter_buttons = [
            Button(
                key,
                label,
                rect,
                selected=index == self.run_filter_selected,
                hovered=rect.contains(self.game.mouse_position),
            )
            for index, ((key, label), rect) in enumerate(zip(labels, rows))
        ]
        return panel

    def _rows(self):
        return self._setup_rows() if self.view == "setup" else self._run_rows()

    @staticmethod
    def _cycle(index, count, direction):
        return (index + direction) % count if count else 0

    def _edit_setup_value(self, key, direction):
        aliases = {
            "deck": "deck_id",
            "opponent_deck": "opponent_deck_id",
            "generations": "evaluator_generations",
            "evaluation": "evaluation_games",
            "outer": "outer_generations",
            "matches": "matches_per_genome",
            "holdout": "holdout_seed_pairs",
        }
        key = aliases.get(key, key)
        if key in {"deck_id", "opponent_deck_id"}:
            self.cockpit.cycle_deck(key, direction)
        elif key in self.cockpit.field_keys and key != "run_label":
            self.cockpit.step_integer(key, direction)

    def _setup_field_label(self, key):
        if key == "workers":
            return "Evaluator workers" if self.kind == TrainingKind.DECK_BUILDER else "Workers"
        if key == "outer_generations" and self.kind == TrainingKind.PLAYER_DECK:
            return "Counter generations"
        if key == "evaluator_generations" and self.kind != TrainingKind.DECK_BUILDER:
            return "Controller generations"
        if key == "evaluation_games" and self.kind == TrainingKind.PLAYER_DECK:
            return "Games / counter deck"
        if key == "deck_id":
            return "Deck under test" if self.kind == TrainingKind.PLAYER_DECK else "Deck A"
        if key == "opponent_deck_id":
            return "Deck B"
        return {
            "run_label": "Run label",
            "deck_id": "Player deck",
            "opponent_deck_id": "Opponent deck",
            "seeds": "Seed set",
            "outer_generations": "Outer generations",
            "evaluator_generations": "Generations",
            "matches_per_genome": "Rival decks / candidate",
            "workers": "Evaluator workers",
            "holdout_seed_pairs": "Holdout seed pairs",
            "evaluation_games": "Games / checkpoint",
        }.get(key, key.replace("_", " ").title())

    def _setup_focus_order(self):
        fields = list(self.cockpit.field_keys)
        return [
            "mission_counter",
            "mission_matchup",
            "mission_builder",
            "preset_0",
            "preset_1",
            "preset_2",
            "preset_3",
            *fields,
            "about",
            "runs",
            "back",
            "launch",
        ]

    def _current_setup_layout(self):
        self.setup_layout = training_cockpit_layout(
            self.game.layout,
            self.kind,
            scroll=self.setup_scroll,
        )
        self.setup_scroll = min(self.setup_scroll, self.setup_layout.max_scroll)
        return self.setup_layout

    def _setup_control_visible(self, rect):
        layout = self.setup_layout
        if layout.mode == "wide" or rect == layout.controls.get("launch"):
            return True
        return rect.bottom > layout.viewport.y and rect.y < layout.viewport.bottom

    def _ensure_setup_focus_visible(self):
        layout = self._current_setup_layout()
        if layout.mode == "wide":
            return
        rect = layout.controls.get(self.setup_focus_key)
        if rect is None or self.setup_focus_key == "launch":
            return
        if rect.y < layout.viewport.y + 4:
            self.setup_scroll = max(0, self.setup_scroll - (layout.viewport.y + 4 - rect.y))
        elif rect.bottom > layout.viewport.bottom - 4:
            self.setup_scroll = min(
                layout.max_scroll,
                self.setup_scroll + rect.bottom - (layout.viewport.bottom - 4),
            )

    def _move_setup_focus(self, direction):
        order = [key for key in self._setup_focus_order() if key in self.setup_layout.controls]
        try:
            index = order.index(self.setup_focus_key)
        except ValueError:
            index = 0
        self.setup_focus_key = order[(index + direction) % len(order)]
        self._ensure_setup_focus_visible()

    def _begin_setup_edit(self, key):
        self.setup_edit_key = key
        self.setup_edit_original = self.cockpit.value(key)
        self.setup_edit_original_preset = self.cockpit.draft.preset_index
        self.setup_edit_original_auto_label = self.cockpit.draft.auto_run_label
        self.setup_focus_key = key

    def _finish_setup_edit(self, *, cancel=False, move=0):
        key = self.setup_edit_key
        if key is None:
            return True
        if cancel:
            self.cockpit.set_value(key, self.setup_edit_original, user_edit=False)
            self.cockpit.draft.preset_index = self.setup_edit_original_preset
            self.cockpit.draft.auto_run_label = self.setup_edit_original_auto_label
        elif key in self.cockpit.validate().errors:
            self.message = self.cockpit.validate().errors[key]
            self.message_color = self.game.palette.danger
            return False
        self.setup_edit_key = None
        self.setup_edit_original = ""
        self.setup_edit_original_preset = None
        self.setup_edit_original_auto_label = False
        if move:
            self._move_setup_focus(move)
        return True

    def _open_setup_picker(self, key):
        if not self.deck_ids:
            self.message = "Create a deck before configuring player training"
            self.message_color = self.game.palette.danger
            return
        self.setup_picker_key = key
        try:
            self.setup_picker_index = self.deck_ids.index(self.cockpit.value(key))
        except ValueError:
            self.setup_picker_index = 0

    def _activate_setup_control(self, key):
        self.setup_focus_key = key
        if key == "mission_counter":
            self.cockpit.switch(TrainingKind.PLAYER_DECK)
            self.setup_scroll = 0
        elif key == "mission_matchup":
            self.cockpit.switch(TrainingKind.MATCHUP_EVALUATION)
            self.setup_scroll = 0
        elif key == "mission_builder":
            self.cockpit.switch(TrainingKind.DECK_BUILDER)
            self.setup_scroll = 0
        elif key.startswith("preset_"):
            index = int(key.rsplit("_", 1)[1])
            self.cockpit.apply_preset(index if index < 3 else None)
        elif key in {"deck_id", "opponent_deck_id"}:
            self._open_setup_picker(key)
        elif key in self.cockpit.field_keys:
            self._begin_setup_edit(key)
        elif key == "about":
            self.view = "about"
            self.about_page = 0
        elif key == "runs":
            self.view = "runs"
            self.selected = 0
            self.run_page = 0
            self.run_selected = 0
            self.run_search.focused = False
            self._refresh_runs(force=True)
        elif key == "back":
            self._return()
        elif key == "launch":
            self._launch()

    def _handle_setup_editor(self):
        key = self.setup_edit_key
        for event in self.game.events:
            if event.type != pg.KEYDOWN:
                continue
            if event.key == pg.K_ESCAPE:
                self.game.BACK_KEY = False
                self._finish_setup_edit(cancel=True)
                return True
            if event.key in (pg.K_RETURN, pg.K_KP_ENTER):
                self.game.START_KEY = False
                self._finish_setup_edit()
                return True
            if event.key == pg.K_TAB:
                direction = -1 if event.mod & pg.KMOD_SHIFT else 1
                if self._finish_setup_edit(move=direction):
                    self.game.START_KEY = False
                return True
            value = self.cockpit.value(key)
            if event.key == pg.K_BACKSPACE:
                self.game.BACK_KEY = False
                self.cockpit.set_value(key, value[:-1])
                return True
            if event.unicode and event.unicode.isprintable() and len(value) < 160:
                self.cockpit.set_value(key, value + event.unicode)
                self.game.START_KEY = False
                return True
        if self.game.mouse_clicked:
            rect = self.setup_layout.controls.get(key)
            if rect is None or not rect.contains(self.game.mouse_position):
                self._finish_setup_edit()
            return True
        return True

    def _picker_panel(self):
        panel = self.game.layout.centered_panel(0.62, 0.72, max_width=760)
        row_height = max(38, min(48, self.game.layout.target_height))
        visible_count = max(1, min(8, (panel.height - 110) // (row_height + 4)))
        start = max(0, min(self.setup_picker_index - visible_count // 2, len(self.deck_ids) - visible_count))
        rows = []
        for offset, deck_id in enumerate(self.deck_ids[start : start + visible_count]):
            rows.append(
                (
                    start + offset,
                    deck_id,
                    self._deck_label(deck_id),
                    RectSpec(
                        panel.x + self.game.layout.gap,
                        panel.y + 62 + offset * (row_height + 4),
                        panel.width - self.game.layout.gap * 2,
                        row_height,
                    ),
                )
            )
        return panel, rows

    def _handle_setup_picker(self):
        if self.game.BACK_KEY:
            self.setup_picker_key = None
            self.game.BACK_KEY = False
            return
        if self.game.UP_KEY:
            self.setup_picker_index = max(0, self.setup_picker_index - 1)
        elif self.game.DOWN_KEY:
            self.setup_picker_index = min(len(self.deck_ids) - 1, self.setup_picker_index + 1)
        if self.game.START_KEY:
            self.cockpit.set_value(
                self.setup_picker_key,
                self.deck_ids[self.setup_picker_index],
                user_edit=False,
            )
            self.setup_picker_key = None
            self.game.START_KEY = False
            return
        if self.game.mouse_clicked:
            _panel, rows = self._picker_panel()
            for index, deck_id, _deck_name, rect in rows:
                if rect.contains(self.game.mouse_position):
                    self.setup_picker_index = index
                    self.cockpit.set_value(self.setup_picker_key, deck_id, user_edit=False)
                    self.setup_picker_key = None
                    return

    def _review_buttons(self):
        panel = self.game.layout.centered_panel(0.78, 0.84, max_width=980)
        gap = self.game.layout.gap
        height = max(42, min(54, self.game.layout.target_height))
        width = (panel.width - gap * 3) // 2
        y = panel.bottom - gap - height
        return panel, (
            RectSpec(panel.x + gap, y, width, height),
            RectSpec(panel.right - gap - width, y, width, height),
        )

    def _handle_setup_review(self):
        if self.game.BACK_KEY:
            if not self.setup_starting:
                self.setup_review_open = False
                self.setup_review_request = None
            self.game.BACK_KEY = False
            return
        if self.setup_starting:
            return
        if self.game.LEFT_KEY or self.game.RIGHT_KEY:
            self.setup_review_selected = 1 - self.setup_review_selected
        if self.game.mouse_clicked:
            _panel, buttons = self._review_buttons()
            if buttons[0].contains(self.game.mouse_position):
                self.setup_review_open = False
                self.setup_review_request = None
                return
            if buttons[1].contains(self.game.mouse_position):
                self.setup_review_selected = 1
                self._start_training(self.setup_review_request)
                return
        if self.game.START_KEY:
            if self.setup_review_selected == 0:
                self.setup_review_open = False
                self.setup_review_request = None
            else:
                self._start_training(self.setup_review_request)
            self.game.START_KEY = False

    def _check_setup_input(self):
        self._current_setup_layout()
        if self.setup_review_open:
            self._handle_setup_review()
            return
        if self.setup_picker_key is not None:
            self._handle_setup_picker()
            return
        if self.setup_edit_key is not None:
            self._handle_setup_editor()
            return
        if self.game.mouse_wheel and self.setup_layout.mode == "compact":
            self.setup_scroll = max(
                0,
                min(
                    self.setup_layout.max_scroll,
                    self.setup_scroll - self.game.mouse_wheel * 64,
                ),
            )
            self._current_setup_layout()
        for event in self.game.events:
            if event.type == pg.KEYDOWN and event.key == pg.K_TAB:
                self._move_setup_focus(-1 if event.mod & pg.KMOD_SHIFT else 1)
                return
        if self.game.BACK_KEY:
            self._return()
            return
        if self.game.UP_KEY:
            self._move_setup_focus(-1)
        elif self.game.DOWN_KEY:
            self._move_setup_focus(1)
        elif self.game.LEFT_KEY or self.game.RIGHT_KEY:
            direction = 1 if self.game.RIGHT_KEY else -1
            if self.setup_focus_key in {"deck_id", "opponent_deck_id"}:
                self.cockpit.cycle_deck(self.setup_focus_key, direction)
            elif self.setup_focus_key in self.cockpit.field_keys and self.setup_focus_key != "run_label":
                self.cockpit.step_integer(self.setup_focus_key, direction)
            else:
                self._move_setup_focus(direction)
        if self.game.mouse_clicked:
            for key, rect in self.setup_layout.controls.items():
                if self._setup_control_visible(rect) and rect.contains(self.game.mouse_position):
                    self._activate_setup_control(key)
                    return
        if self.game.START_KEY:
            self._activate_setup_control(self.setup_focus_key)

    def _draw_cockpit_panel(self, rect, *, accent=None):
        pg_rect = pg.Rect(rect.x, rect.y, rect.width, rect.height)
        pg.draw.rect(self.game.display, self.game.palette.panel, pg_rect, border_radius=12)
        pg.draw.rect(self.game.display, self.game.palette.border, pg_rect, 1, border_radius=12)
        if accent:
            pg.draw.rect(
                self.game.display,
                accent,
                pg.Rect(rect.x, rect.y, 5, rect.height),
                border_radius=3,
            )

    def _draw_setup_button(self, key, label, *, selected=False, enabled=True, compact=False):
        rect = self.setup_layout.controls.get(key)
        if rect is None or not self._setup_control_visible(rect):
            return
        button = Button(
            key,
            label,
            rect,
            enabled=enabled,
            selected=selected or key == self.setup_focus_key,
            hovered=rect.contains(self.game.mouse_position),
        )
        size = max(11, self.game.layout.font_small - (2 if compact else 0))
        button.draw(self.game.display, pg.font.Font(self.game.font_name, size), self.game.palette)

    def _draw_setup_field(self, key, validation):
        rect = self.setup_layout.controls.get(key)
        if rect is None or not self._setup_control_visible(rect):
            return
        error = validation.errors.get(key)
        focused = key == self.setup_focus_key
        editing = key == self.setup_edit_key
        pg_rect = pg.Rect(rect.x, rect.y, rect.width, rect.height)
        fill = self.game.palette.hover if focused else self.game.palette.panel_alt
        border = self.game.palette.danger if error else self.game.palette.accent if focused else self.game.palette.border
        pg.draw.rect(self.game.display, fill, pg_rect, border_radius=7)
        pg.draw.rect(self.game.display, border, pg_rect, 2, border_radius=7)
        self.game.draw_text_left(
            self._setup_field_label(key).upper(),
            max(10, self.game.layout.font_small - 4),
            rect.x,
            rect.y - 7,
            self.game.palette.danger if error else self.game.palette.muted,
            rect.width,
        )
        value = self.cockpit.value(key)
        if key in {"deck_id", "opponent_deck_id"}:
            value = self._deck_label(value) + ("  v" if self.deck_ids else "")
        if editing:
            value += " |"
        value_size = max(13, self.game.layout.font_normal - 3)
        if key == "run_label":
            value_size = self._fitted_text_size(
                value,
                value_size,
                max(1, rect.width - 20),
            )
        self.game.draw_text_left(
            value or " ",
            value_size,
            rect.x + 10,
            rect.y + rect.height // 2,
            self.game.palette.text if value else self.game.palette.muted,
            rect.width - 20,
        )
        if error:
            self.game.draw_text_left(
                error,
                max(10, self.game.layout.font_small - 5),
                rect.x,
                rect.bottom + 7,
                self.game.palette.danger,
                rect.width,
            )

    def _summary_rows(self, request):
        if self.kind == TrainingKind.PLAYER_DECK:
            return (
                ("MISSION", "Counter-deck training"),
                ("PRESET", self.cockpit.preset_label),
                ("DECK UNDER TEST", self._deck_label(request.deck_id if request else self.cockpit.value("deck_id"))),
                ("COUNTER EVOLUTION", f"{request.outer_generations} generations" if request else self.cockpit.value("outer_generations")),
                ("CONTROLLER LEARNING", f"{request.evaluator_generations} persistent generations" if request else self.cockpit.value("evaluator_generations")),
                ("VALIDATION", f"{request.evaluation_games} games/counter" if request else f"{self.cockpit.value('evaluation_games')} games/counter"),
            )
        if self.kind == TrainingKind.MATCHUP_EVALUATION:
            return (
                ("MISSION", "Two-deck matchup"),
                ("PRESET", self.cockpit.preset_label),
                ("DECK A", self._deck_label(request.deck_id if request else self.cockpit.value("deck_id"))),
                ("DECK B", self._deck_label(request.opponent_deck_id if request else self.cockpit.value("opponent_deck_id"))),
                ("CONTROLLER LEARNING", str(request.evaluator_generations) if request else self.cockpit.value("evaluator_generations")),
                ("CHECKPOINT", f"{request.evaluation_games} seat-balanced games" if request else self.cockpit.value("evaluation_games")),
            )
        seeds = request.seeds if request else ()
        return (
            ("MISSION", "Deck builder experiment"),
            ("PRESET", self.cockpit.preset_label),
            ("SEEDS", f"{len(seeds)} independent runs" if seeds else "Pending / invalid"),
            ("EVOLUTION", f"{request.outer_generations} outer / {request.evaluator_generations} inner" if request else "Pending / invalid"),
            ("RIVAL DECKS", f"{request.matches_per_genome} per candidate" if request else self.cockpit.value("matches_per_genome")),
            ("HOLDOUT", f"{request.holdout_seed_pairs} seed pairs" if request else self.cockpit.value("holdout_seed_pairs")),
        )

    def _draw_cockpit_header(self, layout):
        self.game.draw_text_left(
            "DRACI ZVESTI / AI TRAINING",
            max(11, self.game.layout.font_small - 2),
            layout.header.x,
            layout.header.y + 12,
            self.game.palette.accent,
            layout.header.width,
        )
        title = "Training workbench"
        self.game.draw_text_left(
            title,
            self.game.layout.font_large,
            layout.header.x,
            layout.header.y + 43,
            self.game.palette.text,
            layout.header.width,
        )
        if self.game.DISPLAY_W >= 900:
            self.game.draw_text_left(
                "Build counter-decks, evaluate matchups, and evolve new decks",
                self.game.layout.font_small,
                layout.header.x,
                layout.header.y
                + 43
                + self.game.layout.font_large // 2
                + self.game.layout.font_small,
                self.game.palette.muted,
                layout.header.width,
            )

    def _draw_cockpit_rail(self, layout):
        rail = layout.panels["rail"]
        self._draw_cockpit_panel(rail, accent=(109, 169, 223))
        self.game.draw_text_left(
            "Choose a mission" if layout.mode == "wide" else "Mission",
            max(13, self.game.layout.font_small),
            rail.x + self.game.layout.gap,
            rail.y + 20,
            self.game.palette.text,
            rail.width - self.game.layout.gap * 2,
        )
        self._draw_setup_button(
            "mission_counter",
            "Train counters for my deck",
            selected=self.kind == TrainingKind.PLAYER_DECK,
            compact=layout.mode == "compact",
        )
        self._draw_setup_button(
            "mission_matchup",
            "Evaluate a matchup",
            selected=self.kind == TrainingKind.MATCHUP_EVALUATION,
            compact=layout.mode == "compact",
        )
        self._draw_setup_button(
            "mission_builder",
            "Evolve general deck pool",
            selected=self.kind == TrainingKind.DECK_BUILDER,
            compact=layout.mode == "compact",
        )
        if layout.mode == "wide":
            self._draw_setup_button("about", "Training guide >", compact=True)
            self._draw_setup_button("back", "< Back to menu", compact=True)
            self._draw_setup_button("runs", "Open run library >", compact=True)

    def _draw_cockpit_config(self, layout, validation):
        panel = layout.panels["config"]
        self._draw_cockpit_panel(panel, accent=self.game.palette.accent)
        x = panel.x + self.game.layout.gap + 8
        config_title = {
            TrainingKind.PLAYER_DECK: "Configure counter-deck training",
            TrainingKind.MATCHUP_EVALUATION: "Configure matchup evaluation",
            TrainingKind.DECK_BUILDER: "Configure general deck evolution",
        }[self.kind]
        self.game.draw_text_left(
            config_title,
            max(15, self.game.layout.font_normal - 1),
            x,
            panel.y + 21,
            self.game.palette.text,
            panel.width - self.game.layout.gap * 2,
        )
        if layout.mode == "wide":
            self.game.draw_text_left(
                "Presets fill fields; every value remains directly editable",
                max(10, self.game.layout.font_small - 3),
                x,
                panel.y + 43,
                self.game.palette.muted,
                panel.width - self.game.layout.gap * 2,
            )
        labels = [preset.label for preset in presets_for(self.kind)] + ["Custom"]
        active = self.cockpit.draft.preset_index
        for index, label in enumerate(labels):
            self._draw_setup_button(
                f"preset_{index}",
                label,
                selected=(active == index or (index == 3 and active is None)),
                compact=True,
            )
        for key in self.cockpit.field_keys:
            self._draw_setup_field(key, validation)

    def _draw_read_only_field(self, key, label, value, *, helper=""):
        rect = self.setup_layout.controls.get(key)
        if rect is None or not self._setup_control_visible(rect):
            return
        pg_rect = pg.Rect(rect.x, rect.y, rect.width, rect.height)
        pg.draw.rect(self.game.display, self.game.palette.panel_alt, pg_rect, border_radius=7)
        pg.draw.rect(self.game.display, self.game.palette.border, pg_rect, 1, border_radius=7)
        self.game.draw_text_left(label.upper(), max(10, self.game.layout.font_small - 4), rect.x, rect.y - 7, self.game.palette.muted, rect.width)
        self.game.draw_text_left(str(value), max(13, self.game.layout.font_normal - 3), rect.x + 10, rect.y + rect.height // 2, self.game.palette.text, rect.width - 20)
        if helper:
            self.game.draw_text_left(helper, max(10, self.game.layout.font_small - 5), rect.x, rect.bottom + 7, (109, 169, 223), rect.width)

    def _draw_cockpit_evidence(self, layout, validation):
        panel = layout.panels["evidence"]
        self._draw_cockpit_panel(panel, accent=self.game.palette.success)
        x = panel.x + self.game.layout.gap + 8
        title = (
            "Persistent learning & validation"
            if self.kind == TrainingKind.PLAYER_DECK
            else "Matchup checkpoints"
            if self.kind == TrainingKind.MATCHUP_EVALUATION
            else "Workload & preflight"
        )
        self.game.draw_text_left(title, max(15, self.game.layout.font_normal - 1), x, panel.y + 22, self.game.palette.text, panel.width - 24)
        workload = training_workload(validation.request) if validation.request else None
        if self.kind == TrainingKind.PLAYER_DECK:
            if layout.mode == "wide":
                self._draw_setup_field("evaluation_games", validation)
            self._draw_read_only_field(
                "persistence_display",
                "Controller memory",
                "Persists across all counters",
                helper="Learning does not reset between deck candidates",
            )
            self._draw_read_only_field(
                "counter_pool",
                "Counter population",
                "20 evolving decks",
                helper="Best final opponent is reported as Top counter",
            )
            if workload:
                y = panel.bottom - max(42, self.game.layout.target_height)
                self.game.draw_text_left(workload.headline, max(12, self.game.layout.font_small - 1), x, y, self.game.palette.accent, panel.width - 30)
        elif self.kind == TrainingKind.MATCHUP_EVALUATION:
            if layout.mode == "wide":
                self._draw_setup_field("evaluation_games", validation)
            checkpoints = " · ".join(map(str, self.cockpit.checkpoints())) or "Pending"
            self._draw_read_only_field("checkpoint_display", "Win-rate checkpoints", checkpoints, helper="Both controllers evolve directly against each other")
            deck_status = "2 fixed decks selected" if self.deck_ids and not {"deck_id", "opponent_deck_id"} & validation.errors.keys() else "Deck selection incomplete"
            self._draw_read_only_field("deck_status", "Matchup", deck_status, helper="Seats are balanced in every checkpoint")
            if workload:
                y = panel.bottom - max(42, self.game.layout.target_height)
                self.game.draw_text_left(workload.headline, max(12, self.game.layout.font_small - 1), x, y, self.game.palette.accent, panel.width - 30)
        else:
            if workload:
                self.game.draw_text_left(workload.headline, max(15, self.game.layout.font_normal - 1), x, panel.y + 65, self.game.palette.accent, panel.width - 30)
                for index, detail in enumerate(workload.details[:3]):
                    self.game.draw_text_left(detail, max(10, self.game.layout.font_small - 3), x, panel.y + 94 + index * 22, self.game.palette.muted, panel.width - 30)
            else:
                self.game.draw_text_left("Correct the highlighted settings to calculate workload", self.game.layout.font_small, x, panel.y + 68, self.game.palette.danger, panel.width - 30)
        ready = validation.valid and self.setup_edit_key is None
        status = (
            "Ready for review"
            if ready
            else "Finish editing to review"
            if validation.valid
            else f"Fix {len(validation.errors)} setting(s)"
        )
        color = self.game.palette.success if ready else self.game.palette.danger
        self.game.draw_text_left(status, max(11, self.game.layout.font_small - 2), x, panel.bottom - 18, color, panel.width - 30)

    def _draw_cockpit_summary(self, layout, validation):
        panel = layout.panels["summary"]
        self._draw_cockpit_panel(panel, accent=self.game.palette.accent)
        x = panel.x + self.game.layout.gap + 8
        self.game.draw_text_left("Run summary", max(15, self.game.layout.font_normal - 1), x, panel.y + 22, self.game.palette.text, panel.width - 24)
        self.game.draw_text_left("Always visible before committing", max(10, self.game.layout.font_small - 3), x, panel.y + 43, self.game.palette.muted, panel.width - 24)
        y = panel.y + 72
        row_gap = 47 if layout.mode == "wide" else 40
        for label, value in self._summary_rows(validation.request):
            self.game.draw_text_left(label, max(9, self.game.layout.font_small - 5), x, y, self.game.palette.muted, panel.width - 24)
            self.game.draw_text_left(str(value or "Pending"), max(12, self.game.layout.font_normal - 3), x, y + 18, self.game.palette.text, panel.width - 24)
            y += row_gap
        ready = validation.valid and self.setup_edit_key is None
        status_text = (
            "READY TO REVIEW"
            if ready
            else "FINISH EDITING"
            if validation.valid
            else f"FIX {len(validation.errors)} SETTINGS"
        )
        status_color = self.game.palette.success if ready else self.game.palette.danger
        status_y = min(panel.bottom - 84, y + 4)
        self.game.draw_text_left(status_text, max(11, self.game.layout.font_small - 2), x, status_y, status_color, panel.width - 24)
        if validation.errors:
            self.game.draw_text_left(next(iter(validation.errors.values())), max(9, self.game.layout.font_small - 5), x, status_y + 20, self.game.palette.muted, panel.width - 24)

    def _draw_cockpit_actions(self, layout, validation):
        if layout.mode == "compact":
            panel = layout.panels.get("actions")
            if panel and panel.bottom > layout.viewport.y and panel.y < layout.viewport.bottom:
                self._draw_cockpit_panel(panel)
                self._draw_setup_button("about", "Guide", compact=True)
                self._draw_setup_button("runs", "Runs", compact=True)
                self._draw_setup_button("back", "Back", compact=True)
        launch_enabled = validation.valid and self.setup_edit_key is None and not self.setup_starting
        label = "Starting training…" if self.setup_starting else "Review & launch >"
        self._draw_setup_button("launch", label, selected=False, enabled=launch_enabled)

    def _draw_setup_scrollbar(self, layout):
        if layout.mode != "compact" or not layout.max_scroll:
            return
        track = pg.Rect(layout.viewport.right - 4, layout.viewport.y, 3, layout.viewport.height)
        pg.draw.rect(self.game.display, self.game.palette.disabled, track, border_radius=2)
        content_height = layout.viewport.height + layout.max_scroll
        thumb_height = max(24, layout.viewport.height * layout.viewport.height // content_height)
        travel = layout.viewport.height - thumb_height
        thumb_y = layout.viewport.y + travel * self.setup_scroll // layout.max_scroll
        pg.draw.rect(
            self.game.display,
            self.game.palette.accent,
            pg.Rect(track.x, thumb_y, track.width, thumb_height),
            border_radius=2,
        )

    def draw_training_cockpit(self):
        self.draw_background()
        layout = self._current_setup_layout()
        validation = self.cockpit.validate()
        self._draw_cockpit_header(layout)
        if layout.mode == "compact":
            self.game.display.set_clip(pg.Rect(layout.viewport.x, layout.viewport.y, layout.viewport.width, layout.viewport.height))
        self._draw_cockpit_rail(layout)
        self._draw_cockpit_config(layout, validation)
        self._draw_cockpit_evidence(layout, validation)
        self._draw_cockpit_summary(layout, validation)
        if layout.mode == "compact":
            self._draw_cockpit_actions(layout, validation)
            self.game.display.set_clip(None)
            self._draw_setup_scrollbar(layout)
            launch_enabled = validation.valid and self.setup_edit_key is None and not self.setup_starting
            label = "Starting training…" if self.setup_starting else "Review & launch >"
            self._draw_setup_button("launch", label, selected=False, enabled=launch_enabled)
        else:
            self._draw_cockpit_actions(layout, validation)
        if self.message:
            self.game.draw_text_left(
                self.message,
                max(10, self.game.layout.font_small - 3),
                layout.header.x,
                layout.header.bottom - 2,
                self.message_color,
                layout.header.width,
            )
        if self.setup_picker_key is not None:
            self._draw_setup_picker()
        if self.setup_review_open:
            self._draw_setup_review()

    def _draw_setup_picker(self):
        shade = pg.Surface((self.game.DISPLAY_W, self.game.DISPLAY_H), pg.SRCALPHA)
        shade.fill((0, 0, 0, 175))
        self.game.display.blit(shade, (0, 0))
        panel, rows = self._picker_panel()
        self._draw_cockpit_panel(panel, accent=self.game.palette.accent)
        self.game.draw_text_left("Select deck", self.game.layout.font_normal, panel.x + self.game.layout.gap, panel.y + 27, self.game.palette.text, panel.width - self.game.layout.gap * 2)
        font = pg.font.Font(self.game.font_name, max(12, self.game.layout.font_small))
        for index, _deck_id, deck_name, rect in rows:
            Button(
                str(index),
                deck_name,
                rect,
                selected=index == self.setup_picker_index,
                hovered=rect.contains(self.game.mouse_position),
            ).draw(self.game.display, font, self.game.palette)

    def _review_rows(self, request):
        if request.kind == TrainingKind.PLAYER_DECK:
            return (
                ("Deck under test", self._deck_label(request.deck_id)),
                ("Counter generations", request.outer_generations),
                ("Persistent controller generations", request.evaluator_generations),
                ("Workers", request.workers),
                ("Games / counter deck", request.evaluation_games),
                ("Counter population", "20 candidates per generation"),
            )
        if request.kind == TrainingKind.MATCHUP_EVALUATION:
            checkpoints = ", ".join(
                map(str, matchup_checkpoints(request.evaluator_generations))
            )
            return (
                ("Deck A", self._deck_label(request.deck_id)),
                ("Deck B", self._deck_label(request.opponent_deck_id)),
                ("Controller generations", request.evaluator_generations),
                ("Workers", request.workers),
                ("Games / checkpoint", request.evaluation_games),
                ("Checkpoints", checkpoints),
            )
        return (
            ("Seed set", ", ".join(map(str, request.seeds))),
            ("Generations", f"{request.outer_generations} outer · {request.evaluator_generations} inner"),
            ("Rival decks / candidate", request.matches_per_genome),
            ("Evaluator workers", request.workers),
            ("Holdout seed pairs", request.holdout_seed_pairs),
            ("Engine", "20 target decks · 2 fixed outer workers"),
        )

    def _draw_setup_review(self):
        request = self.setup_review_request
        if request is None:
            return
        shade = pg.Surface((self.game.DISPLAY_W, self.game.DISPLAY_H), pg.SRCALPHA)
        shade.fill((0, 0, 0, 190))
        self.game.display.blit(shade, (0, 0))
        panel, button_rects = self._review_buttons()
        self._draw_cockpit_panel(panel, accent=self.game.palette.accent)
        gap = self.game.layout.gap
        x = panel.x + gap * 2
        width = panel.width - gap * 4
        self.game.draw_text_left("Review training request", self.game.layout.font_large, x, panel.y + gap * 2, self.game.palette.text, width)
        self.game.draw_text_left(f"{request.kind.value} · {request.run_label}", self.game.layout.font_small, x, panel.y + gap * 2 + self.game.layout.font_large, self.game.palette.muted, width)
        y = panel.y + gap * 3 + self.game.layout.font_large + self.game.layout.font_small
        available_bottom = button_rects[0].y - gap * 2
        rows = self._review_rows(request)
        row_height = max(25, min(36, (available_bottom - y - 76) // max(1, len(rows))))
        for label, value in rows:
            self.game.draw_text_left(str(label), max(11, self.game.layout.font_small - 2), x, y, self.game.palette.muted, width // 2)
            self.game.draw_text_left(str(value), max(11, self.game.layout.font_small - 2), x + width // 2, y, self.game.palette.text, width // 2)
            y += row_height
        workload = training_workload(request)
        self.game.draw_text_left(workload.headline, max(13, self.game.layout.font_normal - 2), x, y + 10, self.game.palette.accent, width)
        self.game.draw_text_left("Workload is not wall-clock time. Starting creates one training job and opens Runs.", max(10, self.game.layout.font_small - 3), x, y + 40, self.game.palette.muted, width)
        labels = ("Back to settings", "Starting…" if self.setup_starting else "Start training")
        font = pg.font.Font(self.game.font_name, max(12, self.game.layout.font_normal - 2))
        for index, (label, rect) in enumerate(zip(labels, button_rects)):
            Button(
                str(index),
                label,
                rect,
                enabled=not self.setup_starting,
                selected=index == self.setup_review_selected,
                hovered=rect.contains(self.game.mouse_position),
            ).draw(self.game.display, font, self.game.palette)

    def _refresh_runs(self, force=False):
        while True:
            try:
                result = self._refresh_results.get_nowait()
            except queue.Empty:
                break
            if result[0] == "ok":
                (
                    _,
                    self.jobs,
                    self.database_runs,
                    self._linked_database_run_ids,
                ) = result
                if self.dashboard_item is not None:
                    if isinstance(self.dashboard_item, TrainingRunSummary):
                        replacement = next(
                            (
                                run
                                for run in self.database_runs
                                if run.run_id == self.dashboard_item.run_id
                            ),
                            None,
                        )
                    else:
                        replacement = next(
                            (
                                job
                                for job in self.jobs
                                if job.job_id == self.dashboard_item.job_id
                            ),
                            None,
                        )
                    if replacement is not None:
                        previous_status = str(
                            getattr(self.dashboard_item, "status", "") or ""
                        ).lower()
                        self.dashboard_item = replacement
                        self.dashboard_telemetry = None
                        replacement_status = str(
                            getattr(replacement, "status", "") or ""
                        ).lower()
                        if (
                            replacement_status == "completed"
                            and previous_status != "completed"
                        ):
                            self.dashboard_artifact_status = None
                            self.dashboard_insights = None
                        if replacement_status == "completed":
                            self._start_insight_refresh(replacement)
            else:
                self.message = f"Could not refresh runs: {result[1]}"
                self.message_color = (235, 105, 105)

        now = pg.time.get_ticks()
        if not force and now - self.last_refresh < 2000:
            return
        if self._refresh_thread is not None and self._refresh_thread.is_alive():
            return
        self.last_refresh = now

        def refresh():
            try:
                jobs = self.service.jobs()
                linked_database_run_ids = set()
                for job in jobs:
                    database_id = self.service.job_database_run_id(job)
                    if database_id is not None:
                        linked_database_run_ids.add(f"DB {database_id}")
                self._refresh_results.put(
                    (
                        "ok",
                        jobs,
                        self.service.recent_database_runs(),
                        linked_database_run_ids,
                    )
                )
            except (OSError, RuntimeError, TimeoutError) as error:
                self._refresh_results.put(("error", str(error)))

        self._refresh_thread = threading.Thread(
            target=refresh,
            name="training-status-refresh",
            daemon=True,
        )
        self._refresh_thread.start()

    def _launch(self):
        if self._launch_thread is not None and self._launch_thread.is_alive():
            self.message = "Training launch is already in progress"
            self.message_color = (235, 190, 90)
            return
        validation = self.cockpit.validate()
        if validation.request is None:
            self.message = next(iter(validation.errors.values()), "Fix the highlighted settings")
            self.message_color = (235, 105, 105)
            return
        self.setup_review_request = validation.request
        self.setup_review_open = True
        self.setup_review_selected = 0

    def _start_training(self, request):
        if self._launch_thread is not None and self._launch_thread.is_alive():
            self.message = "Training launch is already in progress"
            self.message_color = self.game.palette.accent
            return
        try:
            request.validate()
        except ValueError as error:
            self.setup_review_open = False
            self.message = str(error)
            self.message_color = self.game.palette.danger
            return
        self.message = "Starting training…"
        self.message_color = self.game.palette.muted
        self.setup_starting = True

        def launch():
            try:
                self._launch_results.put(("ok", self.service.start(request)))
            except (ValueError, RuntimeError, OSError) as error:
                self._launch_results.put(("error", str(error)))

        self._launch_thread = threading.Thread(
            target=launch,
            name="training-launch",
            daemon=True,
        )
        self._launch_thread.start()

    def _consume_launch_result(self):
        try:
            status, value = self._launch_results.get_nowait()
        except queue.Empty:
            return
        self.setup_starting = False
        if status == "error":
            self.setup_review_open = False
            self.message = value
            self.message_color = (235, 105, 105)
            return
        self.setup_review_open = False
        self.setup_review_request = None
        self.message = f"Started {value.job_id}"
        self.message_color = (105, 210, 150)
        self._activate_run(value, watched_live=True)
        self._refresh_runs(force=True)

    def _can_stop_dashboard_job(self):
        item = self.dashboard_item
        return (
            isinstance(item, TrainingJob)
            and self.service.can_stop(item)
            and not (self._stop_thread is not None and self._stop_thread.is_alive())
        )

    def _stop_dashboard_job(self):
        if not self._can_stop_dashboard_job():
            return
        job = self.dashboard_item
        if not self.confirm_action(
            "Stop this training run?",
            (
                job.job_id,
                "The UI-owned trainer process will be stopped.",
                "Completed artifacts and logs will remain on disk.",
            ),
            confirm_label="Stop training",
        ):
            return
        self.message = "Stopping training safely…"
        self.message_color = self.game.palette.muted
        job.status = "stopping"
        self.dashboard_telemetry = None

        def stop():
            try:
                self._stop_results.put(("ok", self.service.stop_job(job)))
            except (OSError, RuntimeError, TimeoutError) as error:
                self._stop_results.put(("error", str(error)))

        self._stop_thread = threading.Thread(
            target=stop,
            name="training-stop",
            daemon=True,
        )
        self._stop_thread.start()

    def _consume_stop_result(self):
        try:
            status, value = self._stop_results.get_nowait()
        except queue.Empty:
            return
        if status == "error":
            self.message = f"Could not stop training: {value}"
            self.message_color = self.game.palette.danger
            return
        if value is None:
            self.message = "Training had already finished"
            self.message_color = self.game.palette.muted
            return
        if (
            isinstance(self.dashboard_item, TrainingJob)
            and self.dashboard_item.job_id == value.job_id
        ):
            self.dashboard_item = value
            self.dashboard_telemetry = None
        self.message = "Training stopped; artifacts and logs were kept"
        self.message_color = self.game.palette.accent
        self._refresh_runs(force=True)

    def _activate_setup(self, key):
        if key == "action":
            self._activate_setup_control("back" if self.selected == 0 else "runs")
        elif key == "label":
            self._activate_setup_control("run_label")
        elif key == "kind":
            kinds = (
                TrainingKind.PLAYER_DECK,
                TrainingKind.MATCHUP_EVALUATION,
                TrainingKind.DECK_BUILDER,
            )
            target = kinds[(kinds.index(self.kind) + 1) % len(kinds)]
            self._activate_setup_control(
                {
                    TrainingKind.PLAYER_DECK: "mission_counter",
                    TrainingKind.MATCHUP_EVALUATION: "mission_matchup",
                    TrainingKind.DECK_BUILDER: "mission_builder",
                }[target]
            )
        elif key == "preset":
            current = self.cockpit.draft.preset_index
            self.cockpit.apply_preset(0 if current is None else (current + 1) % 3)
        elif key == "workload":
            workload = self.cockpit.workload()
            if workload:
                self.show_lines("Planned workload", (workload.headline, *workload.details))
        else:
            aliases = {
                "deck": "deck_id",
                "opponent_deck": "opponent_deck_id",
                "generations": "evaluator_generations",
                "evaluation": "evaluation_games",
                "outer": "outer_generations",
                "matches": "matches_per_genome",
                "holdout": "holdout_seed_pairs",
            }
            self._activate_setup_control(aliases.get(key, key))

    def _activate_run(self, value, *, watched_live=False):
        if value == "back" or value == "setup":
            self.view = "setup"
            self.selected = 1
        else:
            self.dashboard_item = value
            self.dashboard_action = 0
            self.dashboard_page = 0
            self.dashboard_telemetry = None
            self.dashboard_insights = None
            self.dashboard_scroll = 0
            self.dashboard_max_scroll = 0
            self.dashboard_watching_live = bool(watched_live)
            self.dashboard_results_opened = False
            self.dashboard_artifact_status = None
            self.counter_candidate_key = None
            self.counter_candidate_scroll = 0
            self.counter_candidate_keys = ()
            self.counter_candidate_rects = []
            self.counter_candidate_viewport = None
            self.counter_candidate_capacity = 1
            self.counter_focus = "candidates"
            self.evolution_selected_deck_id = None
            self.evolution_generation_filter = None
            self.evolution_deck_scroll = 0
            self.evolution_deck_keys = ()
            self.evolution_deck_rects = []
            self.evolution_deck_viewport = None
            self.evolution_focus = "decks"
            self._close_adoption()
            self._dashboard_last_refresh = -1000
            self.view = "dashboard"
            if str(getattr(value, "status", "")).lower() == "completed":
                self._start_insight_refresh(value)

    def _start_insight_refresh(self, item):
        if self._insight_thread is not None and self._insight_thread.is_alive():
            return
        item_key = getattr(item, "run_id", getattr(item, "job_id", ""))

        def analyze():
            try:
                artifact = self.service.result_artifact_status(item)
                if not artifact.ready:
                    self._insight_results.put(
                        ("artifact", item_key, artifact, None)
                    )
                    return
                insights = (
                    self.service.database_insights(item)
                    if isinstance(item, TrainingRunSummary)
                    else self.service.job_insights(item)
                )
                self._insight_results.put(("ok", item_key, artifact, insights))
            except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
                self._insight_results.put(("error", item_key, None, str(error)))

        self._insight_thread = threading.Thread(
            target=analyze,
            name="training-insight-analysis",
            daemon=True,
        )
        self._insight_thread.start()

    def _consume_insight_result(self):
        try:
            status, item_key, artifact, value = self._insight_results.get_nowait()
        except queue.Empty:
            return
        current_key = getattr(
            self.dashboard_item,
            "run_id",
            getattr(self.dashboard_item, "job_id", ""),
        )
        if item_key != current_key:
            return
        if artifact is not None:
            self.dashboard_artifact_status = artifact
        if status == "ok":
            self.dashboard_insights = value
        elif status == "artifact":
            self.dashboard_insights = None
        else:
            self.dashboard_artifact_status = ResultArtifactStatus.invalid(
                f"Results could not be loaded: {value}"
            )
            self.dashboard_insights = TrainingInsights(
                conclusions=(f"Analytics could not be loaded: {value}",)
            )

    def _return(self):
        self.return_to_previous()

    def _open_run_filter(self):
        self.run_filter_pending_status = self.run_filter_status_index
        self.run_filter_pending_mission = self.run_filter_mission_index
        self.run_filter_pending_origin = self.run_filter_origin_index
        self.run_filter_pending_started = self.run_filter_started_index
        self.run_filter_pending_generations = self.run_filter_generations_index
        self.run_filter_selected = 0
        self.run_filter_open = True

    def _cycle_pending_run_filter(self, key, direction):
        options = {
            "filter_status": ("run_filter_pending_status", STATUS_FILTERS),
            "filter_mission": ("run_filter_pending_mission", MISSION_FILTERS),
            "filter_origin": ("run_filter_pending_origin", ORIGIN_FILTERS),
            "filter_started": ("run_filter_pending_started", STARTED_FILTERS),
            "filter_generations": (
                "run_filter_pending_generations",
                GENERATION_FILTERS,
            ),
        }
        if key not in options:
            return
        attribute, values = options[key]
        setattr(
            self,
            attribute,
            self._cycle(getattr(self, attribute), len(values), direction),
        )

    def _apply_run_filter_action(self, key):
        if key.startswith("filter_") and key not in {
            "filter_clear",
            "filter_cancel",
            "filter_apply",
        }:
            self._cycle_pending_run_filter(key, 1)
        elif key == "filter_clear":
            self.run_filter_pending_status = 0
            self.run_filter_pending_mission = 0
            self.run_filter_pending_origin = 0
            self.run_filter_pending_started = 0
            self.run_filter_pending_generations = 0
        elif key == "filter_cancel":
            self.run_filter_open = False
        elif key == "filter_apply":
            self.run_filter_status_index = self.run_filter_pending_status
            self.run_filter_mission_index = self.run_filter_pending_mission
            self.run_filter_origin_index = self.run_filter_pending_origin
            self.run_filter_started_index = self.run_filter_pending_started
            self.run_filter_generations_index = self.run_filter_pending_generations
            self.run_page = 0
            self.run_selected = 0
            self.run_filter_open = False

    def _check_run_filter_input(self):
        if self.game.BACK_KEY:
            self.run_filter_open = False
            return
        if self.game.UP_KEY:
            self.run_filter_selected = (
                self.run_filter_selected - 1
            ) % len(self.run_filter_buttons)
        elif self.game.DOWN_KEY:
            self.run_filter_selected = (
                self.run_filter_selected + 1
            ) % len(self.run_filter_buttons)
        if self.game.LEFT_KEY or self.game.RIGHT_KEY:
            direction = -1 if self.game.LEFT_KEY else 1
            self._cycle_pending_run_filter(
                self.run_filter_buttons[self.run_filter_selected].key,
                direction,
            )
        if self.game.mouse_clicked:
            for index, button in enumerate(self.run_filter_buttons):
                if button.hit_test(self.game.mouse_position):
                    self.run_filter_selected = index
                    self._apply_run_filter_action(button.key)
                    return
        if self.game.START_KEY:
            self._apply_run_filter_action(
                self.run_filter_buttons[self.run_filter_selected].key
            )

    def _activate_run_library_button(self, key):
        if key == "back":
            self.view = "setup"
            self.selected = 1
        elif key == "sort":
            self.run_sort_index = self._cycle(
                self.run_sort_index,
                len(SORT_FIELDS),
                1,
            )
            self.run_page = 0
            self.run_selected = 0
        elif key == "order":
            self.run_sort_descending = not self.run_sort_descending
            self.run_page = 0
            self.run_selected = 0
        elif key == "filter":
            self._open_run_filter()
        elif key == "previous_page":
            self.run_page = max(0, self.run_page - 1)
            self.run_selected = 0
        elif key == "next_page":
            self.run_page += 1
            self.run_selected = 0
        elif key.startswith("run:"):
            index = int(key.split(":", 1)[1])
            if 0 <= index < len(self.run_page_items):
                self._activate_run(self.run_page_items[index])

    def _check_runs_input(self):
        self._prepare_run_view()
        if self.run_filter_open:
            self._check_run_filter_input()
            return

        previous_search = self.run_search.value
        if self.run_search.focused:
            for event in self.game.events:
                if event.type != pg.KEYDOWN:
                    continue
                if event.key == pg.K_ESCAPE:
                    self.run_search.focused = False
                    self.game.BACK_KEY = False
                elif event.key in (pg.K_RETURN, pg.K_KP_ENTER):
                    self.run_search.focused = False
                    self.game.START_KEY = False
                else:
                    self.run_search.handle_event(event)
                    if event.key == pg.K_BACKSPACE:
                        self.game.BACK_KEY = False
                    if event.key == pg.K_SPACE:
                        self.game.START_KEY = False
            if self.run_search.value != previous_search:
                self.run_page = 0
                self.run_selected = 0

        if self.game.mouse_clicked:
            if self.run_search_rect.contains(self.game.mouse_position):
                self.run_search.focused = True
                return
            self.run_search.focused = False
            for button in self.run_buttons:
                if button.hit_test(self.game.mouse_position):
                    self._activate_run_library_button(button.key)
                    return

        if self.run_search.focused:
            return
        if self.game.BACK_KEY:
            self.view = "setup"
            self.selected = 1
            return
        if self.game.mouse_wheel:
            self.run_page = max(0, self.run_page - self.game.mouse_wheel)
            self.run_selected = 0
        if self.game.LEFT_KEY:
            self._activate_run_library_button("previous_page")
        elif self.game.RIGHT_KEY:
            self._activate_run_library_button("next_page")
        if self.run_page_items:
            if self.game.UP_KEY:
                self.run_selected = (self.run_selected - 1) % len(self.run_page_items)
            elif self.game.DOWN_KEY:
                self.run_selected = (self.run_selected + 1) % len(self.run_page_items)
            if self.game.START_KEY:
                self._activate_run(self.run_page_items[self.run_selected])

    def _draw_run_filter_dialog(self):
        shade = pg.Surface((self.game.DISPLAY_W, self.game.DISPLAY_H), pg.SRCALPHA)
        shade.fill((0, 0, 0, 165))
        self.game.display.blit(shade, (0, 0))
        panel = self._prepare_filter_buttons()
        rect = pg.Rect(panel.x, panel.y, panel.width, panel.height)
        pg.draw.rect(self.game.display, self.game.palette.panel, rect, border_radius=14)
        pg.draw.rect(
            self.game.display,
            self.game.palette.accent,
            rect,
            2,
            border_radius=14,
        )
        self.game.draw_text(
            "Filter training runs",
            self.game.layout.font_large,
            panel.center[0],
            panel.y + self.game.layout.margin + self.game.layout.font_large // 2,
        )
        self.game.draw_text(
            "Use Left/Right to change an option, then apply",
            self.game.layout.font_small,
            panel.center[0],
            panel.y + self.game.layout.margin + self.game.layout.font_large + self.game.layout.gap,
            self.game.palette.muted,
        )
        self.draw_buttons(self.run_filter_buttons)

    def draw_training_runs(self):
        layout, queried, _page_count = self._prepare_run_view()
        self.draw_background()
        self.draw_title(
            "Training Runs",
            f"Active and completed experiments · {len(queried)} matches · 10 per page",
        )
        for button in self.run_buttons:
            size = self.game.layout.font_normal
            if button.key.startswith("run:"):
                size = self._fitted_text_size(
                    button.label,
                    size,
                    max(1, button.rect.width - self.game.layout.gap * 2),
                    minimum=6,
                )
            button.draw(
                self.game.display,
                pg.font.Font(self.game.font_name, size),
                self.game.palette,
            )

        search = pg.Rect(
            layout["search"].x,
            layout["search"].y,
            layout["search"].width,
            layout["search"].height,
        )
        pg.draw.rect(
            self.game.display,
            self.game.palette.panel_alt,
            search,
            border_radius=max(4, search.height // 8),
        )
        pg.draw.rect(
            self.game.display,
            self.game.palette.accent
            if self.run_search.focused
            else self.game.palette.border,
            search,
            2,
            border_radius=max(4, search.height // 8),
        )
        search_text = self.run_search.value
        self.game.draw_text_left(
            search_text or "Search by name…",
            self.game.layout.font_normal,
            search.x + self.game.layout.gap,
            search.centery,
            self.game.palette.text if search_text else self.game.palette.muted,
            search.width - self.game.layout.gap * 2,
        )
        if not self.run_page_items:
            self.game.draw_text(
                "No runs match this name and filters",
                self.game.layout.font_normal,
                layout["list"].center[0],
                layout["list"].center[1],
                self.game.palette.muted,
            )
        if self.run_filter_open:
            self._draw_run_filter_dialog()

    def check_input(self):
        if self.view == "setup":
            self._check_setup_input()
            return
        if self.view == "about":
            self._check_about_input()
            return
        if self.view == "dashboard":
            self._check_dashboard_input()
            return
        rows = self._rows()
        if self.game.BACK_KEY:
            if self.view == "runs":
                self.view = "setup"
                self.selected = 0
            else:
                self._return()
            return
        if self.game.UP_KEY:
            self.selected = (self.selected - 1) % len(rows)
        if self.game.DOWN_KEY:
            self.selected = (self.selected + 1) % len(rows)
        if self.game.LEFT_KEY and self.view == "setup":
            self._edit_setup_value(rows[self.selected][1], -1)
        if self.game.RIGHT_KEY and self.view == "setup":
            self._edit_setup_value(rows[self.selected][1], 1)
        clicked = self.clicked_button()
        if clicked is not None:
            self.selected = self._visible_offset + clicked
        if not (self.game.START_KEY or clicked is not None):
            return
        if self.view == "setup":
            self._activate_setup(rows[self.selected][1])
        else:
            self._activate_run(rows[self.selected][1])

    def display_menu(self):
        self.run_display = True
        self.game.reset_keys()
        while self.run_display and self.game.running:
            self._consume_launch_result()
            self._consume_stop_result()
            self._consume_insight_result()
            self._refresh_runs()
            self.begin_frame()
            if self.view == "about":
                self.check_input()
                if not self.run_display:
                    break
                if self.view != "about":
                    continue
                self.draw_training_about()
                self.blit_screen()
                continue
            if self.view == "dashboard":
                self.check_input()
                if not self.run_display:
                    break
                if self.view != "dashboard":
                    continue
                self.draw_training_dashboard()
                self.blit_screen()
                continue
            if self.view == "runs":
                self._check_runs_input()
                if not self.run_display:
                    break
                if self.view != "runs":
                    continue
                self.draw_training_runs()
                self.blit_screen()
                continue
            self.check_input()
            if not self.run_display:
                break
            if self.view != "setup":
                continue
            self.draw_training_cockpit()
            self.blit_screen()

    def _check_about_input(self):
        if self.game.BACK_KEY:
            self.view = "setup"
            self.selected = 2
            return
        if self.game.LEFT_KEY:
            self.about_page = max(0, self.about_page - 1)
        elif self.game.RIGHT_KEY:
            self.about_page = min(len(self.ABOUT_PAGES) - 1, self.about_page + 1)
        if self.game.mouse_clicked:
            for button in self.about_buttons:
                if not button.hit_test(self.game.mouse_position):
                    continue
                if button.key == "back":
                    self.view = "setup"
                    self.selected = 2
                elif button.key == "previous":
                    self.about_page = max(0, self.about_page - 1)
                else:
                    if self.about_page == len(self.ABOUT_PAGES) - 1:
                        self.view = "setup"
                        self.selected = 2
                    else:
                        self.about_page += 1
                return
        if self.game.START_KEY:
            if self.about_page == len(self.ABOUT_PAGES) - 1:
                self.view = "setup"
                self.selected = 2
            else:
                self.about_page += 1

    def draw_training_about(self):
        self.draw_background()
        page_title, subtitle, entries = self.ABOUT_PAGES[self.about_page]
        self.draw_title("About AI Training", f"{page_title} · {self.about_page + 1}/{len(self.ABOUT_PAGES)}")
        metrics = self.game.layout
        panel_top = metrics.margin + metrics.font_large + metrics.font_small + metrics.gap * 3
        footer_y = self.game.DISPLAY_H - metrics.margin - metrics.target_height
        panel = RectSpec(
            metrics.margin,
            panel_top,
            self.game.DISPLAY_W - metrics.margin * 2,
            max(1, footer_y - metrics.gap - panel_top),
        )
        panel_rect = self._draw_dashboard_panel(panel, accent=self.game.palette.accent)
        self.game.draw_text_left(
            subtitle,
            metrics.font_small,
            panel_rect.x + metrics.margin,
            panel_rect.y + metrics.margin,
            self.game.palette.accent,
            panel_rect.width - metrics.margin * 2,
        )
        entry_area = RectSpec(
            panel.x + metrics.margin,
            panel.y + metrics.margin + metrics.font_small + metrics.gap,
            panel.width - metrics.margin * 2,
            panel.height - metrics.margin * 2 - metrics.font_small - metrics.gap,
        )
        rows = metrics.vertical_rows(
            len(entries),
            entry_area,
            gap=max(4, metrics.gap // 2),
        )
        for (heading, description), row in zip(entries, rows):
            rect = pg.Rect(row.x, row.y, row.width, row.height)
            pg.draw.rect(self.game.display, self.game.palette.panel_alt, rect, border_radius=8)
            pg.draw.rect(self.game.display, self.game.palette.border, rect, 1, border_radius=8)
            heading_width = min(max(150, row.width // 4), 280)
            self.game.draw_text_left(
                heading,
                metrics.font_small,
                row.x + metrics.gap,
                row.y + row.height // 2,
                self.game.palette.accent,
                heading_width - metrics.gap,
            )
            self.game.draw_text_left(
                description,
                max(11, metrics.font_small - 1),
                row.x + heading_width,
                row.y + row.height // 2,
                self.game.palette.text,
                row.width - heading_width - metrics.gap,
            )

        footer = RectSpec(
            metrics.margin,
            footer_y,
            self.game.DISPLAY_W - metrics.margin * 2,
            metrics.target_height,
        )
        gap = metrics.gap
        button_width = (footer.width - gap * 2) // 3
        labels = (
            ("back", "Back"),
            ("previous", "Previous"),
            (
                "next",
                "Done" if self.about_page == len(self.ABOUT_PAGES) - 1 else "Next",
            ),
        )
        self.about_buttons = []
        for index, (key, label) in enumerate(labels):
            rect = RectSpec(
                footer.x + index * (button_width + gap),
                footer.y,
                button_width,
                footer.height,
            )
            self.about_buttons.append(
                Button(
                    key,
                    label,
                    rect,
                    enabled=key != "previous" or self.about_page > 0,
                    selected=key == "next",
                    hovered=rect.contains(self.game.mouse_position),
                )
            )
        self.draw_buttons(self.about_buttons)

    def _check_dashboard_input(self):
        if self.adoption_source is not None or self.adoption_receipt is not None:
            self._check_adoption_input()
            return
        destination = self._arena_destination()
        if destination != ArenaDestination.RESULTS:
            self._check_progress_input(destination)
            return
        if self._dashboard_kind() == TrainingKind.PLAYER_DECK.value:
            self._check_counter_dashboard_input()
            return
        if self._dashboard_kind() == TrainingKind.MATCHUP_EVALUATION.value:
            self._check_mission_dashboard_input()
            return
        if self._dashboard_kind() == TrainingKind.DECK_BUILDER.value:
            self._check_evolution_dashboard_input()
            return
        pages = self._dashboard_pages()
        if self.game.BACK_KEY:
            self.view = "runs"
            self.dashboard_item = None
            return
        if self.game.LEFT_KEY:
            self.dashboard_page = (self.dashboard_page - 1) % len(pages)
        elif self.game.RIGHT_KEY:
            self.dashboard_page = (self.dashboard_page + 1) % len(pages)
        if self.game.mouse_clicked:
            for button in self.dashboard_buttons:
                if button.hit_test(self.game.mouse_position):
                    if button.key == "back":
                        self.view = "runs"
                        self.dashboard_item = None
                    elif button.key == "previous":
                        self.dashboard_page = (
                            self.dashboard_page - 1
                        ) % len(pages)
                    elif button.key == "next":
                        self.dashboard_page = (
                            self.dashboard_page + 1
                        ) % len(pages)
                    elif button.key.startswith("page:"):
                        self.dashboard_page = int(button.key.split(":", 1)[1])
                    elif button.key == "stop":
                        self._stop_dashboard_job()
                    return
        if self.game.START_KEY:
            self.dashboard_page = (self.dashboard_page + 1) % len(pages)

    def _arena_destination(self):
        item = self.dashboard_item
        return arena_destination(
            str(getattr(item, "status", "pending") or "pending"),
            watched_live=getattr(self, "dashboard_watching_live", False),
            results_opened=getattr(self, "dashboard_results_opened", False),
            artifact=getattr(self, "dashboard_artifact_status", None),
        )

    def _open_dashboard_log(self):
        item = self.dashboard_item
        if not isinstance(item, TrainingJob):
            self.show_lines(
                "Historical run",
                (getattr(item, "detail", "No local process log is linked."),),
            )
            return
        lines = self.service.tail(item.log_path, 12)
        self.show_lines(item.job_id, lines or ("No trainer messages recorded yet",))

    def _check_progress_input(self, destination):
        if self.game.BACK_KEY:
            self.view = "runs"
            self.dashboard_item = None
            return
        step = max(48, self.game.layout.target_height)
        if self.game.UP_KEY:
            self.dashboard_scroll -= step
        elif self.game.DOWN_KEY:
            self.dashboard_scroll += step
        for event in self.game.events:
            if event.type == pg.KEYDOWN and event.key == pg.K_PAGEUP:
                self.dashboard_scroll -= self.game.DISPLAY_H // 2
            elif event.type == pg.KEYDOWN and event.key == pg.K_PAGEDOWN:
                self.dashboard_scroll += self.game.DISPLAY_H // 2
            elif event.type == pg.KEYDOWN and event.key == pg.K_HOME:
                self.dashboard_scroll = 0
            elif event.type == pg.KEYDOWN and event.key == pg.K_END:
                self.dashboard_scroll = self.dashboard_max_scroll
        if self.game.mouse_wheel:
            self.dashboard_scroll -= self.game.mouse_wheel * step
        self.dashboard_scroll = max(
            0, min(self.dashboard_scroll, self.dashboard_max_scroll)
        )
        if self.dashboard_buttons:
            if self.game.LEFT_KEY:
                self.dashboard_action = (self.dashboard_action - 1) % len(
                    self.dashboard_buttons
                )
            elif self.game.RIGHT_KEY:
                self.dashboard_action = (self.dashboard_action + 1) % len(
                    self.dashboard_buttons
                )
        selected = None
        if self.game.mouse_clicked:
            selected = next(
                (
                    button
                    for button in self.dashboard_buttons
                    if button.hit_test(self.game.mouse_position)
                ),
                None,
            )
        elif self.game.START_KEY and self.dashboard_buttons:
            selected = self.dashboard_buttons[
                self.dashboard_action % len(self.dashboard_buttons)
            ]
        if selected is None or not selected.enabled:
            return
        if selected.key == "back":
            self.view = "runs"
            self.dashboard_item = None
        elif selected.key == "log":
            self._open_dashboard_log()
        elif selected.key == "stop":
            self._stop_dashboard_job()
        elif selected.key == "open_results":
            self.dashboard_results_opened = True
            self.dashboard_scroll = 0
            self.dashboard_action = 0

    def _check_mission_dashboard_input(self):
        """Keyboard, wheel, and footer controls shared by mission detail views."""
        if self.game.BACK_KEY:
            self.view = "runs"
            self.dashboard_item = None
            return
        scroll_step = max(48, self.game.layout.target_height)
        if self.game.UP_KEY:
            self.dashboard_scroll -= scroll_step
        elif self.game.DOWN_KEY:
            self.dashboard_scroll += scroll_step
        if self.game.mouse_wheel:
            self.dashboard_scroll -= self.game.mouse_wheel * scroll_step
        self.dashboard_scroll = max(
            0, min(self.dashboard_scroll, self.dashboard_max_scroll)
        )

        if self.dashboard_buttons:
            if self.game.LEFT_KEY:
                self.dashboard_action = (self.dashboard_action - 1) % len(
                    self.dashboard_buttons
                )
            elif self.game.RIGHT_KEY:
                self.dashboard_action = (self.dashboard_action + 1) % len(
                    self.dashboard_buttons
                )
            self.dashboard_action %= len(self.dashboard_buttons)

        selected = None
        if self.game.mouse_clicked:
            selected = next(
                (
                    button
                    for button in self.dashboard_buttons
                    if button.hit_test(self.game.mouse_position)
                ),
                None,
            )
        elif self.game.START_KEY and self.dashboard_buttons:
            selected = self.dashboard_buttons[self.dashboard_action]
        if selected is None:
            return
        if selected.key == "back":
            self.view = "runs"
            self.dashboard_item = None
        elif selected.key == "stop":
            self._stop_dashboard_job()

    def _check_counter_dashboard_input(self):
        if self.game.BACK_KEY:
            self.view = "runs"
            self.dashboard_item = None
            return
        scroll_step = max(48, self.game.layout.target_height)
        for event in self.game.events:
            if event.type != pg.KEYDOWN:
                continue
            if event.key == pg.K_TAB:
                self.counter_focus = (
                    "footer" if self.counter_focus == "candidates" else "candidates"
                )
            elif event.key == pg.K_PAGEUP:
                self.dashboard_scroll -= max(scroll_step, self.game.DISPLAY_H // 2)
            elif event.key == pg.K_PAGEDOWN:
                self.dashboard_scroll += max(scroll_step, self.game.DISPLAY_H // 2)
            elif event.key == pg.K_HOME:
                self.dashboard_scroll = 0
            elif event.key == pg.K_END:
                self.dashboard_scroll = self.dashboard_max_scroll

        if self.game.mouse_wheel:
            if (
                self.counter_candidate_viewport is not None
                and self.counter_candidate_viewport.contains(self.game.mouse_position)
            ):
                max_start = max(
                    0,
                    len(self.counter_candidate_keys) - self.counter_candidate_capacity,
                )
                self.counter_candidate_scroll = max(
                    0,
                    min(
                        max_start,
                        self.counter_candidate_scroll - self.game.mouse_wheel,
                    ),
                )
            else:
                self.dashboard_scroll -= self.game.mouse_wheel * scroll_step

        if self.counter_focus == "candidates" and self.counter_candidate_keys:
            try:
                index = self.counter_candidate_keys.index(self.counter_candidate_key)
            except ValueError:
                index = 0
            if self.game.UP_KEY:
                index = max(0, index - 1)
            elif self.game.DOWN_KEY:
                index = min(len(self.counter_candidate_keys) - 1, index + 1)
            self.counter_candidate_key = self.counter_candidate_keys[index]
            if index < self.counter_candidate_scroll:
                self.counter_candidate_scroll = index
            elif index >= self.counter_candidate_scroll + self.counter_candidate_capacity:
                self.counter_candidate_scroll = index - self.counter_candidate_capacity + 1
        elif self.counter_focus == "footer":
            if self.game.UP_KEY:
                self.dashboard_scroll -= scroll_step
            elif self.game.DOWN_KEY:
                self.dashboard_scroll += scroll_step
            if self.dashboard_buttons:
                if self.game.LEFT_KEY:
                    self.dashboard_action = (self.dashboard_action - 1) % len(
                        self.dashboard_buttons
                    )
                elif self.game.RIGHT_KEY:
                    self.dashboard_action = (self.dashboard_action + 1) % len(
                        self.dashboard_buttons
                    )

        self.dashboard_scroll = max(
            0, min(self.dashboard_scroll, self.dashboard_max_scroll)
        )
        if self.game.mouse_clicked:
            for key, rect in self.counter_candidate_rects:
                if rect.contains(self.game.mouse_position):
                    self.counter_candidate_key = key
                    self.counter_focus = "candidates"
                    return
            for index, button in enumerate(self.dashboard_buttons):
                if button.hit_test(self.game.mouse_position):
                    self.dashboard_action = index
                    if button.key == "back":
                        self.view = "runs"
                        self.dashboard_item = None
                    elif button.key == "stop":
                        self._stop_dashboard_job()
                    elif button.key == "adopt":
                        self._adopt_counter_selected()
                    return
        if (
            self.game.START_KEY
            and self.counter_focus == "footer"
            and self.dashboard_buttons
        ):
            button = self.dashboard_buttons[self.dashboard_action % len(self.dashboard_buttons)]
            if button.key == "back":
                self.view = "runs"
                self.dashboard_item = None
            elif button.key == "stop":
                self._stop_dashboard_job()
            elif button.key == "adopt":
                self._adopt_counter_selected()

    def _adopt_counter_selected(self):
        detail = (
            self.dashboard_insights.counter
            if self.dashboard_insights is not None
            else None
        )
        selected = self._counter_selected(detail)
        if selected is None:
            return
        card_ids = tuple(
            card.card_id
            for card in selected.deck.cards
            for _ in range(card.copies)
        )
        self._begin_adoption(
            AdoptableDeck(
                selected.deck.deck_id,
                selected.deck.name,
                card_ids,
                f"Counter run · {selected.deck.name}",
            )
        )

    def _evolution_selected(self, detail: EvolutionPresentation | None):
        if detail is None or not detail.decks:
            self.evolution_selected_deck_id = None
            return None
        selected = detail.deck(self.evolution_selected_deck_id)
        if selected is None:
            self.evolution_selected_deck_id = detail.default_deck_id
            selected = detail.deck(self.evolution_selected_deck_id)
        if selected is None:
            selected = detail.decks[0]
            self.evolution_selected_deck_id = selected.deck_id
        return selected

    def _cycle_evolution_filter(self, detail, direction=1):
        generations = sorted(
            {deck.generation for deck in detail.decks if deck.generation},
            reverse=True,
        )
        options = [None, *generations]
        try:
            index = options.index(self.evolution_generation_filter)
        except ValueError:
            index = 0
        self.evolution_generation_filter = options[(index + direction) % len(options)]
        self.evolution_deck_scroll = 0

    def _check_evolution_dashboard_input(self):
        if self.game.BACK_KEY:
            self.view = "runs"
            self.dashboard_item = None
            return
        pages = self._dashboard_pages()
        detail = (
            self.dashboard_insights.evolution
            if self.dashboard_insights is not None
            else None
        )
        step = max(48, self.game.layout.target_height)
        action_indices = [
            index
            for index, button in enumerate(self.dashboard_buttons)
            if not button.key.startswith("page:")
        ]
        for event in self.game.events:
            if event.type != pg.KEYDOWN:
                continue
            if event.key == pg.K_PAGEUP:
                self.dashboard_scroll -= self.game.DISPLAY_H // 2
            elif event.key == pg.K_PAGEDOWN:
                self.dashboard_scroll += self.game.DISPLAY_H // 2
            elif event.key == pg.K_HOME:
                self.dashboard_scroll = 0
            elif event.key == pg.K_END:
                self.dashboard_scroll = self.dashboard_max_scroll
            elif event.key == pg.K_f and detail is not None:
                self._cycle_evolution_filter(detail)
            elif (
                event.key == pg.K_a
                and self.dashboard_page == 1
                and detail is not None
            ):
                self._activate_evolution_button("adopt", detail)
            elif event.key == pg.K_TAB:
                self.evolution_focus = (
                    "actions" if self.evolution_focus != "actions" else "decks"
                )
                if self.evolution_focus == "actions" and action_indices:
                    self.dashboard_action = action_indices[0]
        if self.game.LEFT_KEY:
            if self.evolution_focus == "actions" and action_indices:
                try:
                    index = action_indices.index(self.dashboard_action)
                except ValueError:
                    index = 0
                self.dashboard_action = action_indices[(index - 1) % len(action_indices)]
            else:
                self.dashboard_page = (self.dashboard_page - 1) % len(pages)
                self.dashboard_scroll = 0
        elif self.game.RIGHT_KEY:
            if self.evolution_focus == "actions" and action_indices:
                try:
                    index = action_indices.index(self.dashboard_action)
                except ValueError:
                    index = -1
                self.dashboard_action = action_indices[(index + 1) % len(action_indices)]
            else:
                self.dashboard_page = (self.dashboard_page + 1) % len(pages)
                self.dashboard_scroll = 0
        if self.game.mouse_wheel:
            if (
                self.evolution_deck_viewport is not None
                and self.evolution_deck_viewport.contains(self.game.mouse_position)
                and self.evolution_deck_keys
            ):
                self.evolution_deck_scroll = max(
                    0,
                    min(
                        max(0, len(self.evolution_deck_keys) - 7),
                        self.evolution_deck_scroll - self.game.mouse_wheel,
                    ),
                )
            else:
                self.dashboard_scroll -= self.game.mouse_wheel * step
        self.dashboard_scroll = max(
            0, min(self.dashboard_scroll, self.dashboard_max_scroll)
        )
        if (
            self.evolution_focus != "actions"
            and self.dashboard_page in {1, 2, 3}
            and self.evolution_deck_keys
        ):
            try:
                index = self.evolution_deck_keys.index(
                    self.evolution_selected_deck_id
                )
            except ValueError:
                index = 0
            if self.game.UP_KEY:
                index = max(0, index - 1)
            elif self.game.DOWN_KEY:
                index = min(len(self.evolution_deck_keys) - 1, index + 1)
            self.evolution_selected_deck_id = self.evolution_deck_keys[index]
            if index < self.evolution_deck_scroll:
                self.evolution_deck_scroll = index
            elif index >= self.evolution_deck_scroll + 7:
                self.evolution_deck_scroll = index - 6
        if self.game.mouse_clicked:
            for key, rect in self.evolution_deck_rects:
                if rect.contains(self.game.mouse_position):
                    self.evolution_focus = "decks"
                    self.evolution_selected_deck_id = key
                    return
            for index, button in enumerate(self.dashboard_buttons):
                if not button.hit_test(self.game.mouse_position) or not button.enabled:
                    continue
                self.dashboard_action = index
                self.evolution_focus = (
                    "actions" if not button.key.startswith("page:") else "decks"
                )
                self._activate_evolution_button(button.key, detail)
                return
        if (
            self.game.START_KEY
            and self.evolution_focus == "actions"
            and self.dashboard_buttons
        ):
            button = self.dashboard_buttons[
                self.dashboard_action % len(self.dashboard_buttons)
            ]
            if button.enabled:
                self._activate_evolution_button(button.key, detail)

    def _activate_evolution_button(self, key, detail):
        if key == "back":
            self.view = "runs"
            self.dashboard_item = None
        elif key == "previous":
            self.dashboard_page = (self.dashboard_page - 1) % 5
            self.dashboard_scroll = 0
        elif key == "next":
            self.dashboard_page = (self.dashboard_page + 1) % 5
            self.dashboard_scroll = 0
        elif key.startswith("page:"):
            self.dashboard_page = int(key.split(":", 1)[1])
            self.dashboard_scroll = 0
        elif key == "filter" and detail is not None:
            self._cycle_evolution_filter(detail)
        elif key == "adopt" and detail is not None:
            selected = self._evolution_selected(detail)
            if selected is not None:
                artifact_path = getattr(selected, "player_artifact_path", None)
                manifest_path = (
                    str(Path(artifact_path).with_suffix(".player.json"))
                    if artifact_path
                    else None
                )
                if manifest_path is None:
                    project_root = Path(__file__).resolve().parents[2]
                    artifacts = discover_manifest_artifacts(
                        (
                            project_root / "neat_ai" / "trained_ai",
                            project_root / ".ui_training",
                        ),
                        selected.card_ids,
                    )
                    if artifacts:
                        manifest_path = str(artifacts[0].manifest_path)
                self._begin_adoption(
                    AdoptableDeck(
                        selected.deck_id,
                        selected.name,
                        selected.card_ids,
                        f"Evolution run DB {detail.training_id} · {selected.name}",
                        manifest_path,
                    )
                )

    def _begin_adoption(self, source: AdoptableDeck):
        if self._arena_destination() != ArenaDestination.RESULTS:
            self.message = "Decks can be adopted only from completed results"
            self.message_color = self.game.palette.danger
            return
        self.adoption_source = source
        suggested = f"{source.source_name} copy"[:32]
        self.adoption_input = TextInput(suggested, max_length=32, focused=True)
        self.adoption_error = ""
        self.adoption_conflict_id = None
        self.adoption_receipt = None
        self.adoption_action = 1

    def _close_adoption(self):
        self.adoption_source = None
        self.adoption_error = ""
        self.adoption_conflict_id = None
        self.adoption_receipt = None
        self.adoption_buttons = []
        self.adoption_action = 1

    def _save_adoption(self):
        if self.adoption_source is None:
            return
        try:
            database = DBUtil()
            receipt = DeckAdoptionService(database).adopt(
                self.adoption_source,
                self.adoption_input.value,
            )
        except DeckAdoptionConflict as error:
            self.adoption_error = str(error)
            self.adoption_conflict_id = error.existing_deck_id
            self.adoption_action = 0
            return
        except DeckAdoptionError as error:
            self.adoption_error = str(error)
            self.adoption_conflict_id = None
            return
        self.adoption_receipt = receipt
        self.adoption_source = None
        self.adoption_error = ""
        self.adoption_conflict_id = None
        self.adoption_action = 0
        # Refresh user-facing sources only after persistence and verification.
        self.deck_options = database.get_all_deck_options()
        self.deck_ids = [deck_id for deck_id, _name in self.deck_options]
        self.cockpit.deck_ids = tuple(self.deck_ids)

    def _open_adopted_deck(self, deck_id):
        if not deck_id:
            return
        self._close_adoption()
        self.run_display = False
        editor = DeckBuilderMenu(self.game, deck_id)
        self.game.curr_menu = editor
        editor.previous_menu = self
        editor.display_menu()

    def _check_adoption_input(self):
        if self.game.BACK_KEY:
            self._close_adoption()
            return
        if self.adoption_receipt is not None:
            if self.game.LEFT_KEY or self.game.RIGHT_KEY:
                self.adoption_action = 1 - self.adoption_action
        else:
            for event in self.game.events:
                if event.type == pg.KEYDOWN and event.key in (
                    pg.K_RETURN,
                    pg.K_KP_ENTER,
                    pg.K_ESCAPE,
                ):
                    continue
                self.adoption_input.handle_event(event)
            if self.game.LEFT_KEY:
                self.adoption_action = max(0, self.adoption_action - 1)
            elif self.game.RIGHT_KEY:
                self.adoption_action = min(
                    (2 if self.adoption_conflict_id else 1),
                    self.adoption_action + 1,
                )
        selected = None
        if self.game.mouse_clicked:
            selected = next(
                (
                    button
                    for button in self.adoption_buttons
                    if button.hit_test(self.game.mouse_position)
                ),
                None,
            )
        elif self.game.START_KEY:
            if self.adoption_buttons:
                selected = self.adoption_buttons[
                    self.adoption_action % len(self.adoption_buttons)
                ]
            elif self.adoption_receipt is None:
                self._save_adoption()
                return
        if selected is None:
            return
        if selected.key in {"cancel", "back_results"}:
            self._close_adoption()
        elif selected.key == "save":
            self._save_adoption()
        elif selected.key == "open_existing":
            self._open_adopted_deck(self.adoption_conflict_id)
        elif selected.key == "open_editor":
            self._open_adopted_deck(self.adoption_receipt.deck_id)

    def _draw_adoption_overlay(self):
        if self.adoption_source is None and self.adoption_receipt is None:
            return
        metrics = self.game.layout
        shade = pg.Surface((self.game.DISPLAY_W, self.game.DISPLAY_H), pg.SRCALPHA)
        shade.fill((0, 0, 0, 205))
        self.game.display.blit(shade, (0, 0))
        panel_spec = metrics.centered_panel(0.76, 0.76)
        panel = self._draw_dashboard_panel(panel_spec, accent=self.game.palette.accent)
        x = panel.x + metrics.margin
        width = panel.width - metrics.margin * 2
        y = panel.y + metrics.margin
        self.adoption_buttons = []
        if self.adoption_receipt is not None:
            receipt = self.adoption_receipt
            self.game.draw_text_left("DECK ADDED TO MY DECKS", metrics.font_large, x, y, self.game.palette.text, width)
            y += metrics.font_large + metrics.gap
            self.game.draw_text_left(receipt.name, metrics.font_normal, x, y, self.game.palette.success, width)
            y += metrics.font_normal * 2
            lines = (
                f"Fresh user deck ID: {receipt.deck_id}",
                f"Exact composition preserved: {len(receipt.card_ids)} cards",
                f"Original source remains unchanged: {receipt.source_id}",
                "Classification verified: My deck · not AI-generated",
                (
                    "Trained AI adopted for this exact composition"
                    if receipt.player_artifact_path
                    else "No compatible trained AI was available for this source"
                ),
            )
            for line in lines:
                self.game.draw_text_left(line, metrics.font_small, x, y, self.game.palette.text, width)
                y += metrics.font_normal * 2
            labels = (("back_results", "Back to results"), ("open_editor", "Open in deck editor"))
        else:
            source = self.adoption_source
            self.game.draw_text_left("SAVE A COPY TO MY DECKS", metrics.font_large, x, y, self.game.palette.text, width)
            y += metrics.font_large + metrics.gap
            self.game.draw_text_left("The generated training source stays unchanged.", metrics.font_small, x, y, self.game.palette.muted, width)
            y += metrics.font_normal * 2
            field = pg.Rect(x, y, width, metrics.target_height)
            pg.draw.rect(self.game.display, self.game.palette.panel_alt, field, border_radius=7)
            pg.draw.rect(self.game.display, self.game.palette.accent, field, 2, border_radius=7)
            self.game.draw_text_left(self.adoption_input.value or "New deck name", metrics.font_normal, field.x + metrics.gap, field.centery, self.game.palette.text if self.adoption_input.value else self.game.palette.muted, field.width - metrics.gap * 2)
            y = field.bottom + metrics.gap * 2
            self.game.draw_text_left(f"Source: {source.source_label}", metrics.font_small, x, y, self.game.palette.text, width)
            y += metrics.font_normal
            self.game.draw_text_left(f"Composition: {len(source.card_ids)} cards · exact IDs and copy counts", metrics.font_small, x, y, self.game.palette.text, width)
            y += metrics.font_normal + metrics.gap
            counts = {}
            for card_id in source.card_ids:
                counts[card_id] = counts.get(card_id, 0) + 1
            composition = " · ".join(f"{card_id} ×{count}" for card_id, count in counts.items())
            self._draw_wrapped_text(composition, max(9, metrics.font_small - 2), x, y, width, max_lines=4, color=self.game.palette.muted)
            y += metrics.font_small * 4 + metrics.gap
            if self.adoption_error:
                self._draw_wrapped_text(self.adoption_error, metrics.font_small, x, y, width, max_lines=2, color=self.game.palette.danger)
            labels = [
                ("cancel", "Cancel"),
                (
                    "save",
                    "Save deck + trained AI"
                    if source.player_artifact_manifest
                    else "Save as my deck",
                ),
            ]
            if self.adoption_conflict_id:
                labels.append(("open_existing", "Open existing deck"))
        gap = metrics.gap
        button_width = (width - gap * (len(labels) - 1)) // len(labels)
        button_y = panel.bottom - metrics.margin - metrics.target_height
        for index, (key, label) in enumerate(labels):
            rect = RectSpec(x + index * (button_width + gap), button_y, button_width, metrics.target_height)
            self.adoption_buttons.append(Button(key, label, rect, selected=index == self.adoption_action, hovered=rect.contains(self.game.mouse_position)))
        self.draw_buttons(self.adoption_buttons)

    def _dashboard_kind(self, insights=None):
        insights = insights or self.dashboard_insights
        if insights and insights.run_kind:
            return insights.run_kind
        item = self.dashboard_item
        if isinstance(item, TrainingRunSummary):
            return item.run_kind
        return str((getattr(item, "request", None) or {}).get("kind", ""))

    def _dashboard_pages(self, insights=None):
        kind = self._dashboard_kind(insights)
        if kind == TrainingKind.MATCHUP_EVALUATION.value:
            return ("Duel",)
        if kind == TrainingKind.PLAYER_DECK.value:
            return ("Counters",)
        if kind == TrainingKind.DECK_BUILDER.value:
            return ("Run pulse", "Population", "Matchups", "Composition", "Research")
        return self.BUILDER_DASHBOARD_PAGES

    def _dashboard_telemetry(self) -> TrainingTelemetry:
        now = pg.time.get_ticks()
        if (
            self.dashboard_telemetry is not None
            and now - self._dashboard_last_refresh < 800
        ):
            return self.dashboard_telemetry
        item = self.dashboard_item
        if isinstance(item, TrainingRunSummary):
            telemetry = self.service.database_telemetry(item)
        elif item is not None:
            telemetry = self.service.job_telemetry(item)
        else:
            telemetry = TrainingTelemetry(status="pending")
        self.dashboard_telemetry = telemetry
        self._dashboard_last_refresh = now
        return telemetry

    @staticmethod
    def _training_progress(telemetry: TrainingTelemetry) -> float:
        if telemetry.status == "completed":
            return 1.0
        if telemetry.phase_progress is not None:
            return max(0.0, min(1.0, telemetry.phase_progress))
        if telemetry.total_generations <= 0:
            return 0.0
        round_progress = (
            telemetry.round_completed / telemetry.round_total
            if telemetry.round_total > 0
            else 0.0
        )
        completed_generations = max(0, telemetry.generation - 1)
        return max(
            0.0,
            min(
                1.0,
                (completed_generations + round_progress)
                / telemetry.total_generations,
            ),
        )

    def _draw_dashboard_panel(self, spec, *, accent=None):
        rect = pg.Rect(spec.x, spec.y, spec.width, spec.height)
        pg.draw.rect(self.game.display, self.game.palette.panel, rect, border_radius=14)
        pg.draw.rect(
            self.game.display,
            accent or self.game.palette.border,
            rect,
            2,
            border_radius=14,
        )
        return rect

    def _draw_dashboard_bar(self, rect, ratio, color):
        pg.draw.rect(self.game.display, self.game.palette.disabled, rect, border_radius=6)
        ratio = max(0.0, min(1.0, ratio))
        if ratio:
            fill = rect.copy()
            fill.width = max(2, round(rect.width * ratio))
            pg.draw.rect(self.game.display, color, fill, border_radius=6)
        pg.draw.rect(self.game.display, self.game.palette.border, rect, 1, border_radius=6)

    @staticmethod
    def _duration_label(seconds):
        if seconds is None:
            return "—"
        seconds = max(0, round(seconds))
        if seconds < 60:
            return f"{seconds}s"
        hours, remainder = divmod(seconds, 3600)
        minutes = remainder // 60
        return f"{hours}h {minutes}m" if hours else f"{minutes}m"

    @staticmethod
    def _phase_label(phase):
        return {
            "controller_training": "Training controller",
            "checkpoint_evaluation": "Evaluating controller maturity",
            "counter_controller_training": "Training persistent controllers",
            "counter_evolution": "Evolving counter decks",
            "matchup_evaluation": "Evaluating deck matchup",
            "deck_evolution": "Evolving candidate decks",
            "training": "Training",
            "completed": "Run complete",
            "failed": "Run failed",
            "cancelled": "Run stopped",
            "interrupted": "Run interrupted",
        }.get(phase, str(phase or "Preparing").replace("_", " ").title())

    def _draw_dashboard_navigation(self, layout, insights=None):
        tabs = layout["tabs"]
        gap = self.game.layout.gap
        pages = self._dashboard_pages(insights)
        tab_width = (tabs.width - gap * (len(pages) - 1)) // len(pages)
        for index, label in enumerate(pages):
            rect = RectSpec(
                tabs.x + index * (tab_width + gap),
                tabs.y,
                tab_width,
                tabs.height,
            )
            self.dashboard_buttons.append(
                Button(
                    f"page:{index}",
                    label,
                    rect,
                    selected=index == self.dashboard_page,
                    hovered=rect.contains(self.game.mouse_position),
                )
            )

    def _draw_dashboard_footer(self, layout):
        footer = layout["footer"]
        gap = self.game.layout.gap
        labels = [("back", "Back to runs")]
        if self._can_stop_dashboard_job():
            labels.append(("stop", "Stop training"))
        labels.extend(
            (("previous", "Previous section"), ("next", "Next section"))
        )
        width = (footer.width - gap * (len(labels) - 1)) // len(labels)
        for index, (key, label) in enumerate(labels):
            rect = RectSpec(
                footer.x + index * (width + gap),
                footer.y,
                width,
                footer.height,
            )
            self.dashboard_buttons.append(
                Button(
                    key,
                    label,
                    rect,
                    selected=key == "next",
                    hovered=rect.contains(self.game.mouse_position),
                )
            )
        self.draw_buttons(self.dashboard_buttons)

    def _draw_empty_insights(self, content, message="Analyzing this run…"):
        panel = self._draw_dashboard_panel(content, accent=self.game.palette.accent)
        self.game.draw_text(
            message,
            self.game.layout.font_normal,
            panel.centerx,
            panel.centery,
            self.game.palette.muted,
        )

    def _draw_wrapped_text(self, text, size, x, y, max_width, max_lines=3, color=None):
        font = pg.font.Font(self.game.font_name, int(size))
        words = str(text).split()
        lines = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and font.size(candidate)[0] > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        truncated = len(lines) > max_lines
        lines = lines[:max_lines]
        if truncated and lines:
            while font.size(lines[-1] + "…")[0] > max_width and lines[-1]:
                lines[-1] = lines[-1][:-1]
            lines[-1] += "…"
        line_height = font.get_linesize()
        for index, line in enumerate(lines):
            self.game.draw_text_left(
                line,
                size,
                x,
                y + index * line_height,
                color or self.game.palette.text,
                max_width,
            )

    def _draw_performance_page(self, layout, insights: TrainingInsights | None):
        content = layout["content"]
        if insights is None:
            self._draw_empty_insights(content)
            return
        metrics = self.game.layout
        is_counter = insights.run_kind == TrainingKind.PLAYER_DECK.value
        is_matchup = insights.run_kind == TrainingKind.MATCHUP_EVALUATION.value
        is_evaluation = is_counter or is_matchup
        chart_spec, facts_spec = metrics.columns(content, (0.68, 0.32))
        chart_panel = self._draw_dashboard_panel(chart_spec, accent=self.game.palette.accent)
        facts_panel = self._draw_dashboard_panel(facts_spec)
        self.game.draw_text_left(
            "COUNTER PRESSURE CURVE"
            if is_counter
            else "MATCHUP WIN-RATE CURVE"
            if is_matchup
            else "POPULATION FITNESS BAND",
            metrics.font_normal,
            chart_panel.x + metrics.margin,
            chart_panel.y + metrics.margin,
            self.game.palette.text,
            chart_panel.width - metrics.margin * 2,
        )
        chart = pg.Rect(
            chart_panel.x + metrics.margin + max(32, metrics.font_small * 2),
            chart_panel.y + metrics.margin + metrics.font_normal + metrics.gap * 2,
            chart_panel.width - metrics.margin * 2 - max(32, metrics.font_small * 2),
            max(1, chart_panel.height - metrics.margin * 2 - metrics.font_normal - metrics.gap * 3 - metrics.font_small),
        )
        for index in range(5):
            y = chart.y + chart.height * index // 4
            pg.draw.line(
                self.game.display,
                self.game.palette.panel_alt,
                (chart.x, y),
                (chart.right, y),
                1,
            )
        rows = list(insights.generation_scores)
        if rows:
            values = [value for row in rows for value in row[1:4]]
            low, high = min(values), max(values)
            span = max(1.0, high - low)
            for index in range(5):
                axis_value = high - span * index / 4
                self.game.draw_text_left(
                    f"{axis_value:.0f}",
                    max(9, metrics.font_small - 3),
                    chart.x - max(30, metrics.font_small * 2),
                    chart.y + chart.height * index // 4,
                    self.game.palette.muted,
                    max(26, metrics.font_small * 2 - metrics.gap),
                )

            def points(column):
                return [
                    (
                        chart.x + round(index * chart.width / max(1, len(rows) - 1)),
                        chart.bottom - round((row[column] - low) / span * chart.height),
                    )
                    for index, row in enumerate(rows)
                ]

            series = (
                ((3, self.game.palette.success, "Deck A win rate" if is_matchup else "Selected deck win rate"),)
                if is_evaluation
                else (
                    (1, self.game.palette.danger, "Worst"),
                    (2, self.game.palette.muted, "Average"),
                    (3, self.game.palette.success, "Best"),
                )
            )
            for column, color, _label in series:
                line = points(column)
                if len(line) > 1:
                    pg.draw.lines(self.game.display, color, False, line, 3)
                for point in line:
                    pg.draw.circle(self.game.display, color, point, max(2, metrics.gap // 3))
            legend_x = chart.x
            for _column, color, label in series:
                pg.draw.circle(
                    self.game.display,
                    color,
                    (legend_x + 5, chart.bottom + metrics.gap),
                    4,
                )
                self.game.draw_text_left(
                    label,
                    max(10, metrics.font_small - 2),
                    legend_x + 13,
                    chart.bottom + metrics.gap,
                    self.game.palette.muted,
                )
                legend_x += max(58, chart.width // 4)
            self.game.draw_text_left(
                f"Gen {rows[0][0]}",
                max(9, metrics.font_small - 3),
                chart.x,
                chart.bottom + metrics.font_small + metrics.gap,
                self.game.palette.muted,
                chart.width // 2,
            )
            self.game.draw_text_left(
                f"Gen {rows[-1][0]}",
                max(9, metrics.font_small - 3),
                chart.right - max(60, chart.width // 4),
                chart.bottom + metrics.font_small + metrics.gap,
                self.game.palette.muted,
                max(60, chart.width // 4),
            )
        else:
            self.game.draw_text(
                "No generation scores recorded",
                metrics.font_small,
                chart.centerx,
                chart.centery,
                self.game.palette.muted,
            )

        self.game.draw_text_left(
            "RUN SIGNALS",
            metrics.font_normal,
            facts_panel.x + metrics.margin,
            facts_panel.y + metrics.margin,
            self.game.palette.text,
            facts_panel.width - metrics.margin * 2,
        )
        final = rows[-1] if rows else None
        evaluation_total = sum(insights.evaluation)
        generation_count = max((row[0] for row in rows), default=0)
        if evaluation_total:
            facts = (
                ("Generations completed", str(generation_count or "—")),
                (
                    "Final deck win rate" if is_evaluation else "Final champion",
                    f"{final[3]:.1f}%" if final and is_evaluation else f"{final[3]:.1f}" if final else "—",
                ),
                ("Final checkpoint games", str(evaluation_total)),
                ("All checkpoint trials", str(insights.total_evaluation_games or evaluation_total)),
                ("Deck A win rate" if is_matchup else "Deck win rate", f"{insights.evaluation[0] / evaluation_total * 100:.1f}%"),
            )
        else:
            facts = (
                ("Generations completed", str(generation_count or "—")),
                ("Final champion", f"{final[3]:.1f}" if final else "—"),
                ("Final spread", f"{final[3] - final[1]:.1f}" if final else "—"),
                ("Logged matchups", str(insights.total_matches or "—")),
            )
        available_top = facts_panel.y + metrics.margin + metrics.font_normal + metrics.gap
        row_height = max(28, (facts_panel.height - metrics.margin * 2 - metrics.font_normal - metrics.gap * 2) // 5)
        for index, (label, value) in enumerate(facts):
            y = available_top + index * row_height
            self.game.draw_text_left(
                label,
                max(10, metrics.font_small - 2),
                facts_panel.x + metrics.margin,
                y,
                self.game.palette.muted,
                facts_panel.width - metrics.margin * 2,
            )
            self.game.draw_text_left(
                value,
                metrics.font_normal,
                facts_panel.x + metrics.margin,
                y + metrics.font_small,
                self.game.palette.accent,
                facts_panel.width - metrics.margin * 2,
            )
        if evaluation_total:
            bar = pg.Rect(
                facts_panel.x + metrics.margin,
                facts_panel.bottom - metrics.margin - max(14, metrics.target_height // 3),
                facts_panel.width - metrics.margin * 2,
                max(14, metrics.target_height // 3),
            )
            self.game.draw_text_left(
                f"W {insights.evaluation[0]}  •  D {insights.evaluation[1]}  •  L {insights.evaluation[2]}",
                max(10, metrics.font_small - 2),
                bar.x,
                bar.y - metrics.font_small,
                self.game.palette.muted,
                bar.width,
            )
            x = bar.x
            colors = (
                self.game.palette.success,
                self.game.palette.muted,
                self.game.palette.danger,
            )
            for count, color in zip(insights.evaluation, colors):
                width = round(bar.width * count / evaluation_total)
                if width:
                    pg.draw.rect(self.game.display, color, (x, bar.y, width, bar.height))
                x += width
            pg.draw.rect(self.game.display, self.game.palette.border, bar, 1, border_radius=5)

    def _draw_evaluation_page(self, layout, insights: TrainingInsights | None):
        content = layout["content"]
        if insights is None:
            self._draw_empty_insights(content)
            return
        metrics = self.game.layout
        is_counter = insights.run_kind == TrainingKind.PLAYER_DECK.value
        is_matchup = insights.run_kind == TrainingKind.MATCHUP_EVALUATION.value
        hero_spec, outcomes_spec = metrics.columns(content, (0.40, 0.60))
        hero = self._draw_dashboard_panel(hero_spec, accent=self.game.palette.accent)
        outcomes = self._draw_dashboard_panel(outcomes_spec)
        wins, draws, losses = insights.evaluation
        total = wins + draws + losses
        win_rate = wins / total if total else 0.0

        self.game.draw_text_left(
            "FINAL COUNTER POPULATION" if is_counter else "FINAL MATCHUP CHECKPOINT",
            metrics.font_normal,
            hero.x + metrics.margin,
            hero.y + metrics.margin,
            self.game.palette.accent,
            hero.width - metrics.margin * 2,
        )
        self.game.draw_text_left(
            (
                f"{insights.subject} vs {insights.opponent}"
                if insights.opponent
                else insights.subject or "Selected deck"
            ),
            metrics.font_small,
            hero.x + metrics.margin,
            hero.y + metrics.margin + metrics.font_normal,
            self.game.palette.muted,
            hero.width - metrics.margin * 2,
        )
        radius = max(38, min(hero.width, hero.height) // 5)
        center = (hero.centerx, hero.centery)
        ring = pg.Rect(center[0] - radius, center[1] - radius, radius * 2, radius * 2)
        pg.draw.arc(self.game.display, self.game.palette.disabled, ring, 0, math.tau, 12)
        if total:
            pg.draw.arc(
                self.game.display,
                self.game.palette.success,
                ring,
                -math.pi / 2,
                -math.pi / 2 + math.tau * win_rate,
                12,
            )
        self.game.draw_text(
            f"{win_rate * 100:.0f}%" if total else "—",
            metrics.font_large,
            center[0],
            center[1] - metrics.font_small // 2,
            self.game.palette.success if total else self.game.palette.muted,
        )
        self.game.draw_text(
            "WIN RATE" if total else "EVALUATION PENDING",
            max(10, metrics.font_small - 2),
            center[0],
            center[1] + metrics.font_large // 2,
            self.game.palette.muted,
        )
        if total:
            interval_low, interval_high = wilson_interval(wins, total)
            self.game.draw_text(
                f"95% range {interval_low * 100:.0f}–{interval_high * 100:.0f}%",
                max(10, metrics.font_small - 2),
                center[0],
                center[1] + metrics.font_large // 2 + metrics.font_small,
                self.game.palette.accent,
            )
        elapsed = (
            f" • {insights.elapsed_seconds / 60:.1f} total run min"
            if insights.elapsed_seconds is not None
            else ""
        )
        self.game.draw_text(
            f"{total} test games{elapsed}" if total else "Runs after evolution completes",
            metrics.font_small,
            hero.centerx,
            hero.bottom - metrics.margin,
            self.game.palette.text,
        )

        self.game.draw_text_left(
            (
                "COUNTER GENERATIONS"
                if is_counter
                else "CONTROLLER CHECKPOINTS"
                if insights.skill_evaluations
                else "OUTCOME MIX"
            ),
            metrics.font_normal,
            outcomes.x + metrics.margin,
            outcomes.y + metrics.margin,
            self.game.palette.text,
            outcomes.width - metrics.margin * 2,
        )
        top = outcomes.y + metrics.margin + metrics.font_normal + metrics.gap * 2
        available = outcomes.bottom - metrics.margin * 2 - metrics.font_small - top
        if insights.skill_evaluations:
            rows = insights.skill_evaluations[-4:]
            row_height = max(42, available // max(1, len(rows)))
            gate_names = {10: "EARLY", 25: "DEVELOPING", 40: "MATURE"}
            colors = (
                self.game.palette.success,
                self.game.palette.muted,
                self.game.palette.danger,
            )
            for index, (generation, row_wins, row_draws, row_losses) in enumerate(rows):
                y = top + index * row_height
                row_total = row_wins + row_draws + row_losses
                rate = row_wins / row_total if row_total else 0.0
                gate = (
                    f"COUNTER {generation}"
                    if is_counter
                    else gate_names.get(generation, "FINAL")
                )
                checkpoint_label = (
                    f"{gate}" if is_counter else f"{gate} · GEN {generation}"
                    if outcomes.width < 600
                    else f"{gate} · GENERATION {generation}"
                )
                self.game.draw_text_left(
                    checkpoint_label,
                    metrics.font_small,
                    outcomes.x + metrics.margin,
                    y,
                    self.game.palette.text,
                    max(1, outcomes.width * 48 // 100 - metrics.margin),
                )
                self.game.draw_text_left(
                    f"{rate * 100:.1f}% · W {row_wins} D {row_draws} L {row_losses}",
                    max(10, metrics.font_small - 2),
                    outcomes.x + outcomes.width * 52 // 100,
                    y,
                    self.game.palette.accent,
                    max(1, outcomes.width * 48 // 100 - metrics.margin),
                )
                bar = pg.Rect(
                    outcomes.x + metrics.margin,
                    y + metrics.font_small + metrics.gap,
                    outcomes.width - metrics.margin * 2,
                    max(12, metrics.target_height // 3),
                )
                pg.draw.rect(self.game.display, self.game.palette.disabled, bar, border_radius=6)
                cursor = bar.x
                for count, color in zip((row_wins, row_draws, row_losses), colors):
                    width = round(bar.width * count / row_total) if row_total else 0
                    if width:
                        pg.draw.rect(self.game.display, color, (cursor, bar.y, width, bar.height))
                    cursor += width
                pg.draw.rect(self.game.display, self.game.palette.border, bar, 1, border_radius=6)
        else:
            labels = (
                ("Selected deck victories" if is_counter else "Deck A victories", wins, self.game.palette.success),
                ("Draws", draws, self.game.palette.muted),
                ("Counter victories" if is_counter else "Deck B victories", losses, self.game.palette.danger),
            )
            row_height = max(36, available // 3)
            for index, (label, count, color) in enumerate(labels):
                y = top + index * row_height
                percentage = count / total if total else 0.0
                self.game.draw_text_left(label, metrics.font_small, outcomes.x + metrics.margin, y, self.game.palette.text, outcomes.width - metrics.margin * 2)
                self.game.draw_text_left(
                    f"{count}  ·  {percentage * 100:.1f}%" if total else "pending",
                    max(10, metrics.font_small - 2),
                    outcomes.right - metrics.margin - max(100, outcomes.width // 4),
                    y,
                    color,
                    max(100, outcomes.width // 4),
                )
                self._draw_dashboard_bar(
                    pg.Rect(outcomes.x + metrics.margin, y + metrics.font_small + metrics.gap, outcomes.width - metrics.margin * 2, max(12, metrics.target_height // 3)),
                    percentage,
                    color,
                )
        footer_text = (
            f"{insights.total_evaluation_games or total} trials · {insights.opponent}"
        )
        if is_counter and insights.top_counter_name:
            rate = (
                f" ({insights.top_counter_win_rate * 100:.1f}% counter win rate)"
                if insights.top_counter_win_rate is not None
                else ""
            )
            footer_text = f"Top counter: {insights.top_counter_name}{rate}"
        self.game.draw_text_left(
            footer_text,
            max(10, metrics.font_small - 2),
            outcomes.x + metrics.margin,
            outcomes.bottom - metrics.margin,
            self.game.palette.muted,
            outcomes.width - metrics.margin * 2,
        )

    def _draw_matchup_card(self, rect, item, color, all_scores):
        metrics = self.game.layout
        pg.draw.rect(self.game.display, self.game.palette.panel_alt, rect, border_radius=10)
        pg.draw.rect(self.game.display, color, rect, 2, border_radius=10)
        self.game.draw_text_left(
            f"{item.deck_1}  VS  {item.deck_2}",
            metrics.font_small,
            rect.x + metrics.gap,
            rect.y + metrics.gap + metrics.font_small // 2,
            self.game.palette.text,
            rect.width - metrics.gap * 2,
        )
        self.game.draw_text_left(
            f"Deck 1 fitness {item.score:+.1f}  •  generation {item.generation}  •  {item.shared_cards} shared cards",
            max(10, metrics.font_small - 2),
            rect.x + metrics.gap,
            rect.y + metrics.gap + metrics.font_small * 2,
            color,
            rect.width - metrics.gap * 2,
        )
        snippets = (
            ", ".join(item.deck_1_cards[:4]),
            ", ".join(item.deck_2_cards[:4]),
        )
        self.game.draw_text_left(
            snippets[0],
            max(10, metrics.font_small - 3),
            rect.x + metrics.gap,
            rect.bottom - metrics.gap - metrics.font_small,
            self.game.palette.muted,
            rect.width - metrics.gap * 2,
        )
        self.game.draw_text_left(
            snippets[1],
            max(10, metrics.font_small - 3),
            rect.x + metrics.gap,
            rect.bottom - metrics.gap,
            self.game.palette.muted,
            rect.width - metrics.gap * 2,
        )
        bar = pg.Rect(
            rect.x + metrics.gap,
            rect.centery + metrics.gap // 2,
            rect.width - metrics.gap * 2,
            max(8, metrics.gap),
        )
        pg.draw.rect(self.game.display, self.game.palette.disabled, bar, border_radius=6)
        center_x = bar.centerx
        max_abs = max((abs(score) for score in all_scores), default=1.0) or 1.0
        extent = round((bar.width // 2) * abs(item.score) / max_abs)
        fill = pg.Rect(
            center_x if item.score >= 0 else center_x - extent,
            bar.y,
            max(1, extent),
            bar.height,
        )
        pg.draw.rect(self.game.display, color, fill, border_radius=4)
        pg.draw.line(
            self.game.display,
            self.game.palette.text,
            (center_x, bar.y - 2),
            (center_x, bar.bottom + 2),
            1,
        )
        pg.draw.rect(self.game.display, self.game.palette.border, bar, 1, border_radius=6)

    def _draw_matchups_page(self, layout, insights: TrainingInsights | None):
        content = layout["content"]
        if insights is None:
            self._draw_empty_insights(content)
            return
        metrics = self.game.layout
        favorable_spec, difficult_spec = metrics.columns(content, (1, 1))
        groups = (
            (favorable_spec, "STRONGEST DECK 1 RESULTS", insights.favorable_matchups, self.game.palette.success),
            (difficult_spec, "WEAKEST DECK 1 RESULTS", insights.difficult_matchups, self.game.palette.danger),
        )
        all_items = tuple(insights.favorable_matchups) + tuple(insights.difficult_matchups)
        all_scores = [item.score for item in all_items] or [0.0, 1.0]
        for spec, title, items, color in groups:
            panel = self._draw_dashboard_panel(spec, accent=color)
            self.game.draw_text_left(
                title,
                metrics.font_normal,
                panel.x + metrics.margin,
                panel.y + metrics.margin,
                color,
                panel.width - metrics.margin * 2,
            )
            self.game.draw_text_left(
                "Deck 1 perspective · at most 7 shared card copies",
                max(10, metrics.font_small - 2),
                panel.x + metrics.margin,
                panel.y + metrics.margin + metrics.font_normal,
                self.game.palette.muted,
                panel.width - metrics.margin * 2,
            )
            if not items:
                self.game.draw_text(
                    "No diverse matchup data",
                    metrics.font_small,
                    panel.centerx,
                    panel.centery,
                    self.game.palette.muted,
                )
                continue
            top = panel.y + metrics.margin + metrics.font_normal + metrics.font_small + metrics.gap
            available = panel.bottom - metrics.margin - top
            card_gap = metrics.gap
            card_height = max(1, (available - card_gap * (len(items) - 1)) // len(items))
            for index, item in enumerate(items):
                rect = pg.Rect(
                    panel.x + metrics.margin,
                    top + index * (card_height + card_gap),
                    panel.width - metrics.margin * 2,
                    card_height,
                )
                self._draw_matchup_card(rect, item, color, all_scores)

    def _draw_conclusions_page(self, layout, insights: TrainingInsights | None):
        content = layout["content"]
        if insights is None:
            self._draw_empty_insights(content)
            return
        metrics = self.game.layout
        notes_spec, cards_spec = metrics.columns(content, (0.58, 0.42))
        notes = self._draw_dashboard_panel(notes_spec, accent=self.game.palette.accent)
        cards = self._draw_dashboard_panel(cards_spec)
        self.game.draw_text_left(
            "WHAT THIS RUN SUGGESTS",
            metrics.font_normal,
            notes.x + metrics.margin,
            notes.y + metrics.margin,
            self.game.palette.accent,
            notes.width - metrics.margin * 2,
        )
        conclusions = insights.conclusions or ("More completed data is needed for conclusions.",)
        top = notes.y + metrics.margin + metrics.font_normal + metrics.gap
        available = notes.bottom - metrics.margin - top
        row_height = max(1, available // min(4, len(conclusions)))
        for index, conclusion in enumerate(conclusions[:4]):
            y = top + index * row_height
            badge = pg.Rect(notes.x + metrics.margin, y, max(22, metrics.target_height // 2), max(22, metrics.target_height // 2))
            pg.draw.rect(self.game.display, self.game.palette.panel_alt, badge, border_radius=8)
            pg.draw.rect(self.game.display, self.game.palette.accent, badge, 2, border_radius=8)
            self.game.draw_text(str(index + 1), metrics.font_small, badge.centerx, badge.centery, self.game.palette.accent)
            self._draw_wrapped_text(
                conclusion,
                metrics.font_small,
                badge.right + metrics.gap,
                y + metrics.font_small // 2,
                notes.right - metrics.margin - badge.right - metrics.gap,
                max_lines=max(1, min(3, row_height // max(1, metrics.font_small))),
                color=self.game.palette.text,
            )

        is_counter = insights.run_kind == TrainingKind.PLAYER_DECK.value
        is_evaluation = insights.run_kind in {
            TrainingKind.PLAYER_DECK.value,
            TrainingKind.MATCHUP_EVALUATION.value,
        }
        self.game.draw_text_left(
            "EVALUATION VERDICT" if is_evaluation else "CARD SIGNALS",
            metrics.font_normal,
            cards.x + metrics.margin,
            cards.y + metrics.margin,
            self.game.palette.text,
            cards.width - metrics.margin * 2,
        )
        self.game.draw_text_left(
            (
                f"{insights.subject or 'Selected deck'} vs {insights.opponent or 'opposition'}"
                if is_evaluation
                else "Average fitness of decks containing each card"
            ),
            max(10, metrics.font_small - 2),
            cards.x + metrics.margin,
            cards.y + metrics.margin + metrics.font_normal,
            self.game.palette.muted,
            cards.width - metrics.margin * 2,
        )
        if is_evaluation:
            wins, draws, losses = insights.evaluation
            total = wins + draws + losses
            rate = wins / total if total else 0.0
            interval_low, interval_high = wilson_interval(wins, total)
            verdict = (
                "LIKELY FAVORED"
                if interval_low > 0.5
                else "LIKELY UNFAVORED"
                if interval_high < 0.5
                else "INCONCLUSIVE"
            ) if total else "PENDING"
            verdict_color = (
                self.game.palette.success
                if interval_low > 0.5
                else self.game.palette.accent
                if interval_high >= 0.5
                else self.game.palette.danger
            )
            self.game.draw_text(verdict, metrics.font_large, cards.centerx, cards.y + cards.height // 3, verdict_color)
            self.game.draw_text(
                f"{rate * 100:.1f}% win rate" if total else "No completed evaluation games",
                metrics.font_normal,
                cards.centerx,
                cards.y + cards.height // 3 + metrics.font_large,
                self.game.palette.text,
            )
            self.game.draw_text(
                f"W {wins}  •  D {draws}  •  L {losses}  •  {total} games",
                metrics.font_small,
                cards.centerx,
                cards.y + cards.height * 2 // 3,
                self.game.palette.muted,
            )
            self.game.draw_text(
                f"95% win-rate range {interval_low * 100:.0f}–{interval_high * 100:.0f}% · descriptive, not causal",
                max(10, metrics.font_small - 2),
                cards.centerx,
                cards.y + cards.height * 2 // 3 + metrics.font_normal,
                self.game.palette.accent,
            )
            if is_counter and insights.top_counter_name:
                counter_rate = (
                    f" · {insights.top_counter_win_rate * 100:.1f}% wins"
                    if insights.top_counter_win_rate is not None
                    else ""
                )
                self.game.draw_text(
                    f"Top counter: {insights.top_counter_name}{counter_rate}",
                    max(10, metrics.font_small - 2),
                    cards.centerx,
                    cards.bottom - metrics.margin,
                    self.game.palette.danger,
                )
            return
        if not insights.top_cards:
            self.game.draw_text(
                "No cross-deck card data for this run",
                metrics.font_small,
                cards.centerx,
                cards.centery,
                self.game.palette.muted,
            )
            return
        max_score = max(abs(score) for _card, score, _uses in insights.top_cards) or 1.0
        top = cards.y + metrics.margin + metrics.font_normal + metrics.font_small + metrics.gap * 2
        row_height = max(24, (cards.bottom - metrics.margin - top) // len(insights.top_cards))
        for index, (card, score, uses) in enumerate(insights.top_cards):
            y = top + index * row_height
            self.game.draw_text_left(
                card,
                metrics.font_small,
                cards.x + metrics.margin,
                y,
                self.game.palette.text,
                cards.width - metrics.margin * 2,
            )
            label_width = max(80, cards.width // 5)
            bar = pg.Rect(
                cards.x + metrics.margin,
                y + metrics.font_small,
                max(1, cards.width - metrics.margin * 2 - label_width),
                max(8, metrics.gap),
            )
            self._draw_dashboard_bar(bar, abs(score) / max_score, self.game.palette.success)
            self.game.draw_text_left(
                f"{score:.1f} · {uses}x",
                max(10, metrics.font_small - 3),
                bar.right + metrics.gap,
                bar.centery,
                self.game.palette.muted,
                label_width - metrics.gap,
            )

    @staticmethod
    def _matchup_side_colors():
        return (105, 172, 225), (226, 100, 103), (168, 181, 196)

    @staticmethod
    def _counter_card_color(color, palette):
        return {
            "Red": palette.danger,
            "Blue": (105, 172, 225),
            "Black": (190, 176, 215),
            "Green": palette.success,
        }.get(color, palette.muted)

    def _draw_mission_footer(self, footer, *, focused=True, allow_adopt=False):
        labels = [("back", "Back to runs")]
        if self._can_stop_dashboard_job():
            labels.append(("stop", "Stop training"))
        if allow_adopt:
            labels.append(("adopt", "Adopt selected deck"))
        gap = self.game.layout.gap
        button_width = min(
            260,
            (footer.width - gap * (len(labels) - 1)) // len(labels),
        )
        self.dashboard_buttons = []
        for index, (key, label) in enumerate(labels):
            rect = RectSpec(
                footer.x + index * (button_width + gap),
                footer.y,
                button_width,
                footer.height,
            )
            self.dashboard_buttons.append(
                Button(
                    key,
                    label,
                    rect,
                    selected=focused and index == self.dashboard_action,
                    hovered=rect.contains(self.game.mouse_position),
                )
            )
        if self.dashboard_buttons:
            self.dashboard_action %= len(self.dashboard_buttons)
            for index, button in enumerate(self.dashboard_buttons):
                button.selected = focused and index == self.dashboard_action
        self.draw_buttons(self.dashboard_buttons)

    def _counter_selected(self, detail: CounterPresentation | None):
        if detail is None or not detail.candidates:
            self.counter_candidate_key = None
            return None
        selected = detail.candidate(self.counter_candidate_key)
        if selected is None:
            self.counter_candidate_key = detail.default_candidate_key
            selected = detail.candidate(self.counter_candidate_key)
        if selected is None:
            selected = detail.candidates[0]
            self.counter_candidate_key = selected.key
        return selected

    def _draw_counter_deck_panel(
        self,
        spec,
        *,
        title,
        deck,
        accent,
        provenance,
        comparison=(),
    ):
        panel = self._draw_dashboard_panel(spec, accent=accent)
        metrics = self.game.layout
        x = panel.x + metrics.margin
        width = panel.width - metrics.margin * 2
        y = panel.y + metrics.margin
        self.game.draw_text_left(
            title,
            max(15, metrics.font_normal - 3),
            x,
            y,
            self.game.palette.text,
            width,
        )
        y += metrics.font_normal
        self.game.draw_text_left(
            deck.name,
            metrics.font_normal,
            x,
            y,
            accent,
            width,
        )
        y += metrics.font_normal
        self.game.draw_text_left(
            f"{deck.total_cards} cards · {deck.distinct_cards} distinct",
            max(9, metrics.font_small - 3),
            x,
            y,
            self.game.palette.muted,
            width,
        )
        y += metrics.font_small
        self.game.draw_text_left(
            provenance,
            max(9, metrics.font_small - 4),
            x,
            y,
            self.game.palette.muted,
            width,
        )
        y += metrics.font_small + metrics.gap * 2
        if not deck.cards:
            self._draw_wrapped_text(
                "Saved composition is unavailable. No current database deck has been substituted.",
                metrics.font_small,
                x,
                y,
                width,
                max_lines=3,
                color=self.game.palette.danger,
            )
            y += metrics.font_small * 3 + metrics.gap
        else:
            row_height = max(24, metrics.font_small + 7)
            for card in deck.cards:
                row = pg.Rect(x, y, width, row_height)
                pg.draw.rect(
                    self.game.display,
                    self.game.palette.panel_alt,
                    row,
                    border_radius=6,
                )
                color = self._counter_card_color(card.color, self.game.palette)
                pg.draw.rect(
                    self.game.display,
                    color,
                    (row.x, row.y, max(5, metrics.gap // 2), row.height),
                    border_radius=5,
                )
                self.game.draw_text_left(
                    card.name,
                    metrics.font_small,
                    row.x + metrics.gap,
                    row.centery,
                    self.game.palette.text,
                    max(1, row.width - metrics.gap * 5),
                )
                self.game.draw_text_left(
                    f"×{card.copies}",
                    metrics.font_small,
                    row.right - metrics.gap * 3,
                    row.centery,
                    color,
                    metrics.gap * 3,
                )
                y += row_height + max(4, metrics.gap // 2)
        if comparison:
            y += metrics.gap
            pg.draw.line(
                self.game.display,
                self.game.palette.border,
                (x, y),
                (panel.right - metrics.margin, y),
            )
            y += metrics.gap * 2
            self.game.draw_text_left(
                "COMPOSITION COMPARISON",
                max(10, metrics.font_small - 2),
                x,
                y,
                self.game.palette.accent,
                width,
            )
            y += metrics.font_normal
            for line in comparison:
                self.game.draw_text_left(
                    line,
                    max(9, metrics.font_small - 3),
                    x,
                    y,
                    self.game.palette.muted,
                    width,
                )
                y += metrics.font_normal

    def _draw_counter_result_bar(self, panel, candidate, y):
        metrics = self.game.layout
        x = panel.x + metrics.margin
        width = panel.width - metrics.margin * 2
        segments = counter_bar_segments(candidate)
        colors = {
            "counter": self.game.palette.success,
            "draw": (168, 181, 196),
            "subject": self.game.palette.danger,
        }
        bar = pg.Rect(x, y, width, max(22, metrics.target_height // 2))
        cursor = bar.x
        for index, segment in enumerate(segments):
            segment_width = (
                bar.right - cursor
                if index == len(segments) - 1
                else round(bar.width * segment.ratio)
            )
            if segment_width > 0:
                segment_rect = pg.Rect(cursor, bar.y, segment_width, bar.height)
                pg.draw.rect(self.game.display, colors[segment.key], segment_rect)
                if segment.inline_label:
                    self.game.draw_text(
                        f"{segment.ratio * 100:.1f}%",
                        max(9, metrics.font_small - 4),
                        segment_rect.centerx,
                        segment_rect.centery,
                        self.game.palette.background,
                    )
            cursor += segment_width
        pg.draw.rect(self.game.display, self.game.palette.border, bar, 1, border_radius=5)
        external = [segment for segment in segments if not segment.inline_label]
        if external:
            labels = {
                "counter": "Counter",
                "draw": "Draw",
                "subject": "Selected deck",
            }
            slot = width // len(external)
            for index, segment in enumerate(external):
                self.game.draw_text_left(
                    f"{labels[segment.key]} {segment.ratio * 100:.1f}%",
                    max(9, metrics.font_small - 4),
                    x + index * slot,
                    bar.bottom + metrics.font_small,
                    colors[segment.key],
                    slot,
                )
        return bar.bottom + (metrics.font_normal if external else metrics.gap)

    def _draw_counter_result_panel(
        self, spec, detail, selected, telemetry, run_identity
    ):
        panel = self._draw_dashboard_panel(spec, accent=self.game.palette.accent)
        metrics = self.game.layout
        x = panel.x + metrics.margin
        width = panel.width - metrics.margin * 2
        y = panel.y + metrics.margin
        self.game.draw_text_left(
            "HEAD-TO-HEAD RESULT",
            max(15, metrics.font_normal - 3),
            x,
            y,
            self.game.palette.text,
            width,
        )
        y += metrics.font_normal
        self.game.draw_text_left(
            f"Run · {run_identity}",
            max(9, metrics.font_small - 4),
            x,
            y,
            self.game.palette.muted,
            width,
        )
        y += metrics.font_small + metrics.gap
        if selected is None:
            self.game.draw_text_left(
                "No counter decks evaluated yet",
                metrics.font_normal,
                x,
                y,
                self.game.palette.accent,
                width,
            )
            y += metrics.font_normal
            self._draw_wrapped_text(
                "The first genuine candidate set appears after a counter generation completes.",
                metrics.font_small,
                x,
                y,
                width,
                max_lines=3,
                color=self.game.palette.muted,
            )
            y += metrics.font_small * 3 + metrics.gap
        elif not selected.valid:
            self.game.draw_text_left(
                selected.deck.name,
                metrics.font_normal,
                x,
                y,
                self.game.palette.text,
                width,
            )
            y += metrics.font_normal
            self._draw_wrapped_text(
                f"Result unavailable: {selected.issue}",
                metrics.font_small,
                x,
                y,
                width,
                max_lines=3,
                color=self.game.palette.danger,
            )
            y += metrics.font_small * 3 + metrics.gap
        else:
            rate = selected.counter_win_rate
            self.game.draw_text_left(
                f"Counter win rate {rate * 100:.1f}% · vs {detail.subject.name}",
                metrics.font_normal,
                x,
                y,
                self.game.palette.accent,
                width,
            )
            y += metrics.font_normal
            self.game.draw_text_left(
                f"{selected.deck.name} · {selected.games:,} seat-balanced games",
                max(10, metrics.font_small - 2),
                x,
                y,
                self.game.palette.muted,
                width,
            )
            y += metrics.font_normal
            if selected.exploratory:
                self._draw_wrapped_text(
                    "Exploratory sample · below 1,000-game comparison target",
                    max(10, metrics.font_small - 2),
                    x,
                    y,
                    width,
                    max_lines=2,
                    color=self.game.palette.danger,
                )
                y += metrics.font_small * 2
            self.game.draw_text_left(
                f"Counter {selected.counter_wins}  ·  Draws {selected.draws}  ·  {detail.subject.name} {selected.subject_wins}",
                max(9, metrics.font_small - 3),
                x,
                y,
                self.game.palette.text,
                width,
            )
            y += metrics.font_normal
            y = self._draw_counter_result_bar(panel, selected, y)
            self.game.draw_text_left(
                "This is the selected candidate's sample, not the pooled population.",
                max(9, metrics.font_small - 4),
                x,
                y,
                self.game.palette.muted,
                width,
            )
            y += metrics.font_normal

        pg.draw.line(
            self.game.display,
            self.game.palette.border,
            (x, y),
            (panel.right - metrics.margin, y),
        )
        y += metrics.gap * 2
        workload = detail.workload if detail is not None else None
        self.game.draw_text_left(
            "RUN DEPTH", metrics.font_normal, x, y, self.game.palette.text, width
        )
        y += metrics.font_normal + metrics.gap
        if workload is None:
            return
        controller_games = workload.controller_population_size ** 2
        facts = (
            (
                "Counter generations",
                f"{workload.completed_counter_generations} / {workload.requested_counter_generations}",
            ),
            (
                "Controller generations",
                f"~{workload.completed_controller_generations_estimate} / {workload.requested_controller_generations}",
            ),
            (
                "Controller populations",
                f"2 × {workload.controller_population_size} · ~{controller_games} learning games/gen",
            ),
            (
                "Final legal candidates",
                f"{workload.final_candidate_count} actual · {workload.builder_population_size} configured pop",
            ),
            (
                "Validation work",
                f"{workload.recorded_validation_games:,} recorded / {workload.planned_validation_games:,} planned",
            ),
            (
                "Controller learning",
                f"~{workload.completed_learning_games_estimate:,} / ~{workload.planned_learning_games:,}",
            ),
            (
                "Overall simulations",
                f"~{workload.completed_total_estimate:,} / ~{workload.planned_total_games:,}",
            ),
        )
        label_size = max(9, metrics.font_small - 6)
        value_size = max(10, metrics.font_small - 4)
        row_height = max(22, metrics.font_small + 3)
        for label, value in facts:
            self.game.draw_text_left(
                label,
                label_size,
                x,
                y,
                self.game.palette.muted,
                width * 38 // 100,
            )
            self.game.draw_text_left(
                value,
                value_size,
                x + width * 40 // 100,
                y,
                self.game.palette.text,
                width * 60 // 100,
            )
            y += row_height
        pooled_total = (
            detail.pooled_counter_wins
            + detail.pooled_draws
            + detail.pooled_subject_wins
        )
        if pooled_total:
            self.game.draw_text_left(
                f"Pooled final population: counters {detail.pooled_counter_wins}, draws {detail.pooled_draws}, subject {detail.pooled_subject_wins}",
                max(9, metrics.font_small - 5),
                x,
                y,
                self.game.palette.muted,
                width,
            )

    def _draw_counter_candidates_panel(self, spec, detail, selected):
        panel = self._draw_dashboard_panel(spec, accent=self.game.palette.success)
        metrics = self.game.layout
        x = panel.x + metrics.margin
        width = panel.width - metrics.margin * 2
        y = panel.y + metrics.margin
        self.game.draw_text_left(
            "FINAL-GENERATION COUNTER CANDIDATES",
            max(15, metrics.font_normal - 3),
            x,
            y,
            self.game.palette.text,
            width,
        )
        y += metrics.font_normal
        self.game.draw_text_left(
            "Tab focuses footer · Up/Down selects · wheel scrolls this list",
            max(9, metrics.font_small - 4),
            x,
            y,
            self.game.palette.muted,
            width,
        )
        y += metrics.font_small + metrics.gap
        list_view = RectSpec(
            x,
            y,
            width,
            max(1, panel.bottom - metrics.margin * 2 - metrics.font_small * 2 - y),
        )
        self.counter_candidate_viewport = list_view
        self.counter_candidate_rects = []
        self.counter_candidate_keys = tuple(item.key for item in detail.candidates)
        if not detail.candidates:
            self.game.draw_text(
                "No legal candidates recorded yet",
                metrics.font_small,
                list_view.center[0],
                list_view.center[1],
                self.game.palette.muted,
            )
            self.counter_candidate_capacity = 1
            return
        row_height = max(42, metrics.target_height)
        row_gap = max(4, metrics.gap // 2)
        capacity = max(1, (list_view.height + row_gap) // (row_height + row_gap))
        self.counter_candidate_capacity = capacity
        max_start = max(0, len(detail.candidates) - capacity)
        self.counter_candidate_scroll = min(self.counter_candidate_scroll, max_start)
        visible = detail.candidates[
            self.counter_candidate_scroll : self.counter_candidate_scroll + capacity
        ]
        previous_clip = self.game.display.get_clip()
        list_clip = pg.Rect(list_view.x, list_view.y, list_view.width, list_view.height)
        self.game.display.set_clip(list_clip.clip(previous_clip))
        for offset, candidate in enumerate(visible):
            rect = RectSpec(
                list_view.x,
                list_view.y + offset * (row_height + row_gap),
                list_view.width - (6 if len(detail.candidates) > capacity else 0),
                row_height,
            )
            self.counter_candidate_rects.append((candidate.key, rect))
            selected_row = selected is not None and candidate.key == selected.key
            pg_rect = pg.Rect(rect.x, rect.y, rect.width, rect.height)
            pg.draw.rect(
                self.game.display,
                self.game.palette.selected if selected_row else self.game.palette.panel_alt,
                pg_rect,
                border_radius=7,
            )
            pg.draw.rect(
                self.game.display,
                self.game.palette.accent if selected_row else self.game.palette.border,
                pg_rect,
                2 if selected_row else 1,
                border_radius=7,
            )
            self.game.draw_text_left(
                candidate.deck.name,
                max(10, metrics.font_small - 2),
                rect.x + metrics.gap,
                rect.center[1],
                self.game.palette.text,
                rect.width * 55 // 100,
            )
            rate = (
                f"{candidate.counter_win_rate * 100:.1f}% · {candidate.games:,} games"
                if candidate.counter_win_rate is not None
                else "Result unavailable"
            )
            self.game.draw_text_left(
                rate,
                max(9, metrics.font_small - 3),
                rect.x + rect.width * 57 // 100,
                rect.center[1],
                self.game.palette.accent if selected_row else self.game.palette.muted,
                rect.width * 41 // 100,
            )
        self.game.display.set_clip(previous_clip)
        if len(detail.candidates) > capacity:
            track = pg.Rect(list_view.right - 4, list_view.y, 4, list_view.height)
            thumb_height = max(24, round(track.height * capacity / len(detail.candidates)))
            travel = track.height - thumb_height
            top = track.y + round(travel * self.counter_candidate_scroll / max_start)
            pg.draw.rect(self.game.display, self.game.palette.disabled, track)
            pg.draw.rect(
                self.game.display,
                self.game.palette.success,
                (track.x, top, track.width, thumb_height),
                border_radius=2,
            )
        self._draw_wrapped_text(
            "Top-ranked among tested candidates is not universally superior; ranking a population adds selection bias.",
            max(9, metrics.font_small - 5),
            x,
            panel.bottom - metrics.margin - metrics.font_small * 2,
            width,
            max_lines=2,
            color=self.game.palette.muted,
        )

    def _draw_counter_dashboard(self, telemetry, detail):
        self.draw_background()
        item = self.dashboard_item
        status = str(getattr(item, "status", telemetry.status) or "pending").upper()
        progress = (
            f" · GEN {telemetry.generation}/{telemetry.total_generations}"
            if telemetry.total_generations > 0 and status == "RUNNING"
            else ""
        )
        self.draw_title(
            "Counter hunt / compositions first",
            f"Training Arena · {status}{progress}",
        )
        if isinstance(item, TrainingRunSummary):
            run_identity = f"{item.run_id} · {item.title}"
        else:
            request = getattr(item, "request", None) or {}
            run_identity = str(
                request.get("run_label")
                or getattr(item, "job_id", "Training run")
            )
        selected = self._counter_selected(detail)
        subject_rows = len(detail.subject.cards) if detail else 1
        counter_rows = len(selected.deck.cards) if selected else 1
        layout = counter_dashboard_layout(
            self.game.layout,
            subject_rows=subject_rows,
            counter_rows=counter_rows,
            scroll=self.dashboard_scroll,
        )
        self.dashboard_max_scroll = layout.max_scroll
        self.dashboard_scroll = min(self.dashboard_scroll, layout.max_scroll)
        self.game.display.set_clip(
            pg.Rect(
                layout.viewport.x,
                layout.viewport.y,
                layout.viewport.width,
                layout.viewport.height,
            )
        )
        if detail is None:
            self._draw_empty_insights(layout.viewport, "Loading counter evidence…")
        else:
            absent = (
                max(0, detail.subject.total_cards - selected.shared_cards)
                if selected is not None
                else detail.subject.total_cards
            )
            comparison = (
                (
                    f"Shares {selected.shared_cards} card copies",
                    f"{absent} selected-deck copies absent",
                )
                if selected is not None
                else ("No evaluated counter is available for comparison",)
            )
            self._draw_counter_deck_panel(
                layout.subject,
                title="YOUR SELECTED DECK",
                deck=detail.subject,
                accent=(105, 172, 225),
                provenance="saved training snapshot",
                comparison=comparison,
            )
            self._draw_counter_result_panel(
                layout.result, detail, selected, telemetry, run_identity
            )
            self._draw_counter_candidates_panel(
                layout.candidates, detail, selected
            )
            counter_deck = (
                selected.deck
                if selected is not None
                else CounterDeckSnapshot("", "No counter selected", ())
            )
            self._draw_counter_deck_panel(
                layout.counter,
                title="SELECTED COUNTER",
                deck=counter_deck,
                accent=self.game.palette.accent,
                provenance="generated snapshot",
            )
        self.game.display.set_clip(None)
        self._draw_dashboard_scrollbar(layout.viewport)
        self._draw_mission_footer(
            layout.footer,
            focused=self.counter_focus == "footer",
            allow_adopt=selected is not None,
        )

    def _draw_matchup_deck(self, panel, deck, side, y, color):
        metrics = self.game.layout
        x = panel.x + metrics.margin
        width = panel.width - metrics.margin * 2
        self.game.draw_text_left(
            f"DECK {side}", metrics.font_small, x, y, color, width
        )
        y += metrics.font_normal
        self.game.draw_text_left(
            deck.name or deck.deck_id or f"Deck {side}",
            metrics.font_normal,
            x,
            y,
            self.game.palette.text,
            width,
        )
        y += metrics.font_normal
        self.game.draw_text_left(
            f"ID {deck.deck_id or 'unavailable'}",
            max(10, metrics.font_small - 3),
            x,
            y,
            self.game.palette.muted,
            width,
        )
        y += metrics.font_small + metrics.gap
        if not deck.composition_available:
            self.game.draw_text_left(
                "Composition unavailable",
                metrics.font_small,
                x,
                y,
                self.game.palette.danger,
                width,
            )
            return y + metrics.font_small + metrics.gap * 2
        if not deck.cards:
            self.game.draw_text_left(
                "No cards in the current saved deck",
                metrics.font_small,
                x,
                y,
                self.game.palette.muted,
                width,
            )
            return y + metrics.font_small + metrics.gap * 2
        color_map = {
            "Red": self.game.palette.danger,
            "Blue": (105, 172, 225),
            "Black": (190, 176, 215),
            "Green": self.game.palette.success,
        }
        line_height = max(18, metrics.font_small + 3)
        for card in deck.cards:
            self.game.draw_text_left(
                f"{card.copies}×  {card.name}",
                metrics.font_small,
                x,
                y,
                self.game.palette.text,
                max(1, width * 68 // 100),
            )
            self.game.draw_text_left(
                card.color,
                max(10, metrics.font_small - 3),
                x + width * 70 // 100,
                y,
                color_map.get(card.color, self.game.palette.muted),
                max(1, width * 30 // 100),
            )
            y += line_height
        return y + metrics.gap

    def _draw_matchup_decks_panel(self, spec, detail, run_identity):
        panel = self._draw_dashboard_panel(spec, accent=self._matchup_side_colors()[0])
        metrics = self.game.layout
        x = panel.x + metrics.margin
        width = panel.width - metrics.margin * 2
        y = panel.y + metrics.margin
        self.game.draw_text_left(
            "THE TWO FIXED DECKS",
            max(15, metrics.font_normal - 3),
            x,
            y,
            self.game.palette.text,
            width,
        )
        y += metrics.font_normal
        self.game.draw_text_left(
            run_identity,
            max(10, metrics.font_small - 3),
            x,
            y,
            self.game.palette.muted,
            width,
        )
        y += metrics.font_small + metrics.gap * 2
        color_a, color_b, _ = self._matchup_side_colors()
        y = self._draw_matchup_deck(panel, detail.deck_a, "A", y, color_a)
        pg.draw.line(
            self.game.display,
            self.game.palette.border,
            (x, y),
            (panel.right - metrics.margin, y),
        )
        y += metrics.gap * 2
        y = self._draw_matchup_deck(panel, detail.deck_b, "B", y, color_b)
        self._draw_wrapped_text(
            "Compositions are current database records, not training-time snapshots.",
            max(9, metrics.font_small - 4),
            x,
            y + metrics.gap,
            width,
            max_lines=2,
            color=self.game.palette.muted,
        )

    def _draw_matchup_checkpoint_row(self, panel, row, y, final=False):
        metrics = self.game.layout
        color_a, color_b, draw_color = self._matchup_side_colors()
        x = panel.x + metrics.margin
        width = panel.width - metrics.margin * 2
        height = max(68, metrics.target_height + metrics.gap * 2)
        rect = pg.Rect(x, y, width, height)
        pg.draw.rect(self.game.display, self.game.palette.panel_alt, rect, border_radius=9)
        pg.draw.rect(
            self.game.display,
            self.game.palette.accent if final else self.game.palette.border,
            rect,
            2 if final else 1,
            border_radius=9,
        )
        self.game.draw_text_left(
            f"Gen {row.generation} · {row.games} games",
            metrics.font_small,
            rect.x + metrics.gap,
            rect.y + metrics.font_small,
            self.game.palette.text,
            rect.width - metrics.gap * 2,
        )
        if not row.valid:
            self.game.draw_text_left(
                row.issue,
                max(10, metrics.font_small - 2),
                rect.x + metrics.gap,
                rect.centery + metrics.gap,
                self.game.palette.danger,
                rect.width - metrics.gap * 2,
            )
            return rect.bottom + metrics.gap
        rates = row.rates
        labels = (
            (f"A {row.deck_a_wins} · {rates[0] * 100:.1f}%", color_a),
            (f"Draw {row.draws} · {rates[1] * 100:.1f}%", draw_color),
            (f"B {row.deck_b_wins} · {rates[2] * 100:.1f}%", color_b),
        )
        label_y = rect.y + metrics.font_small * 2 + metrics.gap
        for index, (label, color) in enumerate(labels):
            self.game.draw_text_left(
                label,
                max(10, metrics.font_small - 2),
                rect.x + metrics.gap + index * (rect.width - metrics.gap * 2) // 3,
                label_y,
                color,
                (rect.width - metrics.gap * 2) // 3,
            )
        bar = pg.Rect(
            rect.x + metrics.gap,
            rect.bottom - metrics.gap - max(10, metrics.target_height // 4),
            rect.width - metrics.gap * 2,
            max(10, metrics.target_height // 4),
        )
        cursor = bar.x
        for index, (ratio, color) in enumerate(zip(rates, (color_a, draw_color, color_b))):
            segment_width = bar.right - cursor if index == 2 else round(bar.width * ratio)
            if segment_width:
                pg.draw.rect(
                    self.game.display,
                    color,
                    (cursor, bar.y, segment_width, bar.height),
                )
            cursor += segment_width
        pg.draw.rect(self.game.display, self.game.palette.border, bar, 1, border_radius=5)
        return rect.bottom + metrics.gap

    def _draw_matchup_checkpoints_panel(self, spec, detail):
        panel = self._draw_dashboard_panel(spec, accent=self.game.palette.accent)
        metrics = self.game.layout
        x = panel.x + metrics.margin
        width = panel.width - metrics.margin * 2
        y = panel.y + metrics.margin
        self.game.draw_text_left(
            "SEAT-BALANCED CHECKPOINT OUTCOMES",
            max(15, metrics.font_normal - 3),
            x,
            y,
            self.game.palette.text,
            width,
        )
        y += metrics.font_normal
        self.game.draw_text_left(
            "Every percentage uses all games in that checkpoint.",
            max(10, metrics.font_small - 2),
            x,
            y,
            self.game.palette.muted,
            width,
        )
        y += metrics.font_small + metrics.gap * 2
        if not detail.summary_available:
            self.game.draw_text_left(
                "Evaluation pending · no checkpoint summary yet",
                metrics.font_small,
                x,
                y,
                self.game.palette.accent,
                width,
            )
            return
        if not detail.checkpoints:
            self.game.draw_text_left(
                "No readable checkpoint evidence",
                metrics.font_small,
                x,
                y,
                self.game.palette.danger,
                width,
            )
            return
        for row in detail.checkpoints:
            y = self._draw_matchup_checkpoint_row(
                panel,
                row,
                y,
                final=(row is detail.final_checkpoint),
            )
        if detail.next_checkpoint_generation is not None:
            self.game.draw_text_left(
                f"Next planned checkpoint: generation {detail.next_checkpoint_generation} · pending",
                max(10, metrics.font_small - 2),
                x,
                y + metrics.gap,
                self.game.palette.accent,
                width,
            )

    def _draw_matchup_reading_panel(self, spec, detail, telemetry):
        panel = self._draw_dashboard_panel(spec, accent=self.game.palette.success)
        metrics = self.game.layout
        x = panel.x + metrics.margin
        width = panel.width - metrics.margin * 2
        y = panel.y + metrics.margin
        color_a, color_b, draw_color = self._matchup_side_colors()
        self.game.draw_text_left(
            "FINAL READING", metrics.font_normal, x, y, self.game.palette.text, width
        )
        y += metrics.font_normal + metrics.gap
        final = detail.final_checkpoint
        if final is None:
            self.game.draw_text_left(
                "Final checkpoint pending",
                metrics.font_normal,
                x,
                y,
                self.game.palette.accent,
                width,
            )
            y += metrics.font_normal
            self._draw_wrapped_text(
                "Only a valid checkpoint at the requested final generation is treated as final.",
                max(10, metrics.font_small - 2),
                x,
                y,
                width,
                max_lines=3,
                color=self.game.palette.muted,
            )
            y += metrics.font_small * 3 + metrics.gap
        else:
            rates = final.rates
            self.game.draw_text_left(
                f"Generation {final.generation} · {final.games} games",
                max(10, metrics.font_small - 2),
                x,
                y,
                self.game.palette.muted,
                width,
            )
            y += metrics.font_normal
            for label, color in (
                (f"Deck A · {rates[0] * 100:.1f}% ({final.deck_a_wins}/{final.games})", color_a),
                (f"Deck B · {rates[2] * 100:.1f}% ({final.deck_b_wins}/{final.games})", color_b),
                (f"Draws · {rates[1] * 100:.1f}% ({final.draws}/{final.games})", draw_color),
            ):
                self.game.draw_text_left(label, metrics.font_small, x, y, color, width)
                y += metrics.font_normal
            if final.games < COMPARISON_TARGET:
                self._draw_wrapped_text(
                    "Exploratory sample · below 1,000-game comparison target",
                    max(9, metrics.font_small - 4),
                    x,
                    y,
                    width,
                    max_lines=2,
                    color=self.game.palette.danger,
                )
                y += metrics.font_small * 2
            baseline = next(
                (row for row in detail.checkpoints if row.generation == 1 and row.valid),
                None,
            )
            if baseline is not None and baseline is not final:
                change = (rates[0] - baseline.rates[0]) * 100
                self.game.draw_text_left(
                    f"Deck A: {change:+.1f} points from gen 1",
                    max(10, metrics.font_small - 2),
                    x,
                    y,
                    color_a,
                    width,
                )
                y += metrics.font_normal

        pg.draw.line(
            self.game.display,
            self.game.palette.border,
            (x, y),
            (panel.right - metrics.margin, y),
        )
        y += metrics.gap * 2
        workload = detail.workload
        self.game.draw_text_left(
            "RUN DEPTH", metrics.font_normal, x, y, self.game.palette.text, width
        )
        y += metrics.font_normal + metrics.gap
        planned_checks = len(workload.planned_checkpoint_generations)
        facts = (
            ("Controller populations", "2 evolving"),
            ("Genomes / pop / gen", str(workload.population_size or "Unavailable")),
            ("Learning games / genome / gen", str(workload.games_per_genome_per_generation or "Unavailable")),
            ("Distinct learning games / gen", f"~{workload.learning_games_per_generation:,}"),
            ("Learning gens complete", f"{workload.completed_generations} / {workload.requested_generations}"),
            ("Checkpoint plan (games)", f"{planned_checks} × {workload.games_per_checkpoint}"),
            ("Checkpoint evidence", f"{workload.recorded_checkpoints} · {workload.recorded_evaluation_games:,} games"),
            ("Learning workload", f"~{workload.planned_learning_games:,} planned"),
            ("Evaluation workload", f"{workload.planned_evaluation_games:,} planned"),
            ("Overall workload", f"~{workload.planned_total_games:,} planned"),
            ("Completed estimate", f"~{workload.completed_total_estimate:,} games"),
        )
        label_size = max(9, metrics.font_small - 7)
        value_size = max(10, metrics.font_small - 5)
        row_height = max(22, metrics.font_small + 3)
        for label, value in facts:
            self.game.draw_text_left(
                label,
                label_size,
                x,
                y,
                self.game.palette.muted,
                max(1, width * 56 // 100),
            )
            self.game.draw_text_left(
                value,
                value_size,
                x + width * 58 // 100,
                y,
                self.game.palette.text,
                max(1, width * 42 // 100),
            )
            y += row_height
        self._draw_wrapped_text(
            "Learning totals are configuration-derived estimates. Checkpoint trials are fresh, seat-balanced games and are not learning games.",
            label_size,
            x,
            y,
            width,
            max_lines=4,
            color=self.game.palette.accent,
        )

    def _draw_dashboard_scrollbar(self, viewport):
        if self.dashboard_max_scroll <= 0:
            return
        track = pg.Rect(viewport.right - 4, viewport.y, 4, viewport.height)
        total = viewport.height + self.dashboard_max_scroll
        thumb_height = max(28, round(viewport.height * viewport.height / total))
        travel = viewport.height - thumb_height
        top = viewport.y + round(
            travel * self.dashboard_scroll / self.dashboard_max_scroll
        )
        pg.draw.rect(self.game.display, self.game.palette.disabled, track, border_radius=2)
        pg.draw.rect(
            self.game.display,
            self.game.palette.accent,
            (track.x, top, track.width, thumb_height),
            border_radius=2,
        )

    def _draw_progress_footer(self, footer, destination):
        labels = [("back", "Back to runs"), ("log", "View log")]
        if destination == ArenaDestination.PROGRESS and self._can_stop_dashboard_job():
            labels.append(("stop", "Stop training"))
        if destination == ArenaDestination.COMPLETION_HANDOFF:
            artifact = self.dashboard_artifact_status
            labels.append(
                (
                    "open_results",
                    f"Open {mission_result_label(self._dashboard_kind())}",
                )
            )
        gap = self.game.layout.gap
        width = min(
            330,
            (footer.width - gap * (len(labels) - 1)) // max(1, len(labels)),
        )
        self.dashboard_buttons = []
        for index, (key, label) in enumerate(labels):
            enabled = not (
                key == "open_results"
                and not (
                    self.dashboard_artifact_status is not None
                    and self.dashboard_artifact_status.ready
                    and self.dashboard_insights is not None
                )
            )
            rect = RectSpec(
                footer.x + index * (width + gap),
                footer.y,
                width,
                footer.height,
            )
            self.dashboard_buttons.append(
                Button(
                    key,
                    label,
                    rect,
                    enabled=enabled,
                    selected=index == self.dashboard_action,
                    hovered=rect.contains(self.game.mouse_position),
                    destructive=key == "stop",
                )
            )
        if self.dashboard_buttons:
            self.dashboard_action %= len(self.dashboard_buttons)
            for index, button in enumerate(self.dashboard_buttons):
                button.selected = index == self.dashboard_action
        self.draw_buttons(self.dashboard_buttons)

    def _draw_training_progress(self, telemetry, destination):
        self.draw_background()
        item = self.dashboard_item
        kind = self._dashboard_kind()
        status = str(getattr(item, "status", telemetry.status) or "pending").lower()
        identity = (
            f"{item.run_id} · {item.title}"
            if isinstance(item, TrainingRunSummary)
            else getattr(item, "job_id", "Training run")
        )
        if destination == ArenaDestination.PROGRESS:
            title = "Training in progress" if status != "stopping" else "Stopping training"
            subtitle = f"{mission_progress_name(kind)} · {identity}"
        elif destination == ArenaDestination.COMPLETION_HANDOFF:
            title = "Training complete"
            subtitle = f"{mission_progress_name(kind)} · {identity}"
        else:
            title = "Training did not complete"
            subtitle = f"{mission_progress_name(kind)} · {identity} · {status.upper()}"
        self.draw_title(title, subtitle)
        layout = training_progress_layout(
            self.game.layout,
            scroll=self.dashboard_scroll,
        )
        self.dashboard_max_scroll = layout.max_scroll
        self.dashboard_scroll = min(self.dashboard_scroll, layout.max_scroll)
        viewport_rect = pg.Rect(
            layout.viewport.x,
            layout.viewport.y,
            layout.viewport.width,
            layout.viewport.height,
        )
        self.game.display.set_clip(viewport_rect)
        metrics = self.game.layout
        progress = overall_progress(telemetry)
        status_color = (
            self.game.palette.success
            if destination == ArenaDestination.COMPLETION_HANDOFF
            and self.dashboard_artifact_status is not None
            and self.dashboard_artifact_status.ready
            else self.game.palette.danger
            if destination == ArenaDestination.COMPLETION_HANDOFF
            and self.dashboard_artifact_status is not None
            and self.dashboard_artifact_status.state == "invalid"
            else self.game.palette.danger
            if destination == ArenaDestination.TERMINAL
            else self.game.palette.accent
        )

        hero = self._draw_dashboard_panel(layout.hero, accent=status_color)
        radius = max(38, min(70, hero.height // 3))
        center = (hero.x + metrics.margin + radius, hero.centery)
        ring = pg.Rect(center[0] - radius, center[1] - radius, radius * 2, radius * 2)
        pg.draw.arc(self.game.display, self.game.palette.disabled, ring, 0, math.tau, 10)
        if progress is None:
            angle = (pg.time.get_ticks() % 1800) / 1800 * math.tau
            pg.draw.arc(
                self.game.display,
                status_color,
                ring,
                angle,
                angle + math.pi * 0.65,
                10,
            )
            ring_text = "…"
        else:
            pg.draw.arc(
                self.game.display,
                status_color,
                ring,
                -math.pi / 2,
                -math.pi / 2 + math.tau * progress,
                10,
            )
            ring_text = f"{round(progress * 100)}%"
        self.game.draw_text(
            ring_text, metrics.font_large, center[0], center[1], status_color
        )
        hero_x = center[0] + radius + metrics.margin
        hero_width = max(1, hero.right - metrics.margin - hero_x)
        if destination == ArenaDestination.PROGRESS:
            eyebrow = (
                f"Generation {telemetry.generation} / {telemetry.total_generations}"
                if telemetry.total_generations
                else "Waiting for measured work counters"
            )
            heading = f"Current phase: {self._phase_label(telemetry.phase)}"
            note = "Mission results and deck adoption remain locked until authoritative completion."
        elif destination == ArenaDestination.COMPLETION_HANDOFF:
            artifact = self.dashboard_artifact_status
            eyebrow = "Authoritative job status: completed"
            heading = (
                "The run finished and its result artifact is ready"
                if artifact is not None and artifact.ready
                else "Results are unavailable"
                if artifact is not None and artifact.state == "invalid"
                else "Preparing results…"
            )
            note = (
                artifact.message
                if artifact is not None
                else "Verifying the mission result artifact in the background"
            )
        else:
            eyebrow = f"Stopped at generation {telemetry.generation} of {telemetry.total_generations or '?'}"
            heading = "No completed result is available"
            note = "Partial logs and artifacts remain available for diagnosis; finished-result analysis stays locked."
        self.game.draw_text_left(
            eyebrow,
            metrics.font_small,
            hero_x,
            hero.y + metrics.margin,
            self.game.palette.muted,
            hero_width,
        )
        self.game.draw_text_left(
            heading,
            metrics.font_normal,
            hero_x,
            hero.y + metrics.margin + metrics.font_normal + metrics.gap,
            self.game.palette.text,
            hero_width,
        )
        self._draw_wrapped_text(
            note,
            metrics.font_small,
            hero_x,
            hero.y + metrics.margin + metrics.font_normal * 3,
            hero_width,
            max_lines=3,
            color=self.game.palette.muted,
        )

        levels_panel = self._draw_dashboard_panel(layout.levels, accent=(105, 172, 225))
        x = levels_panel.x + metrics.margin
        width = levels_panel.width - metrics.margin * 2
        y = levels_panel.y + metrics.margin
        self.game.draw_text_left("REPORTED PROGRESS", metrics.font_normal, x, y, self.game.palette.text, width)
        y += metrics.font_normal + metrics.gap
        levels = progress_levels(kind, telemetry)
        if not levels:
            self._draw_wrapped_text(
                "The trainer has not emitted a trustworthy completed/total counter yet.",
                metrics.font_small,
                x,
                y,
                width,
                max_lines=3,
                color=self.game.palette.muted,
            )
        for label, value, ratio in levels:
            self.game.draw_text_left(label, metrics.font_small, x, y, self.game.palette.text, width)
            y += metrics.font_small
            self.game.draw_text_left(value, max(9, metrics.font_small - 3), x, y, self.game.palette.muted, width)
            y += metrics.font_small
            bar = pg.Rect(x, y, width, max(9, metrics.gap))
            if ratio is None:
                pg.draw.rect(self.game.display, self.game.palette.disabled, bar, border_radius=5)
                marker = max(12, bar.width // 5)
                offset = (pg.time.get_ticks() // 12) % max(1, bar.width + marker) - marker
                pg.draw.rect(
                    self.game.display,
                    self.game.palette.hover,
                    (bar.x + offset, bar.y, marker, bar.height),
                    border_radius=5,
                )
            else:
                self._draw_dashboard_bar(bar, ratio, status_color)
            y += bar.height + metrics.gap * 2

        phase_panel = self._draw_dashboard_panel(layout.phase, accent=self.game.palette.accent)
        x = phase_panel.x + metrics.margin
        width = phase_panel.width - metrics.margin * 2
        y = phase_panel.y + metrics.margin
        self.game.draw_text_left("CURRENT PHASE", metrics.font_normal, x, y, self.game.palette.text, width)
        y += metrics.font_normal + metrics.gap
        self.game.draw_text_left(
            self._phase_label(telemetry.phase),
            metrics.font_normal,
            x,
            y,
            status_color,
            width,
        )
        y += metrics.font_normal + metrics.gap
        phase_explanation = {
            TrainingKind.PLAYER_DECK.value: "Counter generation, persistent controller learning, and candidate validation appear only when each level is reported.",
            TrainingKind.MATCHUP_EVALUATION.value: "Controller learning and checkpoint evaluation are distinct phases; no checkpoint outcome appears here.",
            TrainingKind.DECK_BUILDER.value: "Outer deck pairings are reported. Exact progress inside nested controller learning is not streamed.",
        }.get(kind, "Only trainer-reported work is shown.")
        self._draw_wrapped_text(
            phase_explanation,
            metrics.font_small,
            x,
            y,
            width,
            max_lines=6,
            color=self.game.palette.muted,
        )

        timing_panel = self._draw_dashboard_panel(layout.timing, accent=(105, 172, 225))
        x = timing_panel.x + metrics.margin
        width = timing_panel.width - metrics.margin * 2
        y = timing_panel.y + metrics.margin
        self.game.draw_text_left("TIME AND COMPUTE", metrics.font_normal, x, y, self.game.palette.text, width)
        y += metrics.font_normal + metrics.gap * 2
        facts = (
            ("Elapsed", self._duration_label(telemetry.elapsed_seconds)),
            (
                "Estimated remaining",
                eta_label(telemetry, self._duration_label)
                if destination == ArenaDestination.PROGRESS
                else "—",
            ),
            ("Workers", str(telemetry.workers or "Not reported")),
        )
        for label, value in facts:
            self.game.draw_text_left(label, metrics.font_small, x, y, self.game.palette.muted, width // 2)
            self.game.draw_text_left(value, metrics.font_small, x + width // 2, y, self.game.palette.text, width // 2)
            y += metrics.font_normal * 2
        self._draw_wrapped_text(
            "ETA is shown only from fresh trainer evidence; otherwise it remains Estimating…",
            max(9, metrics.font_small - 2),
            x,
            y,
            width,
            max_lines=4,
            color=self.game.palette.muted,
        )

        events_panel = self._draw_dashboard_panel(layout.events, accent=self.game.palette.success)
        x = events_panel.x + metrics.margin
        width = events_panel.width - metrics.margin * 2
        y = events_panel.y + metrics.margin
        self.game.draw_text_left("LATEST RUN EVENTS", metrics.font_normal, x, y, self.game.palette.text, width)
        y += metrics.font_normal + metrics.gap
        events = telemetry.recent_events
        if not events:
            self.game.draw_text_left(
                "Waiting for timestamped trainer events…",
                metrics.font_small,
                x,
                y,
                self.game.palette.muted,
                width,
            )
        for timestamp, event in events[-5:]:
            self.game.draw_text_left(
                f"{timestamp or '—'}  {event}",
                max(10, metrics.font_small - 2),
                x,
                y,
                self.game.palette.text,
                width,
            )
            y += metrics.font_normal

        self.game.display.set_clip(None)
        self._draw_dashboard_scrollbar(layout.viewport)
        self._draw_progress_footer(layout.footer, destination)

    def _draw_matchup_dashboard(self, telemetry, detail):
        self.draw_background()
        item = self.dashboard_item
        run_identity = getattr(item, "job_id", "Training run")
        status = str(getattr(item, "status", telemetry.status) or "pending").upper()
        progress = (
            f" · GEN {telemetry.generation}/{telemetry.total_generations}"
            if telemetry.total_generations > 0 and status == "RUNNING"
            else ""
        )
        self.draw_title(
            "Deck duel / checkpoint study",
            f"Training Arena · {status}{progress}",
        )
        deck_rows = (
            len(detail.deck_a.cards) + len(detail.deck_b.cards) if detail else 2
        )
        checkpoint_rows = len(detail.checkpoints) if detail else 1
        layout = matchup_dashboard_layout(
            self.game.layout,
            deck_rows=deck_rows,
            checkpoint_rows=checkpoint_rows,
            scroll=self.dashboard_scroll,
        )
        self.dashboard_max_scroll = layout.max_scroll
        self.dashboard_scroll = min(self.dashboard_scroll, self.dashboard_max_scroll)
        self.game.display.set_clip(
            pg.Rect(
                layout.viewport.x,
                layout.viewport.y,
                layout.viewport.width,
                layout.viewport.height,
            )
        )
        if detail is None:
            self._draw_empty_insights(layout.viewport, "Loading matchup evidence…")
        else:
            self._draw_matchup_decks_panel(layout.decks, detail, run_identity)
            self._draw_matchup_checkpoints_panel(layout.checkpoints, detail)
            self._draw_matchup_reading_panel(layout.reading, detail, telemetry)
        self.game.display.set_clip(None)
        self._draw_dashboard_scrollbar(layout.viewport)
        self._draw_mission_footer(layout.footer)

    def _draw_evolution_navigation(self, layout, detail):
        pages = self._dashboard_pages()
        self.dashboard_buttons = []
        if layout.mode == "wide":
            panel = self._draw_dashboard_panel(layout.navigation, accent=self.game.palette.border)
            self.game.draw_text_left(
                "DECK EVOLUTION",
                self.game.layout.font_small,
                panel.x + self.game.layout.gap,
                panel.y + self.game.layout.margin,
                self.game.palette.accent,
                panel.width - self.game.layout.gap * 2,
            )
            y = panel.y + self.game.layout.margin + self.game.layout.font_normal * 2
            for index, label in enumerate(pages):
                rect = RectSpec(
                    panel.x + self.game.layout.gap,
                    y,
                    panel.width - self.game.layout.gap * 2,
                    self.game.layout.target_height,
                )
                self.dashboard_buttons.append(
                    Button(
                        f"page:{index}",
                        f"0{index + 1}  {label}",
                        rect,
                        selected=index == self.dashboard_page,
                        hovered=rect.contains(self.game.mouse_position),
                    )
                )
                y += self.game.layout.target_height + self.game.layout.gap
            y = max(y + self.game.layout.gap, panel.bottom - self.game.layout.target_height * 4)
            self.game.draw_text_left(
                f"RUN DB {detail.training_id}",
                max(9, self.game.layout.font_small - 2),
                panel.x + self.game.layout.gap,
                y,
                (105, 172, 225),
                panel.width - self.game.layout.gap * 2,
            )
            self.game.draw_text_left(
                detail.run_label,
                max(9, self.game.layout.font_small - 2),
                panel.x + self.game.layout.gap,
                y + self.game.layout.font_normal,
                self.game.palette.text,
                panel.width - self.game.layout.gap * 2,
            )
        else:
            panel = self._draw_dashboard_panel(layout.navigation, accent=self.game.palette.border)
            gap = max(3, self.game.layout.gap // 2)
            width = (panel.width - gap * 6) // 5
            compact_labels = ("Pulse", "Decks", "Match", "Cards", "Study")
            for index, label in enumerate(compact_labels):
                rect = RectSpec(
                    panel.x + gap + index * (width + gap),
                    panel.y + self.game.layout.gap,
                    width,
                    panel.height - self.game.layout.gap * 2,
                )
                self.dashboard_buttons.append(
                    Button(
                        f"page:{index}",
                        f"{index + 1} {label}",
                        rect,
                        selected=index == self.dashboard_page,
                        hovered=rect.contains(self.game.mouse_position),
                    )
                )
        self.draw_buttons(self.dashboard_buttons)

    def _draw_evolution_footer(self, footer, detail, selected):
        labels = [("back", "Back to runs"), ("previous", "Previous"), ("next", "Next")]
        if self.dashboard_page == 1:
            filter_name = (
                "All generations"
                if self.evolution_generation_filter is None
                else f"Generation {self.evolution_generation_filter}"
            )
            if self.game.DISPLAY_W < 900:
                labels.extend((("filter", "Filter"), ("adopt", "Adopt")))
            else:
                labels.extend(
                    (("filter", f"Filter: {filter_name}"), ("adopt", "Adopt selected deck"))
                )
        gap = self.game.layout.gap
        width = (footer.width - gap * (len(labels) - 1)) // len(labels)
        footer_buttons = []
        first_footer_index = len(self.dashboard_buttons)
        for index, (key, label) in enumerate(labels):
            rect = RectSpec(
                footer.x + index * (width + gap), footer.y, width, footer.height
            )
            footer_buttons.append(
                Button(
                    key,
                    label,
                    rect,
                    enabled=key != "adopt" or bool(selected and selected.card_ids),
                    selected=(
                        self.evolution_focus == "actions"
                        and first_footer_index + index == self.dashboard_action
                    ),
                    hovered=rect.contains(self.game.mouse_position),
                )
            )
        self.dashboard_buttons.extend(footer_buttons)
        self.draw_buttons(footer_buttons)

    def _draw_evolution_run_pulse(self, content, detail):
        metrics = self.game.layout
        x, width = content.x, content.width
        y = content.y
        first, final = detail.first_generation, detail.final_generation
        hero = self._draw_dashboard_panel(
            RectSpec(x, y, width, 165), accent=self.game.palette.success
        )
        self.game.draw_text_left("COMPLETED RUN EVIDENCE", metrics.font_normal, hero.x + metrics.margin, hero.y + metrics.margin, self.game.palette.text, hero.width - metrics.margin * 2)
        generation_text = (
            f"{final.generation} / {detail.requested_outer_generations or final.generation} outer generations"
            if final else "No generation rows"
        )
        self.game.draw_text_left(generation_text, metrics.font_large, hero.x + metrics.margin, hero.y + metrics.margin + metrics.font_normal * 2, self.game.palette.success, hero.width - metrics.margin * 2)
        self.game.draw_text_left(
            f"{detail.coverage.scored_pairings:,} observed outer pairings · these are not individual games",
            metrics.font_small,
            hero.x + metrics.margin,
            hero.bottom - metrics.margin,
            self.game.palette.muted,
            hero.width - metrics.margin * 2,
        )
        y = hero.bottom + metrics.gap
        left, right = metrics.columns(RectSpec(x, y, width, 300), (0.53, 0.47))
        generation_panel = self._draw_dashboard_panel(left, accent=(105, 172, 225))
        self.game.draw_text_left("GENERATION WORK", metrics.font_normal, generation_panel.x + metrics.margin, generation_panel.y + metrics.margin, self.game.palette.text, generation_panel.width - metrics.margin * 2)
        chart = pg.Rect(generation_panel.x + metrics.margin, generation_panel.y + metrics.margin + metrics.font_normal * 2, generation_panel.width - metrics.margin * 2, generation_panel.height - metrics.margin * 3 - metrics.font_normal * 2)
        max_count = max((row.contenders for row in detail.generations), default=1)
        if detail.generations:
            slot = max(3, chart.width // len(detail.generations))
            for index, row in enumerate(detail.generations):
                height = round(chart.height * row.contenders / max_count)
                bar = pg.Rect(chart.x + index * slot + 2, chart.bottom - height, max(2, slot - 4), height)
                pg.draw.rect(self.game.display, (105, 172, 225), bar, border_radius=3)
        evidence = self._draw_dashboard_panel(right, accent=self.game.palette.accent)
        self.game.draw_text_left("EVIDENCE READINESS", metrics.font_normal, evidence.x + metrics.margin, evidence.y + metrics.margin, self.game.palette.text, evidence.width - metrics.margin * 2)
        facts = (
            ("Genome rows", f"{detail.coverage.genome_rows:,} recorded"),
            ("Outer matchup rows", f"{detail.coverage.scored_pairings:,} scored"),
            ("Card compositions", f"{detail.coverage.stored_compositions:,} stored deck lists"),
            ("Fixed benchmark", "Not recorded"),
            ("Live inner-loop detail", "Not streamed per pairing"),
        )
        fy = evidence.y + metrics.margin + metrics.font_normal * 2
        for label, value in facts:
            self.game.draw_text_left(label, max(9, metrics.font_small - 2), evidence.x + metrics.margin, fy, self.game.palette.muted, evidence.width // 2)
            self.game.draw_text_left(value, max(9, metrics.font_small - 2), evidence.x + evidence.width // 2, fy, self.game.palette.text, evidence.width // 2 - metrics.margin)
            fy += metrics.font_normal * 2
        y += 300 + metrics.gap
        guard = self._draw_dashboard_panel(RectSpec(x, y, width, 155), accent=self.game.palette.danger)
        self.game.draw_text_left("READ THIS CORRECTLY", metrics.font_normal, guard.x + metrics.margin, guard.y + metrics.margin, self.game.palette.text, guard.width - metrics.margin * 2)
        self._draw_wrapped_text(
            "Completion measures executed work and evidence coverage. It does not prove that decks improved. Relative fitness compares contemporaries whose opponents changed each generation.",
            metrics.font_small,
            guard.x + metrics.margin,
            guard.y + metrics.margin + metrics.font_normal * 2,
            guard.width - metrics.margin * 2,
            max_lines=4,
            color=self.game.palette.muted,
        )
        if detail.issues:
            y = guard.bottom + metrics.gap
            issue_height = max(
                100,
                metrics.font_normal * 2
                + min(3, len(detail.issues)) * metrics.font_normal * 2,
            )
            issue_panel = self._draw_dashboard_panel(
                RectSpec(x, y, width, issue_height),
                accent=self.game.palette.danger,
            )
            self.game.draw_text_left(
                "HISTORICAL DATA LIMITATIONS",
                metrics.font_small,
                issue_panel.x + metrics.margin,
                issue_panel.y + metrics.margin,
                self.game.palette.danger,
                issue_panel.width - metrics.margin * 2,
            )
            issue_y = issue_panel.y + metrics.margin + metrics.font_normal * 2
            for issue in detail.issues[:3]:
                self._draw_wrapped_text(
                    f"• {issue}",
                    max(9, metrics.font_small - 2),
                    issue_panel.x + metrics.margin,
                    issue_y,
                    issue_panel.width - metrics.margin * 2,
                    max_lines=2,
                    color=self.game.palette.text,
                )
                issue_y += metrics.font_normal * 2

    def _draw_evolution_fitness_chart(self, panel, detail):
        metrics = self.game.layout
        self.game.draw_text_left("RELATIVE FITNESS ENVELOPE", metrics.font_normal, panel.x + metrics.margin, panel.y + metrics.margin, self.game.palette.text, panel.width - metrics.margin * 2)
        self.game.draw_text_left("Generation-local score range · not absolute deck quality", max(9, metrics.font_small - 2), panel.x + metrics.margin, panel.y + metrics.margin + metrics.font_normal, self.game.palette.muted, panel.width - metrics.margin * 2)
        chart = pg.Rect(panel.x + metrics.margin, panel.y + metrics.margin + metrics.font_normal * 3, panel.width - metrics.margin * 2, panel.height - metrics.margin * 2 - metrics.font_normal * 3)
        rows = detail.generations
        if len(rows) < 2:
            self.game.draw_text("Insufficient generation history", metrics.font_small, chart.centerx, chart.centery, self.game.palette.muted)
            return
        low = min(row.worst for row in rows)
        high = max(row.best for row in rows)
        span = max(1.0, high - low)
        def points(attribute):
            return [
                (
                    chart.x + round(index * chart.width / (len(rows) - 1)),
                    chart.bottom - round((getattr(row, attribute) - low) / span * chart.height),
                )
                for index, row in enumerate(rows)
            ]
        pg.draw.lines(self.game.display, self.game.palette.success, False, points("best"), 3)
        pg.draw.lines(self.game.display, self.game.palette.danger, False, points("worst"), 3)
        zero_y = chart.bottom - round((0 - low) / span * chart.height)
        if chart.y <= zero_y <= chart.bottom:
            pg.draw.line(self.game.display, self.game.palette.accent, (chart.x, zero_y), (chart.right, zero_y), 1)

    def _draw_evolution_deck_browser(self, panel, detail, selected):
        metrics = self.game.layout
        decks = sorted(
            (
                deck for deck in detail.decks
                if self.evolution_generation_filter is None
                or deck.generation == self.evolution_generation_filter
            ),
            key=lambda deck: (
                deck.generation,
                deck.relative_fitness if deck.relative_fitness is not None else float("-inf"),
                deck.deck_id,
            ),
            reverse=True,
        )
        self.evolution_deck_keys = tuple(deck.deck_id for deck in decks)
        if selected is not None and selected.deck_id not in self.evolution_deck_keys and decks:
            selected = decks[0]
            self.evolution_selected_deck_id = selected.deck_id
        x = panel.x + metrics.margin
        width = panel.width - metrics.margin * 2
        y = panel.y + metrics.margin
        self.game.draw_text_left("GENERATED DECKS", metrics.font_normal, x, y, self.game.palette.text, width)
        y += metrics.font_normal
        filter_name = "all generations" if self.evolution_generation_filter is None else f"generation {self.evolution_generation_filter}"
        self.game.draw_text_left(f"{len(decks)} stored · {filter_name} · F changes filter", max(9, metrics.font_small - 2), x, y, self.game.palette.muted, width)
        y += metrics.font_normal + metrics.gap
        view = RectSpec(x, y, width, max(1, panel.bottom - metrics.margin - y))
        self.evolution_deck_viewport = view
        capacity = max(1, min(7, view.height // max(44, metrics.target_height)))
        max_start = max(0, len(decks) - capacity)
        self.evolution_deck_scroll = min(self.evolution_deck_scroll, max_start)
        visible = decks[self.evolution_deck_scroll:self.evolution_deck_scroll + capacity]
        self.evolution_deck_rects = []
        row_height = max(42, metrics.target_height)
        old_clip = self.game.display.get_clip()
        self.game.display.set_clip(pg.Rect(view.x, view.y, view.width, view.height).clip(old_clip))
        for index, deck in enumerate(visible):
            rect = RectSpec(view.x, view.y + index * row_height, view.width - 6, row_height - 4)
            self.evolution_deck_rects.append((deck.deck_id, rect))
            chosen = selected is not None and deck.deck_id == selected.deck_id
            pg.draw.rect(self.game.display, self.game.palette.selected if chosen else self.game.palette.panel_alt, pg.Rect(rect.x, rect.y, rect.width, rect.height), border_radius=7)
            pg.draw.rect(self.game.display, self.game.palette.accent if chosen else self.game.palette.border, pg.Rect(rect.x, rect.y, rect.width, rect.height), 2 if chosen else 1, border_radius=7)
            self.game.draw_text_left(deck.name, max(10, metrics.font_small - 2), rect.x + metrics.gap, rect.center[1], self.game.palette.text, rect.width * 65 // 100)
            score = "unscored" if deck.relative_fitness is None else f"{deck.relative_fitness:+.1f} relative"
            self.game.draw_text_left(score, max(9, metrics.font_small - 3), rect.x + rect.width * 66 // 100, rect.center[1], self.game.palette.success if (deck.relative_fitness or 0) >= 0 else self.game.palette.danger, rect.width * 32 // 100)
        self.game.display.set_clip(old_clip)

    def _draw_evolution_composition_panel(self, panel, selected):
        metrics = self.game.layout
        x = panel.x + metrics.margin
        width = panel.width - metrics.margin * 2
        y = panel.y + metrics.margin
        self.game.draw_text_left("SELECTED DECK COMPOSITION", metrics.font_normal, x, y, self.game.palette.text, width)
        y += metrics.font_normal
        if selected is None:
            self.game.draw_text_left("No generated deck selected", metrics.font_small, x, y + metrics.gap, self.game.palette.muted, width)
            return
        self.game.draw_text_left(f"{selected.name} · generation {selected.generation} · exact stored card IDs", max(9, metrics.font_small - 2), x, y, self.game.palette.muted, width)
        y += metrics.font_normal + metrics.gap
        if not selected.cards:
            self._draw_wrapped_text(
                "No recoverable card composition was stored for this historical deck. Adoption is disabled.",
                metrics.font_small,
                x,
                y,
                width,
                max_lines=3,
                color=self.game.palette.danger,
            )
            return
        for card in selected.cards:
            row = pg.Rect(x, y, width, max(24, metrics.font_small + 7))
            pg.draw.rect(self.game.display, self.game.palette.panel_alt, row, border_radius=5)
            color = self._counter_card_color(card.color, self.game.palette)
            pg.draw.rect(self.game.display, color, (row.x, row.y, 5, row.height), border_radius=4)
            self.game.draw_text_left(card.name, metrics.font_small, row.x + metrics.gap, row.centery, self.game.palette.text, row.width - 80)
            self.game.draw_text_left(f"×{card.copies}", metrics.font_small, row.right - 55, row.centery, color, 50)
            y += row.height + 4

    def _draw_evolution_population(self, content, detail, selected):
        metrics = self.game.layout
        chart_height = 260
        chart_panel = self._draw_dashboard_panel(RectSpec(content.x, content.y, content.width, chart_height), accent=(105, 172, 225))
        self._draw_evolution_fitness_chart(chart_panel, detail)
        y = content.y + chart_height + metrics.gap
        remaining = content.bottom - y
        if content.width >= 850:
            left, right = metrics.columns(RectSpec(content.x, y, content.width, remaining), (0.43, 0.57))
        else:
            half = max(420, (remaining - metrics.gap) // 2)
            left = RectSpec(content.x, y, content.width, half)
            right = RectSpec(content.x, left.bottom + metrics.gap, content.width, half)
        browser = self._draw_dashboard_panel(left, accent=self.game.palette.accent)
        composition = self._draw_dashboard_panel(right, accent=self.game.palette.success)
        self._draw_evolution_deck_browser(browser, detail, selected)
        self._draw_evolution_composition_panel(composition, selected)

    def _draw_evolution_matchups(self, content, detail, selected):
        metrics = self.game.layout
        panel = self._draw_dashboard_panel(content, accent=self.game.palette.accent)
        x = panel.x + metrics.margin
        width = panel.width - metrics.margin * 2
        y = panel.y + metrics.margin
        self.game.draw_text_left("LOCAL MATCHUPS", metrics.font_normal, x, y, self.game.palette.text, width)
        y += metrics.font_normal
        self.game.draw_text_left(
            f"Selected: {selected.name if selected else 'none'} · scores are deck-relative fitness, never win rates",
            metrics.font_small, x, y, self.game.palette.muted, width,
        )
        y += metrics.font_normal + metrics.gap
        rows = detail.deck_matchups(selected.deck_id if selected else None)
        if not rows:
            self.game.draw_text_left("No scheduled pairing rows for this deck", metrics.font_small, x, y, self.game.palette.muted, width)
        for row in rows:
            rect = pg.Rect(x, y, width, max(38, metrics.target_height - 4))
            pg.draw.rect(self.game.display, self.game.palette.panel_alt, rect, border_radius=6)
            self.game.draw_text_left(row.opponent_name, metrics.font_small, rect.x + metrics.gap, rect.centery, self.game.palette.text, rect.width * 65 // 100)
            color = self.game.palette.success if row.relative_score >= 0 else self.game.palette.danger
            self.game.draw_text_left(f"{row.relative_score:+.1f} relative fitness", metrics.font_small, rect.x + rect.width * 66 // 100, rect.centery, color, rect.width * 32 // 100)
            y += rect.height + 5
        y += metrics.gap
        self._draw_wrapped_text(
            "Observed match_dbt scores have no W/D/L denominator. Run a separate 1,000-game Duel evaluation for a stable head-to-head comparison.",
            metrics.font_small, x, y, width, max_lines=4, color=self.game.palette.accent,
        )

    def _draw_evolution_composition(self, content, detail, selected):
        metrics = self.game.layout
        top_height = max(440, len(detail.card_signals) * 46 + 80)
        signals_panel = self._draw_dashboard_panel(RectSpec(content.x, content.y, content.width, top_height), accent=(105, 172, 225))
        x = signals_panel.x + metrics.margin
        width = signals_panel.width - metrics.margin * 2
        y = signals_panel.y + metrics.margin
        self.game.draw_text_left("CARD ADOPTION · FIRST VS FINAL GENERATION", metrics.font_normal, x, y, self.game.palette.text, width)
        y += metrics.font_normal + metrics.gap
        if not detail.card_signals:
            self._draw_wrapped_text(
                "No recoverable deck compositions are available for first-versus-final card analysis.",
                metrics.font_small,
                x,
                y,
                width,
                max_lines=3,
                color=self.game.palette.danger,
            )
            return
        for signal in detail.card_signals:
            first = signal.first_presence / max(1, signal.first_total)
            final = signal.final_presence / max(1, signal.final_total)
            self.game.draw_text_left(signal.name, max(9, metrics.font_small - 2), x, y, self.game.palette.text, width * 28 // 100)
            self.game.draw_text_left(f"{signal.first_presence}/{signal.first_total} → {signal.final_presence}/{signal.final_total} decks", max(9, metrics.font_small - 3), x + width * 30 // 100, y, self.game.palette.muted, width * 38 // 100)
            self.game.draw_text_left(f"mean copies when present {signal.first_mean_copies_when_present:.2f} → {signal.final_mean_copies_when_present:.2f}", max(9, metrics.font_small - 4), x + width * 68 // 100, y, self.game.palette.accent, width * 32 // 100)
            y += metrics.font_normal + 6
            bar = pg.Rect(x + width * 30 // 100, y - 8, width * 35 // 100, 6)
            self._draw_dashboard_bar(bar, final, self.game.palette.success if final >= first else self.game.palette.danger)
        note_y = signals_panel.bottom - metrics.margin * 2
        self.game.draw_text_left("Stored deck lists show composition presence—not draw, play, or ability-use frequency.", max(9, metrics.font_small - 2), x, note_y, self.game.palette.muted, width)

    def _draw_evolution_research(self, content, detail):
        metrics = self.game.layout
        intro = self._draw_dashboard_panel(RectSpec(content.x, content.y, content.width, 150), accent=self.game.palette.accent)
        self.game.draw_text_left("THE HONEST SPLIT", metrics.font_normal, intro.x + metrics.margin, intro.y + metrics.margin, self.game.palette.text, intro.width - metrics.margin * 2)
        self._draw_wrapped_text("The Arena keeps bounded, run-scoped evidence live. Controller-level, multi-seed, uncertainty, and causal analyses belong in cached notebooks or raw SQL.", metrics.font_small, intro.x + metrics.margin, intro.y + metrics.margin + metrics.font_normal * 2, intro.width - metrics.margin * 2, max_lines=4, color=self.game.palette.muted)
        y = intro.bottom + metrics.gap
        columns = metrics.columns(RectSpec(content.x, y, content.width, 360), (0.34, 0.33, 0.33)) if content.width >= 850 else (
            RectSpec(content.x, y, content.width, 240),
            RectSpec(content.x, y + 250, content.width, 240),
            RectSpec(content.x, y + 500, content.width, 240),
        )
        groups = (
            ("ARENA · AVAILABLE NOW", self.game.palette.success, ("Run completion and integrity", "Population score spread", "Stored composition shifts", "Relative local matchup scores", "Source and denominators")),
            ("NOTEBOOK / PRECOMPUTE", self.game.palette.accent, ("Controller learning curves", "Held-out W/D/L aggregation", "Composition-aware archetypes", "Multi-seed replication tests", "Uncertainty and sensitivity")),
            ("NOT LOGGED FOR THIS RUN", self.game.palette.danger, ("Drawn-card win rate", "Played-card win rate", "Ability-use causal effects", "Turn-level timing effects", "Dragon-specific outcome paths")),
        )
        for spec, (title, color, rows) in zip(columns, groups):
            panel = self._draw_dashboard_panel(spec, accent=color)
            x = panel.x + metrics.margin
            yy = panel.y + metrics.margin
            self.game.draw_text_left(title, metrics.font_small, x, yy, color, panel.width - metrics.margin * 2)
            yy += metrics.font_normal * 2
            for row in rows:
                self.game.draw_text_left(f"■  {row}", max(9, metrics.font_small - 2), x, yy, self.game.palette.text, panel.width - metrics.margin * 2)
                yy += metrics.font_normal * 2

    def _draw_evolution_dashboard(self, telemetry, detail):
        self.draw_background()
        if detail is None:
            self._draw_mission_placeholder(telemetry, TrainingKind.DECK_BUILDER.value)
            return
        pages = self._dashboard_pages()
        self.dashboard_page %= len(pages)
        title = pages[self.dashboard_page].lower()
        self.draw_title(
            f"Deck evolution / {title}",
            f"Completed run DB {detail.training_id} · relative evidence, not absolute quality",
        )
        compact = self.game.DISPLAY_W < 1050
        pulse_height = 650 + (150 if detail.issues else 0)
        heights = (pulse_height, 1180 if compact else 900, max(720, 150 + len(detail.deck_matchups(self.evolution_selected_deck_id)) * 45), max(760, len(detail.card_signals) * 46 + 110), 820 if compact else 560)
        layout = evolution_dashboard_layout(
            self.game.layout,
            content_height=heights[self.dashboard_page],
            scroll=self.dashboard_scroll,
        )
        self.dashboard_max_scroll = layout.max_scroll
        self.dashboard_scroll = min(self.dashboard_scroll, layout.max_scroll)
        selected = self._evolution_selected(detail)
        self._draw_evolution_navigation(layout, detail)
        self.game.display.set_clip(pg.Rect(layout.viewport.x, layout.viewport.y, layout.viewport.width, layout.viewport.height))
        self.evolution_deck_rects = []
        self.evolution_deck_viewport = None
        if self.dashboard_page == 0:
            self._draw_evolution_run_pulse(layout.content, detail)
        elif self.dashboard_page == 1:
            self._draw_evolution_population(layout.content, detail, selected)
        elif self.dashboard_page == 2:
            self._draw_evolution_matchups(layout.content, detail, selected)
        elif self.dashboard_page == 3:
            self._draw_evolution_composition(layout.content, detail, selected)
        else:
            self._draw_evolution_research(layout.content, detail)
        self.game.display.set_clip(None)
        self._draw_dashboard_scrollbar(layout.viewport)
        self._draw_evolution_footer(layout.footer, detail, selected)

    def _draw_mission_placeholder(self, telemetry, kind):
        self.draw_background()
        mission = {
            TrainingKind.PLAYER_DECK.value: "Counter-deck training",
            TrainingKind.DECK_BUILDER.value: "General deck evolution",
        }.get(kind, "Training mission")
        item = self.dashboard_item
        identity = getattr(item, "job_id", getattr(item, "run_id", "Training run"))
        status = str(getattr(item, "status", telemetry.status) or "pending")
        progress = (
            f" · GEN {telemetry.generation}/{telemetry.total_generations}"
            if telemetry.total_generations > 0 and status == "running"
            else ""
        )
        self.draw_title(
            "Training Arena",
            f"{mission} · {status.upper()}{progress}",
        )
        metrics = self.game.layout
        footer = RectSpec(
            metrics.margin,
            metrics.height - metrics.margin - metrics.target_height,
            metrics.width - metrics.margin * 2,
            metrics.target_height,
        )
        content = RectSpec(
            metrics.margin,
            metrics.margin + metrics.font_large + metrics.font_small + metrics.gap * 3,
            metrics.width - metrics.margin * 2,
            max(1, footer.y - metrics.gap - (metrics.margin + metrics.font_large + metrics.font_small + metrics.gap * 3)),
        )
        panel = self._draw_dashboard_panel(content, accent=self.game.palette.accent)
        self.game.draw_text(
            mission,
            metrics.font_large,
            panel.centerx,
            panel.centery - metrics.font_large,
            self.game.palette.text,
        )
        self.game.draw_text(
            identity,
            metrics.font_small,
            panel.centerx,
            panel.centery,
            self.game.palette.muted,
        )
        self.game.draw_text(
            "Detailed view coming next",
            metrics.font_normal,
            panel.centerx,
            panel.centery + metrics.font_large,
            self.game.palette.accent,
        )
        self.dashboard_scroll = 0
        self.dashboard_max_scroll = 0
        self._draw_mission_footer(footer)

    def draw_training_dashboard(
        self,
        telemetry: TrainingTelemetry | None = None,
        insights: TrainingInsights | None = None,
    ):
        """Draw the game-like Training Arena without opening scientific results."""
        self.draw_background()
        telemetry = telemetry or self._dashboard_telemetry()
        insights = insights or self.dashboard_insights
        kind = self._dashboard_kind(insights)
        destination = self._arena_destination()
        if destination != ArenaDestination.RESULTS:
            self._draw_training_progress(telemetry, destination)
            return
        if kind == TrainingKind.PLAYER_DECK.value:
            detail = insights.counter if insights is not None else None
            self._draw_counter_dashboard(telemetry, detail)
            self._draw_adoption_overlay()
            return
        if kind == TrainingKind.MATCHUP_EVALUATION.value:
            detail = insights.matchup if insights is not None else None
            self._draw_matchup_dashboard(telemetry, detail)
            return
        if kind == TrainingKind.DECK_BUILDER.value:
            detail = insights.evolution if insights is not None else None
            self._draw_evolution_dashboard(telemetry, detail)
            self._draw_adoption_overlay()
            return
        item = self.dashboard_item
        title = (
            f"{item.run_id} · {item.title}"
            if isinstance(item, TrainingRunSummary)
            else getattr(item, "job_id", "Training Arena")
        )
        if insights is not None and insights.subject:
            title = insights.subject
        self.draw_title("Training Arena", title)
        layout = training_dashboard_layout(self.game.layout)
        self.dashboard_buttons = []
        self._draw_dashboard_navigation(layout, insights)
        if self.dashboard_page == 1:
            self._draw_performance_page(layout, insights)
            self._draw_dashboard_footer(layout)
            return
        if self.dashboard_page == 2:
            if self._dashboard_kind(insights) in {
                TrainingKind.PLAYER_DECK.value,
                TrainingKind.MATCHUP_EVALUATION.value,
            }:
                self._draw_evaluation_page(layout, insights)
            else:
                self._draw_matchups_page(layout, insights)
            self._draw_dashboard_footer(layout)
            return
        if self.dashboard_page == 3:
            self._draw_conclusions_page(layout, insights)
            self._draw_dashboard_footer(layout)
            return
        hero = self._draw_dashboard_panel(layout["hero"], accent=self.game.palette.accent)
        trail = self._draw_dashboard_panel(layout["trail"])
        systems = self._draw_dashboard_panel(layout["systems"])
        metrics = self.game.layout
        progress = self._training_progress(telemetry)
        status_color = {
            "running": self.game.palette.accent,
            "completed": self.game.palette.success,
            "failed": self.game.palette.danger,
        }.get(telemetry.status, self.game.palette.muted)

        status_rect = pg.Rect(
            hero.x + metrics.gap,
            hero.y + metrics.gap,
            min(hero.width - metrics.gap * 2, 150),
            max(24, metrics.target_height // 2),
        )
        pg.draw.rect(self.game.display, self.game.palette.panel_alt, status_rect, border_radius=12)
        pg.draw.rect(self.game.display, status_color, status_rect, 2, border_radius=12)
        self.game.draw_text(
            telemetry.status.upper(),
            max(11, metrics.font_small - 2),
            status_rect.centerx,
            status_rect.centery,
            status_color,
        )

        ring_center = (hero.centerx, hero.centery + metrics.gap)
        radius = max(34, min(hero.width // 4, hero.height // 4))
        ring = pg.Rect(
            ring_center[0] - radius,
            ring_center[1] - radius,
            radius * 2,
            radius * 2,
        )
        pg.draw.arc(self.game.display, self.game.palette.disabled, ring, 0, math.tau, 10)
        if progress:
            pg.draw.arc(
                self.game.display,
                status_color,
                ring,
                -math.pi / 2,
                -math.pi / 2 + math.tau * progress,
                10,
            )
        self.game.draw_text(
            f"{round(progress * 100)}%",
            metrics.font_large,
            ring_center[0],
            ring_center[1] - metrics.font_small // 2,
            status_color,
        )
        generation_label = (
            f"CHECKPOINT GEN {telemetry.checkpoint_generation}"
            if telemetry.phase == "checkpoint_evaluation" and telemetry.checkpoint_generation
            else f"GEN {telemetry.generation} / {telemetry.total_generations}"
            if telemetry.total_generations
            else f"GEN {telemetry.generation}"
        )
        self.game.draw_text(
            generation_label,
            metrics.font_small,
            ring_center[0],
            ring_center[1] + metrics.font_large // 2,
            self.game.palette.muted,
        )
        self.game.draw_text(
            self._phase_label(telemetry.phase).upper(),
            max(11, metrics.font_small - 2),
            hero.centerx,
            hero.bottom - metrics.gap,
            self.game.palette.muted,
        )

        self.game.draw_text_left(
            "EVOLUTION TRAIL",
            metrics.font_normal,
            trail.x + metrics.margin,
            trail.y + metrics.margin,
            self.game.palette.text,
            trail.width - metrics.margin * 2,
        )
        score_label = (
            f"Best recorded fitness {telemetry.best_score:.1f}"
            if telemetry.best_score is not None
            else "Fitness data pending"
        )
        self.game.draw_text_left(
            score_label,
            metrics.font_small,
            trail.x + metrics.margin,
            trail.y + metrics.margin + metrics.font_normal + 4,
            self.game.palette.accent,
            trail.width - metrics.margin * 2,
        )
        graph = pg.Rect(
            trail.x + metrics.margin,
            trail.y + metrics.margin + metrics.font_normal + metrics.font_small + metrics.gap,
            trail.width - metrics.margin * 2,
            max(1, trail.height - metrics.margin * 2 - metrics.font_normal - metrics.font_small - metrics.gap),
        )
        for index in range(1, 5):
            y = graph.y + graph.height * index // 5
            pg.draw.line(
                self.game.display,
                self.game.palette.panel_alt,
                (graph.x, y),
                (graph.right, y),
                1,
            )
        history = list(telemetry.fitness_history)
        if len(history) >= 2:
            values = [value for _, value in history]
            low, high = min(values), max(values)
            span = max(1.0, high - low)
            points = [
                (
                    graph.x + round(index * graph.width / max(1, len(history) - 1)),
                    graph.bottom - round((value - low) / span * graph.height),
                )
                for index, (_, value) in enumerate(history)
            ]
            pg.draw.lines(self.game.display, self.game.palette.hover, False, points, 8)
            pg.draw.lines(self.game.display, self.game.palette.accent, False, points, 3)
            for point in points:
                pg.draw.circle(self.game.display, self.game.palette.background, point, 6)
                pg.draw.circle(self.game.display, self.game.palette.accent, point, 4)
        else:
            pulse_y = graph.centery
            pg.draw.line(
                self.game.display,
                self.game.palette.hover,
                (graph.x, pulse_y),
                (graph.right, pulse_y),
                5,
            )
            pg.draw.circle(
                self.game.display,
                self.game.palette.accent,
                (graph.x + round(graph.width * progress), pulse_y),
                7,
            )
            self.game.draw_text(
                "Awaiting the next champion signal",
                metrics.font_small,
                graph.centerx,
                graph.centery + metrics.font_normal,
                self.game.palette.muted,
            )

        inner = systems.inflate(-metrics.margin * 2, -metrics.gap * 2)
        column_width = inner.width // 3
        columns = [
            pg.Rect(inner.x + index * column_width, inner.y, column_width, inner.height)
            for index in range(3)
        ]
        self.game.draw_text_left(
            "GENERATION PROGRESS",
            metrics.font_small,
            columns[0].x,
            columns[0].y + metrics.font_small // 2,
            self.game.palette.muted,
            columns[0].width - metrics.gap,
        )
        gate_y = columns[0].centery
        gate_gap = max(2, metrics.gap // 3)
        gate_width = max(3, (columns[0].width - metrics.gap - gate_gap * 9) // 10)
        for index in range(10):
            rect = pg.Rect(
                columns[0].x + index * (gate_width + gate_gap),
                gate_y,
                gate_width,
                max(10, metrics.target_height // 3),
            )
            color = self.game.palette.accent if (index + 1) / 10 <= progress else self.game.palette.disabled
            pg.draw.rect(self.game.display, color, rect, border_radius=3)

        self.game.draw_text_left(
            "CURRENT BATCH",
            metrics.font_small,
            columns[1].x + metrics.gap,
            columns[1].y + metrics.font_small // 2,
            self.game.palette.muted,
            columns[1].width - metrics.gap * 2,
        )
        round_ratio = (
            telemetry.round_completed / telemetry.round_total
            if telemetry.round_total
            else progress
        )
        pulse_rect = pg.Rect(
            columns[1].x + metrics.gap,
            columns[1].centery,
            columns[1].width - metrics.gap * 2,
            max(14, metrics.target_height // 3),
        )
        self._draw_dashboard_bar(pulse_rect, round_ratio, self.game.palette.success)
        pulse_label = (
            f"{telemetry.round_completed} / {telemetry.round_total} battles"
            if telemetry.round_total
            else f"{telemetry.genome_count} contenders"
            if telemetry.genome_count
            else "Preparing game queue"
        )
        self.game.draw_text(
            pulse_label,
            max(11, metrics.font_small - 2),
            columns[1].centerx,
            pulse_rect.bottom + metrics.gap,
            self.game.palette.text,
        )

        self.game.draw_text_left(
            "RUN TIME",
            metrics.font_small,
            columns[2].x + metrics.gap,
            columns[2].y + metrics.font_small // 2,
            self.game.palette.muted,
            columns[2].width - metrics.gap * 2,
        )
        shown_workers = min(8, telemetry.workers)
        crew_y = columns[2].centery + metrics.gap // 2
        for index in range(max(1, shown_workers)):
            x = columns[2].x + metrics.gap * 2 + index * max(12, metrics.gap * 2)
            if x > columns[2].right - metrics.gap:
                break
            pg.draw.circle(
                self.game.display,
                status_color if index < shown_workers else self.game.palette.disabled,
                (x, crew_y),
                max(4, metrics.gap // 2),
            )
        crew_label = f"Elapsed {self._duration_label(telemetry.elapsed_seconds)}"
        if telemetry.eta_seconds is not None and telemetry.status == "running":
            crew_label = f"ETA {self._duration_label(telemetry.eta_seconds)} · {telemetry.workers} workers"
        elif telemetry.workers:
            crew_label += f" · {telemetry.workers} workers"
        self.game.draw_text(
            crew_label,
            max(11, metrics.font_small - 2),
            columns[2].centerx,
            systems.bottom - metrics.gap,
            self.game.palette.text,
        )

        self._draw_dashboard_footer(layout)

    def _detail_dialog(self, item):
        if isinstance(item, TrainingRunSummary):
            lines = [
                f"Status: {item.status}",
                f"Started: {item.started}",
                item.detail,
                (
                    f"Best fitness: {item.best_score:.2f}"
                    if item.best_score is not None
                    else "Best fitness: pending"
                ),
                f"Best deck: {item.best_deck_id or 'pending'}",
            ]
            title = f"{item.run_id}: {item.title}"
        else:
            job = self.service.refresh(item)
            title = job.job_id
            lines = [
                f"Status: {job.status}",
                f"Started: {job.created_at}",
                f"Process: {job.pid or 'finished'}",
                f"Output: {Path(job.log_path).parent}",
            ]
            try:
                summary = json.loads(Path(job.summary_path).read_text())
                evaluation = summary.get("evaluation", {})
                lines.extend(
                    [
                        f"Best fitness: {summary.get('best_fitness', 0):.2f}",
                        (
                            "AI win rate: "
                            f"{100 * evaluation.get('ai_win_rate', 0):.1f}% "
                            f"({evaluation.get('games', 0)} games)"
                        ),
                        f"Artifact: {Path(summary.get('artifact_path', '')).name}",
                    ]
                )
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                lines.extend(
                    self.service.tail(
                        job.progress_path if Path(job.progress_path).exists() else job.log_path,
                        max_lines=7,
                    )
                )
        self.show_lines(title, lines)

    def _text_dialog(self, title, initial):
        return self.prompt_text(title, initial, max_length=32)

    def _confirm_dialog(self, title, lines):
        return self.confirm_action(title, lines, confirm_label="Launch")
