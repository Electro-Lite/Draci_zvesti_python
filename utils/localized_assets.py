from __future__ import annotations

from pathlib import Path


IMAGE_LANGUAGE_CODES = ("en", "cs")
LEGACY_IMAGE_LANGUAGE = "cs"


def base_image_path(path: str | Path) -> Path:
    """Return the language-neutral path for an optionally suffixed image."""
    candidate = Path(path)
    for code in IMAGE_LANGUAGE_CODES:
        suffix = f"_{code}"
        if candidate.stem.endswith(suffix):
            return candidate.with_name(
                f"{candidate.stem[:-len(suffix)]}{candidate.suffix}"
            )
    return candidate


def image_variant_path(path: str | Path, language_code: str) -> Path:
    base = base_image_path(path)
    return base.with_name(f"{base.stem}_{language_code}{base.suffix}")


def localized_image_path(
    path: str | Path | None,
    language_code: str,
) -> Path | None:
    """Resolve ``Card_en.png``/``Card_cs.png`` with legacy compatibility.

    Existing unsuffixed artwork is Czech, so Czech deliberately checks that
    legacy file before falling back to English. Other languages inherit the
    English image when their own variant is unavailable.
    """
    if path is None:
        return None
    base = base_image_path(path)
    selected = image_variant_path(base, language_code)
    candidates = [selected]
    if language_code == LEGACY_IMAGE_LANGUAGE:
        candidates.append(base)
    if language_code != "en":
        candidates.append(image_variant_path(base, "en"))
    if base not in candidates:
        candidates.append(base)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # Preserve the selected name so missing-art diagnostics describe the
    # resource that was actually requested.
    return selected
