"""Build a self-contained x86-64 Linux AppImage."""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path


APP_NAME = "DraciZvesti"
DEFAULT_VERSION = "0.1.0"
PACKAGER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGER_DIR.parent
ARTIFACTS_DIR = PACKAGER_DIR / "artifacts"
BUILD_DIR = PACKAGER_DIR / ".build-linux"
ENTRY_POINT = PACKAGER_DIR / "windows_entry.py"
ICON_SOURCE = PROJECT_ROOT / "py_game" / "resources" / "transparent_background.png"
REQUIRED_PATHS = (
    PROJECT_ROOT / "py_game" / "resources",
    PROJECT_ROOT / "cards" / "card_images",
    PROJECT_ROOT / "neat_ai" / "configs",
    PROJECT_ROOT / "utils" / "cards.db",
    PROJECT_ROOT / "utils" / "decks.db",
    ENTRY_POINT,
    ICON_SOURCE,
)
HIDDEN_IMPORTS = (
    "cards.ability.abilities",
    "neat_ai.deck_builder_trainer",
    "neat_ai.matchup_trainer",
    "neat_ai.player_trainer",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Draci Zvesti Linux AppImage.")
    parser.add_argument("--version", default=os.environ.get("DRACI_ZVESTI_VERSION", DEFAULT_VERSION))
    parser.add_argument("--appimagetool", type=Path)
    parser.add_argument(
        "--runtime-file",
        type=Path,
        help="Optional local AppImage type-2 runtime (useful for offline builds).",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-build", action="store_true")
    return parser.parse_args()


def validate(args: argparse.Namespace) -> Path | None:
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "AMD64"}:
        raise SystemExit("This builder currently supports Linux x86-64 only.")
    if not re.fullmatch(r"\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9.-]+)?", args.version):
        raise SystemExit(f"Invalid version: {args.version!r}")
    missing = [path for path in REQUIRED_PATHS if not path.exists()]
    if missing:
        raise SystemExit("Missing packaging inputs:\n" + "\n".join(f"  - {p}" for p in missing))
    tool = shutil.which("appimagetool")
    located = args.appimagetool or (Path(tool) if tool else None)
    if not args.dry_run and (located is None or not located.is_file()):
        raise SystemExit("Pass --appimagetool /path/to/appimagetool-x86_64.AppImage")
    if args.runtime_file is not None and not args.runtime_file.is_file():
        raise SystemExit(f"AppImage runtime does not exist: {args.runtime_file}")
    return located


def add_data(command: list[str], source: Path, destination: str) -> None:
    command.extend(("--add-data", f"{source}:{destination}"))


def pyinstaller_command(dist_dir: Path, work_dir: Path, spec_dir: Path) -> list[str]:
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
        "--noupx", "--contents-directory", "_internal", "--name", APP_NAME,
        "--distpath", str(dist_dir), "--workpath", str(work_dir),
        "--specpath", str(spec_dir), "--paths", str(PROJECT_ROOT),
    ]
    for module_name in HIDDEN_IMPORTS:
        command.extend(("--hidden-import", module_name))
    add_data(command, PROJECT_ROOT / "py_game" / "resources", "py_game/resources")
    add_data(command, PROJECT_ROOT / "cards" / "card_images", "cards/card_images")
    add_data(command, PROJECT_ROOT / "neat_ai" / "configs", "neat_ai/configs")
    add_data(command, PROJECT_ROOT / "utils" / "cards.db", "utils")
    add_data(command, PROJECT_ROOT / "utils" / "decks.db", "utils")
    trained_ai = PROJECT_ROOT / "neat_ai" / "trained_ai"
    if trained_ai.is_dir():
        add_data(command, trained_ai, "neat_ai/trained_ai")
    command.append(str(ENTRY_POINT))
    return command


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print(">", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)


def appimagetool_command(
    tool: Path,
    app_dir: Path,
    output: Path,
    runtime_file: Path | None,
) -> list[str]:
    command = [str(tool.resolve())]
    # The official tool is itself an AppImage. Extraction mode also works on
    # build hosts and containers where FUSE is unavailable.
    if tool.name.endswith(".AppImage"):
        command.append("--appimage-extract-and-run")
    if runtime_file is not None:
        command.extend(("--runtime-file", str(runtime_file.resolve())))
    command.extend((str(app_dir), str(output)))
    return command


def write_appdir(app_dir: Path, bundle: Path) -> None:
    app_root = app_dir / "usr" / "lib" / APP_NAME
    shutil.copytree(bundle, app_root)
    app_run = app_dir / "AppRun"
    app_run.write_text(
        "#!/bin/sh\n"
        'APPDIR="$(dirname "$(readlink -f "$0")")"\n'
        f'exec "$APPDIR/usr/lib/{APP_NAME}/{APP_NAME}" "$@"\n',
        encoding="utf-8",
    )
    app_run.chmod(app_run.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    (app_dir / "dracizvesti.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Draci Zvesti\n"
        "Comment=Card game of mana, tactics, and dragons\n"
        f"Exec={APP_NAME}\nIcon=dracizvesti\nTerminal=false\nCategories=Game;CardGame;\n",
        encoding="utf-8",
    )
    shutil.copy2(ICON_SOURCE, app_dir / "dracizvesti.png")


def main() -> int:
    args = parse_args()
    appimagetool = validate(args)
    dist_dir = BUILD_DIR / "dist"
    command = pyinstaller_command(dist_dir, BUILD_DIR / "work", BUILD_DIR / "spec")
    if args.dry_run:
        print("Validated packaging inputs.")
        print(subprocess.list2cmdline(command))
        return 0
    try:
        import PyInstaller  # noqa: F401
    except ImportError as error:
        raise SystemExit(
            "PyInstaller is not installed. Run: "
            "python -m pip install -r packager/requirements-linux-build.txt"
        ) from error
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    dist_dir.mkdir(parents=True)
    run(command)
    bundle = dist_dir / APP_NAME
    if not (bundle / APP_NAME).is_file():
        raise SystemExit(f"PyInstaller did not create {bundle / APP_NAME}")
    app_dir = BUILD_DIR / f"{APP_NAME}.AppDir"
    write_appdir(app_dir, bundle)
    output = ARTIFACTS_DIR / f"{APP_NAME}-{args.version}-Linux-x86_64.AppImage"
    output.unlink(missing_ok=True)
    env = dict(os.environ, ARCH="x86_64", VERSION=args.version)
    run(appimagetool_command(appimagetool, app_dir, output, args.runtime_file), env=env)
    output.chmod(output.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Created Linux package: {output}")
    if not args.keep_build:
        shutil.rmtree(BUILD_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
