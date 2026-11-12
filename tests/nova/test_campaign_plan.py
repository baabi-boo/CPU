"""Offline tests of campaign declarations; no simulator is built or executed."""

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nova_campaign_plan", ROOT / "scripts/nova/campaign_plan.py")
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


class CampaignPlanTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "nova").mkdir()
        self.path = self.root / "nova/g1-workloads.json"
        self.manifest = json.loads((ROOT / "nova/g1-workloads.json").read_text())
        self.lock = json.loads((ROOT / "nova/upstream-lock.json").read_text())
        self.write_manifest()
        self.write_lock()

    def write_manifest(self, value=None):
        self.path.write_text(json.dumps(self.manifest if value is None else value), encoding="utf-8")

    def write_lock(self):
        (self.root / "nova/upstream-lock.json").write_text(json.dumps(self.lock), encoding="utf-8")

    def test_declared_workloads_are_exact_and_narrow(self):
        data = planner.load_workloads(self.path)
        self.assertEqual(data["isa_tests"], list(planner.ISA_TESTS))
        self.assertEqual(len(data["isa_tests"]), 12)
        self.assertEqual(len(set(data["isa_tests"])), 12)
        self.assertFalse(data["full_isa_certification"])
        self.assertEqual(data["reference"]["comparison_scope"], "unresolved")
        self.assertFalse(data["reference"]["qualified"])
        self.assertIn("MMU", data["exclusions"])
        self.assertEqual(data["missing_workload_policy"], "block-no-skips")

    def test_two_profiles_build_separately_with_same_fixed_workloads(self):
        plan = planner.build_plan(self.root)
        self.assertEqual([item["configuration"] for item in plan["profiles"]], list(planner.CONFIGURATIONS))
        first, second = plan["profiles"]
        self.assertIn("CONFIG=RocketConfig", first["build"]["argv"])
        self.assertIn("CONFIG=NovaM1BaselineConfig", second["build"]["argv"])
        self.assertEqual(first["workloads"], second["workloads"])
        self.assertEqual(len(first["workloads"]), 15)
        first["workloads"][0]["id"] = "changed"
        self.assertEqual(second["workloads"][0]["id"], "hello")

    def test_plan_is_deterministic_and_does_not_write_or_execute(self):
        before = sorted((str(path.relative_to(self.root)), path.read_bytes())
                        for path in self.root.rglob("*") if path.is_file())
        with patch("subprocess.run", side_effect=AssertionError("executed command")), \
             patch("subprocess.Popen", side_effect=AssertionError("started command")):
            first = planner.build_plan(self.root)
            second = planner.build_plan(self.root)
        after = sorted((str(path.relative_to(self.root)), path.read_bytes())
                       for path in self.root.rglob("*") if path.is_file())
        self.assertEqual(first, second)
        self.assertEqual(before, after)
        self.assertFalse(first["hardware_qualified"])
        self.assertFalse(first["g1_gate_passed"])
        self.assertTrue(first["execute_requires_approved_budget"])

    def test_plan_keeps_isa_paths_unresolved_and_requires_two_clean_builds(self):
        with patch.dict(os.environ, {"RISCV": "/private/not-used"}):
            plan = planner.build_plan(self.root)
        for row in plan["profiles"][0]["workloads"][3:]:
            self.assertEqual(row["binary_origin"], "riscv_prefix")
            self.assertTrue(row["binary"].startswith(planner.ISA_BINARY_DIRECTORY + "/"))
            self.assertNotIn("*", row["binary"])
            self.assertEqual(row["expected_target_exit"], 0)
        self.assertNotIn("/private/not-used", json.dumps(plan))
        self.assertEqual(plan["reproduction"]["required_clean_builds"], 2)
        self.assertFalse(plan["reproduction"]["automatic_gate_acceptance"])

    def test_cross_compiler_is_selected_before_hello_cmake_project(self):
        plan = planner.build_plan(self.root, jobs=1, java_heap="3G")
        configure = plan["common_build_stages"][0]["argv"]
        self.assertIn("-DCMAKE_C_COMPILER=riscv64-unknown-elf-gcc", configure)
        self.assertIn("-DCMAKE_CXX_COMPILER=riscv64-unknown-elf-g++", configure)
        self.assertIn("-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY", configure)
        for profile in plan["profiles"]:
            self.assertIn("-j1", profile["build"]["argv"])
            self.assertIn("JAVA_HEAP_SIZE=3G", profile["build"]["argv"])

    def test_target_contract_matches_required_marker_and_failure_code(self):
        plan = planner.build_plan(self.root)
        positive, negative = plan["profiles"][0]["workloads"][1:3]
        self.assertEqual(positive["expected_marker"], "NOVA_BASELINE_V1 PASS hart=0 checks=8")
        self.assertEqual(negative["expected_marker"], "NOVA_BASELINE_V1 EXPECTED_FAIL hart=0 code=7")
        self.assertEqual(negative["expected_target_exit"], 7)
        self.assertTrue(negative["binary"].endswith("/nova-baseline-fail.riscv"))
        targets = plan["common_build_stages"][3]["argv"]
        self.assertIn("nova-baseline", targets)
        self.assertIn("nova-baseline-fail", targets)

    def test_direct_simulator_argv_uses_pinned_default_flags(self):
        binary = self.root / "program with spaces.riscv"
        args = planner.simulator_argv(self.root, "RocketConfig", binary)
        self.assertEqual(args[0], str(self.root / "sims/verilator/simulator-chipyard.harness-RocketConfig"))
        self.assertEqual(args[-1], str(binary))
        self.assertEqual(args[1:3], ["+permissive", "+dramsim"])
        self.assertIn("+verbose", args)
        self.assertIn("+max-cycles=10000000", args)
        self.assertIn("+verilator+seed+1", args)
        self.assertEqual(args[-2], "+permissive-off")
        self.assertNotIn("make", args)
        self.assertNotIn("sh", args)
        self.assertEqual(list(self.root.glob("*.riscv")), [])

    def test_only_the_two_single_core_profiles_are_allowed(self):
        for name in ("NovaM1MinimalConfig", "", "RocketConfig;echo", "../RocketConfig", None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                planner.simulator_argv(self.root, name, self.root / "binary")

    def test_seed_cycles_and_budget_bounds_are_strict(self):
        for value in (True, False, 0, -1, 10000001, "10", float("nan")):
            with self.subTest(cycles=value), self.assertRaises(ValueError):
                planner.simulator_argv(self.root, "RocketConfig", self.root / "binary", max_cycles=value)
        for value in (True, 0, -1, 2147483648, "1"):
            with self.subTest(seed=value), self.assertRaises(ValueError):
                planner.simulator_argv(self.root, "RocketConfig", self.root / "binary", seed=value)
        for jobs in (True, 0, 3, "2", 1.0):
            with self.subTest(jobs=jobs), self.assertRaises(ValueError):
                planner.build_plan(self.root, jobs=jobs)
        for heap in ("9G", "4g", "4G -Dunsafe", "", None, 4):
            with self.subTest(heap=heap), self.assertRaises(ValueError):
                planner.build_plan(self.root, java_heap=heap)

    def test_relative_and_control_character_paths_are_rejected(self):
        for path in ("relative", "/tmp/../other", "/tmp/a\nb", "/tmp/a\0b", "/tmp/a\\b"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                planner.simulator_argv(path, "RocketConfig", self.root / "binary")
            with self.subTest(binary=path), self.assertRaises(ValueError):
                planner.simulator_argv(self.root, "RocketConfig", path)

    def test_isa_omission_duplicate_wildcard_and_reordering_fail(self):
        choices = [list(planner.ISA_TESTS[:-1]), list(planner.ISA_TESTS) + [planner.ISA_TESTS[0]],
                   ["rv64ui-p-*"], list(reversed(planner.ISA_TESTS))]
        for names in choices:
            value = copy.deepcopy(self.manifest)
            value["isa_tests"] = names
            self.write_manifest(value)
            with self.subTest(names=names), self.assertRaises(ValueError):
                planner.load_workloads(self.path)

    def test_no_missing_unknown_or_optimistic_fields(self):
        variants = []
        value = copy.deepcopy(self.manifest)
        del value["exclusions"]
        variants.append(value)
        value = copy.deepcopy(self.manifest)
        value["skip_missing"] = True
        variants.append(value)
        for key, new in (("full_isa_certification", True), ("schema_version", True),
                         ("missing_workload_policy", "skip"), ("exclusions", [])):
            value = copy.deepcopy(self.manifest)
            value[key] = new
            variants.append(value)
        for value in variants:
            self.write_manifest(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                planner.load_workloads(self.path)

    def test_boolean_integer_confusion_does_not_weaken_contract(self):
        for value in (False, 0.0):
            manifest = copy.deepcopy(self.manifest)
            manifest["smoke_workloads"][0]["expected_target_exit"] = value
            self.write_manifest(manifest)
            with self.subTest(value=value), self.assertRaises(ValueError):
                planner.load_workloads(self.path)
        manifest = copy.deepcopy(self.manifest)
        manifest["reference"]["qualified"] = 0
        self.write_manifest(manifest)
        with self.assertRaises(ValueError):
            planner.load_workloads(self.path)

    def test_manifest_json_structure_is_bounded_and_strict(self):
        for raw in (b"{", b"[]", b'{"schema_version":1,"schema_version":1}',
                    b'{"value":NaN}', b"\xff", b" " * (planner.MAX_JSON_BYTES + 1)):
            self.path.write_bytes(raw)
            with self.subTest(prefix=raw[:40]), self.assertRaises(ValueError):
                planner.load_workloads(self.path)

    def test_symlink_and_fifo_leaves_are_not_read(self):
        other = self.root / "copy.json"
        other.write_bytes(self.path.read_bytes())
        link = self.root / "link.json"
        link.symlink_to(other)
        with self.assertRaises(ValueError):
            planner.load_workloads(link)
        fifo = self.root / "fifo.json"
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            planner.load_workloads(fifo)

    def test_source_gitlink_pin_mismatch_is_blocked(self):
        self.manifest["source_provenance"]["gitlinks"]["generators/rocket-chip"] = "a" * 40
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "source pins"):
            planner.build_plan(self.root)

    def test_repository_manifest_parent_cannot_escape_checkout(self):
        other = self.root / "other"
        other.mkdir()
        link = other / "nova"
        link.symlink_to(self.root / "nova", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "escapes"):
            planner.build_plan(other)

    def test_source_chipyard_revision_mismatch_is_blocked(self):
        self.manifest["source_provenance"]["chipyard_commit"] = "b" * 40
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "Chipyard revision"):
            planner.build_plan(self.root)

    def test_invalid_and_duplicate_upstream_provenance_is_blocked(self):
        self.lock["submodules"].append(copy.deepcopy(self.lock["submodules"][0]))
        self.write_lock()
        with self.assertRaisesRegex(ValueError, "duplicate upstream"):
            planner.build_plan(self.root)
        self.lock["submodules"] = []
        self.write_lock()
        with self.assertRaisesRegex(ValueError, "source pins"):
            planner.build_plan(self.root)

    def test_cli_is_readonly_json_and_redacts_checkout(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), \
             patch("subprocess.run", side_effect=AssertionError("executed command")):
            result = planner.main(["--root", str(self.root)])
        self.assertEqual(result, 0)
        self.assertNotIn(str(self.root), output.getvalue())
        self.assertIn("<repo>", output.getvalue())
        self.assertFalse(json.loads(output.getvalue())["hardware_qualified"])

    def test_missing_manifest_returns_diagnostic_without_creating_files(self):
        missing = self.root / "missing"
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            result = planner.main(["--root", str(missing)])
        self.assertEqual(result, 2)
        self.assertFalse(missing.exists())
        self.assertNotIn(str(self.root), output.getvalue())


if __name__ == "__main__":
    unittest.main()
