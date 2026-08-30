from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pygame as pg

from py_game.menu.base_menu import Menu
from py_game.training_service import (
    TrainingKind,
    TrainingRequest,
    TrainingRunSummary,
    TrainingService,
    unfinished_database_run,
)
from utils.database_utils import DBUtil

if TYPE_CHECKING:
    from py_game.game import Game


class TrainingMenu(Menu):
    """Professor-facing setup, monitoring, and compact result browser."""

    PLAYER_GENERATIONS = [10, 20, 35, 50, 65]
    BUILDER_GENERATIONS = [35, 50, 65]
    WORKERS = [4, 8, 12]
    MATCH_COUNTS = [4, 8, 12]
    HOLDOUT_COUNTS = [5, 10, 20]
    EVALUATION_GAMES = [20, 100, 300]
    SEED_SETS = [
        (104729,),
        (400009,),
        (400009, 450001, 500009, 550007),
    ]

    def __init__(self, game: "Game"):
        super().__init__(game)
        self.previous_menu = None
        self.service = TrainingService()
        self.view = "setup"
        self.selected = 0
        self.kind_index = list(TrainingKind).index(TrainingKind.PLAYER_DECK)
        self.deck_ids = DBUtil().get_all_deck_ids()
        self.deck_index = 0
        self.generation_index = 2
        self.worker_index = len(self.WORKERS) - 1
        self.match_index = len(self.MATCH_COUNTS) - 1
        self.holdout_index = len(self.HOLDOUT_COUNTS) - 1
        self.evaluation_index = 1
        self.seed_index = 0
        self.outer_generations = 1
        self.run_label = "pygame"
        self.message = ""
        self.message_color = self.game.WHITE
        self.jobs = []
        self.database_runs = []
        self.active_database_id = None
        self.last_refresh = 0
        self._refresh_runs(force=True)

    @property
    def kind(self):
        return list(TrainingKind)[self.kind_index]

    def _generation_options(self):
        if self.kind == TrainingKind.PLAYER_DECK:
            return self.PLAYER_GENERATIONS
        return self.BUILDER_GENERATIONS

    def _generation(self):
        values = self._generation_options()
        return values[self.generation_index % len(values)]

    def _request(self):
        deck_id = (
            self.deck_ids[self.deck_index % len(self.deck_ids)]
            if self.deck_ids
            else None
        )
        return TrainingRequest(
            kind=self.kind,
            run_label=self.run_label,
            deck_id=deck_id,
            seeds=self.SEED_SETS[self.seed_index],
            outer_generations=self.outer_generations,
            matches_per_genome=self.MATCH_COUNTS[self.match_index],
            evaluator_generations=self._generation(),
            workers=self.WORKERS[self.worker_index],
            holdout_seed_pairs=self.HOLDOUT_COUNTS[self.holdout_index],
            evaluation_games=self.EVALUATION_GAMES[self.evaluation_index],
        )

    def _setup_rows(self):
        deck = (
            self.deck_ids[self.deck_index % len(self.deck_ids)]
            if self.deck_ids
            else "No player decks"
        )
        common = [
            ("Back", "action"),
            ("View completed and active runs", "action"),
            (f"Training type: {self.kind.value}", "kind"),
            (f"Run label: {self.run_label}", "label"),
        ]
        if self.kind == TrainingKind.PLAYER_DECK:
            common.extend(
                [
                    (f"Player deck: {deck}", "deck"),
                    (f"Generations: {self._generation()}", "generations"),
                    (f"Workers: {self.WORKERS[self.worker_index]}", "workers"),
                    (
                        f"Evaluation games: {self.EVALUATION_GAMES[self.evaluation_index]}",
                        "evaluation",
                    ),
                ]
            )
        else:
            seed_label = ", ".join(str(seed) for seed in self.SEED_SETS[self.seed_index])
            common.extend(
                [
                    (f"Seeds: {seed_label}", "seeds"),
                    (f"Outer generations: {self.outer_generations}", "outer"),
                    (f"Inner generations: {self._generation()}", "generations"),
                    (
                        f"Matches per builder: {self.MATCH_COUNTS[self.match_index]}",
                        "matches",
                    ),
                    (f"Evaluator workers: {self.WORKERS[self.worker_index]}", "workers"),
                    (
                        f"Holdout seed pairs: {self.HOLDOUT_COUNTS[self.holdout_index]}",
                        "holdout",
                    ),
                ]
            )
        common.append(("Review and launch", "launch"))
        return common

    def _run_rows(self):
        rows = [("Back", "back"), ("Configure a training run", "setup")]
        rows.extend((f"{job.job_id}  [{job.status}]", job) for job in self.jobs)
        rows.extend(
            (
                f"{run.run_id}  {run.title}  [{run.status}]",
                run,
            )
            for run in self.database_runs
        )
        return rows

    def _rows(self):
        return self._setup_rows() if self.view == "setup" else self._run_rows()

    @staticmethod
    def _cycle(index, count, direction):
        return (index + direction) % count if count else 0

    def _edit_setup_value(self, key, direction):
        if key == "kind":
            self.kind_index = self._cycle(
                self.kind_index,
                len(TrainingKind),
                direction,
            )
            preferred = 35 if self.kind == TrainingKind.PLAYER_DECK else 50
            self.generation_index = self._generation_options().index(preferred)
        elif key == "deck":
            self.deck_index = self._cycle(
                self.deck_index,
                len(self.deck_ids),
                direction,
            )
        elif key == "generations":
            self.generation_index = self._cycle(
                self.generation_index,
                len(self._generation_options()),
                direction,
            )
        elif key == "workers":
            self.worker_index = self._cycle(
                self.worker_index,
                len(self.WORKERS),
                direction,
            )
        elif key == "evaluation":
            self.evaluation_index = self._cycle(
                self.evaluation_index,
                len(self.EVALUATION_GAMES),
                direction,
            )
        elif key == "seeds":
            self.seed_index = self._cycle(
                self.seed_index,
                len(self.SEED_SETS),
                direction,
            )
        elif key == "outer":
            self.outer_generations = 10 if self.outer_generations == 1 else 1
        elif key == "matches":
            self.match_index = self._cycle(
                self.match_index,
                len(self.MATCH_COUNTS),
                direction,
            )
        elif key == "holdout":
            self.holdout_index = self._cycle(
                self.holdout_index,
                len(self.HOLDOUT_COUNTS),
                direction,
            )

    def _refresh_runs(self, force=False):
        now = pg.time.get_ticks()
        if not force and now - self.last_refresh < 2000:
            return
        self.last_refresh = now
        try:
            self.jobs = self.service.jobs()
            self.database_runs = self.service.recent_database_runs()
            self.active_database_id = unfinished_database_run()
        except (OSError, RuntimeError, TimeoutError) as error:
            self.message = f"Could not refresh runs: {error}"
            self.message_color = (235, 105, 105)

    def _launch(self):
        request = self._request()
        try:
            request.validate()
        except ValueError as error:
            self.message = str(error)
            self.message_color = (235, 105, 105)
            return
        lines = [
            request.kind.value,
            f"Label: {request.run_label}",
            (
                f"Deck: {request.deck_id}"
                if request.kind == TrainingKind.PLAYER_DECK
                else f"Seeds: {', '.join(map(str, request.seeds))}"
            ),
            f"Generations: {request.evaluator_generations}",
            f"Workers: {request.workers}",
        ]
        if not self._confirm_dialog("Launch training?", lines):
            return
        try:
            job = self.service.start(request)
        except (ValueError, RuntimeError, OSError) as error:
            self.message = str(error)
            self.message_color = (235, 105, 105)
            return
        self.message = f"Started {job.job_id}"
        self.message_color = (105, 210, 150)
        self.view = "runs"
        self.selected = 2
        self._refresh_runs(force=True)

    def _activate_setup(self, key):
        if key == "action":
            if self.selected == 0:
                self._return()
            else:
                self.view = "runs"
                self.selected = 0
                self._refresh_runs(force=True)
        elif key == "label":
            label = self._text_dialog("Run label", self.run_label)
            if label is not None and label.strip():
                self.run_label = label.strip()
        elif key == "launch":
            self._launch()
        else:
            self._edit_setup_value(key, 1)

    def _activate_run(self, value):
        if value == "back":
            self._return()
        elif value == "setup":
            self.view = "setup"
            self.selected = 0
        else:
            self._detail_dialog(value)

    def _return(self):
        self.run_display = False
        self.game.curr_menu = self.previous_menu
        if self.previous_menu is not None:
            self.previous_menu.__init__(self.game)
            self.previous_menu.run_display = True

    def check_input(self):
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
        if not self.game.START_KEY:
            return
        if self.view == "setup":
            self._activate_setup(rows[self.selected][1])
        else:
            self._activate_run(rows[self.selected][1])

    def display_menu(self):
        self.run_display = True
        self.game.reset_keys()
        while self.run_display:
            self._refresh_runs()
            self.game.check_events()
            self.check_input()
            if not self.run_display:
                break
            rows = self._rows()
            self.selected = min(self.selected, len(rows) - 1)
            self.game.display.fill(self.game.DARK_GREY)
            title = "AI Training" if self.view == "setup" else "Training Runs"
            self.game.draw_text(title, self.TEXT_LARGE, self.mid_w, 45)
            active_id = self.active_database_id
            if active_id is not None:
                self.game.draw_text(
                    f"Database run {active_id} is active",
                    self.TEXT_NORMAL,
                    self.mid_w,
                    82,
                    (235, 190, 90),
                )
            page_size = 11
            offset = max(
                0,
                min(self.selected - page_size + 1, len(rows) - page_size),
            )
            for row, (label, _) in enumerate(rows[offset : offset + page_size]):
                index = offset + row
                color = (
                    self.game.ORANGE
                    if index == self.selected
                    else self.game.WHITE
                )
                self.game.draw_text_left(
                    label,
                    self.TEXT_NORMAL,
                    self.game.DISPLAY_W * 0.125,
                    125 + row * 36,
                    color,
                    self.game.DISPLAY_W * 0.75,
                )
            if self.message:
                self.game.draw_text(
                    self.message,
                    self.TEXT_NORMAL,
                    self.mid_w,
                    565,
                    self.message_color,
                )
            self.blit_screen()

    def _detail_dialog(self, item):
        while True:
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    return
                if event.type == pg.KEYDOWN and event.key in (
                    pg.K_ESCAPE,
                    pg.K_BACKSPACE,
                    pg.K_RETURN,
                    pg.K_SPACE,
                ):
                    return
            self.game.display.fill(self.game.DARK_GREY)
            lines = []
            if isinstance(item, TrainingRunSummary):
                lines = [
                    f"{item.run_id}: {item.title}",
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
            else:
                job = self.service.refresh(item)
                lines = [
                    job.job_id,
                    f"Status: {job.status}",
                    f"Started: {job.created_at}",
                    f"Process: {job.pid or 'finished'}",
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
                    log_lines = self.service.tail(
                        job.progress_path
                        if Path(job.progress_path).exists()
                        else job.log_path,
                        max_lines=7,
                    )
                    lines.extend(log_lines)

            self.game.draw_text(lines[0], self.TEXT_LARGE, self.mid_w, 65)
            for index, line in enumerate(lines[1:11]):
                self.game.draw_text_left(
                    str(line),
                    self.TEXT_NORMAL,
                    60,
                    125 + index * 38,
                    self.game.WHITE,
                    680,
                )
            self.game.window.blit(self.game.display, (0, 0))
            pg.display.update()
            self.game.clock.tick(30)

    def _text_dialog(self, title, initial):
        value = initial
        while True:
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    return None
                if event.type != pg.KEYDOWN:
                    continue
                if event.key == pg.K_ESCAPE:
                    return None
                if event.key == pg.K_RETURN:
                    return value
                if event.key == pg.K_BACKSPACE:
                    value = value[:-1]
                elif event.unicode.isprintable() and len(value) < 32:
                    value += event.unicode
            self.game.display.fill(self.game.DARK_GREY)
            self.game.draw_text(title, self.TEXT_LARGE, self.mid_w, 235)
            field = pg.Rect(self.mid_w - 220, 280, 440, 55)
            pg.draw.rect(self.game.display, (20, 22, 24), field)
            pg.draw.rect(self.game.display, self.game.ORANGE, field, 2)
            self.game.draw_text(value, self.TEXT_NORMAL, self.mid_w, 307)
            self.blit_screen()

    def _confirm_dialog(self, title, lines):
        confirmed = False
        while True:
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    return False
                if event.type != pg.KEYDOWN:
                    continue
                if event.key in (pg.K_ESCAPE, pg.K_BACKSPACE):
                    return False
                if event.key in (pg.K_LEFT, pg.K_RIGHT):
                    confirmed = not confirmed
                if event.key in (pg.K_RETURN, pg.K_SPACE):
                    return confirmed
            self.game.display.fill(self.game.DARK_GREY)
            self.game.draw_text(title, self.TEXT_LARGE, self.mid_w, 145)
            for index, line in enumerate(lines):
                self.game.draw_text(
                    line,
                    self.TEXT_NORMAL,
                    self.mid_w,
                    210 + index * 32,
                )
            self.game.draw_text(
                "Launch" if confirmed else "Cancel",
                self.TEXT_NORMAL,
                self.mid_w,
                420,
                self.game.ORANGE,
            )
            self.blit_screen()
