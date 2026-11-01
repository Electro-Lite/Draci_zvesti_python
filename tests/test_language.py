import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from py_game.language import (
    CzechLanguage,
    EnglishLanguage,
    get_language,
    next_language_code,
)
from py_game.menu.main_menu import MainMenu
from py_game.settings import AppSettings, SettingsStore


class LanguageTests(unittest.TestCase):
    def test_czech_inherits_missing_text_from_english(self):
        self.assertEqual(CzechLanguage.settings_language, "Jazyk")
        self.assertEqual(
            CzechLanguage.credits_description,
            "Karetní hra a prostředí pro trénování AI",
        )
        self.assertEqual(CzechLanguage.code, "cs")
        self.assertTrue(issubclass(CzechLanguage, EnglishLanguage))

    def test_unknown_language_falls_back_to_english(self):
        language = get_language("unknown")
        self.assertIsInstance(language, EnglishLanguage)
        self.assertEqual(language.text("main_play"), "Play")

    def test_language_cycle_wraps_in_both_directions(self):
        self.assertEqual(next_language_code("en"), "cs")
        self.assertEqual(next_language_code("cs"), "en")
        self.assertEqual(next_language_code("en", -1), "cs")

    def test_language_setting_round_trips_and_old_files_default_to_english(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = SettingsStore(path)
            store.save(AppSettings(language="cs"))
            self.assertEqual(store.load().language, "cs")

            path.write_text(json.dumps({"width": 1024, "height": 768}))
            self.assertEqual(store.load().language, "en")

    def test_main_menu_labels_follow_active_language(self):
        language = CzechLanguage()
        game = SimpleNamespace(
            DISPLAY_W=1280,
            DISPLAY_H=720,
            TEXT_SMALL=16,
            TEXT_NORMAL=24,
            TEXT_LARGE=40,
            palette=SimpleNamespace(muted=(0, 0, 0)),
            tr=language.text,
        )
        self.assertEqual(MainMenu(game)._items()[0], "Hrát")

    def test_deck_editor_and_training_surfaces_have_czech_labels(self):
        language = CzechLanguage()
        expected = {
            "editor_name_deck": "Pojmenovat balíček",
            "editor_inspect": "Prohlédnout vybranou kartu",
            "training_title": "Trénování AI",
            "training_runs_title": "Trénovací běhy",
            "training_about_title": "O trénování AI",
            "training_failed": "Trénování nebylo dokončeno",
            "evolution_completed_evidence": "DOSTUPNÁ DATA BĚHU",
        }
        for key, text in expected.items():
            with self.subTest(key=key):
                self.assertEqual(language.text(key), text)


if __name__ == "__main__":
    unittest.main()
