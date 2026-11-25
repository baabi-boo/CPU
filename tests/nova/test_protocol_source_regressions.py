"""Source-shaped synthetic logs; no simulator or target execution evidence.

The direct-exit diagnostic comes from pinned Spike fesvr/syscall.cc at
9c190a07c6838f6392bafa4ad83acea462c7f759. That revision's fesvr/htif.cc
handles SIGABRT with exit(-1), which can produce host status 255.
"""

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/nova/workload_assessment.py"
SPEC = importlib.util.spec_from_file_location("nova_protocol_source_regressions", SCRIPT)
assessment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assessment)

PASS = b"*** PASSED *** Completed after          123 simulation cycles\n"
POSITIVE_TARGET = b"NOVA_BASELINE_V1 PASS hart=0 checks=8\n"
NEGATIVE_TARGET = b"NOVA_BASELINE_V1 EXPECTED_FAIL hart=0 code=7\n"
TOHOST = b"*** FAILED *** (tohost = 7)\n"
ASSERTION = b"Assertion failed: *** FAILED *** (exit code =          7)\n"
TRAILER = b"[123] %Error: TestHarness.sv:456: Verilog $stop\nAborting...\n"


class ProtocolSourceRegressionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.stdout = self.root / "stdout.log"
        self.stderr = self.root / "stderr.log"

    def write_logs(self, stdout=NEGATIVE_TARGET, stderr=TOHOST + ASSERTION):
        self.stdout.write_bytes(stdout)
        self.stderr.write_bytes(stderr)

    def assess_negative(self, exit_code=255):
        return assessment.assess_workload(
            self.stdout, self.stderr, exit_code,
            assessment.workload_contract("nova-baseline-fail"))

    def assert_unqualified(self, result):
        for flag in ("target_completion_verified", "hardware_qualified", "g1_gate_passed"):
            self.assertIs(result[flag], False)

    def assert_negative_failed(self, result):
        self.assertEqual(result["status"], "failed")
        self.assertIs(result["expectation_met"], False)
        self.assertIs(result["expected_target_failure_verified"], False)
        self.assertIs(result["completion_protocol_observed"], False)
        self.assertTrue(result["reasons"])
        self.assert_unqualified(result)

    def test_source_correct_direct_exit_with_supported_host_terminations(self):
        for host_exit in (255, -6, 134):
            for assertion in (ASSERTION, b"*** FAILED *** (exit code = 7)\n"):
                for trailer in (b"", TRAILER):
                    with self.subTest(host_exit=host_exit, assertion=assertion, trailer=trailer):
                        stderr = TOHOST + assertion + trailer
                        self.write_logs(stderr=stderr)
                        result = self.assess_negative(host_exit)
                        self.assertEqual(result["status"], "passed", result["reasons"])
                        self.assertIs(result["expectation_met"], True)
                        self.assertIs(result["expected_target_failure_verified"], True)
                        self.assertIs(result["completion_protocol_observed"], False)
                        self.assertIsNone(result["cycles"])
                        self.assertEqual(result["stderr_bytes"], len(stderr))
                        self.assertEqual(result["stderr_sha256"], hashlib.sha256(stderr).hexdigest())
                        self.assert_unqualified(result)

    def test_assertion_only_legacy_logs_remain_supported(self):
        self.write_logs(stderr=ASSERTION)
        for host_exit in (255, -6, 134, 1):
            with self.subTest(host_exit=host_exit):
                result = self.assess_negative(host_exit)
                self.assertEqual(result["status"], "passed", result["reasons"])
                self.assert_unqualified(result)

    def test_tohost_diagnostic_cannot_replace_assertion_or_target_record(self):
        for stdout, stderr in ((NEGATIVE_TARGET, TOHOST), (b"", TOHOST + ASSERTION)):
            with self.subTest(stdout=stdout, stderr=stderr):
                self.write_logs(stdout, stderr)
                self.assert_negative_failed(self.assess_negative())

    def test_wrong_or_malformed_tohost_failure_remains_rejected(self):
        diagnostics = (
            TOHOST.replace(b"7)", b"0)"),
            TOHOST.replace(b"7)", b"8)"),
            TOHOST.replace(b"7)", b"07)"),
            TOHOST.replace(b"7)", b"+7)"),
            TOHOST.replace(b" = ", b" =  "),
            TOHOST.replace(b" = ", b"= "),
            TOHOST.replace(b" = ", b" =\t"),
            TOHOST.replace(b"*** FAILED ***", b"** FAILED **"),
            TOHOST.lower(),
            b"echo " + TOHOST,
            b" " + TOHOST,
            TOHOST.rstrip(b"\n") + b" extra\n",
            TOHOST.replace(b"\n", b"\r\n"),
        )
        for diagnostic in diagnostics:
            for prefix in (b"", TOHOST):
                with self.subTest(diagnostic=diagnostic, prefix=prefix):
                    self.write_logs(stderr=prefix + diagnostic + ASSERTION)
                    self.assert_negative_failed(self.assess_negative())

    def test_duplicate_or_late_tohost_failure_remains_rejected(self):
        for stderr in (TOHOST * 2 + ASSERTION,
                       ASSERTION + TOHOST,
                       TOHOST + ASSERTION + TOHOST,
                       ASSERTION + TRAILER + TOHOST):
            with self.subTest(stderr=stderr):
                self.write_logs(stderr=stderr)
                self.assert_negative_failed(self.assess_negative())

    def test_tohost_failure_on_stdout_remains_rejected(self):
        for stderr in (ASSERTION, TOHOST + ASSERTION):
            with self.subTest(stderr=stderr):
                self.write_logs(NEGATIVE_TARGET + TOHOST, stderr)
                self.assert_negative_failed(self.assess_negative())

    def test_exact_tohost_cannot_mask_other_failure_or_success_diagnostics(self):
        for diagnostic in (b"Segmentation fault\n", b"fatal: helper\n", b"timed out\n", PASS):
            for label in ("stdout", "stderr"):
                with self.subTest(diagnostic=diagnostic, stream=label):
                    self.write_logs()
                    with getattr(self, label).open("ab") as stream:
                        stream.write(diagnostic)
                    self.assert_negative_failed(self.assess_negative())

    def test_positive_segfault_diagnostic_overrides_completion_on_either_stream(self):
        for diagnostic in (b"Segmentation fault\n", b"segmentation\tfault (core dumped)\n",
                           b"helper: Segmentation fault\n"):
            for label in ("stdout", "stderr"):
                with self.subTest(diagnostic=diagnostic, stream=label):
                    self.write_logs(POSITIVE_TARGET, PASS)
                    with getattr(self, label).open("ab") as stream:
                        stream.write(diagnostic)
                    generic = assessment.evidence.assess_simulation(self.stdout, self.stderr, 0)
                    workload = assessment.assess_workload(
                        self.stdout, self.stderr, 0, assessment.workload_contract("nova-baseline"))
                    for result in (generic, workload):
                        self.assertEqual(result["status"], "failed")
                        self.assertIs(result["completion_protocol_observed"], False)
                        self.assertTrue(result["reasons"])
                        self.assert_unqualified(result)
                    self.assertIs(workload["expectation_met"], False)

    def test_related_benign_words_do_not_become_a_crash_blacklist(self):
        trace = b"segmentation units: 2\npage fault handled\ndefault trap handler\n"
        self.write_logs(trace + POSITIVE_TARGET, trace + PASS)
        result = assessment.assess_workload(
            self.stdout, self.stderr, 0, assessment.workload_contract("nova-baseline"))
        self.assertEqual(result["status"], "passed", result["reasons"])
        self.assertIs(result["completion_protocol_observed"], True)
        self.assert_unqualified(result)


if __name__ == "__main__":
    unittest.main()
