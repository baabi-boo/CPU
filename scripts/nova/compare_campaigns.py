#!/usr/bin/env python3
"""Compare recorded G1 identities without executing or qualifying hardware.

A consistent result means agreement between unauthenticated JSON records, not
proof of independent builds, trustworthy logs, or hardware correctness.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat


_OBSERVED_SPEC = importlib.util.spec_from_file_location(
    "nova_compare_observed_record", Path(__file__).with_name("observed_record.py"))
observed_record = importlib.util.module_from_spec(_OBSERVED_SPEC)
_OBSERVED_SPEC.loader.exec_module(observed_record)

MAX_RECORD_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024
MAX_PROFILE_BYTES = 2 * 1024 * 1024 * 1024
MAX_PROFILE_FILES = 8192
MAX_JSON_NODES = 100000
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
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
# Schema 1 is a fixed, protocol-only campaign. A self-consistent plan hash does
# not make a changed approval, reproduction, or reference policy compatible.
LEGACY_PLAN_METADATA = {
    "schema_version": 1, "scope": "G1 declared single-core workload plan only",
    "hardware_qualified": False, "g1_gate_passed": False,
    "does_not_provision_toolchain_or_initialize_submodules": True,
    "build_dependency_resolution": "may_access_network",
    "execute_requires_approved_budget": True, "source_must_be_clean": True,
    "source_provenance": {
        "chipyard_commit": "a7946ede9bd625204435715dc40c750e2f8a251f",
        "gitlinks": {
            "generators/rocket-chip": "ece7b9ad544b07df39cd13b6fd7236562a26355d",
            "generators/testchipip": "555ff3fbc12f81a8feff7a4801930fb384ddd2ae",
            "toolchains/riscv-tools/riscv-tests": "0494f954a3d8d2ca9e4972da7a01e94b6a909bce",
            "toolchains/riscv-tools/riscv-isa-sim": "9c190a07c6838f6392bafa4ad83acea462c7f759",
        },
    },
    "reference": {"model": "Spike", "source_gitlink": "toolchains/riscv-tools/riscv-isa-sim",
                  "comparison_scope": "unresolved", "qualified": False},
    "exclusions": ["F", "D", "A", "C", "MMU", "full-ISA-certification",
                   "per-instruction-differential-checking", "heterogeneous-execution"],
    "reproduction": {"required_clean_builds": 2, "shared_generated_artifacts_allowed": False,
                     "automatic_gate_acceptance": False},
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
OBSERVED_PLAN_METADATA = {
    **LEGACY_PLAN_METADATA,
    "schema_version": 2,
    "target_exit_observer": {
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
    },
}
PINNED_TOOL_VERSIONS = {"verilator": "5.022", "firtool": "1.75.0"}
CLAIM_FLAGS = {
    "hardware_qualified", "g1_gate_passed", "reference_comparison_qualified",
    "full_isa_certification", "toolchain_versions_verified",
    "installed_binary_contents_verified", "lock_origin_verified",
    "target_completion_verified",
    "closure_qualified", "dependency_closure_qualified", "identity_verified",
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


def _claims(value, allowed_target_assessments=frozenset(), path=()):
    if type(value) is dict:
        for key, child in value.items():
            allowed = (key == "target_completion_verified" and child is True
                       and path in allowed_target_assessments)
            if key in CLAIM_FLAGS and child is not False and not allowed:
                return False
            if not _claims(child, allowed_target_assessments, path + (key,)):
                return False
    elif type(value) is list:
        return all(_claims(child, allowed_target_assessments, path + (index,))
                   for index, child in enumerate(value))
    return True


def _same_contract(value, expected):
    """Compare JSON without Python's bool/int/integral-float equality aliases."""
    return _canonical(value) == _canonical(expected)


def _hash_map(value, count=None):
    return (type(value) is dict and bool(value) and (count is None or len(value) == count)
            and all(_relative(path) and _hash(digest) for path, digest in value.items()))


