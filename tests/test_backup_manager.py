import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import backup_manager


class BackupManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "workspace"
        (self.root / "data" / "reference").mkdir(parents=True)
        with closing(sqlite3.connect(self.root / "data" / "workbench.db")) as conn:
            conn.execute("CREATE TABLE saved(value TEXT)")
            conn.execute("INSERT INTO saved VALUES('original')")
            conn.commit()
        (self.root / "data" / "ai_feedback.jsonl").write_text(
            '{"accepted": true}\n', encoding="utf-8"
        )
        (self.root / "data" / "reference" / "library.json").write_text(
            '{"records": 3}', encoding="utf-8"
        )
        (self.root / "data" / "chrome-profile").mkdir()
        (self.root / "data" / "chrome-profile" / "Cookies").write_text(
            "secret", encoding="utf-8"
        )
        self.archive = Path(self.tmp.name) / "research.leadbackup"

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_excludes_browser_login_profile_and_restores_database(self):
        manifest = backup_manager.create(self.root, self.archive)
        names = {item["path"] for item in manifest["files"]}
        self.assertIn("data/workbench.db", names)
        self.assertNotIn("data/chrome-profile/Cookies", names)
        with closing(sqlite3.connect(self.root / "data" / "workbench.db")) as conn:
            conn.execute("UPDATE saved SET value='changed'")
            conn.commit()
        result = backup_manager.restore(self.root, self.archive)
        with closing(sqlite3.connect(self.root / "data" / "workbench.db")) as conn:
            self.assertEqual("original", conn.execute("SELECT value FROM saved").fetchone()[0])
        self.assertTrue(Path(result["safety_backup"]).is_file())

    def test_restore_rejects_unexpected_archive_file(self):
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format": backup_manager.FORMAT,
                        "files": [{"path": "../escape.txt", "bytes": 1, "sha256": "x"}],
                    }
                ),
            )
            archive.writestr("../escape.txt", "x")
        with self.assertRaises(ValueError):
            backup_manager.restore(self.root, self.archive)

    def test_personal_mode_includes_browser_profile_and_protected_credentials(self):
        with patch.object(
            backup_manager,
            "_export_credentials",
            side_effect=lambda target: (
                target.parent.mkdir(parents=True, exist_ok=True),
                target.write_bytes(b"protected"),
            ),
        ):
            manifest = backup_manager.create(
                self.root, self.archive, personal=True
            )
        names = {item["path"] for item in manifest["files"]}
        self.assertIn("data/chrome-profile/Cookies", names)
        self.assertIn(backup_manager.PRIVATE_CREDENTIAL, names)
        self.assertTrue(manifest["personal"])


if __name__ == "__main__":
    unittest.main()
