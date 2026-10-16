"""PyInstaller entry point for the Windows distribution.

The normal UI starts without command-line arguments.  UI training currently
launches ``sys.executable -m neat_ai.<trainer>``; in a frozen application
``sys.executable`` is this executable, so this small dispatcher preserves that
existing contract without changing the project layout.
"""

from __future__ import annotations

import multiprocessing
import os
import runpy
import sys
from pathlib import Path


TRAINING_MODULES = {
    "neat_ai.deck_builder_trainer",
    "neat_ai.matchup_trainer",
    "neat_ai.player_trainer",
}


def _enter_bundle_root() -> None:
    """Make existing project-relative data paths work in an onedir bundle."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        os.chdir(Path(bundle_root))
        return

    # Also allow this packaging entry point to be exercised directly from a
    # source checkout, where sys.path would otherwise start at packager/.
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def _run_training_module() -> bool:
    if len(sys.argv) < 3 or sys.argv[1] != "-m":
        return False
    module_name = sys.argv[2]
    if module_name not in TRAINING_MODULES:
        raise SystemExit(f"Unsupported packaged module: {module_name}")
    sys.argv = [module_name, *sys.argv[3:]]
    runpy.run_module(module_name, run_name="__main__", alter_sys=True)
    return True


def main() -> None:
    _enter_bundle_root()
    # Required when trainers create multiprocessing workers in a frozen app.
    multiprocessing.freeze_support()
    if _run_training_module():
        return

    from py_game.main import main as game_main

    game_main()


if __name__ == "__main__":
    main()
