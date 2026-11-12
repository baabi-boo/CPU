"""Synthetic record-schema tests only; no simulator or hardware is executed."""

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


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nova_compare_campaigns_test", ROOT / "scripts/nova/compare_campaigns.py")
compare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compare)
PLAN_SPEC = importlib.util.spec_from_file_location(
    "nova_compare_campaign_plan_fixture", ROOT / "scripts/nova/campaign_plan.py")
planner = importlib.util.module_from_spec(PLAN_SPEC)
PLAN_SPEC.loader.exec_module(planner)
PLAN_CACHE = {}


def digest(label):
    return hashlib.sha256(("SYNTHETIC ONLY: " + label).encode()).hexdigest()


def synthetic_stage(name, negative=False):
    result = {
        "name": name, "status": "failed" if negative else "passed",
        "exit_code": -6 if negative else 0, "timed_out": False,
        "stdout": name + ".stdout.log", "stderr": name + ".stderr.log",
        "stdout_sha256": digest(name + " stdout"), "stderr_sha256": digest(name + " stderr"),
        "stdout_bytes": 100, "stderr_bytes": 100,
        "started_utc": "2026-11-12T00:00:01Z", "finished_utc": "2026-11-12T00:00:02Z",
        "elapsed_seconds": 1.0, "command": ["synthetic-not-executed", name],
        "timeout_seconds": 300, "max_log_bytes": 1024 * 1024, "min_free_gib": 10,
    }
    if negative:
        result["reason"] = "command exited unsuccessfully"
    return result


