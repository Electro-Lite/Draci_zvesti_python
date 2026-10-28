"""Generate the browser-safe card catalogue from authoritative databases."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import cards.ability.abilities as abilities  # noqa: E402


OUTPUT = ROOT / "website" / "game-download" / "dist" / "play" / "catalog.json"
IMAGE_ROOT = OUTPUT.parent / "card-images"


def web_image_paths(card_id: str, source: str | None) -> tuple[str | None, str | None]:
    if not source:
        return None, None
    converter = shutil.which("magick")
    if converter is None:
        raise RuntimeError("ImageMagick is required to build optimized browser card art")
    source_path = ROOT / source
    if not source_path.is_file():
        raise RuntimeError(f"Missing card image: {source_path}")
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", card_id).strip("-")
    thumbnail = IMAGE_ROOT / "thumb" / f"{safe_id}.webp"
    detail = IMAGE_ROOT / "detail" / f"{safe_id}.webp"
    thumbnail.parent.mkdir(parents=True, exist_ok=True)
    detail.parent.mkdir(parents=True, exist_ok=True)
    for destination, geometry, quality in (
        (thumbnail, "240x336>", "64"),
        (detail, "750x1050>", "80"),
    ):
        subprocess.run(
            [
                converter,
                str(source_path),
                "-auto-orient",
                "-strip",
                "-resize",
                geometry,
                "-quality",
                quality,
                str(destination),
            ],
            check=True,
        )
    return (
        detail.relative_to(OUTPUT.parent).as_posix(),
        thumbnail.relative_to(OUTPUT.parent).as_posix(),
    )


def main() -> None:
    connection = sqlite3.connect(ROOT / "utils" / "cards.db")
    rows = connection.execute(
        """
        SELECT id, name, power, color, hp, dmg, color_dmg_buff,
               color_hp_buff, ability, image, type, secondary_color,
               secondary_color_dmg_buff, secondary_color_hp_buff
        FROM cards
        ORDER BY CASE type WHEN 'PLAYER' THEN 0 ELSE 1 END, LOWER(name), id
        """
    ).fetchall()
    cards = []
    for row in rows:
        ability = getattr(abilities, row[8])()
        image, thumbnail = web_image_paths(row[0], row[9])
        cards.append(
            {
                "id": row[0],
                "name": row[1],
                "power": int(row[2]),
                "color": row[3],
                "hp": int(row[4]),
                "dmg": int(row[5]),
                "manaBonus": {"dmg": int(row[6] or 0), "hp": int(row[7] or 0)},
                "secondaryColor": row[11],
                "secondaryManaBonus": {
                    "dmg": int(row[12] or 0),
                    "hp": int(row[13] or 0),
                },
                "ability": {
                    "name": str(ability.name),
                    "description": str(ability.description),
                },
                "image": image,
                "thumbnail": thumbnail,
                "type": row[10],
            }
        )
    presets = []
    decks = sqlite3.connect(ROOT / "utils" / "decks.db")
    for deck_id, name in (("Starter Blue_1", "Starter Blue"), ("Killer Queen_1", "Killer Queen")):
        card_ids = [
            row[0]
            for row in decks.execute(
                "SELECT card_id FROM deck_lines WHERE deck_id = ? ORDER BY rowid",
                (deck_id,),
            )
        ]
        if 10 <= len(card_ids) <= 12:
            presets.append({"id": deck_id, "name": name, "cardIds": card_ids})
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps({"schemaVersion": 1, "cards": cards, "presets": presets}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(cards)} cards and {len(presets)} starter decks to {OUTPUT}")


if __name__ == "__main__":
    main()
