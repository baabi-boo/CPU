"""Synthetic completion-protocol fixtures, never actual processor evidence."""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/nova/target_evidence.py"
SPEC = importlib.util.spec_from_file_location("nova_target_evidence", SCRIPT)
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)
PASS = b"*** PASSED *** Completed after          123 simulation cycles\n"
MARKER = "NOVA_BASELINE_V1 PASS hart=0 checks=12"


class TargetEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.stdout = self.root / "stdout.log"
        self.stderr = self.root / "stderr.log"
        self.stdout.write_bytes(MARKER.encode() + b"\n")
        self.stderr.write_bytes(PASS)

    def assess(self, **kwargs):
        return evidence.assess_simulation(self.stdout, self.stderr, 0, **kwargs)

    def assertFailed(self, result):
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["target_completion_verified"])
        self.assertFalse(result["completion_protocol_observed"])
        self.assertFalse(result["hardware_qualified"])
        self.assertFalse(result["g1_gate_passed"])
        self.assertTrue(result["reasons"])

    def test_exact_positive_protocol_does_not_qualify_hardware(self):
        result = self.assess(expected_marker=MARKER)
        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["target_completion_verified"])
        self.assertTrue(result["completion_protocol_observed"])
        self.assertFalse(result["hardware_qualified"])
        self.assertFalse(result["g1_gate_passed"])
        self.assertEqual(result["cycles"], 123)
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["stderr_sha256"], hashlib.sha256(PASS).hexdigest())
        self.assertEqual(result["stderr_bytes"], len(PASS))

    def test_empty_isa_stdout_is_accepted_without_target_record(self):
        self.stdout.write_bytes(b"")
        self.assertEqual(self.assess()["status"], "passed")

    def test_unrelated_complete_trace_lines_are_allowed(self):
        self.stderr.write_bytes(b"testing $random 12345678\nCore 0: 0x80000000\n" + PASS)
        self.stdout.write_bytes(b"other target output\n" + MARKER.encode() + b"\n")
        self.assertEqual(self.assess(expected_marker=MARKER)["status"], "passed")

    def test_nonzero_absent_boolean_or_coerced_exit_never_reads_logs(self):
        for status in (1, 7, 124, -9, None, False, True, "0", 0.0):
            with self.subTest(status=status), patch.object(evidence, "_read_log") as read:
                self.assertFailed(evidence.assess_simulation(self.stdout, self.stderr, status))
                read.assert_not_called()

    def test_invalid_bounds_never_read_logs(self):
        for bound in (0, -1, False, True, None, "123", 123.0, 1 << 64):
            with self.subTest(bound=bound), patch.object(evidence, "_read_log") as read:
                self.assertFailed(self.assess(max_cycles=bound))
                read.assert_not_called()

    def test_missing_and_duplicate_completion_are_rejected(self):
        for data in (b"", b"only tracing\n", PASS + PASS):
            with self.subTest(data=data):
                self.stderr.write_bytes(data)
                self.assertFailed(self.assess())

    def test_prefixed_suffixed_lowercase_and_malformed_records_are_rejected(self):
        for data in (
            b"echo " + PASS, b" " + PASS, PASS.rstrip(b"\n") + b" extra\n",
            PASS.lower(), PASS.replace(b"*** PASSED ***", b"** PASSED **"),
            PASS.replace(b"123", b"0"), PASS.replace(b"123", b"-1"),
            PASS.replace(b"123", b"1.5"), PASS.replace(b"123", b"1e3"),
            PASS.replace(b"123", b"9" * 200), PASS.replace(b"123", b"0123"),
            PASS.replace(b"\n", b"\r\n"),
        ):
            with self.subTest(data=data):
                self.stderr.write_bytes(data)
                self.assertFailed(self.assess())

    def test_valid_record_plus_malformed_record_is_not_accepted(self):
        self.stderr.write_bytes(PASS + b"echo " + PASS)
        self.assertFailed(self.assess())

    def test_completion_must_not_appear_in_stdout(self):
        for data in (PASS, b"echo " + PASS, PASS.lower()):
            with self.subTest(data=data):
                self.stdout.write_bytes(data)
                self.assertFailed(self.assess())

    def test_failure_signals_override_valid_completion_on_either_stream(self):
        for indicator in (b"*** FAIL ***", b"FAIL hart=0 check=7", b"fail: check 7",
                          b"*** FAILED ***", b"FATAL: assertion", b"(timeout)",
                          b"timed out", b"%Error: simulator assertion"):
            for stream in (self.stdout, self.stderr):
                with self.subTest(indicator=indicator, stream=stream.name):
                    self.stdout.write_bytes(MARKER.encode() + b"\n")
                    self.stderr.write_bytes(PASS)
                    with stream.open("ab") as target:
                        target.write(indicator + b"\n")
                    self.assertFailed(self.assess())

    def test_cycle_bound_is_inclusive_and_not_silently_relaxed(self):
        self.assertEqual(self.assess(max_cycles=123)["status"], "passed")
        self.assertFailed(self.assess(max_cycles=122))
        self.stderr.write_bytes(PASS.replace(b"123", str((1 << 64) - 1).encode()))
        self.assertEqual(self.assess(max_cycles=(1 << 64) - 1)["status"], "passed")
        self.stderr.write_bytes(PASS.replace(b"123", str(1 << 64).encode()))
        self.assertFailed(self.assess(max_cycles=(1 << 64) - 1))

    def test_exact_marker_rejects_missing_duplicate_prefixed_and_suffixed_output(self):
        marker = MARKER.encode() + b"\n"
        for data in (b"", marker + marker, b"echo " + marker,
                     marker.rstrip(b"\n") + b" extra\n"):
            with self.subTest(data=data):
                self.stdout.write_bytes(data)
                self.assertFailed(self.assess(expected_marker=MARKER))

    def test_invalid_expected_marker_never_reads_logs(self):
        for marker in ("", "one\ntwo", "text\r", "\x00", 123, b"bytes", "\ud800"):
            with self.subTest(marker=repr(marker)), patch.object(evidence, "_read_log") as read:
                self.assertFailed(self.assess(expected_marker=marker))
                read.assert_not_called()

    def test_incomplete_final_line_is_rejected_on_either_stream(self):
        for stream in (self.stdout, self.stderr):
            with self.subTest(stream=stream.name):
                self.stdout.write_bytes(MARKER.encode() + b"\n")
                self.stderr.write_bytes(PASS)
                stream.write_bytes(stream.read_bytes().rstrip(b"\n"))
                self.assertFailed(self.assess())

    def test_incomplete_trace_after_complete_pass_is_rejected(self):
        self.stderr.write_bytes(PASS + b"partial trailing output")
        self.assertFailed(self.assess())

    def test_binary_or_invalid_utf8_logs_are_rejected(self):
        for data in (b"\x00\n", b"\xff\n"):
            self.stderr.write_bytes(PASS + data)
            self.assertFailed(self.assess())

    def test_missing_log_is_rejected_without_creating_any_path(self):
        missing = self.root / "missing" / "stdout.log"
        before = sorted(str(p) for p in self.root.rglob("*"))
        result = evidence.assess_simulation(missing, self.stderr, 0)
        self.assertFailed(result)
        self.assertEqual(before, sorted(str(p) for p in self.root.rglob("*")))

    def test_directory_and_fifo_are_rejected_before_open(self):
        values = [self.root]
        if hasattr(os, "mkfifo"):
            fifo = self.root / "log.fifo"
            os.mkfifo(fifo)
            values.append(fifo)
        for value in values:
            with self.subTest(value=value.name), \
                 patch.object(evidence.os, "open", wraps=os.open) as opened:
                self.assertFailed(evidence.assess_simulation(value, self.stderr, 0))
                # stderr is still inspected; only the bad path must not open.
                self.assertNotIn(value, [call.args[0] for call in opened.call_args_list])

    def test_leaf_and_parent_symlinks_are_rejected(self):
        alias = self.root / "stdout-alias.log"
        alias.symlink_to(self.stdout)
        self.assertFailed(evidence.assess_simulation(alias, self.stderr, 0))
        parent = self.root / "alias-directory"
        parent.symlink_to(self.root, target_is_directory=True)
        self.assertFailed(evidence.assess_simulation(parent / "stdout.log", self.stderr, 0))

    def test_same_file_or_hardlink_cannot_supply_both_streams(self):
        self.assertFailed(evidence.assess_simulation(self.stderr, self.stderr, 0))
        link = self.root / "stderr-hardlink.log"
        os.link(self.stderr, link)
        self.assertFailed(evidence.assess_simulation(link, self.stderr, 0))

    def test_overlimit_logs_are_rejected_without_large_allocations(self):
        with patch.object(evidence, "MAX_LOG_BYTES", len(PASS) - 1):
            self.assertFailed(self.assess())
        with patch.object(evidence, "MAX_LOG_BYTES", len(PASS)):
            self.assertEqual(self.assess()["status"], "passed")

    def test_unreadable_logs_do_not_leak_operating_system_diagnostics(self):
        with patch.object(evidence.os, "open", side_effect=OSError("private fixture detail")):
            result = self.assess()
        self.assertFailed(result)
        self.assertNotIn("private fixture detail", json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_changed_file_metadata_is_rejected(self):
        real_identity = evidence._identity
        calls = 0

        def altered_identity(info):
            nonlocal calls
            calls += 1
            actual = real_identity(info)
            return actual if calls != 3 else (*actual[:-1], actual[-1] + 1)

        with patch.object(evidence, "_identity", side_effect=altered_identity):
            self.assertFailed(self.assess())

    def test_invalid_path_types_fail_cleanly(self):
        for value in (None, 12, b"path", "\x00"):
            with self.subTest(value=value):
                self.assertFailed(evidence.assess_simulation(value, self.stderr, 0))

    def test_cli_outputs_json_without_mutating_inputs(self):
        before = {path.name: path.read_bytes() for path in (self.stdout, self.stderr)}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = evidence.main(["--stdout", str(self.stdout), "--stderr", str(self.stderr),
                                  "--exit-code", "0", "--expected-marker", MARKER])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "passed")
        self.assertEqual(before, {path.name: path.read_bytes() for path in (self.stdout, self.stderr)})
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_cli_nonzero_exit_and_missing_arguments_fail(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(evidence.main(["--stdout", str(self.stdout), "--stderr", str(self.stderr),
                                            "--exit-code", "124"]), 1)
        self.assertFailed(json.loads(output.getvalue()))
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                evidence.main([])
        self.assertEqual(raised.exception.code, 2)

    def test_command_line_works_outside_repository(self):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--stdout", str(self.stdout),
             "--stderr", str(self.stderr), "--exit-code", "0"],
            cwd=self.root, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "passed")


if __name__ == "__main__":
    unittest.main()
