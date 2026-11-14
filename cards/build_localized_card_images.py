#!/usr/bin/env python3
"""Migrate Czech card faces and deterministically build English variants.

Database image paths intentionally remain language-neutral. For example,
``cards/card_images/Bard.png`` resolves at runtime to ``Bard_cs.png`` or
``Bard_en.png``.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cards.ability import abilities  # noqa: E402
from cards.power import Power  # noqa: E402


CARD_DATABASE = PROJECT_ROOT / "utils" / "cards.db"
ITALIC_FONT = Path("/usr/share/fonts/TTF/DejaVuSerifCondensed-Italic.ttf")
BOLD_ITALIC_FONT = Path("/usr/share/fonts/TTF/DejaVuSerif-BoldItalic.ttf")


ENGLISH_NAMES = {
    "Asketa": "Ascetic",
    "InnosuvFanatik": "Inno's Fanatic",
    "Kvasimir": "Kvasimir EXPLOSIVE",
    "Lucisnik": "Archer",
    "NepotrabnyNovic": "Useless Novice",
    "Novic": "Novice",
    "Panos": "Panos",
    "Pesak": "Footman",
    "Skret": "Orc",
    "Strazny": "Guard",
    "Arcimág": "Archmage",
    "Bard": "Bard",
    "CikankaModra": "Blue Fortune Teller",
    "CikankaCerna_v4": "Black Fortune Teller",
    "CikankaCervena": "Red Fortune Teller",
    "DonJuan": "Don Juan",
    "DraciFanatik": "Dragon Fanatic",
    "DraciPosluhovac": "Dragon Minion",
    "Goblin": "Goblin",
    "GoblinKral": "Goblin King",
    "GobliniSaman": "Goblin Shaman",
    "HloupeLojzek": "Foolish Lojzek",
    "Skritek": "Inno's Goblin",
    "Katapult": "Catapult",
    "MagOhne": "Fire Mage",
    "Medved": "Bear",
    "Paladin": "Paladin",
    "Principal": "Principal",
    "Silak": "Strongman",
    "Slon": "Elephant",
    "Upir": "Vampire",
    "VelitelStraze": "Guard Commander",
    "Zabijak": "Killer",
    "Sasek": "Jester",
}


RULE_OVERRIDES = {
    "HitAll1Dmg": "Destroy all characters with 1 health or less.",
    "SideWay2DmgOnDeath": "When this card dies, adjacent characters take 2 damage.",
    "WeakenDragon1Dmg": "Decrease dragon damage by 1, or by 2 while blue mana is active.",
    "DragonFanaticDrawWin": (
        "If the round is tied, the owner of the first Dragon Fanatic defeated "
        "in dragon combat wins the round."
    ),
    "HealDragon1": "After each combat round, heal the dragon by 1, up to its maximum health.",
    "SummonOtherGoblins": (
        "Take all Goblins from your deck and hand. Fill empty board spaces from "
        "left to right, then discard the rest."
    ),
    "BuffFromGoblin": "Get +1 attack and +1 health for each Goblin on the board.",
    "ReturnByDeath": "When this card dies, return it to its owner's hand.",
    "HitDragon2Dmg": "When a dragon is revealed, it immediately takes 2 damage.",
    "SidewaysMinus1": (
        "Adjacent characters get -1 attack and -1 health, or -2/-2 on black mana."
    ),
    "AttackFront": "Attack the character directly in front.",
}


# Finished card faces that are not registered in cards.db yet. Their silver
# frame identifies them as legendary; Prorok is the sole normal card here.
EXTRA_FACES = {
    "Brek": (
        Power.LEGENDARY.value,
        "When this enters play, you may destroy another character with 1 health.",
    ),
    "Ctiprd": (
        Power.LEGENDARY.value,
        "When this enters play, you may play Mesaros from your hand.",
    ),
    "Gumpold": (Power.LEGENDARY.value, ""),
    "Jadviga": (
        Power.LEGENDARY.value,
        "When this dies, return one other card from your discard pile to your hand.",
    ),
    "Kovozdob": (
        Power.LEGENDARY.value,
        "When this enters play, it may overtake the character in front. Give +1/+1 to adjacent allies.",
    ),
    "Majdalena": (
        Power.LEGENDARY.value,
        "Secretly place a second card beneath this one. When this dies, reveal that card and resolve its on-play effects.",
    ),
    "Mesaros": (
        Power.LEGENDARY.value,
        "Give +1 attack to every ally positioned in front of this card.",
    ),
    "Presentes": (
        Power.LEGENDARY.value,
        "Adjacent characters get -1/-1, or -2/-2 while black mana is active.",
    ),
    "Prorok": (
        Power.NORMAL.value,
        "When this enters play, secretly view the top dragon. You may move it to the bottom of the dragon deck.",
    ),
    "Psonek": (
        Power.LEGENDARY.value,
        "When this enters play, it may swap positions with any of your characters.",
    ),
    "Trol": (
        Power.LEGENDARY.value,
        "When this enters play, eat the character directly in front.",
    ),
    "Vikulio": (
        Power.LEGENDARY.value,
        "Adjacent characters get -1/-1, or -2/-2 while blue mana is active.",
    ),
}


@dataclass(frozen=True)
class CardFace:
    image: Path
    power: int
    ability_class: str
    rules: str

    @property
    def legendary(self) -> bool:
        return self.power == Power.LEGENDARY.value


def card_faces() -> list[CardFace]:
    by_image: dict[Path, CardFace] = {}
    with sqlite3.connect(CARD_DATABASE) as connection:
        rows = connection.execute(
            """
            SELECT power, ability, image
            FROM cards
            WHERE type = 'PLAYER' AND image IS NOT NULL
            ORDER BY power, id
            """
        )
        for power, ability_class, image in rows:
            image_path = PROJECT_ROOT / image
            if image_path.name.startswith("mana"):
                continue
            ability = getattr(abilities, ability_class)()
            rules = RULE_OVERRIDES.get(ability_class, str(ability.description).strip())
            by_image.setdefault(
                image_path,
                CardFace(image_path, int(power), ability_class, rules),
            )
    for stem, (power, rules) in EXTRA_FACES.items():
        image_path = PROJECT_ROOT / "cards" / "card_images" / f"{stem}.png"
        by_image.setdefault(
            image_path,
            CardFace(image_path, power, "", rules),
        )
    return sorted(by_image.values(), key=lambda face: face.image.name.casefold())


def dimensions(path: Path) -> tuple[int, int]:
    output = subprocess.check_output(
        ["magick", "identify", "-format", "%w %h", str(path)],
        text=True,
    )
    width, height = output.split()
    return int(width), int(height)


def caption_image(
    destination: Path,
    text: str,
    size: tuple[int, int],
    point_size: int,
    font: Path,
) -> None:
    subprocess.run(
        [
            "magick",
            "-background",
            "none",
            "-fill",
            "#111111",
            "-font",
            str(font),
            "-pointsize",
            str(point_size),
            "-gravity",
            "center",
            "-size",
            f"{size[0]}x{size[1]}",
            f"caption:{text}",
            str(destination),
        ],
        check=True,
    )


def overlay_panel(source: Path, destination: Path, box, color: str) -> None:
    x, y, width, height = box
    subprocess.run(
        [
            "magick",
            str(source),
            "-fill",
            color,
            "-draw",
            f"rectangle {x},{y} {x + width},{y + height}",
            str(destination),
        ],
        check=True,
    )


def composite(source: Path, overlay: Path, destination: Path, x: int, y: int) -> None:
    subprocess.run(
        [
            "magick",
            str(source),
            str(overlay),
            "-geometry",
            f"+{x}+{y}",
            "-composite",
            str(destination),
        ],
        check=True,
    )


def description_point_size(width: int, text: str) -> int:
    # Card faces are commonly displayed at roughly one quarter of their source
    # size.  A bold face and deliberately generous source point size keep rules
    # legible in the deck editor and during a match.
    base = 31 if len(text) <= 72 else 27 if len(text) <= 108 else 23
    return max(10, round(base * width / 750))


def english_name(face: CardFace) -> str | None:
    if face.legendary:
        return None
    if face.image.stem == "Prorok":
        return "Prophet"
    try:
        return ENGLISH_NAMES[face.image.stem]
    except KeyError as error:
        raise RuntimeError(f"Missing English name for {face.image.name}") from error


def render_english(face: CardFace, czech: Path, english: Path) -> None:
    width, height = dimensions(czech)
    with tempfile.TemporaryDirectory(prefix="card-translation-") as directory:
        temporary = Path(directory)
        current = temporary / "current.png"
        shutil.copy2(czech, current)

        if face.rules:
            panel = (
                round(width * 0.13),
                round(height * 0.74),
                round(width * 0.74),
                round(height * 0.14),
            )
            covered = temporary / "rules-covered.png"
            overlay_panel(current, covered, panel, "#d8d8d8")
            caption = temporary / "rules.png"
            inner = (
                max(1, panel[2] - round(width * 0.035)),
                max(1, panel[3] - round(height * 0.015)),
            )
            caption_image(
                caption,
                face.rules,
                inner,
                description_point_size(width, face.rules),
                BOLD_ITALIC_FONT,
            )
            composited = temporary / "rules-composited.png"
            composite(
                covered,
                caption,
                composited,
                panel[0] + (panel[2] - inner[0]) // 2,
                panel[1] + (panel[3] - inner[1]) // 2,
            )
            current = composited

        name = english_name(face)
        if name is not None:
            panel = (
                round(width * 0.245),
                round(height * 0.885),
                round(width * 0.51),
                round(height * 0.06),
            )
            covered = temporary / "name-covered.png"
            overlay_panel(current, covered, panel, "#f7f3ed")
            caption = temporary / "name.png"
            inner = (
                max(1, panel[2] - round(width * 0.025)),
                max(1, panel[3] - round(height * 0.01)),
            )
            base_size = 33 if len(name) <= 15 else 27
            caption_image(
                caption,
                name,
                inner,
                max(10, round(base_size * width / 750)),
                BOLD_ITALIC_FONT,
            )
            composited = temporary / "name-composited.png"
            composite(
                covered,
                caption,
                composited,
                panel[0] + (panel[2] - inner[0]) // 2,
                panel[1] + (panel[3] - inner[1]) // 2,
            )
            current = composited

        shutil.copy2(current, english)


def migrate_and_build(*, overwrite: bool) -> tuple[int, int]:
    migrated = generated = 0
    for face in card_faces():
        neutral = face.image
        czech = neutral.with_name(f"{neutral.stem}_cs{neutral.suffix}")
        english = neutral.with_name(f"{neutral.stem}_en{neutral.suffix}")
        if not czech.exists():
            if not neutral.exists():
                raise FileNotFoundError(f"Missing Czech source image: {neutral}")
            neutral.rename(czech)
            migrated += 1
        if overwrite or not english.exists():
            render_english(face, czech, english)
            generated += 1
        print(f"{czech.name} -> {english.name}")
    return migrated, generated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate English variants that already exist.",
    )
    args = parser.parse_args()
    if shutil.which("magick") is None:
        raise RuntimeError("ImageMagick 7 ('magick') is required")
    for font in (ITALIC_FONT, BOLD_ITALIC_FONT):
        if not font.is_file():
            raise RuntimeError(f"Required font is missing: {font}")
    migrated, generated = migrate_and_build(overwrite=args.overwrite)
    print(f"Migrated {migrated} Czech images; generated {generated} English images.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
