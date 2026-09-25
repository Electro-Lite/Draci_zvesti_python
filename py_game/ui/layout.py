from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RectSpec:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def contains(self, position: tuple[int, int]) -> bool:
        px, py = position
        return self.x <= px < self.right and self.y <= py < self.bottom

    def inset(self, amount: int) -> "RectSpec":
        amount = max(0, min(amount, self.width // 2, self.height // 2))
        return RectSpec(
            self.x + amount,
            self.y + amount,
            self.width - amount * 2,
            self.height - amount * 2,
        )


@dataclass(frozen=True)
class LayoutMetrics:
    """Responsive geometry derived from the current drawable size.

    Geometry is calculated from a 1280x720 design surface, while font and
    target sizes are clamped so the UI remains usable in small windows.
    """

    width: int
    height: int
    scale: float
    margin: int
    gap: int
    font_small: int
    font_normal: int
    font_large: int
    target_height: int

    DESIGN_WIDTH = 1280
    DESIGN_HEIGHT = 720
    MIN_WIDTH = 640
    MIN_HEIGHT = 480

    @classmethod
    def from_size(cls, width: int, height: int) -> "LayoutMetrics":
        width = max(cls.MIN_WIDTH, int(width))
        height = max(cls.MIN_HEIGHT, int(height))
        scale = min(width / cls.DESIGN_WIDTH, height / cls.DESIGN_HEIGHT)
        scale = max(0.67, min(scale, 2.0))
        return cls(
            width=width,
            height=height,
            scale=scale,
            margin=max(16, round(28 * scale)),
            gap=max(8, round(14 * scale)),
            font_small=max(13, round(17 * scale)),
            font_normal=max(17, round(23 * scale)),
            font_large=max(28, round(42 * scale)),
            target_height=max(42, round(52 * scale)),
        )

    @property
    def content(self) -> RectSpec:
        return RectSpec(
            self.margin,
            self.margin,
            self.width - self.margin * 2,
            self.height - self.margin * 2,
        )

    def centered_panel(
        self,
        width_ratio: float = 0.72,
        height_ratio: float = 0.82,
        *,
        max_width: int | None = 980,
    ) -> RectSpec:
        panel_width = int(self.width * width_ratio)
        if max_width is not None:
            panel_width = min(panel_width, round(max_width * max(1.0, self.scale)))
        panel_height = min(
            int(self.height * height_ratio),
            self.height - self.margin * 2,
        )
        return RectSpec(
            (self.width - panel_width) // 2,
            (self.height - panel_height) // 2,
            panel_width,
            panel_height,
        )

    def vertical_rows(
        self,
        count: int,
        area: RectSpec,
        *,
        row_height: int | None = None,
        gap: int | None = None,
    ) -> list[RectSpec]:
        if count <= 0:
            return []
        gap = self.gap if gap is None else max(0, gap)
        available = area.height - gap * (count - 1)
        calculated = available // count
        height = min(row_height or self.target_height, calculated)
        height = max(1, height)
        total = height * count + gap * (count - 1)
        start_y = area.y + max(0, (area.height - total) // 2)
        return [
            RectSpec(area.x, start_y + index * (height + gap), area.width, height)
            for index in range(count)
        ]

    def columns(
        self,
        area: RectSpec,
        weights: tuple[float, ...],
        *,
        gap: int | None = None,
    ) -> list[RectSpec]:
        if not weights or any(weight <= 0 for weight in weights):
            raise ValueError("Column weights must be positive")
        gap = self.gap if gap is None else max(0, gap)
        usable = area.width - gap * (len(weights) - 1)
        total_weight = sum(weights)
        widths = [int(usable * weight / total_weight) for weight in weights]
        widths[-1] += usable - sum(widths)
        result = []
        x = area.x
        for width in widths:
            result.append(RectSpec(x, area.y, width, area.height))
            x += width + gap
        return result

    def card_size(
        self,
        area: RectSpec,
        count: int,
        *,
        aspect_ratio: float = 5 / 7,
        minimum_width: int = 42,
    ) -> tuple[int, int, int]:
        """Return card width, card height, and inter-card gap."""
        count = max(1, count)
        gap = max(4, min(self.gap, area.width // (count * 5)))
        width = (area.width - gap * (count - 1)) // count
        width = max(minimum_width, width)
        height = round(width / aspect_ratio)
        if height > area.height:
            height = area.height
            width = round(height * aspect_ratio)
        return width, max(1, height), gap
