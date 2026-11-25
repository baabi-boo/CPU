"""Synthetic HTIF observer witnesses; these tests never execute a processor."""

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


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/nova/htif_exit_evidence.py"
SPEC = importlib.util.spec_from_file_location("nova_htif_exit_evidence", SCRIPT)
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)
RUN_ID = "a" * 64
BINDING = "b" * 64


class HtifExitEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.witness = self.root / "exit.json"
        self.write_event()

    def write_event(self, **changes):
        event = {
            "schema_version": 1, "kind": "nova-htif-exit", "run_id": RUN_ID,
            "binding_sha256": BINDING, "target_exit_present": True,
            "raw_exit_code": 1, "target_exit_code": 0, "signal_exit": False,
        }
        event.update(changes)
        self.write_object(event)
        return event

    def write_object(self, event):
        self.witness.write_bytes(json.dumps(event, separators=(",", ":")).encode() + b"\n")

    def assess(self, path=None, **changes):
        constraints = {"run_id": RUN_ID, "binding_sha256": BINDING, "expected_target_exit": 0}
        constraints.update(changes)
        return evidence.assess_exit(self.witness if path is None else path, **constraints)

    def assertFailed(self, result):
        self.assertEqual(result["status"], "failed")
        for flag in ("target_exit_observed", "target_completion_verified",
                     "hardware_qualified", "g1_gate_passed"):
            self.assertIs(result[flag], False)
        self.assertTrue(result["reasons"])

    def test_matching_zero_and_code7_observations_have_exact_result_fields(self):
        for code in (0, 7):
            with self.subTest(code=code):
                event = self.write_event(raw_exit_code=(code << 1) | 1, target_exit_code=code)
                data = self.witness.read_bytes()
                result = self.assess(expected_target_exit=code)
                self.assertEqual(set(result), {
                    "status", "target_exit_observed", "target_completion_verified",
                    "hardware_qualified", "g1_gate_passed", "reasons",
                    "witness_sha256", "witness_bytes", "event",
                })
                self.assertEqual(result["status"], "observed")
                self.assertIs(result["target_exit_observed"], True)
                self.assertIs(result["target_completion_verified"], True)
                self.assertIs(result["hardware_qualified"], False)
                self.assertIs(result["g1_gate_passed"], False)
                self.assertEqual(result["reasons"], [])
                self.assertEqual(result["event"], event)
                self.assertEqual(result["witness_sha256"], hashlib.sha256(data).hexdigest())
                self.assertEqual(result["witness_bytes"], len(data))

    def test_wrong_target_code_never_preserves_a_completion_flag(self):
        for raw, decoded, expected in ((1, 0, 7), (15, 7, 0), (3, 1, 0),
                                       (251, 125, 7), ((1 << 31) - 1, (1 << 30) - 1, 0)):
            with self.subTest(raw=raw, expected=expected):
                event = self.write_event(raw_exit_code=raw, target_exit_code=decoded)
                result = self.assess(expected_target_exit=expected)
                self.assertFailed(result)
                self.assertEqual(result["event"], event)
                self.assertIsNotNone(result["witness_sha256"])

    def test_absent_and_signaled_terminal_states_fail(self):
        for present, signaled in ((False, False), (False, True), (True, True)):
            with self.subTest(present=present, signaled=signaled):
                self.write_event(target_exit_present=present, signal_exit=signaled,
                                 raw_exit_code=1 if present else None,
                                 target_exit_code=0 if present else None)
                self.assertFailed(self.assess())
        self.write_event(target_exit_present=False)
        self.assertFailed(self.assess())

    def test_raw_exit_requires_positive_odd_actual_signed32_integer(self):
        for raw in (None, False, True, 0, -1, -3, 2, 14, 1 << 31, (1 << 31) + 1,
                    "1", 1.0):
            with self.subTest(raw=repr(raw)):
                self.write_event(raw_exit_code=raw)
                self.assertFailed(self.assess())

    def test_decoded_exit_requires_actual_integer_consistent_with_raw(self):
        for decoded in (None, False, True, "0", 0.0, 1, -1):
            with self.subTest(decoded=repr(decoded)):
                self.write_event(target_exit_code=decoded)
                self.assertFailed(self.assess())
        self.write_event(raw_exit_code=15, target_exit_code=0)
        self.assertFailed(self.assess(expected_target_exit=7))

    def test_schema_and_boolean_types_are_not_coerced(self):
        cases = {
            "schema_version": (True, "1", 1.0, 2, None),
            "target_exit_present": (1, "true", None),
            "signal_exit": (0, "false", None),
            "kind": (True, None, "nova-htif-EXIT"),
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=repr(value)):
                    self.write_event(**{field: value})
                    self.assertFailed(self.assess())

    def test_every_field_is_required_and_extra_fields_are_rejected(self):
        original = self.write_event()
        for field in original:
            with self.subTest(missing=field):
                event = dict(original)
                del event[field]
                self.write_object(event)
                self.assertFailed(self.assess())
        self.write_event(target_completion_verified=True)
        self.assertFailed(self.assess())

    def test_wrong_binding_or_replayed_run_id_fails(self):
        for field in ("run_id", "binding_sha256"):
            with self.subTest(field=field):
                self.write_event(**{field: "c" * 64})
                self.assertFailed(self.assess())
        self.write_event()
        self.assertFailed(self.assess(run_id="c" * 64))
        self.assertFailed(self.assess(binding_sha256="c" * 64))

    def test_event_identities_require_exact_lowercase_hex64(self):
        for field in ("run_id", "binding_sha256"):
            for value in (None, 1, "", "a" * 63, "A" * 64, "g" * 64, "a" * 64 + "\n"):
                with self.subTest(field=field, value=repr(value)):
                    self.write_event(**{field: value})
                    self.assertFailed(self.assess())

    def test_invalid_caller_constraints_never_read_a_file(self):
        cases = {
            "run_id": (None, False, b"a" * 64, "a" * 63, "A" * 64),
            "binding_sha256": (None, False, b"b" * 64, "b" * 63, "B" * 64),
            "expected_target_exit": (None, False, True, "0", 0.0, -1, 1, 125),
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=repr(value)), \
                     patch.object(evidence, "_read_witness") as read:
                    self.assertFailed(self.assess(**{field: value}))
                    read.assert_not_called()

    def test_missing_newline_truncation_and_multiple_records_are_rejected(self):
        complete = self.witness.read_bytes()
        for data in (b"", b"\n", complete[:-1], complete[:-2] + b"\n", complete + complete):
            with self.subTest(data=data):
                self.witness.write_bytes(data)
                result = self.assess()
                self.assertFailed(result)
                self.assertIsNone(result["event"])
                self.assertEqual(result["witness_bytes"], len(data))
                self.assertEqual(result["witness_sha256"], hashlib.sha256(data).hexdigest())

    def test_invalid_encoding_nonobject_and_binary_json_are_rejected(self):
        complete = self.witness.read_bytes()
        for data in (b"\xff\n", b"\xef\xbb\xbf" + complete, b"\x00" + complete,
                     b"null\n", b"[]\n", b'"text"\n', complete + b"true\n"):
            with self.subTest(data=data):
                self.witness.write_bytes(data)
                self.assertFailed(self.assess())

    def test_duplicate_keys_include_equivalent_escaped_keys(self):
        complete = self.witness.read_bytes()
        for prefix in (b'{"schema_version":1,',
                       b'{"\\u0072un_id":"' + RUN_ID.encode() + b'",'):
            with self.subTest(prefix=prefix):
                self.witness.write_bytes(prefix + complete[1:])
                result = self.assess()
                self.assertFailed(result)
                self.assertIsNone(result["event"])

    def test_float_nonfinite_and_noncanonical_integer_lexemes_are_rejected(self):
        complete = self.witness.read_bytes()
        for token in (b"1.0", b"1e0", b"NaN", b"Infinity", b"-Infinity", b"01", b"+1"):
            with self.subTest(token=token):
                self.witness.write_bytes(complete.replace(b'"raw_exit_code":1',
                                                         b'"raw_exit_code":' + token))
                self.assertFailed(self.assess())
        self.witness.write_bytes(complete.replace(b'"target_exit_code":0',
                                                 b'"target_exit_code":-0'))
        self.assertFailed(self.assess())

    def test_nested_and_deep_json_are_rejected_without_recursion(self):
        for data in (b'{"raw_exit_code":{"nested":1}}\n',
                     b'{"raw_exit_code":[1]}\n', b"[" * 1500 + b"0" + b"]" * 1500 + b"\n"):
            with self.subTest(size=len(data)):
                self.witness.write_bytes(data)
                self.assertFailed(self.assess())

    def test_4096_byte_limit_is_inclusive_and_oversize_is_not_read(self):
        data = self.witness.read_bytes()
        bounded = data[:-1] + b" " * (4096 - len(data)) + b"\n"
        self.assertEqual(len(bounded), 4096)
        self.witness.write_bytes(bounded)
        self.assertEqual(self.assess()["status"], "observed")
        self.witness.write_bytes(bounded + b"\n")
        with patch.object(evidence.os, "read", wraps=os.read) as read:
            result = self.assess()
            self.assertFailed(result)
            self.assertIsNone(result["witness_bytes"])
            read.assert_not_called()

    def test_missing_path_directory_and_fifo_fail_without_creating_files(self):
        values = [self.root / "missing" / "exit.json", self.root]
        if hasattr(os, "mkfifo"):
            fifo = self.root / "witness.fifo"
            os.mkfifo(fifo)
            values.append(fifo)
        before = sorted(path.name for path in self.root.iterdir())
        for value in values:
            with self.subTest(path=value.name):
                self.assertFailed(self.assess(path=value))
        self.assertEqual(before, sorted(path.name for path in self.root.iterdir()))

    def test_leaf_and_parent_symlinks_fail(self):
        leaf = self.root / "exit-link.json"
        leaf.symlink_to(self.witness)
        self.assertFailed(self.assess(path=leaf))
        parent = self.root / "parent-link"
        parent.symlink_to(self.root, target_is_directory=True)
        self.assertFailed(self.assess(path=parent / self.witness.name))
        self.assertFailed(self.assess(path=parent / ".." / self.root.name / self.witness.name))

    def test_invalid_path_types_fail_cleanly(self):
        for value in (None, 12, b"path", "", "\x00"):
            with self.subTest(value=repr(value)):
                self.assertFailed(evidence.assess_exit(
                    value, run_id=RUN_ID, binding_sha256=BINDING, expected_target_exit=0))

    def test_unreadable_file_does_not_leak_os_details(self):
        with patch.object(evidence.os, "open", side_effect=OSError("private fixture detail")):
            result = self.assess()
        self.assertFailed(result)
        self.assertNotIn("private fixture detail", json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_content_change_during_read_fails(self):
        read = os.read
        before = self.witness.stat()
        changed = False

        def change_after_read(descriptor, size):
            nonlocal changed
            data = read(descriptor, size)
            if data and not changed:
                changed = True
                self.witness.write_bytes(data.replace(b'"target_exit_code":0',
                                                     b'"target_exit_code":7'))
                os.utime(self.witness, ns=(before.st_atime_ns, before.st_mtime_ns + 1000000))
            return data

        with patch.object(evidence.os, "read", side_effect=change_after_read):
            result = self.assess()
        self.assertFailed(result)
        self.assertIsNone(result["witness_sha256"])

    def test_replaced_leaf_during_read_fails(self):
        read = os.read
        changed = False

        def replace_after_read(descriptor, size):
            nonlocal changed
            data = read(descriptor, size)
            if data and not changed:
                changed = True
                replacement = self.root / "replacement.json"
                replacement.write_bytes(data)
                replacement.replace(self.witness)
            return data

        with patch.object(evidence.os, "read", side_effect=replace_after_read):
            self.assertFailed(self.assess())

    def test_parent_replaced_by_symlink_during_read_fails(self):
        parent = self.root / "original"
        parent.mkdir()
        self.witness = self.witness.replace(parent / "exit.json")
        read = os.read
        changed = False

        def replace_parent_after_read(descriptor, size):
            nonlocal changed
            data = read(descriptor, size)
            if data and not changed:
                changed = True
                moved = parent.rename(self.root / "moved")
                parent.symlink_to(moved, target_is_directory=True)
            return data

        with patch.object(evidence.os, "read", side_effect=replace_parent_after_read):
            self.assertFailed(self.assess())

    def test_cli_returns_json_without_mutating_the_witness(self):
        before = self.witness.read_bytes()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = evidence.main([
                "--witness", str(self.witness), "--run-id", RUN_ID,
                "--binding-sha256", BINDING, "--expected-target-exit", "0",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "observed")
        self.assertEqual(self.witness.read_bytes(), before)
        self.assertEqual(list(self.root.iterdir()), [self.witness])

    def test_cli_failure_and_missing_arguments_have_nonzero_status(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = evidence.main([
                "--witness", str(self.witness), "--run-id", RUN_ID,
                "--binding-sha256", BINDING, "--expected-target-exit", "7",
            ])
        self.assertEqual(code, 1)
        self.assertFailed(json.loads(output.getvalue()))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            evidence.main([])
        self.assertEqual(raised.exception.code, 2)

    def test_cli_works_outside_repository(self):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--witness", str(self.witness),
             "--run-id", RUN_ID, "--binding-sha256", BINDING,
             "--expected-target-exit", "0"],
            cwd=self.root, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "observed")


if __name__ == "__main__":
    unittest.main()
