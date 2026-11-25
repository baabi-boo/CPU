"""Native finish-time cancellation fixtures, confined to separate processes."""

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
DRIVER = r"""
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import types

spec = importlib.util.spec_from_file_location("fixture_engine", sys.argv[1])
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
engine.shutil.disk_usage = lambda _: types.SimpleNamespace(free=20 * 1024 ** 3)
boundary = sys.argv[4]
exit_code = int(sys.argv[5])
real_now = engine._now
real_signal = signal.signal
now_calls = 0
signals_sent = []
outer_signals = []

def outer_handler(signum, _frame):
    outer_signals.append(signum)

for signum in (signal.SIGINT, signal.SIGTERM):
    real_signal(signum, outer_handler)
previous = {signum: signal.getsignal(signum)
            for signum in (signal.SIGINT, signal.SIGTERM)}

def send_term():
    signals_sent.append(int(signal.SIGTERM))
    os.kill(os.getpid(), signal.SIGTERM)

def finish_timestamp():
    global now_calls
    now_calls += 1
    if boundary == "timestamp" and now_calls == 2:
        send_term()
    return real_now()

def restore_handler(signum, handler):
    restoring = handler is previous.get(signum)
    if restoring and boundary == "restore-term" and signum == signal.SIGTERM:
        # The last scoped handler can still receive a signal on restoration entry.
        send_term()
    old = real_signal(signum, handler)
    if restoring and boundary == "restore-int" and signum == signal.SIGINT:
        # INT is restored, but TERM still belongs to the inner execution scope.
        send_term()
    return old

engine._now = finish_timestamp
engine.signal.signal = restore_handler
child = "import os, signal, sys; os.write(1, b'out'); os.write(2, b'err'); "
if exit_code < 0:
    child += "os.kill(os.getpid(), " + str(-exit_code) + ")"
else:
    child += "sys.exit(" + str(exit_code) + ")"
record = engine.run_command(
    Path(sys.argv[2]), Path(sys.argv[3]), "late-signal",
    [sys.executable, "-B", "-c", child], 2, min_free_gib=1)
restored = all(signal.getsignal(signum) is handler
               for signum, handler in previous.items())
print(json.dumps({"record": record, "signals_sent": signals_sent,
                  "outer_signals": outer_signals, "handlers_restored": restored}))
"""


@unittest.skipUnless(os.name == "posix", "POSIX execution contract")
class CampaignExitCancellationTests(unittest.TestCase):
    def run_fixture(self, boundary, exit_code):
        # Native signals are sent only by this isolated driver's own process.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            output = root / "output"
            output.mkdir()
            completed = subprocess.run(
                [sys.executable, "-B", "-c", DRIVER,
                 str(ROOT / "scripts/nova/campaign_exec.py"), str(root),
                 str(output), boundary, str(exit_code)],
                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                start_new_session=True, timeout=8, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            observed = json.loads(completed.stdout)
            result = observed["record"]
            self.assertTrue(observed["handlers_restored"])
            self.assertEqual(observed["outer_signals"], [])
            self.assertEqual(result["exit_code"], exit_code)
            self.assertFalse(result["timed_out"])
            self.assertFalse(result["hardware_qualified"])
            self.assertFalse(result["g1_gate_passed"])
            self.assertGreaterEqual(result["elapsed_seconds"], 0)
            self.assertTrue(result["finished_utc"].endswith("+00:00"))
            for channel, expected in (("stdout", b"out"), ("stderr", b"err")):
                self.assertEqual((output / result[channel]).read_bytes(), expected)
                self.assertEqual(result[f"{channel}_bytes"], len(expected))
                self.assertEqual(result[f"{channel}_sha256"],
                                 hashlib.sha256(expected).hexdigest())
            return observed

    def assert_cancelled_boundary(self, boundary):
        for exit_code in (0, 7, -signal.SIGTERM):
            with self.subTest(boundary=boundary, exit_code=exit_code):
                observed = self.run_fixture(boundary, exit_code)
                self.assertEqual(observed["signals_sent"], [signal.SIGTERM])
                result = observed["record"]
                self.assertEqual(result["status"], "blocked")
                self.assertIs(result["interrupted"], True)
                self.assertEqual(result["interruption_signal"], signal.SIGTERM)
                self.assertEqual(result["reason"], "command execution interrupted")

    def test_sigterm_during_final_timestamp_is_retained(self):
        self.assert_cancelled_boundary("timestamp")

    def test_sigterm_after_first_handler_restoration_is_retained(self):
        self.assert_cancelled_boundary("restore-int")

    def test_sigterm_during_last_handler_restoration_is_retained(self):
        self.assert_cancelled_boundary("restore-term")

    def test_normal_returns_preserve_status_exit_hashes_and_handlers(self):
        for exit_code in (0, 7, -signal.SIGTERM):
            with self.subTest(exit_code=exit_code):
                observed = self.run_fixture("none", exit_code)
                self.assertEqual(observed["signals_sent"], [])
                result = observed["record"]
                self.assertEqual(result["status"], "passed" if exit_code == 0 else "failed")
                self.assertNotIn("interrupted", result)
                self.assertNotIn("interruption_signal", result)


if __name__ == "__main__":
    unittest.main()
