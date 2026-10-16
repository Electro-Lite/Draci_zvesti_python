"""Responsive shell for the five completed Deck Evolution result pages."""

from __future__ import annotations

from dataclasses import dataclass

from py_game.ui.layout import LayoutMetrics, RectSpec


@dataclass(frozen=True)
class EvolutionDashboardLayout:
    mode: str
    viewport: RectSpec
    navigation: RectSpec
    content: RectSpec
    footer: RectSpec
    max_scroll: int


def evolution_dashboard_layout(
    metrics: LayoutMetrics,
    *,
    content_height: int,
    scroll: int = 0,
) -> EvolutionDashboardLayout:
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
    if metrics.width >= 1050:
        navigation_width = max(210, viewport.width * 16 // 100)
        navigation = RectSpec(
            viewport.x, viewport.y, navigation_width, viewport.height
        )
        content_view = RectSpec(
            navigation.right + metrics.gap,
            viewport.y,
            viewport.width - navigation.width - metrics.gap,
            viewport.height,
        )
        max_scroll = max(0, content_height - content_view.height)
        offset = min(max(0, scroll), max_scroll)
        content = RectSpec(
            content_view.x,
            content_view.y - offset,
            content_view.width,
            max(content_view.height, content_height),
        )
        return EvolutionDashboardLayout(
            "wide", content_view, navigation, content, footer, max_scroll
        )

    navigation_height = max(metrics.target_height * 2, 96)
    navigation = RectSpec(
        viewport.x, viewport.y, viewport.width, navigation_height
    )
    content_view = RectSpec(
        viewport.x,
        navigation.bottom + metrics.gap,
        viewport.width,
        max(1, viewport.height - navigation.height - metrics.gap),
    )
    max_scroll = max(0, content_height - content_view.height)
    offset = min(max(0, scroll), max_scroll)
    content = RectSpec(
        content_view.x,
        content_view.y - offset,
        content_view.width,
        max(content_view.height, content_height),
    )
    return EvolutionDashboardLayout(
        "compact", content_view, navigation, content, footer, max_scroll
    )
