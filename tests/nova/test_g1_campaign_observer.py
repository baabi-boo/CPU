"""Offline finalization regressions; synthetic campaigns are not CPU execution."""

import contextlib
import copy
import importlib.util
import os
from pathlib import Path
import signal
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nova_campaign_finalization_fixtures", ROOT / "tests/nova/test_g1_observed_campaign.py")
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)
campaign = fixtures.campaign


class CampaignObserverFinalizationTests(unittest.TestCase):
    def fixture(self, *, observed=True):
        case = fixtures.ObservedCampaignTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        if not observed:
            del case.args.observe_target_exit
        return case

    def assert_deadline_retained(self, record):
        self.assertEqual(record["elapsed_seconds"], 301.0)
        self.assertEqual(sum("aggregate wall-clock deadline exceeded" in reason
                             for reason in record["reasons"]), 1)

    def test_sigterm_during_handler_restoration_reconciles_same_exclusive_record(self):
        for observed, bad_manifest in ((False, False), (True, False), (True, True)):
            with self.subTest(observed=observed, bad_manifest=bad_manifest):
                case = self.fixture(observed=observed)
                if bad_manifest:
                    (case.root / "nova/g1-workloads.json").write_text("{}")
                original_signal = signal.signal
                original_open = Path.open
                previous = {number: signal.getsignal(number)
                            for number in (signal.SIGINT, signal.SIGTERM)}
                previous_context = campaign._CANCELLATION.get()
                injected = []
                restorations = []
                record_opens = []

                def restore(number, handler):
                    result = original_signal(number, handler)
                    if handler is previous[number]:
                        restorations.append(number)
                        if number == signal.SIGINT and not injected:
                            injected.append(True)
                            os.kill(os.getpid(), signal.SIGTERM)
                    return result

                def open_path(path, mode="r", *args, **kwargs):
                    if path.name == "record.json" and any(flag in mode for flag in "wax+"):
                        record_opens.append(mode)
                    return original_open(path, mode, *args, **kwargs)

                with patch.object(signal, "signal", side_effect=restore), \
                     patch.object(Path, "open", new=open_path):
                    record = case.execute()
                self.assertEqual(injected, [True])
                self.assertEqual(record["status"], "blocked")
                self.assertEqual(sum("SIGTERM" in reason for reason in record["reasons"]), 1)
                self.assertEqual(restorations, [signal.SIGINT, signal.SIGTERM])
                self.assertEqual(previous, {number: signal.getsignal(number) for number in previous})
                self.assertIs(campaign._CANCELLATION.get(), previous_context)
                self.assertEqual(record_opens, ["x"])
                if bad_manifest:
                    self.assertEqual(record["profiles"], [])
                    self.assertIsNone(record["target_exit_observer"])
                    self.assertEqual(case.fixture.commands, [])

    def test_validation_failure_without_a_record_still_restores_signal_scope(self):
        case = self.fixture()
        case.args.approved_budget = False
        original_signal = signal.signal
        previous = {number: signal.getsignal(number)
                    for number in (signal.SIGINT, signal.SIGTERM)}
        previous_context = campaign._CANCELLATION.get()
        injected = []

        def restore(number, handler):
            result = original_signal(number, handler)
            if number == signal.SIGINT and handler is previous[number] and not injected:
                injected.append(True)
                os.kill(os.getpid(), signal.SIGTERM)
            return result

        with patch.object(signal, "signal", side_effect=restore), \
             case.fixture.prepared(), self.assertRaisesRegex(ValueError, "approved-budget"):
            campaign.execute(case.root, case.args, env=case.env)
        self.assertEqual(injected, [True])
        self.assertFalse((case.root / "nova-out").exists())
        self.assertEqual(previous, {number: signal.getsignal(number) for number in previous})
        self.assertIs(campaign._CANCELLATION.get(), previous_context)

    def test_initial_serialization_overrun_blocks_legacy_and_observed_records(self):
        for observed in (False, True):
            with self.subTest(observed=observed):
                case = self.fixture(observed=observed)
                case.args.total_timeout_seconds = 300
                clock = [0.0]
                original_dump = campaign.json.dump

                def dump(*args, **kwargs):
                    original_dump(*args, **kwargs)
                    clock[0] = 301.0

                with patch.object(campaign.time, "monotonic", side_effect=lambda: clock[0]), \
                     patch.object(campaign.json, "dump", side_effect=dump):
                    record = case.execute()
                self.assertEqual(record["status"], "blocked")
                self.assert_deadline_retained(record)

    def test_corrective_serialization_overrun_cannot_preserve_success(self):
        case = self.fixture()
        case.args.total_timeout_seconds = 300
        clock = [0.0]
        writes = []
        original_dump = campaign.json.dump

        def dump(record, stream, **kwargs):
            original_dump(record, stream, **kwargs)
            writes.append(record["status"])
            clock[0] = 1.0 if len(writes) == 1 else 301.0

        with patch.object(campaign.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(campaign.json, "dump", side_effect=dump):
            record = case.execute()
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(writes, ["workloads_observed", "workloads_observed", "blocked"])
        self.assert_deadline_retained(record)

    def test_buffered_record_flush_is_included_in_deadline_check(self):
        case = self.fixture()
        case.args.total_timeout_seconds = 300
        clock = [0.0]
        original_dump = campaign.json.dump
        patched = []
        with contextlib.ExitStack() as stack:
            def dump(record, stream, **kwargs):
                original_dump(record, stream, **kwargs)
                if not patched:
                    original_flush = stream.flush

                    def flush():
                        original_flush()
                        clock[0] = 301.0

                    stack.enter_context(patch.object(stream, "flush", side_effect=flush))
                    patched.append(True)

            stack.enter_context(patch.object(campaign.time, "monotonic", side_effect=lambda: clock[0]))
            stack.enter_context(patch.object(campaign.json, "dump", side_effect=dump))
            record = case.execute()
        self.assertEqual(record["status"], "blocked")
        self.assert_deadline_retained(record)

    def test_handler_restoration_time_is_included_in_deadline_check(self):
        case = self.fixture()
        case.args.total_timeout_seconds = 300
        clock = [0.0]
        original_signal = signal.signal
        previous = signal.getsignal(signal.SIGTERM)

        def restore(number, handler):
            result = original_signal(number, handler)
            if number == signal.SIGTERM and handler is previous:
                clock[0] = 301.0
            return result

        with patch.object(campaign.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(signal, "signal", side_effect=restore):
            record = case.execute()
        self.assertEqual(record["status"], "blocked")
        self.assert_deadline_retained(record)

    def test_success_elapsed_includes_initial_serialization(self):
        case = self.fixture()
        clock = [0.0]
        original_dump = campaign.json.dump

        def dump(*args, **kwargs):
            original_dump(*args, **kwargs)
            clock[0] = 5.0

        with patch.object(campaign.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(campaign.json, "dump", side_effect=dump):
            record = case.execute()
        self.assertEqual(record["status"], "workloads_observed")
        self.assertEqual(record["reasons"], [])
        self.assertEqual(record["elapsed_seconds"], 5.0)

    def test_all_drifted_witnesses_are_invalidated_without_skipping_later_rows(self):
        case = self.fixture()
        calls = []
        rechecked = []
        changed = {0, 1, 29}

        def source(root):
            calls.append(root)
            if len(calls) == 2:
                for index in changed:
                    case.witness_paths[index].write_text("changed\n")
            return copy.deepcopy(case.fixture.source)

        def capture(root, path, kind="artifact", max_bytes=512 * 1024 * 1024):
            if len(calls) == 2 and kind == "htif_exit_witness":
                rechecked.append(path)
            return case.capture(root, path, kind=kind, max_bytes=max_bytes)

        record = case.execute(capture_source=source, capture_file=capture)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(rechecked, case.witness_paths)
        self.assertEqual(len(rechecked), 30)
        self.assertEqual(len(record["reasons"]), len(changed))
        for index, row in enumerate(case.rows(record)):
            assessment = row["target_exit"]["assessment"]
            self.assertEqual(assessment["target_completion_verified"], index not in changed)
            self.assertEqual(assessment["target_exit_observed"], index not in changed)
            if index in changed:
                self.assertEqual(assessment["status"], "failed")
                self.assertIsNotNone(row["target_exit"]["witness"])

    def test_missing_first_witness_does_not_skip_a_later_changed_witness(self):
        case = self.fixture()
        calls = []

        def source(root):
            calls.append(root)
            if len(calls) == 2:
                case.witness_paths[0].unlink()
                case.witness_paths[1].write_text("changed\n")
            return copy.deepcopy(case.fixture.source)

        record = case.execute(capture_source=source)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(len(record["reasons"]), 2)
        for row in case.rows(record)[:2]:
            self.assertFalse(row["target_exit"]["assessment"]["target_completion_verified"])
            self.assertFalse(row["target_exit"]["assessment"]["target_exit_observed"])

    def test_later_cancellation_preserves_an_already_detected_witness_failure(self):
        case = self.fixture()
        calls = []
        injected = []

        def source(root):
            calls.append(root)
            if len(calls) == 2:
                case.witness_paths[0].write_text("changed\n")
            return copy.deepcopy(case.fixture.source)

        def capture(root, path, kind="artifact", max_bytes=512 * 1024 * 1024):
            result = case.capture(root, path, kind=kind, max_bytes=max_bytes)
            if (len(calls) == 2 and kind == "htif_exit_witness"
                    and path == case.witness_paths[1] and not injected):
                injected.append(True)
                os.kill(os.getpid(), signal.SIGTERM)
            return result

        record = case.execute(capture_source=source, capture_file=capture)
        self.assertEqual(injected, [True])
        self.assertEqual(record["status"], "failed")
        self.assertTrue(any("changed before finalization" in reason for reason in record["reasons"]))
        self.assertTrue(any("SIGTERM" in reason for reason in record["reasons"]))

    def test_deadline_and_cancellation_do_not_downgrade_existing_failure(self):
        case = self.fixture()
        case.args.total_timeout_seconds = 300
        clock = [0.0]
        calls = []
        writes = []
        original_dump = campaign.json.dump

        def source(root):
            calls.append(root)
            if len(calls) == 2:
                case.witness_paths[0].write_text("changed\n")
            return copy.deepcopy(case.fixture.source)

        def dump(record, stream, **kwargs):
            original_dump(record, stream, **kwargs)
            writes.append(record["status"])
            if len(writes) == 1:
                clock[0] = 301.0
                os.kill(os.getpid(), signal.SIGTERM)

        with patch.object(campaign.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(campaign.json, "dump", side_effect=dump):
            record = case.execute(capture_source=source)
        self.assertEqual(record["status"], "failed")
        self.assertTrue(any("SIGTERM" in reason for reason in record["reasons"]))
        self.assert_deadline_retained(record)


if __name__ == "__main__":
    unittest.main()
