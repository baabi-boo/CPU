#!/usr/bin/env python3
"""Validate the recorded schema-2 HTIF extension without filesystem access.

These checks establish internal agreement between supplied JSON fields only.
They do not re-read or authenticate witness files, manifests, builds, or target
execution. A caller must also validate the ordinary campaign record, process
results, log assessment, source provenance, and retained artifacts. Only the
nested observer assessment may report target_completion_verified=True; no
hardware or G1 qualification follows from an accepted extension.
"""

import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re


_SPEC = importlib.util.spec_from_file_location(
    "nova_observed_record_htif_observer", Path(__file__).with_name("htif_observer.py"))
_observer = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_observer)

MAX_RECORD_BYTES = 4 * 1024 * 1024
MAX_JSON_NODES = 100000
MAX_JSON_DEPTH = 32
MAX_WITNESS_BYTES = 4096
MAX_REASONS = 80
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
EXTENSION_FIELDS = {"witness", "binding", "assessment"}
WITNESS_FIELDS = {"path", "kind", "size_bytes", "sha256"}
BINDING_FIELDS = {
    "schema_version", "configuration", "workload_id", "run_id",
    "binary_sha256", "simulator_sha256", "observer_manifest_sha256",
    "source_revision", "source_tree", "source_state_digest", "max_cycles", "seed",
}
EVENT_FIELDS = {
    "schema_version", "kind", "run_id", "binding_sha256",
    "target_exit_present", "raw_exit_code", "target_exit_code", "signal_exit",
}
ASSESSMENT_FIELDS = {
    "status", "target_exit_observed", "target_completion_verified",
    "hardware_qualified", "g1_gate_passed", "reasons", "witness_sha256",
    "witness_bytes", "event",
}
SEMANTIC_EVENT_FIELDS = (
    "schema_version", "kind", "target_exit_present", "raw_exit_code",
    "target_exit_code", "signal_exit",
)
SEMANTIC_ASSESSMENT_FIELDS = (
    "status", "target_exit_observed", "target_completion_verified",
    "hardware_qualified", "g1_gate_passed", "reasons",
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("ascii")


def _json_problem(value):
    """Bound corrupt in-memory input before encoding or inspecting its fields."""
    pending = [(value, 0)]
    count = scalar_characters = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > MAX_JSON_DEPTH or count > MAX_JSON_NODES:
            return "record exceeds JSON complexity bounds"
        kind = type(item)
        if kind in (dict, list):
            if count + len(pending) + len(item) > MAX_JSON_NODES:
                return "record exceeds JSON complexity bounds"
            if kind is dict:
                for key in item:
                    if type(key) is not str:
                        return "record contains a non-string JSON object key"
                    scalar_characters += len(key)
                children = item.values()
            else:
                children = item
            pending.extend((child, depth + 1) for child in children)
        elif kind is str:
            scalar_characters += len(item)
        elif kind is float:
            if not math.isfinite(item):
                return "record contains a non-finite JSON number"
        elif kind is int:
            # No accepted campaign integer approaches this bound. Avoid an
            # expensive conversion, including Python's integer-string limit.
            if item.bit_length() > 4096:
                return "record contains an excessively large JSON integer"
        elif item is not None and kind is not bool:
            return "record contains a non-JSON value"
        if scalar_characters > MAX_RECORD_BYTES:
            return "record exceeds JSON size bound"
    try:
        if len(_canonical(value)) > MAX_RECORD_BYTES:
            return "record exceeds JSON size bound"
    except (TypeError, ValueError, OverflowError, RecursionError):
        return "record cannot be canonically encoded"
    return None


def _hash(value, pattern=SHA256):
    return type(value) is str and pattern.fullmatch(value) is not None


def _shape(value, fields):
    return type(value) is dict and set(value) == fields


def _claim_errors(record):
    allowed = {
        ("profiles", profile, "workloads", row, "target_exit", "assessment")
        for profile in range(len(CONFIGURATIONS)) for row in range(len(WORKLOAD_IDS))
    }
    pending = [(record, ())]
    errors = []
    while pending and len(errors) < MAX_REASONS:
        value, path = pending.pop()
        if type(value) is dict:
            for key, child in value.items():
                if key in {"hardware_qualified", "g1_gate_passed"} and child is not False:
                    errors.append("observer records cannot claim hardware or G1 qualification")
                if (key == "target_completion_verified" and child is not False
                        and not (path in allowed and child is True)):
                    errors.append("target completion claim is outside its exact observer assessment")
                pending.append((child, path + (key,)))
        elif type(value) is list:
            pending.extend((child, path + (index,)) for index, child in enumerate(value))
    return errors


def _row_errors(row, config, identifier, source, resources, metadata, simulator,
                seen_runs, seen_paths):
    label = config + "/" + identifier + ": "
    errors = []
    ordinary = row.get("assessment")
    if (type(ordinary) is not dict
            or ordinary.get("target_completion_verified") is not False):
        errors.append("ordinary log assessment must remain protocol-only")
    extension = row.get("target_exit")
    if not _shape(extension, EXTENSION_FIELDS):
        return [label + item for item in errors + ["target_exit extension is incomplete or unsupported"]]
    witness, binding, assessment = (extension[key] for key in ("witness", "binding", "assessment"))
    witness_ok = _shape(witness, WITNESS_FIELDS)
    if witness_ok:
        expected_path = config + "-" + identifier + ".htif-exit.json"
        witness_ok = (
            witness["path"] == expected_path and witness["kind"] == "htif_exit_witness"
            and type(witness["size_bytes"]) is int and 0 < witness["size_bytes"] <= MAX_WITNESS_BYTES
            and _hash(witness["sha256"]) and witness["sha256"] != EMPTY_SHA256
        )
        if type(witness["path"]) is str:
            if witness["path"] in seen_paths:
                errors.append("witness filename is reused within the campaign")
            seen_paths.add(witness["path"])
    if not witness_ok:
        errors.append("witness identity must have the exact row filename, kind, bounded bytes, and SHA256")

    binding_ok = _shape(binding, BINDING_FIELDS)
    if binding_ok:
        binary = row.get("binary")
        binary_sha256 = binary.get("sha256") if type(binary) is dict else None
        expected = {
            "schema_version": 1, "configuration": config, "workload_id": identifier,
            "binary_sha256": binary_sha256, "simulator_sha256": row.get("simulator_sha256"),
            "observer_manifest_sha256": metadata.get("manifest_sha256"),
            "source_revision": source.get("revision"), "source_tree": source.get("tree"),
            "source_state_digest": source.get("state_digest"),
            "max_cycles": resources.get("max_cycles"), "seed": resources.get("seed"),
        }
        if (not _hash(binary_sha256) or row.get("simulator_sha256") != simulator
                or not _hash(simulator)):
            errors.append("row ELF or captured simulator identity is missing or inconsistent")
        if any(type(binding[key]) is not type(value) or binding[key] != value
               for key, value in expected.items()):
            errors.append("binding differs from its source, row, observer, or resource identities")
        if not _hash(binding["run_id"]):
            errors.append("binding run ID must be lowercase hex64")
        else:
            if binding["run_id"] in seen_runs:
                errors.append("run ID is reused within the campaign")
            seen_runs.add(binding["run_id"])
    else:
        errors.append("binding fields differ from the exact observer contract")

    if not _shape(assessment, ASSESSMENT_FIELDS):
        errors.append("observer assessment fields are incomplete or unsupported")
        return [label + item for item in errors]
    if (assessment["status"] != "observed" or assessment["target_exit_observed"] is not True
            or assessment["target_completion_verified"] is not True
            or assessment["hardware_qualified"] is not False or assessment["g1_gate_passed"] is not False
            or type(assessment["reasons"]) is not list or assessment["reasons"]):
        errors.append("observer assessment does not establish its matching supplied event")
    if (not _hash(assessment["witness_sha256"])
            or type(assessment["witness_bytes"]) is not int
            or not 0 < assessment["witness_bytes"] <= MAX_WITNESS_BYTES
            or not witness_ok or assessment["witness_sha256"] != witness["sha256"]
            or assessment["witness_bytes"] != witness["size_bytes"]):
        errors.append("observer assessment is not bound to its recorded witness SHA256 and bytes")
    event = assessment["event"]
    if not _shape(event, EVENT_FIELDS):
        errors.append("observer event must have exactly the dedicated witness fields")
        return [label + item for item in errors]
    expected_exit = 7 if identifier == "nova-baseline-fail" else 0
    if (type(event["schema_version"]) is not int or event["schema_version"] != 1
            or event["kind"] != "nova-htif-exit"
            or event["target_exit_present"] is not True or event["signal_exit"] is not False
            or type(event["raw_exit_code"]) is not int
            or event["raw_exit_code"] != ((expected_exit << 1) | 1)
            or type(event["target_exit_code"]) is not int or event["target_exit_code"] != expected_exit):
        errors.append("observer event is not the exact present nonsignaled expected target exit")
    if (not _hash(event["run_id"]) or not _hash(event["binding_sha256"])
            or not binding_ok or event["run_id"] != binding["run_id"]
            or event["binding_sha256"] != hashlib.sha256(_canonical(binding)).hexdigest()):
        errors.append("observer event run ID or canonical binding SHA256 does not match its row binding")
    # The parser accepts whitespace/key-order variation, so reserializing an
    # event cannot recover its raw file hash. Only an impossible byte count can
    # be rejected here; the separately retained raw bytes remain unauthenticated.
    if witness_ok and witness["size_bytes"] < len(_canonical(event)) + 1:
        errors.append("recorded witness is too short to contain its event and required newline")
    return [label + item for item in errors]


def _validate(record):
    problem = _json_problem(record)
    if problem:
        return [problem]
    if (type(record) is not dict or type(record.get("schema_version")) is not int
            or record["schema_version"] != 2):
        return ["observer extension requires a schema-2 campaign record"]
    errors = _claim_errors(record)
    if record.get("kind") != "nova-g1-campaign" or record.get("status") != "workloads_observed":
        errors.append("observer comparison requires a completed workloads_observed campaign record")
    if record.get("hardware_qualified") is not False or record.get("g1_gate_passed") is not False:
        errors.append("campaign hardware and G1 qualification flags must remain false")
    metadata = record.get("target_exit_observer")
    try:
        _observer.validate_build_metadata(metadata)
    except (ValueError, TypeError, KeyError):
        errors.append("observer build metadata is missing or differs from the frozen contract")
    if type(metadata) is not dict:
        metadata = {}
    source = record.get("source_before")
    source_after = record.get("source_after")
    if (type(source) is not dict or type(source_after) is not dict
            or any(not _hash(source.get(key), pattern) for key, pattern in (
                ("revision", SHA1), ("tree", SHA1), ("state_digest", SHA256)))
            or any(source.get(key) != source_after.get(key) for key in ("revision", "tree", "state_digest"))):
        errors.append("observer binding requires stable canonical source revision, tree, and state digest")
    if type(source) is not dict:
        source = {}
    resources = record.get("resource_limits")
    if (type(resources) is not dict or any(
            type(resources.get(key)) is not int or not 1 <= resources[key] <= limit
            for key, limit in (("max_cycles", 10000000), ("seed", 2147483647)))):
        errors.append("observer binding requires canonical bounded max_cycles and seed")
    if type(resources) is not dict:
        resources = {}
    profiles = record.get("profiles")
    if (type(profiles) is not list or len(profiles) != len(CONFIGURATIONS)
            or any(type(profile) is not dict for profile in profiles)
            or tuple(profile.get("configuration") for profile in profiles) != CONFIGURATIONS):
        return errors + ["observer extension requires both ordered configurations exactly once"]
    seen_runs, seen_paths = set(), set()
    for profile, config in zip(profiles, CONFIGURATIONS):
        capture = profile.get("artifacts")
        artifacts = capture.get("artifacts") if type(capture) is dict else None
        simulators = ([item for item in artifacts if type(item) is dict and item.get("kind") == "simulator"]
                      if type(artifacts) is list else [])
        if (len(simulators) != 1 or not _hash(simulators[0].get("sha256"))
                or simulators[0].get("path") != "sims/verilator/simulator-chipyard.harness-" + config):
            errors.append(config + ": observer binding requires one captured simulator for its configuration")
            simulator = None
        else:
            simulator = simulators[0]["sha256"]
        rows = profile.get("workloads")
        if (type(rows) is not list or len(rows) != len(WORKLOAD_IDS)
                or any(type(row) is not dict for row in rows)
                or tuple(row.get("id") for row in rows) != WORKLOAD_IDS):
            errors.append(config + ": observer extension requires every ordered workload exactly once")
            continue
        for row, identifier in zip(rows, WORKLOAD_IDS):
            errors.extend(_row_errors(row, config, identifier, source, resources, metadata,
                                      simulator, seen_runs, seen_paths))
    return errors[:MAX_REASONS]


def validate_extension(record):
    """Return reasons for refusing a schema-2 extension; never inspect raw files.

    An empty list validates this extension only, not the ordinary campaign or
    claimed execution. Blocked/pending/failed extensions are not comparable.
    Bounded malformed JSON-like inputs return reasons instead of raising.
    """
    try:
        return _validate(record)[:MAX_REASONS]
    except (TypeError, ValueError, KeyError, OverflowError, RecursionError):
        return ["observer extension is not safely inspectable JSON metadata"]


def comparison_view(record):
    """Return stable observer metadata and ordered semantic exit assessments.

    Per-run binding objects, run IDs, witness filenames, witness SHA256 values,
    and witness byte counts are validated internally but omitted from equality.
    Their stable source/binary/resource identities remain the core comparator's
    responsibility. Invalid input yields {}; callers must validate both records
    first, rather than equating two rejected views. The view shares no mutable
    objects with the input.
    """
    if validate_extension(record):
        return {}
    return {
        "target_exit_observer": copy.deepcopy(record["target_exit_observer"]),
        "profiles": [{
            "configuration": profile["configuration"],
            "workloads": [{
                "id": row["id"],
                "target_exit": {
                    "event": {key: row["target_exit"]["assessment"]["event"][key]
                              for key in SEMANTIC_EVENT_FIELDS},
                    "assessment": {key: copy.deepcopy(row["target_exit"]["assessment"][key])
                                   for key in SEMANTIC_ASSESSMENT_FIELDS},
                },
            } for row in profile["workloads"]],
        } for profile in record["profiles"]],
    }


def run_ids(record):
    """Return validated run IDs for a caller's cross-record freshness check.

    Invalid records return an empty set. A comparator must reject validation
    errors before checking that the two accepted records have disjoint sets.
    """
    if validate_extension(record):
        return set()
    return {row["target_exit"]["binding"]["run_id"]
            for profile in record["profiles"] for row in profile["workloads"]}
