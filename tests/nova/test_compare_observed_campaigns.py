"""Offline schema-2 producer/comparator tests; no CPU or build is executed.

Synthetic identity fixtures exercise rejection and comparison. Integration uses
the real planner, runner, log/witness readers and serializer around the existing
explicitly synthetic process, source, toolchain and artifact boundaries.
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


def load_module(name, filename):
    specification = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


fixtures = load_module("nova_observed_compare_legacy_fixtures", "test_compare_campaigns.py")
extension_fixtures = load_module("nova_observed_compare_extension_fixtures", "test_observed_record.py")
integration = load_module("nova_observed_compare_integration_fixtures", "test_campaign_integration.py")
compare = fixtures.compare


def rows(record):
    return [row for profile in record["profiles"] for row in profile["workloads"]]


def refresh_plan(record):
    record["plan_sha256"] = hashlib.sha256(extension_fixtures.canonical(record["declared_plan"])).hexdigest()


def bind_observer_source(source, metadata):
    flags = metadata["inputs"]["upstream_sim_flags"]
    source["source_inputs"][flags["path"]] = flags["sha256"]
    fixtures.refresh_source_digest(source)


def bind_observer_profile(profile, metadata):
    flags = metadata["inputs"]["upstream_sim_flags"]
    if flags["path"] in profile.get("source_inputs", {}):
        profile["source_inputs"][flags["path"]]["sha256"] = flags["sha256"]
    for observer_field, profile_field in (("archive", "fesvr_library"), ("installed_header", "fesvr_header")):
        if profile_field in profile.get("collateral", {}):
            identity = metadata[observer_field]
            profile["collateral"][profile_field].update(
                path=identity["path"], sha256=identity["sha256"], bytes=identity["size_bytes"])


def rebind_record(record):
    """Update invented row context after intentional coherent fixture changes."""
    source = record["source_before"]
    for profile in record["profiles"]:
        for row in profile["workloads"]:
            row["target_exit"]["binding"].update(
                configuration=profile["configuration"], workload_id=row["id"],
                binary_sha256=row["binary"]["sha256"], simulator_sha256=row["simulator_sha256"],
                observer_manifest_sha256=record["target_exit_observer"]["manifest_sha256"],
                source_revision=source["revision"], source_tree=source["tree"],
                source_state_digest=source["state_digest"],
                max_cycles=record["resource_limits"]["max_cycles"], seed=record["resource_limits"]["seed"])
            extension_fixtures.rebind(row)


def synthetic_observed_record(checkout, jobs=2):
    """Return a complete, coherent invented record, never execution evidence."""
    record = fixtures.synthetic_record(checkout, jobs=jobs)
    extension = extension_fixtures.synthetic_record(checkout)
    record.update(schema_version=2, target_exit_observer=extension["target_exit_observer"])
    for field in ("source_before", "source_after"):
        bind_observer_source(record[field], record["target_exit_observer"])
    for profile in (record["preflight"]["profile"], record["profile_after"]):
        bind_observer_profile(profile, record["target_exit_observer"])
    plan = fixtures.planner.build_plan(ROOT, jobs=jobs, observe_target_exit=True)
    record["declared_plan"] = json.loads(json.dumps(plan).replace(str(ROOT), "<repo>"))
    refresh_plan(record)
    preparation = fixtures.synthetic_stage("htif-observer-prepare")
    record["common_stages"].insert(0, preparation)
    for stage, declared in zip(record["common_stages"], record["declared_plan"]["common_build_stages"]):
        stage.update(command=[arg.replace("<repo>", record["execution_paths"]["repository"])
                              for arg in declared["argv"]], timeout_seconds=declared["timeout_seconds"])
    for profile, declared in zip(record["profiles"], record["declared_plan"]["profiles"]):
        profile["build"]["command"] = [arg.replace("<repo>", record["execution_paths"]["repository"])
                                       for arg in declared["build"]["argv"]]
    for row, observed in zip(rows(record), rows(extension)):
        row["target_exit"] = observed["target_exit"]
    rebind_record(record)
    return record


class CompareObservedCampaignsTests(unittest.TestCase):
    def setUp(self):
        self.left = synthetic_observed_record("observed-left")
        self.right = synthetic_observed_record("observed-right")

    def result(self, left=None, right=None):
        result = compare.compare_records(self.left if left is None else left,
                                         self.right if right is None else right)
        for field in ("hardware_qualified", "g1_gate_passed", "reference_comparison_qualified"):
            self.assertIs(result[field], False)
        self.assertEqual(result["reference_comparison"], "not_run")
        self.assertEqual(result["comparison_scope"], "recorded_input_and_artifact_identities_only")
        self.assertNotIn("target_completion_verified", result)
        return result

    def assert_blocked(self, right, text=None):
        result = self.result(right=right)
        self.assertEqual(result["status"], "blocked", result)
        if text:
            self.assertTrue(any(text in reason for reason in result["reasons"]), result["reasons"])

    def test_fresh_witness_identities_have_equal_stable_semantics(self):
        self.assertEqual(compare._validate(self.left), [])
        self.assertEqual(compare._validate(self.right), [])
        self.assertEqual(len(compare.observed_record.run_ids(self.left)), 30)
        self.assertFalse(compare.observed_record.run_ids(self.left) & compare.observed_record.run_ids(self.right))
        self.assertTrue(all(a["target_exit"]["witness"]["sha256"] != b["target_exit"]["witness"]["sha256"]
                            for a, b in zip(rows(self.left), rows(self.right))))
        result = self.result()
        self.assertEqual(result["status"], "consistent", result["reasons"])
        self.assertNotEqual(result["record_sha256"]["left"], result["record_sha256"]["right"])
        self.assertTrue(any("not authenticated" in line for line in result["limitations"]))
        self.assertTrue(all(not row["assessment"]["target_completion_verified"] for row in rows(self.left)))

    def test_raw_witness_format_and_nonce_changes_do_not_change_semantic_comparison(self):
        for row in rows(self.right):
            raw = (json.dumps(row["target_exit"]["assessment"]["event"], indent=2) + "\n").encode()
            extension_fixtures.retain_event(row, raw=raw)
        self.assertEqual(compare._validate(self.right), [])
        self.assertEqual(self.result()["status"], "consistent")

    def test_comparison_is_read_only_and_does_not_open_retained_files(self):
        before = copy.deepcopy((self.left, self.right))
        with patch("builtins.open", side_effect=AssertionError("unexpected file read")), \
             patch("os.open", side_effect=AssertionError("unexpected file read")):
            self.assertEqual(self.result()["status"], "consistent")
        self.assertEqual((self.left, self.right), before)

    def test_mixed_campaign_versions_are_not_comparable(self):
        legacy = fixtures.synthetic_record("legacy")
        for left, right in ((legacy, self.right), (self.left, legacy)):
            result = self.result(left, right)
            self.assertEqual(result["status"], "blocked")
            self.assertIn("schemas", result["reasons"][0])

    def test_schema_downgrade_retaining_observer_fields_is_blocked(self):
        self.right["schema_version"] = 1
        self.assert_blocked(self.right, "schema-1")
        legacy = fixtures.synthetic_record("legacy")
        legacy["target_exit_observer"] = None
        self.assert_blocked(legacy, "schema-1")
        legacy.pop("target_exit_observer")
        rows(legacy)[0]["target_exit"] = {"status": "not_run"}
        self.assert_blocked(legacy, "schema-1")

    def test_legacy_records_remain_protocol_only_and_accepted(self):
        left, right = fixtures.synthetic_record("legacy-left"), fixtures.synthetic_record("legacy-right")
        self.assertEqual(self.result(left, right)["status"], "consistent")
        for target in (right, rows(right)[0]["assessment"]):
            target["target_completion_verified"] = True
            self.assertEqual(self.result(left, right)["status"], "blocked")
            target.pop("target_completion_verified")

    def test_schema_two_and_extension_cannot_be_missing_or_coerced(self):
        for value in (True, 2.0, "2", 0, 3, None):
            with self.subTest(version=value):
                record = copy.deepcopy(self.right)
                record["schema_version"] = value
                self.assert_blocked(record, "schema")
        for field, value in (("target_exit_observer", None), ("profiles", {}), ("resource_limits", [])):
            with self.subTest(field=field):
                record = copy.deepcopy(self.right)
                record[field] = value
                self.assert_blocked(record)
        record = copy.deepcopy(self.right)
        del rows(record)[-1]["target_exit"]
        self.assert_blocked(record, "extension")

    def test_nonce_reuse_inside_a_campaign_is_blocked_after_coherent_rebinding(self):
        first, second = rows(self.right)[:2]
        second["target_exit"]["binding"]["run_id"] = first["target_exit"]["binding"]["run_id"]
        extension_fixtures.rebind(second)
        self.assert_blocked(self.right, "reused within")

    def test_nonce_replay_across_different_workload_positions_is_blocked(self):
        last = rows(self.right)[-1]
        last["target_exit"]["binding"]["run_id"] = rows(self.left)[0]["target_exit"]["binding"]["run_id"]
        extension_fixtures.rebind(last)
        self.assertEqual(compare._validate(self.right), [])
        self.assert_blocked(self.right, "reused across")

    def test_copying_all_witness_rows_to_another_checkout_is_blocked(self):
        for left, right in zip(rows(self.left), rows(self.right)):
            right["target_exit"] = copy.deepcopy(left["target_exit"])
        self.assertEqual(compare._validate(self.right), [])
        self.assert_blocked(self.right, "reused across")

    def test_all_other_qualification_claims_stay_false(self):
        for flag in compare.CLAIM_FLAGS:
            with self.subTest(flag=flag):
                record = copy.deepcopy(self.right)
                record[flag] = True
                self.assert_blocked(record, "claim")
        record = copy.deepcopy(self.right)
        rows(record)[0]["assessment"]["target_completion_verified"] = True
        self.assert_blocked(record, "protocol-only")
        record = copy.deepcopy(self.right)
        record["extra"] = {"target_exit": {"assessment": {"target_completion_verified": True}}}
        self.assert_blocked(record, "outside")

    def test_valid_extension_does_not_override_normal_process_log_or_artifact_failures(self):
        changes = (
            lambda record: rows(record)[0]["stage"].update(status="failed", exit_code=1),
            lambda record: rows(record)[0]["stage"].update(timed_out=True),
            lambda record: rows(record)[0]["stage"].update(interrupted=True),
            lambda record: rows(record)[2]["stage"].update(exit_code=125),
            lambda record: rows(record)[0]["assessment"].update(expectation_met=False),
            lambda record: rows(record)[0]["assessment"].update(stdout_sha256=fixtures.digest("changed log")),
            lambda record: rows(record)[0]["binary_after"].update(sha256=fixtures.digest("changed ELF")),
            lambda record: record["profiles"][0]["artifacts"]["artifacts"][1].update(path="elsewhere.sv"),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                record = copy.deepcopy(self.right)
                change(record)
                self.assertEqual(compare.observed_record.validate_extension(record), [])
                self.assert_blocked(record)

    def test_changed_exit_semantics_cannot_be_hidden_by_fresh_witness_hashes(self):
        for changes in ({"signal_exit": True}, {"target_exit_code": 7, "raw_exit_code": 15},
                        {"target_exit_present": False, "target_exit_code": None, "raw_exit_code": None}):
            with self.subTest(changes=changes):
                record = copy.deepcopy(self.right)
                row = rows(record)[0]
                row["target_exit"]["assessment"]["event"].update(changes)
                extension_fixtures.retain_event(row)
                self.assert_blocked(record, "expected target exit")

    def test_metadata_changes_participate_in_both_input_and_output_comparison(self):
        for field in ("manifest_sha256", "native", "header", "installed_config"):
            with self.subTest(field=field):
                record = copy.deepcopy(self.right)
                metadata = record["target_exit_observer"]
                if field == "manifest_sha256":
                    metadata[field] = fixtures.digest("changed manifest")
                    rebind_record(record)
                else:
                    metadata[field]["sha256"] = fixtures.digest("changed " + field)
                self.assertEqual(compare._validate(record), [])
                self.assertNotEqual(compare._inputs(self.left), compare._inputs(record))
                self.assertNotEqual(compare._outputs(self.left), compare._outputs(record))
                self.assertEqual(self.result(right=record)["status"], "different")

    def test_source_changes_require_bound_rows_and_compare_as_different(self):
        for field in ("source_before", "source_after"):
            self.right[field]["revision"] = "9" * 40
            fixtures.refresh_source_digest(self.right[field])
        self.assert_blocked(self.right, "binding differs")
        rebind_record(self.right)
        self.assertEqual(compare._validate(self.right), [])
        self.assertEqual(self.result()["status"], "different")

    def test_observer_flags_are_bound_to_the_source_snapshot(self):
        path = "sims/common-sim-flags.mk"
        digest = fixtures.digest("contradictory source flags")
        for field in ("source_before", "source_after"):
            self.right[field]["source_inputs"][path] = digest
            fixtures.refresh_source_digest(self.right[field])
        for profile in (self.right["preflight"]["profile"], self.right["profile_after"]):
            if path in profile["source_inputs"]:
                profile["source_inputs"][path]["sha256"] = digest
        rebind_record(self.right)
        self.assertEqual(compare.observed_record.validate_extension(self.right), [])
        self.assert_blocked(self.right, "simulation flags are not bound")

    def test_observer_source_must_be_initialized_at_its_declared_pin(self):
        path = "toolchains/riscv-tools/riscv-isa-sim"
        for field in ("source_before", "source_after"):
            source = self.right[field]
            source_row = next(row for row in source["submodules"] if row["path"] == path)
            source_row.update(initialized=False, clean=None, revision=None, state="uninitialized")
            fixtures.refresh_source_digest(source)
        rebind_record(self.right)
        self.assert_blocked(self.right, "initialized pinned source")

    def test_retained_prerequisite_identities_must_match_observer_collateral(self):
        for name in ("fesvr_library", "fesvr_header"):
            for field, value in (("sha256", fixtures.digest("changed collateral")), ("bytes", 129)):
                with self.subTest(name=name, field=field):
                    record = copy.deepcopy(self.right)
                    for profile in (record["preflight"]["profile"], record["profile_after"]):
                        profile["collateral"][name][field] = value
                    self.assert_blocked(record, "retained prerequisite collateral")

    def test_absent_optional_profile_details_are_not_invented(self):
        for record in (self.left, self.right):
            for profile in (record["preflight"]["profile"], record["profile_after"]):
                profile.pop("collateral")
        self.assertEqual(self.result()["status"], "consistent")

    def test_fixed_observer_policy_cannot_change_even_with_matching_plan_hash(self):
        changes = {
            "schema_version": True, "kind": "other", "source_gitlink": "other/source",
            "source_commit": "0" * 40, "upstream_htif_sha256": "0" * 64,
            "output_directory": "nova-out/elsewhere", "manifest_path": "nova-out/elsewhere/manifest.json",
            "make_fragment": "software/nova/other.mk", "witness_max_bytes": 4096.0,
            "dedicated_witness_required": False, "signal_exit_accepted": True,
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                record = copy.deepcopy(self.right)
                record["declared_plan"]["target_exit_observer"][field] = value
                refresh_plan(record)
                self.assert_blocked(record, "fixed schema-2")
        for change in (lambda plan: plan.pop("target_exit_observer"),
                       lambda plan: plan["target_exit_observer"].update(extra=False),
                       lambda plan: plan.update(schema_version=1),
                       lambda plan: plan.update(source_must_be_clean=False)):
            record = copy.deepcopy(self.right)
            change(record["declared_plan"])
            refresh_plan(record)
            self.assert_blocked(record, "fixed schema-2")

    def test_fixed_observer_preparation_and_make_commands_are_required(self):
        changes = (
            lambda plan: plan["common_build_stages"].pop(0),
            lambda plan: plan["common_build_stages"][0].update(timeout_seconds=121),
            lambda plan: plan["common_build_stages"][0]["argv"].append("--unreviewed"),
            lambda plan: plan["profiles"][0]["build"]["argv"].__delitem__(slice(3, 7)),
            lambda plan: plan["profiles"][0]["build"]["argv"].append("SIM_LDFLAGS=-lfesvr"),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                record = copy.deepcopy(self.right)
                change(record["declared_plan"])
                refresh_plan(record)
                self.assert_blocked(record, "declared")

    def test_observed_preparation_remains_an_authoritative_normal_stage(self):
        for changes in ({"exit_code": 1, "status": "failed"}, {"timed_out": True},
                        {"timeout_seconds": 121}, {"max_log_bytes": 1},
                        {"command": ["python3", "-B", "wrong-generator.py"]}):
            with self.subTest(changes=changes):
                record = copy.deepcopy(self.right)
                record["common_stages"][0].update(changes)
                self.assert_blocked(record)
        record = copy.deepcopy(self.right)
        record["common_stages"].pop(0)
        self.assert_blocked(record, "common build stages")

    def test_manifest_path_must_match_fixed_preparation_output(self):
        metadata = self.right["target_exit_observer"]
        metadata["manifest_path"] = "nova-out/htif-observer/nested/manifest.json"
        metadata["generated"]["path"] = "nova-out/htif-observer/nested/htif.cc"
        self.assertEqual(compare.observed_record.validate_extension(self.right), [])
        self.assert_blocked(self.right, "manifest path")

    def test_supported_resource_and_checkout_relocation_keep_plan_semantics(self):
        left = synthetic_observed_record("single-job-left", jobs=1)
        right = synthetic_observed_record("single-job-right", jobs=1)
        self.assertEqual(self.result(left, right)["status"], "consistent")
        self.assertEqual(self.result(self.left, right)["status"], "different")

    def test_observer_preparation_diagnostics_remain_separate_from_identity_equality(self):
        self.right["common_stages"][0]["stdout_sha256"] = fixtures.digest("other preparation diagnostics")
        result = self.result()
        self.assertEqual(result["status"], "consistent")
        self.assertEqual(result["build_log_differences"], ["htif-observer-prepare"])

    def test_cli_reads_schema_two_records_without_qualifying_hardware(self):
        with tempfile.TemporaryDirectory(prefix="nova-observed-compare-") as directory:
            paths = [Path(directory) / name for name in ("left.json", "right.json")]
            for record, path in zip((self.left, self.right), paths):
                path.write_text(json.dumps(record))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = compare.main([str(path) for path in paths])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "consistent")
        self.assertIs(result["hardware_qualified"], False)


class ObservedCampaignIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = integration.CampaignIntegrationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.directory = self.fixture.directory
        self.record_paths = {}

    def produce_observed(self, label, *, witness_transform=None, **kwargs):
        """Reuse the real-producer fixture, adding actual synthetic witness files.

        Returned records and retained files are test doubles. The existing
        fixture refuses every process launch, including accidental future ones.
        Source/profile patches align repeated metadata before the runner binds
        it; no record is repaired after production or witness assessment.
        """
        campaign = integration.campaign
        execute = campaign.execute
        metadata = extension_fixtures.synthetic_metadata()

        def observed_execute(root, args, env=None):
            args.observe_target_exit = True
            capture_source, inspect_profile, run_command = (
                campaign.capture_source, campaign.inspect_profile, campaign.run_command)

            def source(*args, **kwargs):
                result = copy.deepcopy(capture_source(*args, **kwargs))
                bind_observer_source(result, metadata)
                return result

            def profile(*args, **kwargs):
                result = copy.deepcopy(inspect_profile(*args, **kwargs))
                bind_observer_profile(result, metadata)
                return result

            def run(cwd, output_dir, name, argv, timeout_seconds, **limits):
                result = run_command(cwd, output_dir, name, argv, timeout_seconds, **limits)
                stage_env = limits["env"]
                if "NOVA_HTIF_WITNESS_PATH" in stage_env:
                    expected = 7 if name.endswith("-nova-baseline-fail") else 0
                    event = {"schema_version": 1, "kind": "nova-htif-exit",
                             "run_id": stage_env["NOVA_HTIF_RUN_ID"],
                             "binding_sha256": stage_env["NOVA_HTIF_BINDING_SHA256"],
                             "target_exit_present": True, "raw_exit_code": (expected << 1) | 1,
                             "target_exit_code": expected, "signal_exit": False}
                    if witness_transform is not None:
                        event = witness_transform(event)
                    data = event if type(event) is bytes else extension_fixtures.canonical(event) + b"\n"
                    descriptor = os.open(stage_env["NOVA_HTIF_WITNESS_PATH"],
                                         os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(data)
                return result

            with patch.object(campaign, "capture_source", side_effect=source), \
                 patch.object(campaign, "inspect_profile", side_effect=profile), \
                 patch.object(campaign, "run_command", side_effect=run), \
                 patch.object(campaign, "build_observer_metadata", side_effect=lambda *a, **k: copy.deepcopy(metadata)):
                result, path = execute(root, args, env=env)
            self.record_paths[label] = path
            return result, path

        with patch.object(campaign, "execute", side_effect=observed_execute):
            return self.fixture.produce(label, **kwargs)

    def test_real_producer_and_readers_supply_complete_comparable_observer_records(self):
        left, left_calls = self.produce_observed("observed-left")
        right, right_calls = self.produce_observed("observed-right")
        for label, record, calls in (("observed-left", left, left_calls), ("observed-right", right, right_calls)):
            self.assertEqual(record["status"], "workloads_observed", record["reasons"])
            self.assertEqual(record["schema_version"], 2)
            self.assertEqual(len(calls), 38)
            self.assertEqual(compare._validate(record), [])
            self.assertEqual(compare.read_record(self.record_paths[label]), record)
            for row in rows(record):
                witness = row["target_exit"]["witness"]
                raw = (self.record_paths[label].parent / witness["path"]).read_bytes()
                self.assertEqual(len(raw), witness["size_bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), witness["sha256"])
                self.assertIs(row["assessment"]["target_completion_verified"], False)
                self.assertIs(row["target_exit"]["assessment"]["target_completion_verified"], True)
        result = compare.compare_records(left, right)
        self.assertEqual(result["status"], "consistent", result["reasons"])
        self.assertIs(result["hardware_qualified"], False)
        self.assertIs(result["g1_gate_passed"], False)
        self.assertIs(result["reference_comparison_qualified"], False)

    def test_actual_producer_protocol_failure_cannot_be_repaired_by_witness(self):
        left, _ = self.produce_observed("left")
        right, calls = self.produce_observed("wrong-negative", wrong_negative=True)
        self.assertEqual(right["status"], "failed")
        self.assertLess(len(calls), 38)
        self.assertIsNone(rows(right)[2]["target_exit"]["assessment"])
        self.assertEqual(compare.compare_records(left, right)["status"], "blocked")

    def test_actual_producer_signal_witness_blocks_after_successful_normal_protocol(self):
        left, _ = self.produce_observed("left")
        right, _ = self.produce_observed("signal", witness_transform=lambda event: {**event, "signal_exit": True})
        self.assertEqual(right["status"], "failed")
        self.assertIs(rows(right)[0]["assessment"]["expectation_met"], True)
        self.assertIs(rows(right)[0]["target_exit"]["assessment"]["target_completion_verified"], False)
        self.assertEqual(compare.compare_records(left, right)["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
