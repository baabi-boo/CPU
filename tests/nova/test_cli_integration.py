"""Bounded subprocess checks of NOVA's offline diagnostic CLI contracts."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CHECKS = ("check.py", "check_whitespace.py")
CLIS = CHECKS + ("doctor.py",)
CLI_TIMEOUT_SECONDS = 45


class CliIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nova-cli-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.cwd = self.directory / "external-working-directory"
        self.cwd.mkdir()
        # Keep host Git configuration and Python startup settings out of the
        # contract tests. Only version queries and read-only Git queries run.
        self.environment = {
            "PATH": os.environ.get("PATH", ""),
            "LC_ALL": "C",
            "PYTHONDONTWRITEBYTECODE": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_OPTIONAL_LOCKS": "0",
        }

    def run_cli(self, script, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts/nova" / script),
             *(str(argument) for argument in args)],
            cwd=self.cwd, env=self.environment, capture_output=True,
            text=True, errors="replace", timeout=CLI_TIMEOUT_SECONDS,
            check=False,
        )
        self.assertNotIn("Traceback (most recent call last)",
                         result.stdout + result.stderr)
        return result

    def assert_exit(self, result, expected):
        self.assertEqual(result.returncode, expected,
                         result.stdout + result.stderr)

    def snapshot(self):
        return {
            path.relative_to(self.directory).as_posix():
            None if path.is_dir() else path.read_bytes()
            for path in self.directory.rglob("*")
        }

    def assert_report(self, result):
        self.assertEqual(result.stderr, "")
        report = json.loads(result.stdout)
        self.assertIsInstance(report, dict)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["scope"], "prerequisite diagnostics only")
        self.assertIs(report["hardware_qualified"], False)
        self.assertIsInstance(report["blockers"], list)
        self.assertTrue(all(isinstance(value, str) for value in report["blockers"]))
        self.assertEqual(report["prerequisites_present"], not report["blockers"])
        return report

    def test_all_cli_help_from_external_directory(self):
        before = self.snapshot()
        for script in CLIS:
            with self.subTest(script=script):
                result = self.run_cli(script, "--help")
                self.assert_exit(result, 0)
                self.assertIn("usage:", result.stdout)
                self.assertIn("--root", result.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_all_cli_default_roots_ignore_working_directory(self):
        before = self.snapshot()
        for script in CHECKS:
            with self.subTest(script=script):
                result = self.run_cli(script)
                self.assert_exit(result, 0)
                self.assertIn("checks passed", result.stdout)
        result = self.run_cli("doctor.py", "--json")
        self.assert_exit(result, 0)
        report = self.assert_report(result)
        self.assertTrue(report["repository"]["valid"])
        self.assertRegex(report["repository"]["revision"], r"^[0-9a-f]{40}$")
        self.assertEqual(self.snapshot(), before)

    def test_explicit_valid_root_checks_from_external_directory(self):
        before = self.snapshot()
        for script in CHECKS:
            with self.subTest(script=script):
                result = self.run_cli(script, "--root", ROOT)
                self.assert_exit(result, 0)
                self.assertIn("checks passed", result.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_nonexistent_root_checks_fail_without_creating_it(self):
        missing = self.directory / "nonexistent-root"
        before = self.snapshot()
        for script in CHECKS:
            with self.subTest(script=script):
                result = self.run_cli(script, "--root", missing)
                self.assert_exit(result, 1)
                self.assertIn("ERROR:", result.stdout + result.stderr)
                self.assertIn(str(missing), result.stdout + result.stderr)
        self.assertFalse(missing.exists())
        self.assertEqual(self.snapshot(), before)

    def test_malformed_root_checks_do_not_write_inside_or_beside_fixture(self):
        fixture = self.directory / "malformed-root"
        (fixture / "nova").mkdir(parents=True)
        (fixture / "nova/project.json").write_text("{not-json\n", encoding="utf-8")
        (fixture / "README.md").write_text("Malformed fixture   \n", encoding="utf-8")
        (self.directory / "outside-root-sentinel.txt").write_text(
            "This file is outside the supplied repository root.\n", encoding="utf-8")
        before = self.snapshot()
        for script in CHECKS:
            with self.subTest(script=script):
                result = self.run_cli(script, "--root", fixture)
                self.assert_exit(result, 1)
                self.assertIn("ERROR:", result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_doctor_normal_and_strict_json_agree_on_reported_blockers(self):
        before = self.snapshot()
        normal_result = self.run_cli("doctor.py", "--root", ROOT, "--json")
        strict_result = self.run_cli("doctor.py", "--root", ROOT, "--json", "--strict")
        self.assert_exit(normal_result, 0)
        normal = self.assert_report(normal_result)
        strict = self.assert_report(strict_result)
        self.assert_exit(strict_result, 1 if strict["blockers"] else 0)
        # The installed toolchain and initialized submodules can vary; assert
        # agreement, never a fixed count or a supposedly qualified processor.
        self.assertEqual(normal["blockers"], strict["blockers"])
        self.assertEqual(self.snapshot(), before)

    def test_doctor_missing_root_json_is_diagnostic_in_both_modes(self):
        missing = self.directory / "missing-doctor-root"
        before = self.snapshot()
        for strict in (False, True):
            with self.subTest(strict=strict):
                args = ["--root", missing, "--json"]
                if strict:
                    args.append("--strict")
                result = self.run_cli("doctor.py", *args)
                self.assert_exit(result, 1 if strict else 0)
                report = self.assert_report(result)
                self.assertFalse(report["repository"]["valid"])
                self.assertTrue(report["blockers"])
                self.assertIn("root is not a readable repository root", report["blockers"])
        self.assertFalse(missing.exists())
        self.assertEqual(self.snapshot(), before)

    def test_all_cli_unknown_options_fail_cleanly(self):
        before = self.snapshot()
        for script in CLIS:
            with self.subTest(script=script):
                result = self.run_cli(script, "--not-a-nova-option")
                self.assert_exit(result, 2)
                self.assertIn("usage:", result.stderr)
                self.assertIn("unrecognized arguments:", result.stderr)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
