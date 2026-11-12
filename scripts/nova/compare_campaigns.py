#!/usr/bin/env python3
"""Compare recorded G1 identities without executing or qualifying hardware.

A consistent result means agreement between unauthenticated JSON records, not
proof of independent builds, trustworthy logs, or hardware correctness.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat


MAX_RECORD_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024
MAX_PROFILE_BYTES = 2 * 1024 * 1024 * 1024
MAX_PROFILE_FILES = 8192
MAX_JSON_NODES = 100000
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
CONFIGURATIONS = ("RocketConfig", "NovaM1BaselineConfig")
WORKLOAD_IDS = (
    "hello", "nova-baseline", "nova-baseline-fail", "rv64ui-p-simple",
    "rv64ui-p-add", "rv64ui-p-sub", "rv64ui-p-beq", "rv64ui-p-jalr",
    "rv64ui-p-ld", "rv64ui-p-sd", "rv64um-p-mul", "rv64um-p-div",
    "rv64mi-p-csr", "rv64mi-p-illegal", "rv64mi-p-scall",
)
COMMON_STAGES = (
    "hello-configure", "hello-build", "nova-target-configure", "nova-target-build",
)
CONDA_INPUTS = frozenset({
    "conda-reqs/chipyard-base.yaml", "conda-reqs/chipyard-extended.yaml",
    "conda-reqs/circt.json", "conda-reqs/docs.yaml", "conda-reqs/riscv-tools.yaml",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-64-lean.conda-lock.yml",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-64.conda-lock.yml",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-aarch64-lean.conda-lock.yml",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-aarch64.conda-lock.yml",
})
SOURCE_INPUTS = frozenset({
    "build.sbt", "project/build.properties", "project/plugins.sbt", "variables.mk",
    "common.mk", "sims/verilator/Makefile", "sims/common-sim-flags.mk",
    "generators/chipyard/src/main/scala/config/NovaM1Configs.scala",
    "nova/upstream-lock.json", "nova/g1-profile.json", "nova/g1-workloads.json",
})
CLAIM_FLAGS = {
    "hardware_qualified", "g1_gate_passed", "reference_comparison_qualified",
    "full_isa_certification", "toolchain_versions_verified",
    "installed_binary_contents_verified", "lock_origin_verified",
    "target_completion_verified",
    "closure_qualified",
}
REQUIRED_FIELDS = {
    "schema_version", "kind", "status", "source_before", "source_after",
    "plan_sha256", "profile_sha256", "workloads_sha256", "provenance_before",
    "provenance_after", "inventory", "resource_limits", "common_stages", "profiles",
    "started_utc", "finished_utc", "hardware_qualified", "g1_gate_passed",
    "reference_comparison", "limitations", "declared_plan", "execution_paths",
    "elapsed_seconds", "preflight", "reasons", "profile_after", "inventory_after",
}
LIMITATIONS = [
    "Consistent means recorded input and retained artifact identities agree, not actual reproduction.",
    "Record JSON, logs, claimed execution, and hashes are not authenticated by this comparison.",
    "Distinct checkout identifiers do not prove independent builds or absence of shared caches.",
    "Reference comparison remains not_run; no reference-model or hardware qualification is awarded.",
    "Build log hashes may differ; diagnostics are not proof of execution.",
    "Observed TestDriver completion protocol is not independent attestation of the target exit.",
]


class RecordError(ValueError):
    """A record cannot safely participate in an identity comparison."""


def _hash(value, pattern=SHA256):
    return type(value) is str and pattern.fullmatch(value) is not None


def _relative(value, basename=False):
    if (type(value) is not str or not value or len(value) > 4096
            or "\\" in value or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        return False
    path = PurePosixPath(value)
    return (bool(path.parts) and not path.is_absolute() and ".." not in path.parts
            and path.as_posix() == value and (not basename or len(path.parts) == 1))


def _canonical(value):
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > 32 or count > MAX_JSON_NODES:
            raise RecordError("record exceeds JSON complexity bounds")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise RecordError("record contains a non-string object key")
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is float:
            if not math.isfinite(item):
                raise RecordError("record contains a non-finite number")
        elif item is not None and type(item) not in (str, int, bool):
            raise RecordError("record contains a non-JSON value")
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False, ensure_ascii=True).encode("ascii")
    except (ValueError, TypeError, RecursionError) as exc:
        raise RecordError("record cannot be canonically encoded") from exc
    if len(encoded) > MAX_RECORD_BYTES:
        raise RecordError("record exceeds size bound")
    return encoded


def _claims(value):
    if type(value) is dict:
        for key, child in value.items():
            if key in CLAIM_FLAGS and child is not False:
                return False
            if not _claims(child):
                return False
    elif type(value) is list:
        return all(_claims(child) for child in value)
    return True


def _hash_map(value, count=None):
    return (type(value) is dict and bool(value) and (count is None or len(value) == count)
            and all(_relative(path) and _hash(digest) for path, digest in value.items()))


def _source(value, errors):
    required = {"revision", "tree", "clean", "checkout_identity_sha256", "lock_hashes",
                "source_inputs", "submodules", "state_digest"}
    if type(value) is not dict or not required <= value.keys():
        errors.append("source snapshot is incomplete")
        return
    if (value["clean"] is not True or not _hash(value["revision"], SHA1)
            or not _hash(value["tree"], SHA1) or not _hash(value["state_digest"])
            or not _hash(value["checkout_identity_sha256"])):
        errors.append("source snapshot lacks clean, canonical identities")
    if not _hash_map(value["lock_hashes"], 9) or set(value["lock_hashes"]) != CONDA_INPUTS:
        errors.append("source snapshot must retain all nine Conda input hashes")
    if not _hash_map(value["source_inputs"]) or set(value["source_inputs"]) != SOURCE_INPUTS:
        errors.append("source input hashes are incomplete or malformed")
    rows = value["submodules"]
    if type(rows) is not list or len(rows) < 57:
        errors.append("source snapshot must retain all root gitlinks")
        return
    seen = set()
    for row in rows:
        if (type(row) is not dict or not _relative(row.get("path"))
                or row["path"] in seen or not _hash(row.get("pin"), SHA1)
                or type(row.get("initialized")) is not bool):
            errors.append("source gitlink row is invalid or duplicated")
            continue
        seen.add(row["path"])
        if row["initialized"]:
            if (row.get("revision") != row["pin"] or row.get("clean") is not True
                    or row.get("state") != "at_pin"):
                errors.append("initialized gitlink differs from its clean pinned source")
        elif (row.get("revision") is not None or row.get("clean") is not None
              or row.get("state") != "uninitialized"):
            errors.append("uninitialized gitlink state is inconsistent")


def _time(value):
    if (type(value) is not str or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value)):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _absolute(value):
    if (type(value) is not str or not value or len(value) > 4096
            or "\\" in value or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        return False
    path = PurePosixPath(value)
    return (path.is_absolute() and value != "/" and not value.startswith("//")
            and ".." not in path.parts and path.as_posix() == value
            and not any(token in value for token in ("<repo>", "<riscv>", "<python>")))


def _paths(value, errors):
    if (type(value) is not dict or set(value) != {"repository", "riscv_prefix", "python"}
            or not all(_absolute(item) for item in value.values())
            or len(set(value.values())) != 3):
        errors.append("execution path aliases are missing, unsafe, or ambiguous")
        return None
    return value


def _command(command, paths):
    """Normalize only complete path tokens or a path value following '='.

    This is identity normalization, not filesystem resolution or execution
    attestation. Literal alias tokens in raw argv are rejected rather than
    accidentally treated as paths that were actually invoked.
    """
    if (paths is None or type(command) is not list or not command
            or any(type(item) is not str or not item for item in command)):
        raise RecordError("stage command cannot be normalized")
    aliases = sorted(((paths["repository"], "<repo>"),
                      (paths["riscv_prefix"], "<riscv>")), reverse=True, key=lambda item: len(item[0]))
    result = []
    for argument in command:
        if any(token in argument for token in ("<repo>", "<riscv>", "<python>")):
            raise RecordError("raw command contains a placeholder instead of an executed path")
        if argument == paths["python"]:
            result.append("<python>")
            continue
        head, separator, value = argument.partition("=")
        path_value = value if separator else argument
        for prefix, alias in aliases:
            if path_value == prefix or path_value.startswith(prefix + "/"):
                path_value = alias + path_value[len(prefix):]
                break
        result.append(head + separator + path_value if separator else path_value)
    return result


def _workload(identifier):
    if identifier == "hello":
        return {"id": identifier, "kind": "smoke", "binary_origin": "repository",
                "binary": "tests/build/hello.riscv", "expected_target_exit": 0,
                "expected_marker": None, "output_contract": "inherited-hello-line-and-completion-protocol"}
    if identifier in ("nova-baseline", "nova-baseline-fail"):
        negative = identifier.endswith("-fail")
        return {"id": identifier, "kind": "smoke", "binary_origin": "repository",
                "binary": "software/nova/baseline/build/" + identifier + ".riscv",
                "expected_target_exit": 7 if negative else 0,
                "expected_marker": ("NOVA_BASELINE_V1 EXPECTED_FAIL hart=0 code=7" if negative
                                    else "NOVA_BASELINE_V1 PASS hart=0 checks=8"),
                "output_contract": ("exact-line-and-expected-target-failure" if negative
                                    else "exact-line-and-completion-protocol")}
    return {"id": identifier, "kind": "isa", "binary_origin": "riscv_prefix",
            "binary": "riscv64-unknown-elf/share/riscv-tests/isa/" + identifier,
            "expected_target_exit": 0, "expected_marker": None,
            "output_contract": "completion-protocol"}


def _declared_commands(record, resources, errors):
    plan = record["declared_plan"]
    if type(plan) is not dict or type(resources) is not dict:
        errors.append("declared campaign plan is missing")
        return {}
    if hashlib.sha256(_canonical(plan)).hexdigest() != record["plan_sha256"]:
        errors.append("declared campaign plan does not match its recorded hash")
    if (type(plan.get("schema_version")) is not int or plan["schema_version"] != 1
            or plan.get("hardware_qualified") is not False or plan.get("g1_gate_passed") is not False
            or type(plan.get("reference")) is not dict
            or plan["reference"].get("qualified") is not False):
        errors.append("declared campaign plan has an unsupported schema or claim")
    jobs, heap = resources.get("jobs"), resources.get("java_heap")
    cycles, seed = resources.get("max_cycles"), resources.get("seed")
    commands = {"pinned-input-check": (["<python>", "-B", "scripts/nova/check.py"], 120)}
    common = [
        ["cmake", "-S", "<repo>/tests", "-B", "<repo>/tests/build",
         "-DCMAKE_SYSTEM_NAME=Generic", "-DCMAKE_C_COMPILER=riscv64-unknown-elf-gcc",
         "-DCMAKE_CXX_COMPILER=riscv64-unknown-elf-g++", "-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY"],
        ["cmake", "--build", "<repo>/tests/build", "--target", "hello", "--parallel", str(jobs)],
        ["cmake", "-S", "<repo>/software/nova/baseline", "-B", "<repo>/software/nova/baseline/build",
         "-DCMAKE_C_COMPILER=riscv64-unknown-elf-gcc", "-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY"],
        ["cmake", "--build", "<repo>/software/nova/baseline/build", "--target",
         "nova-baseline", "nova-baseline-fail", "--parallel", str(jobs)],
    ]
    declared_common = plan.get("common_build_stages")
    expected_common = [{"id": name, "timeout_seconds": 600, "argv": argv}
                       for name, argv in zip(COMMON_STAGES, common)]
    if declared_common != expected_common:
        errors.append("declared common build commands differ from the fixed campaign")
    for name, argv in zip(COMMON_STAGES, common):
        commands[name] = (argv, 600)
    profiles = plan.get("profiles")
    if (type(profiles) is not list or len(profiles) != 2
            or any(type(item) is not dict for item in profiles)
            or tuple(item.get("configuration") for item in profiles) != CONFIGURATIONS):
        errors.append("declared plan must contain both ordered configurations")
        return commands
    for profile, config in zip(profiles, CONFIGURATIONS):
        build = ["make", "-C", "<repo>/sims/verilator", "CONFIG=" + config,
                 "JAVA_HEAP_SIZE=" + str(heap), "-j" + str(jobs)]
        if profile.get("build") != {"id": config + "-build", "timeout_seconds": 7200, "argv": build}:
            errors.append("declared simulator build differs from its configuration or resources")
        commands[config + "-build"] = (build, 7200)
        simulator = "<repo>/sims/verilator/simulator-chipyard.harness-" + config
        if (profile.get("simulator") != simulator or profile.get("simulation_cwd") != "<repo>/sims/verilator"
                or profile.get("simulation_limits") != {"max_cycles": cycles, "seed": seed, "timeout_seconds": 300}):
            errors.append("declared simulation paths or resource limits differ from the campaign")
        expected_workloads = [_workload(identifier) for identifier in WORKLOAD_IDS]
        if profile.get("workloads") != expected_workloads:
            errors.append("declared workload identities differ from the fixed campaign")
        for workload in expected_workloads:
            prefix = "<repo>" if workload["binary_origin"] == "repository" else "<riscv>"
            commands[config + "-" + workload["id"]] = ([
                simulator, "+permissive", "+dramsim",
                "+dramsim_ini_dir=<repo>/generators/testchipip/src/main/resources/dramsim2_ini",
                "+max-cycles=" + str(cycles), "+verbose", "+verilator+seed+" + str(seed),
                "+permissive-off", prefix + "/" + workload["binary"],
            ], 300)
    return commands


def _bind_stage(value, name, commands, paths, resources, errors):
    if type(value) is not dict or type(resources) is not dict or name not in commands:
        errors.append("stage cannot be bound to its declared command and budget")
        return
    expected, ceiling = commands[name]
    try:
        if _command(value.get("command"), paths) != expected:
            errors.append("executed command differs from its declared stage: " + name)
    except RecordError as error:
        errors.append(str(error))
    timeout = value.get("timeout_seconds")
    budget = resources.get("total_timeout_seconds")
    if (type(timeout) is not int or type(budget) is not int
            or not 1 <= timeout <= min(ceiling, budget)):
        errors.append("stage timeout is missing or exceeds its declared command budget")
    for field in ("max_log_bytes", "min_free_gib"):
        if type(value.get(field)) is not int or value.get(field) != resources.get(field):
            errors.append("stage resource metadata differs from the campaign: " + field)


def _stage(value, name, errors, negative=False):
    if type(value) is not dict:
        errors.append("stage record is missing")
        return
    code = value.get("exit_code")
    if negative:
        valid_exit = (type(code) is int and (code == -6 or 1 <= code <= 255)
                      and code not in {124, 125, 126, 127, 130, 137, 139, 143})
        valid_status = value.get("status") == "failed"
        if value.get("reason") != "command exited unsuccessfully":
            errors.append("negative workload has an infrastructure or unexplained failure")
    else:
        valid_exit = type(code) is int and code == 0
        valid_status = value.get("status") == "passed"
        if value.get("reason") not in (None, ""):
            errors.append("successful stage retains an unexplained failure reason")
    if not valid_status or not valid_exit or value.get("name") != name:
        errors.append("stage name, status, or actual exit does not match its workload expectation")
    if "id" in value and value["id"] != name:
        errors.append("stage identifier differs from its required name")
    if value.get("timed_out") is not False:
        errors.append("stage timeout state is not explicitly false")
    if value.get("interrupted", False) is not False or value.get("interruption_signal") is not None:
        errors.append("stage retains interruption evidence")
    for stream in ("stdout", "stderr"):
        if (not _relative(value.get(stream), basename=True)
                or not _hash(value.get(stream + "_sha256"))
                or type(value.get(stream + "_bytes")) is not int
                or not 0 <= value[stream + "_bytes"] <= 64 * 1024 * 1024):
            errors.append("stage stream identity or byte count is invalid")
        if (value.get(stream + "_bytes") == 0
                and value.get(stream + "_sha256") != hashlib.sha256(b"").hexdigest()):
            errors.append("empty stage log has an inconsistent hash")
    if value.get("stdout") == value.get("stderr"):
        errors.append("stdout and stderr must retain separate logs")
    start, finish = _time(value.get("started_utc")), _time(value.get("finished_utc"))
    elapsed = value.get("elapsed_seconds")
    if (start is None or finish is None or finish < start
            or type(elapsed) not in (int, float) or not 0 <= elapsed <= 7200):
        errors.append("stage timing is invalid")
    command = value.get("command")
    if (type(command) is not list or not command or any(
            type(arg) is not str or not arg or len(arg) > 4096
            or any(ord(char) < 32 or ord(char) == 127 for char in arg) for arg in command)):
        errors.append("stage command identity is missing or noncanonical")


def _artifact(value, errors, kind=None):
    if (type(value) is not dict or not _relative(value.get("path"))
            or type(value.get("size_bytes")) is not int
            or not 0 < value["size_bytes"] <= MAX_ARTIFACT_BYTES
            or not _hash(value.get("sha256")) or type(value.get("kind")) is not str
            or not value["kind"] or (kind is not None and value["kind"] != kind)):
        errors.append("artifact identity is missing or noncanonical")
        return False
    if value["kind"] in {"metadata", "device_tree"} and value["size_bytes"] > MAX_METADATA_BYTES:
        errors.append("recorded metadata exceeds its capture byte limit")
        return False
    return True


def _validate(record):
    errors = []
    if type(record) is not dict or not REQUIRED_FIELDS <= record.keys():
        return ["campaign record schema is incomplete"]
    if (type(record["schema_version"]) is not int or record["schema_version"] != 1
            or record["kind"] != "nova-g1-campaign"):
        errors.append("unsupported campaign record schema")
    if record["status"] != "workloads_observed":
        errors.append("campaign did not observe every required workload")
    if record["reasons"] != []:
        errors.append("observed campaign retains missing or contradictory failure reasons")
    if (record["hardware_qualified"] is not False or record["g1_gate_passed"] is not False
            or record["reference_comparison"] != "not_run" or not _claims(record)):
        errors.append("campaign contains an unsupported qualification claim")
    if (type(record["limitations"]) is not list or not record["limitations"]
            or any(type(item) is not str or not item for item in record["limitations"])):
        errors.append("campaign limitations are missing")
    for field in ("plan_sha256", "profile_sha256", "workloads_sha256"):
        if not _hash(record[field]):
            errors.append(field + " is not a canonical SHA256")
    for field in ("source_before", "source_after"):
        _source(record[field], errors)
    if record["source_before"] != record["source_after"]:
        errors.append("source changed during campaign")
    source = record["source_before"]
    inputs = source.get("source_inputs") if type(source) is dict else None
    if type(inputs) is dict and (
            record["profile_sha256"] != inputs.get("nova/g1-profile.json")
            or record["workloads_sha256"] != inputs.get("nova/g1-workloads.json")):
        errors.append("profile or workload manifest hash is not bound to the source snapshot")
    for field in ("provenance_before", "provenance_after"):
        value = record[field]
        tools = value.get("tool_versions") if type(value) is dict else None
        if (type(value) is not dict or value.get("capture_complete") is not True
                or type(value.get("host")) is not dict or not value["host"]
                or type(tools) is not dict
                or any(type(tools.get(name)) is not str or not tools[name] for name in (
                    "java", "verilator", "firtool", "make", "cmake", "riscv64-unknown-elf-gcc"))
                or type(value.get("submodules")) is not list or not value["submodules"]
                or type(record["source_before"]) is not dict
                or value.get("lock_hashes") != record["source_before"].get("lock_hashes")):
            errors.append("toolchain provenance is incomplete or inconsistent")
    if record["provenance_before"] != record["provenance_after"]:
        errors.append("toolchain provenance changed during campaign")
    inventory = record["inventory"]
    counts = ("package_count", "installed_package_count", "matching_package_count")
    if (type(inventory) is not dict or inventory.get("status") != "matched"
            or not _hash(inventory.get("lock_sha256")) or inventory.get("metadata_only") is not True
            or any(type(inventory.get(key)) is not int or not 1 <= inventory[key] <= 1024 for key in counts)
            or len({inventory[key] for key in counts}) != 1
            or any(inventory.get(key) != [] for key in ("blockers", "missing", "unexpected", "mismatched"))):
        errors.append("prepared environment inventory is incomplete or unmatched")
    lean_lock = "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-64-lean.conda-lock.yml"
    locks = source.get("lock_hashes") if type(source) is dict else None
    if (type(inventory) is dict and type(locks) is dict
            and inventory.get("lock_sha256") != locks.get(lean_lock)):
        errors.append("prepared inventory lock is not bound to the source snapshot")
    if inventory != record["inventory_after"]:
        errors.append("prepared environment inventory changed or was not rechecked")
    preflight = record["preflight"]
    profile_before = preflight.get("profile") if type(preflight) is dict else None
    if (type(profile_before) is not dict or profile_before.get("status") != "ready"
            or profile_before.get("profile") != "g1-chisel6-rocket"
            or profile_before.get("known_prerequisites_present") is not True
            or profile_before.get("toolchain_version_inputs_verified") is not True
            or profile_before.get("hardware_qualified") is not False
            or profile_before.get("g1_gate_passed") is not False
            or profile_before.get("blockers") != []):
        errors.append("successful campaign prerequisite profile is missing or incomplete")
    if profile_before != record["profile_after"]:
        errors.append("prepared profile or collateral changed or was not rechecked")
    resources = record["resource_limits"]
    bounds = {"jobs": (1, 2), "total_timeout_seconds": (300, 7200), "min_free_gib": (1, 50),
              "max_log_bytes": (1, 64 * 1024 * 1024), "max_cycles": (1, 10000000),
              "seed": (1, 2147483647)}
    if (type(resources) is not dict or any(
            type(resources.get(key)) is not int or not low <= resources[key] <= high
            for key, (low, high) in bounds.items())
            or type(resources.get("java_heap")) is not str
            or re.fullmatch(r"[1-8]G", resources["java_heap"]) is None):
        errors.append("campaign resource limits are missing or outside reviewed bounds")
    start, finish = _time(record["started_utc"]), _time(record["finished_utc"])
    if start is None or finish is None or finish <= start:
        errors.append("campaign timing is missing or invalid")
    elapsed = record["elapsed_seconds"]
    budget = resources.get("total_timeout_seconds") if type(resources) is dict else None
    if (type(elapsed) not in (int, float) or type(budget) is not int
            or not 0 < elapsed <= budget):
        errors.append("campaign monotonic elapsed duration is missing or exceeds its budget")
    execution_paths = _paths(record["execution_paths"], errors)
    commands = _declared_commands(record, resources, errors)
    stages = record["common_stages"]
    retained_stages = []
    checker = preflight.get("checker") if type(preflight) is dict else None
    _stage(checker, "pinned-input-check", errors)
    _bind_stage(checker, "pinned-input-check", commands, execution_paths, resources, errors)
    retained_stages.append(checker)
    if type(stages) is not list or len(stages) != len(COMMON_STAGES):
        errors.append("common build stages are incomplete")
    else:
        for stage, name in zip(stages, COMMON_STAGES):
            _stage(stage, name, errors)
            _bind_stage(stage, name, commands, execution_paths, resources, errors)
            retained_stages.append(stage)
    profiles = record["profiles"]
    if (type(profiles) is not list or len(profiles) != 2
            or any(type(profile) is not dict for profile in profiles)
            or tuple(profile.get("configuration") for profile in profiles) != CONFIGURATIONS):
        errors.append("both ordered configurations must be retained exactly once")
        return errors
    binary_sets = []
    for profile in profiles:
        config = profile["configuration"]
        _stage(profile.get("build"), config + "-build", errors)
        _bind_stage(profile.get("build"), config + "-build", commands, execution_paths, resources, errors)
        retained_stages.append(profile.get("build"))
        capture = profile.get("artifacts")
        artifacts = capture.get("artifacts") if type(capture) is dict else None
        if (type(capture) is not dict or capture.get("status") != "captured"
                or capture.get("reasons") != [] or type(artifacts) is not list or not artifacts):
            errors.append("profile artifacts were not completely captured")
            artifacts = []
        good_artifacts = [artifact for artifact in artifacts if _artifact(artifact, errors)]
        if (len(artifacts) > MAX_PROFILE_FILES
                or sum(item["size_bytes"] for item in good_artifacts) > MAX_PROFILE_BYTES):
            errors.append("recorded profile artifacts exceed their capture limits")
        paths = [artifact["path"] for artifact in good_artifacts]
        kinds = [artifact["kind"] for artifact in good_artifacts]
        if (len(set(paths)) != len(paths) or kinds.count("simulator") != 1
                or set(kinds) != {"simulator", "rtl", "device_tree", "metadata"}):
            errors.append("profile simulator, RTL, device tree, or metadata artifacts are incomplete")
        simulator = next((item["sha256"] for item in good_artifacts if item["kind"] == "simulator"), None)
        if any(item["path"] != "sims/verilator/simulator-chipyard.harness-" + config
               for item in good_artifacts if item["kind"] == "simulator"):
            errors.append("captured simulator path differs from its configuration")
        workloads = profile.get("workloads")
        if (type(workloads) is not list or len(workloads) != len(WORKLOAD_IDS)
                or any(type(item) is not dict for item in workloads)
                or tuple(item.get("id") for item in workloads) != WORKLOAD_IDS):
            errors.append("every declared workload must be retained exactly once in order")
            continue
        binaries = []
        for workload in workloads:
            negative = workload["id"] == "nova-baseline-fail"
            _artifact(workload.get("binary"), errors, "riscv_elf")
            _artifact(workload.get("binary_after"), errors, "riscv_elf")
            if workload.get("binary_after") != workload.get("binary"):
                errors.append("workload binary changed during execution")
            declared = _workload(workload["id"])
            binary = workload.get("binary")
            if (workload.get("binary_origin") != declared["binary_origin"]
                    or type(binary) is not dict or binary.get("path") != declared["binary"]):
                errors.append("workload binary path or origin differs from its declared input")
            binaries.append(workload.get("binary"))
            if not _hash(workload.get("simulator_sha256")) or workload["simulator_sha256"] != simulator:
                errors.append("workload is not bound to its captured simulator")
            if (not _hash(workload.get("simulator_sha256_after"))
                    or workload["simulator_sha256_after"] != workload.get("simulator_sha256")):
                errors.append("workload simulator changed or its post-execution identity is missing")
            stage = workload.get("stage")
            _stage(stage, config + "-" + workload["id"], errors, negative)
            _bind_stage(stage, config + "-" + workload["id"], commands, execution_paths, resources, errors)
            retained_stages.append(stage)
            assessment = workload.get("assessment")
            if (type(assessment) is not dict or assessment.get("status") != "passed"
                    or assessment.get("expectation_met") is not True
                    or assessment.get("target_completion_verified") is not False
                    or assessment.get("completion_protocol_observed") is not (not negative)
                    or assessment.get("expected_target_failure_verified") is not negative
                    or assessment.get("reasons") != []):
                errors.append("workload assessment does not establish its recorded expectation")
            elif type(stage) is dict:
                if type(stage.get("stderr_bytes")) is not int or stage["stderr_bytes"] <= 0:
                    errors.append("observed workload protocol requires a nonempty diagnostic log")
                for stream in ("stdout", "stderr"):
                    if (assessment.get(stream + "_sha256") != stage.get(stream + "_sha256")
                            or type(assessment.get(stream + "_bytes")) is not int
                            or assessment.get(stream + "_bytes") != stage.get(stream + "_bytes")):
                        errors.append("workload assessment is not bound to its recorded logs")
                cycles = assessment.get("cycles")
                if ((negative and cycles is not None) or (not negative and (
                        type(cycles) is not int or not 1 <= cycles <= 10000000
                        or (type(resources) is dict and type(resources.get("max_cycles")) is int
                            and cycles > resources["max_cycles"])))):
                    errors.append("workload cycle assessment is noncanonical")
        binary_sets.append(binaries)
    if len(binary_sets) == 2 and binary_sets[0] != binary_sets[1]:
        errors.append("the two configurations did not use identical workload binaries")
    log_paths = [stage.get(stream) for stage in retained_stages if type(stage) is dict
                 for stream in ("stdout", "stderr") if type(stage.get(stream)) is str]
    if len(set(log_paths)) != len(log_paths):
        errors.append("multiple stages reuse a retained log path")
    if type(resources) is dict and type(resources.get("max_log_bytes")) is int:
        for stage in retained_stages:
            if type(stage) is dict and any(
                    type(stage.get(key)) is int and stage[key] > resources["max_log_bytes"]
                    for key in ("stdout_bytes", "stderr_bytes")):
                errors.append("retained stage log exceeds its recorded resource limit")
    durations = [stage.get("elapsed_seconds") for stage in retained_stages if type(stage) is dict]
    # Only aggregate already bounded numbers: JSON integers can be arbitrarily
    # large, and conversion during mixed int/float arithmetic can overflow.
    if (type(elapsed) in (int, float) and 0 < elapsed <= 7200
            and all(type(value) in (int, float) and 0 <= value <= 7200 for value in durations)
            and sum(durations) > elapsed + 0.001):
        errors.append("sequential stage durations exceed the recorded campaign elapsed duration")
    return errors


def _inputs(record):
    source = dict(record["source_before"])
    source.pop("checkout_identity_sha256")
    stages = [record["preflight"]["checker"], *record["common_stages"]]
    for profile in record["profiles"]:
        stages.append(profile["build"])
        stages.extend(workload["stage"] for workload in profile["workloads"])
    return {"source": source, "profile": record["preflight"]["profile"],
            "commands": {stage["name"]: _command(stage["command"], record["execution_paths"])
                         for stage in stages}, **{field: record[field] for field in (
        "plan_sha256", "profile_sha256", "workloads_sha256", "provenance_before",
        "declared_plan", "inventory", "resource_limits", "reference_comparison")}}


def _outputs(record):
    return [{"configuration": profile["configuration"],
             "artifacts": sorted(profile["artifacts"]["artifacts"], key=lambda item: item["path"]),
             "workloads": [{"id": item["id"], "binary": item["binary"],
                            "binary_after": item["binary_after"],
                            "simulator_sha256": item["simulator_sha256"],
                            "simulator_sha256_after": item["simulator_sha256_after"],
                            "assessment": item["assessment"]} for item in profile["workloads"]]}
            for profile in record["profiles"]]


def _result(status, reasons):
    return {"schema_version": 1, "status": status, "reasons": reasons[:80],
            "comparison_scope": "recorded_input_and_artifact_identities_only",
            "hardware_qualified": False, "g1_gate_passed": False,
            "reference_comparison_qualified": False, "reference_comparison": "not_run",
            "limitations": list(LIMITATIONS)}


def compare_records(left, right):
    """Read-only, fail-closed comparison; consistency is not execution evidence."""
    try:
        left_bytes, right_bytes = _canonical(left), _canonical(right)
    except RecordError as error:
        return _result("blocked", [str(error)])
    errors = ["left: " + item for item in _validate(left)]
    errors += ["right: " + item for item in _validate(right)]
    if errors:
        return _result("blocked", errors)
    if left_bytes == right_bytes:
        return _result("blocked", ["identical campaign records cannot establish distinct capture"])
    if left["source_before"]["checkout_identity_sha256"] == right["source_before"]["checkout_identity_sha256"]:
        return _result("blocked", ["the same checkout identity was reused"])
    reasons = []
    if _inputs(left) != _inputs(right):
        reasons.append("recorded source, plan, workload, resource, or environment identities differ")
    if _outputs(left) != _outputs(right):
        reasons.append("recorded simulator, RTL, metadata, binary, or workload-result identities differ; review required")
    result = _result("different" if reasons else "consistent", reasons)
    left_stages = left["common_stages"] + [profile["build"] for profile in left["profiles"]]
    right_stages = right["common_stages"] + [profile["build"] for profile in right["profiles"]]
    result["build_log_differences"] = [stage["name"] for stage, other in zip(left_stages, right_stages)
                                       if any(stage[key] != other[key] for key in (
                                           "stdout_sha256", "stderr_sha256", "stdout_bytes", "stderr_bytes"))]
    result["record_sha256"] = {"left": hashlib.sha256(left_bytes).hexdigest(),
                               "right": hashlib.sha256(right_bytes).hexdigest()}
    return result


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecordError("record contains duplicate JSON keys")
        result[key] = value
    return result


def _constant(_value):
    raise RecordError("record contains a non-finite JSON number")


def read_record(path):
    """Read a bounded stable regular JSON record, rejecting symlink components."""
    try:
        path = Path(path)
        if ".." in path.parts or any(part.is_symlink() for part in (path, *path.parents)):
            raise RecordError("record path contains traversal or a symlink")
        before = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_RECORD_BYTES:
            raise RecordError("record must be a bounded regular file")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_RECORD_BYTES:
                raise RecordError("record must be a bounded regular file")
            raw = stream.read(MAX_RECORD_BYTES + 1)
            after = os.fstat(stream.fileno())
        current = path.stat(follow_symlinks=False)
        identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        if (len(raw) > MAX_RECORD_BYTES or not identity(before) == identity(opened)
                == identity(after) == identity(current)):
            raise RecordError("record changed during bounded read")
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
        _canonical(result)
        return result
    except RecordError:
        raise
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise RecordError("record is not safely readable canonical JSON") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare_records(read_record(args.left), read_record(args.right))
    except RecordError as error:
        result = _result("blocked", [str(error)])
    print(json.dumps(result, sort_keys=True, indent=2))
    return {"consistent": 0, "different": 1, "blocked": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
