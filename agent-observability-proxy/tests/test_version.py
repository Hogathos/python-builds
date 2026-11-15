"""Version and changelog consistency tests.

Verifies that repository root metadata files exist, follow semantic
versioning, and document the initial release.
"""
import os
import re
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VERSION_FILE = os.path.join(REPO_ROOT, "VERSION")
CHANGELOG_FILE = os.path.join(REPO_ROOT, "CHANGELOG.md")

SEMVER_REGEX = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class VersionTest(unittest.TestCase):
    def test_version_and_changelog_consistent(self):
        self.assertTrue(os.path.isfile(VERSION_FILE), f"Missing {VERSION_FILE}")
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            version_text = f.read()

        # VERSION contains only 0.1.0
        version = version_text.strip()
        self.assertEqual(version, "0.1.0")
        self.assertTrue(
            SEMVER_REGEX.match(version),
            f"Version '{version}' is not valid semantic versioning (MAJOR.MINOR.PATCH)",
        )
        self.assertIn(version_text, ("0.1.0", "0.1.0\n"))

        self.assertTrue(os.path.isfile(CHANGELOG_FILE), f"Missing {CHANGELOG_FILE}")
        with open(CHANGELOG_FILE, "r", encoding="utf-8") as f:
            changelog_text = f.read()

        self.assertIn("0.1.0", changelog_text)
        self.assertIn("2026-11-15", changelog_text)


if __name__ == "__main__":
    unittest.main()
