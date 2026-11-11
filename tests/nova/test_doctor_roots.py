"""Invalid-root regressions for the read-only prerequisite diagnostic."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/nova/doctor.py"
SPEC = importlib.util.spec_from_file_location("nova_doctor_roots", SCRIPT)
doctor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(doctor)
REPORT_KEYS = {
    "schema_version", "scope", "hardware_qualified", "repository", "submodules",
    "files", "tools", "blockers", "limitations", "riscv", "prerequisites_present",
}


class DoctorRootTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="nova-doctor-roots-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def loop_root(self):
        loop = self.directory / "private-root-loop"
        try:
            loop.symlink_to(loop.name, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlinks unavailable: {type(error).__name__}")
        return loop

    def assert_unresolved_report(self, report):
        self.assertEqual(set(report), REPORT_KEYS)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["repository"],
                         {"valid": False, "revision": None, "dirty": None})
        self.assertFalse(report["hardware_qualified"])
        self.assertFalse(report["prerequisites_present"])
        self.assertEqual(report["blockers"], ["root could not be resolved safely"])
        self.assertEqual(report["files"], {})
        self.assertEqual(report["tools"], [])
        self.assertEqual(report["submodules"], [])
        self.assertIsNone(report["riscv"]["directory_exists"])
        self.assertIn("Root resolution failed; remaining prerequisite checks were not run.",
                      report["limitations"])

    def test_self_referential_root_is_blocked_without_probes(self):
        loop = self.loop_root()
        with patch.object(doctor, "git") as git, \
                patch.object(doctor, "tool_status") as tool_status:
            report = doctor.collect(loop, environ={
                "RISCV": str(self.directory), "PRIVATE_VALUE": "do-not-report"})
        self.assert_unresolved_report(report)
        self.assertTrue(report["riscv"]["set"])
        git.assert_not_called()
        tool_status.assert_not_called()
        self.assertNotIn("private-root-loop", json.dumps(report))
        self.assertNotIn("do-not-report", json.dumps(report))
        self.assertTrue(loop.is_symlink())

    def test_resolution_exceptions_produce_generic_schema_not_private_details(self):
        for error in (OSError("private-path"), PermissionError("private-path"),
                      RuntimeError("private-path"), ValueError("private-path")):
            with self.subTest(error=type(error).__name__), \
                    patch.object(doctor.Path, "resolve", side_effect=error), \
                    patch.object(doctor, "git") as git:
                report = doctor.collect("private-root", environ={})
                self.assert_unresolved_report(report)
                self.assertFalse(report["riscv"]["set"])
                self.assertNotIn("private-path", json.dumps(report))
                self.assertNotIn("private-root", json.dumps(report))
                git.assert_not_called()

    def test_valid_root_keeps_existing_schema_and_prerequisite_semantics(self):
        (self.directory / "scripts").mkdir()
        (self.directory / "env.sh").touch()
        (self.directory / "scripts/sbt-launch.jar").touch()
        index = "".join("160000 " + "a" * 40 + " 0\t" + path + "\0"
                        for path in sorted(doctor.REQUIRED_SUBMODULES))

        def module_state(_root, link):
            return dict(link, required=True, state="at_pin", dirty=False)

        def available_tool(name, _args, _root):
            return {"name": name, "available": True, "version": "fixture",
                    "error": None}

        with patch.object(doctor, "git", side_effect=[
            {"ok": True, "stdout": str(self.directory)},
            {"ok": True, "stdout": "a" * 40},
            {"ok": True, "stdout": ""}, {"ok": True, "stdout": index},
        ]), patch.object(doctor, "submodule_status", side_effect=module_state), \
                patch.object(doctor, "tool_status", side_effect=available_tool):
            report = doctor.collect(self.directory, environ={"RISCV": str(self.directory)})
        self.assertEqual(set(report), REPORT_KEYS)
        self.assertEqual(report["repository"],
                         {"valid": True, "revision": "a" * 40, "dirty": False})
        self.assertEqual(report["riscv"], {"set": True, "directory_exists": True})
        self.assertEqual(report["files"], {"env.sh": True, "scripts/sbt-launch.jar": True})
        self.assertEqual(report["blockers"], [])
        self.assertTrue(report["prerequisites_present"])
        self.assertFalse(report["hardware_qualified"])

    def run_cli(self, root, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--root", str(root), *args],
            cwd=self.directory, capture_output=True, text=True, errors="replace",
            timeout=20, check=False, env={
                "PATH": os.environ.get("PATH", ""), "LC_ALL": "C",
                "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
            },
        )

    def test_loop_root_cli_json_is_diagnostic_normal_and_strict(self):
        loop = self.loop_root()
        for strict in (False, True):
            with self.subTest(strict=strict):
                result = self.run_cli(loop, "--json", *(["--strict"] if strict else []))
                self.assertEqual(result.returncode, int(strict), result.stdout + result.stderr)
                self.assertEqual(result.stderr, "")
                self.assert_unresolved_report(json.loads(result.stdout))
                self.assertNotIn("private-root-loop", result.stdout)
        self.assertTrue(loop.is_symlink())

    def test_loop_root_cli_text_marks_unrun_probe_and_strict_blocks(self):
        loop = self.loop_root()
        for strict in (False, True):
            with self.subTest(strict=strict):
                result = self.run_cli(loop, *(["--strict"] if strict else []))
                self.assertEqual(result.returncode, int(strict), result.stdout + result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertIn("root could not be resolved safely", result.stdout)
                self.assertIn("RISCV directory: not checked", result.stdout)
                self.assertIn("not hardware verification", result.stdout)
                self.assertNotIn("private-root-loop", result.stdout)


if __name__ == "__main__":
    unittest.main()
