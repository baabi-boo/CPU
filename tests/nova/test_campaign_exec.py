"""Harmless local subprocess fixtures for the bounded campaign executor."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nova_campaign_exec_tests", ROOT / "scripts/nova/campaign_exec.py")
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)


@unittest.skipUnless(os.name == "posix", "POSIX execution contract")
class CampaignExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.output = self.root / "output"
        self.output.mkdir()
        disk = mock.patch.object(engine.shutil, "disk_usage", return_value=
                                 types.SimpleNamespace(free=20 * 1024 ** 3))
        disk.start()
        self.addCleanup(disk.stop)

    def run_python(self, code, **kwargs):
        args = dict(cwd=self.root, output_dir=self.output, name="fixture",
                    argv=[sys.executable, "-c", code], timeout_seconds=2,
                    min_free_gib=1)
        args.update(kwargs)
        return engine.run_command(**args)

    def assert_record(self, result):
        self.assertIn(result["status"], {"passed", "failed", "blocked"})
        self.assertFalse(result["hardware_qualified"])
        self.assertFalse(result["g1_gate_passed"])
        self.assertGreaterEqual(result["elapsed_seconds"], 0)
        self.assertTrue(result["started_utc"].endswith("+00:00"))
        self.assertTrue(result["finished_utc"].endswith("+00:00"))

    def test_zero_exit_separate_private_hashed_logs(self):
        result = self.run_python("import os; os.write(1,b'out'); os.write(2,b'err')")
        self.assert_record(result)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["exit_code"], 0)
        for channel, expected in (("stdout", b"out"), ("stderr", b"err")):
            path = self.output / result[channel]
            self.assertEqual(result[channel], f"fixture.{channel}.log")
            self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(result[f"{channel}_sha256"], hashlib.sha256(expected).hexdigest())
            self.assertEqual(result[f"{channel}_bytes"], len(expected))

    def test_empty_logs_have_real_hashes(self):
        result = self.run_python("pass")
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["stdout_sha256"], hashlib.sha256(b"").hexdigest())
        self.assertEqual(result["stderr_sha256"], hashlib.sha256(b"").hexdigest())

    def test_nonzero_exit_remains_failure(self):
        result = self.run_python("import sys; print('target failure'); sys.exit(7)")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 7)
        self.assertEqual(result["reason"], "command exited unsuccessfully")
        self.assertFalse(result["timed_out"])
        self.assertTrue(result["stdout_sha256"])

    def test_signal_exit_preserves_actual_negative_code(self):
        result = self.run_python("import os,signal; os.kill(os.getpid(),signal.SIGTERM)")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], -signal.SIGTERM)

    def test_timeout_is_bounded_and_does_not_invent_exit_124(self):
        result = self.run_python("import time; time.sleep(10)", timeout_seconds=0.08)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["timed_out"])
        self.assertIn(result["exit_code"], {-signal.SIGTERM, -signal.SIGKILL})
        self.assertLess(result["elapsed_seconds"], engine.CLEANUP_GRACE_SECONDS + 1)

    def test_ignoring_term_escalates_to_kill(self):
        result = self.run_python(
            "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
            "print('ready',flush=True); time.sleep(10)", timeout_seconds=0.4)
        self.assertEqual((self.output / result["stdout"]).read_text(), "ready\n")
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["exit_code"], -signal.SIGKILL)
        self.assertLess(result["elapsed_seconds"], engine.CLEANUP_GRACE_SECONDS + 1)

    def test_fast_exit_stdout_limit_is_checked_after_exit(self):
        with mock.patch.object(engine, "_log_issue", return_value=None):
            result = self.run_python("import os; os.write(1,b'x'*4096)", max_log_bytes=64)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["stdout_sha256"])
        self.assertIn("byte limit", result["reason"])

    def cancellation_fixture(self, repeated=False):
        """Signal only an isolated fixture runner and its identified child."""
        child_code = (
            "import os,signal,time; "
            + ("signal.signal(signal.SIGTERM,signal.SIG_IGN); " if repeated else "")
            + "print(os.getpid(),flush=True); time.sleep(20)"
        )
        driver = "\n".join((
            "import importlib.util,json,pathlib,sys,types",
            "spec=importlib.util.spec_from_file_location('fixture_engine',sys.argv[1])",
            "engine=importlib.util.module_from_spec(spec)",
            "spec.loader.exec_module(engine)",
            "engine.shutil.disk_usage=lambda _:types.SimpleNamespace(free=20*1024**3)",
            "original_stop=engine._stop_group",
            "def observed_stop(process):",
            "    pathlib.Path(sys.argv[5]).write_text('cancellation observed')",
            "    return original_stop(process)",
            "engine._stop_group=observed_stop",
            "record=engine.run_command(sys.argv[2],sys.argv[3],'cancel-fixture',",
            "    [sys.executable,'-c',sys.argv[4]],10,min_free_gib=1)",
            "print(json.dumps(record),flush=True)",
        ))
        runner = subprocess.Popen(
            [sys.executable, "-B", "-c", driver, str(ROOT / "scripts/nova/campaign_exec.py"),
             str(self.root), str(self.output), child_code,
             str(self.output / "cleanup-observed")],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        child_pid = None
        try:
            ready = self.output / "cancel-fixture.stdout.log"
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline and runner.poll() is None:
                if ready.exists():
                    line = ready.read_text().strip()
                    if line.isdigit():
                        child_pid = int(line)
                        break
                time.sleep(0.01)
            self.assertIsNotNone(child_pid, "fixture child did not become ready")
            cancelled_at = time.monotonic()
            runner.send_signal(signal.SIGTERM)
            if repeated:
                # Sender order alone does not establish Python handler order
                # when several signals are pending. Wait for actual cleanup
                # entry, rather than assuming a fixed sleep acknowledged TERM.
                acknowledged = self.output / "cleanup-observed"
                while (not acknowledged.exists() and runner.poll() is None
                       and time.monotonic() - cancelled_at < 2):
                    time.sleep(0.01)
                self.assertTrue(acknowledged.exists(), "first cancellation was not acknowledged")
                runner.send_signal(signal.SIGTERM)
                runner.send_signal(signal.SIGINT)
            stdout, stderr = runner.communicate(timeout=5)
            self.assertEqual(runner.returncode, 0, stderr)
            result = json.loads(stdout)
            self.assertEqual(result["status"], "blocked")
            self.assertTrue(result["interrupted"])
            self.assertEqual(result["interruption_signal"], signal.SIGTERM)
            self.assertEqual(result["reason"], "command execution interrupted")
            self.assertFalse(result["timed_out"])
            self.assertEqual(result["exit_code"],
                             -signal.SIGKILL if repeated else -signal.SIGTERM)
            self.assertTrue(result["stdout_sha256"])
            self.assertTrue(result["stderr_sha256"])
            self.assertLess(time.monotonic() - cancelled_at,
                            engine.CLEANUP_GRACE_SECONDS + 1)
            with self.assertRaises(ProcessLookupError):
                os.kill(child_pid, 0)
        finally:
            # Clean only the explicit fixture processes if a regression fails.
            for pid in (child_pid, runner.pid):
                if pid is not None:
                    try:
                        os.killpg(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            runner.communicate(timeout=3)

    def test_sigterm_cleans_child_and_retains_interrupted_record(self):
        self.cancellation_fixture()

    def test_repeated_termination_does_not_abandon_cleanup(self):
        self.cancellation_fixture(repeated=True)

    def test_signal_handlers_are_restored_after_success_and_launch_failure(self):
        original = {signum: signal.getsignal(signum)
                    for signum in (signal.SIGINT, signal.SIGTERM)}
        handler = lambda _signum, _frame: None
        try:
            for signum in original:
                signal.signal(signum, handler)
            for name, argv in (("success", [sys.executable, "-c", "pass"]),
                               ("missing", [str(self.root / "missing")])):
                self.run_python("pass", name=name, argv=argv)
                for signum in original:
                    self.assertIs(signal.getsignal(signum), handler)
        finally:
            for signum, previous in original.items():
                signal.signal(signum, previous)

    def test_non_main_thread_blocks_before_launch_or_log_creation(self):
        results = []
        with mock.patch.object(engine.subprocess, "Popen") as launch:
            worker = threading.Thread(target=lambda: results.append(self.run_python("pass")))
            worker.start()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
        launch.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "blocked")
        self.assertIn("main-thread", results[0]["reason"])
        self.assertEqual(list(self.output.iterdir()), [])

    def test_cancellation_before_launch_never_starts_command(self):
        original = {signum: signal.getsignal(signum)
                    for signum in (signal.SIGINT, signal.SIGTERM)}
        def cancel(*_args):
            os.kill(os.getpid(), signal.SIGTERM)
            return None
        with mock.patch.object(engine, "_disk_issue", side_effect=cancel), \
                mock.patch.object(engine.subprocess, "Popen") as launch:
            result = self.run_python("pass")
        launch.assert_not_called()
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["interrupted"])
        self.assertIsNone(result["exit_code"])
        self.assertEqual(list(self.output.iterdir()), [])
        for signum, previous in original.items():
            self.assertIs(signal.getsignal(signum), previous)

    def test_cancellation_during_post_exit_capture_never_becomes_success(self):
        capture = engine._capture_log
        def cancel_and_capture(*args):
            os.kill(os.getpid(), signal.SIGTERM)
            return capture(*args)
        with mock.patch.object(engine, "_capture_log", side_effect=cancel_and_capture):
            result = self.run_python("pass")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["interrupted"])
        self.assertTrue(result["stdout_sha256"])
        self.assertTrue(result["stderr_sha256"])

    def test_stderr_has_independent_limit(self):
        result = self.run_python("import os; os.write(2,b'x'*4096)", max_log_bytes=64)
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["stderr_sha256"])
        self.assertIn("byte limit", result["reason"])

    def test_fast_nonzero_cannot_hide_incomplete_log_evidence(self):
        with mock.patch.object(engine, "_log_issue", return_value=None):
            result = self.run_python(
                "import os,sys; os.write(1,b'x'*4096); sys.exit(7)", max_log_bytes=64)
        self.assertEqual(result["exit_code"], 7)
        self.assertEqual(result["status"], "failed")
        self.assertIn("byte limit", result["reason"])
        self.assertIsNone(result["stdout_sha256"])

    def test_exact_log_limit_is_accepted(self):
        result = self.run_python("import os; os.write(1,b'x'*64)", max_log_bytes=64)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["stdout_bytes"], 64)

    def test_prelaunch_disk_floor_prevents_log_creation(self):
        with mock.patch.object(engine.shutil, "disk_usage", return_value=
                               types.SimpleNamespace(free=0)), \
                mock.patch.object(engine.subprocess, "Popen") as launch:
            result = self.run_python("pass")
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["exit_code"])
        self.assertEqual(list(self.output.iterdir()), [])
        launch.assert_not_called()

    def test_disk_floor_is_checked_during_execution(self):
        with mock.patch.object(engine, "_disk_issue", side_effect=[
                None, "disk floor lost", "disk floor lost"]):
            result = self.run_python("import time; time.sleep(10)")
        self.assertEqual(result["status"], "blocked")
        self.assertIsNotNone(result["exit_code"])
        self.assertEqual(result["reason"], "disk floor lost")

    def test_disk_floor_is_checked_after_fast_zero_exit(self):
        child = mock.Mock(pid=123456789, returncode=0)
        child.poll.return_value = 0
        with mock.patch.object(engine.subprocess, "Popen", return_value=child), \
                mock.patch.object(engine, "_group_alive", return_value=False), \
                mock.patch.object(engine, "_disk_issue", side_effect=[None, "disk floor lost"]):
            result = self.run_python("pass")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "disk floor lost")

    def test_disk_inspection_failure_is_fail_closed_and_sanitized(self):
        with mock.patch.object(engine.shutil, "disk_usage", side_effect=OSError("private detail")):
            result = self.run_python("pass")
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("private detail", json.dumps(result))

    def test_existing_stdout_is_never_overwritten(self):
        sentinel = self.output / "fixture.stdout.log"
        sentinel.write_bytes(b"existing")
        result = self.run_python("print('new')")
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["exit_code"])
        self.assertEqual(sentinel.read_bytes(), b"existing")

    def test_existing_stderr_prevents_launch_and_preserves_file(self):
        sentinel = self.output / "fixture.stderr.log"
        sentinel.write_bytes(b"existing")
        with mock.patch.object(engine.subprocess, "Popen") as launch:
            result = self.run_python("pass")
        launch.assert_not_called()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(sentinel.read_bytes(), b"existing")
        self.assertEqual((self.output / "fixture.stdout.log").read_bytes(), b"")

    def test_existing_log_symlink_is_not_followed(self):
        sentinel = self.root / "sentinel"
        sentinel.write_bytes(b"existing")
        (self.output / "fixture.stdout.log").symlink_to(sentinel)
        result = self.run_python("pass")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(sentinel.read_bytes(), b"existing")

    def test_symlink_working_or_output_directory_is_rejected(self):
        link = self.root / "linked"
        link.symlink_to(self.output, target_is_directory=True)
        for key in ("cwd", "output_dir"):
            with self.subTest(key=key):
                result = self.run_python("pass", **{key: link})
                self.assertEqual(result["status"], "blocked")
                self.assertIsNone(result["exit_code"])
        self.assertEqual(list(self.output.iterdir()), [])

    def test_invalid_names_are_rejected_before_creation(self):
        for name in ("", ".", "..", "../name", "a/b", "-name", "a\n", "x" * 97, None):
            with self.subTest(name=name):
                self.assertEqual(self.run_python("pass", name=name)["status"], "blocked")
        self.assertEqual(list(self.output.iterdir()), [])

    def test_invalid_arguments_limits_and_environment_do_not_launch(self):
        invalid = [
            {"argv": "echo no"}, {"argv": []}, {"argv": ["", "arg"]},
            {"argv": ["-option"]}, {"argv": [1]}, {"argv": ["a\x00"]},
            {"argv": ["a\n"]}, {"argv": ["x" * 16385]}, {"argv": ["a"] * 257},
            {"argv": ["x" * 16000] * 5}, {"timeout_seconds": True},
            {"timeout_seconds": 0}, {"timeout_seconds": float("nan")},
            {"timeout_seconds": float("inf")}, {"timeout_seconds": 7201},
            {"timeout_seconds": 10 ** 1000}, {"min_free_gib": 10 ** 1000},
            {"min_free_gib": True}, {"min_free_gib": 0}, {"min_free_gib": 51},
            {"max_log_bytes": True}, {"max_log_bytes": 0},
            {"max_log_bytes": engine.MAX_LOG_BYTES + 1},
            {"env": []}, {"env": {"A=B": "x"}}, {"env": {"A": 1}},
            {"env": {"": "x"}}, {"env": {"A": "\x00"}},
        ]
        with mock.patch.object(engine.subprocess, "Popen") as launch:
            for kwargs in invalid:
                with self.subTest(kwargs=kwargs):
                    result = self.run_python("pass", **kwargs)
                    self.assertEqual(result["status"], "blocked")
                    self.assertIsNone(result["exit_code"])
        launch.assert_not_called()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_relative_missing_or_traversal_directories_are_rejected(self):
        for path in (Path("relative"), self.root / "missing", self.output / ".."):
            with self.subTest(path=path):
                self.assertEqual(self.run_python("pass", cwd=path)["status"], "blocked")
        self.assertEqual(list(self.output.iterdir()), [])

    def test_missing_executable_preserves_null_actual_exit(self):
        result = self.run_python("pass", argv=[str(self.root / "missing-program")])
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["exit_code"])
        self.assertEqual(result["stdout_sha256"], hashlib.sha256(b"").hexdigest())

    def test_environment_is_forwarded_but_never_added_to_record(self):
        result = self.run_python(
            "import os,sys; sys.exit(0 if os.getenv('NOVA_FIXTURE') else 1)",
            env={"NOVA_FIXTURE": "synthetic-secret-for-test"})
        self.assertEqual(result["status"], "passed")
        self.assertNotIn("synthetic-secret-for-test", json.dumps(result))
        self.assertNotIn("env", result)

    def test_launch_is_direct_with_no_stdin_and_new_session(self):
        real_popen = subprocess.Popen
        with mock.patch.object(engine.subprocess, "Popen", wraps=real_popen) as launch:
            result = self.run_python("pass")
        self.assertEqual(result["status"], "passed")
        kwargs = launch.call_args.kwargs
        self.assertIs(kwargs["shell"], False)
        self.assertIs(kwargs["start_new_session"], True)
        self.assertIs(kwargs["close_fds"], True)
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertIsNot(kwargs["stdout"], kwargs["stderr"])

    def test_child_receives_eof_on_stdin(self):
        result = self.run_python("import sys; print(repr(sys.stdin.read()))")
        self.assertEqual(result["status"], "passed")
        self.assertEqual((self.output / result["stdout"]).read_text(), "''\n")

    def test_surviving_group_descendant_cannot_create_a_pass(self):
        result = self.run_python(
            "import subprocess,sys; subprocess.Popen([sys.executable,'-c',"
            "'import time; time.sleep(10); print(\"late\")']); print('parent')")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("surviving group descendants", result["reason"])
        self.assertLess(result["elapsed_seconds"], engine.CLEANUP_GRACE_SECONDS + 1)
        original = (self.output / result["stdout"]).read_bytes()
        time.sleep(0.1)
        self.assertEqual((self.output / result["stdout"]).read_bytes(), original)
        self.assertNotIn(b"late", original)

    def test_capture_failure_invalidates_zero_exit(self):
        with mock.patch.object(engine, "_capture_log", return_value=(None, None, "missing log")):
            result = self.run_python("pass")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["stdout_sha256"])

    def test_capture_rejects_wrong_inode(self):
        path = self.output / "log"
        path.write_bytes(b"original")
        descriptor = os.open(self.output, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, descriptor)
        digest, _, reason = engine._capture_log(descriptor, "log", (-1, -1), 64)
        self.assertIsNone(digest)
        self.assertIn("replaced", reason)


if __name__ == "__main__":
    unittest.main()
