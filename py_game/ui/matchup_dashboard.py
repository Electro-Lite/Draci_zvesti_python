"""Responsive geometry for the fixed-deck matchup Training Arena."""

from __future__ import annotations

from dataclasses import dataclass

from py_game.ui.layout import LayoutMetrics, RectSpec


@dataclass(frozen=True)
class MatchupDashboardLayout:
    mode: str
    viewport: RectSpec
    decks: RectSpec
    checkpoints: RectSpec
    reading: RectSpec
    footer: RectSpec
    max_scroll: int


def matchup_dashboard_layout(
    metrics: LayoutMetrics,
    *,
    deck_rows: int,
    checkpoint_rows: int,
    scroll: int = 0,
) -> MatchupDashboardLayout:
    """Return wide columns or compact stacked sections with one scroll axis."""
    header_bottom = metrics.margin + metrics.font_large + metrics.font_small + metrics.gap * 3
    footer_height = metrics.target_height
    viewport = RectSpec(
        metrics.margin,
        header_bottom,
        metrics.width - metrics.margin * 2,
        max(1, metrics.height - header_bottom - footer_height - metrics.margin - metrics.gap),
    )
    footer = RectSpec(
        metrics.margin,
        metrics.height - metrics.margin - footer_height,
        metrics.width - metrics.margin * 2,
        footer_height,
    )
    line_height = max(18, metrics.font_small + 3)
    deck_height = max(550, 450 + max(2, deck_rows) * line_height)
    checkpoint_height = max(
        410,
        90 + max(1, checkpoint_rows) * max(76, metrics.target_height + metrics.gap * 2) + 150,
    )
    reading_height = max(560, 23 * line_height + metrics.gap * 5)
    mode = "wide" if metrics.width >= 1050 else "compact"
    if mode == "wide":
        left, center, right = metrics.columns(viewport, (0.27, 0.46, 0.27))
        content_height = max(deck_height, checkpoint_height, reading_height, viewport.height)
        max_scroll = max(0, content_height - viewport.height)
        offset = min(max(0, scroll), max_scroll)
        return MatchupDashboardLayout(
            mode,
            viewport,
            RectSpec(left.x, left.y - offset, left.width, deck_height),
            RectSpec(center.x, center.y - offset, center.width, checkpoint_height),
            RectSpec(right.x, right.y - offset, right.width, reading_height),
            footer,
            max_scroll,
        )

    section_gap = metrics.gap
    content_height = deck_height + checkpoint_height + reading_height + section_gap * 2
    max_scroll = max(0, content_height - viewport.height)
    offset = min(max(0, scroll), max_scroll)
    y = viewport.y - offset
    decks = RectSpec(viewport.x, y, viewport.width, deck_height)
    checkpoints = RectSpec(
        viewport.x, decks.bottom + section_gap, viewport.width, checkpoint_height
    )
    reading = RectSpec(
        viewport.x, checkpoints.bottom + section_gap, viewport.width, reading_height
    )
    return MatchupDashboardLayout(
        mode, viewport, decks, checkpoints, reading, footer, max_scroll
    )
