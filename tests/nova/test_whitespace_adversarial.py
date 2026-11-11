"""Filesystem and encoding regressions for the offline managed-text check."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nova_whitespace_adversarial", ROOT / "scripts/nova/check_whitespace.py")
WHITESPACE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WHITESPACE)


class WhitespaceAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root = self.parent / "repo"
        self.root.mkdir()
        for name in WHITESPACE.ROOT_FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("clean\n", encoding="utf-8")

    def test_external_file_symlink_is_rejected_before_read(self):
        outside = self.parent / "outside.txt"
        outside.write_text("private fixture\n", encoding="utf-8")
        readme = self.root / "README.md"
        readme.unlink()
        readme.symlink_to(outside)
        original = Path.read_bytes

        def guarded_read(path):
            self.assertTrue(path.resolve().is_relative_to(self.root))
            return original(path)

        with mock.patch.object(Path, "read_bytes", guarded_read):
            errors = WHITESPACE.validate(self.root)
        self.assertTrue(any("README.md: managed path escapes" in error for error in errors))

    def test_external_search_directory_is_rejected_before_glob(self):
        outside = self.parent / "outside-scripts"
        outside.mkdir()
        (outside / "secret.py").write_text("private fixture\n", encoding="utf-8")
        (self.root / "scripts").mkdir()
        (self.root / "scripts/nova").symlink_to(outside, target_is_directory=True)
        original = Path.glob

        def guarded_glob(path, pattern):
            self.assertNotEqual(pattern, "scripts/nova/*.py")
            return original(path, pattern)

        with mock.patch.object(Path, "glob", guarded_glob):
            errors = WHITESPACE.validate(self.root)
        self.assertTrue(any("managed directory escapes repository" in error for error in errors))

    def test_managed_file_symlink_loop_is_diagnostic(self):
        readme = self.root / "README.md"
        readme.unlink()
        readme.symlink_to("README.md")
        errors = WHITESPACE.validate(self.root)
        self.assertTrue(any("README.md" in error for error in errors))

    def test_root_symlink_loop_is_diagnostic(self):
        loop = self.parent / "loop"
        loop.symlink_to("loop", target_is_directory=True)
        self.assertTrue(WHITESPACE.validate(loop))

    def test_search_directory_symlink_loop_is_diagnostic(self):
        (self.root / "docs").mkdir()
        (self.root / "docs/nova").symlink_to("nova", target_is_directory=True)
        self.assertTrue(WHITESPACE.validate(self.root))

    def test_missing_managed_file_is_diagnostic(self):
        (self.root / "AGENTS.md").unlink()
        self.assertTrue(any("AGENTS.md" in error for error in WHITESPACE.validate(self.root)))

    def test_non_utf8_managed_file_is_diagnostic(self):
        (self.root / "README.md").write_bytes(b"invalid \xff\n")
        self.assertTrue(any("README.md" in error for error in WHITESPACE.validate(self.root)))

    def test_unicode_trailing_whitespace_and_final_newline(self):
        errors = WHITESPACE.check_text("first\u00a0\nsecond\u2003", "fixture")
        self.assertEqual(len(errors), 3)
        self.assertIn("fixture: missing final newline", errors)
        self.assertIn("fixture:1: trailing whitespace", errors)
        self.assertIn("fixture:2: trailing whitespace", errors)

    def test_preserved_upstream_files_are_not_decoded(self):
        for name in ("README.chipyard.md", "LICENSE", "LICENSE.SiFive",
                     "docs/nova/upstream/CONTRIBUTING.chipyard.md"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"preserved fixture \xff ")
        self.assertEqual(WHITESPACE.validate(self.root), [])

    def test_safe_internal_file_symlink_remains_supported(self):
        target = self.root / "internal.txt"
        target.write_text("clean\n", encoding="utf-8")
        readme = self.root / "README.md"
        readme.unlink()
        readme.symlink_to("internal.txt")
        self.assertEqual(WHITESPACE.validate(self.root), [])


if __name__ == "__main__":
    unittest.main()
