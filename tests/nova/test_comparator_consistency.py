"""Legacy metadata contradictions only; every campaign fixture is synthetic.

Paired mutations deliberately keep the two records in agreement. A comparator
must reject an impossible record even when its counterpart repeats the claim.
No compiler, simulator, CPU workload, or dependency installer is executed.
"""

import copy
import hashlib
import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    "nova_comparator_consistency_fixtures", Path(__file__).with_name("test_compare_campaigns.py"))
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)
compare = fixtures.compare


def replace(value, path, replacement):
    for part in path[:-1]:
        value = value[part]
    value[path[-1]] = copy.deepcopy(replacement)


class ComparatorConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.templates = (fixtures.synthetic_record("consistency-synthetic-left"),
                         fixtures.synthetic_record("consistency-synthetic-right"))

    def records(self):
        return copy.deepcopy(self.templates)

    def assert_pair(self, records, expected="blocked"):
        result = compare.compare_records(*records)
        self.assertEqual(result["status"], expected, result["reasons"])
        for field in ("hardware_qualified", "g1_gate_passed", "reference_comparison_qualified"):
            self.assertIs(result[field], False)
        self.assertEqual(result["reference_comparison"], "not_run")
        self.assertEqual(result["comparison_scope"], "recorded_input_and_artifact_identities_only")
        return result

    def mutate_plan(self, path, value):
        records = self.records()
        for record in records:
            replace(record["declared_plan"], path, value)
            record["plan_sha256"] = hashlib.sha256(compare._canonical(record["declared_plan"])).hexdigest()
        self.assert_pair(records)

    def mutate_profile(self, path, value):
        records = self.records()
        for record in records:
            for profile in (record["preflight"]["profile"], record["profile_after"]):
                replace(profile, path, value)
        self.assert_pair(records)

    def test_rehashed_plan_cannot_weaken_fixed_policies(self):
        cases = (
            (("reproduction", "required_clean_builds"), 1),
            (("reproduction", "shared_generated_artifacts_allowed"), True),
            (("reproduction", "automatic_gate_acceptance"), True),
            (("execute_requires_approved_budget",), False),
            (("source_must_be_clean",), False),
            (("does_not_provision_toolchain_or_initialize_submodules",), False),
            (("build_dependency_resolution",), "offline-guaranteed"),
            (("missing_workload_policy",), "skip-unavailable"),
            (("scope",), "hardware-qualified"),
            (("reference", "comparison_scope"), "fully_qualified"),
            (("reference", "model"), "unreviewed-reference"),
            (("reference", "source_gitlink"), "unrelated/reference"),
            (("exclusions",), []),
            (("notes",), []),
        )
        for path, value in cases:
            with self.subTest(path=path):
                self.mutate_plan(path, value)

    def test_rehashed_plan_requires_exact_semantic_field_sets(self):
        for path in ((), ("reference",), ("reproduction",), ("source_provenance",),
                     ("profiles", 0), ("profiles", 0, "simulation_limits"),
                     ("profiles", 0, "workloads", 0), ("common_build_stages", 0)):
            for operation in ("remove", "add"):
                with self.subTest(path=path, operation=operation):
                    records = self.records()
                    for record in records:
                        parent = record["declared_plan"]
                        for key in path:
                            parent = parent[key]
                        if operation == "remove":
                            del parent[next(iter(parent))]
                        else:
                            parent["unsupported_synthetic_policy"] = False
                        record["plan_sha256"] = hashlib.sha256(
                            compare._canonical(record["declared_plan"])).hexdigest()
                    self.assert_pair(records)

    def test_rehashed_plan_rejects_bool_integer_and_float_aliases(self):
        cases = (
            (("schema_version",), True), (("schema_version",), 1.0),
            (("execute_requires_approved_budget",), 1),
            (("source_must_be_clean",), 1.0),
            (("hardware_qualified",), 0), (("g1_gate_passed",), 0.0),
            (("reference", "qualified"), 0),
            (("reproduction", "required_clean_builds"), 2.0),
            (("reproduction", "shared_generated_artifacts_allowed"), 0),
            (("reproduction", "automatic_gate_acceptance"), 0.0),
            (("common_build_stages", 0, "timeout_seconds"), 600.0),
            (("profiles", 0, "build", "timeout_seconds"), 7200.0),
            (("profiles", 0, "simulation_limits", "seed"), True),
            (("profiles", 0, "simulation_limits", "seed"), 1.0),
            (("profiles", 0, "simulation_limits", "max_cycles"), 10000000.0),
            (("profiles", 0, "simulation_limits", "timeout_seconds"), 300.0),
            (("profiles", 0, "workloads", 0, "expected_target_exit"), False),
            (("profiles", 0, "workloads", 1, "expected_target_exit"), 0.0),
            (("profiles", 0, "workloads", 2, "expected_target_exit"), 7.0),
        )
        for path, value in cases:
            with self.subTest(path=path, value=value):
                self.mutate_plan(path, value)

    def test_plan_source_provenance_is_fixed_and_bound_to_snapshot(self):
        self.mutate_plan(("source_provenance", "chipyard_commit"), "a" * 40)
        path = "generators/rocket-chip"
        self.mutate_plan(("source_provenance", "gitlinks", path), "a" * 40)
        records = self.records()
        for record in records:
            for source in (record["source_before"], record["source_after"]):
                row = next(row for row in source["submodules"] if row["path"] == path)
                row.update(pin="a" * 40, revision="a" * 40)
                fixtures.refresh_source_digest(source)
            for profile in (record["preflight"]["profile"], record["profile_after"]):
                next(row for row in profile["source_gitlinks"] if row["path"] == path)["pin"] = "a" * 40
        self.assert_pair(records)

    def test_coherent_commands_cannot_change_the_fixed_plan_seed_or_cycle_limit(self):
        for field, value, argument, prefix in (("max_cycles", 1000, 4, "+max-cycles="),
                                                ("seed", 2, 6, "+verilator+seed+")):
            with self.subTest(field=field):
                records = self.records()
                for record in records:
                    record["resource_limits"][field] = value
                    for declared in record["declared_plan"]["profiles"]:
                        declared["simulation_limits"][field] = value
                    record["plan_sha256"] = hashlib.sha256(
                        compare._canonical(record["declared_plan"])).hexdigest()
                    for profile in record["profiles"]:
                        for row in profile["workloads"]:
                            row["stage"]["command"][argument] = prefix + str(value)
                self.assert_pair(records)

    def test_each_marker_workload_requires_enough_stdout_for_its_exact_line(self):
        markers = ("Hello world from core 0, a rocket", "NOVA_BASELINE_V1 PASS hart=0 checks=8",
                   "NOVA_BASELINE_V1 EXPECTED_FAIL hart=0 code=7")
        for index, marker in enumerate(markers):
            for size in (0, len(marker.encode())):
                with self.subTest(workload=index, size=size):
                    records = self.records()
                    for record in records:
                        for profile in record["profiles"]:
                            row = profile["workloads"][index]
                            for destination in (row["stage"], row["assessment"]):
                                destination["stdout_bytes"] = size
                                destination["stdout_sha256"] = (hashlib.sha256(b"").hexdigest()
                                    if size == 0 else fixtures.digest("invented short marker log"))
                    self.assert_pair(records)

    def test_marker_byte_bound_does_not_claim_to_authenticate_marker_contents(self):
        records = self.records()
        for record in records:
            for profile in record["profiles"]:
                for row in profile["workloads"][:3]:
                    marker = ("Hello world from core 0, a rocket" if row["id"] == "hello"
                              else compare._workload(row["id"])["expected_marker"])
                    for destination in (row["stage"], row["assessment"]):
                        destination["stdout_bytes"] = len(marker.encode()) + 1
                        destination["stdout_sha256"] = fixtures.digest("not authenticated by JSON comparison")
        result = self.assert_pair(records, "consistent")
        self.assertIn("not authenticated", " ".join(result["limitations"]))

    def test_isa_workload_may_have_empty_stdout(self):
        records = self.records()
        for record in records:
            for profile in record["profiles"]:
                for destination in (profile["workloads"][3]["stage"], profile["workloads"][3]["assessment"]):
                    destination.update(stdout_bytes=0, stdout_sha256=hashlib.sha256(b"").hexdigest())
        self.assert_pair(records, "consistent")

    def test_generated_artifacts_require_exact_configuration_prefix_and_suffix(self):
        for artifact_index, suffix in ((1, ".sv"), (2, ".dts"), (3, ".json")):
            for path in ("unrelated/SYNTHETIC" + suffix,
                         "sims/verilator/generated-src/chipyard.harness.TestHarness.NovaM1BaselineConfig/SYNTHETIC" + suffix,
                         "sims/verilator/generated-src/chipyard.harness.TestHarness.RocketConfig-extra/SYNTHETIC" + suffix,
                         "sims/verilator/generated-src/chipyard.harness.TestHarness.RocketConfig/",
                         "sims/verilator/generated-src/chipyard.harness.TestHarness.RocketConfig/SYNTHETIC.wrong"):
                with self.subTest(artifact=artifact_index, path=path):
                    records = self.records()
                    for record in records:
                        record["profiles"][0]["artifacts"]["artifacts"][artifact_index]["path"] = path
                    self.assert_pair(records)

    def test_kind_cannot_be_swapped_between_valid_suffixes(self):
        records = self.records()
        for record in records:
            artifacts = record["profiles"][0]["artifacts"]["artifacts"]
            artifacts[2]["kind"], artifacts[3]["kind"] = artifacts[3]["kind"], artifacts[2]["kind"]
        self.assert_pair(records)

    def test_nested_generated_collateral_and_both_rtl_suffixes_remain_valid(self):
        for suffix in (".v", ".sv"):
            with self.subTest(suffix=suffix):
                records = self.records()
                for record in records:
                    artifact = record["profiles"][0]["artifacts"]["artifacts"][1]
                    prefix = str(Path(artifact["path"]).parent)
                    artifact["path"] = prefix + "/nested/SYNTHETIC-UNEXECUTED" + suffix
                self.assert_pair(records, "consistent")

    def test_both_elf_kinds_reject_impossible_sizes(self):
        for size in (1, 64, 119):
            for kind in ("simulator", "riscv_elf"):
                with self.subTest(size=size, kind=kind):
                    records = self.records()
                    for record in records:
                        for profile in record["profiles"]:
                            if kind == "simulator":
                                profile["artifacts"]["artifacts"][0]["size_bytes"] = size
                            else:
                                for row in profile["workloads"]:
                                    row["binary"]["size_bytes"] = row["binary_after"]["size_bytes"] = size
                    self.assert_pair(records)

    def test_elf_size_minimum_does_not_attest_elf_contents(self):
        records = self.records()
        for record in records:
            for profile in record["profiles"]:
                profile["artifacts"]["artifacts"][0]["size_bytes"] = 120
                for row in profile["workloads"]:
                    row["binary"]["size_bytes"] = row["binary_after"]["size_bytes"] = 120
        self.assert_pair(records, "consistent")

    def test_source_state_digest_rejects_unbound_or_stale_metadata(self):
        for field, value in (("state_digest", "0" * 64), ("tree", "a" * 40),
                             ("revision", "b" * 40)):
            with self.subTest(field=field):
                records = self.records()
                for record in records:
                    for source in (record["source_before"], record["source_after"]):
                        source[field] = value
                self.assert_pair(records)

    def test_source_digest_binding_rejects_unsupported_snapshot_and_gitlink_fields(self):
        for scope in ("source", "gitlink"):
            with self.subTest(scope=scope):
                records = self.records()
                for record in records:
                    for source in (record["source_before"], record["source_after"]):
                        target = source if scope == "source" else source["submodules"][0]
                        target["unsupported_state"] = "synthetic"
                        fixtures.refresh_source_digest(source)
                self.assert_pair(records)

    def test_coherent_source_revision_difference_is_reviewable(self):
        left, right = self.records()
        for source in (right["source_before"], right["source_after"]):
            source["revision"] = "a" * 40
            source["tree"] = "b" * 40
            fixtures.refresh_source_digest(source)
        self.assert_pair((left, right), "different")

    def test_inspector_qualification_flags_cannot_be_promoted_or_numeric(self):
        for value in (True, 1, 0, 0.0):
            with self.subTest(field="dependency_closure_qualified", value=value):
                self.mutate_profile(("dependency_closure_qualified",), value)
            with self.subTest(field="identity_verified", value=value):
                self.mutate_profile(("tools", 0, "identity_verified"), value)

    def test_ready_profile_rejects_tool_and_source_detail_contradictions(self):
        source_path = next(iter(fixtures.PROFILE_DECLARATION["source_inputs_sha256"]))
        cases = (
            (("schema_version",), True), (("schema_version",), 1.0),
            (("host", "system"), "unsupported"),
            (("initialized_optional_generators",), ["gemmini"]),
            (("nested_dependency_closure",), "qualified"),
            (("maven_artifact_closure",), "qualified"),
            (("tools", 0, "available"), False), (("tools", 0, "available"), 1),
            (("tools", 1, "version_matches"), False), (("tools", 1, "version_matches"), 1),
            (("tools", 1, "observed_version"), "9.999"),
            (("tools", 1, "expected_version"), "9.999"),
            (("source_inputs", source_path, "matches_profile"), False),
            (("source_inputs", source_path, "matches_profile"), 1),
            (("source_inputs", source_path, "sha256"), fixtures.digest("unbound input")),
            (("source_gitlinks", 0, "state"), "uninitialized"),
            (("source_gitlinks", 0, "pin"), "a" * 40),
            (("provisioning_sources", 0, "state"), "dirty"),
        )
        for path, value in cases:
            with self.subTest(path=path, value=value):
                self.mutate_profile(path, value)

    def test_ready_profile_rejects_collateral_detail_contradictions(self):
        cases = (
            (("collateral", "fesvr_library", "available"), False),
            (("collateral", "fesvr_library", "path"), "../outside"),
            (("collateral", "fesvr_library", "bytes"), 0),
            (("collateral", "fesvr_library", "bytes"), True),
            (("collateral", "fesvr_library", "bytes"), 256.0),
            (("collateral", "fesvr_library", "bytes"), 256 * 1024 * 1024 + 1),
            (("collateral", "fesvr_library", "sha256"), "not-a-hash"),
            (("collateral", "htif_installed_linker", "matches_pinned"), False),
            (("collateral", "htif_installed_linker", "matches_pinned"), 1),
            (("collateral", "htif_installed_linker", "sha256"), fixtures.digest("different linker")),
        )
        for path, value in cases:
            with self.subTest(path=path, value=value):
                self.mutate_profile(path, value)

    def test_present_profile_detail_containers_fail_closed(self):
        for field in ("tools", "source_inputs", "source_gitlinks", "provisioning_sources", "collateral"):
            for value in (None, True, 42, "malformed"):
                with self.subTest(field=field, value=value):
                    self.mutate_profile((field,), value)

    def test_legacy_summary_does_not_invent_missing_detailed_observations(self):
        records = self.records()
        keep = {"profile", "status", "known_prerequisites_present", "toolchain_version_inputs_verified",
                "hardware_qualified", "g1_gate_passed", "blockers"}
        for record in records:
            summary = {key: value for key, value in record["preflight"]["profile"].items() if key in keep}
            record["preflight"]["profile"] = summary
            record["profile_after"] = copy.deepcopy(summary)
        self.assert_pair(records, "consistent")

    def test_postcheck_numeric_boolean_alias_does_not_hide_drift(self):
        records = self.records()
        for record in records:
            record["inventory_after"]["metadata_only"] = 1
        self.assert_pair(records)

    def test_metadata_identity_comparison_is_type_preserving(self):
        left, right = self.records()
        for record, value in ((left, False), (right, 0)):
            for profile in (record["preflight"]["profile"], record["profile_after"]):
                profile["synthetic_diagnostic"] = value
        self.assert_pair((left, right), "different")


if __name__ == "__main__":
    unittest.main()
