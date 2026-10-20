# Windows packager

This directory builds the current project layout as a self-contained 64-bit
Windows application. It creates both a portable ZIP and, when Inno Setup 6 is
installed, a per-user installer. Users do not need Python.

The actual build must run on Windows; PyInstaller does not cross-compile a
Windows executable from Linux.

## Prerequisites

- 64-bit Python 3.12
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) for the installer

From PowerShell in the repository root:

```powershell
py -3.12 -m venv .packager-venv
.\.packager-venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r packager\requirements-windows-build.txt
python packager\build_windows_installer.py --version 0.1.0
```

Outputs are written to `packager\artifacts`:

- `DraciZvesti-<version>-Windows-x64-portable.zip`
- `DraciZvesti-<version>-Windows-x64-Setup.exe`

Use `--portable-only` if Inno Setup is unavailable. Use `--keep-build` to keep
the intermediate PyInstaller directory for troubleshooting.

## Included data

The build includes the current card artwork, Pygame resources, NEAT
configuration, `utils/cards.db`, `utils/decks.db`, and files currently present
in `neat_ai/trained_ai`.

The large development `train.db`, WAL files, local UI training runs, notebooks,
tests, recovery files, and wireframes are not included. A new `train.db` is
created inside the per-user installation when training first needs it.

The installer uses `%LOCALAPPDATA%\Programs\DraciZvesti`, rather than Program
Files, because the current application stores mutable databases and training
artifacts relative to its bundled modules. Existing card and deck databases are
preserved during an upgrade and uninstall.

## Linux AppImage

The Linux build is also self-contained; users do not need Python. Build it on
an x86-64 Linux machine with the project's virtual environment:

```bash
python -m pip install -r packager/requirements-linux-build.txt
python packager/build_linux_appimage.py \
  --version 0.1.0 \
  --appimagetool /absolute/path/to/appimagetool-x86_64.AppImage \
  --runtime-file /absolute/path/to/runtime-x86_64
```

This creates `packager/artifacts/DraciZvesti-0.1.0-Linux-x86_64.AppImage`.
Download the official appimagetool from the AppImage project releases. Build
on the oldest Linux distribution you intend to support because native system
library compatibility generally runs forward, not backward.