def _source(value, errors):
    required = {"revision", "tree", "clean", "checkout_identity_sha256", "lock_hashes",
                "source_inputs", "submodules", "state_digest"}
    if type(value) is not dict or set(value) != required:
        errors.append("source snapshot is incomplete or has unsupported fields")
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
        if (type(row) is not dict
                or set(row) != {"path", "pin", "revision", "initialized", "clean", "state"}
                or not _relative(row.get("path"))
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
    # capture_source hashes these exact fields plus the raw Git status hash.
    # An accepted clean snapshot implies empty status; this binds only recorded
    # metadata, not the real Git contents or the claimed cleanliness.
    state = {key: item for key, item in value.items()
             if key not in {"state_digest", "checkout_identity_sha256"}}
    state["status_sha256"] = EMPTY_SHA256
    if hashlib.sha256(_canonical(state)).hexdigest() != value["state_digest"]:
        errors.append("source state digest does not bind its clean snapshot")


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


def _profile_details(profile, source, errors):
    """Reject contradictions in retained details without inventing legacy rows.

    Older schema-1 records may retain only the summary. Present tool, source,
    and collateral observations must nevertheless agree with a ready summary.
    None of these checks authenticates the observations or qualifies closure.
    """
    if type(profile) is not dict:
        return
    if "schema_version" in profile and not _same_contract(profile["schema_version"], 1):
        errors.append("prerequisite profile detail has an unsupported schema")
    for field in ("nested_dependency_closure", "maven_artifact_closure"):
        if field in profile and profile[field] != "unqualified":
            errors.append("ready prerequisite profile retains an unsupported closure claim")
    if "initialized_optional_generators" in profile and profile["initialized_optional_generators"] != []:
        errors.append("ready prerequisite profile retains initialized optional generators")
    if "host" in profile and not _same_contract(
            profile["host"], {"system": "Linux", "architecture": "x86_64"}):
        errors.append("ready prerequisite profile has an unsupported host")

    source_inputs = source.get("source_inputs") if type(source) is dict else None
    if "source_inputs" in profile:
        inputs = profile["source_inputs"]
        if type(inputs) is not dict:
            errors.append("prerequisite source input details are malformed")
        else:
            for path, row in inputs.items():
                if (not _relative(path) or type(row) is not dict
                        or row.get("matches_profile") is not True or not _hash(row.get("sha256"))
                        or type(source_inputs) is not dict
                        or row["sha256"] != source_inputs.get(path)):
                    errors.append("ready prerequisite source input contradicts its source snapshot")

    source_rows = source.get("submodules") if type(source) is dict else None
    snapshots = {row["path"]: row for row in source_rows
                 if type(row) is dict and type(row.get("path")) is str} if type(source_rows) is list else {}
    for field in ("source_gitlinks", "provisioning_sources"):
        if field not in profile:
            continue
        rows = profile[field]
        if type(rows) is not list:
            errors.append("prerequisite source gitlink details are malformed")
            continue
        seen = set()
        for row in rows:
            if (type(row) is not dict or not _relative(row.get("path"))
                    or row["path"] in seen or not _hash(row.get("pin"), SHA1)):
                errors.append("prerequisite source gitlink detail is invalid or duplicated")
                continue
            seen.add(row["path"])
            observed = snapshots.get(row["path"])
            allowed = ("at_pin",) if field == "source_gitlinks" else ("at_pin", "uninitialized")
            if (row.get("state") not in allowed or observed is None
                    or row["pin"] != observed.get("pin") or row.get("state") != observed.get("state")):
                errors.append("ready prerequisite gitlink contradicts its source snapshot")

    if "tools" in profile:
        rows = profile["tools"]
        if type(rows) is not list:
            errors.append("prerequisite tool details are malformed")
        else:
            seen = set()
            for row in rows:
                if (type(row) is not dict or type(row.get("name")) is not str
                        or not row["name"] or row["name"] in seen):
                    errors.append("prerequisite tool detail is invalid or duplicated")
                    continue
                seen.add(row["name"])
                expected = PINNED_TOOL_VERSIONS.get(row["name"])
                observed = row.get("observed_version")
                if (row.get("available") is not True
                        or row.get("expected_version") != expected
                        or (observed is not None and (type(observed) is not str or not observed))
                        or (expected is not None and (observed != expected
                            or row.get("version_matches") is not True))
                        or (expected is None and row.get("version_matches") is not None)):
                    errors.append("ready prerequisite tool contradicts availability or its pinned version")

    if "collateral" in profile:
        rows = profile["collateral"]
        if type(rows) is not dict:
            errors.append("prerequisite collateral details are malformed")
        else:
            for name, row in rows.items():
                if (not name or type(row) is not dict or row.get("available") is not True
                        or not _relative(row.get("path")) or not _hash(row.get("sha256"))
                        or type(row.get("bytes")) is not int or not 1 <= row["bytes"] <= 256 * 1024 * 1024
                        or ("matches_pinned" in row and row["matches_pinned"] is not True)
                        or (name == "htif_installed_linker" and row.get("matches_pinned") is not True)):
                    errors.append("ready prerequisite collateral is unavailable or inconsistent")
            linker, installed = rows.get("htif_linker"), rows.get("htif_installed_linker")
            if (type(linker) is dict and type(installed) is dict
                    and any(not _same_contract(linker.get(key), installed.get(key))
                            for key in ("sha256", "bytes"))):
                errors.append("installed prerequisite linker differs from its recorded pinned source")


def _declared_commands(record, resources, errors):
    plan = record["declared_plan"]
    if type(plan) is not dict or type(resources) is not dict:
        errors.append("declared campaign plan is missing")
        return {}
    if hashlib.sha256(_canonical(plan)).hexdigest() != record["plan_sha256"]:
        errors.append("declared campaign plan does not match its recorded hash")
    observed = record["schema_version"] == 2
    metadata = OBSERVED_PLAN_METADATA if observed else LEGACY_PLAN_METADATA
    if (set(plan) != set(metadata) | {"common_build_stages", "profiles"}
            or not _same_contract({key: plan.get(key) for key in metadata}, metadata)):
        errors.append("declared campaign plan differs from fixed schema-"
                      + ("2" if observed else "1") + " policies or provenance")
    source = record.get("source_before")
    rows = source.get("submodules") if type(source) is dict else None
    pins = {row["path"]: row.get("pin") for row in rows
            if type(row) is dict and type(row.get("path")) is str} if type(rows) is list else {}
    if any(pins.get(path) != pin for path, pin in LEGACY_PLAN_METADATA["source_provenance"]["gitlinks"].items()):
        errors.append("declared workload source provenance is not bound to the source snapshot")
    jobs, heap = resources.get("jobs"), resources.get("java_heap")
    cycles, seed = resources.get("max_cycles"), resources.get("seed")
    if not _same_contract({"max_cycles": cycles, "seed": seed}, {"max_cycles": 10000000, "seed": 1}):
        errors.append("campaign cycle and seed limits differ from the fixed plan")
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
    if observed:
        expected_common.insert(0, {
            "id": "htif-observer-prepare", "timeout_seconds": 120,
            "argv": ["python3", "-B", "<repo>/scripts/nova/htif_observer.py",
                     "--prepare", "--root", "<repo>",
                     "--output", "<repo>/nova-out/htif-observer"],
        })
    if not _same_contract(declared_common, expected_common):
        errors.append("declared common build commands differ from the fixed campaign")
    for stage in expected_common:
        commands[stage["id"]] = (stage["argv"], stage["timeout_seconds"])
    profiles = plan.get("profiles")
    if (type(profiles) is not list or len(profiles) != 2
            or any(type(item) is not dict for item in profiles)
            or tuple(item.get("configuration") for item in profiles) != CONFIGURATIONS):
        errors.append("declared plan must contain both ordered configurations")
        return commands
    for profile, config in zip(profiles, CONFIGURATIONS):
        if set(profile) != {"configuration", "build", "simulator", "simulation_cwd",
                            "simulation_limits", "workloads"}:
            errors.append("declared configuration plan has missing or unsupported fields")
        observer_make_args = (["-f", "Makefile", "-f", "<repo>/software/nova/observer/observer.mk"]
                              if observed else [])
        build = ["make", "-C", "<repo>/sims/verilator", *observer_make_args, "CONFIG=" + config,
                 "JAVA_HEAP_SIZE=" + str(heap), "-j" + str(jobs)]
        if not _same_contract(profile.get("build"),
                              {"id": config + "-build", "timeout_seconds": 7200, "argv": build}):
            errors.append("declared simulator build differs from its configuration or resources")
        commands[config + "-build"] = (build, 7200)
        simulator = "<repo>/sims/verilator/simulator-chipyard.harness-" + config
        if (profile.get("simulator") != simulator or profile.get("simulation_cwd") != "<repo>/sims/verilator"
                or not _same_contract(profile.get("simulation_limits"),
                                      {"max_cycles": cycles, "seed": seed, "timeout_seconds": 300})):
            errors.append("declared simulation paths or resource limits differ from the campaign")
        expected_workloads = [_workload(identifier) for identifier in WORKLOAD_IDS]
        if not _same_contract(profile.get("workloads"), expected_workloads):
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
                and value.get(stream + "_sha256") != EMPTY_SHA256):
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
    # The producer requires ELF64's 64-byte header and at least one 56-byte
    # program header. A plausible size alone does not establish real ELF bytes.
    if value["kind"] in {"riscv_elf", "simulator"} and value["size_bytes"] < 120:
        errors.append("recorded ELF artifact is smaller than its structural minimum")
        return False
    if value["kind"] in {"metadata", "device_tree"} and value["size_bytes"] > MAX_METADATA_BYTES:
        errors.append("recorded metadata exceeds its capture byte limit")
        return False
    return True


