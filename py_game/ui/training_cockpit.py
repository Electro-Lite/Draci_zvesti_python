"""State and responsive geometry for the AI training workbench."""

from __future__ import annotations

import datetime as dt
import re
import secrets
from dataclasses import dataclass, field

from neat_ai.training_plan import matchup_checkpoints
from py_game.training_service import TrainingKind, TrainingRequest
from py_game.ui.layout import LayoutMetrics, RectSpec
from py_game.ui.training_setup import presets_for, training_workload


COUNTER_FIELDS = (
    "run_label",
    "deck_id",
    "outer_generations",
    "evaluator_generations",
    "workers",
    "evaluation_games",
)
MATCHUP_FIELDS = (
    "run_label",
    "deck_id",
    "opponent_deck_id",
    "evaluator_generations",
    "workers",
    "evaluation_games",
)
BUILDER_FIELDS = (
    "run_label",
    "seeds",
    "outer_generations",
    "evaluator_generations",
    "matches_per_genome",
    "workers",
    "holdout_seed_pairs",
)
PRESET_FIELDS = {
    "seeds",
    "outer_generations",
    "evaluator_generations",
    "matches_per_genome",
    "workers",
    "holdout_seed_pairs",
    "evaluation_games",
}


@dataclass
class TrainingDraft:
    run_label: str = ""
    deck_id: str = ""
    opponent_deck_id: str = ""
    seeds: str = "104729"
    outer_generations: str = "1"
    evaluator_generations: str = "40"
    matches_per_genome: str = "12"
    workers: str = "8"
    holdout_seed_pairs: str = "20"
    evaluation_games: str = "1000"
    preset_index: int | None = 1
    auto_run_label: bool = True
    run_stamp: str = field(
        default_factory=lambda: dt.datetime.now().strftime("%y%m%d-%H")
    )
    run_id: str = field(default_factory=lambda: secrets.token_hex(2).upper())


def _run_name_segment(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9.-]+", "-", str(value).strip()).strip("-")
    return cleaned or fallback


def _bounded_segment(value: str, maximum: int) -> str:
    if len(value) <= maximum:
        return value
    return value[:maximum].rstrip("-.")


