"""Offline CLI/closure/limit tests; these tests are not native or CPU evidence.

The explicit CLI is exercised separately with actual audited Spike sources.
No source pin is substituted, no compiler is launched, and no synthetic full
build is presented as a real native execution.
"""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("nova_test_host_probe", ROOT / "scripts/nova/htif_host_probe.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class HostProbeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "spike"
        self.source.mkdir()
        self.output = self.root / "fresh-output"

    def test_pinned_closure_has_all_real_units_headers_and_license(self):
        self.assertEqual(probe.PIN, "9c190a07c6838f6392bafa4ad83acea462c7f759")
        self.assertEqual({name for name in probe.SOURCE_HASHES if name.endswith(".cc")},
                         {"fesvr/" + name + ".cc" for name in probe.SOURCE_NAMES})
        self.assertEqual(len(probe.SOURCE_NAMES), 7)
        for name, expected in probe.observer.SOURCE_HEADERS.items():
            self.assertEqual(probe.SOURCE_HASHES[name], expected)
        self.assertEqual(probe.SOURCE_HASHES["fesvr/htif.cc"], probe.observer.PINNED_HTIF_SHA256)
        self.assertEqual(probe.SOURCE_HASHES["LICENSE"],
                         "c65e436d18972c9c4bd192494fe4870bd2e158179474975b80a3559f27631632")
        self.assertIn("fesvr/term.h", probe.SOURCE_HASHES)
        self.assertNotIn("config.h", probe.SOURCE_HASHES)

    def test_unpinned_source_is_rejected_without_pin_override(self):
        (self.source / "fesvr").mkdir()
        (self.source / "fesvr/htif.cc").write_bytes(b"// not the pinned source\n")
        with self.assertRaisesRegex(probe.ProbeError, "SHA256 mismatch"):
            probe.capture_source(self.source, "fesvr/htif.cc", retain=True)
        self.assertFalse(self.output.exists())

    def test_missing_source_and_unknown_source_are_rejected(self):
        with self.assertRaises(probe.observer.ObserverError):
            probe.capture_source(self.source, "fesvr/syscall.cc")
        with self.assertRaisesRegex(probe.ProbeError, "outside"):
            probe.capture_source(self.source, "../outside")

    def test_symlink_and_oversized_source_are_rejected(self):
        sentinel = self.root / "sentinel"
        sentinel.write_bytes(b"not a pinned license")
        (self.source / "LICENSE").symlink_to(sentinel)
        with self.assertRaises(probe.observer.ObserverError):
            probe.capture_source(self.source, "LICENSE")
        (self.source / "LICENSE").unlink()
        with (self.source / "LICENSE").open("wb") as stream:
            stream.truncate(probe.observer.MAX_INPUT_BYTES + 1)
        with self.assertRaises(probe.observer.ObserverError):
            probe.capture_source(self.source, "LICENSE")

    def test_limits_reject_nonfinite_bool_and_out_of_range_values(self):
        invalid = (
            {"total_seconds": 301}, {"total_seconds": 0}, {"total_seconds": True},
            {"total_seconds": float("nan")}, {"total_seconds": float("inf")},
            {"total_seconds": 10 ** 1000}, {"command_seconds": 61},
            {"case_seconds": 31}, {"min_free_gib": 0.5}, {"min_free_gib": 51},
            {"max_log_bytes": True}, {"max_log_bytes": 0},
            {"max_log_bytes": probe.MAX_LOG_BYTES + 1},
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(probe.ProbeError):
                probe.limits(**value)
        self.assertEqual(probe.limits(total_seconds=300)["total_seconds"], 300)
        self.assertEqual(probe.limits()["min_free_gib"], 1)

    def test_default_plan_is_read_only_and_absence_is_explicit(self):
        with patch.object(probe.engine, "run_command") as run:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = probe.main(["--source-root", str(self.source), "--output", str(self.output)])
        run.assert_not_called()
        plan = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(plan["status"], "planned")
        self.assertIs(plan["read_only"], True)
        self.assertIs(plan["ready"], False)
        self.assertTrue(plan["blockers"])
        self.assertEqual(list(self.source.iterdir()), [])
        self.assertFalse(self.output.exists())
        for name in probe.FALSE_FLAGS:
            self.assertIs(plan[name], False)

    def test_real_plan_uses_serial_native_commands_and_twelve_fresh_processes(self):
        plan = probe.plan_probe(self.source)
        self.assertEqual(plan["parallel_jobs"], 1)
        self.assertEqual(plan["native_processes"], 12)
        self.assertEqual(len(plan["cases"]), 12)
        self.assertEqual(len({tuple(case["argv"]) for case in plan["cases"]}), 12)
        compilation = [item for item in plan["commands"] if item["name"].startswith("compile-")]
        self.assertEqual(len(compilation), 10)
        for command in compilation:
            self.assertIn("-std=c++17", command["argv"])
            self.assertIn("-O0", command["argv"])
            self.assertIn("-pthread", command["argv"])
        self.assertFalse(plan["network"])
        self.assertFalse(plan["install"])
        self.assertIn("SYNTHETIC", plan["synthetic_config"])
        observed_link = next(item["argv"] for item in plan["commands"] if item["name"] == "link-observed")
        self.assertLess(observed_link.index("{fresh-output}/objects/nova_htif.o"),
                        observed_link.index("{fresh-output}/libfesvr-host-fixture.a"))
        for variant in ("original", "observed"):
            cases = {case["mode"]: case for case in plan["cases"] if case["variant"] == variant}
            self.assertEqual(set(cases), set(probe.MODES))
            self.assertEqual(cases["signal-only"]["expected_host_exit"], 0)
            self.assertEqual(cases["syscall7-signal"]["expected_host_exit"], 7)
        self.assertEqual(cases["signal-only"]["expected_parser_status"], "failed")
        self.assertEqual(cases["syscall7-signal"]["expected_parser_status"], "failed")

    def test_execution_requires_explicit_source_and_output(self):
        with redirect_stderr(io.StringIO()):
            for arguments in (["--execute"], ["--execute", "--source-root", str(self.source)],
                              ["--execute", "--output", str(self.output)]):
                with self.subTest(arguments=arguments), self.assertRaises(SystemExit) as raised:
                    probe.main(arguments)
                self.assertEqual(raised.exception.code, 2)
        self.assertFalse(self.output.exists())

    def test_unavailable_inputs_block_execution_before_creating_any_output(self):
        with patch.object(probe.engine, "run_command") as run:
            result = probe.execute_probe(self.source, self.output)
        run.assert_not_called()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["commands"], [])
        self.assertTrue(result["reasons"])
        self.assertFalse(self.output.exists())

    def test_missing_native_tools_are_reported_without_launch(self):
        with patch.object(probe.shutil, "which", return_value=None), \
                patch.object(probe.engine, "run_command") as run:
            plan = probe.plan_probe(self.source, self.output)
        run.assert_not_called()
        self.assertEqual(plan["tools"], {"gxx": None, "ar": None, "nm": None})
        self.assertEqual(sum("required native tool is unavailable" in reason
                             for reason in plan["blockers"]), 3)
        self.assertFalse(self.output.exists())

    def test_existing_output_and_symlink_parent_are_never_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "sentinel"
        sentinel.write_bytes(b"preserve this")
        plan = probe.plan_probe(self.source, self.output)
        self.assertTrue(any("already exists" in value for value in plan["blockers"]))
        result = probe.execute_probe(self.source, self.output)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(sentinel.read_bytes(), b"preserve this")
        alias = self.root / "alias"
        alias.symlink_to(self.output, target_is_directory=True)
        plan = probe.plan_probe(self.source, alias / "nested")
        self.assertTrue(any("nonsymlink" in value for value in plan["blockers"]))
        self.assertFalse((self.output / "nested").exists())

    def test_expected_exit_seven_preserves_failed_record_and_rejects_other_failure_causes(self):
        record = {"exit_code": 7, "status": "failed", "reason": "command exited unsuccessfully",
                  "timed_out": False, "stdout_sha256": "a" * 64, "stderr_sha256": "b" * 64}
        self.assertTrue(probe.command_matches(record, 7))
        self.assertEqual(record["status"], "failed")
        for update in ({"timed_out": True}, {"interrupted": True}, {"exit_code": -15},
                       {"stdout_sha256": None}, {"stderr_sha256": None},
                       {"status": "blocked"}, {"reason": "stage log exceeded configured byte limit"}):
            with self.subTest(update=update):
                self.assertFalse(probe.command_matches({**record, **update}, 7))
        self.assertFalse(probe.command_matches(record, 0))

    def test_link_map_and_symbols_require_original_only_baseline_extraction(self):
        self.output.mkdir()
        member = str(self.output / "libfesvr-host-fixture.a") + "(htif.o)"
        (self.output / "original.map").write_text(member + "\n")
        (self.output / "observed.map").write_text("nova_htif_observe_stop\n")
        members = "\n".join(name + ".o" for name in probe.SOURCE_NAMES) + "\n"
        original = "0000 T htif_t::stop()\n"
        observed = original + "0001 T nova_htif_observe_stop(void const*, bool, int, bool)\n"
        facts = probe.verify_linkage(self.output, members, original, observed)
        self.assertFalse(facts["original_htif_member_extracted_in_observed"])
        for bad_members, bad_original, bad_observed in (
                (members + "fake.o\n", original, observed),
                (members, original + original, observed),
                (members, observed, observed), (members, original, original)):
            with self.subTest(symbols=bad_observed), self.assertRaises(probe.ProbeError):
                probe.verify_linkage(self.output, bad_members, bad_original, bad_observed)
        (self.output / "observed.map").write_text("nova_htif_observe_stop\n" + member)
        with self.assertRaisesRegex(probe.ProbeError, "excluded only"):
            probe.verify_linkage(self.output, members, original, observed)

    def test_exclusive_evidence_write_refuses_existing_file(self):
        self.output.mkdir()
        target = self.output / "results.json"
        target.write_bytes(b"existing evidence")
        with self.assertRaises(FileExistsError):
            probe._write_new(target, b"replacement")
        self.assertEqual(target.read_bytes(), b"existing evidence")


if __name__ == "__main__":
    unittest.main()
