"""Pastikan metadata fork dan hak cipta upstream tetap konsisten."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "Nizwarax/MusangAPI"


class RepositoryMetadataTests(unittest.TestCase):
    def test_update_sources_use_the_selected_repository(self):
        self.assertEqual(json.loads((ROOT / "version.json").read_text())["repo"],
                         f"https://github.com/{REPO}")
        for path in ("app.py", "admin.html", "README.md", "VERSION_REPORTING.md",
                     "deploy/termux/install.sh", "tools/muse2api_cookie_importer.user.js"):
            with self.subTest(path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn(REPO, text)

    def test_author_and_upstream_license(self):
        self.assertIn("Deki_niswara", (ROOT / "README.md").read_text())
        self.assertIn("Deki_niswara", (ROOT / "admin.html").read_text())
        self.assertIn("MUSE2API Authors", (ROOT / "LICENSE").read_text())
        self.assertIn("czg86389-hub/muse2api", (ROOT / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
