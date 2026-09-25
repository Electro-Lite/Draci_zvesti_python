from __future__ import annotations

import time
from collections.abc import Callable

from display_strategies.display_strategy_none import DisplayStrategyNone


def wait_for_battle_frame(
    seconds: float,
    cancelled: Callable[[], bool] | None = None,
) -> None:
    """Keep a battle frame visible while remaining quick to cancel."""
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        if cancelled is not None and cancelled():
            raise SystemExit
        time.sleep(min(0.03, max(0.0, deadline - time.monotonic())))


def wait_for_battle_confirmation(
    continue_requested: Callable[[], bool],
    cancelled: Callable[[], bool] | None = None,
) -> None:
    """Hold the final battle frame without blocking the responsive UI thread."""
    while not continue_requested():
        if cancelled is not None and cancelled():
            raise SystemExit
        time.sleep(0.03)


def local_battle_display_strategy(
    frame_seconds: float,
    cancelled: Callable[[], bool] | None = None,
    continue_requested: Callable[[], bool] | None = None,
    reset_continue: Callable[[], None] | None = None,
):
    """Create a no-I/O display strategy that paces visible battle states."""

    class LocalBattleDisplayStrategy(DisplayStrategyNone):
        def _battle_frame(self):
            wait_for_battle_frame(frame_seconds, cancelled)

        def _battle_result(self):
            if continue_requested is None:
                wait_for_battle_frame(frame_seconds, cancelled)
                return
            wait_for_battle_confirmation(continue_requested, cancelled)
            if reset_continue is not None:
                reset_continue()

        display_dragon = _battle_frame
        display_dragon_vs_card = _battle_frame
        display_battle_result = _battle_result

    return LocalBattleDisplayStrategy
