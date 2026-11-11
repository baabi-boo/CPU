"""Exercise doctor against disposable local Git repositories, never remotes."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "nova_doctor_integration", Path(__file__).resolve().parents[2] / "scripts/nova/doctor.py")
doctor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(doctor)


@unittest.skipUnless(shutil.which("git"), "Git is required for repository integration tests")
class DoctorGitIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nova-doctor-git-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "super"
        self.root.mkdir()
        self.child = self.root / "generators/boom"
        self.child.mkdir(parents=True)
        # No credentials, remote configuration, hooks, or host Git identity enter
        # these fixtures. The diagnostic itself also runs under this environment.
        self.environment = {
            "PATH": os.environ.get("PATH", ""), "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "NOVA test fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "NOVA test fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        }
        environment_patch = patch.dict(os.environ, self.environment, clear=True)
        environment_patch.start()
        self.addCleanup(environment_patch.stop)
        for directory in (self.root, self.child):
            self.git(directory, "init", "--quiet", "--initial-branch=main", "--template=")
        (self.child / "source.txt").write_text("base\n", encoding="utf-8")
        self.git(self.child, "add", "source.txt")
        self.git(self.child, "commit", "--quiet", "-m", "fixture base")
        self.pin = self.git(self.child, "rev-parse", "HEAD").stdout.strip()
        (self.root / ".gitmodules").write_text(
            '[submodule "fixture"]\n\tpath = generators/boom\n'
            '\turl = ./unused-local-fixture\n', encoding="utf-8")
        self.git(self.root, "add", ".gitmodules")
        self.git(self.root, "update-index", "--add", "--cacheinfo",
                 "160000", self.pin, "generators/boom")
        self.git(self.root, "commit", "--quiet", "-m", "fixture superproject")

    def git(self, directory, *args, check=True):
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=" + os.devnull, "-C", str(directory), *args],
            env=self.environment, capture_output=True, text=True, timeout=10,
            check=False,
        )
        if check:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def state(self, path="generators/boom"):
        output = self.git(self.root, "ls-files", "--stage", "-z").stdout
        entries = doctor.parse_gitlinks(output)
        entry = next(row for row in entries if row["path"] == path)
        return doctor.submodule_status(self.root, entry)

    def test_clean_at_pin_diagnostic_does_not_mutate_index(self):
        indexes = (self.root / ".git/index", self.child / ".git/index")
        before = [path.read_bytes() for path in indexes]
        result = self.state()
        self.assertEqual(result["state"], "at_pin")
        self.assertFalse(result["dirty"])
        self.assertTrue(result["required"])
        self.assertEqual(result["head"], self.pin)
        self.assertEqual([path.read_bytes() for path in indexes], before)

    def test_tracked_modification_is_dirty(self):
        (self.child / "source.txt").write_text("modified\n", encoding="utf-8")
        result = self.state()
        self.assertEqual(result["state"], "dirty")
        self.assertTrue(result["dirty"])
        self.assertEqual(result["head"], self.pin)
        with patch.object(doctor, "TOOLS", {}):
            report = doctor.collect(self.root, environ={})
        self.assertIn("generators/boom: dirty", report["blockers"])
        self.assertFalse(report["hardware_qualified"])

    def test_untracked_file_is_dirty_without_disclosing_name(self):
        (self.child / "private-fixture-note.txt").write_text("fixture only\n", encoding="utf-8")
        result = self.state()
        self.assertEqual(result["state"], "dirty")
        self.assertTrue(result["dirty"])
        self.assertNotIn("private-fixture-note", str(result))

    def test_real_merge_conflict_is_conflict(self):
        self.git(self.child, "checkout", "--quiet", "-b", "alternate")
        (self.child / "source.txt").write_text("alternate\n", encoding="utf-8")
        self.git(self.child, "commit", "--quiet", "-am", "fixture alternate")
        self.git(self.child, "checkout", "--quiet", "main")
        (self.child / "source.txt").write_text("main\n", encoding="utf-8")
        self.git(self.child, "commit", "--quiet", "-am", "fixture main")
        result = self.git(self.child, "merge", "--no-edit", "alternate", check=False)
        self.assertEqual(result.returncode, 1)
        state = self.state()
        self.assertEqual(state["state"], "conflict")
        self.assertTrue(state["dirty"])

    def test_clean_new_commit_is_mismatch(self):
        (self.child / "source.txt").write_text("new revision\n", encoding="utf-8")
        self.git(self.child, "commit", "--quiet", "-am", "fixture new revision")
        result = self.state()
        self.assertEqual(result["state"], "mismatch")
        self.assertFalse(result["dirty"])
        self.assertNotEqual(result["head"], self.pin)

    def test_indexed_module_without_metadata_is_uninitialized(self):
        (self.root / "generators/missing").mkdir()
        self.git(self.root, "update-index", "--add", "--cacheinfo",
                 "160000", self.pin, "generators/missing")
        result = self.state("generators/missing")
        self.assertEqual(result["state"], "uninitialized")
        self.assertIsNone(result["dirty"])

    def test_absorbed_gitfile_submodule_is_at_pin(self):
        self.git(self.root, "submodule", "absorbgitdirs", "generators/boom")
        self.assertTrue((self.child / ".git").is_file())
        result = self.state()
        self.assertEqual(result["state"], "at_pin")
        self.assertFalse(result["dirty"])

    def test_broken_gitfile_metadata_is_unreadable(self):
        self.git(self.root, "submodule", "absorbgitdirs", "generators/boom")
        (self.child / ".git").write_text("gitdir: missing-fixture-metadata\n", encoding="utf-8")
        result = self.state()
        self.assertEqual(result["state"], "unreadable")
        self.assertIsNone(result["dirty"])


if __name__ == "__main__":
    unittest.main()
