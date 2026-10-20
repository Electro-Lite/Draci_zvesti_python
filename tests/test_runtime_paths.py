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
            (bundle / "utils").mkdir(parents=True)
            (bundle / "utils" / "cards.db").write_bytes(b"cards-seed")
            (bundle / "utils" / "decks.db").write_bytes(b"decks-seed")
            persistent = root / "persistent"

            with (
                patch.object(runtime_paths, "PROJECT_ROOT", bundle),
                patch.object(runtime_paths.sys, "frozen", True, create=True),
                patch.dict(os.environ, {"DRACI_ZVESTI_DATA_DIR": str(persistent)}),
            ):
                runtime_paths.initialize_packaged_data()
                decks = persistent / "utils" / "decks.db"
                decks.write_bytes(b"user-data")
                runtime_paths.initialize_packaged_data()

            self.assertEqual(
                (persistent / "utils" / "cards.db").read_bytes(), b"cards-seed"
            )
            self.assertEqual(decks.read_bytes(), b"user-data")
            self.assertTrue((persistent / ".ui_training").is_dir())
            self.assertTrue((persistent / "trained_ai").is_dir())
