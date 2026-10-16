from __future__ import annotations

from pathlib import Path

import pygame as pg


class AssetCache:
    def __init__(self):
        self._source: dict[str, pg.Surface] = {}
        self._scaled: dict[tuple[str, int, int], pg.Surface] = {}
        self._covered: dict[tuple[str, int, int], pg.Surface] = {}
        self._tinted_covered: dict[
            tuple[str, int, int, tuple[int, int, int]], pg.Surface
        ] = {}

    def image(
        self,
        path: str | Path | None,
        size: tuple[int, int],
    ) -> pg.Surface:
        width, height = max(1, int(size[0])), max(1, int(size[1]))
        key = str(path) if path else "//placeholder:missing-card-art"
        scaled_key = (key, width, height)
        if scaled_key in self._scaled:
            return self._scaled[scaled_key]
        source = self._load_source(path)
        result = pg.transform.smoothscale(source, (width, height))
        self._scaled[scaled_key] = result
        return result

    def cover(
        self,
        path: str | Path | None,
        size: tuple[int, int],
    ) -> pg.Surface:
        """Scale an image proportionally and center-crop it to fill ``size``."""
        width, height = max(1, int(size[0])), max(1, int(size[1]))
        key = str(path) if path else "//placeholder:missing-background-art"
        covered_key = (key, width, height)
        if covered_key in self._covered:
            return self._covered[covered_key]
        source = self._load_source(path)
        source_width, source_height = source.get_size()
        scale = max(width / source_width, height / source_height)
        scaled_size = (
            max(width, round(source_width * scale)),
            max(height, round(source_height * scale)),
        )
        scaled = pg.transform.smoothscale(source, scaled_size)
        result = pg.Surface((width, height), pg.SRCALPHA)
        result.blit(
            scaled,
            ((width - scaled_size[0]) // 2, (height - scaled_size[1]) // 2),
        )
        self._covered[covered_key] = result
        return result

    def tinted_cover(
        self,
        path: str | Path | None,
        size: tuple[int, int],
        color: tuple[int, int, int],
    ) -> pg.Surface:
        """Return a cached colorized copy while preserving per-pixel alpha."""
        width, height = max(1, int(size[0])), max(1, int(size[1]))
        key = str(path) if path else "//placeholder:missing-background-art"
        tint = tuple(max(0, min(255, int(channel))) for channel in color)
        tinted_key = (key, width, height, tint)
        if tinted_key not in self._tinted_covered:
            result = self.cover(path, (width, height)).copy()
            result.fill((*tint, 255), special_flags=pg.BLEND_RGBA_MULT)
            self._tinted_covered[tinted_key] = result
        return self._tinted_covered[tinted_key]

    def _load_source(self, path: str | Path | None) -> pg.Surface:
        key = str(path) if path else "//placeholder:missing-card-art"
        if key in self._source:
            return self._source[key]
        try:
            if path is None:
                raise FileNotFoundError
            source = pg.image.load(str(path)).convert_alpha()
        except (FileNotFoundError, OSError, pg.error):
            # //placeholder: replace generated fallback when final artwork is supplied.
            source = pg.Surface((500, 700), pg.SRCALPHA)
            source.fill((52, 59, 72))
            pg.draw.rect(source, (116, 130, 148), source.get_rect(), 16)
            pg.draw.line(source, (116, 130, 148), (70, 90), (430, 610), 16)
            pg.draw.line(source, (116, 130, 148), (430, 90), (70, 610), 16)
        self._source[key] = source
        return source

    def clear_scaled(self) -> None:
        self._scaled.clear()
        self._covered.clear()
        self._tinted_covered.clear()
