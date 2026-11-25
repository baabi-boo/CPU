"""Offline observer orchestration tests; the simulator/build boundary is mocked.

The dedicated witness reader, metadata shape validator, and bounded file capture
are real. Synthetic process records and metadata do not establish CPU execution.
"""

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nova_observed_campaign_fixtures", ROOT / "tests/nova/test_g1_campaign.py")
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)
campaign = fixtures.campaign


def synthetic_metadata():
    """Structurally valid fixture identities, never a claim about local inputs."""
    observer = campaign._module("htif_observer")

    def identity(scope, path, digest="1" * 64):
        return {"scope": scope, "path": path, "sha256": digest, "size_bytes": 1}

    metadata = {
        "schema_version": 1, "kind": "nova-htif-observer",
        "manifest_path": campaign.OBSERVER_MANIFEST_PATH,
        "manifest_sha256": "2" * 64, "manifest_bytes": 1024,
        "source_pin": observer.PINNED_SPIKE_COMMIT,
        "source": identity("repository", observer.SPIKE_REL + "/fesvr/htif.cc",
                           observer.PINNED_HTIF_SHA256),
        "generated": identity("repository", observer.DEFAULT_OUTPUT_REL + "/htif.cc",
                              observer.GENERATED_HTIF_SHA256),
        "native": identity("repository", observer.NATIVE_REL),
        "header": identity("repository", observer.HEADER_REL),
        "archive": identity("riscv", "lib/libfesvr.a"),
        "installed_header": identity("riscv", "include/fesvr/htif.h",
                                     observer.SOURCE_HEADERS["fesvr/htif.h"]),
        "installed_config": identity("riscv", "include/fesvr/config.h"),
        "source_headers": {
            path: identity("repository", observer.SPIKE_REL + "/" + path, digest)
            for path, digest in observer.SOURCE_HEADERS.items()
        },
        "inputs": {
            name: identity("repository", path,
                           observer.SIM_FLAGS_SHA256 if name == "upstream_sim_flags" else "1" * 64)
            for name, path in observer.INPUT_PATHS.items()
        },
        "link_order": "overlay-object-before-static-fesvr",
        "hardware_qualified": False, "g1_gate_passed": False,
    }
    observer.validate_build_metadata(metadata)
    return metadata


class ObservedCampaignTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CampaignTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.args = self.fixture.args
        self.args.observe_target_exit = True
        self.env = self.fixture.env
        self.metadata = synthetic_metadata()
        self.metadata_calls = []
        self.witness_paths = []
        self.emit_witness = True
        self.event_transform = lambda event: event
        self.record_path = None

    def fake_metadata(self, manifest_path, *, root, environ):
        self.assertEqual(manifest_path, root / campaign.OBSERVER_MANIFEST_PATH)
        self.assertEqual(root, self.root)
        self.metadata_calls.append((len(self.fixture.commands), dict(environ)))
        return copy.deepcopy(self.metadata)

    def capture(self, root, path, kind="artifact", max_bytes=512 * 1024 * 1024):
        if kind == "htif_exit_witness":
            return campaign._module("campaign_artifacts").capture_file(
                root, path, kind=kind, max_bytes=max_bytes)
        return self.fixture.fake_capture(root, path, kind=kind, max_bytes=max_bytes)

    def fake_run(self, *args, **kwargs):
        result = self.fixture.fake_run(*args, **kwargs)
        env = kwargs["env"]
        if "NOVA_HTIF_WITNESS_PATH" in env and self.emit_witness:
            expected = 7 if result["name"].endswith("-nova-baseline-fail") else 0
            event = self.event_transform({
                "schema_version": 1, "kind": "nova-htif-exit",
                "run_id": env["NOVA_HTIF_RUN_ID"],
                "binding_sha256": env["NOVA_HTIF_BINDING_SHA256"],
                "target_exit_present": True, "raw_exit_code": (expected << 1) | 1,
                "target_exit_code": expected, "signal_exit": False,
            })
            data = event if isinstance(event, bytes) else (json.dumps(event) + "\n").encode()
            path = Path(env["NOVA_HTIF_WITNESS_PATH"])
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
            self.witness_paths.append(path)
        return result

    def execute(self, **overrides):
        defaults = {"run_command": self.fake_run, "capture_file": self.capture,
                    "build_observer_metadata": self.fake_metadata}
        defaults.update(overrides)
        with self.fixture.prepared(**defaults):
            record, self.record_path = campaign.execute(self.root, self.args, env=self.env)
        self.assertEqual(json.loads(self.record_path.read_text()), record)
        self.assertFalse(record["hardware_qualified"])
        self.assertFalse(record["g1_gate_passed"])
        self.assertEqual(record["reference_comparison"], "not_run")
        return record

    @staticmethod
    def rows(record):
        return [row for profile in record["profiles"] for row in profile["workloads"]]

    def test_observed_plan_is_read_only_and_cli_flag_selects_schema_two(self):
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        output = io.StringIO()
        with patch.object(campaign, "run_command", side_effect=AssertionError("command ran")), \
             patch.object(campaign, "build_observer_metadata", side_effect=AssertionError("observer probed")), \
             patch.object(campaign, "make_output_dir", side_effect=AssertionError("output created")), \
             contextlib.redirect_stdout(output):
            self.assertEqual(campaign.main([
                "--root", str(self.root), "--plan", "--observe-target-exit"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["plan"]["schema_version"], 2)
        self.assertEqual(result["plan"]["common_build_stages"][0]["id"], "htif-observer-prepare")
        self.assertNotIn(str(self.root), output.getvalue())
        self.assertFalse(result["hardware_qualified"])
        self.assertEqual(before, sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*")))

    def test_legacy_namespace_without_new_option_has_no_observer_keys_or_calls(self):
        del self.args.observe_target_exit
        record = self.execute(build_observer_metadata=lambda *a, **k: self.fail("observer probed"))
        self.assertEqual(record["schema_version"], 1)
        self.assertNotIn("target_exit_observer", record)
        self.assertTrue(all("target_exit" not in row for row in self.rows(record)))
        self.assertEqual(len(self.fixture.commands), 37)
        self.assertEqual(self.witness_paths, [])

    def test_mode_requires_exact_boolean_before_creating_output(self):
        for value in (1, "true", None):
            self.args.observe_target_exit = value
            with self.subTest(value=value), self.fixture.prepared(), self.assertRaisesRegex(ValueError, "boolean"):
                campaign.execute(self.root, self.args, env=self.env)
        self.assertFalse((self.root / "nova-out").exists())

    def test_success_records_separate_bound_target_exit_for_all_thirty_workloads(self):
        original_env = dict(self.env)
        record = self.execute()
        self.assertEqual(record["status"], "workloads_observed", record["reasons"])
        self.assertEqual(record["schema_version"], 2)
        self.assertEqual(record["target_exit_observer"], self.metadata)
        self.assertEqual(record["declared_plan"]["schema_version"], 2)
        self.assertEqual(record["common_stages"][0]["id"], "htif-observer-prepare")
        self.assertEqual(len(self.fixture.commands), 38)
        self.assertEqual(len(self.rows(record)), 30)
        run_ids = set()
        paths = set()
        for profile in record["profiles"]:
            for row in profile["workloads"]:
                target_exit = row["target_exit"]
                self.assertEqual(set(target_exit), {"witness", "binding", "assessment"})
                self.assertFalse(row["assessment"]["target_completion_verified"])
                self.assertTrue(target_exit["assessment"]["target_completion_verified"])
                self.assertTrue(target_exit["assessment"]["target_exit_observed"])
                binding = target_exit["binding"]
                self.assertEqual(set(binding), {
                    "schema_version", "configuration", "workload_id", "run_id",
                    "binary_sha256", "simulator_sha256", "observer_manifest_sha256",
                    "source_revision", "source_tree", "source_state_digest", "max_cycles", "seed",
                })
                self.assertEqual(binding["configuration"], profile["configuration"])
                self.assertEqual(binding["workload_id"], row["id"])
                self.assertEqual(binding["binary_sha256"], row["binary"]["sha256"])
                self.assertEqual(binding["simulator_sha256"], row["simulator_sha256"])
                self.assertEqual(binding["observer_manifest_sha256"], self.metadata["manifest_sha256"])
                for field, source_field in (("source_revision", "revision"), ("source_tree", "tree"),
                                            ("source_state_digest", "state_digest")):
                    self.assertEqual(binding[field], record["source_before"][source_field])
                for field in ("schema_version", "max_cycles", "seed"):
                    self.assertIs(type(binding[field]), int)
                self.assertEqual(binding["max_cycles"], campaign.MAX_CYCLES)
                self.assertEqual(binding["seed"], campaign.SEED)
                self.assertRegex(binding["run_id"], r"^[0-9a-f]{64}$")
                run_ids.add(binding["run_id"])
                event = target_exit["assessment"]["event"]
                digest = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":"),
                                                   allow_nan=False).encode()).hexdigest()
                self.assertEqual(event["binding_sha256"], digest)
                self.assertEqual(event["run_id"], binding["run_id"])
                self.assertEqual(event["target_exit_code"], 7 if row["id"].endswith("-fail") else 0)
                witness = target_exit["witness"]
                self.assertEqual(set(witness), {"path", "kind", "size_bytes", "sha256"})
                self.assertEqual(witness["kind"], "htif_exit_witness")
                self.assertEqual(witness["path"], profile["configuration"] + "-" + row["id"] + ".htif-exit.json")
                self.assertEqual(witness["sha256"], target_exit["assessment"]["witness_sha256"])
                self.assertEqual(witness["size_bytes"], target_exit["assessment"]["witness_bytes"])
                paths.add(witness["path"])
        self.assertEqual(len(run_ids), 30)
        self.assertEqual(len(paths), 30)
        self.assertEqual(self.env, original_env)
        for command in self.fixture.commands:
            observed = "NOVA_HTIF_WITNESS_PATH" in command["env"]
            self.assertEqual(observed, "/simulator-" in command["argv"][0])
            if observed:
                self.assertTrue(Path(command["env"]["NOVA_HTIF_WITNESS_PATH"]).is_absolute())
        self.assertEqual(self.metadata_calls[0][0], 2)  # checker then observer preparation
        self.assertEqual(self.metadata_calls[-1][0], 38)
        self.assertTrue(all(not any(key.startswith("NOVA_HTIF_") for key in env)
                            for _, env in self.metadata_calls))

    def test_independent_records_get_disjoint_run_identifiers(self):
        first = {row["target_exit"]["binding"]["run_id"] for row in self.rows(self.execute())}
        second = {row["target_exit"]["binding"]["run_id"] for row in self.rows(self.execute())}
        self.assertEqual(first & second, set())

    def test_duplicate_random_identifier_stops_before_second_workload(self):
        with patch.object(campaign.secrets, "token_hex", return_value="3" * 64) as nonce:
            record = self.execute()
        self.assertEqual(record["status"], "failed")
        self.assertIn("reused", record["reasons"][0])
        self.assertEqual(self.rows(record)[1]["stage"], {"status": "not_run"})
        self.assertTrue(all(call.args == (32,) for call in nonce.call_args_list))

    def test_ambient_observer_and_link_overrides_are_blocked_even_empty(self):
        for name in ("NOVA_HTIF_WITNESS_PATH", "NOVA_HTIF_RUN_ID", "NOVA_HTIF_BINDING_SHA256",
                     "NOVA_HTIF_OBSERVER_DIR", "NOVA_HTIF_UNKNOWN", "LRISCV", "SIM_LDFLAGS"):
            with self.subTest(name=name):
                self.env[name] = ""
                record = self.execute()
                del self.env[name]
                self.assertEqual(record["status"], "blocked")
                self.assertIn(name, record["reasons"][0])
                self.assertIsNone(record["target_exit_observer"])
                self.assertTrue(all(row["target_exit"] == {"status": "not_run"} for row in self.rows(record)))
        self.assertEqual(self.fixture.commands, [])
        self.assertEqual(self.metadata_calls, [])

    def test_existing_observer_output_is_retained_and_blocks_preflight(self):
        output = self.root / "nova-out/htif-observer"
        output.mkdir(parents=True)
        retained = output / "keep.txt"
        retained.write_text("prior products")
        record = self.execute()
        self.assertEqual(record["status"], "blocked")
        self.assertIn("stale", record["reasons"][0])
        self.assertEqual(retained.read_text(), "prior products")
        self.assertEqual(self.fixture.commands, [])

    def test_failed_preparation_keeps_null_metadata_and_pending_rows(self):
        def run(*args, **kwargs):
            result = self.fake_run(*args, **kwargs)
            if result["name"] == "htif-observer-prepare":
                result.update(status="failed", exit_code=2, reason="command exited unsuccessfully")
            return result
        record = self.execute(run_command=run)
        self.assertEqual(record["status"], "failed")
        self.assertIsNone(record["target_exit_observer"])
        self.assertEqual(self.metadata_calls, [])
        self.assertEqual([row["name"] for row in self.fixture.commands], ["pinned-input-check", "htif-observer-prepare"])

    def test_invalid_prepared_metadata_cannot_authorize_builds(self):
        self.metadata["hardware_qualified"] = True
        record = self.execute()
        self.assertEqual(record["status"], "blocked")
        self.assertIsNone(record["target_exit_observer"])
        self.assertEqual(len(self.fixture.commands), 2)

    def test_observer_drift_after_common_stage_stops_before_simulator_build(self):
        def metadata(*args, **kwargs):
            result = self.fake_metadata(*args, **kwargs)
            if self.fixture.commands[-1]["name"] == "hello-configure":
                result["native"]["sha256"] = "4" * 64
            return result
        record = self.execute(build_observer_metadata=metadata)
        self.assertEqual(record["status"], "failed")
        self.assertIn("observer build metadata changed", record["reasons"][0])
        self.assertEqual(record["target_exit_observer"], self.metadata)
        self.assertFalse(any(call["argv"][0] == "make" for call in self.fixture.commands))

    def test_observer_drift_during_simulator_build_stops_before_workloads(self):
        def metadata(*args, **kwargs):
            result = self.fake_metadata(*args, **kwargs)
            if self.fixture.commands[-1]["name"] == "RocketConfig-build":
                result["manifest_sha256"] = "4" * 64
            return result
        record = self.execute(build_observer_metadata=metadata)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(self.witness_paths, [])
        self.assertTrue(all(row["target_exit"] == {"status": "not_run"} for row in self.rows(record)))

    def test_final_observer_recheck_runs_after_final_profile_inspection(self):
        calls = [0]
        changed = [False]
        def profile(root, env=None):
            calls[0] += 1
            changed[0] = calls[0] > 1
            return copy.deepcopy(self.fixture.profile)
        def metadata(*args, **kwargs):
            result = self.fake_metadata(*args, **kwargs)
            if changed[0]:
                result["archive"]["sha256"] = "4" * 64
            return result
        record = self.execute(inspect_profile=profile, build_observer_metadata=metadata)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(len(self.witness_paths), 30)
        self.assertTrue(any("post-execution observer evidence" in reason for reason in record["reasons"]))

    def test_missing_witness_fails_after_normal_protocol_without_fabricated_identity(self):
        self.emit_witness = False
        record = self.execute()
        row = self.rows(record)[0]
        self.assertEqual(record["status"], "failed")
        self.assertTrue(row["assessment"]["expectation_met"])
        self.assertIsNone(row["target_exit"]["witness"])
        self.assertFalse(row["target_exit"]["assessment"]["target_completion_verified"])
        self.assertEqual(self.rows(record)[1]["target_exit"], {"status": "not_run"})

    def test_wrong_or_signal_terminal_witnesses_fail_closed(self):
        changes = (
            {"signal_exit": True},
            {"target_exit_present": False, "raw_exit_code": None, "target_exit_code": None},
            {"raw_exit_code": 15, "target_exit_code": 7},
            {"run_id": "0" * 64},
            {"binding_sha256": "0" * 64},
            {"raw_exit_code": True},
        )
        for change in changes:
            with self.subTest(change=change):
                self.event_transform = lambda event: {**event, **change}
                record = self.execute()
                assessment = self.rows(record)[0]["target_exit"]["assessment"]
                self.assertEqual(record["status"], "failed")
                self.assertFalse(assessment["target_completion_verified"])
                self.assertFalse(assessment["target_exit_observed"])
                self.assertIsNotNone(self.rows(record)[0]["target_exit"]["witness"])

    def test_oversized_and_malformed_witnesses_do_not_pass(self):
        for payload in (b"x" * 4097, b'{"schema_version":1,"schema_version":1}\n', b"{}"):
            with self.subTest(size=len(payload)):
                self.event_transform = lambda event: payload
                record = self.execute()
                self.assertEqual(record["status"], "failed")
                self.assertFalse(self.rows(record)[0]["target_exit"]["assessment"]["target_completion_verified"])

    def test_symlink_witness_is_not_followed(self):
        def run(*args, **kwargs):
            result = self.fake_run(*args, **kwargs)
            if "NOVA_HTIF_WITNESS_PATH" in kwargs["env"]:
                path = Path(kwargs["env"]["NOVA_HTIF_WITNESS_PATH"])
                outside = self.root / "outside-witness.json"
                path.rename(outside)
                path.symlink_to(outside)
            return result
        record = self.execute(run_command=run)
        self.assertEqual(record["status"], "failed")
        self.assertIsNone(self.rows(record)[0]["target_exit"]["witness"])

    def test_witness_changed_by_parser_is_rejected_and_flag_cleared(self):
        original = campaign.assess_exit
        def assess(path, **kwargs):
            result = original(path, **kwargs)
            path.write_bytes(path.read_bytes() + b" ")
            return result
        record = self.execute(assess_exit=assess)
        self.assertEqual(record["status"], "failed")
        self.assertIn("changed during assessment", record["reasons"][0])
        self.assertFalse(self.rows(record)[0]["target_exit"]["assessment"]["target_completion_verified"])

    def test_witness_changed_after_its_workload_is_caught_during_finalization(self):
        calls = [0]
        def source(root):
            calls[0] += 1
            if calls[0] == 2:
                self.witness_paths[0].write_text("changed\n")
            return copy.deepcopy(self.fixture.source)
        record = self.execute(capture_source=source)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(len(self.witness_paths), 30)
        self.assertFalse(self.rows(record)[0]["target_exit"]["assessment"]["target_completion_verified"])
        self.assertTrue(any("changed before finalization" in reason for reason in record["reasons"]))

    def test_native_error_125_cannot_be_accepted_as_expected_negative_exit(self):
        def run(*args, **kwargs):
            result = self.fake_run(*args, **kwargs)
            if result["name"].endswith("-nova-baseline-fail"):
                result["exit_code"] = 125
            return result
        record = self.execute(run_command=run)
        row = self.rows(record)[2]
        self.assertEqual(record["status"], "failed")
        self.assertEqual(row["stage"]["exit_code"], 125)
        self.assertIsNone(row["assessment"])
        self.assertIsNone(row["target_exit"]["assessment"])
        self.assertIsNotNone(row["target_exit"]["witness"])

    def test_failed_positive_timeout_and_interrupt_take_precedence_over_witness(self):
        changes = (
            ({"status": "failed", "exit_code": 1, "reason": "command exited unsuccessfully"}, "failed"),
            ({"timed_out": True, "reason": "stage deadline exceeded"}, "failed"),
            ({"status": "blocked", "interrupted": True, "reason": "command execution interrupted"}, "blocked"),
        )
        for update, status in changes:
            with self.subTest(update=update):
                def run(*args, **kwargs):
                    result = self.fake_run(*args, **kwargs)
                    if result["name"].endswith("-hello"):
                        result.update(update)
                    return result
                record = self.execute(run_command=run)
                self.assertEqual(record["status"], status)
                self.assertIsNone(self.rows(record)[0]["target_exit"]["assessment"])
                self.assertIsNotNone(self.rows(record)[0]["target_exit"]["witness"])

    def test_protocol_failure_or_optimistic_legacy_flag_cannot_be_overridden(self):
        for update in ({"completion_protocol_observed": False}, {"target_completion_verified": True}):
            with self.subTest(update=update):
                def assess(*args, **kwargs):
                    return {**self.fixture.fake_assessment(*args, **kwargs), **update}
                record = self.execute(assess_workload=assess)
                self.assertEqual(record["status"], "failed")
                self.assertIsNone(self.rows(record)[0]["target_exit"]["assessment"])

    def test_signal_during_witness_assessment_blocks_and_clears_completion(self):
        original = campaign.assess_exit
        def assess(path, **kwargs):
            result = original(path, **kwargs)
            os.kill(os.getpid(), signal.SIGTERM)
            return result
        record = self.execute(assess_exit=assess)
        self.assertEqual(record["status"], "blocked")
        self.assertFalse(self.rows(record)[0]["target_exit"]["assessment"]["target_completion_verified"])
        self.assertTrue(any("SIGTERM" in reason for reason in record["reasons"]))


if __name__ == "__main__":
    unittest.main()
