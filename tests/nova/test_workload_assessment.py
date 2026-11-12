"""Synthetic workload-result fixtures; none is processor execution evidence."""

import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/nova/workload_assessment.py"
SPEC = importlib.util.spec_from_file_location("nova_workload_assessment", SCRIPT)
assessment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assessment)
PASS = b"*** PASSED *** Completed after          123 simulation cycles\n"
NEGATIVE = b"Assertion failed: *** FAILED *** (exit code =          7)\n"
TARGET = b"NOVA_BASELINE_V1 EXPECTED_FAIL hart=0 code=7\n"


class WorkloadAssessmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.stdout = self.root / "stdout.log"
        self.stderr = self.root / "stderr.log"
        self.stdout.write_bytes(b"NOVA_BASELINE_V1 PASS hart=0 checks=8\n")
        self.stderr.write_bytes(PASS)

    def assess(self, identifier="nova-baseline", exit_code=0, **kwargs):
        return assessment.assess_workload(
            self.stdout, self.stderr, exit_code,
            assessment.workload_contract(identifier), **kwargs)

    def negative_logs(self, diagnostic=NEGATIVE):
        self.stdout.write_bytes(TARGET)
        self.stderr.write_bytes(diagnostic)

    def assertFailed(self, result):
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["expectation_met"])
        self.assertFalse(result["target_completion_verified"])
        self.assertFalse(result["completion_protocol_observed"])
        self.assertFalse(result["expected_target_failure_verified"])
        self.assertFalse(result["hardware_qualified"])
        self.assertFalse(result["g1_gate_passed"])
        self.assertTrue(result["reasons"])

    def test_positive_target_requires_completion_and_has_no_gate_claim(self):
        result = self.assess()
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["expectation_met"])
        self.assertFalse(result["target_completion_verified"])
        self.assertTrue(result["completion_protocol_observed"])
        self.assertFalse(result["expected_target_failure_verified"])
        self.assertFalse(result["hardware_qualified"])
        self.assertFalse(result["g1_gate_passed"])
        self.assertEqual(result["cycles"], 123)

    def test_positive_delegates_exact_marker_to_completion_parser(self):
        with patch.object(assessment.evidence, "assess_simulation", wraps=
                          assessment.evidence.assess_simulation) as delegated:
            self.assess()
        self.assertEqual(delegated.call_args.kwargs["expected_marker"],
                         "NOVA_BASELINE_V1 PASS hart=0 checks=8")

    def test_positive_printed_record_without_completion_fails(self):
        self.stderr.write_bytes(b"")
        self.assertFailed(self.assess())

    def test_positive_rejects_conflicting_nova_records_on_both_streams(self):
        marker = b"NOVA_BASELINE_V1 PASS hart=0 checks=8\n"
        for extra in (
            b"NOVA_BASELINE_V1 FAIL hart=0 check=7 observed=1 expected=2\n",
            TARGET,
            b"NOVA_BASELINE_V1 PASS hart=1 checks=8\n",
            b"NOVA_BASELINE_V1 PASS hart=0 checks=7\n",
            b"echo " + marker,
            marker.lower(),
            b"NOVA_BASELINE_V2 PASS hart=0 checks=8\n",
        ):
            for stream in (self.stdout, self.stderr):
                with self.subTest(extra=extra, stream=stream.name):
                    self.stdout.write_bytes(marker)
                    self.stderr.write_bytes(PASS)
                    with stream.open("ab") as output:
                        output.write(extra)
                    self.assertFailed(self.assess())

    def test_positive_rejects_target_record_on_diagnostic_stream(self):
        self.stderr.write_bytes(PASS + b"NOVA_BASELINE_V1 PASS hart=0 checks=8\n")
        self.assertFailed(self.assess())

    def test_hello_rejects_extra_or_malformed_hello_on_both_streams(self):
        marker = b"Hello world from core 0, a rocket\n"
        for extra in (b"Hello world from core 0, a sonicboom\n",
                      b"Hello world from core 1, a rocket\n",
                      b"Hello world from core 0\n", b"echo " + marker,
                      marker.lower(), marker.rstrip(b"\n") + b" extra\n"):
            for stream in (self.stdout, self.stderr):
                with self.subTest(extra=extra, stream=stream.name):
                    self.stdout.write_bytes(marker)
                    self.stderr.write_bytes(PASS)
                    with stream.open("ab") as output:
                        output.write(extra)
                    self.assertFailed(self.assess("hello"))

    def test_hello_rejects_exact_record_on_diagnostic_stream(self):
        marker = b"Hello world from core 0, a rocket\n"
        self.stdout.write_bytes(marker)
        self.stderr.write_bytes(PASS + marker)
        self.assertFailed(self.assess("hello"))

    def test_positive_workloads_do_not_borrow_another_terminal_namespace(self):
        cases = (
            ("nova-baseline", b"NOVA_BASELINE_V1 PASS hart=0 checks=8\n",
             b"Hello world from core 0, a rocket\n"),
            ("hello", b"Hello world from core 0, a rocket\n",
             b"NOVA_BASELINE_V1 PASS hart=0 checks=8\n"),
            (assessment.plan.ISA_TESTS[0], b"", b"NOVA_BASELINE_V1 PASS hart=0 checks=8\n"),
            (assessment.plan.ISA_TESTS[0], b"", b"Hello world from core 0, a rocket\n"),
        )
        for identifier, marker, extra in cases:
            for stream in (self.stdout, self.stderr):
                with self.subTest(identifier=identifier, stream=stream.name):
                    self.stdout.write_bytes(marker)
                    self.stderr.write_bytes(PASS)
                    with stream.open("ab") as output:
                        output.write(extra)
                    self.assertFailed(self.assess(identifier))

    def test_positive_namespace_check_preserves_unrelated_tracing(self):
        for identifier, marker in (
            ("nova-baseline", b"NOVA_BASELINE_V1 PASS hart=0 checks=8\n"),
            ("hello", b"Hello world from core 0, a rocket\n"),
            (assessment.plan.ISA_TESTS[0], b""),
        ):
            with self.subTest(identifier=identifier):
                self.stdout.write_bytes(b"target startup\n" + marker + b"target shutdown\n")
                self.stderr.write_bytes(b"Core 0: 0x80000000\n" + PASS + b"statistics: 3\n")
                result = self.assess(identifier)
                self.assertEqual(result["status"], "passed", result["reasons"])
                self.assertTrue(result["completion_protocol_observed"])
                self.assertFalse(result["target_completion_verified"])

    def test_positive_namespace_recheck_rejects_changed_log_snapshot(self):
        original = assessment.evidence._read_log
        for changed in (self.stdout, self.stderr):
            calls = 0

            def mutate_after_protocol(path):
                nonlocal calls
                calls += 1
                if calls == 3:
                    with changed.open("ab") as output:
                        output.write(b"additional informational output\n")
                return original(path)

            with self.subTest(stream=changed.name):
                self.stdout.write_bytes(b"NOVA_BASELINE_V1 PASS hart=0 checks=8\n")
                self.stderr.write_bytes(PASS)
                with patch.object(assessment.evidence, "_read_log", side_effect=mutate_after_protocol):
                    result = self.assess()
                self.assertFailed(result)
                self.assertIn("changed between protocol and workload checks", " ".join(result["reasons"]))

    def test_positive_namespace_recheck_rejects_lost_log(self):
        original = assessment.evidence._read_log
        calls = 0

        def unavailable_after_protocol(path):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise assessment.evidence._LogFailure("is missing, unreadable, or invalid")
            return original(path)

        with patch.object(assessment.evidence, "_read_log", side_effect=unavailable_after_protocol):
            self.assertFailed(self.assess())

    def test_hello_requires_one_exact_rocket_line(self):
        self.stdout.write_bytes(b"Hello world from core 0, a rocket\n")
        self.assertEqual(self.assess("hello")["status"], "passed")
        for text in (b"", b"Hello world from core 0\n",
                     b"Hello world from core 0, a sonicboom\n",
                     b"Hello world from core 0, a unknown\n",
                     b"echo Hello world from core 0, a rocket\n",
                     b"Hello world from core 0, a rocket\n" * 2):
            with self.subTest(text=text):
                self.stdout.write_bytes(text)
                self.assertFailed(self.assess("hello"))

    def test_all_declared_isa_tests_accept_empty_stdout_with_completion(self):
        self.stdout.write_bytes(b"")
        for identifier in assessment.plan.ISA_TESTS:
            with self.subTest(identifier=identifier):
                self.assertEqual(self.assess(identifier)["status"], "passed")
        self.stderr.write_bytes(b"")
        self.assertFailed(self.assess(assessment.plan.ISA_TESTS[0]))

    def test_unknown_or_malformed_workloads_never_read_logs(self):
        valid = assessment.workload_contract("nova-baseline")
        variants = [None, [], {}, {"id": "unknown"}]
        for key, value in (("id", "hello"), ("kind", "isa"),
                           ("expected_target_exit", False),
                           ("expected_marker", None),
                           ("output_contract", "anything"),
                           ("binary", "other.riscv"),
                           ("binary_origin", "riscv_prefix")):
            row = copy.deepcopy(valid)
            row[key] = value
            variants.append(row)
        for value in variants:
            with self.subTest(value=value), patch.object(assessment.evidence, "_read_log") as read:
                result = assessment.assess_workload(self.stdout, self.stderr, 0, value)
                self.assertFailed(result)
                read.assert_not_called()

    def test_negative_control_requires_target_and_hardware_error(self):
        self.negative_logs()
        for exit_code in (-6, 134, 1):
            with self.subTest(exit_code=exit_code):
                result = self.assess("nova-baseline-fail", exit_code)
                self.assertEqual(result["status"], "passed")
                self.assertTrue(result["expectation_met"])
                self.assertTrue(result["expected_target_failure_verified"])
                self.assertFalse(result["target_completion_verified"])
                self.assertFalse(result["completion_protocol_observed"])
                self.assertFalse(result["hardware_qualified"])
                self.assertFalse(result["g1_gate_passed"])
                self.assertIsNone(result["cycles"])
                self.assertIsNotNone(result["stderr_sha256"])

    def test_negative_plain_simtsi_assertion_is_supported(self):
        self.negative_logs(b"*** FAILED *** (exit code = 7)\n")
        self.assertEqual(self.assess("nova-baseline-fail", -6)["status"], "passed")

    def test_negative_rejects_conflicting_terminal_namespaces_on_either_stream(self):
        extras = (
            b"Hello world from core 0, a rocket\n",
            TARGET.lower(),
            b"NOVA_BASELINE_V2 EXPECTED_FAIL hart=1 code=7\n",
        )
        for extra in extras:
            for stream in (self.stdout, self.stderr):
                with self.subTest(extra=extra, stream=stream.name):
                    self.negative_logs()
                    with stream.open("ab") as output:
                        output.write(extra)
                    self.assertFailed(self.assess("nova-baseline-fail", -6))

    def test_known_verilator_stop_trailer_after_assertion_is_allowed(self):
        for prefix in (b"", b"[123] "):
            self.negative_logs(NEGATIVE + prefix + b"%Error: TestHarness.sv:456: Verilog $stop\n"
                               + b"Aborting...\n")
            self.assertEqual(self.assess("nova-baseline-fail", -6)["status"], "passed")

    def test_negative_exit_zero_timeout_launcher_and_kill_codes_reject_without_reads(self):
        for code in (0, 124, 125, 126, 127, 130, 137, 139, 143, -9, -15, -11,
                     None, True, False, "134", 134.0, 256):
            with self.subTest(code=code), patch.object(assessment.evidence, "_read_log") as read:
                self.assertFailed(self.assess("nova-baseline-fail", code))
                read.assert_not_called()

    def test_negative_invalid_cycle_bound_rejects_without_reads(self):
        for bound in (0, -1, True, None, "10", 1 << 64):
            with self.subTest(bound=bound), patch.object(assessment.evidence, "_read_log") as read:
                self.assertFailed(self.assess("nova-baseline-fail", -6, max_cycles=bound))
                read.assert_not_called()

    def test_nonzero_generic_crash_without_exact_error_is_not_expected_failure(self):
        for diagnostic in (b"", b"Segmentation fault\n", b"Aborting...\n",
                           b"%Error: generic failure\n", b"*** FAILED *** (timeout)\n"):
            with self.subTest(diagnostic=diagnostic):
                self.negative_logs(diagnostic)
                self.assertFailed(self.assess("nova-baseline-fail", -6))

    def test_wrong_missing_duplicate_and_prefixed_target_records_fail(self):
        for target in (b"", TARGET * 2, b"echo " + TARGET,
                       TARGET + b"echo " + TARGET,
                       TARGET.replace(b"code=7", b"code=8"),
                       b"NOVA_BASELINE_V1 FAIL hart=0 check=7\n"):
            with self.subTest(target=target):
                self.negative_logs()
                self.stdout.write_bytes(target)
                self.assertFailed(self.assess("nova-baseline-fail", -6))

    def test_wrong_duplicate_prefixed_or_malformed_simtsi_assertions_fail(self):
        for diagnostic in (NEGATIVE * 2, b"echo " + NEGATIVE,
                           NEGATIVE.replace(b"7)", b"8)"),
                           NEGATIVE.replace(b"7)", b"07)"),
                           NEGATIVE + b"*** FAILED *** (exit code = 8)\n",
                           NEGATIVE.rstrip(b"\n") + b" extra\n"):
            with self.subTest(diagnostic=diagnostic):
                self.negative_logs(diagnostic)
                self.assertFailed(self.assess("nova-baseline-fail", -6))

    def test_success_or_timeout_in_either_negative_stream_is_rejected(self):
        for diagnostic in (PASS, b"(timeout)\n", b"timed out\n",
                           b"*** SUCCESS ***\n", b"simulation succeeded\n",
                           b"NOVA_BASELINE_V1 PASS hart=0 checks=8\n"):
            for stream in (self.stdout, self.stderr):
                with self.subTest(diagnostic=diagnostic, stream=stream.name):
                    self.negative_logs()
                    with stream.open("ab") as output:
                        output.write(diagnostic)
                    self.assertFailed(self.assess("nova-baseline-fail", -6))

    def test_unrelated_fatal_diagnostic_is_not_masked_by_expected_assertion(self):
        for diagnostic in (b"fatal: unrelated assertion\n", b"%Error: other problem\n",
                           b"Segmentation fault\n"):
            self.negative_logs(NEGATIVE + diagnostic)
            self.assertFailed(self.assess("nova-baseline-fail", -6))

    def test_stop_trailer_before_assertion_or_repeated_is_rejected(self):
        trailer = b"%Error: TestHarness.sv:456: Verilog $stop\n"
        for diagnostic in (trailer + NEGATIVE, NEGATIVE + trailer * 2):
            self.negative_logs(diagnostic)
            self.assertFailed(self.assess("nova-baseline-fail", -6))

    def test_negative_logs_must_be_separate_complete_regular_text(self):
        self.negative_logs()
        result = assessment.assess_workload(self.stdout, self.stdout, -6,
                                            assessment.workload_contract("nova-baseline-fail"))
        self.assertFailed(result)
        for diagnostic in (NEGATIVE.rstrip(b"\n"), NEGATIVE + b"\x00\n",
                           NEGATIVE + b"\xff\n"):
            self.negative_logs(diagnostic)
            self.assertFailed(self.assess("nova-baseline-fail", -6))

    def test_negative_missing_and_symlink_logs_fail_without_writes(self):
        self.negative_logs()
        missing = self.root / "missing"
        result = assessment.assess_workload(missing, self.stderr, -6,
                                            assessment.workload_contract("nova-baseline-fail"))
        self.assertFailed(result)
        self.assertFalse(missing.exists())
        link = self.root / "linked.log"
        link.symlink_to(self.stdout)
        result = assessment.assess_workload(link, self.stderr, -6,
                                            assessment.workload_contract("nova-baseline-fail"))
        self.assertFailed(result)

    def test_cli_reads_only_and_reports_observed_scope(self):
        self.negative_logs()
        before = sorted(path.name for path in self.root.iterdir())
        process = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--stdout", str(self.stdout),
             "--stderr", str(self.stderr), "--exit-code=-6", "--workload", "nova-baseline-fail"],
            capture_output=True, text=True, check=False, timeout=10, cwd=self.root)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('"expected_target_failure_verified": true', process.stdout)
        self.assertIn('"hardware_qualified": false', process.stdout)
        self.assertEqual(before, sorted(path.name for path in self.root.iterdir()))


if __name__ == "__main__":
    unittest.main()
