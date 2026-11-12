"""Bounded malformed-record corpus; all campaign observations are synthetic.

These tests inspect unauthenticated dictionaries only. They never execute a
compiler, simulator, target workload, or dependency installer.
"""

import copy
import importlib.util
from pathlib import Path
import unittest


FIXTURE_PATH = Path(__file__).with_name("test_compare_campaigns.py")
FIXTURE_SPEC = importlib.util.spec_from_file_location(
    "nova_record_contract_synthetic_fixture", FIXTURE_PATH)
fixtures = importlib.util.module_from_spec(FIXTURE_SPEC)
FIXTURE_SPEC.loader.exec_module(fixtures)
compare = fixtures.compare
HUGE_INTEGER = 10 ** 1000


def replace(record, path, value):
    parent = record
    for part in path[:-1]:
        parent = parent[part]
    parent[path[-1]] = copy.deepcopy(value)


class RecordContractRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.left_fixture = fixtures.synthetic_record("contract-synthetic-left")
        cls.right_fixture = fixtures.synthetic_record("contract-synthetic-right")

    def records(self):
        return copy.deepcopy(self.left_fixture), copy.deepcopy(self.right_fixture)

    def assertResult(self, left, right, expected="blocked"):
        result = compare.compare_records(left, right)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], expected, result["reasons"])
        self.assertIsInstance(result["reasons"], list)
        if expected == "blocked":
            self.assertTrue(result["reasons"])
        for field in ("hardware_qualified", "g1_gate_passed", "reference_comparison_qualified"):
            self.assertIs(result[field], False)
        self.assertEqual(result["reference_comparison"], "not_run")
        self.assertEqual(result["comparison_scope"], "recorded_input_and_artifact_identities_only")
        self.assertTrue(result["limitations"])

    def test_nested_container_shapes_return_structured_rejection(self):
        paths = (
            ("source_before", "submodules", 0),
            ("source_before", "source_inputs"),
            ("provenance_before", "tool_versions"),
            ("preflight", "profile"), ("preflight", "checker"),
            ("declared_plan", "profiles", 0),
            ("profiles", 0, "artifacts"),
            ("profiles", 0, "artifacts", "artifacts", 0),
            ("profiles", 0, "workloads", 0, "stage"),
            ("profiles", 0, "workloads", 0, "assessment"),
            ("profiles", 0, "workloads", 0, "binary_after"),
        )
        for path in paths:
            for value in (None, [], {}, True, 17, "wrong container"):
                with self.subTest(path=path, value=value):
                    left, right = self.records()
                    replace(right, path, value)
                    self.assertResult(left, right)

    def test_missing_nested_fields_return_structured_rejection(self):
        paths = (
            ("source_before", "clean"), ("source_before", "state_digest"),
            ("inventory", "matching_package_count"),
            ("execution_paths", "python"), ("preflight", "checker"),
            ("preflight", "profile", "known_prerequisites_present"),
            ("profiles", 0, "build", "timeout_seconds"),
            ("profiles", 0, "workloads", 0, "binary_after"),
            ("profiles", 0, "workloads", 0, "simulator_sha256_after"),
            ("profiles", 0, "workloads", 0, "stage", "command"),
            ("profiles", 0, "workloads", 0, "assessment", "completion_protocol_observed"),
        )
        for path in paths:
            with self.subTest(path=path):
                left, right = self.records()
                parent = right
                for part in path[:-1]:
                    parent = parent[part]
                del parent[path[-1]]
                self.assertResult(left, right)

    def test_bad_command_alias_types_and_values_are_blocked(self):
        values = (None, [], {}, True, 17, "relative", "/", "/tmp/../elsewhere",
                  "/tmp//checkout", "/tmp/check\x00out", "/tmp/check\nout", "<repo>")
        for alias in ("repository", "riscv_prefix", "python"):
            for value in values:
                with self.subTest(alias=alias, value=value):
                    left, right = self.records()
                    right["execution_paths"][alias] = copy.deepcopy(value)
                    self.assertResult(left, right)
        left, right = self.records()
        right["execution_paths"]["python"] = right["execution_paths"]["repository"]
        self.assertResult(left, right)

    def test_resource_bounds_reject_noncanonical_numbers(self):
        for field in ("jobs", "total_timeout_seconds", "max_log_bytes", "max_cycles", "seed"):
            for value in (None, True, "1", 1.0, -1, HUGE_INTEGER):
                with self.subTest(field=field, value_type=type(value).__name__):
                    left, right = self.records()
                    right["resource_limits"][field] = value
                    self.assertResult(left, right)

    def test_nested_nonfinite_numbers_fail_before_schema_comparison(self):
        for value in (float("nan"), float("inf"), -float("inf"), float("1e999")):
            for path in (("elapsed_seconds",),
                         ("profiles", 0, "workloads", 0, "stage", "elapsed_seconds")):
                with self.subTest(path=path, value=value):
                    left, right = self.records()
                    replace(right, path, value)
                    self.assertResult(left, right)

    def test_large_elapsed_integers_do_not_overflow_float_aggregation(self):
        paths = (("elapsed_seconds",), ("preflight", "checker", "elapsed_seconds"),
                 ("profiles", 0, "workloads", 0, "stage", "elapsed_seconds"))
        for path in paths:
            for value in (HUGE_INTEGER, -HUGE_INTEGER):
                with self.subTest(path=path, sign=1 if value > 0 else -1):
                    left, right = self.records()
                    replace(right, path, value)
                    self.assertResult(left, right)

    def test_well_formed_input_identity_difference_remains_unqualified(self):
        left, right = self.records()
        self.assertResult(left, right, "consistent")
        for field in ("source_before", "source_after"):
            right[field]["tree"] = "a" * 40
        self.assertResult(left, right, "different")

    def test_recorded_artifacts_cannot_exceed_capture_file_ceiling(self):
        for kind, size in (("rtl", 512 * 1024 * 1024 + 1),
                           ("metadata", 1024 * 1024 + 1),
                           ("device_tree", 1024 * 1024 + 1)):
            with self.subTest(kind=kind):
                left, right = self.records()
                for record in (left, right):
                    for artifact in record["profiles"][0]["artifacts"]["artifacts"]:
                        if artifact["kind"] == kind:
                            artifact["size_bytes"] = size
                self.assertResult(left, right)


if __name__ == "__main__":
    unittest.main()
