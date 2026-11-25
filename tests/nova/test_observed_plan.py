"""Offline contract tests for the opt-in HTIF observer campaign plan."""

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nova_observed_campaign_plan", ROOT / "scripts/nova/campaign_plan.py")
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


class ObservedPlanTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="nova observed plan ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "nova").mkdir()
        for name in ("g1-workloads.json", "upstream-lock.json"):
            (self.root / "nova" / name).write_bytes((ROOT / "nova" / name).read_bytes())

    def test_default_plan_preserves_exact_legacy_contract(self):
        plan = planner.build_plan(self.root)
        self.assertEqual(plan, planner.build_plan(self.root, observe_target_exit=False))
        self.assertIs(type(plan["schema_version"]), int)
        self.assertEqual(plan["schema_version"], 1)
        self.assertNotIn("target_exit_observer", plan)
        # Captured from the unchanged schema-1 producer before this extension.
        serialized = json.dumps(plan, sort_keys=True, separators=(",", ":"),
                                allow_nan=False).replace(str(self.root), "<repo>")
        self.assertEqual(hashlib.sha256(serialized.encode()).hexdigest(),
                         "5bac843981ec9ca9e1b12047c15cc5efb510e9604297d73b89c05cedecce5a89")

    def test_observer_metadata_has_exact_fixed_keys_values_and_types(self):
        plan = planner.build_plan(self.root, observe_target_exit=True)
        expected = {
            "schema_version": 1,
            "kind": "nova-htif-exit",
            "source_gitlink": "toolchains/riscv-tools/riscv-isa-sim",
            "source_commit": "9c190a07c6838f6392bafa4ad83acea462c7f759",
            "upstream_htif_sha256": "c669e8352c6e21d61118849b0b969d291b84100e83343659f3d08979ae89a11d",
            "output_directory": "nova-out/htif-observer",
            "manifest_path": "nova-out/htif-observer/manifest.json",
            "make_fragment": "software/nova/observer/observer.mk",
            "witness_max_bytes": 4096,
            "dedicated_witness_required": True,
            "signal_exit_accepted": False,
        }
        self.assertIs(type(plan["schema_version"]), int)
        self.assertEqual(plan["schema_version"], 2)
        self.assertEqual(plan["target_exit_observer"], expected)
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertIs(type(plan["target_exit_observer"][key]), type(value))

    def test_preparation_is_first_bounded_stage_with_exact_direct_argv(self):
        plan = planner.build_plan(self.root, observe_target_exit=True)
        prepare = plan["common_build_stages"][0]
        self.assertEqual(prepare, {
            "id": "htif-observer-prepare", "timeout_seconds": 120,
            "argv": ["python3", "-B", str(self.root / "scripts/nova/htif_observer.py"),
                     "--prepare", "--root", str(self.root),
                     "--output", str(self.root / "nova-out/htif-observer")],
        })
        self.assertIs(type(prepare["timeout_seconds"]), int)
        self.assertTrue(all(type(arg) is str for arg in prepare["argv"]))
        self.assertEqual([stage["id"] for stage in plan["common_build_stages"]],
                         ["htif-observer-prepare", "hello-configure", "hello-build",
                          "nova-target-configure", "nova-target-build"])

    def test_both_builds_load_observer_after_upstream_makefile(self):
        plan = planner.build_plan(self.root, jobs=1, java_heap="3G",
                                  observe_target_exit=True)
        for profile in plan["profiles"]:
            with self.subTest(configuration=profile["configuration"]):
                self.assertEqual(profile["build"]["argv"], [
                    "make", "-C", str(self.root / "sims/verilator"),
                    "-f", "Makefile", "-f",
                    str(self.root / "software/nova/observer/observer.mk"),
                    "CONFIG=" + profile["configuration"], "JAVA_HEAP_SIZE=3G", "-j1",
                ])
                self.assertEqual(profile["build"]["timeout_seconds"], 7200)
                self.assertTrue(all(type(arg) is str for arg in profile["build"]["argv"]))

    def test_mode_changes_only_schema_metadata_preparation_and_make_arguments(self):
        for jobs, heap in ((1, "1G"), (2, "4G"), (2, "8G")):
            with self.subTest(jobs=jobs, java_heap=heap):
                legacy = planner.build_plan(self.root, jobs=jobs, java_heap=heap)
                observed = planner.build_plan(self.root, jobs=jobs, java_heap=heap,
                                               observe_target_exit=True)
                restored = copy.deepcopy(observed)
                restored["schema_version"] = 1
                del restored["target_exit_observer"]
                del restored["common_build_stages"][0]
                for profile in restored["profiles"]:
                    del profile["build"]["argv"][3:7]
                self.assertEqual(restored, legacy)

    def test_policy_is_immutable_and_each_plan_owns_its_metadata(self):
        with self.assertRaises(TypeError):
            planner.TARGET_EXIT_OBSERVER_POLICY["witness_max_bytes"] = 8192
        first = planner.build_plan(self.root, observe_target_exit=True)
        original = copy.deepcopy(first)
        first["target_exit_observer"]["signal_exit_accepted"] = True
        first["target_exit_observer"]["source_commit"] = "0" * 40
        first["common_build_stages"][0]["argv"].append("--unsafe")
        first["profiles"][0]["build"]["argv"][6] = "another.mk"
        self.assertEqual(planner.build_plan(self.root, observe_target_exit=True), original)
        self.assertNotEqual(first["profiles"][0]["build"]["argv"][6],
                            first["profiles"][1]["build"]["argv"][6])

    def test_observer_option_requires_an_actual_boolean(self):
        for value in (None, 0, 1, -1, 0.0, 1.0, "true", "false", [], {}, object()):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "boolean"):
                planner.build_plan(self.root, observe_target_exit=value)

    def test_observer_plan_needs_no_prepared_dependencies_and_never_executes(self):
        before = sorted((str(path.relative_to(self.root)), path.read_bytes())
                        for path in self.root.rglob("*") if path.is_file())
        with patch("subprocess.run", side_effect=AssertionError("executed command")), \
             patch("subprocess.Popen", side_effect=AssertionError("started command")), \
             patch("os.system", side_effect=AssertionError("executed shell")), \
             patch("shutil.which", side_effect=AssertionError("probed dependency")), \
             patch("os.getenv", side_effect=AssertionError("read environment")), \
             patch("pathlib.Path.mkdir", side_effect=AssertionError("created directory")), \
             patch.dict("os.environ", {"RISCV": "/not/a/prepared/prefix"}, clear=True):
            first = planner.build_plan(self.root, observe_target_exit=True)
            second = planner.build_plan(self.root, observe_target_exit=True)
        after = sorted((str(path.relative_to(self.root)), path.read_bytes())
                       for path in self.root.rglob("*") if path.is_file())
        self.assertEqual(first, second)
        self.assertEqual(before, after)
        self.assertFalse((self.root / "nova-out").exists())
        self.assertFalse((self.root / "software").exists())
        self.assertNotIn("/not/a/prepared/prefix", json.dumps(first))

    def test_observer_plan_retains_unqualified_scope_and_all_workloads(self):
        plan = planner.build_plan(self.root, observe_target_exit=True)
        self.assertIs(plan["hardware_qualified"], False)
        self.assertIs(plan["g1_gate_passed"], False)
        self.assertIs(plan["reference"]["qualified"], False)
        self.assertIs(plan["reproduction"]["automatic_gate_acceptance"], False)
        self.assertEqual(plan["missing_workload_policy"], "block-no-skips")
        self.assertEqual([profile["configuration"] for profile in plan["profiles"]],
                         ["RocketConfig", "NovaM1BaselineConfig"])
        self.assertEqual(plan["profiles"][0]["workloads"], plan["profiles"][1]["workloads"])
        for profile in plan["profiles"]:
            self.assertEqual(len(profile["workloads"]), 15)
            self.assertEqual(profile["workloads"][2]["expected_target_exit"], 7)

    def test_cli_observer_flag_is_readonly_and_redacts_checkout(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), \
             patch("subprocess.run", side_effect=AssertionError("executed command")), \
             patch("subprocess.Popen", side_effect=AssertionError("started command")):
            result = planner.main(["--root", str(self.root), "--observe-target-exit"])
        self.assertEqual(result, 0)
        self.assertNotIn(str(self.root), output.getvalue())
        plan = json.loads(output.getvalue())
        self.assertEqual(plan["schema_version"], 2)
        self.assertEqual(plan["common_build_stages"][0]["argv"], [
            "python3", "-B", "<repo>/scripts/nova/htif_observer.py",
            "--prepare", "--root", "<repo>", "--output", "<repo>/nova-out/htif-observer",
        ])
        self.assertIs(plan["hardware_qualified"], False)
        self.assertFalse((self.root / "nova-out").exists())

    def test_make_target_routes_to_runner_plan_with_observer_flag(self):
        makefile = (ROOT / "nova.mk").read_text(encoding="utf-8")
        phony = re.search(r"^\.PHONY: (.+)$", makefile, re.MULTILINE)
        self.assertIn("g1-observed-plan", phony.group(1).split())
        recipes = re.findall(r"^g1-observed-plan:\n((?:\t.*\n)+)",
                             makefile, re.MULTILINE)
        self.assertEqual(recipes, [
            "\t$(PYTHON) -B scripts/nova/g1_campaign.py --plan --observe-target-exit\n",
        ])


if __name__ == "__main__":
    unittest.main()
