"""Disposable process fixtures for legacy runner cancellation, not CPU evidence."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


RUNNER_PATH = Path(__file__).resolve().parents[2] / "scripts/nova/rocket_baseline.py"
SPEC = importlib.util.spec_from_file_location("nova_cancellation_target", RUNNER_PATH)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class RocketCancellationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.logs = self.root / "logs"
        self.logs.mkdir()

    def stage(self):
        return runner.run_stage(self.root, self.logs, "fixture", 10, ["fixture"])

    def test_forced_timeout_keeps_actual_status_separate(self):
        process = SimpleNamespace(
            pid=1234, wait=Mock(side_effect=subprocess.TimeoutExpired("fixture", 50)),
            poll=lambda: -signal.SIGKILL)
        with patch.object(runner.subprocess, "Popen", return_value=process), \
             patch.object(runner, "stop_process_group") as stop:
            result = self.stage()
        stop.assert_called_once_with(process)
        self.assertEqual(result["exit_code"], 124)
        self.assertEqual(result["process_exit_code"], -signal.SIGKILL)
        self.assertEqual(result["status"], "failed")

    def test_keyboard_interrupt_keeps_actual_status_separate(self):
        process = SimpleNamespace(pid=1234, wait=Mock(side_effect=KeyboardInterrupt),
                                  poll=lambda: -signal.SIGTERM)
        with patch.object(runner.subprocess, "Popen", return_value=process), \
             patch.object(runner, "stop_process_group") as stop:
            result = self.stage()
        stop.assert_called_once_with(process)
        self.assertEqual(result["exit_code"], 130)
        self.assertEqual(result["process_exit_code"], -signal.SIGTERM)
        self.assertNotEqual(result["status"], "passed")

    def test_unavailable_actual_exit_is_not_normalized(self):
        process = SimpleNamespace(
            pid=1234, wait=Mock(side_effect=subprocess.TimeoutExpired("fixture", 50)),
            poll=lambda: None)
        with patch.object(runner.subprocess, "Popen", return_value=process), \
             patch.object(runner, "stop_process_group"):
            result = self.stage()
        self.assertEqual(result["exit_code"], 124)
        self.assertIsNone(result["process_exit_code"])

    def test_reaped_wrapper_still_has_its_group_cleaned(self):
        process = SimpleNamespace(pid=1234, wait=Mock(return_value=-signal.SIGTERM))
        with patch.object(runner.os, "killpg") as kill:
            runner.stop_process_group(process)
        self.assertEqual([call.args for call in kill.call_args_list],
                         [(1234, signal.SIGTERM), (1234, signal.SIGKILL)])
        process.wait.assert_called_once_with(timeout=5)

    def test_main_thread_is_required_before_launch_or_log_creation(self):
        results = []
        with patch.object(runner.subprocess, "Popen") as launch:
            worker = threading.Thread(target=lambda: results.append(self.stage()))
            worker.start()
            worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        launch.assert_not_called()
        self.assertEqual(results[0]["status"], "blocked")
        self.assertIsNone(results[0]["process_exit_code"])
        self.assertEqual(list(self.logs.iterdir()), [])

    def test_handlers_restored_after_success_and_launch_failure(self):
        original = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        process = SimpleNamespace(pid=1234, wait=lambda timeout: 0)
        for name, failure in (("success", False), ("unavailable", True)):
            with self.subTest(name=name), \
                 patch.object(runner.subprocess, "Popen", return_value=process,
                              side_effect=OSError if failure else None):
                result = runner.run_stage(self.root, self.logs, name, 10, ["fixture"])
            self.assertEqual(result["status"], "failed" if failure else "passed")
            for sig, handler in original.items():
                self.assertIs(signal.getsignal(sig), handler)

    def test_cancellation_during_log_capture_cannot_pass(self):
        process = SimpleNamespace(pid=1234, wait=lambda timeout: 0, poll=lambda: 0)
        capture = runner.stage_log_integrity

        def interrupted_capture(path):
            os.kill(os.getpid(), signal.SIGTERM)
            return capture(path)

        with patch.object(runner.subprocess, "Popen", return_value=process), \
             patch.object(runner, "stage_log_integrity", side_effect=interrupted_capture), \
             patch.object(runner, "stop_process_group") as stop:
            result = self.stage()
        stop.assert_called_once_with(process)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["interruption_signal"], signal.SIGTERM)
        self.assertEqual(result["process_exit_code"], 0)

    @staticmethod
    def is_running(pid):
        try:
            # A killed grandchild may briefly remain a zombie for the host reaper.
            return Path(f"/proc/{pid}/stat").read_text().split(")", 1)[1].split()[0] != "Z"
        except FileNotFoundError:
            return False

    def cancellation_fixture(self, repeated=False):
        if os.name != "posix" or not Path("/proc").is_dir() or not shutil.which("timeout"):
            self.skipTest("requires POSIX /proc and the existing timeout executable")
        child_code = "import os, signal, time; "
        if repeated:
            child_code += "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        child_code += "print(os.getpid(), os.getpgrp(), flush=True); time.sleep(20)"
        acknowledgement = self.root / "cleanup-started"
        driver = """
