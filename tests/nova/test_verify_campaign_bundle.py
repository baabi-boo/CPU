"""Retained synthetic-file checks only; no CPU, build, or toolchain is run.

Every source, binary, process, and observer identity is invented. Real local
files contain deliberately synthetic protocol examples for the existing parsers.
Passing these tests does not establish execution or hardware qualification.
"""

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


verify = load("nova_verify_bundle_test", ROOT / "scripts/nova/verify_campaign_bundle.py")
fixtures = load("nova_verify_bundle_fixtures", Path(__file__).with_name("test_compare_observed_campaigns.py"))
workloads = load("nova_verify_bundle_workload_fixture", ROOT / "scripts/nova/workload_assessment.py")


def rows(record):
    return [row for profile in record["profiles"] for row in profile["workloads"]]


def stages(record):
    result = [record["preflight"]["checker"], *record["common_stages"]]
    for profile in record["profiles"]:
        result.extend([profile["build"], *(row["stage"] for row in profile["workloads"])])
    return result


def write_record(path, record):
    path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def write_stream(directory, stage, stream, data, assessment=None):
    (directory / stage[stream]).write_bytes(data)
    identity = {stream + "_bytes": len(data), stream + "_sha256": hashlib.sha256(data).hexdigest()}
    stage.update(identity)
    if assessment is not None:
        assessment.update(identity)


def write_witness(directory, row, data):
    extension = row["target_exit"]
    (directory / extension["witness"]["path"]).write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    extension["witness"].update(sha256=digest, size_bytes=len(data))
    extension["assessment"].update(witness_sha256=digest, witness_bytes=len(data))


def synthetic_bundle(directory, observed=False):
    """Create only small invented evidence files beside a complete JSON record."""
    record = (fixtures.synthetic_observed_record("bundle-synthetic") if observed
              else fixtures.fixtures.synthetic_record("bundle-synthetic"))
    for stage in stages(record):
        for stream in ("stdout", "stderr"):
            write_stream(directory, stage, stream, b"Synthetic retained stage output only.\n")
    for row in rows(record):
        contract = workloads.workload_contract(row["id"])
        marker = workloads.HELLO_MARKER if row["id"] == "hello" else contract["expected_marker"]
        stdout = (marker + "\n").encode() if marker else b""
        stderr = (b"*** FAILED *** (tohost = 7)\n*** FAILED *** (exit code =  7)\n"
                  if row["id"] == "nova-baseline-fail" else
                  b"*** PASSED *** Completed after 100 simulation cycles\n")
        write_stream(directory, row["stage"], "stdout", stdout)
        write_stream(directory, row["stage"], "stderr", stderr)
        row["assessment"] = workloads.assess_workload(
            directory / row["stage"]["stdout"], directory / row["stage"]["stderr"],
            row["stage"]["exit_code"], contract, record["resource_limits"]["max_cycles"])
        if observed:
            raw = json.dumps(row["target_exit"]["assessment"]["event"],
                             sort_keys=True, separators=(",", ":")).encode() + b"\n"
            write_witness(directory, row, raw)
    path = directory / "campaign.json"
    write_record(path, record)
    return path, record


class VerifyCampaignBundleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="nova-synthetic-bundle-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "retained"
        self.directory.mkdir()
        self.path, self.record = synthetic_bundle(self.directory)

    def observed(self):
        # Reuse names only in this fixture setup; the verifier itself writes no
        # files and never changes or deletes a retained campaign.
        self.path, self.record = synthetic_bundle(self.directory, observed=True)

    def result(self, expected, reason=None, path=None):
        result = verify.verify_bundle(self.path if path is None else path)
        self.assertEqual(result["status"], expected, result)
        self.assertEqual(result["verification_scope"], "retained_files_and_reported_protocol_only")
        for field in ("hardware_qualified", "g1_gate_passed", "reference_comparison_qualified",
                      "target_completion_verified"):
            self.assertIs(result[field], False)
        self.assertLessEqual(len(result["reasons"]), verify.MAX_REASONS)
        if reason:
            self.assertIn(reason, " ".join(result["reasons"]))
        return result

    def save(self):
        write_record(self.path, self.record)

    def test_legacy_bundle_checks_all_logs_and_remains_protocol_only(self):
        self.assertEqual(verify.compare._validate(self.record), [])
        result = self.result("intact")
        self.assertEqual(result["record_schema_version"], 1)
        self.assertEqual(result["retained_files_checked"], 74)
        self.assertEqual(result["workload_protocols_checked"], 30)
        self.assertEqual(result["witnesses_checked"], 0)
        self.assertEqual(result["record_sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertIn("not authenticate", " ".join(result["limitations"]))

    def test_observed_bundle_checks_thirty_bound_raw_witnesses(self):
        self.observed()
        self.assertEqual(verify.compare._validate(self.record), [])
        result = self.result("intact")
        self.assertEqual(result["record_schema_version"], 2)
        self.assertEqual(result["retained_files_checked"], 106)
        self.assertEqual(result["workload_protocols_checked"], 30)
        self.assertEqual(result["witnesses_checked"], 30)
        self.assertTrue(all(row["target_exit"]["assessment"]["target_completion_verified"]
                            for row in rows(self.record)))

    def test_legacy_optional_scope_omission_is_supported(self):
        for row in rows(self.record):
            row["assessment"].pop("evidence_scope")
        self.save()
        self.result("intact")

    def test_verification_is_read_only_and_uses_shared_record_parser_and_validator(self):
        before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ctime_ns)
                  for path in self.directory.iterdir()}
        with patch.object(verify.compare, "parse_record_bytes", wraps=verify.compare.parse_record_bytes) as parser, \
             patch.object(verify.compare, "read_record", side_effect=AssertionError("no record path reopen")), \
             patch.object(verify.compare, "_validate", wraps=verify.compare._validate) as validator, \
             patch("subprocess.run", side_effect=AssertionError("no commands authorized")), \
             patch("subprocess.Popen", side_effect=AssertionError("no processes authorized")):
            self.result("intact")
        self.assertEqual(parser.call_count, 1)
        self.assertEqual(validator.call_count, 1)
        after = {path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ctime_ns)
                 for path in self.directory.iterdir()}
        self.assertEqual(after, before)

    def test_external_execution_source_and_build_paths_need_not_exist_or_be_opened(self):
        self.observed()
        opened = []
        original = os.open

        def track(path, flags, *args, **kwargs):
            opened.append(os.fspath(path))
            return original(path, flags, *args, **kwargs)

        with patch.object(verify.os, "open", side_effect=track):
            self.result("intact")
        self.assertFalse(any("synthetic-not-executed" in name for name in opened))
        self.assertFalse(any("nova-out" in name or "libfesvr" in name for name in opened))
        self.assertTrue(all(not Path(name).is_absolute() or name == "/" for name in opened))

    def test_cli_reports_json_and_meaningful_status_codes(self):
        for expected, code in (("intact", 0), ("failed", 1), ("blocked", 2)):
            if expected == "failed":
                (self.directory / self.record["common_stages"][0]["stdout"]).unlink()
            elif expected == "blocked":
                self.path.write_text("{}", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                observed = verify.main(["--record", str(self.path)])
            self.assertEqual(observed, code)
            self.assertEqual(json.loads(output.getvalue())["status"], expected)

    def test_missing_or_malformed_record_blocks(self):
        for data in (b"{", b'{"schema_version":1,"schema_version":2}', b"[]", b'{"x":NaN}'):
            with self.subTest(data=data):
                self.path.write_bytes(data)
                self.result("blocked")
        self.path.unlink()
        self.result("blocked")

    def test_shared_record_byte_parser_rejects_invalid_capture_type_and_size(self):
        for raw in ("{}", bytearray(b"{}")):
            with self.subTest(raw_type=type(raw).__name__), self.assertRaises(verify.compare.RecordError):
                verify.compare.parse_record_bytes(raw)
        with patch.object(verify.compare, "MAX_RECORD_BYTES", 2):
            self.assertEqual(verify.compare.parse_record_bytes(b"{}"), {})
            with self.assertRaises(verify.compare.RecordError):
                verify.compare.parse_record_bytes(b"{} ")

    def test_record_parser_cannot_read_outside_during_parent_check_open_race(self):
        outside = self.root / "outside-directory"
        outside.mkdir()
        outside_record = outside / self.path.name
        outside_record.write_bytes(self.path.read_bytes() + b" \n")
        outside_identity = outside_record.stat()
        parked = self.root / "retained-original"
        original_symlink = Path.is_symlink
        original_reader = verify.compare.read_record
        original_open = os.open
        redirected = []
        external_opens = []

        def redirect_after_checks(candidate):
            result = original_symlink(candidate)
            if candidate == Path("/") and not redirected:
                self.directory.rename(parked)
                self.directory.symlink_to(outside, target_is_directory=True)
                redirected.append(True)
            return result

        def restore_after_read(candidate):
            try:
                return original_reader(candidate)
            finally:
                if original_symlink(self.directory):
                    self.directory.unlink()
                    parked.rename(self.directory)

        def track_open(candidate, flags, *args, **kwargs):
            descriptor = original_open(candidate, flags, *args, **kwargs)
            opened = os.fstat(descriptor)
            if ((opened.st_dev, opened.st_ino)
                    == (outside_identity.st_dev, outside_identity.st_ino)):
                external_opens.append(True)
            return descriptor

        with patch.object(Path, "is_symlink", side_effect=redirect_after_checks, autospec=True), \
             patch.object(verify.compare, "read_record", side_effect=restore_after_read), \
             patch.object(verify.os, "open", side_effect=track_open):
            self.result("intact")
        self.assertEqual(external_opens, [])
        self.assertEqual(redirected, [])

    def test_oversized_record_blocks_without_a_large_read(self):
        with self.path.open("wb") as stream:
            stream.truncate(verify.compare.MAX_RECORD_BYTES + 1)
        with patch.object(verify.os, "read", side_effect=AssertionError("oversized record must not be read")):
            self.result("blocked", "byte limit")

    def test_missing_checker_build_common_and_workload_logs_fail(self):
        selected = [self.record["preflight"]["checker"], self.record["common_stages"][0],
                    self.record["profiles"][0]["build"], rows(self.record)[0]["stage"]]
        for stage in selected:
            for stream in ("stdout", "stderr"):
                with self.subTest(stage=stage["name"], stream=stream):
                    path = self.directory / stage[stream]
                    data = path.read_bytes()
                    path.unlink()
                    self.result("failed", "missing")
                    path.write_bytes(data)

    def test_same_size_log_tamper_is_detected_by_actual_hash(self):
        path = self.directory / self.record["common_stages"][0]["stdout"]
        path.write_bytes(b"x" * path.stat().st_size)
        self.result("failed", "SHA256")

    def test_different_size_log_tamper_is_detected(self):
        path = self.directory / rows(self.record)[0]["stage"]["stdout"]
        path.write_bytes(path.read_bytes() + b"extra\n")
        self.result("failed", "size differs")

    def test_actual_log_exceeding_64_mib_is_never_read(self):
        path = self.directory / self.record["preflight"]["checker"]["stdout"]
        with path.open("wb") as stream:
            stream.truncate(verify.MAX_LOG_BYTES + 1)
        self.result("failed", "byte limit")

    def test_forged_passing_assessment_cannot_hide_contradictory_log_bytes(self):
        row = rows(self.record)[0]
        data = b"*** PASSED *** Completed after 100 simulation cycles\nfatal synthetic conflict\n"
        write_stream(self.directory, row["stage"], "stderr", data, row["assessment"])
        self.save()
        self.assertEqual(verify.compare._validate(self.record), [])
        self.result("failed", "protocol failed")

    def test_recorded_cycle_count_is_recomputed(self):
        rows(self.record)[0]["assessment"]["cycles"] = 101
        self.save()
        self.assertEqual(verify.compare._validate(self.record), [])
        self.result("failed", "contradict")

    def test_negative_control_requires_actual_code_seven_protocol(self):
        row = rows(self.record)[2]
        data = b"*** FAILED *** (tohost = 8)\n*** FAILED *** (exit code =  8)\n"
        write_stream(self.directory, row["stage"], "stderr", data, row["assessment"])
        self.save()
        self.assertEqual(verify.compare._validate(self.record), [])
        self.result("failed", "protocol failed")

    def test_malformed_log_encoding_nul_and_partial_line_fail_after_coherent_hash_updates(self):
        row = rows(self.record)[0]
        for data in (b"\xff\n", b"\x00\n", b"unterminated"):
            with self.subTest(data=data):
                write_stream(self.directory, row["stage"], "stderr", data, row["assessment"])
                self.save()
                self.assertEqual(verify.compare._validate(self.record), [])
                self.result("failed", "protocol failed")

    def test_protocol_line_count_has_a_separate_object_allocation_budget(self):
        row = rows(self.record)[0]
        data = b"\n\n*** PASSED *** Completed after 100 simulation cycles\n"
        write_stream(self.directory, row["stage"], "stderr", data, row["assessment"])
        self.save()
        self.assertEqual(verify.compare._validate(self.record), [])
        with patch.object(verify, "MAX_LOG_LINES", 2):
            self.result("failed", "line-count budget")

    def test_protocol_line_budget_counts_bare_cr_and_crlf_boundaries(self):
        row = rows(self.record)[0]
        completion = b"*** PASSED *** Completed after 100 simulation cycles\n"
        for prefix, expected in ((b"\r\r\r", "failed"), (b"\r\n", "intact")):
            with self.subTest(prefix=prefix):
                data = prefix + completion
                write_stream(self.directory, row["stage"], "stderr", data, row["assessment"])
                self.save()
                self.assertEqual(verify.compare._validate(self.record), [])
                with patch.object(verify, "MAX_LOG_LINES", 2):
                    self.result(expected, "line-count budget" if expected == "failed" else None)

    def test_process_timeout_interruption_and_reserved_exit_block_even_with_valid_witness(self):
        self.observed()
        original = copy.deepcopy(self.record)
        for field, value in (("timed_out", True), ("interrupted", True),
                             ("interruption_signal", 15), ("exit_code", 125), ("status", "failed")):
            with self.subTest(field=field):
                self.record = copy.deepcopy(original)
                rows(self.record)[0]["stage"][field] = value
                self.save()
                result = self.result("blocked")
                self.assertEqual(result["retained_files_checked"], 0)
                self.assertEqual(result["witnesses_checked"], 0)

    def test_missing_or_tampered_witness_fails(self):
        self.observed()
        path = self.directory / rows(self.record)[0]["target_exit"]["witness"]["path"]
        data = path.read_bytes()
        path.unlink()
        self.result("failed", "missing")
        path.write_bytes(b"x" * len(data))
        self.result("failed", "SHA256")

    def test_actual_witness_replay_fails_after_coherent_identity_updates(self):
        self.observed()
        first, second = rows(self.record)[:2]
        raw = (self.directory / first["target_exit"]["witness"]["path"]).read_bytes()
        write_witness(self.directory, second, raw)
        self.save()
        self.assertEqual(verify.compare._validate(self.record), [])
        self.result("failed", "replayed")

    def test_witness_event_is_parsed_and_not_trusted_from_record(self):
        self.observed()
        row = rows(self.record)[0]
        event = row["target_exit"]["assessment"]["event"]
        for change in ({"signal_exit": True}, {"target_exit_present": False, "raw_exit_code": None,
                                               "target_exit_code": None},
                       {"raw_exit_code": 15, "target_exit_code": 7}, {"run_id": "f" * 64},
                       {"binding_sha256": "e" * 64}):
            with self.subTest(change=change):
                raw = json.dumps({**event, **change}, sort_keys=True).encode() + b"\n"
                write_witness(self.directory, row, raw)
                self.save()
                self.assertEqual(verify.compare._validate(self.record), [])
                self.result("failed", "witness")

    def test_duplicate_truncated_and_noncanonical_raw_witness_json_fails(self):
        self.observed()
        row = rows(self.record)[0]
        raw = json.dumps(row["target_exit"]["assessment"]["event"]).encode()
        for data in (raw, raw[:-1] + b', "run_id": "duplicate"}\n',
                     raw.replace(b'"raw_exit_code": 1', b'"raw_exit_code": NaN') + b"\n"):
            with self.subTest(data=data):
                write_witness(self.directory, row, data)
                self.save()
                self.assertEqual(verify.compare._validate(self.record), [])
                self.result("failed", "witness")

    def test_wrong_recorded_binding_and_duplicate_run_identity_block(self):
        self.observed()
        original = copy.deepcopy(self.record)
        rows(self.record)[0]["target_exit"]["binding"]["binary_sha256"] = "a" * 64
        self.save()
        self.result("blocked")
        self.record = original
        first, second = rows(self.record)[:2]
        second["target_exit"]["binding"]["run_id"] = first["target_exit"]["binding"]["run_id"]
        fixtures.extension_fixtures.rebind(second)
        self.save()
        self.result("blocked", "reused")

    def test_unsafe_log_references_block_before_any_retained_file_read(self):
        stage = self.record["preflight"]["checker"]
        for reference in ("../outside.log", "/outside.log", "sub/log", "bad\\log", "bad\nlog", ".", ""):
            with self.subTest(reference=reference):
                stage["stdout"] = reference
                self.save()
                result = self.result("blocked")
                self.assertEqual(result["retained_files_checked"], 0)

    def test_log_reference_cannot_alias_witness_or_record_name(self):
        self.observed()
        stage = self.record["preflight"]["checker"]
        for reference in (rows(self.record)[0]["target_exit"]["witness"]["path"], self.path.name):
            with self.subTest(reference=reference):
                stage["stdout"] = reference
                self.save()
                self.assertEqual(verify.compare._validate(self.record), [])
                self.result("blocked", "reused")

    def test_symlink_log_and_witness_are_not_followed(self):
        self.observed()
        for name in (self.record["common_stages"][0]["stdout"],
                     rows(self.record)[0]["target_exit"]["witness"]["path"]):
            with self.subTest(name=name):
                path = self.directory / name
                raw = path.read_bytes()
                external = self.root / "outside"
                external.write_bytes(raw)
                path.unlink()
                path.symlink_to(external)
                self.result("failed", "symlink")
                path.unlink()
                path.write_bytes(raw)

    def test_symlink_record_parent_and_parent_traversal_block(self):
        link = self.root / "linked"
        link.symlink_to(self.directory, target_is_directory=True)
        self.result("blocked", path=link / self.path.name)
        leaf = self.directory / "record-link.json"
        leaf.symlink_to(self.path)
        self.result("blocked", path=leaf)
        self.result("blocked", path=self.directory / ".." / "retained" / self.path.name)

    def test_directory_and_fifo_cannot_be_read_as_logs(self):
        path = self.directory / self.record["preflight"]["checker"]["stdout"]
        path.unlink()
        path.mkdir()
        self.result("failed", "regular")
        path.rmdir()
        os.mkfifo(path)
        self.result("failed", "regular")

    def test_hardlink_alias_with_separate_names_is_rejected(self):
        stage = self.record["preflight"]["checker"]
        stdout, stderr = (self.directory / stage[stream] for stream in ("stdout", "stderr"))
        self.assertEqual(stdout.read_bytes(), stderr.read_bytes())
        stderr.unlink()
        os.link(stdout, stderr)
        self.result("failed", "same file identity")

    def test_aggregate_byte_budget_is_checked_before_log_reads(self):
        self.record["resource_limits"]["max_log_bytes"] = verify.MAX_LOG_BYTES
        for stage in stages(self.record):
            stage["max_log_bytes"] = verify.MAX_LOG_BYTES
            for stream in ("stdout", "stderr"):
                stage[stream + "_bytes"] = verify.MAX_LOG_BYTES
        for row in rows(self.record):
            row["assessment"].update({stream + "_bytes": verify.MAX_LOG_BYTES
                                      for stream in ("stdout", "stderr")})
        self.save()
        self.assertEqual(verify.compare._validate(self.record), [])
        result = self.result("blocked", "aggregate")
        self.assertEqual(result["retained_files_checked"], 0)

    def test_explicit_stage_and_file_count_budgets_fail_closed(self):
        for field in ("MAX_STAGES", "MAX_FILES"):
            with self.subTest(field=field), patch.object(verify, field, 1):
                result = self.result("blocked")
                self.assertEqual(result["retained_files_checked"], 0)

    def test_log_change_during_read_is_detected_even_at_same_size(self):
        target = self.directory / self.record["preflight"]["checker"]["stdout"]
        inode = target.stat().st_ino
        original_read = os.read
        changed = []

        def change(descriptor, amount):
            data = original_read(descriptor, amount)
            if data and os.fstat(descriptor).st_ino == inode and not changed:
                changed.append(True)
                target.write_bytes(b"x" * target.stat().st_size)
            return data

        with patch.object(verify.os, "read", side_effect=change):
            self.result("failed", "changed during")
        self.assertTrue(changed)

    def test_previous_log_is_rechecked_after_other_protocols(self):
        target = self.directory / self.record["preflight"]["checker"]["stdout"]
        original = verify._protocol_assessment
        changed = []

        def change(*args, **kwargs):
            result = original(*args, **kwargs)
            if not changed:
                changed.append(True)
                saved = target.stat()
                target.write_bytes(b"x" * saved.st_size)
                os.utime(target, ns=(saved.st_atime_ns, saved.st_mtime_ns))
            return result

        with patch.object(verify, "_protocol_assessment", side_effect=change):
            self.result("failed", "changed during")

    def test_record_raw_bytes_are_rechecked_after_protocols(self):
        original = verify._protocol_assessment
        changed = []

        def change(*args, **kwargs):
            result = original(*args, **kwargs)
            if not changed:
                changed.append(True)
                # Equivalent JSON still changes the retained record's bytes.
                self.path.write_bytes(self.path.read_bytes() + b" \n")
            return result

        with patch.object(verify, "_protocol_assessment", side_effect=change):
            self.result("failed", "record changed")

    def test_parent_replacement_cannot_redirect_snapshot_readers(self):
        original = verify._protocol_assessment
        changed = []

        def replace(*args, **kwargs):
            result = original(*args, **kwargs)
            if not changed:
                changed.append(True)
                self.directory.rename(self.root / "retained-original")
                outside = self.root / "outside-directory"
                outside.mkdir()
                self.directory.symlink_to(outside, target_is_directory=True)
            return result

        with patch.object(verify, "_protocol_assessment", side_effect=replace):
            result = self.result("failed", "directory")
        # All protocols came from the captured/anchored original directory;
        # there are no replacement files to accidentally pass via a reopen.
        self.assertEqual(result["workload_protocols_checked"], 30)


if __name__ == "__main__":
    unittest.main()
