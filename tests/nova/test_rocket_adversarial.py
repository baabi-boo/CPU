"""Negative controls for the opt-in Rocket baseline smoke runner.

Only mocked subprocesses and disposable fixtures are used. These tests cannot
establish NOVA HDL elaboration, CPU execution, or gate acceptance.
"""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "nova_rocket_adversarial_target",
    Path(__file__).resolve().parents[2] / "scripts/nova/rocket_baseline.py",
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def elf_fixture(path, *, machine=243, elf_class=2):
    """Write only enough of an ELF header for a safe architecture probe."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4] = elf_class
    header[5] = 1  # little-endian
    header[6] = 1  # ELF version
    header[16:18] = (2).to_bytes(2, "little")
    header[18:20] = machine.to_bytes(2, "little")
    path.write_bytes(header)


def budget():
    return SimpleNamespace(jobs=2, java_heap="4G", build_timeout=7200,
                           test_timeout=300, total_timeout=7200, min_free_gib=10)


class RocketAdversarialTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = self.root / "recorded-run"
        self.output.mkdir()
        self.binary = self.root / "tests/build/hello.riscv"

    def fake_successful_stage(self, *, hello_output=b"Hello world from core 0, a Rocket\n"):
        def fake(root, output, name, seconds, argv, min_free_gib=None):
            log = output / f"{name}.log"
            log.write_bytes(hello_output if name == "hello-simulate" else b"stage ended\n")
            return {"stage": name, "exit_code": 0, "status": "passed",
                    "log": log.name, "log_sha256": runner.digest(log)}
        return fake

    def mocked_execute(self, side_effect):
        from test_rocket_provenance import expected_provenance

        with patch.object(runner, "validate_execution", return_value=("a" * 40, None)), \
             patch.object(runner, "clean_source", return_value="a" * 40), \
             patch.object(runner, "collect_provenance", return_value=expected_provenance()), \
             patch.object(runner, "make_output_dir", return_value=self.output), \
             patch.object(runner.shutil, "disk_usage",
                          return_value=SimpleNamespace(free=64 * 1024 ** 3)), \
             patch.object(runner, "run_stage", side_effect=side_effect), \
             contextlib.redirect_stdout(io.StringIO()):
            result = runner.execute(self.root, budget(),
                                    runner.stages(self.root, 2, "4G", 7200, 300))
        return result, json.loads((self.output / "record.json").read_text(encoding="utf-8"))

    def test_zero_exit_without_hello_marker_must_not_pass_smoke(self):
        elf_fixture(self.binary)
        status, record = self.mocked_execute(
            self.fake_successful_stage(hello_output=b"simulator started and exited normally\n"))
        self.assertNotEqual(status, 0)
        self.assertNotEqual(record["status"], "smoke_completed_not_gate_accepted")
        self.assertFalse(record["g1_gate_passed"])

    def test_zero_exit_with_wrong_hello_text_must_not_pass_smoke(self):
        elf_fixture(self.binary)
        status, record = self.mocked_execute(
            self.fake_successful_stage(hello_output=b"Hello world from the wrong test\n"))
        self.assertNotEqual(status, 0)
        self.assertNotEqual(record["status"], "smoke_completed_not_gate_accepted")

    def test_echoed_hello_marker_is_not_independent_target_completion(self):
        """A make/simulator log can echo this text without a target exiting."""
        elf_fixture(self.binary)
        status, record = self.mocked_execute(
            self.fake_successful_stage(hello_output=b"make: echo Hello world from core 0, a Rocket\n"))
        self.assertFalse(record["g1_gate_passed"])
        self.assertFalse(record["hardware_qualified"])
        self.assertIs(record["observations"].get("target_completion_verified"), False)
        self.assertNotEqual(record["status"], "smoke_completed_not_gate_accepted")

    def test_external_symlink_is_not_accepted_as_riscv_binary(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "outside.riscv"
            elf_fixture(external)
            self.binary.parent.mkdir(parents=True, exist_ok=True)
            self.binary.symlink_to(external)
            self.assertIsNone(runner.safe_hello_binary(self.root))

    def test_ignored_stale_build_directory_blocks_before_execution(self):
        """Git worktree cleanliness cannot prove generated inputs are fresh."""
        self.binary.parent.mkdir(parents=True, exist_ok=True)
        (self.root / "env.sh").write_text("# fixture only\n", encoding="utf-8")
        riscv = self.root / "riscv"
        riscv.mkdir()
        with patch.object(runner, "clean_source", return_value="a" * 40), \
             patch.dict(runner.os.environ, {"RISCV": str(riscv)}), \
             patch.object(runner.shutil, "which", return_value="/usr/bin/timeout"), \
             patch.object(runner.shutil, "disk_usage",
                          return_value=SimpleNamespace(free=64 * 1024 ** 3)), \
             patch.object(runner, "command", return_value=SimpleNamespace(returncode=0)):
            revision, error = runner.validate_execution(self.root, 10)
        self.assertIsNone(revision)
        self.assertIsNotNone(error)
        self.assertTrue(any(word in error.lower() for word in ("stale", "generated", "artifact", "build")))

    def test_stale_simulator_output_is_explicitly_detected(self):
        for relative in ("sims/verilator/generated-src", "sims/verilator/output"):
            with self.subTest(path=relative):
                target = self.root / relative
                target.mkdir(parents=True)
                self.assertTrue(runner.stale_build_artifacts(self.root))
                target.rmdir()

    def test_log_directory_failure_is_a_recordable_stage_failure(self):
        missing = self.root / "missing-output-directory"
        with patch.object(runner.subprocess, "Popen",
                          side_effect=AssertionError("should not launch subprocess")):
            result = runner.run_stage(self.root, missing, "not-started", 15, ["make"])
        self.assertEqual(result["status"], "failed")
        self.assertNotEqual(result["exit_code"], 0)

    def test_wrong_elf_class_and_machine_fail_before_smoke_acceptance(self):
        for name, machine, elf_class in (("x86_64", 62, 2), ("riscv32", 243, 1)):
            with self.subTest(name=name):
                # Each case gets an isolated run directory so record.json cannot be reused.
                run = self.root / ("run-" + name)
                run.mkdir()
                self.output = run
                elf_fixture(self.binary, machine=machine, elf_class=elf_class)
                status, record = self.mocked_execute(self.fake_successful_stage())
                self.assertNotEqual(status, 0)
                self.assertFalse(record["g1_gate_passed"])
                self.assertNotEqual(record["status"], "smoke_completed_not_gate_accepted")

    def test_cross_compiler_selected_before_cmake_project(self):
        configure_argv = runner.stages(self.root, 2, "4G", 7200, 300)[1][2]
        self.assertEqual(configure_argv[0], "cmake")
        self.assertTrue(any("CMAKE_C_COMPILER=riscv64-unknown-elf-gcc" in arg
                            for arg in configure_argv))
        self.assertTrue(any("CMAKE_CXX_COMPILER=riscv64-unknown-elf-g++" in arg
                            for arg in configure_argv))
        self.assertTrue(any("CMAKE_SYSTEM_NAME=Generic" in arg
                            for arg in configure_argv))

    def test_bounded_stage_reports_python_timeout_not_exception(self):
        def timed_out(timeout):
            raise subprocess.TimeoutExpired(cmd=["timeout", "make"], timeout=timeout)

        fake_process = SimpleNamespace(pid=1234, wait=timed_out)
        with patch.object(runner.subprocess, "Popen", return_value=fake_process), \
             patch.object(runner, "stop_process_group") as stopped:
            record = runner.run_stage(self.root, self.output, "hung-build", 15, ["make"])
        stopped.assert_called_once_with(fake_process)
        self.assertNotEqual(record["exit_code"], 0)
        self.assertEqual(record["status"], "failed")
        self.assertTrue((self.output / "hung-build.log").is_file())
        self.assertEqual(record["log_sha256"], runner.digest(self.output / "hung-build.log"))

    def test_modified_repository_provenance_blocks_before_build(self):
        (self.root / "env.sh").write_text("# test fixture\n", encoding="utf-8")
        riscv = self.root / "riscv"
        riscv.mkdir()
        probed = []

        def fake_command(argv, root):
            probed.append(argv)
            if "scripts/nova/check.py" in argv:
                return SimpleNamespace(returncode=1)
            return SimpleNamespace(returncode=0)

        with patch.object(runner, "clean_source", return_value="a" * 40), \
             patch.dict(runner.os.environ, {"RISCV": str(riscv)}), \
             patch.object(runner.shutil, "which", return_value="/usr/bin/timeout"), \
             patch.object(runner.shutil, "disk_usage",
                          return_value=SimpleNamespace(free=64 * 1024 ** 3)), \
             patch.object(runner, "command", side_effect=fake_command):
            revision, error = runner.validate_execution(self.root, 10)
        self.assertIsNone(revision)
        self.assertIsNotNone(error)
        self.assertTrue(any("scripts/nova/check.py" in argv for argv in probed))

    def test_missing_approval_cannot_start_build(self):
        with patch.object(runner, "ROOT", self.root), \
             patch.object(runner.subprocess, "run",
                          side_effect=AssertionError("executed a subprocess")), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                runner.main(["--execute"])
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
