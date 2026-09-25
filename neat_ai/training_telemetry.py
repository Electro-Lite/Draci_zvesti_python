"""Structured, append-only progress events shared by command-line trainers."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path


TELEMETRY_ENV = "TRAINING_TELEMETRY_PATH"
SCHEMA_VERSION = 1


def emit_training_event(event: str, **values) -> None:
    """Append one JSONL event when a telemetry destination is configured."""
    destination = os.environ.get(TELEMETRY_ENV)
    if not destination:
        return
    payload = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "event": event,
        **values,
    }
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, sort_keys=True) + "\n")

