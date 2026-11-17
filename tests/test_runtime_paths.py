from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from py_game import runtime_paths


class RuntimePathsTests(unittest.TestCase):
    def test_configured_data_root_is_used(self):
        with tempfile.TemporaryDirectory() as directory:
            configured = Path(directory) / "persistent"
            with patch.dict(os.environ, {"DRACI_ZVESTI_DATA_DIR": str(configured)}):
                self.assertEqual(
                    runtime_paths.data_path(".ui_training"),
                    configured / ".ui_training",
                )

    def test_packaged_data_is_seeded_without_overwriting_user_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "bundle"
            (bundle / "data").mkdir(parents=True)
            (bundle / "data" / "cards.db").write_bytes(b"cards-seed")
            (bundle / "data" / "decks.db").write_bytes(b"decks-seed")
            persistent = root / "persistent"

            with (
                patch.object(runtime_paths, "PROJECT_ROOT", bundle),
                patch.object(runtime_paths.sys, "frozen", True, create=True),
                patch.dict(os.environ, {"DRACI_ZVESTI_DATA_DIR": str(persistent)}),
            ):
                runtime_paths.initialize_packaged_data()
                decks = persistent / "data" / "decks.db"
                decks.write_bytes(b"user-data")
                runtime_paths.initialize_packaged_data()

            self.assertEqual(
                (persistent / "data" / "cards.db").read_bytes(), b"cards-seed"
            )
            self.assertEqual(decks.read_bytes(), b"user-data")
            self.assertTrue((persistent / ".ui_training").is_dir())
            self.assertTrue((persistent / "trained_ai").is_dir())

    def test_packaged_data_migrates_legacy_utils_databases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "bundle"
            (bundle / "data").mkdir(parents=True)
            (bundle / "data" / "cards.db").write_bytes(b"cards-seed")
            (bundle / "data" / "decks.db").write_bytes(b"decks-seed")
            persistent = root / "persistent"
            (persistent / "utils").mkdir(parents=True)
            (persistent / "utils" / "cards.db").write_bytes(b"legacy-cards")
            (persistent / "utils" / "decks.db").write_bytes(b"legacy-decks")

            with (
                patch.object(runtime_paths, "PROJECT_ROOT", bundle),
                patch.object(runtime_paths.sys, "frozen", True, create=True),
                patch.dict(os.environ, {"DRACI_ZVESTI_DATA_DIR": str(persistent)}),
            ):
                runtime_paths.initialize_packaged_data()

            self.assertEqual(
                (persistent / "data" / "cards.db").read_bytes(), b"legacy-cards"
            )
            self.assertEqual(
                (persistent / "data" / "decks.db").read_bytes(), b"legacy-decks"
            )