def _observer_context(record, errors):
    """Bind validated observer metadata to overlapping core input identities."""
    metadata = record["target_exit_observer"]
    policy = OBSERVED_PLAN_METADATA["target_exit_observer"]
    if metadata["manifest_path"] != policy["manifest_path"]:
        errors.append("observer manifest path differs from the fixed campaign plan")
    source = record["source_before"]
    inputs = source.get("source_inputs") if type(source) is dict else None
    flags = metadata["inputs"]["upstream_sim_flags"]
    if type(inputs) is not dict or inputs.get(flags["path"]) != flags["sha256"]:
        errors.append("observer simulation flags are not bound to the source snapshot")
    rows = source.get("submodules") if type(source) is dict else None
    spike = next((row for row in rows if type(row) is dict
                  and row.get("path") == policy["source_gitlink"]), None) if type(rows) is list else None
    if (spike is None or spike.get("initialized") is not True or spike.get("clean") is not True
            or spike.get("state") != "at_pin" or spike.get("revision") != metadata["source_pin"]
            or spike.get("pin") != metadata["source_pin"]):
        errors.append("observer source is not bound to its initialized pinned source snapshot")
    preflight = record["preflight"]
    profile = preflight.get("profile") if type(preflight) is dict else None
    collateral = profile.get("collateral") if type(profile) is dict else None
    if type(collateral) is dict:
        for observer_field, profile_field in (("archive", "fesvr_library"),
                                               ("installed_header", "fesvr_header")):
            if profile_field not in collateral:
                continue
            retained = collateral[profile_field]
            identity = metadata[observer_field]
            if (type(retained) is not dict or not _same_contract(
                    {"path": retained.get("path"), "sha256": retained.get("sha256"),
                     "size_bytes": retained.get("bytes")},
                    {key: identity[key] for key in ("path", "sha256", "size_bytes")})):
                errors.append("observer " + observer_field
                              + " differs from retained prerequisite collateral")


