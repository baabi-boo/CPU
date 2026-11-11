"""Offline text-contract regressions; these are not a complete YAML parser."""

import importlib.util
from pathlib import Path
import re
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nova_whitespace", ROOT / "scripts/nova/check_whitespace.py")
WHITESPACE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WHITESPACE)


class WhitespaceTests(unittest.TestCase):
    def test_clean_text_and_make_indentation(self):
        self.assertEqual(WHITESPACE.check_text("target:\n\tcommand\n", "fixture"), [])
        self.assertEqual(WHITESPACE.check_text("", "empty"), [])

    def test_trailing_whitespace_and_missing_newline(self):
        errors = WHITESPACE.check_text("line \nsecond\t", "fixture")
        self.assertEqual(len(errors), 3)
        self.assertIn("fixture:1: trailing whitespace", errors)
        self.assertIn("fixture: missing final newline", errors)

    def test_scope_excludes_preserved_upstream_and_generated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("docs/nova/a.md", "docs/nova/upstream/old.md",
                         "scripts/nova/a.py", "scripts/nova/__pycache__/a.pyc",
                         "nova/a.json", "README.chipyard.md", "LICENSE"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            names = {str(path.relative_to(root)) for path in WHITESPACE.managed_paths(root)}
            self.assertIn("docs/nova/a.md", names)
            self.assertIn("scripts/nova/a.py", names)
            self.assertIn("nova/a.json", names)
            for name in ("docs/nova/upstream/old.md", "README.chipyard.md",
                         "LICENSE", "scripts/nova/__pycache__/a.pyc"):
                self.assertNotIn(name, names)

    def test_nonexistent_root_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(WHITESPACE.validate(Path(tmp) / "missing"))

    def test_current_managed_files_are_clean(self):
        self.assertEqual(WHITESPACE.validate(ROOT), [])


class CIContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/nova-foundation.yml").read_text(encoding="utf-8")

    def test_checkout_is_pinned_and_credentials_are_not_persisted(self):
        uses = re.findall(r"^\s*uses:\s*(\S+)", self.workflow, re.MULTILINE)
        self.assertEqual(uses, ["actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"])
        self.assertRegex(self.workflow, r"persist-credentials:\s*false")
        self.assertRegex(self.workflow, r"submodules:\s*false")

    def test_foundation_has_readonly_permissions_and_no_privileged_trigger(self):
        self.assertRegex(self.workflow, r"(?m)^permissions:\n  contents: read\n")
        self.assertNotRegex(self.workflow, r"(?m)^\s*(?:contents|packages|actions|id-token):\s*write")
        self.assertNotIn("write-all", self.workflow)
        self.assertNotIn("pull_request_target", self.workflow)
        self.assertNotIn("secrets.", self.workflow)
        self.assertNotIn("secrets:", self.workflow)

    def test_bounded_repository_only_job(self):
        self.assertIn("timeout-minutes: 5", self.workflow)
        self.assertIn("runs-on: ubuntu-24.04", self.workflow)
        self.assertIn("run: make -f nova.mk check", self.workflow)
        for command in ("build-setup.sh", "sims/verilator", "docker push", "pip install"):
            self.assertNotIn(command, self.workflow)

    def test_upstream_entry_points_remain_guarded(self):
        guard = "github.repository == 'ucb-bar/chipyard'"
        for name in ("pr-ci.yml", "build-and-publish-container.yml"):
            content = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            conditions = re.findall(r"(?m)^\s*if:\s*(.+)$", content)
            self.assertTrue(any(guard in condition for condition in conditions), name)
        dispatcher = (ROOT / ".github/workflows/pr-ci.yml").read_text(encoding="utf-8")
        self.assertEqual(dispatcher.count("needs: check-ci-disable"), 6)

    def test_make_checks_committed_text_and_worktree_diff(self):
        makefile = (ROOT / "nova.mk").read_text(encoding="utf-8")
        self.assertIn("$(PYTHON) -B scripts/nova/check_whitespace.py", makefile)
        self.assertIn("git diff --check", makefile)


if __name__ == "__main__":
    unittest.main()
