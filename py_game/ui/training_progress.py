"""Responsive geometry for shared live/completion/terminal Training Arena states."""

from __future__ import annotations

from dataclasses import dataclass

from py_game.ui.layout import LayoutMetrics, RectSpec


@dataclass(frozen=True)
class TrainingProgressLayout:
    mode: str
    viewport: RectSpec
    hero: RectSpec
    levels: RectSpec
    phase: RectSpec
    timing: RectSpec
    events: RectSpec
    footer: RectSpec
    max_scroll: int


def training_progress_layout(
    metrics: LayoutMetrics,
    *,
    scroll: int = 0,
) -> TrainingProgressLayout:
    header_bottom = (
        metrics.margin + metrics.font_large + metrics.font_small + metrics.gap * 3
    )
    footer = RectSpec(
        metrics.margin,
        metrics.height - metrics.margin - metrics.target_height,
        metrics.width - metrics.margin * 2,
        metrics.target_height,
    )
    viewport = RectSpec(
        metrics.margin,
        header_bottom,
        metrics.width - metrics.margin * 2,
        max(1, footer.y - metrics.gap - header_bottom),
    )
    hero_height = max(180, metrics.target_height * 4)
    detail_height = max(260, metrics.target_height * 6)
    events_height = max(190, metrics.target_height * 4)
    compact = metrics.width < 1050
    if not compact:
        columns = metrics.columns(
            RectSpec(
                viewport.x,
                viewport.y + hero_height + metrics.gap,
                viewport.width,
                detail_height,
            ),
            (0.34, 0.33, 0.33),
        )
        content_height = hero_height + metrics.gap + detail_height + metrics.gap + events_height
        max_scroll = max(0, content_height - viewport.height)
        offset = min(max(0, scroll), max_scroll)
        hero = RectSpec(viewport.x, viewport.y - offset, viewport.width, hero_height)
        levels = RectSpec(columns[0].x, columns[0].y - offset, columns[0].width, detail_height)
        phase = RectSpec(columns[1].x, columns[1].y - offset, columns[1].width, detail_height)
        timing = RectSpec(columns[2].x, columns[2].y - offset, columns[2].width, detail_height)
        events = RectSpec(viewport.x, levels.bottom + metrics.gap, viewport.width, events_height)
        return TrainingProgressLayout(
            "wide", viewport, hero, levels, phase, timing, events, footer, max_scroll
        )

    heights = (hero_height, detail_height, detail_height, detail_height, events_height)
    content_height = sum(heights) + metrics.gap * 4
    max_scroll = max(0, content_height - viewport.height)
    offset = min(max(0, scroll), max_scroll)
    y = viewport.y - offset
    sections = []
    for height in heights:
        sections.append(RectSpec(viewport.x, y, viewport.width, height))
        y += height + metrics.gap
    return TrainingProgressLayout(
        "compact",
        viewport,
        sections[0],
        sections[1],
        sections[2],
        sections[3],
        sections[4],
        footer,
        max_scroll,
    )