def default_run_label(kind: TrainingKind, draft: TrainingDraft) -> str:
    """Return a descriptive mission/preset/time/deck label within 64 characters.

    The job service owns the unique run ID. Repeating that ID in this
    user-facing label wastes the limited width available in the workbench and
    run library.
    """
    preset = (
        ("quick", "balanced", "deep")[draft.preset_index]
        if draft.preset_index in range(3)
        else "custom"
    )
    if kind == TrainingKind.PLAYER_DECK:
        prefix = f"counter_{preset}_{draft.run_stamp}_"
        deck = _run_name_segment(draft.deck_id, "no-deck")
        deck = _bounded_segment(deck, 64 - len(prefix))
        return f"{prefix}{deck}"
    if kind == TrainingKind.MATCHUP_EVALUATION:
        prefix = f"matchup_{preset}_{draft.run_stamp}_"
        available = 64 - len(prefix) - len("-vs-")
        first_width = max(1, available // 2)
        second_width = max(1, available - first_width)
        first = _bounded_segment(
            _run_name_segment(draft.deck_id, "no-deck"),
            first_width,
        )
        second = _bounded_segment(
            _run_name_segment(draft.opponent_deck_id, "no-deck"),
            second_width,
        )
        return f"{prefix}{first}-vs-{second}"
    return f"deck-builder_{preset}_{draft.run_stamp}"


@dataclass(frozen=True)
class CockpitValidation:
    errors: dict[str, str]
    request: TrainingRequest | None

    @property
    def valid(self) -> bool:
        return self.request is not None and not self.errors


class TrainingCockpitState:
    """Own independent, editable drafts for both training missions."""

    def __init__(self, deck_ids=()):
        self.deck_ids = tuple(str(deck_id) for deck_id in deck_ids)
        first = self.deck_ids[0] if self.deck_ids else ""
        second = self.deck_ids[1] if len(self.deck_ids) > 1 else first
        self.drafts = {
            TrainingKind.PLAYER_DECK: TrainingDraft(
                deck_id=first,
                outer_generations="5",
                evaluation_games="1000",
            ),
            TrainingKind.MATCHUP_EVALUATION: TrainingDraft(
                deck_id=first,
                opponent_deck_id=second,
            ),
            TrainingKind.DECK_BUILDER: TrainingDraft(
                evaluator_generations="50",
            ),
        }
        for kind, draft in self.drafts.items():
            draft.run_label = default_run_label(kind, draft)
        self.kind = TrainingKind.PLAYER_DECK

    @property
    def draft(self) -> TrainingDraft:
        return self.drafts[self.kind]

    @property
    def field_keys(self) -> tuple[str, ...]:
        if self.kind == TrainingKind.PLAYER_DECK:
            return COUNTER_FIELDS
        if self.kind == TrainingKind.MATCHUP_EVALUATION:
            return MATCHUP_FIELDS
        return BUILDER_FIELDS

    @property
    def preset_label(self) -> str:
        index = self.draft.preset_index
        options = presets_for(self.kind)
        return options[index].label if index is not None and index < len(options) else "Custom"

    def switch(self, kind: TrainingKind) -> None:
        self.kind = kind

    def value(self, key: str) -> str:
        return str(getattr(self.draft, key))

    def set_value(self, key: str, value: str, *, user_edit: bool = True) -> None:
        if key not in self.field_keys:
            raise KeyError(key)
        setattr(self.draft, key, str(value))
        if key == "run_label":
            if user_edit:
                self.draft.auto_run_label = False
            return
        if user_edit and key in PRESET_FIELDS:
            self.draft.preset_index = None
        if self.draft.auto_run_label:
            self.draft.run_label = default_run_label(self.kind, self.draft)

    def apply_preset(self, index: int | None) -> None:
        if index is None:
            self.draft.preset_index = None
            return
        preset = presets_for(self.kind)[index]
        self.draft.evaluator_generations = str(preset.generations)
        self.draft.workers = str(preset.workers)
        self.draft.evaluation_games = str(preset.evaluation_games)
        self.draft.outer_generations = str(preset.outer_generations)
        self.draft.matches_per_genome = str(preset.matches_per_genome)
        self.draft.holdout_seed_pairs = str(preset.holdout_seed_pairs)
        if self.kind == TrainingKind.DECK_BUILDER:
            seed_sets = (
                (104729,),
                (400009,),
                (400009, 450001, 500009, 550007),
            )
            self.draft.seeds = ", ".join(map(str, seed_sets[preset.seed_set_index]))
        self.draft.preset_index = index
        if self.draft.auto_run_label:
            self.draft.run_label = default_run_label(self.kind, self.draft)

    def cycle_deck(self, key: str, direction: int = 1) -> None:
        if key not in {"deck_id", "opponent_deck_id"} or not self.deck_ids:
            return
        current = self.value(key)
        try:
            index = self.deck_ids.index(current)
        except ValueError:
            index = 0
        self.set_value(key, self.deck_ids[(index + direction) % len(self.deck_ids)])

    def step_integer(self, key: str, direction: int) -> None:
        try:
            current = int(self.value(key).strip())
        except ValueError:
            return
        step = 2 if key == "matches_per_genome" else 1
        self.set_value(key, str(current + direction * step))

    @staticmethod
    def _integer(
        raw: str,
        key: str,
        label: str,
        minimum: int,
        maximum: int,
        errors: dict[str, str],
        *,
        even: bool = False,
    ) -> int | None:
        try:
            value = int(raw.strip())
        except (TypeError, ValueError):
            errors[key] = f"{label} must be an integer"
            return None
        if not minimum <= value <= maximum:
            errors[key] = f"Use {minimum:,}–{maximum:,}"
            return None
        if even and value % 2:
            errors[key] = "Use an even number"
            return None
        return value

    @staticmethod
    def _seeds(raw: str, errors: dict[str, str]) -> tuple[int, ...] | None:
        parts = [part.strip() for part in raw.split(",")]
        if not parts or any(not part for part in parts):
            errors["seeds"] = "Enter one or more comma-separated integers"
            return None
        try:
            return tuple(int(part) for part in parts)
        except ValueError:
            errors["seeds"] = "Every seed must be an integer"
            return None

    def validate(self) -> CockpitValidation:
        draft = self.draft
        errors: dict[str, str] = {}
        label = draft.run_label.strip()
        if not label:
            errors["run_label"] = "Run label cannot be empty"
        elif len(label) > 64:
            errors["run_label"] = "Use at most 64 characters"

        generations = self._integer(
            draft.evaluator_generations,
            "evaluator_generations",
            "Generations",
            2 if self.kind == TrainingKind.MATCHUP_EVALUATION else 1,
            10_000,
            errors,
        )
        workers = self._integer(
            draft.workers,
            "workers",
            "Workers",
            1,
            128,
            errors,
        )

        if self.kind in {TrainingKind.PLAYER_DECK, TrainingKind.MATCHUP_EVALUATION}:
            if not self.deck_ids:
                errors["deck_id"] = "Create a deck before training"
                if self.kind == TrainingKind.MATCHUP_EVALUATION:
                    errors["opponent_deck_id"] = "Create a deck before training"
            else:
                if draft.deck_id not in self.deck_ids:
                    errors["deck_id"] = "Select an existing deck"
                if (
                    self.kind == TrainingKind.MATCHUP_EVALUATION
                    and draft.opponent_deck_id not in self.deck_ids
                ):
                    errors["opponent_deck_id"] = "Select an existing opponent deck"
            evaluation_games = self._integer(
                draft.evaluation_games,
                "evaluation_games",
                "Games per checkpoint",
                2,
                100_000,
                errors,
                even=True,
            )
            outer = 1
            if self.kind == TrainingKind.PLAYER_DECK:
                outer = self._integer(
                    draft.outer_generations,
                    "outer_generations",
                    "Counter generations",
                    1,
                    1_000,
                    errors,
                )
            if errors:
                return CockpitValidation(errors, None)
            request = TrainingRequest(
                kind=self.kind,
                run_label=label,
                deck_id=draft.deck_id,
                opponent_deck_id=(
                    draft.opponent_deck_id
                    if self.kind == TrainingKind.MATCHUP_EVALUATION
                    else None
                ),
                outer_generations=outer,
                evaluator_generations=generations,
                workers=workers,
                evaluation_games=evaluation_games,
            )
        else:
            seeds = self._seeds(draft.seeds, errors)
            outer = self._integer(
                draft.outer_generations,
                "outer_generations",
                "Outer generations",
                1,
                1_000,
                errors,
            )
            matches = self._integer(
                draft.matches_per_genome,
                "matches_per_genome",
                "Rival decks per candidate",
                2,
                10_000,
                errors,
                even=True,
            )
            holdout = self._integer(
                draft.holdout_seed_pairs,
                "holdout_seed_pairs",
                "Holdout seed pairs",
                1,
                10_000,
                errors,
            )
            if errors:
                return CockpitValidation(errors, None)
            request = TrainingRequest(
                kind=self.kind,
                run_label=label,
                seeds=seeds,
                outer_generations=outer,
                matches_per_genome=matches,
                evaluator_generations=generations,
                workers=workers,
                holdout_seed_pairs=holdout,
            )
        try:
            request.validate()
        except ValueError as error:
            errors["request"] = str(error)
            return CockpitValidation(errors, None)
        return CockpitValidation(errors, request)

    def checkpoints(self) -> tuple[int, ...]:
        validation = self.validate()
        if self.kind != TrainingKind.MATCHUP_EVALUATION or validation.request is None:
            return ()
        return matchup_checkpoints(validation.request.evaluator_generations)

    def workload(self):
        validation = self.validate()
        return training_workload(validation.request) if validation.request else None


@dataclass(frozen=True)
class CockpitLayout:
    mode: str
    header: RectSpec
    viewport: RectSpec
    panels: dict[str, RectSpec]
    controls: dict[str, RectSpec]
    section_scroll: dict[str, int] = field(default_factory=dict)
    max_scroll: int = 0


def _columns(area: RectSpec, weights: tuple[int, ...], gap: int) -> list[RectSpec]:
    usable = area.width - gap * (len(weights) - 1)
    total = sum(weights)
    widths = [usable * weight // total for weight in weights]
    widths[-1] += usable - sum(widths)
    result = []
    x = area.x
    for width in widths:
        result.append(RectSpec(x, area.y, width, area.height))
        x += width + gap
    return result


def training_cockpit_layout(
    metrics: LayoutMetrics,
    kind: TrainingKind,
    *,
    scroll: int = 0,
) -> CockpitLayout:
    """Return cockpit panels and hit targets for wide and compact windows."""
    margin = metrics.margin
    gap = max(8, metrics.gap)
    header_height = max(72, metrics.font_large + metrics.font_small + gap * 2)
    header = RectSpec(margin, margin // 2, metrics.width - margin * 2, header_height)
    body_y = header.bottom + gap
    body = RectSpec(
        margin,
        body_y,
        metrics.width - margin * 2,
        max(1, metrics.height - body_y - margin),
    )
    if metrics.width >= 1200:
        return _wide_layout(metrics, kind, header, body, gap)
    return _compact_layout(metrics, kind, header, body, gap, scroll)


def _wide_layout(metrics, kind, header, body, gap):
    rail_width = min(286, max(205, body.width * 19 // 100))
    summary_width = min(388, max(270, body.width * 25 // 100))
    center_width = body.width - rail_width - summary_width - gap * 2
    rail = RectSpec(body.x, body.y, rail_width, body.height)
    center = RectSpec(rail.right + gap, body.y, center_width, body.height)
    summary = RectSpec(center.right + gap, body.y, summary_width, body.height)
    config_ratio = 64 if kind == TrainingKind.DECK_BUILDER else 59
    config_height = max(280, (center.height - gap) * config_ratio // 100)
    config = RectSpec(center.x, center.y, center.width, config_height)
    evidence = RectSpec(center.x, config.bottom + gap, center.width, center.bottom - config.bottom - gap)
    panels = {"rail": rail, "config": config, "evidence": evidence, "summary": summary}
    controls: dict[str, RectSpec] = {}
    target = max(36, min(44, metrics.target_height))
    pad = max(12, gap)

    rail_inner = rail.inset(pad)
    y = rail_inner.y + 52
    for key in ("mission_counter", "mission_matchup", "mission_builder"):
        controls[key] = RectSpec(rail_inner.x, y, rail_inner.width, target)
        y += target + 8
    bottom_y = rail_inner.bottom - target
    controls["runs"] = RectSpec(rail_inner.x, bottom_y, rail_inner.width, target)
    bottom_y -= target + 8
    controls["back"] = RectSpec(rail_inner.x, bottom_y, rail_inner.width, target)
    bottom_y -= target + 8
    controls["about"] = RectSpec(rail_inner.x, bottom_y, rail_inner.width, target)

    inner = config.inset(pad)
    chip_y = inner.y + 58
    chip_gap = 8
    chip_width = (inner.width - chip_gap * 3) // 4
    for index in range(4):
        controls[f"preset_{index}"] = RectSpec(
            inner.x + index * (chip_width + chip_gap), chip_y, chip_width, target
        )
    field_top = chip_y + target + 28
    row_height = max(62, target + 22)
    if kind == TrainingKind.MATCHUP_EVALUATION:
        row = RectSpec(inner.x, field_top, inner.width, row_height)
        left, right = _columns(row, (1, 1), gap)
        controls["run_label"] = RectSpec(left.x, left.y + 18, left.width, target)
        controls["deck_id"] = RectSpec(right.x, right.y + 18, right.width, target)
        row = RectSpec(inner.x, field_top + row_height + 6, inner.width, row_height)
        opponent, generations, workers = _columns(row, (2, 1, 1), gap)
        controls["opponent_deck_id"] = RectSpec(opponent.x, opponent.y + 18, opponent.width, target)
        controls["evaluator_generations"] = RectSpec(generations.x, generations.y + 18, generations.width, target)
        controls["workers"] = RectSpec(workers.x, workers.y + 18, workers.width, target)

        evidence_inner = evidence.inset(pad)
        row = RectSpec(evidence_inner.x, evidence_inner.y + 66, evidence_inner.width, row_height)
        games, checkpoints, decks = _columns(row, (1, 1, 1), gap)
        controls["evaluation_games"] = RectSpec(games.x, games.y + 18, games.width, target)
        controls["checkpoint_display"] = RectSpec(checkpoints.x, checkpoints.y + 18, checkpoints.width, target)
        controls["deck_status"] = RectSpec(decks.x, decks.y + 18, decks.width, target)
    elif kind == TrainingKind.PLAYER_DECK:
        row = RectSpec(inner.x, field_top, inner.width, row_height)
        left, right = _columns(row, (1, 1), gap)
        controls["run_label"] = RectSpec(left.x, left.y + 18, left.width, target)
        controls["deck_id"] = RectSpec(right.x, right.y + 18, right.width, target)
        row = RectSpec(inner.x, field_top + row_height + 6, inner.width, row_height)
        outer, controller, workers = _columns(row, (1, 1, 1), gap)
        controls["outer_generations"] = RectSpec(outer.x, outer.y + 18, outer.width, target)
        controls["evaluator_generations"] = RectSpec(controller.x, controller.y + 18, controller.width, target)
        controls["workers"] = RectSpec(workers.x, workers.y + 18, workers.width, target)

        evidence_inner = evidence.inset(pad)
        row = RectSpec(evidence_inner.x, evidence_inner.y + 66, evidence_inner.width, row_height)
        games, persistence, pool = _columns(row, (1, 1, 1), gap)
        controls["evaluation_games"] = RectSpec(games.x, games.y + 18, games.width, target)
        controls["persistence_display"] = RectSpec(persistence.x, persistence.y + 18, persistence.width, target)
        controls["counter_pool"] = RectSpec(pool.x, pool.y + 18, pool.width, target)
    else:
        row = RectSpec(inner.x, field_top, inner.width, row_height)
        left, right = _columns(row, (1, 1), gap)
        controls["run_label"] = RectSpec(left.x, left.y + 18, left.width, target)
        controls["seeds"] = RectSpec(right.x, right.y + 18, right.width, target)
        row = RectSpec(inner.x, field_top + row_height + 4, inner.width, row_height)
        outer, inner_gen, matches = _columns(row, (1, 1, 1), gap)
        controls["outer_generations"] = RectSpec(outer.x, outer.y + 18, outer.width, target)
        controls["evaluator_generations"] = RectSpec(inner_gen.x, inner_gen.y + 18, inner_gen.width, target)
        controls["matches_per_genome"] = RectSpec(matches.x, matches.y + 18, matches.width, target)
        row = RectSpec(inner.x, field_top + (row_height + 4) * 2, inner.width, row_height)
        workers, holdout = _columns(row, (1, 1), gap)
        controls["workers"] = RectSpec(workers.x, workers.y + 18, workers.width, target)
        controls["holdout_seed_pairs"] = RectSpec(holdout.x, holdout.y + 18, holdout.width, target)

    controls["launch"] = RectSpec(
        summary.x + pad,
        summary.bottom - pad - target,
        summary.width - pad * 2,
        target,
    )
    viewport = RectSpec(body.x, body.y, body.width, body.height)
    return CockpitLayout("wide", header, viewport, panels, controls)


def _compact_layout(metrics, kind, header, body, gap, scroll):
    footer_height = max(50, metrics.target_height + gap)
    viewport = RectSpec(body.x, body.y, body.width, max(1, body.height - footer_height - gap))
    content_width = body.width
    pad = max(12, gap)
    target = max(42, min(48, metrics.target_height))
    controls: dict[str, RectSpec] = {}
    panels: dict[str, RectSpec] = {}
    logical_y = viewport.y

    toolbar_height = target * 3 + gap * 4 + 34
    rail = RectSpec(body.x, logical_y, content_width, toolbar_height)
    panels["rail"] = rail
    y = rail.y + 30
    for key in ("mission_counter", "mission_matchup", "mission_builder"):
        controls[key] = RectSpec(rail.x + pad, y, rail.width - pad * 2, target)
        y += target + gap
    logical_y = rail.bottom + gap
    section_scroll = {"mission": 0, "configuration": logical_y - viewport.y}

    field_rows = len(
        COUNTER_FIELDS
        if kind == TrainingKind.PLAYER_DECK
        else MATCHUP_FIELDS
        if kind == TrainingKind.MATCHUP_EVALUATION
        else BUILDER_FIELDS
    )
    config_height = 74 + target * 2 + gap + field_rows * (target + 30) + pad * 2
    config = RectSpec(body.x, logical_y, content_width, config_height)
    panels["config"] = config
    inner = config.inset(pad)
    chip_y = inner.y + 54
    chip_gap = max(4, gap // 2)
    chip_width = (inner.width - chip_gap) // 2
    for index in range(4):
        controls[f"preset_{index}"] = RectSpec(
            inner.x + (index % 2) * (chip_width + chip_gap),
            chip_y + (index // 2) * (target + chip_gap),
            chip_width,
            target,
        )
    y = chip_y + target * 2 + chip_gap + 20
    field_keys = (
        COUNTER_FIELDS
        if kind == TrainingKind.PLAYER_DECK
        else MATCHUP_FIELDS
        if kind == TrainingKind.MATCHUP_EVALUATION
        else BUILDER_FIELDS
    )
    for key in field_keys:
        controls[key] = RectSpec(inner.x, y + 18, inner.width, target)
        y += target + 30
    logical_y = config.bottom + gap
    section_scroll["evidence"] = logical_y - viewport.y

    evidence_height = 205 if kind != TrainingKind.DECK_BUILDER else 190
    evidence = RectSpec(body.x, logical_y, content_width, evidence_height)
    panels["evidence"] = evidence
    if kind == TrainingKind.MATCHUP_EVALUATION:
        inner = evidence.inset(pad)
        controls["checkpoint_display"] = RectSpec(inner.x, inner.y + 66, inner.width, target)
        controls["deck_status"] = RectSpec(inner.x, inner.y + 66 + target + gap, inner.width, target)
    elif kind == TrainingKind.PLAYER_DECK:
        inner = evidence.inset(pad)
        controls["persistence_display"] = RectSpec(inner.x, inner.y + 66, inner.width, target)
        controls["counter_pool"] = RectSpec(inner.x, inner.y + 66 + target + gap, inner.width, target)
    logical_y = evidence.bottom + gap
    section_scroll["preflight"] = logical_y - viewport.y

    summary_height = 420 if kind != TrainingKind.DECK_BUILDER else 400
    summary = RectSpec(body.x, logical_y, content_width, summary_height)
    panels["summary"] = summary
    logical_y = summary.bottom + gap
    action_height = target + gap * 2
    actions = RectSpec(body.x, logical_y, content_width, action_height)
    panels["actions"] = actions
    action_inner = actions.inset(gap)
    about, runs, back = _columns(action_inner, (1, 1, 1), max(4, gap // 2))
    controls["about"] = about
    controls["runs"] = runs
    controls["back"] = back
    logical_y = actions.bottom

    max_scroll = max(0, logical_y - viewport.bottom)
    scroll = max(0, min(int(scroll), max_scroll))
    offset = -scroll
    shifted_panels = {
        key: RectSpec(rect.x, rect.y + offset, rect.width, rect.height)
        for key, rect in panels.items()
    }
    shifted_controls = {
        key: RectSpec(rect.x, rect.y + offset, rect.width, rect.height)
        for key, rect in controls.items()
    }
    shifted_controls["launch"] = RectSpec(
        body.x,
        viewport.bottom + gap,
        body.width,
        footer_height - gap,
    )
    return CockpitLayout(
        "compact",
        header,
        viewport,
        shifted_panels,
        shifted_controls,
        section_scroll,
        max_scroll,
    )
