"""Responsive geometry for the counter-deck Training Arena."""

from __future__ import annotations

from dataclasses import dataclass

from py_game.ui.layout import LayoutMetrics, RectSpec


@dataclass(frozen=True)
class CounterDashboardLayout:
    mode: str
    viewport: RectSpec
    subject: RectSpec
    result: RectSpec
    candidates: RectSpec
    counter: RectSpec
    footer: RectSpec
    max_scroll: int


def counter_dashboard_layout(
    metrics: LayoutMetrics,
    *,
    subject_rows: int,
    counter_rows: int,
    scroll: int = 0,
) -> CounterDashboardLayout:
    header_bottom = metrics.margin + metrics.font_large + metrics.font_small + metrics.gap * 3
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
    line_height = max(21, metrics.font_small + 5)
    subject_height = max(500, 300 + subject_rows * line_height)
    counter_height = max(500, 250 + counter_rows * line_height)
    # The evidence panel carries both the selected result and the complete run-
    # depth explanation.  Keep enough breathing room that the pooled-result
    # disclaimer never collides with the lower border at intermediate widths.
    result_height = max(520, 23 * line_height)
    candidates_height = max(330, 13 * line_height)
    mode = "wide" if metrics.width >= 1050 else "compact"
    if mode == "wide":
        left, center, right = metrics.columns(viewport, (0.28, 0.44, 0.28))
        center_height = result_height + metrics.gap + candidates_height
        content_height = max(subject_height, center_height, counter_height, viewport.height)
        max_scroll = max(0, content_height - viewport.height)
        offset = min(max(0, scroll), max_scroll)
        subject = RectSpec(left.x, left.y - offset, left.width, subject_height)
        result = RectSpec(center.x, center.y - offset, center.width, result_height)
        candidates = RectSpec(
            center.x, result.bottom + metrics.gap, center.width, candidates_height
        )
        counter = RectSpec(right.x, right.y - offset, right.width, counter_height)
        return CounterDashboardLayout(
            mode, viewport, subject, result, candidates, counter, footer, max_scroll
        )

    content_height = (
        subject_height
        + result_height
        + candidates_height
        + counter_height
        + metrics.gap * 3
    )
    max_scroll = max(0, content_height - viewport.height)
    offset = min(max(0, scroll), max_scroll)
    y = viewport.y - offset
    subject = RectSpec(viewport.x, y, viewport.width, subject_height)
    result = RectSpec(viewport.x, subject.bottom + metrics.gap, viewport.width, result_height)
    candidates = RectSpec(viewport.x, result.bottom + metrics.gap, viewport.width, candidates_height)
    counter = RectSpec(viewport.x, candidates.bottom + metrics.gap, viewport.width, counter_height)
    return CounterDashboardLayout(
        mode, viewport, subject, result, candidates, counter, footer, max_scroll
    )
