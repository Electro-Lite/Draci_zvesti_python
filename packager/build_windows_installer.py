"""Build a portable Windows bundle and an Inno Setup installer.

Run this script on 64-bit Windows from the repository root or from any other
working directory.  PyInstaller does not cross-compile Windows executables, so
running the actual build on Linux is intentionally rejected.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path


APP_NAME = "DraciZvesti"
DEFAULT_VERSION = "0.1.0"
PACKAGER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGER_DIR.parent
ARTIFACTS_DIR = PACKAGER_DIR / "artifacts"
BUILD_DIR = PACKAGER_DIR / ".build"
ENTRY_POINT = PACKAGER_DIR / "windows_entry.py"
INNO_SCRIPT = PACKAGER_DIR / "DraciZvesti.iss"

REQUIRED_PATHS = (
    PROJECT_ROOT / "py_game" / "resources",
    PROJECT_ROOT / "cards" / "card_images",
    PROJECT_ROOT / "neat_ai" / "configs",
    PROJECT_ROOT / "utils" / "cards.db",
    PROJECT_ROOT / "utils" / "decks.db",
)

HIDDEN_IMPORTS = (
    "cards.ability.abilities",
    "neat_ai.deck_builder_trainer",
    "neat_ai.matchup_trainer",
    "neat_ai.player_trainer",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the Draci Zvesti Windows portable ZIP and installer."
    )
    parser.add_argument(
        "--version",
        default=os.environ.get("DRACI_ZVESTI_VERSION", DEFAULT_VERSION),
        help="Installer version, for example 0.2.0 (default: %(default)s).",
    )
    parser.add_argument(
        "--portable-only",
        action="store_true",
        help="Build the portable ZIP but do not invoke Inno Setup.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print commands without building.",
    )
    parser.add_argument(
        "--keep-build",
        action="store_true",
        help="Keep packager/.build after a successful build.",
    )
    return parser.parse_args()


def validate_inputs(version: str) -> None:
    if not re.fullmatch(r"\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9.-]+)?", version):
        raise SystemExit(
            f"Invalid version {version!r}; use a value such as 0.2.0 or 0.2.0-beta.1."
        )
    missing = [path for path in REQUIRED_PATHS if not path.exists()]
    if missing:
        formatted = "\n".join(f"  - {path}" for path in missing)
        raise SystemExit(f"Required packaging inputs are missing:\n{formatted}")
    if not ENTRY_POINT.is_file() or not INNO_SCRIPT.is_file():
        raise SystemExit("Packaging entry point or Inno Setup script is missing.")


def add_data(command: list[str], source: Path, destination: str) -> None:
    # PyInstaller uses a semicolon between source and destination on Windows.
    command.extend(("--add-data", f"{source};{destination}"))


def pyinstaller_command(dist_dir: Path, work_dir: Path, spec_dir: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--hide-console",
        "hide-early",
        "--noupx",
        "--contents-directory",
        "_internal",
        "--name",
        APP_NAME,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        "--paths",
        str(PROJECT_ROOT),
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


def find_inno_compiler() -> Path | None:
    located = shutil.which("ISCC.exe") or shutil.which("iscc")
    if located:
        return Path(located)
    candidates = []
    for variable in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "Inno Setup 6" / "ISCC.exe")
            candidates.append(Path(root) / "Programs" / "Inno Setup 6" / "ISCC.exe")
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def run(command: list[str]) -> None:
    printable = subprocess.list2cmdline(command)
    print(f"> {printable}", flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def build_portable_zip(dist_dir: Path, version: str) -> Path:
    archive_base = ARTIFACTS_DIR / f"{APP_NAME}-{version}-Windows-x64-portable"
    archive_path = archive_base.with_suffix(".zip")
    archive_path.unlink(missing_ok=True)
    created = shutil.make_archive(
        str(archive_base),
        "zip",
        root_dir=dist_dir,
        base_dir=APP_NAME,
    )
    return Path(created)


def build_installer(dist_app: Path, version: str, compiler: Path) -> Path:
    output_name = f"{APP_NAME}-{version}-Windows-x64-Setup.exe"
    expected_output = ARTIFACTS_DIR / output_name
    expected_output.unlink(missing_ok=True)
    run(
        [
            str(compiler),
            f'/DSourceDir="{dist_app}"',
            f'/DOutputDir="{ARTIFACTS_DIR}"',
            f'/DAppVersion="{version}"',
            str(INNO_SCRIPT),
        ]
    )
    if not expected_output.is_file():
        raise SystemExit(
            "Inno Setup reported success but the expected installer was not created: "
            f"{expected_output}"
        )
    return expected_output


def main() -> int:
    args = parse_args()
    validate_inputs(args.version)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    dist_dir = BUILD_DIR / "dist"
    work_dir = BUILD_DIR / "work"
    spec_dir = BUILD_DIR / "spec"
    command = pyinstaller_command(dist_dir, work_dir, spec_dir)

    if args.dry_run:
        print("Validated packaging inputs.")
        print(subprocess.list2cmdline(command))
        if not args.portable_only:
            print("Inno Setup command will be generated after the PyInstaller build.")
        return 0

    if platform.system() != "Windows":
        raise SystemExit(
            "Windows executables must be built on Windows. Run this script from "
            "64-bit Windows or a Windows CI runner."
        )
    if struct.calcsize("P") != 8:
        raise SystemExit("Use 64-bit Python to produce the Windows x64 package.")

    try:
        import PyInstaller  # noqa: F401
    except ImportError as error:
        raise SystemExit(
            "PyInstaller is not installed. Run: "
            "py -m pip install -r packager\\requirements-windows-build.txt"
        ) from error

    compiler = None if args.portable_only else find_inno_compiler()
    if not args.portable_only and compiler is None:
        raise SystemExit(
            "Inno Setup 6 was not found. Install it or use --portable-only."
        )

    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    dist_dir.mkdir(parents=True)
    work_dir.mkdir(parents=True)
    spec_dir.mkdir(parents=True)

    run(command)
    dist_app = dist_dir / APP_NAME
    executable = dist_app / f"{APP_NAME}.exe"
    if not executable.is_file():
        raise SystemExit(f"PyInstaller did not create {executable}")

    portable_zip = build_portable_zip(dist_dir, args.version)
    print(f"Created portable package: {portable_zip}")

    if compiler is not None:
        installer = build_installer(dist_app, args.version, compiler)
        print(f"Created installer: {installer}")

    if not args.keep_build:
        shutil.rmtree(BUILD_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