def _validate(record):
    errors = []
    if type(record) is not dict or not REQUIRED_FIELDS <= record.keys():
        return ["campaign record schema is incomplete"]
    if (type(record["schema_version"]) is not int or record["schema_version"] not in (1, 2)
            or record["kind"] != "nova-g1-campaign"):
        errors.append("unsupported campaign record schema")
    observed = type(record["schema_version"]) is int and record["schema_version"] == 2
    allowed_target_assessments = frozenset()
    if observed:
        extension_errors = observed_record.validate_extension(record)
        errors.extend("target-exit extension: " + item for item in extension_errors)
        if not extension_errors:
            allowed_target_assessments = frozenset(
                ("profiles", profile, "workloads", row, "target_exit", "assessment")
                for profile in range(len(CONFIGURATIONS)) for row in range(len(WORKLOAD_IDS)))
            _observer_context(record, errors)
    elif ("target_exit_observer" in record or (type(record["profiles"]) is list and any(
            type(profile) is dict and type(profile.get("workloads")) is list
            and any(type(row) is dict and "target_exit" in row for row in profile["workloads"])
            for profile in record["profiles"]))):
        errors.append("schema-1 campaign cannot retain target-exit observer extensions")
    if record["status"] != "workloads_observed":
        errors.append("campaign did not observe every required workload")
    if record["reasons"] != []:
        errors.append("observed campaign retains missing or contradictory failure reasons")
    if (record["hardware_qualified"] is not False or record["g1_gate_passed"] is not False
            or record["reference_comparison"] != "not_run"
            or not _claims(record, allowed_target_assessments)):
        errors.append("campaign contains an unsupported qualification claim")
    if (type(record["limitations"]) is not list or not record["limitations"]
            or any(type(item) is not str or not item for item in record["limitations"])):
        errors.append("campaign limitations are missing")
    for field in ("plan_sha256", "profile_sha256", "workloads_sha256"):
        if not _hash(record[field]):
            errors.append(field + " is not a canonical SHA256")
    for field in ("source_before", "source_after"):
        _source(record[field], errors)
    if not _same_contract(record["source_before"], record["source_after"]):
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
    if not _same_contract(record["provenance_before"], record["provenance_after"]):
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
    if not _same_contract(inventory, record["inventory_after"]):
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
    _profile_details(profile_before, source, errors)
    _profile_details(record["profile_after"], record["source_after"], errors)
    if not _same_contract(profile_before, record["profile_after"]):
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
    common_stages = (("htif-observer-prepare",) + COMMON_STAGES if observed else COMMON_STAGES)
    if type(stages) is not list or len(stages) != len(common_stages):
        errors.append("common build stages are incomplete")
    else:
        for stage, name in zip(stages, common_stages):
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
        generated_prefix = "sims/verilator/generated-src/chipyard.harness.TestHarness." + config + "/"
        suffix_kinds = {".v": "rtl", ".sv": "rtl", ".dts": "device_tree", ".json": "metadata"}
        if any(not item["path"].startswith(generated_prefix)
               or not _relative(item["path"][len(generated_prefix):])
               or suffix_kinds.get(PurePosixPath(item["path"]).suffix) != item["kind"]
               for item in good_artifacts if item["kind"] != "simulator"):
            errors.append("generated artifact path or suffix differs from its configuration and kind")
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
                marker = ("Hello world from core 0, a rocket" if workload["id"] == "hello"
                          else declared["expected_marker"])
                if (marker is not None and (type(stage.get("stdout_bytes")) is not int
                        or stage["stdout_bytes"] < len(marker.encode("utf-8")) + 1)):
                    errors.append("marker-required workload stdout is too short for its exact line")
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
    result = {"source": source, "profile": record["preflight"]["profile"],
              "commands": {stage["name"]: _command(stage["command"], record["execution_paths"])
                           for stage in stages}, **{field: record[field] for field in (
        "plan_sha256", "profile_sha256", "workloads_sha256", "provenance_before",
        "declared_plan", "inventory", "resource_limits", "reference_comparison")}}
    if record["schema_version"] == 2:
        result["target_exit_observer"] = observed_record.comparison_view(record)["target_exit_observer"]
    return result


