"""Offline tests for the non-mutating prerequisite diagnostic."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "nova_doctor", Path(__file__).resolve().parents[2] / "scripts/nova/doctor.py")
doctor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(doctor)


class DoctorTests(unittest.TestCase):
    def test_default_chisel6_rocket_build_gitlinks_are_required(self):
        # build.sbt's default chipyard baseProjects include these even for a
        # single RocketConfig target. The project graph also pulls in BOOM/PMU,
        # HardFloat's FireSim target utilities and the Chisel 6 DSP/FIRRTL2
        # bridge. Merely initializing the original seven gitlinks was not enough.
        expected = {
            "generators/bar-fetchers", "generators/boom",
            "generators/constellation", "generators/diplomacy",
            "generators/hardfloat", "generators/icenet", "generators/pmu",
            "generators/rerocc", "generators/rocket-chip",
            "generators/rocket-chip-blocks",
            "generators/rocket-chip-inclusive-cache", "generators/shuttle",
            "generators/testchipip", "sims/firesim", "tools/cde",
            "tools/dsptools", "tools/firrtl2", "tools/fixedpoint",
            "tools/rocket-dsp-utils",
        }
        self.assertTrue(expected.issubset(doctor.REQUIRED_SUBMODULES))
        self.assertEqual(len(doctor.REQUIRED_SUBMODULES), 21)

        root = Path(__file__).resolve().parents[2]
        index = doctor.git(root, "ls-files", "--stage", "-z")
        self.assertTrue(index["ok"])
        gitlinks = {entry["path"] for entry in doctor.parse_gitlinks(index["stdout"])}
        self.assertTrue(doctor.REQUIRED_SUBMODULES.issubset(gitlinks))

    def test_g1_verilator_and_hello_submodules_are_required(self):
        # These gitlinks are not optional for the documented G1 build and hello
        # workload, even though some other Chipyard profiles can omit them.
        for path in ("tools/DRAMSim2", "toolchains/libgloss"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as folder, \
                    patch.object(doctor, "git") as git:
                self.assertIn(path, doctor.REQUIRED_SUBMODULES)
                result = doctor.submodule_status(Path(folder), {
                    "path": path, "pin": "a" * 40, "stage": "0"})
                self.assertTrue(result["required"])
                self.assertEqual(result["state"], "uninitialized")
                git.assert_not_called()

    def test_parse_only_gitlinks_and_preserve_spaces(self):
        entries = doctor.parse_gitlinks(
            "100644 abc 0\tREADME.md\0" + "160000 " + "a" * 40 + " 0\tpath with spaces\0")
        self.assertEqual(entries, [{"path": "path with spaces", "pin": "a" * 40, "stage": "0"}])

    def test_malformed_gitlinks_are_rejected(self):
        for value in ("broken", "160000 bad 0\tdep\0", "160000 " + "a" * 40 + " 9\tdep\0",
                      "160000 " + "a" * 40 + " 0\tdep"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                doctor.parse_gitlinks(value)

    def test_empty_or_relative_repository_top_is_rejected(self):
        for output in ("", ".", "relative/path"):
            with self.subTest(output=output):
                self.assertFalse(doctor.is_repository_top(
                    Path.cwd(), {"ok": True, "stdout": output}))

    def test_worktree_status_clean_dirty_and_conflicted(self):
        self.assertEqual(doctor.worktree_state(""), (False, False))
        self.assertEqual(doctor.worktree_state(" M modified\0?? untracked\0"), (True, False))
        self.assertEqual(doctor.worktree_state("UU conflict\0"), (True, True))
        # A rename source is a path, not another porcelain status record.
        self.assertEqual(doctor.worktree_state("R  destination\0UU old name\0"), (True, False))

    def test_malformed_worktree_status_is_rejected(self):
        for value in (" M truncated", "bad\0", "R  new\0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                doctor.worktree_state(value)

    def test_submodule_uninitialized_never_invokes_git(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(doctor, "git") as git:
            result = doctor.submodule_status(Path(folder), {
                "path": "generators/boom", "pin": "a" * 40, "stage": "0"})
            self.assertEqual(result["state"], "uninitialized")
            self.assertTrue(result["required"])
            git.assert_not_called()

    def test_submodule_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "generators/boom"
            target.mkdir(parents=True)
            (target / ".git").touch()
            with patch.object(doctor, "git", side_effect=[
                {"ok": True, "stdout": str(target)}, {"ok": True, "stdout": "b" * 40},
                {"ok": True, "stdout": ""},
            ]):
                result = doctor.submodule_status(root, {
                    "path": "generators/boom", "pin": "a" * 40, "stage": "0"})
            self.assertEqual(result["state"], "mismatch")

    def test_submodule_at_pin(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "optional"
            target.mkdir()
            (target / ".git").touch()
            with patch.object(doctor, "git", side_effect=[
                {"ok": True, "stdout": str(target)}, {"ok": True, "stdout": "a" * 40},
                {"ok": True, "stdout": ""},
            ]):
                result = doctor.submodule_status(root, {
                    "path": "optional", "pin": "a" * 40, "stage": "0"})
            self.assertEqual(result["state"], "at_pin")
            self.assertFalse(result["required"])
            self.assertFalse(result["dirty"])

    def test_initialized_submodule_dirty_conflicted_and_unreadable(self):
        cases = [
            ({"ok": True, "stdout": " M source.v\0"}, "dirty", True),
            ({"ok": True, "stdout": "?? local.v\0"}, "dirty", True),
            ({"ok": True, "stdout": "UU source.v\0"}, "conflict", True),
            ({"ok": False, "error": "read failure"}, "unreadable", None),
            ({"ok": True, "stdout": "truncated"}, "unreadable", None),
        ]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "generators/boom"
            target.mkdir(parents=True)
            (target / ".git").touch()
            for status, state, dirty in cases:
                with self.subTest(state=state, status=status), patch.object(doctor, "git", side_effect=[
                    {"ok": True, "stdout": str(target)},
                    {"ok": True, "stdout": "a" * 40}, status,
                ]):
                    result = doctor.submodule_status(root, {
                        "path": "generators/boom", "pin": "a" * 40, "stage": "0"})
                self.assertEqual(result["state"], state)
                self.assertEqual(result["dirty"], dirty)

    def test_malformed_submodule_head_is_unreadable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "optional"
            target.mkdir()
            (target / ".git").touch()
            with patch.object(doctor, "git", side_effect=[
                {"ok": True, "stdout": str(target)}, {"ok": True, "stdout": "not-a-sha"},
            ]):
                result = doctor.submodule_status(root, {
                    "path": "optional", "pin": "a" * 40, "stage": "0"})
            self.assertEqual(result["state"], "unreadable")

    def test_required_dirty_blocks_strict_optional_dirty_is_recorded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "scripts").mkdir()
            (root / "env.sh").touch()
            (root / "scripts/sbt-launch.jar").touch()
            for dirty_path, expected_blocked in (("generators/boom", True), ("optional", False)):
                paths = sorted(doctor.REQUIRED_SUBMODULES | {"optional"})
                index = "".join("160000 " + "a" * 40 + " 0\t" + path + "\0" for path in paths)
                def module_state(_root, link):
                    dirty = link["path"] == dirty_path
                    return dict(link, required=link["path"] in doctor.REQUIRED_SUBMODULES,
                                state="dirty" if dirty else "at_pin", dirty=dirty)
                with self.subTest(dirty_path=dirty_path), patch.object(doctor, "git", side_effect=[
                    {"ok": True, "stdout": str(root)}, {"ok": True, "stdout": "a" * 40},
                    {"ok": True, "stdout": ""}, {"ok": True, "stdout": index},
                ]), patch.object(doctor, "submodule_status", side_effect=module_state), \
                        patch.object(doctor, "tool_status", return_value={"available": True}):
                    report = doctor.collect(root, environ={"RISCV": str(root)})
                self.assertEqual(bool(report["blockers"]), expected_blocked)
                self.assertTrue(next(row for row in report["submodules"] if row["path"] == dirty_path)["dirty"])
                with patch.object(doctor, "collect", return_value=report), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(doctor.main(["--strict", "--json"]), int(expected_blocked))

    def test_malformed_index_is_a_blocker_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(doctor, "git", side_effect=[
                {"ok": True, "stdout": str(root)}, {"ok": True, "stdout": "a" * 40},
                {"ok": True, "stdout": ""}, {"ok": True, "stdout": "bad index"},
            ]), patch.object(doctor.shutil, "which", return_value=None):
                report = doctor.collect(root, environ={})
        self.assertIn("submodule index output is malformed", report["blockers"])

    def test_submodule_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            result = doctor.submodule_status(Path(folder), {
                "path": "../outside", "pin": "a" * 40, "stage": "0"})
            self.assertEqual(result["state"], "invalid_path")

    def test_submodule_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            result = doctor.submodule_status(Path(folder), {
                "path": "optional", "pin": "a" * 40, "stage": "2"})
            self.assertEqual(result["state"], "conflict")

    def test_timeout_is_diagnostic(self):
        with patch.object(doctor.subprocess, "run", side_effect=subprocess.TimeoutExpired("tool", 5)):
            result = doctor.run_command(["tool", "--version"], Path("."))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "timeout")

    def test_missing_command_is_diagnostic(self):
        with patch.object(doctor.subprocess, "run", side_effect=FileNotFoundError):
            result = doctor.run_command(["missing"], Path("."))
        self.assertFalse(result["ok"])

    def test_commands_use_argv_no_shell_and_timeout(self):
        fake = subprocess.CompletedProcess(["tool"], 0, "v1", "")
        with patch.object(doctor.subprocess, "run", return_value=fake) as run:
            doctor.run_command(["tool", "--version"], Path("."))
        self.assertIsInstance(run.call_args.args[0], list)
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertEqual(run.call_args.kwargs["timeout"], 5)
        self.assertEqual(run.call_args.kwargs["env"]["GIT_OPTIONAL_LOCKS"], "0")

    def test_tool_missing_on_path(self):
        with patch.object(doctor.shutil, "which", return_value=None):
            result = doctor.tool_status("java", ["-version"], Path("."))
        self.assertFalse(result["available"])

    def test_java_environment_echo_is_not_reported(self):
        with patch.object(doctor.shutil, "which", return_value="/java"), \
                patch.object(doctor, "run_command", return_value={
                    "ok": True, "stdout": "", "stderr":
                    "Picked up JAVA_TOOL_OPTIONS: private-value\nopenjdk version 20\n", "error": None}):
            result = doctor.tool_status("java", ["-version"], Path("."))
        self.assertEqual(result["version"], "openjdk version 20")
        self.assertNotIn("private-value", json.dumps(result))

    def test_invalid_root_and_missing_environment_are_reported(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(doctor, "git", return_value={"ok": False, "error": "not git"}), \
                patch.object(doctor.shutil, "which", return_value=None):
            report = doctor.collect(Path(folder), environ={"UNRELATED_SECRET": "private-value"})
        self.assertFalse(report["repository"]["valid"])
        self.assertFalse(report["prerequisites_present"])
        self.assertFalse(report["hardware_qualified"])
        self.assertNotIn("private-value", json.dumps(report))

    def test_strict_exit_and_json_output(self):
        report = {"blockers": ["missing"], "hardware_qualified": False}
        with patch.object(doctor, "collect", return_value=report), contextlib.redirect_stdout(io.StringIO()) as output:
            code = doctor.main(["--json", "--strict"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue()), report)

    def test_non_strict_reports_blockers_without_failing(self):
        with patch.object(doctor, "collect", return_value={"blockers": ["missing"]}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(doctor.main(["--json"]), 0)


if __name__ == "__main__":
    unittest.main()
