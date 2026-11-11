"""Adversarial, offline tests for NOVA-001's read-only bootstrap preflight."""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nova_bootstrap_adversarial_target", ROOT / "scripts/nova/bootstrap_preflight.py")
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def source_git(root, *, dirty=False):
    def query(_root, *args):
        if args == ("rev-parse", "--show-toplevel"):
            return str(root)
        if args == ("rev-parse", "HEAD"):
            return "a" * 40
        if args == ("status", "--porcelain=v1", "--untracked-files=normal"):
            return " M tracked-file\n" if dirty else ""
        raise AssertionError("unexpected Git command")
    return query


class BootstrapAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nova-adversarial-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        original = {}
        for relative in preflight.CONDA_INPUTS:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = (b"dependencies:\n  - sysroot_linux-64=2.34\n"
                   if relative == "conda-reqs/chipyard-base.yaml"
                   else ("fixture " + relative + "\n").encode("utf-8"))
            path.write_bytes(raw)
            original[relative] = git_blob(raw)
        manifest = self.root / "nova/upstream-lock.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"preserved_blobs": original}), encoding="utf-8")
        scripts = self.root / "scripts"
        scripts.mkdir()
        (scripts / "build-setup.sh").write_text(
            "for version in 2.39 2.34 2.28 2.17 2.12.2 2.12; do\n  :\ndone\n",
            encoding="utf-8")

    def collect(self, *, dirty=False, glibc="2.34"):
        with patch.object(preflight, "git", side_effect=source_git(self.root, dirty=dirty)), \
             patch.object(preflight.platform, "libc_ver", return_value=("glibc", glibc)), \
             patch.object(preflight.shutil, "which", return_value="/mock/bin/tool"):
            return preflight.collect(self.root)

    def test_text_output_counts_only_matching_pinned_inputs(self):
        changed = self.root / "conda-reqs/riscv-tools.yaml"
        changed.write_text("different input\n", encoding="utf-8")
        report = self.collect()
        self.assertEqual(len(report["lock_hashes"]), len(preflight.CONDA_INPUTS))
        self.assertEqual(sum(item["matches_imported_blob"]
                             for item in report["lock_hashes"].values()), 8)
        output = io.StringIO()
        with patch.object(preflight, "collect", return_value=report), \
             contextlib.redirect_stdout(output):
            self.assertEqual(preflight.main([]), 0)
        self.assertIn("Verified pinned inputs: 8 of 9", output.getvalue())
        self.assertNotIn("Verified pinned inputs: 9 of 9", output.getvalue())

    def test_self_referential_manifest_symlink_yields_blocker_not_traceback(self):
        manifest = self.root / "nova/upstream-lock.json"
        manifest.unlink()
        manifest.symlink_to("upstream-lock.json")
        report = self.collect()
        self.assertIn("pinned-input manifest unavailable or invalid", report["blockers"])
        self.assertEqual(report["lock_hashes"], {})
        self.assertIs(report["hardware_qualified"], False)

    def test_oversized_version_component_is_rejected_without_exception(self):
        malformed = "2." + "9" * 5000
        self.assertIsNone(preflight.version_tuple(malformed))
        self.assertIsNone(preflight.chosen_sysroot(malformed))
        report = self.collect(glibc=malformed)
        self.assertTrue(report["unsafe_upstream_setup"])
        self.assertIsNone(report["setup_selected_sysroot"])

    def test_dirty_source_is_rejected_by_strict_qualification(self):
        report = self.collect(dirty=True)
        self.assertTrue(report["repository"]["dirty"])
        self.assertTrue(any("uncommitted" in item.lower() or "dirty" in item.lower()
                            for item in report["blockers"]))
        output = io.StringIO()
        with patch.object(preflight, "collect", return_value=report), \
             contextlib.redirect_stdout(output):
            self.assertEqual(preflight.main(["--strict", "--json"]), 1)
        self.assertIs(json.loads(output.getvalue())["repository"]["dirty"], True)

    def test_sysroot_candidate_order_matches_upstream_script(self):
        setup = (ROOT / "scripts/build-setup.sh").read_text(encoding="utf-8")
        match = re.search(r"(?m)^\s*for version in ([0-9. ]+); do\s*$", setup)
        self.assertIsNotNone(match)
        self.assertEqual(tuple(match.group(1).split()), tuple(preflight.SETUP_SYSROOTS))

    def test_changed_upstream_selector_fails_closed(self):
        scripts = self.root / "scripts"
        (scripts / "build-setup.sh").write_text(
            "for version in 2.99 2.34; do\n  :\ndone\n", encoding="utf-8")
        report = self.collect()
        self.assertIn("upstream setup sysroot selector cannot be verified",
                      report["blockers"])
        self.assertTrue(report["unsafe_upstream_setup"])
        self.assertIsNone(report["setup_selected_sysroot"])

    def test_missing_setup_script_is_strict_blocker(self):
        (self.root / "scripts/build-setup.sh").unlink()
        report = self.collect()
        self.assertIn("upstream setup sysroot selector cannot be verified",
                      report["blockers"])
        self.assertTrue(report["unsafe_upstream_setup"])
        output = io.StringIO()
        with patch.object(preflight, "collect", return_value=report), \
             contextlib.redirect_stdout(output):
            self.assertEqual(preflight.main(["--json", "--strict"]), 1)
        self.assertNotIn(str(self.root), output.getvalue())

    def test_symlinked_setup_script_outside_repository_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="nova-external-setup-") as outside:
            external = Path(outside) / "build-setup.sh"
            external.write_text(
                "for version in 2.39 2.34 2.28 2.17 2.12.2 2.12; do\n"
                "  :\ndone\n", encoding="utf-8")
            setup = self.root / "scripts/build-setup.sh"
            setup.unlink()
            setup.symlink_to(external)
            report = self.collect()
            self.assertIn("upstream setup sysroot selector cannot be verified",
                          report["blockers"])
            self.assertNotIn(str(external), json.dumps(report))

    def test_git_queries_disable_fsmonitor_hooks_and_lazy_fetch(self):
        # Source diagnostics must not invoke an untrusted checkout's configured
        # fsmonitor hook or lazy-fetch a missing object over the network.
        with patch.object(preflight.subprocess, "run", return_value=Mock(
                returncode=0, stdout="")) as process:
            self.assertEqual(preflight.git(self.root, "status", "--porcelain=v1"), "")
        argv = process.call_args.args[0]
        self.assertIn("core.fsmonitor=false", argv)
        self.assertIn("core.hooksPath=/dev/null", argv)
        self.assertIn("submodule.recurse=false", argv)
        environment = process.call_args.kwargs["env"]
        self.assertEqual(environment.get("GIT_NO_LAZY_FETCH"), "1")
        self.assertEqual(environment.get("GIT_TERMINAL_PROMPT"), "0")

    def test_json_and_text_omit_sensitive_environment_and_root(self):
        secret = "NOVA_SECRET_VALUE_NEVER_REPORT"
        report = self.collect()
        with patch.dict(os.environ, {"NOVA_INTERNAL_CREDENTIAL": secret}), \
             patch.object(preflight, "collect", return_value=report):
            for args in ([], ["--json"]):
                with self.subTest(args=args):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        self.assertEqual(preflight.main(args), 0)
                    result = output.getvalue()
                    self.assertNotIn(secret, result)
                    self.assertNotIn(str(self.root), result)


if __name__ == "__main__":
    unittest.main()