import importlib.util, json, pathlib, subprocess, sys
spec = importlib.util.spec_from_file_location('isolated_runner', sys.argv[1])
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
created = []
original_popen = subprocess.Popen
def start(*args, **kwargs):
    process = original_popen(*args, **kwargs)
    created.append(process)
    return process
runner.subprocess.Popen = start
original_stop = runner.stop_process_group
def stop(process):
    pathlib.Path(sys.argv[5]).write_text('cleanup started')
    original_stop(process)
runner.stop_process_group = stop
result = runner.run_stage(pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]),
                          'fixture', 10, [sys.executable, '-c', sys.argv[4]])
print(json.dumps({'record': result, 'actual': created[0].returncode}), flush=True)
"""
        controller = subprocess.Popen(
            [sys.executable, "-B", "-c", driver, str(RUNNER_PATH), str(self.root),
             str(self.logs), child_code, str(acknowledgement)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True)
        child_group = None
        try:
            deadline = time.monotonic() + 5
            child_pid = None
            while time.monotonic() < deadline:
                log = self.logs / "fixture.log"
                if log.exists():
                    fields = log.read_text().strip().split()
                    if len(fields) == 2:
                        child_pid, child_group = map(int, fields)
                        break
                if controller.poll() is not None:
                    self.fail("isolated controller exited before the child announced its group")
                time.sleep(0.02)
            self.assertIsNotNone(child_pid, "fixture child did not start")
            self.assertNotIn(child_group, (0, os.getpgrp(), controller.pid))
            # GNU timeout owns the group; the child PID is not the group ID.
            self.assertNotEqual(child_pid, child_group)
            started = time.monotonic()
            os.kill(controller.pid, signal.SIGTERM)
            if repeated:
                deadline = time.monotonic() + 3
                while not acknowledgement.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(acknowledgement.exists(), "cancellation was not acknowledged")
                os.kill(controller.pid, signal.SIGINT)
                os.kill(controller.pid, signal.SIGTERM)
            output, error = controller.communicate(timeout=12)
            self.assertEqual(controller.returncode, 0, error)
            captured = json.loads(output)
            result = captured["record"]
            self.assertEqual(result["status"], "blocked")
            self.assertTrue(result["interrupted"])
            self.assertEqual(result["interruption_signal"], signal.SIGTERM)
            self.assertEqual(result["exit_code"], 128 + signal.SIGTERM)
            self.assertIsInstance(result["process_exit_code"], int)
            self.assertNotEqual(result["process_exit_code"], 0)
            self.assertEqual(result["process_exit_code"], captured["actual"])
            self.assertIsNotNone(result["log_sha256"])
            self.assertFalse(self.is_running(child_pid), "fixture descendant survived cancellation")
            self.assertLess(time.monotonic() - started, 12)
        finally:
            # Cleanup only the fixture groups identified above, never the test runner's group.
            for group in (child_group, controller.pid):
                if group is not None and group > 0 and group != os.getpgrp():
                    try:
                        os.killpg(group, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            controller.communicate(timeout=3)

    def test_sigterm_stops_legacy_group_and_preserves_actual_exit(self):
        self.cancellation_fixture()

    def test_repeated_signals_do_not_abandon_legacy_cleanup(self):
        self.cancellation_fixture(repeated=True)


if __name__ == "__main__":
    unittest.main()
