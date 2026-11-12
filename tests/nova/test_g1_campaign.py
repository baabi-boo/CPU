"""Offline orchestration-boundary tests; never execute a real target/simulator."""

import argparse
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("nova_g1_campaign_tested", ROOT / "scripts/nova/g1_campaign.py")
campaign = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(campaign)


class CampaignTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "nova").mkdir()
        for name in ("g1-workloads.json", "upstream-lock.json", "g1-profile.json"):
            shutil.copyfile(ROOT / "nova" / name, self.root / "nova" / name)
        (self.root / "sims/verilator").mkdir(parents=True)
        (self.root / "env.sh").write_text("# existing fixture, never sourced\n")
        self.riscv = self.root / "prepared-riscv"
        self.riscv.mkdir()
        self.conda = self.root / "prepared-conda"
        self.conda.mkdir()
        self.env = {"RISCV": str(self.riscv), "CONDA_PREFIX": str(self.conda), "PATH": "/usr/bin"}
        self.args = argparse.Namespace(approved_budget=True, jobs=2, java_heap="4G",
                                       total_timeout_seconds=7200, min_free_gib=10)
        self.source = {
            "revision": "a" * 40, "tree": "b" * 40, "clean": True,
            "checkout_identity_sha256": "c" * 64, "state_digest": "d" * 64,
            "lock_hashes": {campaign.CONDA_LOCK: "e" * 64}, "source_inputs": {},
            "submodules": [{"path": "generators/rocket-chip", "pin": "f" * 40,
                            "revision": "f" * 40, "initialized": True,
                            "clean": True, "state": "at_pin"}],
        }
        self.profile = {"status": "ready", "profile": "g1-chisel6-rocket",
                        "known_prerequisites_present": True,
                        "toolchain_version_inputs_verified": True,
                        "hardware_qualified": False, "g1_gate_passed": False, "blockers": []}
        self.inventory = {"status": "matched", "blockers": [], "lock_sha256": "e" * 64,
                          "metadata_only": True, "hardware_qualified": False,
                          "g1_gate_passed": False}
        self.provenance = {"capture_complete": True, "toolchain_versions_verified": False,
                           "tool_versions": {"verilator": "5.022"}}
        self.commands = []
        self.captured = []

    def fake_capture(self, root, path, kind="artifact", max_bytes=512 * 1024 * 1024):
        path = Path(path)
        self.captured.append((root, path, kind))
        relative = str(path.relative_to(root))
        data = path.read_bytes() if path.is_file() else (relative + ":" + kind).encode()
        return {"path": relative, "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(), "kind": kind}

    def fake_run(self, cwd, output_dir, name, argv, timeout_seconds, **kwargs):
        self.commands.append({"cwd": cwd, "name": name, "argv": argv,
                              "timeout_seconds": timeout_seconds, **kwargs})
        stdout = output_dir / (name + ".stdout.log")
        stderr = output_dir / (name + ".stderr.log")
        stdout.write_bytes(b"offline fixture stdout\n")
        stderr.write_bytes(b"offline fixture stderr\n")
        negative = name.endswith("-nova-baseline-fail")
        return {"name": name, "status": "failed" if negative else "passed",
                "exit_code": -6 if negative else 0, "command": argv,
                "stdout": stdout.name, "stderr": stderr.name,
                "stdout_sha256": hashlib.sha256(stdout.read_bytes()).hexdigest(),
                "stderr_sha256": hashlib.sha256(stderr.read_bytes()).hexdigest(),
                "stdout_bytes": stdout.stat().st_size, "stderr_bytes": stderr.stat().st_size,
                "timed_out": False,
                "reason": "command exited unsuccessfully" if negative else None,
                "elapsed_seconds": 0.001, "started_utc": "test-start", "finished_utc": "test-finish"}

    def fake_artifacts(self, root, config):
        return {"status": "captured", "reasons": [], "artifacts": [
            self.fake_capture(root, root / "sims/verilator" / ("simulator-chipyard.harness-" + config),
                              kind="simulator")]}

    @staticmethod
    def fake_assessment(stdout, stderr, exit_code, workload, max_cycles=10000000):
        negative = workload["expected_target_exit"] != 0
        return {"status": "passed", "expectation_met": True,
                "target_completion_verified": False, "completion_protocol_observed": not negative,
                "expected_target_failure_verified": negative, "reasons": [],
                "hardware_qualified": False, "g1_gate_passed": False,
                "stdout_sha256": hashlib.sha256(stdout.read_bytes()).hexdigest(),
                "stderr_sha256": hashlib.sha256(stderr.read_bytes()).hexdigest(),
                "stdout_bytes": stdout.stat().st_size, "stderr_bytes": stderr.stat().st_size}

    @contextlib.contextmanager
    def prepared(self, **overrides):
        defaults = {
            "capture_source": lambda root: copy.deepcopy(self.source),
            "capture_file": self.fake_capture,
            "capture_profile_artifacts": self.fake_artifacts,
            "inspect_profile": lambda root, env=None: copy.deepcopy(self.profile),
            "inspect_inventory": lambda lock, prefix: copy.deepcopy(self.inventory),
            "collect_provenance": lambda root: copy.deepcopy(self.provenance),
            "run_command": self.fake_run,
            "assess_workload": self.fake_assessment,
        }
        defaults.update(overrides)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(campaign, "ROOT", self.root))
            for name, replacement in defaults.items():
                stack.enter_context(patch.object(campaign, name, side_effect=replacement))
            stack.enter_context(patch.object(campaign.shutil, "disk_usage",
                                            return_value=shutil._ntuple_diskusage(100, 0, 100 * 1024 ** 3)))
            yield

    def execute(self, **overrides):
        with self.prepared(**overrides):
            record, path = campaign.execute(self.root, self.args, env=self.env)
        self.assertEqual(json.loads(path.read_text()), record)
        self.assertFalse(record["hardware_qualified"])
        self.assertFalse(record["g1_gate_passed"])
        self.assertEqual(record["reference_comparison"], "not_run")
        self.assertIsNotNone(record["finished_utc"])
        return record

    def test_default_plan_is_read_only_and_checkout_normalized(self):
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        output = io.StringIO()
        with patch("subprocess.run", side_effect=AssertionError("subprocess ran")), \
             patch("subprocess.Popen", side_effect=AssertionError("subprocess ran")), \
             patch.object(campaign, "make_output_dir", side_effect=AssertionError("created output")), \
             contextlib.redirect_stdout(output):
            self.assertEqual(campaign.main(["--root", str(self.root)]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["kind"], "nova-g1-campaign-plan")
        self.assertNotIn(str(self.root), output.getvalue())
        self.assertFalse(report["g1_gate_passed"])
        self.assertEqual(before, sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*")))
        self.assertEqual(report["resource_limits"]["java_heap"], "4G")
        self.assertEqual(report["resource_limits"]["min_free_gib"], 10)

    def test_plan_digest_is_equal_for_independent_checkout_paths(self):
        plan = campaign.build_plan(self.root)
        other = Path("/some/other/checkout")
        relocated = json.loads(json.dumps(plan).replace(str(self.root), str(other)))
        self.assertEqual(campaign.plan_digest(plan, self.root), campaign.plan_digest(relocated, other))

    def test_explicit_approval_required_before_creating_output(self):
        self.args.approved_budget = False
        with self.assertRaises(ValueError):
            campaign.execute(self.root, self.args, env=self.env)
        self.assertFalse((self.root / "nova-out").exists())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            campaign.main(["--root", str(self.root), "--execute"])

    def test_budget_and_resource_bounds_cannot_be_overridden(self):
        for field, values in {"jobs": [True, 0, 3], "java_heap": ["9G", "4g", "4G -Xmx99G"],
                              "total_timeout_seconds": [True, 0, 299, 7201],
                              "min_free_gib": [True, 0, 51]}.items():
            for value in values:
                args = copy.copy(self.args)
                setattr(args, field, value)
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    campaign.resource_limits(args)

    def test_both_profiles_all_workloads_and_raw_negative_exit_are_retained(self):
        record = self.execute()
        self.assertEqual(record["status"], "workloads_observed")
        self.assertEqual(record["reasons"], [])
        self.assertEqual(record["profile_after"], record["preflight"]["profile"])
        self.assertEqual(record["inventory_after"], record["inventory"])
        self.assertGreaterEqual(record["elapsed_seconds"], 0)
        self.assertEqual(record["declared_plan"], campaign.normalized_plan(campaign.build_plan(self.root), self.root))
        self.assertEqual(record["execution_paths"]["repository"], str(self.root))
        self.assertEqual(len(record["common_stages"]), 4)
        self.assertEqual([row["configuration"] for row in record["profiles"]], list(campaign.CONFIGURATIONS))
        self.assertEqual(len(self.commands), 37)  # checker + 4 target + 2 simulator + 30 workload
        for profile in record["profiles"]:
            self.assertEqual(len(profile["workloads"]), 15)
            for row in profile["workloads"]:
                self.assertEqual(row["binary"], row["binary_after"])
                self.assertEqual(row["simulator_sha256"], row["simulator_sha256_after"])
                self.assertTrue(row["assessment"]["expectation_met"])
                self.assertFalse(row["assessment"]["target_completion_verified"])
            negative = profile["workloads"][2]
            self.assertEqual(negative["stage"]["status"], "failed")
            self.assertEqual(negative["stage"]["exit_code"], -6)
            self.assertTrue(negative["assessment"]["expected_target_failure_verified"])

    def test_execution_commands_are_direct_and_profiles_are_built_separately(self):
        self.execute()
        builds = [call for call in self.commands if call["argv"][0] == "make"]
        self.assertEqual(len(builds), 2)
        for call, config in zip(builds, campaign.CONFIGURATIONS):
            self.assertIn("CONFIG=" + config, call["argv"])
            self.assertIn("JAVA_HEAP_SIZE=4G", call["argv"])
            self.assertIn("-j2", call["argv"])
        sims = [call for call in self.commands if "/simulator-" in call["argv"][0]]
        self.assertEqual(len(sims), 30)
        for call in sims:
            self.assertEqual(call["cwd"], self.root / "sims/verilator")
            self.assertIn("+verbose", call["argv"])
            self.assertIn("+max-cycles=10000000", call["argv"])
            self.assertEqual(call["min_free_gib"], 10)
            self.assertLessEqual(call["timeout_seconds"], 300)
        self.assertTrue(any(kind == "riscv_elf" and root == self.riscv for root, path, kind in self.captured))

    def test_dirty_checkout_is_blocked_without_any_build(self):
        self.source["clean"] = False
        record = self.execute()
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(self.commands, [])
        self.assertTrue(all(row["stage"]["status"] == "not_run"
                            for profile in record["profiles"] for row in profile["workloads"]))

    def test_relevant_inherited_overrides_are_rejected_even_when_empty(self):
        for key in ("MAKEFLAGS", "USE_CHISEL7", "CONFIG", "JAVA_TOOL_OPTIONS", "CMAKE_TOOLCHAIN_FILE",
                    "CLOCK_PERIOD", "RESET_DELAY", "EXTRA_SIM_PREPROC_DEFINES", "EXTRA_CHISEL_OPTIONS",
                    "TB", "MFC_BASE_LOWERING_OPTIONS", "TOP_MACROCOMPILER_MODE", "GEN_COLLATERAL_DIR",
                    "generated_src_name", "MFC_EXTRA_ANNO_FILE", "sim_common_files"):
            with self.subTest(key=key):
                self.env[key] = ""
                record = self.execute()
                self.assertEqual(record["status"], "blocked")
                self.assertIn(key, record["reasons"][0])
                del self.env[key]
        self.assertEqual(self.commands, [])

    def test_conditional_pinned_make_inputs_are_enumerated_in_override_policy(self):
        inputs = ("variables.mk", "common.mk", "sims/common-sim-flags.mk", "sims/verilator/Makefile")
        names = set()
        for relative in inputs:
            names.update(re.findall(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*\?=",
                                    (ROOT / relative).read_text(), flags=re.MULTILINE))
        self.assertEqual(names - campaign.FORBIDDEN_ENV, set())

    def test_foreign_execution_root_blocks_before_output_or_commands(self):
        with patch.object(campaign, "run_command") as runner, self.assertRaisesRegex(ValueError, "checkout containing"):
            campaign.execute(self.root, self.args, env=self.env)
        runner.assert_not_called()
        self.assertFalse((self.root / "nova-out").exists())

    def test_engine_cannot_substitute_a_different_recorded_command(self):
        def run(*args, **kwargs):
            result = self.fake_run(*args, **kwargs)
            result["command"] = ["different-command"]
            return result
        record = self.execute(run_command=run)
        self.assertEqual(record["status"], "failed")
        self.assertIn("command differs", record["reasons"][0])

    def test_override_values_are_not_copied_to_report(self):
        self.env["SBT_OPTS"] = "PRIVATE_ARGUMENT_DO_NOT_RECORD"
        record = self.execute()
        self.assertNotIn(self.env["SBT_OPTS"], json.dumps(record))

    def test_stale_products_are_not_removed(self):
        stale = self.root / "software/nova/baseline/build"
        stale.mkdir(parents=True)
        marker = stale / "keep.txt"
        marker.write_text("user data")
        record = self.execute()
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(marker.read_text(), "user data")
        self.assertEqual(self.commands, [])

    def test_prepared_prefixes_and_env_file_are_required(self):
        del self.env["CONDA_PREFIX"]
        record = self.execute()
        self.assertEqual(record["status"], "blocked")
        self.assertIn("CONDA_PREFIX", record["reasons"][0])
        self.assertEqual(self.commands, [])

    def test_profile_not_ready_blocks(self):
        self.profile["known_prerequisites_present"] = False
        record = self.execute()
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(self.commands, [])

    def test_inventory_must_match_the_same_pinned_lock(self):
        self.inventory["lock_sha256"] = "0" * 64
        record = self.execute()
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(self.commands, [])

    def test_complete_legacy_provenance_is_required(self):
        self.provenance["capture_complete"] = False
        record = self.execute()
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(self.commands, [])

    def test_missing_named_isa_binary_blocks_before_builds(self):
        def capture(root, path, **kwargs):
            if Path(path).name == "rv64mi-p-scall":
                raise ValueError("required ISA binary absent")
            return self.fake_capture(root, path, **kwargs)
        record = self.execute(capture_file=capture)
        self.assertEqual(record["status"], "blocked")
        self.assertEqual([row["name"] for row in self.commands], ["pinned-input-check"])

    def test_build_failure_stops_and_retains_record(self):
        def run(*args, **kwargs):
            result = self.fake_run(*args, **kwargs)
            if result["name"] == "hello-build":
                result.update(status="failed", exit_code=2, reason="command exited unsuccessfully")
            return result
        record = self.execute(run_command=run)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["common_stages"][-1]["exit_code"], 2)
        self.assertEqual(len(self.commands), 3)

    def test_missing_profile_artifact_blocks_all_its_workloads(self):
        record = self.execute(capture_profile_artifacts=lambda *args: {
            "status": "blocked", "artifacts": [], "reasons": ["missing DTS"]})
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(record["profiles"][0]["workloads"][0]["stage"]["status"], "not_run")

    def test_negative_target_is_not_accepted_after_timeout(self):
        def run(*args, **kwargs):
            result = self.fake_run(*args, **kwargs)
            if result["name"].endswith("-nova-baseline-fail"):
                result.update(timed_out=True, reason="stage deadline exceeded")
            return result
        record = self.execute(run_command=run)
        self.assertEqual(record["status"], "failed")
        self.assertIsNone(record["profiles"][0]["workloads"][2]["assessment"])

    def test_negative_target_not_accepted_on_engine_integrity_failure(self):
        def run(*args, **kwargs):
            result = self.fake_run(*args, **kwargs)
            if result["name"].endswith("-nova-baseline-fail"):
                result["reason"] = "command exited with surviving group descendants"
            return result
        record = self.execute(run_command=run)
        self.assertEqual(record["status"], "failed")
        self.assertIsNone(record["profiles"][0]["workloads"][2]["assessment"])

    def test_marker_or_assessment_alone_does_not_count_as_protocol(self):
        def assess(*args, **kwargs):
            result = self.fake_assessment(*args, **kwargs)
            result["completion_protocol_observed"] = False
            return result
        record = self.execute(assess_workload=assess)
        self.assertEqual(record["status"], "failed")

    def test_positive_target_exit_attestation_is_never_claimed(self):
        def assess(*args, **kwargs):
            result = self.fake_assessment(*args, **kwargs)
            result["target_completion_verified"] = True
            return result
        self.assertEqual(self.execute(assess_workload=assess)["status"], "failed")

    def test_assessment_must_reference_the_exact_retained_streams(self):
        def assess(*args, **kwargs):
            result = self.fake_assessment(*args, **kwargs)
            result["stdout_sha256"] = "0" * 64
            return result
        self.assertEqual(self.execute(assess_workload=assess)["status"], "failed")

    def test_log_tampering_after_execution_is_rejected(self):
        def run(*args, **kwargs):
            result = self.fake_run(*args, **kwargs)
            if result["name"].endswith("-hello"):
                (args[1] / result["stdout"]).write_text("changed")
            return result
        self.assertEqual(self.execute(run_command=run)["status"], "failed")

    def test_binary_changed_during_simulation_is_rejected(self):
        changed = [False]
        def run(*args, **kwargs):
            result = self.fake_run(*args, **kwargs)
            if result["name"].endswith("-hello"):
                changed[0] = True
            return result
        def capture(root, path, **kwargs):
            result = self.fake_capture(root, path, **kwargs)
            if Path(path).name == "hello.riscv" and changed[0]:
                result["sha256"] = "0" * 64
            return result
        self.assertEqual(self.execute(run_command=run, capture_file=capture)["status"], "failed")

    def test_simulator_changed_during_simulation_is_rejected(self):
        changed = [False]
        def run(*args, **kwargs):
            result = self.fake_run(*args, **kwargs)
            if result["name"].endswith("-hello"):
                changed[0] = True
            return result
        def capture(root, path, **kwargs):
            result = self.fake_capture(root, path, **kwargs)
            if kwargs.get("kind") == "simulator" and changed[0]:
                result["sha256"] = "0" * 64
            return result
        self.assertEqual(self.execute(run_command=run, capture_file=capture)["status"], "failed")

    def test_second_profile_must_use_same_workload_binary_hashes(self):
        changed = [False]
        def run(*args, **kwargs):
            result = self.fake_run(*args, **kwargs)
            if result["name"] == "NovaM1BaselineConfig-build":
                changed[0] = True
            return result
        def capture(root, path, **kwargs):
            result = self.fake_capture(root, path, **kwargs)
            if Path(path).name == "hello.riscv" and changed[0]:
                result["sha256"] = "0" * 64
            return result
        record = self.execute(run_command=run, capture_file=capture)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["profiles"][1]["workloads"][0]["stage"]["status"], "not_run")

    def test_source_or_lock_drift_after_observations_fails_campaign(self):
        calls = [0]
        def source(root):
            calls[0] += 1
            snapshot = copy.deepcopy(self.source)
            if calls[0] > 1:
                snapshot["clean"] = False
            return snapshot
        self.assertEqual(self.execute(capture_source=source)["status"], "failed")

    def test_tool_provenance_drift_after_observations_fails_campaign(self):
        calls = [0]
        def provenance(root):
            calls[0] += 1
            snapshot = copy.deepcopy(self.provenance)
            if calls[0] > 1:
                snapshot["tool_versions"]["verilator"] = "different"
            return snapshot
        self.assertEqual(self.execute(collect_provenance=provenance)["status"], "failed")

    def test_runtime_collateral_drift_is_detected_with_unchanged_legacy_versions(self):
        calls = [0]
        def profile(root, env=None):
            calls[0] += 1
            result = copy.deepcopy(self.profile)
            result["collateral"] = {"fesvr_library": {"sha256": str(calls[0]) * 64}}
            return result
        record = self.execute(inspect_profile=profile)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["provenance_before"], record["provenance_after"])
        self.assertNotEqual(record["profile_after"], record["preflight"]["profile"])
        self.assertEqual(record["inventory_after"], record["inventory"])

    def test_installed_metadata_drift_is_detected_with_unchanged_legacy_versions(self):
        calls = [0]
        def inventory(lock, prefix):
            calls[0] += 1
            result = copy.deepcopy(self.inventory)
            result["matching_package_count"] = 165 if calls[0] == 1 else 164
            return result
        record = self.execute(inspect_inventory=inventory)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["provenance_before"], record["provenance_after"])
        self.assertNotEqual(record["inventory_after"], record["inventory"])

    def test_rejected_overrides_do_not_trigger_post_profile_or_inventory_probes(self):
        self.env["JAVA_TOOL_OPTIONS"] = "forbidden"
        def forbidden(*args, **kwargs):
            raise AssertionError("unsafe environment was probed")
        record = self.execute(inspect_profile=forbidden, inspect_inventory=forbidden,
                              collect_provenance=forbidden)
        self.assertEqual(record["status"], "blocked")
        self.assertIsNone(record["profile_after"])
        self.assertIsNone(record["inventory_after"])

    def test_aggregate_budget_caps_each_stage_and_blocks_remaining_work(self):
        clock = [0.0]
        self.args.total_timeout_seconds = 300
        def run(*args, **kwargs):
            result = self.fake_run(*args, **kwargs)
            if result["name"] == "hello-configure":
                clock[0] = 295.0
            return result
        with patch.object(campaign.time, "monotonic", side_effect=lambda: clock[0]):
            record = self.execute(run_command=run)
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(len(self.commands), 2)
        self.assertTrue(all(call["timeout_seconds"] <= 290 for call in self.commands))
        self.assertIn("aggregate", record["reasons"][0])

    def test_final_evidence_time_cannot_silently_overrun_aggregate_budget(self):
        clock = [0.0]
        self.args.total_timeout_seconds = 300
        def run(*args, **kwargs):
            result = self.fake_run(*args, **kwargs)
            if result["name"] == "NovaM1BaselineConfig-rv64mi-p-scall":
                clock[0] = 301.0
            return result
        with patch.object(campaign.time, "monotonic", side_effect=lambda: clock[0]):
            record = self.execute(run_command=run)
        self.assertEqual(record["status"], "blocked")
        self.assertIn("deadline exceeded", record["reasons"][-1])

    def test_interrupt_retains_blocked_record(self):
        def run(*args, **kwargs):
            raise KeyboardInterrupt()
        record = self.execute(run_command=run)
        self.assertEqual(record["status"], "blocked")
        self.assertIn("interrupted", record["reasons"][0])

    def test_nested_engine_signal_result_stops_and_retains_actual_exit(self):
        def run(*args, **kwargs):
            result = self.fake_run(*args, **kwargs)
            if result["name"] == "hello-build":
                result.update(status="blocked", interrupted=True, interruption_signal=signal.SIGTERM,
                              exit_code=-15, reason="command execution interrupted")
            return result
        record = self.execute(run_command=run)
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(record["common_stages"][-1]["exit_code"], -15)
        self.assertTrue(record["common_stages"][-1]["interrupted"])
        self.assertEqual(len(self.commands), 3)

    def test_sigterm_during_preflight_is_latched_and_handlers_are_restored(self):
        previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
        def profile(root, env=None):
            os.kill(os.getpid(), signal.SIGTERM)
            os.kill(os.getpid(), signal.SIGTERM)
            return copy.deepcopy(self.profile)
        record = self.execute(inspect_profile=profile)
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(self.commands, [])
        self.assertTrue(any("SIGTERM" in reason for reason in record["reasons"]))
        self.assertEqual(previous, {number: signal.getsignal(number) for number in previous})

    def test_sigterm_during_finalization_cannot_preserve_observed_status(self):
        calls = [0]
        def source(root):
            calls[0] += 1
            if calls[0] == 2:
                os.kill(os.getpid(), signal.SIGTERM)
            return copy.deepcopy(self.source)
        record = self.execute(capture_source=source)
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(len(self.commands), 37)
        self.assertTrue(any("SIGTERM" in reason for reason in record["reasons"]))

    def test_signal_during_record_write_rewrites_same_exclusive_record_as_blocked(self):
        original = campaign.json.dump
        calls = [0]
        def dump(*args, **kwargs):
            original(*args, **kwargs)
            calls[0] += 1
            if calls[0] == 1:
                os.kill(os.getpid(), signal.SIGTERM)
        with patch.object(campaign.json, "dump", side_effect=dump):
            record = self.execute()
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(calls[0], 2)

    def test_nonmain_thread_execution_blocks_before_output(self):
        errors = []
        def run():
            try:
                campaign.execute(self.root, self.args, env=self.env)
            except ValueError as exc:
                errors.append(str(exc))
        thread = threading.Thread(target=run)
        thread.start()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIn("main thread", errors[0])
        self.assertFalse((self.root / "nova-out").exists())

    def test_bad_manifest_execute_attempt_retains_explicit_incomplete_record(self):
        (self.root / "nova/g1-workloads.json").write_text("{}")
        record = self.execute()
        self.assertEqual(record["status"], "blocked")
        self.assertIsNone(record["plan_sha256"])
        self.assertEqual(record["profiles"], [])
        self.assertEqual(self.commands, [])

    def test_output_symlink_is_rejected_without_writing_external_target(self):
        external = self.root / "outside"
        external.mkdir()
        (self.root / "nova-out").symlink_to(external, target_is_directory=True)
        with patch.object(campaign, "ROOT", self.root), self.assertRaises(ValueError):
            campaign.execute(self.root, self.args, env=self.env)
        self.assertEqual(list(external.iterdir()), [])