def _outputs(record):
    profiles = [{"configuration": profile["configuration"],
             "artifacts": sorted(profile["artifacts"]["artifacts"], key=lambda item: item["path"]),
             "workloads": [{"id": item["id"], "binary": item["binary"],
                            "binary_after": item["binary_after"],
                            "simulator_sha256": item["simulator_sha256"],
                            "simulator_sha256_after": item["simulator_sha256_after"],
                            "assessment": item["assessment"]} for item in profile["workloads"]]}
            for profile in record["profiles"]]
    if record["schema_version"] == 2:
        return {"profiles": profiles, "target_exit": observed_record.comparison_view(record)}
    return profiles


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
    if left["schema_version"] != right["schema_version"]:
        return _result("blocked", ["protocol-only and observed-target campaign schemas are not comparable"])
    if left_bytes == right_bytes:
        return _result("blocked", ["identical campaign records cannot establish distinct capture"])
    if left["source_before"]["checkout_identity_sha256"] == right["source_before"]["checkout_identity_sha256"]:
        return _result("blocked", ["the same checkout identity was reused"])
    if left["schema_version"] == 2 and observed_record.run_ids(left) & observed_record.run_ids(right):
        return _result("blocked", ["target-exit run IDs were reused across campaign records"])
    reasons = []
    if not _same_contract(_inputs(left), _inputs(right)):
        reasons.append("recorded source, plan, workload, resource, or environment identities differ")
    if not _same_contract(_outputs(left), _outputs(right)):
        reasons.append("recorded simulator, RTL, metadata, binary, or workload-result identities differ; review required")
    result = _result("different" if reasons else "consistent", reasons)
    if left["schema_version"] == 2:
        result["limitations"].append(
            "Observer metadata and exit semantics are compared as recorded; raw witnesses and execution are not authenticated.")
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


def parse_record_bytes(raw):
    """Parse bounded UTF-8 JSON already captured by a caller's safe reader."""
    if type(raw) is not bytes or len(raw) > MAX_RECORD_BYTES:
        raise RecordError("record must be bounded captured bytes")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
        _canonical(result)
        return result
    except RecordError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise RecordError("record is not safely readable canonical JSON") from exc


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
        return parse_record_bytes(raw)
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
