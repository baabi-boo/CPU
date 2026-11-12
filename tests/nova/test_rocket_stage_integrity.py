"""Offline regressions for stage evidence and before/after source integrity.

Subprocesses are mocked and fixtures are disposable. These tests do not compile
or simulate a processor, install tools, or establish hardware qualification.
"""

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import signal
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_rocket_provenance import expected_provenance


SPEC = importlib.util.spec_from_file_location(
    "nova_stage_integrity_target",
    Path(__file__).resolve().parents[2] / "scripts/nova/rocket_baseline.py",
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class StageIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = self.root / "run"
        self.output.mkdir()

    def run_fast_fixture(self, payload=b"fixture\n", *, disk=None, after_wait=None):
        def start(argv, **kwargs):
            kwargs["stdout"].write(payload)

            def wait(timeout):
                if after_wait:
                    after_wait()
                return 0

            return SimpleNamespace(pid=1234, wait=wait)

        def capacity(_root):
            if callable(disk):
                return disk(_root)
            return SimpleNamespace(free=disk if disk is not None else 64 * 1024 ** 3)

        # Disable polling to reproduce a fast exit without timing assumptions
        # or sending a process-group signal to any real process.
        monitor = SimpleNamespace(start=lambda: None, join=lambda timeout: None)
        with patch.object(runner.subprocess, "Popen", side_effect=start), \
             patch.object(runner.threading, "Thread", return_value=monitor), \
             patch.object(runner.shutil, "disk_usage", side_effect=capacity):
            return runner.run_stage(self.root, self.output, "fast", 30,
                                    ["fixture-command"], min_free_gib=10)

    def test_fast_zero_exit_with_oversized_log_fails(self):
        with patch.object(runner, "MAX_STAGE_LOG_BYTES", 32):
            result = self.run_fast_fixture(b"x" * 33)
        self.assertEqual(result["process_exit_code"], 0)
        self.assertNotEqual(result["exit_code"], 0)
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["log_sha256"])
        self.assertIn("limit", result["error"])

    def test_exact_log_limit_is_hashable(self):
        with patch.object(runner, "MAX_STAGE_LOG_BYTES", 32):
            result = self.run_fast_fixture(b"x" * 32)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["log_sha256"], hashlib.sha256(b"x" * 32).hexdigest())

    def test_missing_post_exit_log_fails(self):
        result = self.run_fast_fixture(after_wait=lambda: (self.output / "fast.log").unlink())
        self.assertEqual(result["process_exit_code"], 0)
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["log_sha256"])

    def test_unreadable_post_exit_log_fails_without_disclosing_path(self):
        with patch.object(runner.os, "open", side_effect=PermissionError("private fixture")):
            result = self.run_fast_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("private fixture", result["error"])

    def test_final_disk_floor_catches_fast_exit(self):
        result = self.run_fast_fixture(disk=2 * 1024 ** 3)
        self.assertEqual(result["process_exit_code"], 0)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["blocked"])

    def test_final_unreadable_disk_is_blocked(self):
        def unavailable(_root):
            raise OSError("private fixture")

        result = self.run_fast_fixture(disk=unavailable)
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("private fixture", result["error"])

    def test_log_symlink_is_not_accepted(self):
        source = self.output / "source.log"
        source.write_bytes(b"fixture\n")
        link = self.output / "alias.log"
        link.symlink_to(source)
        digest, error = runner.stage_log_integrity(link)
        self.assertIsNone(digest)
        self.assertIn("regular", error)

    def test_cleanup_waits_remain_bounded(self):
        process = SimpleNamespace(pid=1234, wait=Mock(side_effect=[
            subprocess.TimeoutExpired("fixture", 5),
            subprocess.TimeoutExpired("fixture", 5),
        ]))
        with patch.object(runner.os, "killpg") as kill:
            runner.stop_process_group(process)
        self.assertEqual([call.args[1] for call in kill.call_args_list],
                         [signal.SIGTERM, signal.SIGKILL])
        self.assertEqual([call.kwargs for call in process.wait.call_args_list],
                         [{"timeout": 5}, {"timeout": 5}])

    def test_chisel7_presence_rejected_even_for_zero_or_empty(self):
        for value in ("", "0", "1"):
            with self.subTest(value=value), \
                 patch.dict(runner.os.environ, {"USE_CHISEL7": value}), \
                 patch.object(runner, "clean_source", side_effect=AssertionError("unexpected probe")):
                revision, error = runner.validate_execution(self.root, 10)
            self.assertIsNone(revision)
            self.assertIn("USE_CHISEL7", error)


class ExecutionIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = self.root / "run"
        self.output.mkdir()
        self.binary = self.root / "tests/build/hello.riscv"
        self.binary.parent.mkdir(parents=True)
        header = bytearray(64)
        header[:4] = b"\x7fELF"
        header[4:7] = bytes((2, 1, 1))
        header[18:20] = (243).to_bytes(2, "little")
        self.binary.write_bytes(header)

    def execute_fixture(self, *, before=None, after=None, revision_after="a" * 40,
                        mutate_result=None, mutate_binary=False, steps=None):
        initial = expected_provenance() if before is None else before
        final = copy.deepcopy(initial) if after is None else after

        def stage(root, output, name, seconds, argv, min_free_gib=None):
            payload = (b"Hello world from core 0, a Rocket\n"
                       if name == "hello-simulate" else b"fixture stage\n")
            log = output / (name + ".log")
            log.write_bytes(payload)
            result = {"stage": name, "exit_code": 0, "status": "passed",
                      "log": log.name, "log_sha256": hashlib.sha256(payload).hexdigest()}
            if mutate_result:
                mutate_result(result)
            if mutate_binary and name == "hello-simulate":
                with self.binary.open("ab") as stream:
                    stream.write(b"changed fixture")
            return result

        args = SimpleNamespace(jobs=2, java_heap="4G", build_timeout=7200,
                               test_timeout=300, total_timeout=7200, min_free_gib=10)
        with patch.object(runner, "validate_execution", return_value=("a" * 40, None)), \
             patch.object(runner, "clean_source", return_value=revision_after), \
             patch.object(runner, "make_output_dir", return_value=self.output), \
             patch.object(runner, "collect_provenance", side_effect=[initial, final]), \
             patch.object(runner.shutil, "disk_usage",
                          return_value=SimpleNamespace(free=64 * 1024 ** 3)), \
             patch.object(runner, "run_stage", side_effect=stage) as stages, \
             contextlib.redirect_stdout(io.StringIO()):
            code = runner.execute(self.root, args,
                                  runner.stages(self.root, 2, "4G", 7200, 300)
                                  if steps is None else steps)
        return code, json.loads((self.output / "record.json").read_text()), stages.call_count

    def test_failed_stage_status_overrules_zero_exit(self):
        code, record, count = self.execute_fixture(
            mutate_result=lambda result: result.update(status="failed"))
        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(count, 1)

    def test_missing_stage_hash_rejects_zero_exit(self):
        code, record, count = self.execute_fixture(
            mutate_result=lambda result: result.update(log_sha256=None))
        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(count, 1)

    def test_wrong_stage_hash_rejects_zero_exit(self):
        code, record, _ = self.execute_fixture(
            mutate_result=lambda result: result.update(log_sha256="0" * 64))
        self.assertEqual(code, 1)
        self.assertIn("integrity", record["stages"][0]["error"])

    def test_intact_fixture_remains_explicitly_unqualified(self):
        code, record, count = self.execute_fixture()
        self.assertEqual(code, 0)
        self.assertEqual(count, 4)
        self.assertTrue(record["provenance_unchanged"])
        self.assertEqual(record["provenance"], record["provenance_after"])
        self.assertFalse(record["g1_gate_passed"])
        self.assertFalse(record["hardware_qualified"])

    def test_incomplete_initial_provenance_blocks_all_stages(self):
        provenance = expected_provenance()
        provenance["capture_complete"] = False
        code, record, count = self.execute_fixture(before=provenance)
        self.assertEqual(code, 1)
        self.assertEqual(count, 0)
        self.assertEqual(record["status"], "blocked")

    def test_incomplete_final_provenance_blocks_marker_success(self):
        provenance = expected_provenance()
        provenance["capture_complete"] = False
        code, record, count = self.execute_fixture(after=provenance)
        self.assertEqual(code, 1)
        self.assertEqual(count, 4)
        self.assertEqual(record["status"], "blocked")
        self.assertFalse(record["provenance_unchanged"])

    def test_changed_or_dirty_source_blocks_marker_success(self):
        code, record, _ = self.execute_fixture(revision_after=None)
        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "blocked")
        self.assertTrue(any("source revision" in item for item in record["integrity_errors"]))

    def test_changed_lock_is_not_accepted(self):
        provenance = expected_provenance()
        provenance["lock_hashes"]["conda-reqs/fixture-0.yaml"] = "b" * 64
        code, record, _ = self.execute_fixture(after=provenance)
        self.assertEqual(code, 1)
        self.assertIn("lock_hashes changed during execution", record["integrity_errors"])

    def test_changed_tool_identity_is_not_accepted(self):
        provenance = expected_provenance()
        provenance["tool_versions"]["verilator"] = "different version"
        code, record, _ = self.execute_fixture(after=provenance)
        self.assertEqual(code, 1)
        self.assertIn("tool_versions changed during execution", record["integrity_errors"])

    def test_changed_submodule_inventory_is_not_accepted(self):
        provenance = expected_provenance()
        provenance["submodules"].append({"path": "generators/gemmini", "pin": "c" * 40,
                                         "state": "at_pin", "required": False})
        code, record, _ = self.execute_fixture(after=provenance)
        self.assertEqual(code, 1)
        self.assertIn("submodules changed during execution", record["integrity_errors"])

    def test_changed_target_binary_is_not_accepted(self):
        code, record, _ = self.execute_fixture(mutate_binary=True)
        self.assertEqual(code, 1)
        self.assertEqual(record["status"], "blocked")
        self.assertNotEqual(record["hello_binary_sha256_before_simulation"],
                            record["hello_binary_sha256"])

    def test_empty_campaign_cannot_report_success(self):
        code, record, count = self.execute_fixture(steps=[])
        self.assertEqual(code, 1)
        self.assertEqual(count, 0)
        self.assertEqual(record["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
