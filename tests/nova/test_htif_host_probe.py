"""Offline CLI/closure/limit tests; these tests are not native or CPU evidence.

The explicit CLI is exercised separately with actual audited Spike sources.
No source pin is substituted, no compiler is launched, and no synthetic full
build is presented as a real native execution.
"""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import stat
import tempfile
from types import SimpleNamespace
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


class HostProbeFinalizationTests(unittest.TestCase):
    """Failure-only finalization fixtures never fabricate a native execution."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def fixture(self, name):
        output = self.root / name
        output.mkdir()
        (output / "partial.log").write_bytes(b"partial failure evidence\n")
        result = {"kind": "nova-htif-host-probe-result", "status": "failed",
                  "source_pin": probe.PIN, "commands": [], "cases": [],
                  "reasons": ["failure-only fixture; no native process was launched"],
                  **probe.FALSE_FLAGS}
        return output, result

    @contextmanager
    def cancellation_scope(self):
        cancellation, previous = {"signal": None}, {}

        def cancel(number, _frame):
            if cancellation["signal"] is None:
                cancellation["signal"] = number

        def restore():
            for number, handler in list(previous.items()):
                signal.signal(number, handler)
                del previous[number]

        try:
            for number in (signal.SIGINT, signal.SIGTERM):
                previous[number] = signal.getsignal(number)
                signal.signal(number, cancel)
            yield cancellation, restore
        finally:
            restore()

    def assert_saved_failure(self, output, result):
        self.assertEqual(result["status"], "failed")
        self.assertIn("failure-only fixture; no native process was launched", result["reasons"])
        self.assertEqual(json.loads((output / "results.json").read_bytes()), result)
        self.assertEqual(json.loads((output / "commands.json").read_bytes()), [])
        self.assertEqual(result["commands"], [])
        self.assertEqual(result["cases"], [])
        self.assertEqual(result["source_pin"], probe.PIN)
        for name in probe.FALSE_FLAGS:
            self.assertIs(result[name], False)
        inventory = json.loads((output / "artifacts.json").read_bytes())
        self.assertEqual(len({item["path"] for item in inventory}), len(inventory))
        for item in inventory:
            data = (output / item["path"]).read_bytes()
            self.assertEqual(item["bytes"], len(data))
            self.assertEqual(item["sha256"], probe._sha(data))
        self.assertEqual((output / "partial.log").read_bytes(), b"partial failure evidence\n")

    def boundary(self, phase, *, interrupted):
        output, result = self.fixture(phase)
        clock, events, descriptors, creations, syncs = [0.0], [], {}, {}, {}
        original_open, original_sync = os.open, os.fsync
        original_json, original_signal = probe._json, signal.signal
        previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}

        def inject():
            if not events:
                events.append(phase)
                if interrupted:
                    os.kill(os.getpid(), signal.SIGTERM)
                else:
                    clock[0] = 61.0

        def open_file(path, flags, *args, **kwargs):
            descriptor = original_open(path, flags, *args, **kwargs)
            if path in {"commands.json", "results.json", "artifacts.json"} and flags & os.O_CREAT:
                self.assertTrue(flags & os.O_EXCL)
                self.assertTrue(flags & os.O_NOFOLLOW)
                creations[path] = creations.get(path, 0) + 1
                descriptors[descriptor] = path
            return descriptor

        def sync(descriptor):
            original_sync(descriptor)
            name = descriptors.get(descriptor)
            if name is not None:
                syncs[name] = syncs.get(name, 0) + 1
                if phase == name + "-fsync" and syncs[name] == 1:
                    inject()
                if phase == "corrective-" + name + "-fsync" and syncs[name] == 2:
                    inject()

        def serialize(value):
            data = original_json(value)
            if phase == "results-serialization" and value is result:
                inject()
            return data

        def restore(number, handler):
            value = original_signal(number, handler)
            if phase == "handler-restoration" and number == signal.SIGINT and handler is previous[number]:
                # SIGTERM is still owned by the probe after SIGINT is restored.
                inject()
            return value

        with patch.object(probe, "time", SimpleNamespace(monotonic=lambda: clock[0])), \
                patch.object(os, "open", side_effect=open_file), \
                patch.object(os, "fsync", side_effect=sync), \
                patch.object(probe, "_json", side_effect=serialize), \
                patch.object(signal, "signal", side_effect=restore), \
                self.cancellation_scope() as (cancellation, restore_handlers):
            probe._finalize_probe(output, result, 0.0, 60.0, cancellation, restore_handlers)
        self.assertEqual(events, [phase])
        self.assertEqual(creations, {name: 1 for name in ("commands.json", "results.json", "artifacts.json")})
        self.assertLessEqual(syncs["results.json"], 3)
        self.assertLessEqual(syncs["artifacts.json"], 3)
        self.assertEqual(previous, {number: signal.getsignal(number) for number in previous})
        for descriptor in descriptors:
            with self.assertRaises(OSError):
                os.fstat(descriptor)
        self.assert_saved_failure(output, result)
        return result

    def test_real_sigterm_at_terminal_boundaries_is_persisted_without_losing_failure(self):
        for phase in ("commands.json-fsync", "results-serialization", "results.json-fsync",
                      "artifacts.json-fsync", "handler-restoration"):
            with self.subTest(phase=phase):
                result = self.boundary(phase, interrupted=True)
                self.assertIs(result["interrupted"], True)
                self.assertEqual(result["interruption_signal"], signal.SIGTERM)
                self.assertEqual(result["reasons"].count("native comparison interrupted"), 1)

    def test_clock_overrun_in_terminal_work_and_corrections_is_persisted(self):
        for phase in ("commands.json-fsync", "results-serialization", "results.json-fsync",
                      "artifacts.json-fsync", "handler-restoration",
                      "corrective-results.json-fsync", "corrective-artifacts.json-fsync"):
            with self.subTest(phase=phase):
                result = self.boundary(phase, interrupted=False)
                self.assertIs(result["deadline_exhausted"], True)
                self.assertEqual(result["elapsed_seconds"], 61.0)
                self.assertEqual(result["reasons"].count("total native comparison deadline exhausted"), 1)

    def test_terminal_facts_block_success_and_preserve_failure_without_clock_only_rewrites(self):
        for status in ("passed", "blocked", "failed"):
            with self.subTest(status=status):
                result = {"status": status, "reasons": []}
                cancellation = {"signal": signal.SIGTERM}
                with patch.object(probe, "time", SimpleNamespace(monotonic=lambda: 61.0)):
                    changed = probe._retain_final_state(result, 0.0, 60.0, cancellation)
                self.assertTrue(changed)
                self.assertEqual(result["status"], "failed" if status == "failed" else "blocked")
                self.assertTrue(result["interrupted"])
                self.assertTrue(result["deadline_exhausted"])
                with patch.object(probe, "time", SimpleNamespace(monotonic=lambda: 62.0)):
                    changed = probe._retain_final_state(result, 0.0, 60.0, cancellation, refresh_clock=False)
                self.assertFalse(changed)
                self.assertEqual(result["elapsed_seconds"], 61.0)
                self.assertEqual(len(result["reasons"]), 2)

    def test_elapsed_sample_includes_initial_metadata_work_without_an_endless_rewrite(self):
        output, result = self.fixture("elapsed")
        clock, writes = [0.0], []
        original_write = probe._write_owned

        def write(descriptor, data):
            original_write(descriptor, data)
            writes.append(descriptor)
            clock[0] += 1.0

        with patch.object(probe, "time", SimpleNamespace(monotonic=lambda: clock[0])), \
                patch.object(probe, "_write_owned", side_effect=write), \
                self.cancellation_scope() as (cancellation, restore):
            probe._finalize_probe(output, result, 0.0, 60.0, cancellation, restore)
        self.assertEqual(len(writes), 4)
        self.assertEqual(result["elapsed_seconds"], 2.0)
        self.assert_saved_failure(output, result)

    def test_artifact_capture_does_not_start_another_read_after_deadline(self):
        output, result = self.fixture("capture")
        (output / "second.log").write_bytes(b"retained even if not inventoried\n")
        clock, reads = [0.0], []
        original_read = probe._read_artifact

        def read(*args, **kwargs):
            reads.append(clock[0])
            data = original_read(*args, **kwargs)
            clock[0] = 61.0
            return data

        with patch.object(probe, "time", SimpleNamespace(monotonic=lambda: clock[0])), \
                patch.object(probe, "_read_artifact", side_effect=read), \
                self.cancellation_scope() as (cancellation, restore):
            probe._finalize_probe(output, result, 0.0, 60.0, cancellation, restore)
        self.assertEqual(reads, [0.0])
        self.assertIs(result["artifacts_incomplete"], True)
        self.assertIs(result["deadline_exhausted"], True)
        self.assert_saved_failure(output, result)

    def test_chunk_reads_stop_after_clock_expiry_or_real_sigterm(self):
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted):
                output, _ = self.fixture("chunks-" + str(interrupted))
                path = output / "large.log"
                path.write_bytes(b"x" * (3 * 65536))
                clock, reads = [0.0], []
                original_read = os.read

                def read(descriptor, count):
                    reads.append(descriptor)
                    data = original_read(descriptor, count)
                    if interrupted:
                        os.kill(os.getpid(), signal.SIGTERM)
                    else:
                        clock[0] = 61.0
                    return data

                with patch.object(probe, "time", SimpleNamespace(monotonic=lambda: clock[0])), \
                        patch.object(os, "read", side_effect=read), \
                        self.cancellation_scope() as (cancellation, _restore):
                    with self.assertRaises(probe._ProbeStopped):
                        probe._read_artifact(output, path.name, probe.MAX_ARTIFACT_BYTES,
                                             check=lambda: probe._check_remaining(60.0, cancellation))
                self.assertEqual(len(reads), 1)
                with self.assertRaises(OSError):
                    os.fstat(reads[0])
                self.assertEqual(path.stat().st_size, 3 * 65536)

    def test_streaming_traversal_stops_at_file_and_directory_entry_caps(self):
        for directories in (False, True):
            with self.subTest(directories=directories):
                output, _ = self.fixture("iterator-" + str(directories))
                cap = probe.MAX_ARTIFACT_ENTRIES if directories else probe.MAX_ARTIFACT_FILES
                seen = []

                def entries():
                    for index in range(cap + 2):
                        if index > cap:
                            self.fail("artifact iterator was consumed beyond the first excess entry")
                        seen.append(index)
                        info = SimpleNamespace(st_mode=stat.S_IFDIR if directories else stat.S_IFREG, st_size=0)
                        yield SimpleNamespace(name=str(index), stat=lambda *, follow_symlinks: info)

                @contextmanager
                def scandir(_descriptor):
                    yield entries()

                with patch.object(os, "scandir", side_effect=scandir), \
                        patch.object(Path, "rglob") as rglob:
                    with self.assertRaisesRegex(probe.ProbeError, "entry limit|count limit"):
                        list(probe._artifact_paths(output, lambda: None))
                self.assertEqual(len(seen), cap + 1)
                rglob.assert_not_called()

    def test_cancellation_during_enumeration_stops_before_artifact_reads(self):
        output, result = self.fixture("enumeration-signal")
        original_scan = os.scandir

        @contextmanager
        def scandir(descriptor):
            with original_scan(descriptor) as entries:
                def interrupted_entries():
                    for entry in entries:
                        os.kill(os.getpid(), signal.SIGTERM)
                        yield entry
                yield interrupted_entries()

        with patch.object(os, "scandir", side_effect=scandir), \
                patch.object(probe, "_read_artifact") as read, \
                self.cancellation_scope() as (cancellation, restore):
            probe._finalize_probe(output, result, 0.0, float("inf"), cancellation, restore)
        read.assert_not_called()
        self.assertIs(result["interrupted"], True)
        self.assertIs(result["artifacts_incomplete"], True)
        self.assert_saved_failure(output, result)

    def test_metadata_write_failure_retains_original_reason_and_partial_evidence(self):
        output, result = self.fixture("metadata-failure")
        original_write = probe._write_new

        def write(path, data):
            original_write(path, data)
            if path.name == "commands.json":
                raise OSError("injected commands durability failure")

        with patch.object(probe, "_write_new", side_effect=write), \
                self.cancellation_scope() as (cancellation, restore):
            probe._finalize_probe(output, result, 0.0, float("inf"), cancellation, restore)
        self.assertIs(result["artifacts_incomplete"], True)
        self.assertEqual(sum("injected commands durability failure" in reason for reason in result["reasons"]), 1)
        self.assert_saved_failure(output, result)

    def test_repeated_metadata_failures_do_not_cause_unbounded_corrections(self):
        output, result = self.fixture("repeated-failure")
        attempts = []
        original_write = probe._write_owned

        def write(descriptor, data):
            original_write(descriptor, data)
            if data.startswith(b"["):
                attempts.append(descriptor)
                raise OSError("injected inventory durability failure " + str(len(attempts)))

        with patch.object(probe, "_write_owned", side_effect=write), \
                self.cancellation_scope() as (cancellation, restore):
            probe._finalize_probe(output, result, 0.0, float("inf"), cancellation, restore)
        self.assertEqual(len(attempts), 2)
        self.assertIs(result["artifacts_incomplete"], True)
        self.assertEqual(sum("injected inventory durability failure" in reason for reason in result["reasons"]), 1)
        self.assert_saved_failure(output, result)

    def test_finalization_never_reopens_or_overwrites_an_existing_result(self):
        output, result = self.fixture("existing-result")
        sentinel = output / "results.json"
        sentinel.write_bytes(b"previous evidence must survive\n")
        with self.cancellation_scope() as (cancellation, restore):
            probe._finalize_probe(output, result, 0.0, float("inf"), cancellation, restore)
        self.assertEqual(sentinel.read_bytes(), b"previous evidence must survive\n")
        self.assertEqual(result["status"], "failed")
        self.assertIs(result["artifacts_incomplete"], True)
        self.assertTrue(any("could not retain results.json" in reason for reason in result["reasons"]))
        self.assertEqual(result["commands"], [])
        self.assertEqual(result["cases"], [])


if __name__ == "__main__":
    unittest.main()
