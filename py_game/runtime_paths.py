"""Writable runtime paths for source checkouts and packaged applications."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _packaged_data_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "DraciZvesti"


def data_root() -> Path:
    configured = os.environ.get("DRACI_ZVESTI_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return _packaged_data_root() if getattr(sys, "frozen", False) else PROJECT_ROOT


def data_path(*parts: str) -> Path:
    return data_root().joinpath(*parts)


def initialize_packaged_data() -> Path:
    """Create persistent state and seed databases on first packaged launch."""
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    if not getattr(sys, "frozen", False):
        return root

    bundled_utils = PROJECT_ROOT / "utils"
    writable_utils = root / "utils"
    writable_utils.mkdir(parents=True, exist_ok=True)
    for filename in ("cards.db", "decks.db"):
        destination = writable_utils / filename
        if not destination.exists():
            shutil.copy2(bundled_utils / filename, destination)

    (root / ".ui_training").mkdir(parents=True, exist_ok=True)
    (root / "trained_ai").mkdir(parents=True, exist_ok=True)
    os.environ["DRACI_ZVESTI_DATA_DIR"] = str(root)
    os.environ["TRAIN_DB_PATH"] = str(root / "train.db")
    return root
