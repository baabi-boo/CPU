#!/usr/bin/env python3
"""Assess the fixed G1 workload expectations in retained simulator logs.

These checks describe an observed protocol, not trusted execution or hardware
qualification. The caller must separately bind the logs and real exit status
to the identified simulator, target binary, limits, and source provenance.
The deliberate failure workload is assessed independently of ordinary success:
an arbitrary nonzero exit, crash, or timeout never satisfies that control.
"""

import argparse
import importlib.util
import json
from pathlib import Path
import re


def _sibling(name):
    specification = importlib.util.spec_from_file_location(
        "nova_workload_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


evidence = _sibling("target_evidence")
plan = _sibling("campaign_plan")
HELLO_MARKER = "Hello world from core 0, a rocket"
NEGATIVE_MARKER = "NOVA_BASELINE_V1 EXPECTED_FAIL hart=0 code=7"
# Match the terminal-record namespaces even when an otherwise valid line is
# accompanied by a prefixed, lowercased, or malformed conflicting record.
TERMINAL_NAMESPACE = re.compile(
    rb"NOVA_BASELINE|hello[ \t]+world[ \t]+from[ \t]+core", re.IGNORECASE
)
NEGATIVE_ASSERTION = re.compile(
    rb"(?:Assertion failed:[ \t]*)?\*\*\* FAILED \*\*\* "
    rb"\(exit code =[ \t]+7\)[ \t]*\n"
)
# Verilator may print this trailer after the Chisel assertion. Other error
# diagnostics remain failures until their actual pinned format is reviewed.
VERILATOR_STOP = re.compile(
    rb"(?:\[[0-9]+\] )?%Error: [^\r\n]+\.s?v:[0-9]+: Verilog \$stop\n"
)
UNEXPECTED_FAILURE = re.compile(
    rb"\b(?:fail|failed|fatal|timeout|timed[ \t]+out|segmentation[ \t]+fault)\b"
    rb"|%Error(?:\b|:)", re.IGNORECASE
)
SUCCESS_WORDING = re.compile(
    rb"\b(?:pass|passed|success|succeeded)\b|\bcompleted[ \t]+after\b", re.IGNORECASE)
# Timeout/launcher/interruption results are not target failures. A direct
# Verilator assertion typically produces -SIGABRT (-6); a wrapper may report
# 134. Neither is treated as the target's own HTIF exit value.
EXCLUDED_EXITS = {0, 124, 125, 126, 127, 130, 137, 139, 143}


def workload_contract(identifier):
    """Return a fresh fixed workload row, or None for an unknown identifier."""
    if not isinstance(identifier, str):
        return None
    for item in plan.SMOKE_WORKLOADS:
        if item["id"] == identifier:
            return {"kind": "smoke", "binary_origin": "repository", **item}
    if identifier in plan.ISA_TESTS:
        return {
            "id": identifier, "kind": "isa", "binary_origin": "riscv_prefix",
            "binary": plan.ISA_BINARY_DIRECTORY + "/" + identifier,
            "expected_target_exit": 0, "expected_marker": None,
            "output_contract": "completion-protocol",
        }
    return None


def _validated_contract(workload):
    if not isinstance(workload, dict):
        return None
    expected = workload_contract(workload.get("id"))
    if expected is None:
        return None
    for key in ("id", "kind", "expected_target_exit", "expected_marker", "output_contract"):
        if key not in workload or workload[key] != expected[key]:
            return None
    if type(workload["expected_target_exit"]) is not int:
        return None
    for key in ("binary_origin", "binary"):
        if key in workload and workload[key] != expected[key]:
            return None
    return expected


def _result():
    return {
        "status": "failed", "expectation_met": False,
        "target_completion_verified": False,
        "completion_protocol_observed": False,
        "expected_target_failure_verified": False,
        "cycles": None, "reasons": [],
        "hardware_qualified": False, "g1_gate_passed": False,
        "evidence_scope": "observed_workload_protocol_only",
        "stdout_bytes": None, "stdout_sha256": None,
        "stderr_bytes": None, "stderr_sha256": None,
    }


def _negative(stdout_path, stderr_path, exit_code, max_cycles):
    result = _result()
    reasons = result["reasons"]
    if (type(exit_code) is not int or exit_code in EXCLUDED_EXITS
            or not (-6 == exit_code or 1 <= exit_code <= 255)):
        reasons.append("simulator result is not a supported nonzero target-failure termination")
    if type(max_cycles) is not int or not 1 <= max_cycles <= evidence.MAX_CYCLE_COUNT:
        reasons.append("max_cycles must be an integer within 1..2^64-1")
    if reasons:
        return result

    logs = {}
    for label, path in (("stdout", stdout_path), ("stderr", stderr_path)):
        try:
            logs[label] = evidence._read_log(path)
            result[label + "_bytes"] = logs[label]["bytes"]
            result[label + "_sha256"] = logs[label]["sha256"]
        except evidence._LogFailure as error:
            reasons.append(label + " " + str(error))
    if len(logs) != 2:
        return result
    if logs["stdout"]["identity"] == logs["stderr"]["identity"]:
        reasons.append("stdout and stderr must be separate files")

    marker = NEGATIVE_MARKER.encode("ascii") + b"\n"
    target_records = 0
    for line in logs["stdout"]["data"].splitlines(keepends=True):
        if line == marker:
            target_records += 1
            continue
        if TERMINAL_NAMESPACE.search(line):
            reasons.append("stdout contains a conflicting or malformed target record")
        if UNEXPECTED_FAILURE.search(line) or SUCCESS_WORDING.search(line):
            reasons.append("stdout contains an unexpected success or failure diagnostic")
    if target_records != 1:
        reasons.append("stdout must contain exactly one expected negative-control record")

    assertions = 0
    trailers = 0
    for line in logs["stderr"]["data"].splitlines(keepends=True):
        if NEGATIVE_ASSERTION.fullmatch(line):
            assertions += 1
            continue
        if VERILATOR_STOP.fullmatch(line) and assertions == 1:
            trailers += 1
            continue
        if TERMINAL_NAMESPACE.search(line):
            reasons.append("target output appeared on the simulator diagnostic stream")
        if UNEXPECTED_FAILURE.search(line) or SUCCESS_WORDING.search(line):
            reasons.append("stderr contains a conflicting success, failure, or timeout diagnostic")
    if assertions != 1:
        reasons.append("stderr must contain exactly one pinned SimTSI target exit-code-7 assertion")
    if trailers > 1:
        reasons.append("stderr contains repeated Verilator termination trailers")
    if not reasons:
        result["status"] = "passed"
        result["expectation_met"] = True
        result["expected_target_failure_verified"] = True
    return result


def _check_positive_terminal_records(result, stdout_path, stderr_path, marker):
    """Reject contradictory workload records in the same bounded log snapshot.

    The generic parser owns completion grammar and exact-marker counting. The
    workload-specific check permits only that exact marker in either known
    target namespace, and only on stdout. ISA tests have no such marker and
    must not borrow a hello or NOVA result from another workload.
    """
    expected = marker.encode("utf-8") + b"\n" if marker is not None else None
    for label, path in (("stdout", stdout_path), ("stderr", stderr_path)):
        try:
            log = evidence._read_log(path)
        except evidence._LogFailure as error:
            result["reasons"].append(label + " " + str(error))
            continue
        if (log["sha256"] != result[label + "_sha256"]
                or log["bytes"] != result[label + "_bytes"]):
            result["reasons"].append(label + " changed between protocol and workload checks")
            continue
        for line in log["data"].splitlines(keepends=True):
            if TERMINAL_NAMESPACE.search(line) and not (label == "stdout" and line == expected):
                result["reasons"].append(label + " contains a conflicting or malformed target record")
                break
    if result["reasons"]:
        result["status"] = "failed"
        result["completion_protocol_observed"] = False


def assess_workload(stdout_path, stderr_path, exit_code, workload, max_cycles=10000000):
    """Check the fixed workload's observed result without running or writing.

    Positive workload records require the TestDriver completion protocol;
    this does not establish target exit cause. Hello additionally requires the
    inherited Rocket-specific line; that hard-coded core number is not runtime
    hart identification. Conflicting target terminal records fail. Negative
    control success requires the expected target record and SimTSI assertion,
    not merely a failed process. No result accepts G1 or authenticates artifacts.
    """
    contract = _validated_contract(workload)
    if contract is None:
        result = _result()
        result["reasons"].append("workload differs from the fixed G1 expectation contract")
        return result
    if contract["id"] == "nova-baseline-fail":
        return _negative(stdout_path, stderr_path, exit_code, max_cycles)
    marker = HELLO_MARKER if contract["id"] == "hello" else contract["expected_marker"]
    observed = evidence.assess_simulation(
        stdout_path, stderr_path, exit_code, expected_marker=marker, max_cycles=max_cycles)
    result = _result()
    result.update(observed)
    result["evidence_scope"] = "observed_workload_protocol_only"
    if result["status"] == "passed":
        _check_positive_terminal_records(result, stdout_path, stderr_path, marker)
    result["expectation_met"] = result["status"] == "passed"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--stderr", type=Path, required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--workload", choices=[item["id"] for item in plan.SMOKE_WORKLOADS]
                        + list(plan.ISA_TESTS), required=True)
    parser.add_argument("--max-cycles", type=int, default=10000000)
    args = parser.parse_args(argv)
    result = assess_workload(args.stdout, args.stderr, args.exit_code,
                             workload_contract(args.workload), args.max_cycles)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
