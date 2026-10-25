"""Safe, user-editable NEAT configuration profiles for training jobs."""

from __future__ import annotations

import configparser
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import neat


CONFIG_ROOT = Path(__file__).resolve().parent / "configs"
PROFILE_PATHS = {
    "builder": CONFIG_ROOT / "neat_config_builder.txt",
    "evaluator": CONFIG_ROOT / "neat_config_evaluator.txt",
}
PROFILE_ENVIRONMENT = {
    "builder": "NEAT_BUILDER_CONFIG_PATH",
    "evaluator": "NEAT_EVALUATOR_CONFIG_PATH",
}
PROFILE_LABELS = {
    "builder": "Deck builder",
    "evaluator": "Controller / evaluator",
}
LOCKED_OPTIONS = {
    ("DefaultGenome", "num_inputs"),
    ("DefaultGenome", "num_outputs"),
}


@dataclass(frozen=True)
class NeatConfigField:
    profile: str
    section: str
    option: str
    default: str
    locked: bool = False

    @property
    def key(self) -> str:
        return f"{self.section}.{self.option}"


def _parser(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    if not parser.read(path):
        raise FileNotFoundError(path)
    return parser


def fields_for_profile(profile: str) -> tuple[NeatConfigField, ...]:
    path = PROFILE_PATHS[profile]
    parser = _parser(path)
    return tuple(
        NeatConfigField(
            profile=profile,
            section=section,
            option=option,
            default=value,
            locked=(section, option) in LOCKED_OPTIONS,
        )
        for section in parser.sections()
        for option, value in parser.items(section)
    )


def default_values(profile: str) -> dict[str, str]:
    return {field.key: field.default for field in fields_for_profile(profile)}


def normalize_overrides(raw) -> dict[str, dict[str, str]]:
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise ValueError("Advanced NEAT configuration must be an object")
    normalized = {}
    for profile, values in raw.items():
        if profile not in PROFILE_PATHS:
            raise ValueError(f"Unknown NEAT configuration group: {profile}")
        if not isinstance(values, dict):
            raise ValueError(f"NEAT configuration group {profile} must be an object")
        defaults = default_values(profile)
        clean = {}
        for key, value in values.items():
            if key not in defaults:
                raise ValueError(f"Unknown NEAT parameter: {profile}.{key}")
            text = str(value).strip()
            if not text:
                raise ValueError(f"NEAT parameter {profile}.{key} cannot be empty")
            field = next(item for item in fields_for_profile(profile) if item.key == key)
            if field.locked and text != field.default:
                raise ValueError(f"{profile}.{key} is fixed by the game encoding")
            if text != defaults[key]:
                clean[key] = text
        if clean:
            normalized[profile] = clean
    return normalized


def configured_text(profile: str, overrides: dict[str, str] | None = None) -> str:
    parser = _parser(PROFILE_PATHS[profile])
    for key, value in (overrides or {}).items():
        section, option = key.split(".", 1)
        parser.set(section, option, str(value))
    from io import StringIO

    output = StringIO()
    parser.write(output, space_around_delimiters=True)
    return output.getvalue()


def validate_overrides(raw) -> dict[str, dict[str, str]]:
    normalized = normalize_overrides(raw)
    with tempfile.TemporaryDirectory(prefix="draci-neat-validate-") as directory:
        for profile, overrides in normalized.items():
            path = Path(directory) / f"{profile}.txt"
            path.write_text(configured_text(profile, overrides), encoding="utf-8")
            neat.Config(
                neat.DefaultGenome,
                neat.DefaultReproduction,
                neat.DefaultSpeciesSet,
                neat.DefaultStagnation,
                str(path),
            )
    return normalized


def materialize_configs(
    raw,
    destination: Path,
    *,
    profiles: tuple[str, ...] | None = None,
) -> dict[str, str]:
    normalized = normalize_overrides(raw)
    environment = {}
    destination.mkdir(parents=True, exist_ok=True)
    selected = profiles or tuple(normalized)
    for profile in selected:
        if profile not in PROFILE_PATHS:
            raise ValueError(f"Unknown NEAT configuration group: {profile}")
        overrides = normalized.get(profile, {})
        path = destination / f"neat_config_{profile}.txt"
        path.write_text(configured_text(profile, overrides), encoding="utf-8")
        neat.Config(
            neat.DefaultGenome,
            neat.DefaultReproduction,
            neat.DefaultSpeciesSet,
            neat.DefaultStagnation,
            str(path),
        )
        environment[PROFILE_ENVIRONMENT[profile]] = str(path)
    return environment


def config_path(profile: str) -> Path:
    configured = os.environ.get(PROFILE_ENVIRONMENT[profile])
    return Path(configured) if configured else PROFILE_PATHS[profile]


def load_named_profiles(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_named_profiles(path: Path, profiles: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(profiles, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)
