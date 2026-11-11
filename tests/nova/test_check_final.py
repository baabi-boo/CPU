"""Documentation-enumeration containment regressions, not hardware tests."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nova_check_final", ROOT / "scripts/nova/check.py")
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


class DocumentationContainmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="nova-doc-containment-")
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name)
        self.root = self.parent / "repo"
        (self.root / "docs").mkdir(parents=True)
        for name in check.ROOT_DOCS:
            (self.root / name).write_text("# Fixture\n", encoding="utf-8")

    def test_external_search_root_is_rejected_before_enumeration(self):
        outside = self.parent / "outside"
        outside.mkdir()
        (outside / "private.md").write_text("# Private fixture\n", encoding="utf-8")
        (self.root / "docs/nova").symlink_to(outside, target_is_directory=True)
        with mock.patch.object(Path, "rglob") as scan:
            errors = check.validate(self.root)
        scan.assert_not_called()
        self.assertTrue(any("docs/nova" in error and "escapes repository" in error
                            for error in errors))

    def test_looped_search_root_is_rejected_before_enumeration(self):
        (self.root / "docs/nova").symlink_to("nova", target_is_directory=True)
        with mock.patch.object(Path, "rglob") as scan:
            errors = check.validate(self.root)
        scan.assert_not_called()
        self.assertTrue(any("docs/nova" in error and "symlink loop" in error
                            for error in errors))

    def test_missing_search_root_is_diagnostic(self):
        errors = check.validate(self.root)
        self.assertTrue(any("docs/nova" in error and "directory missing" in error
                            for error in errors))

    def test_file_instead_of_search_directory_is_diagnostic(self):
        (self.root / "docs/nova").write_text("not a directory\n", encoding="utf-8")
        errors = check.validate(self.root)
        self.assertTrue(any("docs/nova" in error and "directory missing" in error
                            for error in errors))

    def test_safe_internal_search_alias_retains_link_validation(self):
        internal = self.root / "internal-docs"
        internal.mkdir()
        (internal / "guide.md").write_text("[missing](absent.md)\n", encoding="utf-8")
        (self.root / "docs/nova").symlink_to(internal, target_is_directory=True)
        original = Path.rglob

        def guarded_scan(path, pattern):
            self.assertTrue(path.resolve().is_relative_to(self.root))
            return original(path, pattern)

        with mock.patch.object(Path, "rglob", guarded_scan):
            errors = check.validate(self.root)
        self.assertTrue(any("guide.md" in error and "missing link target: absent.md" in error
                            for error in errors))

    def test_external_document_file_is_rejected_before_read(self):
        (self.root / "docs/nova").mkdir()
        outside = self.parent / "outside.md"
        outside.write_text("# Private fixture\n", encoding="utf-8")
        (self.root / "docs/nova/guide.md").symlink_to(outside)
        original = Path.read_text

        def guarded_read(path, *args, **kwargs):
            self.assertTrue(path.resolve().is_relative_to(self.root))
            return original(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", guarded_read):
            errors = check.validate(self.root)
        self.assertTrue(any("guide.md" in error and "escapes repository" in error
                            for error in errors))


if __name__ == "__main__":
    unittest.main()
