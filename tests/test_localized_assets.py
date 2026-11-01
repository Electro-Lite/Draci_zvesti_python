import tempfile
import unittest
from pathlib import Path

from utils.localized_assets import (
    base_image_path,
    image_variant_path,
    localized_image_path,
)


class LocalizedAssetTests(unittest.TestCase):
    def test_variant_names_are_based_on_language_neutral_path(self):
        self.assertEqual(
            image_variant_path("cards/Bard_cs.png", "en"),
            Path("cards/Bard_en.png"),
        )
        self.assertEqual(base_image_path("cards/Bard_en.png"), Path("cards/Bard.png"))

    def test_runtime_selects_requested_language(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "Bard.png"
            english = Path(directory) / "Bard_en.png"
            czech = Path(directory) / "Bard_cs.png"
            base.touch()
            english.touch()
            czech.touch()

            self.assertEqual(localized_image_path(base, "en"), english)
            self.assertEqual(localized_image_path(base, "cs"), czech)

    def test_legacy_unsuffixed_card_is_the_czech_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "Bard.png"
            english = Path(directory) / "Bard_en.png"
            base.touch()
            english.touch()

            self.assertEqual(localized_image_path(base, "cs"), base)
            self.assertEqual(localized_image_path(base, "en"), english)

    def test_future_language_falls_back_to_english_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "Bard.png"
            english = Path(directory) / "Bard_en.png"
            base.touch()
            english.touch()

            self.assertEqual(localized_image_path(base, "de"), english)


if __name__ == "__main__":
    unittest.main()
