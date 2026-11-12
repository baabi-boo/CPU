#!/usr/bin/env python3
"""Describe the fixed G1 workload campaign without executing or installing it.

This module validates a declared, narrow workload set and produces argv lists.
A plan, a test name, and a source pin are not processor-execution evidence.
The caller must independently verify the prepared environment, executable and
workload hashes, separate output streams, completion, and clean reproduction.
"""

import argparse
import copy
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys


ROOT = Path(__file__).resolve().parents[2]
CONFIGURATIONS = ("RocketConfig", "NovaM1BaselineConfig")
ISA_TESTS = (
    "rv64ui-p-simple", "rv64ui-p-add", "rv64ui-p-sub", "rv64ui-p-beq",
    "rv64ui-p-jalr", "rv64ui-p-ld", "rv64ui-p-sd", "rv64um-p-mul",
    "rv64um-p-div", "rv64mi-p-csr", "rv64mi-p-illegal", "rv64mi-p-scall",
)
ISA_BINARY_DIRECTORY = "riscv64-unknown-elf/share/riscv-tests/isa"
EXCLUSIONS = (
    "F", "D", "A", "C", "MMU", "full-ISA-certification",
    "per-instruction-differential-checking", "heterogeneous-execution",
)
SOURCE_PATHS = (
    "generators/rocket-chip", "generators/testchipip",
    "toolchains/riscv-tools/riscv-tests", "toolchains/riscv-tools/riscv-isa-sim",
)
SMOKE_WORKLOADS = (
    {
        "id": "hello", "binary": "tests/build/hello.riscv",
        "expected_target_exit": 0, "expected_marker": None,
        "output_contract": "inherited-hello-line-and-completion-protocol",
    },
    {
        "id": "nova-baseline",
        "binary": "software/nova/baseline/build/nova-baseline.riscv",
        "expected_target_exit": 0,
        "expected_marker": "NOVA_BASELINE_V1 PASS hart=0 checks=8",
        "output_contract": "exact-line-and-completion-protocol",
    },
    {
        "id": "nova-baseline-fail",
        "binary": "software/nova/baseline/build/nova-baseline-fail.riscv",
        "expected_target_exit": 7,
        "expected_marker": "NOVA_BASELINE_V1 EXPECTED_FAIL hart=0 code=7",
        "output_contract": "exact-line-and-expected-target-failure",
    },
)
MANIFEST_KEYS = {
    "schema_version", "campaign", "configurations", "source_provenance",
    "smoke_workloads", "isa_tests", "isa_binary_directory", "reference",
    "exclusions", "full_isa_certification", "missing_workload_policy",
    "reproduction",
}
MAX_JSON_BYTES = 128 * 1024
SHA1 = re.compile(r"[0-9a-f]{40}\Z")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("non-finite JSON number")