def synthetic_record(checkout, jobs=2):
    """Claims are deliberately invented fixtures, NEVER real campaign evidence."""
    source = {
        "revision": "1" * 40, "tree": "2" * 40, "clean": True,
        "checkout_identity_sha256": digest(checkout), "state_digest": digest("source state"),
        "lock_hashes": {name: digest(name) for name in sorted(compare.CONDA_INPUTS)},
        "source_inputs": {name: digest(name) for name in sorted(compare.SOURCE_INPUTS)},
        "submodules": [{"path": "synthetic-source/" + str(index), "pin": "3" * 40,
                        "revision": "3" * 40, "initialized": True, "clean": True,
                        "state": "at_pin"} for index in range(57)],
    }
    provenance = {
        "capture_complete": True, "toolchain_versions_verified": False,
        "host": {"os": "synthetic", "architecture": "synthetic"},
        "tool_versions": {name: "synthetic-version" for name in (
            "java", "verilator", "firtool", "make", "cmake", "riscv64-unknown-elf-gcc")},
        "lock_hashes": copy.deepcopy(source["lock_hashes"]),
        "submodules": [{"path": "synthetic", "pin": "3" * 40}],
    }
    profiles = []
    for config in compare.CONFIGURATIONS:
        simulator_digest = digest(config + " simulator")
        artifacts = [{"path": "synthetic/" + config + "/" + kind,
                      "kind": kind, "size_bytes": 100,
                      "sha256": simulator_digest if kind == "simulator" else digest(config + kind)}
                     for kind in ("simulator", "rtl", "device_tree", "metadata")]
        workloads = []
        for identifier in compare.WORKLOAD_IDS:
            negative = identifier == "nova-baseline-fail"
            stage = synthetic_stage(config + "-" + identifier, negative)
            assessment = {
                "status": "passed", "expectation_met": True,
                "completion_protocol_observed": not negative,
                "target_completion_verified": False,
                "expected_target_failure_verified": negative,
                "hardware_qualified": False, "g1_gate_passed": False,
                "reasons": [], "cycles": None if negative else 100,
                **{key: stage[key] for key in (
                    "stdout_sha256", "stderr_sha256", "stdout_bytes", "stderr_bytes")},
            }
            workloads.append({
                "id": identifier, "stage": stage, "assessment": assessment,
                "simulator_sha256": simulator_digest,
                "binary": {"path": "synthetic/" + identifier, "size_bytes": 100,
                           "sha256": digest(identifier), "kind": "riscv_elf"},
            })
        profiles.append({"configuration": config, "build": synthetic_stage(config + "-build"),
                         "artifacts": {"status": "captured", "artifacts": artifacts, "reasons": []},
                         "workloads": workloads})
    result = {
        "schema_version": 1, "kind": "nova-g1-campaign", "status": "workloads_observed",
        "source_before": copy.deepcopy(source), "source_after": copy.deepcopy(source),
        "provenance_before": copy.deepcopy(provenance), "provenance_after": copy.deepcopy(provenance),
        "plan_sha256": digest("plan"), "profile_sha256": digest("nova/g1-profile.json"),
        "workloads_sha256": digest("nova/g1-workloads.json"),
        "inventory": {"status": "matched", "lock_sha256": digest(
                          "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-64-lean.conda-lock.yml"),
                      "package_count": 165, "installed_package_count": 165,
                      "matching_package_count": 165, "metadata_only": True,
                      "installed_binary_contents_verified": False, "lock_origin_verified": False,
                      "blockers": [], "missing": [], "unexpected": [], "mismatched": []},
        "resource_limits": {"jobs": jobs, "java_heap": "4G", "total_timeout_seconds": 7200,
                            "min_free_gib": 10, "max_log_bytes": 1024 * 1024,
                            "max_cycles": 10000000, "seed": 1},
        "common_stages": [synthetic_stage(name) for name in compare.COMMON_STAGES],
        "profiles": profiles, "started_utc": "2026-11-12T00:00:00Z",
        "finished_utc": "2026-11-12T00:01:00Z", "hardware_qualified": False,
        "g1_gate_passed": False, "reference_comparison": "not_run",
        "limitations": ["Synthetic schema fixture; never executed and not hardware evidence."],
    }
    # Use the real read-only planner to catch cross-module contract drift, but
    # retain invented identities/logs and nonexistent synthetic execution paths.
    def normalized(value):
        if type(value) is str:
            return value.replace(str(ROOT), "<repo>")
        if type(value) is list:
            return [normalized(item) for item in value]
        if type(value) is dict:
            return {key: normalized(item) for key, item in value.items()}
        return value

    if jobs not in PLAN_CACHE:
        PLAN_CACHE[jobs] = planner.build_plan(ROOT, jobs=jobs)
    plan = normalized(PLAN_CACHE[jobs])
    paths = {"repository": "/synthetic-not-executed/" + checkout,
             "riscv_prefix": "/synthetic-not-executed/toolchain-" + checkout,
             "python": "/synthetic-not-executed/python-" + checkout}
    result.update(declared_plan=plan, execution_paths=paths, elapsed_seconds=60.0,
                  reasons=[], inventory_after=copy.deepcopy(result["inventory"]))
    result["plan_sha256"] = hashlib.sha256(json.dumps(
        plan, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    ready = {"profile": "g1-chisel6-rocket", "status": "ready",
             "known_prerequisites_present": True, "toolchain_version_inputs_verified": True,
             "hardware_qualified": False, "g1_gate_passed": False, "blockers": [],
             "collateral": {"synthetic": {"sha256": digest("synthetic collateral")}}}
    checker = synthetic_stage("pinned-input-check")
    checker.update(command=[paths["python"], "-B", "scripts/nova/check.py"], timeout_seconds=120)
    result.update(preflight={"profile": ready, "checker": checker}, profile_after=copy.deepcopy(ready))
    for stage, declared in zip(result["common_stages"], plan["common_build_stages"]):
        stage.update(command=[arg.replace("<repo>", paths["repository"]) for arg in declared["argv"]],
                     timeout_seconds=declared["timeout_seconds"])
    for profile, declared in zip(result["profiles"], plan["profiles"]):
        profile["build"].update(
            command=[arg.replace("<repo>", paths["repository"]) for arg in declared["build"]["argv"]],
            timeout_seconds=declared["build"]["timeout_seconds"])
        profile["artifacts"]["artifacts"][0]["path"] = (
            "sims/verilator/simulator-chipyard.harness-" + profile["configuration"])
        for workload, expected in zip(profile["workloads"], declared["workloads"]):
            workload["binary"]["path"] = expected["binary"]
            workload.update(binary_after=copy.deepcopy(workload["binary"]),
                            binary_origin=expected["binary_origin"],
                            simulator_sha256_after=workload["simulator_sha256"])
            base = paths["repository"] if expected["binary_origin"] == "repository" else paths["riscv_prefix"]
            workload["stage"]["command"] = planner.simulator_argv(
                Path(paths["repository"]), profile["configuration"], Path(base) / expected["binary"])
    return result


class CompareCampaignsTests(unittest.TestCase):
    def setUp(self):
        self.left = synthetic_record("synthetic-left")
        self.right = synthetic_record("synthetic-right")

    def result(self):
        result = compare.compare_records(self.left, self.right)
        for field in ("hardware_qualified", "g1_gate_passed", "reference_comparison_qualified"):
            self.assertIs(result[field], False)
        self.assertEqual(result["reference_comparison"], "not_run")
        return result

    def test_synthetic_identities_agree_without_awarding_qualification(self):
        result = self.result()
        self.assertEqual(result["status"], "consistent", result["reasons"])
        self.assertEqual(result["reasons"], [])
        self.assertIn("not actual reproduction", " ".join(result["limitations"]))
        self.assertIn("not authenticated", " ".join(result["limitations"]))
        self.assertIn("shared caches", " ".join(result["limitations"]))

    def test_comparison_does_not_mutate_input_records(self):
        original = copy.deepcopy((self.left, self.right))
        self.result()
        self.assertEqual((self.left, self.right), original)

    def test_identical_records_are_blocked(self):
        self.right = copy.deepcopy(self.left)
        self.assertEqual(self.result()["status"], "blocked")

    def test_checkout_reuse_is_blocked_despite_different_timestamp(self):
        self.right = copy.deepcopy(self.left)
        self.right["finished_utc"] = "2026-11-12T00:02:00Z"
        self.assertEqual(self.result()["status"], "blocked")

    def test_source_drift_during_capture_is_blocked(self):
        self.right["source_after"]["tree"] = "4" * 40
        self.assertEqual(self.result()["status"], "blocked")

    def test_environment_drift_during_capture_is_blocked(self):
        self.right["provenance_after"]["tool_versions"]["java"] = "changed"
        self.assertEqual(self.result()["status"], "blocked")

    def test_changed_input_identity_is_different(self):
        for snapshot in ("source_before", "source_after"):
            self.right[snapshot]["tree"] = "5" * 40
        self.assertEqual(self.result()["status"], "different")

    def test_changed_environment_identity_is_different(self):
        for key in ("provenance_before", "provenance_after"):
            self.right[key]["tool_versions"]["java"] = "another synthetic version"
        self.assertEqual(self.result()["status"], "different")

    def test_changed_resource_identity_is_different(self):
        self.right = synthetic_record("synthetic-right", jobs=1)
        self.assertEqual(self.result()["status"], "different")

    def test_changed_rtl_identity_requires_review(self):
        self.right["profiles"][0]["artifacts"]["artifacts"][1]["sha256"] = digest("changed RTL")
        result = self.result()
        self.assertEqual(result["status"], "different")
        self.assertIn("review required", " ".join(result["reasons"]))

    def test_build_log_variance_is_diagnostic_only(self):
        self.right["profiles"][0]["build"]["stdout_sha256"] = digest("different build log")
        result = self.result()
        self.assertEqual(result["status"], "consistent", result["reasons"])
        self.assertEqual(result["build_log_differences"], ["RocketConfig-build"])

    def test_workload_log_variance_is_different(self):
        workload = self.right["profiles"][0]["workloads"][0]
        for key in ("stage", "assessment"):
            workload[key]["stdout_sha256"] = digest("different workload log")
        self.assertEqual(self.result()["status"], "different")

    def test_incomplete_configuration_and_workload_sets_are_blocked(self):
        for category in ("profiles", "workloads", "common_stages"):
            with self.subTest(category=category):
                self.right = synthetic_record("synthetic-right")
                if category == "workloads":
                    self.right["profiles"][0]["workloads"].pop()
                else:
                    self.right[category].pop()
                self.assertEqual(self.result()["status"], "blocked")

    def test_missing_artifact_class_is_blocked(self):
        self.right["profiles"][0]["artifacts"]["artifacts"].pop()
        self.assertEqual(self.result()["status"], "blocked")

    def test_reordered_or_duplicate_workloads_are_blocked(self):
        workloads = self.right["profiles"][0]["workloads"]
        workloads[1] = copy.deepcopy(workloads[0])
        self.assertEqual(self.result()["status"], "blocked")

    def test_wrong_simulator_binding_is_blocked(self):
        self.right["profiles"][0]["workloads"][0]["simulator_sha256"] = digest("unrelated")
        self.assertEqual(self.result()["status"], "blocked")

    def test_wrong_assessment_log_binding_is_blocked(self):
        self.right["profiles"][0]["workloads"][0]["assessment"]["stdout_sha256"] = digest("unrelated")
        self.assertEqual(self.result()["status"], "blocked")

    def test_negative_expected_failure_accepts_actual_abort_not_zero(self):
        self.assertEqual(self.result()["status"], "consistent")
        stage = self.right["profiles"][0]["workloads"][2]["stage"]
        stage.update(exit_code=0, status="passed")
        self.assertEqual(self.result()["status"], "blocked")

    def test_negative_timeout_crash_and_launcher_exits_are_blocked(self):
        for code in (124, 125, 126, 127, 130, 137, 139, 143, -9, -11, -15, True):
            with self.subTest(code=code):
                self.right = synthetic_record("synthetic-right")
                self.right["profiles"][0]["workloads"][2]["stage"]["exit_code"] = code
                self.assertEqual(self.result()["status"], "blocked")

    def test_negative_infrastructure_reason_is_blocked(self):
        self.right["profiles"][0]["workloads"][2]["stage"]["reason"] = "output exceeded limit"
        self.assertEqual(self.result()["status"], "blocked")

    def test_positive_nonzero_exit_and_timeout_are_blocked(self):
        self.right["profiles"][0]["workloads"][0]["stage"]["exit_code"] = 1
        self.assertEqual(self.result()["status"], "blocked")
        self.right = synthetic_record("synthetic-right")
        self.right["profiles"][0]["workloads"][0]["stage"]["timed_out"] = True
        self.assertEqual(self.result()["status"], "blocked")

    def test_fake_qualification_and_target_attestation_are_blocked(self):
        for field in compare.CLAIM_FLAGS:
            with self.subTest(field=field):
                self.right = synthetic_record("synthetic-right")
                self.right["profiles"][0]["workloads"][0]["assessment"][field] = True
                self.assertEqual(self.result()["status"], "blocked")

    def test_noncanonical_integer_booleans_are_blocked(self):
        targets = [("schema_version",), ("resource_limits", "jobs"),
                   ("inventory", "package_count"), ("profiles", 0, "build", "exit_code"),
                   ("profiles", 0, "workloads", 0, "binary", "size_bytes")]
        for target in targets:
            with self.subTest(target=target):
                self.right = synthetic_record("synthetic-right")
                parent = self.right
                for part in target[:-1]:
                    parent = parent[part]
                parent[target[-1]] = True
                self.assertEqual(self.result()["status"], "blocked")

    def test_invalid_hash_and_unsafe_log_path_are_blocked(self):
        for field, value in (("stdout_sha256", "not-a-hash"), ("stdout", "../outside"),
                             ("stdout", "/absolute"), ("stdout", ".")):
            with self.subTest(field=field, value=value):
                self.right = synthetic_record("synthetic-right")
                self.right["common_stages"][0][field] = value
                self.assertEqual(self.result()["status"], "blocked")

    def test_same_log_path_reused_across_stages_is_blocked(self):
        self.right["common_stages"][1]["stdout"] = self.right["common_stages"][0]["stdout"]
        self.assertEqual(self.result()["status"], "blocked")

    def test_malformed_root_or_nonfinite_values_are_blocked(self):
        for value in (None, [], {}, {"x": float("nan")}, {"x": float("inf")}, {1: "invalid"}):
            with self.subTest(value=value):
                self.left = value
                self.assertEqual(self.result()["status"], "blocked")

    def test_cycles_and_nonjson_values_are_blocked(self):
        self.left["cycle"] = self.left
        self.assertEqual(self.result()["status"], "blocked")

    def test_source_hash_inventory_membership_is_strict(self):
        for field in ("lock_hashes", "source_inputs"):
            with self.subTest(field=field):
                self.right = synthetic_record("synthetic-right")
                for snapshot in ("source_before", "source_after"):
                    mapping = self.right[snapshot][field]
                    mapping["synthetic/unexpected"] = mapping.pop(next(iter(mapping)))
                self.assertEqual(self.result()["status"], "blocked")

    def test_empty_log_hash_must_be_the_hash_of_empty_bytes(self):
        stage = self.right["common_stages"][0]
        stage["stdout_bytes"] = 0
        self.assertEqual(self.result()["status"], "blocked")
        stage["stdout_sha256"] = hashlib.sha256(b"").hexdigest()
        self.assertEqual(self.result()["status"], "consistent")

    def test_cycle_claim_above_recorded_limit_is_blocked(self):
        self.right["resource_limits"]["max_cycles"] = 10
        self.assertEqual(self.result()["status"], "blocked")

    def test_required_root_fields_reject_noncanonical_containers(self):
        for field in compare.REQUIRED_FIELDS:
            for value in (None, [], {}, True, 17):
                with self.subTest(field=field, value=value):
                    self.right = synthetic_record("synthetic-right")
                    if type(value) is type(self.right[field]) and value == self.right[field]:
                        continue
                    self.right[field] = value
                    self.assertEqual(self.result()["status"], "blocked")

    def test_manifest_and_inventory_hashes_are_bound_to_source(self):
        for field in ("profile_sha256", "workloads_sha256", "inventory"):
            with self.subTest(field=field):
                self.right = synthetic_record("synthetic-right")
                if field == "inventory":
                    self.right[field]["lock_sha256"] = digest("unbound")
                else:
                    self.right[field] = digest("unbound")
                self.assertEqual(self.result()["status"], "blocked")

    def test_retained_log_size_above_recorded_limit_is_blocked(self):
        self.right["common_stages"][0]["stdout_bytes"] = 2 * 1024 * 1024
        self.assertEqual(self.result()["status"], "blocked")

    def test_post_execution_binary_and_simulator_fields_are_required_and_equal(self):
        for profile_index in (0, 1):
            for field in ("binary_after", "simulator_sha256_after"):
                for missing in (False, True):
                    with self.subTest(profile=profile_index, field=field, missing=missing):
                        self.right = synthetic_record("synthetic-right")
                        workload = self.right["profiles"][profile_index]["workloads"][0]
                        if missing:
                            del workload[field]
                        elif field == "binary_after":
                            workload[field]["sha256"] = digest("changed after execution")
                        else:
                            workload[field] = digest("changed after execution")
                        self.assertEqual(self.result()["status"], "blocked")

    def test_raw_commands_bind_simulator_binary_seed_and_cycle_arguments(self):
        replacements = {0: "/different/simulator", 3: "+dramsim_ini_dir=/different/input",
                        4: "+max-cycles=9", 6: "+verilator+seed+9", 8: "/different/binary"}
        for profile_index in (0, 1):
            for position, replacement in replacements.items():
                with self.subTest(profile=profile_index, position=position):
                    self.right = synthetic_record("synthetic-right")
                    self.right["profiles"][profile_index]["workloads"][0]["stage"]["command"][position] = replacement
                    self.assertEqual(self.result()["status"], "blocked")

    def test_common_checker_and_configuration_commands_are_bound(self):
        for scope in ("common", "checker", "build"):
            with self.subTest(scope=scope):
                self.right = synthetic_record("synthetic-right")
                if scope == "common":
                    stage = self.right["common_stages"][0]
                    stage["command"][1] = "--different-configure"
                elif scope == "checker":
                    self.right["preflight"]["checker"]["command"][-1] = "unreviewed-check.py"
                else:
                    self.right["profiles"][0]["build"]["command"][3] = "CONFIG=OtherConfig"
                self.assertEqual(self.result()["status"], "blocked")

    def test_declared_plan_must_match_hash_and_fixed_command_contract(self):
        self.right["plan_sha256"] = digest("not the retained plan")
        self.assertEqual(self.result()["status"], "blocked")
        self.right = synthetic_record("synthetic-right")
        self.right["declared_plan"]["common_build_stages"][0]["argv"][0] = "other-builder"
        self.right["plan_sha256"] = hashlib.sha256(compare._canonical(self.right["declared_plan"])).hexdigest()
        self.assertEqual(self.result()["status"], "blocked")

    def test_execution_aliases_are_canonical_and_prefix_boundaries_are_exact(self):
        for value in ("relative", "/", "/synthetic/../outside", "/synthetic//path", "/synthetic/path/", "<repo>"):
            with self.subTest(value=value):
                self.right = synthetic_record("synthetic-right")
                self.right["execution_paths"]["repository"] = value
                self.assertEqual(self.result()["status"], "blocked")
        self.right = synthetic_record("synthetic-right")
        command = self.right["profiles"][0]["workloads"][0]["stage"]["command"]
        command[0] = command[0].replace(self.right["execution_paths"]["repository"],
                                        self.right["execution_paths"]["repository"] + "-different")
        self.assertEqual(self.result()["status"], "blocked")

    def test_raw_placeholder_commands_are_not_treated_as_executed_paths(self):
        self.right["profiles"][0]["workloads"][0]["stage"]["command"][0] = (
            "<repo>/sims/verilator/simulator-chipyard.harness-RocketConfig")
        self.assertEqual(self.result()["status"], "blocked")

    def test_alias_relocation_does_not_create_an_identity_difference(self):
        self.assertNotEqual(self.left["execution_paths"], self.right["execution_paths"])
        self.assertNotEqual(self.left["profiles"][0]["workloads"][3]["stage"]["command"],
                            self.right["profiles"][0]["workloads"][3]["stage"]["command"])
        self.assertEqual(self.result()["status"], "consistent")

    def test_success_cannot_retain_campaign_failure_reasons(self):
        for value in (None, ["source changed during execution"], ""):
            with self.subTest(value=value):
                self.right["reasons"] = value
                self.assertEqual(self.result()["status"], "blocked")

    def test_success_requires_passing_preflight_and_matching_post_checks(self):
        for field in ("inventory_after", "profile_after", "preflight"):
            with self.subTest(field=field):
                self.right = synthetic_record("synthetic-right")
                self.right[field] = None
                self.assertEqual(self.result()["status"], "blocked")
        self.right = synthetic_record("synthetic-right")
        self.right["profile_after"]["collateral"]["synthetic"]["sha256"] = digest("changed library")
        self.assertEqual(self.result()["status"], "blocked")
        self.right = synthetic_record("synthetic-right")
        self.right["inventory_after"]["matching_package_count"] = 164
        self.assertEqual(self.result()["status"], "blocked")
        self.right = synthetic_record("synthetic-right")
        self.right["preflight"]["checker"]["exit_code"] = 1
        self.assertEqual(self.result()["status"], "blocked")

    def test_aggregate_monotonic_budget_is_required_and_enforced(self):
        for elapsed in (None, True, 0, -1, 7200.001, "60"):
            with self.subTest(elapsed=elapsed):
                self.right = synthetic_record("synthetic-right")
                self.right["elapsed_seconds"] = elapsed
                self.assertEqual(self.result()["status"], "blocked")
        self.right = synthetic_record("synthetic-right")
        self.right["elapsed_seconds"] = 2
        self.assertEqual(self.result()["status"], "blocked")

    def test_utc_span_is_not_used_as_monotonic_elapsed_proof(self):
        self.right["finished_utc"] = "2026-11-14T00:00:00Z"
        self.assertEqual(self.result()["status"], "consistent")

    def test_stage_timeout_metadata_must_match_declared_budget(self):
        for timeout in (None, True, 0, 301, 7201, 300.0):
            with self.subTest(timeout=timeout):
                self.right = synthetic_record("synthetic-right")
                self.right["profiles"][0]["workloads"][0]["stage"]["timeout_seconds"] = timeout
                self.assertEqual(self.result()["status"], "blocked")
        self.right = synthetic_record("synthetic-right")
        self.right["common_stages"][0]["min_free_gib"] = 1
        self.assertEqual(self.result()["status"], "blocked")

    def test_interruption_cannot_be_overridden_by_a_successful_status(self):
        for field, value in (("interrupted", True), ("interruption_signal", 15)):
            with self.subTest(field=field):
                self.right = synthetic_record("synthetic-right")
                self.right["profiles"][0]["workloads"][0]["stage"][field] = value
                self.assertEqual(self.result()["status"], "blocked")

    def test_recorded_binary_origin_and_path_must_match_declared_workload(self):
        for field, value in (("binary_origin", "riscv_prefix"), ("path", "another/binary.riscv")):
            with self.subTest(field=field):
                self.right = synthetic_record("synthetic-right")
                row = self.right["profiles"][0]["workloads"][0]
                if field == "path":
                    row["binary"][field] = value
                    row["binary_after"][field] = value
                else:
                    row[field] = value
                self.assertEqual(self.result()["status"], "blocked")
    def test_nonjson_nested_tuple_is_blocked(self):
        self.left["unsupported"] = ("tuple",)
        self.assertEqual(self.result()["status"], "blocked")


class CompareRecordReaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nova-compare-synthetic-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def write_record(self, name, record):
        path = self.directory / name
        path.write_text(json.dumps(record), encoding="utf-8")
        return path

    def test_cli_consistent_different_and_blocked_codes(self):
        left = self.write_record("left.json", synthetic_record("left"))
        right_record = synthetic_record("right")
        right = self.write_record("right.json", right_record)
        for expected, mode in ((0, "consistent"), (1, "different"), (2, "blocked")):
            with self.subTest(mode=mode):
                if mode == "different":
                    for snapshot in ("source_before", "source_after"):
                        right_record[snapshot]["tree"] = "5" * 40
                elif mode == "blocked":
                    right_record["schema_version"] = True
                self.write_record("right.json", right_record)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = compare.main([str(left), str(right)])
                self.assertEqual(code, expected)
                self.assertEqual(json.loads(output.getvalue())["status"], mode)

    def test_duplicate_json_keys_and_nonfinite_numbers_are_rejected(self):
        path = self.directory / "invalid.json"
        for content in ('{"x": 1, "x": 2}', '{"x": NaN}', '{"x": Infinity}',
                        '{"x": -Infinity}', '{"x": 1e999}', '{"x": '):
            with self.subTest(content=content):
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(compare.RecordError):
                    compare.read_record(path)

    def test_symlink_leaf_and_parent_are_rejected(self):
        path = self.write_record("record.json", {})
        link = self.directory / "link.json"
        link.symlink_to(path)
        with self.assertRaises(compare.RecordError):
            compare.read_record(link)
        linkdir = self.directory / "linkdir"
        linkdir.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(compare.RecordError):
            compare.read_record(linkdir / "record.json")

    def test_fifo_and_directory_are_rejected_without_blocking(self):
        fifo = self.directory / "pipe"
        os.mkfifo(fifo)
        for path in (fifo, self.directory):
            with self.subTest(path=path):
                with self.assertRaises(compare.RecordError):
                    compare.read_record(path)

    def test_size_limit_and_invalid_utf8_are_rejected(self):
        path = self.directory / "oversized.json"
        with path.open("wb") as stream:
            stream.truncate(compare.MAX_RECORD_BYTES + 1)
        with self.assertRaises(compare.RecordError):
            compare.read_record(path)
        path.write_bytes(b"\xff")
        with self.assertRaises(compare.RecordError):
            compare.read_record(path)

    def test_read_failure_has_false_qualification_flags(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = compare.main([str(self.directory / "absent"), str(self.directory / "absent2")])
        self.assertEqual(code, 2)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "blocked")
        self.assertIs(result["hardware_qualified"], False)
        self.assertIs(result["g1_gate_passed"], False)


if __name__ == "__main__":
    unittest.main()
