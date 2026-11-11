"""Offline contract tests for the opt-in Rocket baseline runner.

Only temporary fixtures and mocked subprocesses are used. These tests cannot
compile a processor or qualify the G1 hardware milestone.
"""

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "nova_rocket_baseline",
    Path(__file__).resolve().parents[2] / "scripts/nova/rocket_baseline.py",
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def budget(**overrides):
    values = {
        "jobs": 2, "java_heap": "4G", "build_timeout": 7200,
        "test_timeout": 300, "total_timeout": 7200, "min_free_gib": 10,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class RocketBaselineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def test_default_plan_is_read_only_and_never_executes(self):
        captured = io.StringIO()
        with patch.object(runner, "ROOT", self.root), \
             patch.object(runner.subprocess, "run", side_effect=AssertionError("ran subprocess")), \
             patch.object(runner, "make_output_dir", side_effect=AssertionError("wrote output")), \
             contextlib.redirect_stdout(captured):
            self.assertEqual(runner.main([]), 0)
        plan = json.loads(captured.getvalue())
        self.assertTrue(plan["execute_requires_approved_budget"])
        self.assertTrue(plan["does_not_install_or_initialize_dependencies"])
        self.assertEqual([item["name"] for item in plan["stages"]], [
            "rocket-build", "hello-configure", "hello-build", "hello-simulate",
        ])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_stages_are_explicit_argv_with_bounded_config(self):
        steps = runner.stages(self.root, 1, "3G", 1800, 90)
        self.assertEqual([entry[1] for entry in steps], [1800, 600, 600, 90])
        self.assertIn("CONFIG=RocketConfig", steps[0][2])
        self.assertIn("JAVA_HEAP_SIZE=3G", steps[0][2])
        self.assertIn("-j1", steps[0][2])
        self.assertIn("run-binary-fast", steps[3][2])
        self.assertTrue(steps[3][2][-1].endswith("/tests/build/hello.riscv"))
        self.assertTrue(all(isinstance(argv, list) for _, _, argv in steps))

    def test_execute_needs_explicit_approved_budget(self):
        with patch.object(runner.subprocess, "run", side_effect=AssertionError("ran subprocess")), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                runner.main(["--execute"])
        self.assertEqual(raised.exception.code, 2)

    def test_resource_bounds_reject_invalid_options(self):
        for args in (["--jobs", "0"], ["--jobs", "3"],
                     ["--java-heap", "16G"], ["--build-timeout", "59"],
                     ["--test-timeout", "999"], ["--total-timeout", "299"],
                     ["--min-free-gib", "0"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    runner.main(args)
                self.assertEqual(raised.exception.code, 2)

    def test_clean_source_rejects_dirty_or_wrong_root(self):
        revision = "a" * 40
        for top, dirty in ((str(self.root), " M tests/hello.c\n"),
                           (str(self.root.parent), "")):
            outputs = [SimpleNamespace(returncode=0, stdout=value) for value in
                       (top, revision, dirty)]
            with self.subTest(top=top, dirty=bool(dirty)), \
                 patch.object(runner, "command", side_effect=outputs):
                self.assertIsNone(runner.clean_source(self.root))

    def test_missing_environment_blocks_before_tool_probes(self):
        with patch.object(runner, "clean_source", return_value="a" * 40), \
             patch.dict(runner.os.environ, {"RISCV": ""}), \
             patch.object(runner, "command", side_effect=AssertionError("unexpected doctor")):
            revision, error = runner.validate_execution(self.root, 10)
        self.assertIsNone(revision)
        self.assertIn("RISCV environment", error)

    def test_doctor_failure_blocks_even_with_fake_active_environment(self):
        (self.root / "env.sh").write_text("# fixture only\n", encoding="utf-8")
        riscv = self.root / "riscv"
        riscv.mkdir()
        with patch.object(runner, "clean_source", return_value="a" * 40), \
             patch.dict(runner.os.environ, {"RISCV": str(riscv)}), \
             patch.object(runner.shutil, "which", return_value="/usr/bin/timeout"), \
             patch.object(runner, "command", return_value=SimpleNamespace(returncode=1)):
            revision, error = runner.validate_execution(self.root, 10)
        self.assertIsNone(revision)
        self.assertIn("doctor", error)

    def test_run_stage_records_real_exit_status_and_log_digest(self):
        output = self.root / "logs"
        output.mkdir()
        for exit_code in (0, 124, 2):
            name = "stage" + str(exit_code)

            def fake_popen(argv, **kwargs):
                self.assertEqual(argv[:3], ["timeout", "--kill-after=30s", "45s"])
                self.assertEqual(argv[3:], ["make", "-C", "sims/verilator"])
                self.assertNotIn("shell", kwargs)
                self.assertTrue(kwargs["start_new_session"])
                kwargs["stdout"].write(b"fixture log\n")
                return SimpleNamespace(pid=1234, wait=lambda timeout: exit_code)

            with self.subTest(code=exit_code), patch.object(runner.subprocess, "Popen", side_effect=fake_popen):
                result = runner.run_stage(self.root, output, name, 45,
                                          ["make", "-C", "sims/verilator"])
            self.assertEqual(result["exit_code"], exit_code)
            self.assertEqual(result["status"], "passed" if exit_code == 0 else "failed")
            self.assertEqual(result["log_sha256"], hashlib.sha256(b"fixture log\n").hexdigest())

    def test_execute_stops_at_first_stage_failure_and_keeps_gate_unpassed(self):
        output = self.root / "run"
        output.mkdir()
        first = {"stage": "rocket-build", "exit_code": 124, "status": "failed"}
        with patch.object(runner, "validate_execution", return_value=("a" * 40, None)), \
             patch.object(runner, "make_output_dir", return_value=output), \
             patch.object(runner.shutil, "disk_usage", return_value=SimpleNamespace(free=64 * 1024 ** 3)), \
             patch.object(runner, "run_stage", return_value=first) as stage, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.execute(self.root, budget(), runner.stages(self.root, 2, "4G", 7200, 300)), 1)
        stage.assert_called_once()
        record = json.loads((output / "record.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "failed")
        self.assertEqual(len(record["stages"]), 1)
        self.assertFalse(record["hardware_qualified"])
        self.assertFalse(record["g1_gate_passed"])

    def test_completed_mock_smoke_still_does_not_pass_g1(self):
        output = self.root / "run"
        output.mkdir()
        # A zero-exit no-op simulator is not a successful smoke test. Supply a
        # genuine-looking RV64 ELF header and the expected target output in the
        # fake result, without running any compiler or processor simulator.
        binary = self.root / "tests/build/hello.riscv"
        binary.parent.mkdir(parents=True)
        header = bytearray(64)
        header[:4] = b"\x7fELF"
        header[4] = 2  # ELF64
        header[5] = 1  # little-endian
        header[6] = 1
        header[16:18] = (2).to_bytes(2, "little")
        header[18:20] = (243).to_bytes(2, "little")  # EM_RISCV
        binary.write_bytes(header)

        def fake_stage(root, directory, name, seconds, argv):
            log = directory / f"{name}.log"
            log.write_bytes(b"Hello world from core 0, a Rocket\n"
                            if name == "hello-simulate" else b"fixture stage\n")
            return {"stage": name, "exit_code": 0, "status": "passed",
                    "log": log.name, "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()}

        with patch.object(runner, "validate_execution", return_value=("a" * 40, None)), \
             patch.object(runner, "make_output_dir", return_value=output), \
             patch.object(runner.shutil, "disk_usage", return_value=SimpleNamespace(free=64 * 1024 ** 3)), \
             patch.object(runner, "run_stage", side_effect=fake_stage) as stage, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.execute(self.root, budget(), runner.stages(self.root, 2, "4G", 7200, 300)), 0)
        self.assertEqual(stage.call_count, 4)
        record = json.loads((output / "record.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "hello_marker_observed_unqualified")
        self.assertIs(record["observations"]["target_completion_verified"], False)
        self.assertFalse(record["g1_gate_passed"])
        self.assertFalse(record["hardware_qualified"])


if __name__ == "__main__":
    unittest.main()