def _read_json(path):
    """Read a bounded regular input, refusing a symlink/FIFO leaf."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_JSON_BYTES:
                raise ValueError("JSON input is not a bounded regular file")
            data = stream.read(MAX_JSON_BYTES + 1)
        if len(data) > MAX_JSON_BYTES:
            raise ValueError("JSON input exceeds size limit")
        return json.loads(data.decode("utf-8"), object_pairs_hook=_object,
                          parse_constant=_invalid_constant)
    except (OSError, UnicodeError, RecursionError) as exc:
        raise ValueError("JSON input cannot be safely read") from exc


def _absolute_path(value, label):
    text = os.fspath(value)
    if (not isinstance(text, str) or not text or len(text) > 4096
            or any(ord(char) < 32 or ord(char) == 127 for char in text)
            or "\\" in text):
        raise ValueError(label + " is not a safe absolute path")
    path = PurePosixPath(text)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(label + " must be absolute without traversal")
    return Path(path)


def _bounded_integer(value, lower, upper, label):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(label + " is outside its fixed bounded range")


def _repository_input(root, relative):
    """Confine repository-owned declarations before reading their contents."""
    path = root / relative
    try:
        if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
            raise ValueError("repository declaration escapes its checkout")
    except (OSError, RuntimeError) as exc:
        raise ValueError("repository declaration cannot be safely resolved") from exc
    return path


def load_workloads(path):
    """Load the exact reviewed workload contract; never silently skip a test.

    A revised workload scope requires an intentional code/manifest review.
    Unknown fields, reordered/duplicated tests, and optimistic qualification
    flags are rejected rather than being interpreted as compatible variants.
    """
    data = _read_json(path)
    if not isinstance(data, dict) or set(data) != MANIFEST_KEYS:
        raise ValueError("unexpected workload manifest structure")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("unsupported workload manifest version")
    required = {
        "campaign": "g1-single-core",
        "configurations": list(CONFIGURATIONS),
        "smoke_workloads": list(SMOKE_WORKLOADS),
        "isa_tests": list(ISA_TESTS),
        "isa_binary_directory": ISA_BINARY_DIRECTORY,
        "reference": {
            "model": "Spike", "source_gitlink": SOURCE_PATHS[-1],
            "comparison_scope": "unresolved", "qualified": False,
        },
        "exclusions": list(EXCLUSIONS),
        "missing_workload_policy": "block-no-skips",
        "reproduction": {
            "required_clean_builds": 2,
            "shared_generated_artifacts_allowed": False,
            "automatic_gate_acceptance": False,
        },
    }
    for key, expected in required.items():
        if data[key] != expected:
            raise ValueError("workload contract differs for " + key)
    if data["full_isa_certification"] is not False:
        raise ValueError("a workload plan cannot certify an ISA")
    # JSON booleans compare equal to integers; do not permit them in exits/counts.
    if any(type(item["expected_target_exit"]) is not int
           for item in data["smoke_workloads"]):
        raise ValueError("target exit values must be integers")
    reproduction = data["reproduction"]
    if (type(reproduction["required_clean_builds"]) is not int
            or reproduction["shared_generated_artifacts_allowed"] is not False
            or reproduction["automatic_gate_acceptance"] is not False
            or data["reference"]["qualified"] is not False):
        raise ValueError("invalid qualification or reproduction flags")
    source = data["source_provenance"]
    if (not isinstance(source, dict)
            or set(source) != {"chipyard_commit", "gitlinks"}
            or not isinstance(source["chipyard_commit"], str)
            or not SHA1.fullmatch(source["chipyard_commit"])
            or not isinstance(source["gitlinks"], dict)
            or set(source["gitlinks"]) != set(SOURCE_PATHS)
            or any(not isinstance(pin, str) or not SHA1.fullmatch(pin)
                   for pin in source["gitlinks"].values())):
        raise ValueError("invalid workload source provenance")
    return data


def _verify_source_provenance(root, source):
    lock = _read_json(_repository_input(root, "nova/upstream-lock.json"))
    if not isinstance(lock, dict) or not isinstance(lock.get("upstream"), dict):
        raise ValueError("upstream provenance is unavailable")
    if lock["upstream"].get("commit") != source["chipyard_commit"]:
        raise ValueError("workload Chipyard revision differs from upstream lock")
    modules = lock.get("submodules")
    if not isinstance(modules, list):
        raise ValueError("upstream gitlink provenance is unavailable")
    pins = {}
    for row in modules:
        if (not isinstance(row, dict) or not isinstance(row.get("path"), str)
                or row["path"] in pins or not isinstance(row.get("commit"), str)
                or not SHA1.fullmatch(row["commit"])):
            raise ValueError("invalid or duplicate upstream gitlink")
        pins[row["path"]] = row["commit"]
    if any(pins.get(path) != pin for path, pin in source["gitlinks"].items()):
        raise ValueError("workload source pins differ from upstream lock")


def simulator_argv(root, config, binary, max_cycles=10000000, seed=1):
    """Return direct pinned-profile simulator argv, never a shell command.

    This does not claim that either executable exists or is trustworthy. The
    execution layer must validate its path, ELF identity, hashes and source
    provenance. In particular, an external ISA binary needs prefix containment.
    """
    root = _absolute_path(root, "root")
    binary = _absolute_path(binary, "binary")
    if config not in CONFIGURATIONS:
        raise ValueError("unsupported G1 configuration")
    _bounded_integer(max_cycles, 1, 10000000, "max_cycles")
    _bounded_integer(seed, 1, 2147483647, "seed")
    return [
        str(root / "sims/verilator" / ("simulator-chipyard.harness-" + config)),
        "+permissive", "+dramsim",
        "+dramsim_ini_dir=" + str(root / "generators/testchipip/src/main/resources/dramsim2_ini"),
        "+max-cycles=" + str(max_cycles), "+verbose",
        "+verilator+seed+" + str(seed), "+permissive-off", str(binary),
    ]


def build_plan(root, jobs=2, java_heap="4G"):
    """Return a read-only plan for one clean campaign, repeated separately twice.

    ISA binary paths remain relative to a separately verified RISCV prefix. No
    environment variable is read or expanded here, and no setup/build runs.
    """
    root = _absolute_path(root, "root")
    _bounded_integer(jobs, 1, 2, "jobs")
    if not isinstance(java_heap, str) or not re.fullmatch(r"[1-8]G", java_heap):
        raise ValueError("java_heap must be 1G..8G")
    manifest = load_workloads(_repository_input(root, "nova/g1-workloads.json"))
    _verify_source_provenance(root, manifest["source_provenance"])
    hello_build = str(root / "tests/build")
    target_build = str(root / "software/nova/baseline/build")
    common_build = [
        {
            "id": "hello-configure", "timeout_seconds": 600,
            "argv": ["cmake", "-S", str(root / "tests"), "-B", hello_build,
                     "-DCMAKE_SYSTEM_NAME=Generic",
                     "-DCMAKE_C_COMPILER=riscv64-unknown-elf-gcc",
                     "-DCMAKE_CXX_COMPILER=riscv64-unknown-elf-g++",
                     "-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY"],
        },
        {
            "id": "hello-build", "timeout_seconds": 600,
            "argv": ["cmake", "--build", hello_build, "--target", "hello",
                     "--parallel", str(jobs)],
        },
        {
            "id": "nova-target-configure", "timeout_seconds": 600,
            "argv": ["cmake", "-S", str(root / "software/nova/baseline"),
                     "-B", target_build,
                     "-DCMAKE_C_COMPILER=riscv64-unknown-elf-gcc",
                     "-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY"],
        },
        {
            "id": "nova-target-build", "timeout_seconds": 600,
            "argv": ["cmake", "--build", target_build, "--target",
                     "nova-baseline", "nova-baseline-fail", "--parallel", str(jobs)],
        },
    ]
    workloads = []
    for item in manifest["smoke_workloads"]:
        workloads.append({"kind": "smoke", "binary_origin": "repository", **item})
    for name in manifest["isa_tests"]:
        workloads.append({
            "id": name, "kind": "isa", "binary_origin": "riscv_prefix",
            "binary": ISA_BINARY_DIRECTORY + "/" + name,
            "expected_target_exit": 0, "expected_marker": None,
            "output_contract": "completion-protocol",
        })
    profiles = []
    for config in CONFIGURATIONS:
        profiles.append({
            "configuration": config,
            "build": {
                "id": config + "-build", "timeout_seconds": 7200,
                "argv": ["make", "-C", str(root / "sims/verilator"),
                         "CONFIG=" + config, "JAVA_HEAP_SIZE=" + java_heap,
                         "-j" + str(jobs)],
            },
            "simulator": str(root / "sims/verilator" / ("simulator-chipyard.harness-" + config)),
            "simulation_cwd": str(root / "sims/verilator"),
            "simulation_limits": {"max_cycles": 10000000, "seed": 1, "timeout_seconds": 300},
            "workloads": copy.deepcopy(workloads),
        })
    return {
        "schema_version": 1, "scope": "G1 declared single-core workload plan only",
        "hardware_qualified": False, "g1_gate_passed": False,
        "does_not_provision_toolchain_or_initialize_submodules": True,
        "build_dependency_resolution": "may_access_network",
        "execute_requires_approved_budget": True,
        "source_must_be_clean": True,
        "source_provenance": copy.deepcopy(manifest["source_provenance"]),
        "common_build_stages": common_build,
        "profiles": profiles,
        "reference": copy.deepcopy(manifest["reference"]),
        "exclusions": list(manifest["exclusions"]),
        "reproduction": copy.deepcopy(manifest["reproduction"]),
        "missing_workload_policy": "block-no-skips",
        "notes": [
            "Build tools may resolve JVM dependencies; this runner is not an offline dependency closure.",
            "Each simulator is built separately; a second clean checkout must repeat the whole campaign.",
            "Timeouts are per-stage upper bounds, not an approved aggregate execution budget.",
            "Never expand a missing ISA binary to an empty wildcard or skip it.",
            "Keep simulator stdout and stderr separate and verify the pinned completion protocol.",
            "The negative workload requires its expected target exit, not an arbitrary crash or timeout.",
            "Reference comparison remains unresolved; this plan cannot close T-ISA-001 or G1.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--java-heap", default="4G")
    args = parser.parse_args(argv)
    try:
        plan = build_plan(args.root, jobs=args.jobs, java_heap=args.java_heap)
    except (ValueError, TypeError) as exc:
        print("Blocked: " + str(exc), file=sys.stderr)
        return 2
    # The CLI has no need to disclose the caller's absolute checkout path.
    serialized = json.dumps(plan, sort_keys=True, indent=2)
    escaped_root = json.dumps(str(_absolute_path(args.root, "root")))[1:-1]
    print(serialized.replace(escaped_root, "<repo>"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
