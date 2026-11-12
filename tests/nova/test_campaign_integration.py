"""Offline producer/consumer integration; all build and CPU results are synthetic.

Real planning, orchestration, log assessment, hashing, serialization, and
comparison run. No compiler, target, simulator, or dependency installer runs.
Source/toolchain identities and hardware artifacts are deliberately invented
test doubles and must never be cited as processor-execution evidence.
"""

import argparse
import contextlib
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


def load_module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


campaign = load_module("nova_integration_campaign", ROOT / "scripts/nova/g1_campaign.py")
fixtures = load_module("nova_integration_fixtures", Path(__file__).with_name("test_compare_campaigns.py"))
compare = fixtures.compare
capture_regular = campaign.capture_file
FIXTURE_LINE = b"SYNTHETIC FIXTURE ONLY; no processor executed\n"
COMPLETION = b"*** PASSED *** Completed after          123 simulation cycles\n"


class CampaignIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="nova-synthetic-integration-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()

    def produce(self, label, *, wrong_negative=False, conflicting_positive=False,
                post_drift=None):
        """Produce the real record schema around explicitly synthetic boundaries."""
        root = self.directory / label
        (root / "nova").mkdir(parents=True)
        (root / "sims/verilator").mkdir(parents=True)
        (root / "env.sh").write_text("# Synthetic prepared fixture; never sourced.\n")
        for name in ("g1-workloads.json", "g1-profile.json", "upstream-lock.json"):
            shutil.copyfile(ROOT / "nova" / name, root / "nova" / name)
        riscv, conda = self.directory / (label + "-riscv"), self.directory / (label + "-conda")
        riscv.mkdir()
        conda.mkdir()
        env = {"RISCV": str(riscv), "CONDA_PREFIX": str(conda), "PATH": "/usr/bin"}
        template = fixtures.synthetic_record(label)
        source = copy.deepcopy(template["source_before"])
        for relative in ("nova/g1-workloads.json", "nova/g1-profile.json", "nova/upstream-lock.json"):
            source["source_inputs"][relative] = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        profile = copy.deepcopy(template["preflight"]["profile"])
        inventory = copy.deepcopy(template["inventory"])
        inventory.update(hardware_qualified=False, g1_gate_passed=False)
        provenance = copy.deepcopy(template["provenance_before"])
        calls = []

        def fake_capture(base, path, kind="artifact", max_bytes=512 * 1024 * 1024):
            if kind not in {"riscv_elf", "simulator"}:
                # Manifests and retained logs use the actual bounded capture.
                return capture_regular(base, path, kind=kind, max_bytes=max_bytes)
            relative = str(Path(path).relative_to(base))
            invented = ("SYNTHETIC UNEXECUTED " + kind + ":" + relative).encode()
            return {"path": relative, "kind": kind, "size_bytes": len(invented),
                    "sha256": hashlib.sha256(invented).hexdigest()}

        def fake_artifacts(base, config):
            simulator = fake_capture(base, base / "sims/verilator" /
                                     ("simulator-chipyard.harness-" + config), kind="simulator")
            collateral = [{"path": "synthetic-not-generated/" + config + "/" + kind,
                           "kind": kind, "size_bytes": 100,
                           "sha256": fixtures.digest(config + " invented " + kind)}
                          for kind in ("rtl", "device_tree", "metadata")]
            return {"status": "captured", "reasons": [], "artifacts": [simulator, *collateral]}

        def fake_run(cwd, output_dir, name, argv, timeout_seconds, **limits):
            """Emit fixtures, never launch the argv being recorded as a test double."""
            calls.append(name)
            stdout, stderr = FIXTURE_LINE, FIXTURE_LINE
            negative = name.endswith("-nova-baseline-fail")
            if name.endswith("-hello"):
                stdout += b"Hello world from core 0, a rocket\n"
                stderr += COMPLETION
            elif negative:
                stdout += b"NOVA_BASELINE_V1 EXPECTED_FAIL hart=0 code=7\n"
                stderr += (b"Assertion failed: *** FAILED *** (exit code =          "
                           + (b"6" if wrong_negative else b"7") + b")\n")
            elif name.endswith("-nova-baseline"):
                stdout += b"NOVA_BASELINE_V1 PASS hart=0 checks=8\n"
                if conflicting_positive:
                    stdout += b"NOVA_BASELINE_V1 EXPECTED_FAIL hart=0 code=7\n"
                stderr += COMPLETION
            elif any(name.endswith("-" + identifier) for identifier in compare.WORKLOAD_IDS[3:]):
                stderr += COMPLETION
            paths = {stream: output_dir / (name + "." + stream + ".log")
                     for stream in ("stdout", "stderr")}
            paths["stdout"].write_bytes(stdout)
            paths["stderr"].write_bytes(stderr)
            instant = campaign.utc_now()
            result = {"name": name, "status": "failed" if negative else "passed",
                      "exit_code": -6 if negative else 0, "command": list(argv),
                      "timed_out": False, "elapsed_seconds": 0.0,
                      "started_utc": instant, "finished_utc": instant,
                      "timeout_seconds": timeout_seconds,
                      "min_free_gib": limits["min_free_gib"], "max_log_bytes": limits["max_log_bytes"],
                      "hardware_qualified": False, "g1_gate_passed": False}
            if negative:
                result["reason"] = "command exited unsuccessfully"
            for stream, data in (("stdout", stdout), ("stderr", stderr)):
                result[stream] = paths[stream].name
                result[stream + "_bytes"] = len(data)
                result[stream + "_sha256"] = hashlib.sha256(data).hexdigest()
            return result

        profile_after, inventory_after = copy.deepcopy(profile), copy.deepcopy(inventory)
        if post_drift == "profile":
            profile_after["collateral"]["synthetic"]["sha256"] = fixtures.digest("changed collateral")
        elif post_drift == "inventory":
            inventory_after["matching_package_count"] -= 1
        args = argparse.Namespace(approved_budget=True, jobs=2, java_heap="4G",
                                  total_timeout_seconds=7200, min_free_gib=10)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(campaign, "ROOT", root))
            stack.enter_context(patch.object(campaign, "capture_source", side_effect=lambda _: copy.deepcopy(source)))
            stack.enter_context(patch.object(campaign, "capture_file", side_effect=fake_capture))
            stack.enter_context(patch.object(campaign, "capture_profile_artifacts", side_effect=fake_artifacts))
            stack.enter_context(patch.object(campaign, "inspect_profile", side_effect=[profile, profile_after]))
            stack.enter_context(patch.object(campaign, "inspect_inventory", side_effect=[inventory, inventory_after]))
            stack.enter_context(patch.object(campaign, "collect_provenance",
                                            side_effect=lambda _: copy.deepcopy(provenance)))
            stack.enter_context(patch.object(campaign, "run_command", side_effect=fake_run))
            stack.enter_context(patch.object(campaign.shutil, "disk_usage", return_value=
                                            shutil._ntuple_diskusage(100, 0, 100 * 1024 ** 3)))
            # Any unexpected real process launch fails, including future helpers.
            stack.enter_context(patch("subprocess.Popen", side_effect=AssertionError("unexpected process launch")))
            record, path = campaign.execute(root, args, env=env)
        self.assertEqual(json.loads(path.read_text()), record)
        self.assertIs(record["hardware_qualified"], False)
        self.assertIs(record["g1_gate_passed"], False)
        self.assertEqual(record["reference_comparison"], "not_run")
        return record, calls

    def test_paired_producer_records_compare_without_hardware_claims(self):
        left, left_calls = self.produce("left")
        right, right_calls = self.produce("right")
        for record, calls in ((left, left_calls), (right, right_calls)):
            self.assertEqual(record["status"], "workloads_observed", record["reasons"])
            self.assertEqual(len(calls), 37)
            self.assertEqual([len(profile["workloads"]) for profile in record["profiles"]], [15, 15])
            for profile in record["profiles"]:
                for row in profile["workloads"]:
                    self.assertIs(row["assessment"]["target_completion_verified"], False)
                    self.assertTrue(row["assessment"]["expectation_met"])
                self.assertEqual(profile["workloads"][2]["stage"]["exit_code"], -6)
        result = compare.compare_records(left, right)
        self.assertEqual(result["status"], "consistent", result["reasons"])
        for key in ("hardware_qualified", "g1_gate_passed", "reference_comparison_qualified"):
            self.assertIs(result[key], False)

    def test_wrong_negative_control_survives_as_failed_record(self):
        left, _ = self.produce("left")
        right, calls = self.produce("wrong-negative", wrong_negative=True)
        self.assertEqual(right["status"], "failed", right["reasons"])
        row = right["profiles"][0]["workloads"][2]
        self.assertEqual(row["stage"]["exit_code"], -6)
        self.assertFalse(row["assessment"]["expected_target_failure_verified"])
        self.assertLess(len(calls), 37)
        self.assertEqual(compare.compare_records(left, right)["status"], "blocked")

    def test_conflicting_positive_log_blocks_producer_and_consumer(self):
        left, _ = self.produce("left")
        right, _ = self.produce("conflicting", conflicting_positive=True)
        self.assertEqual(right["status"], "failed", right["reasons"])
        assessment = right["profiles"][0]["workloads"][1]["assessment"]
        self.assertFalse(assessment["expectation_met"])
        self.assertFalse(assessment["completion_protocol_observed"])
        self.assertEqual(compare.compare_records(left, right)["status"], "blocked")

    def test_counterpart_source_identity_difference_is_not_consistent(self):
        left, _ = self.produce("left")
        right, _ = self.produce("right")
        for key in ("source_before", "source_after"):
            right[key]["revision"] = "9" * 40
            right[key]["state_digest"] = fixtures.digest("different source")
        self.assertEqual(compare.compare_records(left, right)["status"], "different")

    def test_produced_commands_and_post_binary_fields_are_checked(self):
        left, _ = self.produce("left")
        right, _ = self.produce("right")
        for field in ("command", "binary_after"):
            with self.subTest(field=field):
                changed = copy.deepcopy(right)
                row = changed["profiles"][1]["workloads"][0]
                if field == "command":
                    row["stage"]["command"][0] += "-wrong"
                else:
                    row["binary_after"]["sha256"] = fixtures.digest("changed binary")
                self.assertEqual(compare.compare_records(left, changed)["status"], "blocked")

    def test_post_environment_drift_invalidates_produced_campaign(self):
        left, _ = self.produce("left")
        for kind in ("profile", "inventory"):
            with self.subTest(kind=kind):
                right, calls = self.produce("drift-" + kind, post_drift=kind)
                self.assertEqual(len(calls), 37)
                self.assertEqual(right["status"], "failed", right["reasons"])
                self.assertEqual(compare.compare_records(left, right)["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
