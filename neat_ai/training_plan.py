"""Shared, dependency-light planning rules for AI training."""

from __future__ import annotations


def evaluation_checkpoints(generations: int) -> tuple[int, ...]:
    """Return early/developing/mature checkpoints plus a longer final state."""
    checkpoints = [value for value in (10, 25, 40) if value <= generations]
    if generations not in checkpoints:
        checkpoints.append(generations)
    return tuple(sorted(set(checkpoints)))

