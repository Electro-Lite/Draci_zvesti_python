from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path


DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parents[1] / ".ui_settings.json"


@dataclass
class AppSettings:
    width: int = 1280
    height: int = 720
    fullscreen: bool = False
    master_volume: int = 70
    ai_delay_ms: int = 350
    show_tooltips: bool = True
    player_name: str = "Player"
    lan_port: int = 47777
    last_join_host: str = "127.0.0.1"

    def validate(self) -> None:
        if type(self.width) is not int or not 640 <= self.width <= 7680:
            raise ValueError("Window width must be between 640 and 7680")
        if type(self.height) is not int or not 480 <= self.height <= 4320:
            raise ValueError("Window height must be between 480 and 4320")
        if not isinstance(self.fullscreen, bool):
            raise ValueError("Fullscreen must be enabled or disabled")
        if type(self.master_volume) is not int or not 0 <= self.master_volume <= 100:
            raise ValueError("Master volume must be between 0 and 100")
        if type(self.ai_delay_ms) is not int or not 0 <= self.ai_delay_ms <= 5000:
            raise ValueError("AI delay must be between 0 and 5000 ms")
        if not isinstance(self.show_tooltips, bool):
            raise ValueError("Tooltips must be enabled or disabled")
        if (
            not isinstance(self.player_name, str)
            or not self.player_name.strip()
            or len(self.player_name.strip()) > 24
        ):
            raise ValueError("Player name must contain 1-24 characters")
        if type(self.lan_port) is not int or not 1024 <= self.lan_port <= 65535:
            raise ValueError("LAN port must be between 1024 and 65535")
        if (
            not isinstance(self.last_join_host, str)
            or not self.last_join_host.strip()
            or len(self.last_join_host) > 253
        ):
            raise ValueError("Join host must contain 1-253 characters")


class SettingsStore:
    def __init__(self, path: str | Path = DEFAULT_SETTINGS_PATH):
        self.path = Path(path)

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            allowed = {item.name for item in fields(AppSettings)}
            settings = AppSettings(**{key: value for key, value in raw.items() if key in allowed})
            settings.validate()
            return settings
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        settings.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temp_file:
                json.dump(asdict(settings), temp_file, indent=2, sort_keys=True)
                temp_file.write("\n")
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_name, self.path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
