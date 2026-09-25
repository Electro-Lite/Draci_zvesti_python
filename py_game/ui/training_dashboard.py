from __future__ import annotations

from py_game.ui.layout import LayoutMetrics, RectSpec


def training_dashboard_layout(metrics: LayoutMetrics) -> dict[str, RectSpec]:
    """Return responsive, non-overlapping regions for the Training Arena."""
    title_bottom = metrics.margin + metrics.font_large + metrics.font_small + metrics.gap * 3
    footer_height = metrics.target_height + metrics.gap
    tabs = RectSpec(
        metrics.margin,
        title_bottom,
        metrics.width - metrics.margin * 2,
        metrics.target_height,
    )
    content = RectSpec(
        metrics.margin,
        tabs.bottom + metrics.gap,
        metrics.width - metrics.margin * 2,
        max(1, metrics.height - tabs.bottom - metrics.gap - footer_height - metrics.margin),
    )
    top_height = max(1, int((content.height - metrics.gap) * 0.62))
    top = RectSpec(content.x, content.y, content.width, top_height)
    bottom = RectSpec(
        content.x,
        top.bottom + metrics.gap,
        content.width,
        max(1, content.bottom - top.bottom - metrics.gap),
    )
    hero, trail = metrics.columns(top, (0.36, 0.64))
    return {
        "tabs": tabs,
        "content": content,
        "hero": hero,
        "trail": trail,
        "systems": bottom,
        "footer": RectSpec(
            metrics.margin,
            metrics.height - metrics.margin - metrics.target_height,
            metrics.width - metrics.margin * 2,
            metrics.target_height,
        ),
    }
