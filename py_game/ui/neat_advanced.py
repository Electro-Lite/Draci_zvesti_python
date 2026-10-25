"""State model for the paginated advanced NEAT editor."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from neat_ai.config_profiles import (
    PROFILE_LABELS,
    default_values,
    fields_for_profile,
    load_named_profiles,
    normalize_overrides,
    save_named_profiles,
)
from py_game.runtime_paths import data_path
from py_game.training_service import TrainingKind


NAMED_CONFIG_PATH = data_path(".ui_training", "named_neat_configs.json")
FIELDS_PER_PAGE = 8


def profiles_for_mission(kind: TrainingKind) -> tuple[str, ...]:
    if kind == TrainingKind.MATCHUP_EVALUATION:
        return ("evaluator",)
    return ("builder", "evaluator")


@dataclass
class AdvancedNeatEditor:
    kind: TrainingKind
    initial_overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    profile_index: int = 0
    page: int = 0
    selected: int = 0
    editing_key: str | None = None
    editing_original: str = ""

    def __post_init__(self):
        self.profiles = profiles_for_mission(self.kind)
        normalized = normalize_overrides(self.initial_overrides)
        self.values = {}
        for profile in self.profiles:
            values = default_values(profile)
            values.update(normalized.get(profile, {}))
            self.values[profile] = values

    @property
    def profile(self) -> str:
        return self.profiles[self.profile_index]

    @property
    def profile_label(self) -> str:
        return PROFILE_LABELS[self.profile]

    @property
    def fields(self):
        return fields_for_profile(self.profile)

    @property
    def page_count(self) -> int:
        return max(1, math.ceil(len(self.fields) / FIELDS_PER_PAGE))

    @property
    def page_fields(self):
        start = self.page * FIELDS_PER_PAGE
        return self.fields[start : start + FIELDS_PER_PAGE]

    def switch_profile(self, index: int) -> None:
        self.profile_index = max(0, min(int(index), len(self.profiles) - 1))
        self.page = 0
        self.selected = 0
        self.editing_key = None

    def change_page(self, direction: int) -> None:
        self.page = max(0, min(self.page_count - 1, self.page + int(direction)))
        self.selected = min(self.selected, max(0, len(self.page_fields) - 1))
        self.editing_key = None

    def value(self, key: str) -> str:
        return self.values[self.profile][key]

    def begin_edit(self, key: str) -> bool:
        field = next((item for item in self.fields if item.key == key), None)
        if field is None or field.locked:
            return False
        self.editing_key = key
        self.editing_original = self.value(key)
        return True

    def set_edit_value(self, value: str) -> None:
        if self.editing_key is not None:
            self.values[self.profile][self.editing_key] = value

    def finish_edit(self, *, cancel=False) -> None:
        if self.editing_key is None:
            return
        if cancel:
            self.values[self.profile][self.editing_key] = self.editing_original
        self.editing_key = None
        self.editing_original = ""

    def reset_profile(self) -> None:
        self.values[self.profile] = default_values(self.profile)
        self.editing_key = None

    def _raw_overrides(self) -> dict[str, dict[str, str]]:
        raw = {}
        for profile in self.profiles:
            defaults = default_values(profile)
            changed = {
                key: value
                for key, value in self.values[profile].items()
                if value != defaults[key]
            }
            if changed:
                raw[profile] = changed
        return raw

    def overrides(self) -> dict[str, dict[str, str]]:
        return normalize_overrides(self._raw_overrides())

    @property
    def changed_count(self) -> int:
        # Editing is intentionally allowed to pass through temporary invalid
        # states such as an empty numeric field. Validation belongs to Save and
        # Apply, not to the render loop that displays this counter.
        return sum(len(values) for values in self._raw_overrides().values())

    def named_configs(self) -> tuple[str, ...]:
        profiles = load_named_profiles(NAMED_CONFIG_PATH)
        return tuple(
            sorted(
                name
                for name, value in profiles.items()
                if isinstance(value, dict) and value.get("kind") == self.kind.value
            )
        )

    def save_named(self, name: str) -> None:
        clean = str(name).strip()
        if not clean:
            raise ValueError("Enter a configuration name")
        if len(clean) > 48:
            raise ValueError("Configuration name must contain at most 48 characters")
        profiles = load_named_profiles(NAMED_CONFIG_PATH)
        if clean in profiles:
            raise ValueError("That configuration name already exists")
        profiles[clean] = {
            "kind": self.kind.value,
            "overrides": self.overrides(),
        }
        save_named_profiles(NAMED_CONFIG_PATH, profiles)

    def load_named(self, name: str) -> None:
        profiles = load_named_profiles(NAMED_CONFIG_PATH)
        stored = profiles.get(name)
        if not isinstance(stored, dict) or stored.get("kind") != self.kind.value:
            raise ValueError("Named configuration is unavailable for this mission")
        normalized = normalize_overrides(stored.get("overrides", {}))
        for profile in self.profiles:
            values = default_values(profile)
            values.update(normalized.get(profile, {}))
            self.values[profile] = values
        self.page = 0
        self.selected = 0
        self.editing_key = None
