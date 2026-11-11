"""Offline evidence-contract tests for the optional Rocket smoke runner.

The simulated stages below never build or run a CPU.  They check that a later
real attempt can be recorded without confusing it with G1 gate acceptance.
"""

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "nova_rocket_provenance_target",
    Path(__file__).resolve().parents[2] / "scripts/nova/rocket_baseline.py",
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def budget():
    return SimpleNamespace(jobs=2, java_heap="4G", build_timeout=7200,
                           test_timeout=300, total_timeout=7200, min_free_gib=10)


def minimal_riscv64_elf(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4] = 2
    header[5] = 1
    header[6] = 1
    header[18:20] = (243).to_bytes(2, "little")
    path.write_bytes(header)


def expected_provenance():
    return {
        "host": {"architecture": "x86_64", "glibc": "2.41"},
        "tool_versions": {"verilator": "Verilator 5.022", "cmake": "cmake 3.30"},
        "lock_hashes": {"conda-reqs/chipyard-base.yaml": {
            "sha256": "a" * 64, "matches_imported_blob": True}},
        "submodules": [{"path": "generators/rocket-chip", "pin": "b" * 40,
                        "state": "at_pin", "required": True}],
        "capture_complete": True,
        "limitations": ["Mock values are for test fixtures only."],
    }


class RocketProvenanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = self.root / "run"
        self.output.mkdir()

    def fake_stage(self, *, marker=True):
        def stage(root, output, name, seconds, argv, min_free_gib=None):
            log = output / (name + ".log")
            payload = (b"Hello world from core 0, a Rocket\n"
                       if name == "hello-simulate" and marker else b"fixture stage\n")
            log.write_bytes(payload)
            return {"stage": name, "exit_code": 0, "status": "passed",
                    "log": log.name, "log_sha256": hashlib.sha256(payload).hexdigest()}
        return stage

    def execute_fixture(self, *, marker=True):
        minimal_riscv64_elf(self.root / "tests/build/hello.riscv")
        with patch.object(runner, "validate_execution", return_value=("c" * 40, None)), \
             patch.object(runner, "make_output_dir", return_value=self.output), \
             patch.object(runner, "collect_provenance", return_value=expected_provenance()), \
             patch.object(runner.shutil, "disk_usage",
                          return_value=SimpleNamespace(free=64 * 1024 ** 3)), \
             patch.object(runner, "run_stage", side_effect=self.fake_stage(marker=marker)), \
             contextlib.redirect_stdout(io.StringIO()):
            exit_code = runner.execute(self.root, budget(),
                                       runner.stages(self.root, 2, "4G", 7200, 300))
        record = json.loads((self.output / "record.json").read_text(encoding="utf-8"))
        return exit_code, record

    def test_completed_smoke_keeps_partial_test_scope_and_gate_closed(self):
        exit_code, record = self.execute_fixture()
        self.assertEqual(exit_code, 0)
        self.assertEqual(record["status"], "hello_marker_observed_unqualified")
        self.assertEqual(record["evidence_scope"], {
            "gate": "G1", "requirements": ["REQ-BUILD-001"],
            "tests": ["T-BUILD-001"], "qualification": "partial_smoke_only",
        })
        self.assertFalse(record["g1_gate_passed"])
        self.assertFalse(record["hardware_qualified"])
        self.assertEqual(record["revision"], "c" * 40)

    def test_record_captures_provenance_and_target_observations(self):
        _, record = self.execute_fixture()
        self.assertEqual(record["provenance"], expected_provenance())
        self.assertIn("Hello world from core 0", record["observations"]["expected_hello_marker"])
        self.assertTrue(record["observations"]["hello_marker_observed"])
        self.assertTrue(record["observations"]["riscv64_elf_verified"])
        self.assertIs(record["observations"]["target_completion_verified"], False)
        self.assertEqual(len(record["stages"]), 4)
        self.assertEqual(record["hello_binary_sha256"],
                         runner.digest(self.root / "tests/build/hello.riscv"))

    def test_absent_real_output_fails_even_with_provenance_and_zero_exits(self):
        exit_code, record = self.execute_fixture(marker=False)
        self.assertEqual(exit_code, 1)
        self.assertEqual(record["status"], "failed")
        self.assertFalse(record["observations"]["hello_marker_observed"])
        self.assertFalse(record["g1_gate_passed"])
        self.assertFalse(record["hardware_qualified"])

    def test_collect_provenance_filters_unknown_secret_fields(self):
        marker = "FAKE_SECRET_MUST_NOT_APPEAR_IN_EVIDENCE"
        preflight = {
            "host_glibc": "2.41", "pinned_sysroot": "2.34",
            "setup_selected_sysroot": "2.39", "unsafe_upstream_setup": True,
            "lock_hashes": {"conda-reqs/chipyard-base.yaml": {
                "sha256": "a" * 64, "matches_imported_blob": True}},
            "resources": {"logical_cpus": 2, "ram_bytes": 8 * 1024 ** 3},
            "secret_field": marker,
        }
        doctor = {
            "tools": [{"name": "verilator", "version": "Verilator 5.022", "available": True}],
            "submodules": [{"path": "generators/rocket-chip", "pin": "b" * 40,
                            "state": "at_pin", "required": True}],
            "secret_field": marker,
        }
        reports = [SimpleNamespace(returncode=0, stdout=json.dumps(preflight)),
                   SimpleNamespace(returncode=0, stdout=json.dumps(doctor))]
        with patch.object(runner, "command", side_effect=reports) as commands:
            provenance = runner.collect_provenance(self.root)
        self.assertEqual(commands.call_count, 2)
        self.assertIn("lock_hashes", provenance)
        self.assertIn("submodules", provenance)
        self.assertIs(provenance["toolchain_versions_verified"], False)
        self.assertFalse(provenance["capture_complete"])
        self.assertNotIn(marker, json.dumps(provenance))

    def test_six_observed_tools_do_not_prove_pinned_version_match(self):
        """Complete metadata capture is distinct from toolchain qualification."""
        names = ("java", "verilator", "firtool", "make", "cmake",
                 "riscv64-unknown-elf-gcc")
        preflight = {"lock_hashes": {
            f"conda-reqs/example-{index}.yaml": {
                "sha256": "a" * 64, "matches_imported_blob": True,
            } for index in range(9)
        }}
        doctor = {
            "tools": [{"name": name, "version": f"{name} 1.0", "available": True}
                      for name in names],
            "submodules": [{"path": "generators/rocket-chip", "pin": "b" * 40,
                            "state": "at_pin", "required": True}],
        }
        reports = [SimpleNamespace(returncode=0, stdout=json.dumps(preflight)),
                   SimpleNamespace(returncode=0, stdout=json.dumps(doctor))]
        with patch.object(runner, "command", side_effect=reports):
            provenance = runner.collect_provenance(self.root)
        self.assertTrue(provenance["capture_complete"])
        self.assertIs(provenance["toolchain_versions_verified"], False)
        self.assertTrue(any("not matched" in item for item in provenance["limitations"]))

    def test_unreadable_evidence_source_does_not_look_complete(self):
        reports = [SimpleNamespace(returncode=0, stdout="{not json"), None]
        with patch.object(runner, "command", side_effect=reports):
            provenance = runner.collect_provenance(self.root)
        self.assertFalse(provenance["capture_complete"])
        self.assertTrue(provenance["limitations"])
        self.assertNotIn("Traceback", json.dumps(provenance))


if __name__ == "__main__":
    unittest.main()
