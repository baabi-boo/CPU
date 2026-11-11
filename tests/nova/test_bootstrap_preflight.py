"""Offline regression tests for the read-only NOVA-001 bootstrap preflight."""

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "nova_bootstrap_preflight",
    Path(__file__).resolve().parents[2] / "scripts/nova/bootstrap_preflight.py",
)
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def blob_sha1(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def fixture(root):
    """Create a small synthetic pinned-source fixture, without a real Git checkout."""
    originals = {}
    for relative in preflight.CONDA_INPUTS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (b"dependencies:\n  - sysroot_linux-64=2.34\n"
               if relative == "conda-reqs/chipyard-base.yaml"
               else ("fixture " + relative + "\n").encode("utf-8"))
        path.write_bytes(raw)
        originals[relative] = blob_sha1(raw)
    manifest = root / "nova/upstream-lock.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"preserved_blobs": originals}), encoding="utf-8")
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "build-setup.sh").write_text(
        "for version in 2.39 2.34 2.28 2.17 2.12.2 2.12; do\n"
        "  :\ndone\n", encoding="utf-8")
    return originals


def source_git(root):
    def git(_root, *args):
        if args == ("rev-parse", "--show-toplevel"):
            return str(root)
        if args == ("rev-parse", "HEAD"):
            return "a" * 40
        if args == ("status", "--porcelain=v1", "--untracked-files=normal"):
            return ""
        raise AssertionError("unexpected git query: " + repr(args))
    return git


class BootstrapPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.originals = fixture(self.root)

    def collect(self, glibc="2.41", libc="glibc"):
        with patch.object(preflight, "git", side_effect=source_git(self.root)), \
             patch.object(preflight.platform, "libc_ver", return_value=(libc, glibc)), \
             patch.object(preflight.shutil, "which", return_value="/mock/bin/tool"):
            return preflight.collect(self.root)

    def test_glibc_241_would_rewrite_pinned_234(self):
        result = self.collect()
        self.assertEqual(result["host_glibc"], "2.41")
        self.assertEqual(result["pinned_sysroot"], "2.34")
        self.assertEqual(result["setup_selected_sysroot"], "2.39")
        self.assertTrue(result["unsafe_upstream_setup"])
        self.assertIn("upstream setup may rewrite pinned sysroot/Conda locks", result["blockers"])
        self.assertFalse(result["hardware_qualified"])
        self.assertEqual(len(result["lock_hashes"]), len(preflight.CONDA_INPUTS))
        self.assertTrue(all(x["matches_imported_blob"] for x in result["lock_hashes"].values()))

    def test_compatible_glibc_preserves_selected_sysroot(self):
        result = self.collect(glibc="2.34")
        self.assertEqual(result["setup_selected_sysroot"], "2.34")
        self.assertFalse(result["unsafe_upstream_setup"])
        self.assertEqual(result["blockers"], [])
        self.assertTrue(result["repository"]["valid"])

    def test_sysroot_selection_and_invalid_versions(self):
        self.assertEqual(preflight.chosen_sysroot("2.41"), "2.39")
        self.assertEqual(preflight.chosen_sysroot("2.34"), "2.34")
        self.assertEqual(preflight.chosen_sysroot("2.28"), "2.28")
        for value in ("", "2", "2.41-ubuntu", "unknown", "2..41"):
            with self.subTest(value=value):
                self.assertIsNone(preflight.chosen_sysroot(value))

    def test_missing_and_modified_lock_are_blocked(self):
        changed = "conda-reqs/riscv-tools.yaml"
        (self.root / changed).write_text("modified\n", encoding="utf-8")
        missing = "conda-reqs/docs.yaml"
        (self.root / missing).unlink()
        result = self.collect(glibc="2.34")
        self.assertFalse(result["lock_hashes"][changed]["matches_imported_blob"])
        self.assertIn("pinned input has changed: " + changed, result["blockers"])
        self.assertIn("pinned input cannot be verified: " + missing, result["blockers"])
        self.assertNotIn(missing, result["lock_hashes"])

    def test_symlink_escape_is_rejected_before_input_read(self):
        relative = "conda-reqs/riscv-tools.yaml"
        outside = Path(self.temp.name).parent / (self.root.name + "-external-lock")
        try:
            outside.write_text("outside\n", encoding="utf-8")
            (self.root / relative).unlink()
            (self.root / relative).symlink_to(outside)
            result = self.collect(glibc="2.34")
            self.assertIn("pinned input cannot be verified: " + relative, result["blockers"])
        finally:
            outside.unlink(missing_ok=True)

    def test_corrupt_manifest_is_blocked(self):
        manifest = self.root / "nova/upstream-lock.json"
        for body in ("{broken", "{}", json.dumps({"preserved_blobs": {}})):
            with self.subTest(body=body):
                manifest.write_text(body, encoding="utf-8")
                result = self.collect(glibc="2.34")
                self.assertIn("pinned-input manifest unavailable or invalid", result["blockers"])
                self.assertEqual(result["lock_hashes"], {})

    def test_unknown_glibc_is_unsafe_not_a_pass(self):
        result = self.collect(glibc="", libc="other")
        self.assertIsNone(result["host_glibc"])
        self.assertIsNone(result["setup_selected_sysroot"])
        self.assertTrue(result["unsafe_upstream_setup"])
        self.assertIn("host glibc is not identifiable by the preflight", result["warnings"])

    def test_invalid_root_returns_structured_error(self):
        result = preflight.collect(self.root / "not-a-repository")
        self.assertFalse(result["repository"]["valid"])
        self.assertIn("root could not be resolved safely", result["blockers"])
        with patch.object(preflight, "git", return_value=None):
            result = preflight.collect(self.root)
        self.assertIn("root is not a readable repository top-level", result["blockers"])

    def test_cli_json_and_strict_semantics(self):
        with patch.object(preflight, "collect", return_value=self.collect()), \
             contextlib.redirect_stdout(io.StringIO()) as stream:
            code = preflight.main(["--json", "--strict", "--root", str(self.root)])
        payload = json.loads(stream.getvalue())
        self.assertEqual(code, 1)
        self.assertTrue(payload["unsafe_upstream_setup"])
        self.assertEqual(payload["schema_version"], 1)
        safe = self.collect(glibc="2.34")
        with patch.object(preflight, "collect", return_value=safe), \
             contextlib.redirect_stdout(io.StringIO()) as stream:
            code = preflight.main(["--json", "--strict", "--root", str(self.root)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stream.getvalue())["blockers"], [])

    def test_preflight_does_not_mutate_source_files(self):
        before = {relative: (self.root / relative).read_bytes()
                  for relative in preflight.CONDA_INPUTS}
        manifest_before = (self.root / "nova/upstream-lock.json").read_bytes()
        with patch.object(preflight, "git", side_effect=source_git(self.root)), \
             patch.object(preflight.platform, "libc_ver", return_value=("glibc", "2.41")), \
             patch.object(preflight.shutil, "which", return_value=None), \
             patch.object(preflight.subprocess, "run", side_effect=AssertionError("must not spawn")):
            result = preflight.collect(self.root)
        self.assertTrue(result["unsafe_upstream_setup"])
        self.assertEqual(before, {relative: (self.root / relative).read_bytes()
                                  for relative in preflight.CONDA_INPUTS})
        self.assertEqual(manifest_before, (self.root / "nova/upstream-lock.json").read_bytes())
