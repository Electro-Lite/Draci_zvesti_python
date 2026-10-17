"""Versioned, composition-bound player-controller artifacts."""

from __future__ import annotations

import hashlib
import json
import pickle
import re
from dataclasses import asdict, dataclass
from pathlib import Path


SCHEMA_VERSION = 1
ARTIFACT_TYPE = "player_controller"
CONFIG_PROFILE = "evaluator-v1"


def composition_card_ids(deck_or_ids) -> tuple[str, ...]:
    values = getattr(deck_or_ids, "cards", deck_or_ids)
    return tuple(
        sorted(
            str(getattr(value, "id", value))
            for value in values
            if getattr(value, "id", value) is not None
        )
    )


def composition_signature(deck_or_ids) -> str:
    card_ids = composition_card_ids(deck_or_ids)
    return hashlib.md5(",".join(card_ids).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PlayerArtifactManifest:
    schema_version: int
    artifact_type: str
    display_name: str
    mission: str
    role: str
    run_label: str
    deck_id: str
    deck_name: str
    deck_signature: str
    card_ids: tuple[str, ...]
    generation: int
    config_profile: str
    artifact_file: str

    @classmethod
    def from_dict(cls, value: dict):
        return cls(
            schema_version=int(value.get("schema_version", 0)),
            artifact_type=str(value.get("artifact_type", "")),
            display_name=str(value.get("display_name", "")),
            mission=str(value.get("mission", "")),
            role=str(value.get("role", "")),
            run_label=str(value.get("run_label", "")),
            deck_id=str(value.get("deck_id", "")),
            deck_name=str(value.get("deck_name", "")),
            deck_signature=str(value.get("deck_signature", "")),
            card_ids=tuple(str(item) for item in value.get("card_ids", ())),
            generation=int(value.get("generation", 0)),
            config_profile=str(value.get("config_profile", "")),
            artifact_file=str(value.get("artifact_file", "")),
        )

    @property
    def valid(self) -> bool:
        return (
            self.schema_version == SCHEMA_VERSION
            and self.artifact_type == ARTIFACT_TYPE
            and self.config_profile == CONFIG_PROFILE
            and bool(self.display_name)
            and bool(self.deck_signature)
            and bool(self.card_ids)
            and self.deck_signature == composition_signature(self.card_ids)
            and bool(self.artifact_file)
            and Path(self.artifact_file).name == self.artifact_file
            and self.artifact_file.endswith(".pickle")
        )


@dataclass(frozen=True)
class PlayerArtifact:
    path: Path
    manifest_path: Path
    manifest: PlayerArtifactManifest

    @property
    def label(self) -> str:
        return self.manifest.display_name


def safe_artifact_segment(value: str, fallback: str, maximum: int = 32) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "")).strip("-.")
    cleaned = cleaned or fallback
    if len(cleaned) <= maximum:
        return cleaned
    digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:8]
    return f"{cleaned[:maximum - len(digest) - 1]}-{digest}"


def export_player_artifact(
    output_dir: Path,
    genome,
    deck,
    *,
    mission: str,
    role: str,
    run_label: str,
    generation: int,
    display_name: str | None = None,
) -> PlayerArtifact:
    """Persist one controller and enough evidence to bind it to a composition."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    card_ids = composition_card_ids(deck)
    if not card_ids:
        raise ValueError("Cannot export a player controller without a deck composition")
    base = "player_{}_{}_{}".format(
        safe_artifact_segment(mission, "training"),
        safe_artifact_segment(role, "player"),
        safe_artifact_segment(run_label, "run"),
    )
    artifact_path = output_dir / f"{base}.pickle"
    manifest_path = output_dir / f"{base}.player.json"
    manifest = PlayerArtifactManifest(
        schema_version=SCHEMA_VERSION,
        artifact_type=ARTIFACT_TYPE,
        display_name=str(
            display_name
            or f"{getattr(deck, 'name', None) or getattr(deck, 'id', 'Deck')} · {role}"
        ),
        mission=str(mission),
        role=str(role),
        run_label=str(run_label),
        deck_id=str(getattr(deck, "id", "") or ""),
        deck_name=str(getattr(deck, "name", "") or getattr(deck, "id", "") or "Deck"),
        deck_signature=composition_signature(card_ids),
        card_ids=card_ids,
        generation=int(generation),
        config_profile=CONFIG_PROFILE,
        artifact_file=artifact_path.name,
    )
    with artifact_path.open("wb") as artifact_file:
        pickle.dump(genome, artifact_file)
    manifest_path.write_text(json.dumps(asdict(manifest), indent=2, sort_keys=True))
    return PlayerArtifact(artifact_path, manifest_path, manifest)


def load_player_artifact(manifest_path: Path) -> PlayerArtifact | None:
    try:
        manifest_path = Path(manifest_path)
        value = json.loads(manifest_path.read_text())
        manifest = PlayerArtifactManifest.from_dict(value)
        artifact_path = manifest_path.parent / manifest.artifact_file
        if not manifest.valid or not artifact_path.is_file():
            return None
        return PlayerArtifact(artifact_path, manifest_path, manifest)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def clone_player_artifact(
    manifest_path: Path,
    output_dir: Path,
    deck,
    *,
    role: str,
    display_name: str,
) -> PlayerArtifact:
    """Copy a validated controller and bind the copy to a new deck identity."""
    source = load_player_artifact(manifest_path)
    if source is None:
        raise ValueError("The trained AI artifact is missing or invalid")
    if source.manifest.deck_signature != composition_signature(deck):
        raise ValueError(
            "The trained AI artifact does not match this exact deck composition"
        )
    try:
        with source.path.open("rb") as artifact_file:
            genome = pickle.load(artifact_file)
    except (OSError, EOFError, pickle.PickleError) as error:
        raise ValueError(f"The trained AI genome could not be loaded: {error}") from error
    return export_player_artifact(
        output_dir,
        genome,
        deck,
        mission=source.manifest.mission,
        role=role,
        run_label=source.manifest.run_label,
        generation=source.manifest.generation,
        display_name=display_name,
    )


def discover_player_artifacts(
    roots: tuple[Path, ...] | list[Path],
    deck_or_ids,
) -> list[PlayerArtifact]:
    """Return only controllers proven to match the exact selected composition."""
    expected = composition_signature(deck_or_ids)
    if not composition_card_ids(deck_or_ids):
        return []
    artifacts = []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for manifest_path in root.glob("**/*.player.json"):
            artifact = load_player_artifact(manifest_path)
            if artifact is not None and artifact.manifest.deck_signature == expected:
                artifacts.append(artifact)
    return sorted(
        artifacts,
        key=lambda item: item.manifest_path.stat().st_mtime,
        reverse=True,
    )
