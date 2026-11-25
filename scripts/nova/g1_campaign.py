#!/usr/bin/env python3
"""Plan or run fixed G1 workloads; never provision a toolchain or accept G1.

The read-only plan does not access the network. Explicit builds can resolve JVM
dependencies under the operator's separately approved network/resource policy.
"""

import argparse
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
CONDA_LOCK = "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-64-lean.conda-lock.yml"
PROFILE_PATH = "nova/g1-profile.json"
WORKLOADS_PATH = "nova/g1-workloads.json"
MAX_LOG_BYTES = 64 * 1024 * 1024
MAX_CYCLES = 10000000
SEED = 1
CLEANUP_RESERVE_SECONDS = 10
OBSERVER_MANIFEST_PATH = "nova-out/htif-observer/manifest.json"
MAX_WITNESS_BYTES = 4096
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
CONFIGURATIONS = ("RocketConfig", "NovaM1BaselineConfig")
LIMITATIONS = [
    "Workload observations are not hardware qualification or a G1 gate pass.",
    "A second independent clean checkout and retained evidence review are required.",
    "Spike reference comparison is not run; T-ISA-001 and full ISA certification remain open.",
    "Installed Conda metadata matching does not verify installed binary contents.",
    "Known prerequisites do not establish complete nested or Maven dependency closure.",
    "Pinned HTIF success can also follow signal_exit; protocol observations do not attest target exit cause.",
    "Unrun rows in a blocked or failed campaign are not accepted or skipped coverage.",
    "The enumerated build-override policy does not attest to arbitrary inherited environment or tool contents.",
    "Cancellation is checked between bounded operations; final evidence capture is not an instantaneous wall-clock kill.",
]
# Reject even empty overrides; values may be private and are never recorded.
FORBIDDEN_ENV = frozenset({
    "USE_CHISEL7", "MAKEFLAGS", "MFLAGS", "GNUMAKEFLAGS", "MAKEFILES", "MAKEOVERRIDES",
    "CONFIG", "CONFIG_PACKAGE", "SUB_PROJECT", "SBT_PROJECT", "MODEL", "VLOG_MODEL",
    "MODEL_PACKAGE", "GENERATOR_PACKAGE", "TOP", "SIM_FLAGS", "EXTRA_SIM_FLAGS",
    "BINARY", "BINARIES", "BINARY_ARGS", "LOADMEM", "LOADARCH", "TIMEOUT_CYCLES",
    "RANDOM_SEED", "VERBOSE_FLAGS", "JAVA_HEAP_SIZE", "JAVA_TMP_DIR", "JAVA_TOOL_OPTIONS",
    "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "SBT_OPTS", "SBT", "SBT_COMMAND", "FIRTOOL_BIN",
    "FIRTOOL_EXTRA_FLAGS", "CLASSPATH_CACHE", "GENERATOR_CLASSPATH", "TAPEOUT_CLASSPATH",
    "EXTRA_GENERATOR_REQS", "EXTRA_SIM_CXXFLAGS", "EXTRA_SIM_LDFLAGS", "EXTRA_SIM_SOURCES",
    "EXTRA_SIM_REQS", "EXTRA_SIM_OUT_NAME", "EXT_FILELISTS", "EXT_INCDIRS", "NUMACTL",
    "VERILATOR", "VERILATOR_ROOT", "VERILATOR_THREADS", "VERILATOR_PROFILE",
    "VERILATOR_OPT_FLAGS", "VERILATOR_OPTS", "USE_FST", "CC", "CXX", "AR", "CFLAGS",
    "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "LD_PRELOAD", "LD_AUDIT", "CMAKE_TOOLCHAIN_FILE",
    "CMAKE_GENERATOR", "CMAKE_GENERATOR_PLATFORM", "CMAKE_GENERATOR_TOOLSET",
    "CMAKE_PROJECT_INCLUDE", "CMAKE_PROJECT_INCLUDE_BEFORE", "CMAKE_PROJECT_TOP_LEVEL_INCLUDES",
    "CMAKE_MAKE_PROGRAM", "base_dir", "sim_dir", "build_dir", "output_dir", "sim",
    "sim_debug", "sim_prefix", "long_name", "timeout_cycles",
    "CLOCK_PERIOD", "RESET_DELAY", "EXTRA_SIM_PREPROC_DEFINES", "EXTRA_CHISEL_OPTIONS",
    "TB", "MFC_BASE_LOWERING_OPTIONS", "TOP_MACROCOMPILER_MODE", "ENABLE_YOSYS_FLOW",
    "SED", "FIRRTL_FILE", "ANNO_FILE", "CHISEL_LOG_FILE", "FIRTOOL_LOG_FILE",
    "MFC_EXTRA_ANNO_FILE", "FINAL_ANNO_FILE", "MFC_TOP_HRCHY_JSON", "MFC_MODEL_HRCHY_JSON",
    "MFC_MODEL_HRCHY_JSON_UNIQUIFIED", "MFC_SMEMS_CONF", "TOP_SMEMS_CONF", "TOP_SMEMS_FILE",
    "TOP_SMEMS_FIR", "MODEL_SMEMS_CONF", "MODEL_SMEMS_FILE", "MODEL_SMEMS_FIR",
    "TOP_MODS_FILELIST", "MODEL_MODS_FILELIST", "BB_MODS_FILELIST", "ALL_MODS_FILELIST",
    "sim_files", "sim_common_files", "MFC_LOWERING_OPTIONS", "generated_src_name",
    "GEN_COLLATERAL_DIR", "DUMP_BINARY", "BINARIES_DIR", "BREAK_SIM_PREREQ",
    "RV64GC_ISA_TEST_PREFIXES", "RV64GC_ASM_TEST_EXCLUDES", "RV64GC_ASM_TESTS",
    "RISCV_BMARK_TEST_NAMES", "RISCV_BMARK_TESTS", "SIM_PREPROC_DEFINES",
    "VERILATOR_FLAGS", "VERILATOR_CXXFLAGS", "VERILATOR_LDFLAGS",
    "LRISCV", "SIM_LDFLAGS", "NOVA_HTIF_OBSERVER_DIR", "NOVA_HTIF_WITNESS_PATH",
    "NOVA_HTIF_RUN_ID", "NOVA_HTIF_BINDING_SHA256",
})
_CANCELLATION = ContextVar("nova_campaign_cancellation", default=None)


@contextmanager
def _cancellation_scope():
    """Latch signals without raising across file/process creation or cleanup."""
    if threading.current_thread() is not threading.main_thread():
        raise ValueError("campaign execution requires the main thread for cancellation handling")
    state = {"signal": None}
    token = _CANCELLATION.set(state)
    previous = {}

    def interrupted(number, _frame):
        if state["signal"] is None:
            state["signal"] = number

    def restore_handlers():
        # The record owner can restore while its exclusive descriptor is still
        # open. Keep the latch available until that record has been reconciled.
        for number, handler in list(previous.items()):
            signal.signal(number, handler)
            del previous[number]

    try:
        for number in (signal.SIGINT, signal.SIGTERM):
            previous[number] = signal.signal(number, interrupted)
        yield restore_handlers
    finally:
        try:
            restore_handlers()
        finally:
            _CANCELLATION.reset(token)


def _check_cancellation():
    state = _CANCELLATION.get()
    if state is not None and state["signal"] is not None:
        raise CampaignStop("blocked", "campaign interrupted by " +
                           signal.Signals(state["signal"]).name + "; remaining workloads not run")


def _retain_cancellation(record):
    try:
        _check_cancellation()
    except CampaignStop as exc:
        if record["status"] != "failed":
            record["status"] = "blocked"
        if str(exc) not in record["reasons"]:
            record["reasons"].append(str(exc))


@lru_cache(maxsize=None)
def _module(name):
    """Load reviewed siblings even under spec_from_file_location tests."""
    spec = importlib.util.spec_from_file_location("nova_g1_campaign_" + name,
                                                SCRIPTS / (name + ".py"))
    if spec is None or spec.loader is None:
        raise ValueError("campaign helper cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# All tool/hardware boundaries are patchable for offline tests.
def build_plan(root, jobs=2, java_heap="4G", *, observe_target_exit=False):
    return _module("campaign_plan").build_plan(
        root, jobs=jobs, java_heap=java_heap, observe_target_exit=observe_target_exit)


def simulator_argv(root, config, binary, max_cycles=MAX_CYCLES, seed=SEED):
    return _module("campaign_plan").simulator_argv(root, config, binary, max_cycles=max_cycles, seed=seed)


def inspect_profile(root, env=None):
    return _module("g1_profile").inspect_profile(root, env=env)


def inspect_inventory(lock_path, prefix):
    return _module("conda_inventory").inspect_inventory(lock_path, prefix)


def collect_provenance(root):
    return _module("rocket_baseline").collect_provenance(root)


def capture_source(root):
    return _module("campaign_artifacts").capture_source(root)


def capture_file(root, path, kind="artifact", max_bytes=512 * 1024 * 1024):
    return _module("campaign_artifacts").capture_file(root, path, kind=kind, max_bytes=max_bytes)


def capture_profile_artifacts(root, configuration):
    return _module("campaign_artifacts").capture_profile_artifacts(root, configuration)


def run_command(cwd, output_dir, name, argv, timeout_seconds, min_free_gib=10,
                env=None, max_log_bytes=MAX_LOG_BYTES):
    return _module("campaign_exec").run_command(cwd, output_dir, name, argv, timeout_seconds,
                                               min_free_gib=min_free_gib, env=env,
                                               max_log_bytes=max_log_bytes)


def assess_workload(stdout_path, stderr_path, exit_code, workload, max_cycles=MAX_CYCLES):
    return _module("workload_assessment").assess_workload(stdout_path, stderr_path, exit_code,
                                                        workload, max_cycles=max_cycles)


def build_observer_metadata(manifest_path, *, root, environ):
    return _module("htif_observer").build_metadata(manifest_path, root=root, environ=environ)


def validate_observer_metadata(metadata):
    return _module("htif_observer").validate_build_metadata(metadata)


def assess_exit(path, *, run_id, binding_sha256, expected_target_exit):
    return _module("htif_exit_evidence").assess_exit(
        path, run_id=run_id, binding_sha256=binding_sha256,
        expected_target_exit=expected_target_exit)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def normalized_plan(plan, root):
    """Remove only the checkout prefix for cross-checkout plan identity."""
    prefix = str(root)

    def normalize(value):
        if isinstance(value, str):
            return value.replace(prefix + "/", "<repo>/") if value != prefix else "<repo>"
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        return value
    return normalize(plan)


def plan_digest(plan, root):
    serialized = json.dumps(normalized_plan(plan, root), sort_keys=True,
                            separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def resource_limits(args):
    values = {"jobs": args.jobs, "java_heap": args.java_heap,
              "total_timeout_seconds": args.total_timeout_seconds,
              "min_free_gib": args.min_free_gib,
              "max_log_bytes": MAX_LOG_BYTES, "max_cycles": MAX_CYCLES, "seed": SEED}
    for name, lower, upper in (("jobs", 1, 2), ("total_timeout_seconds", 300, 7200),
                               ("min_free_gib", 1, 50)):
        if type(values[name]) is not int or not lower <= values[name] <= upper:
            raise ValueError(name + " is outside its approved bounded range")
    if not isinstance(args.java_heap, str) or not re.fullmatch(r"[1-8]G", args.java_heap):
        raise ValueError("java_heap must be 1G..8G")
    return values


def stale_products(root):
    """Refuse known generated products; never delete anything."""
    known = ("tests/build", "software/nova/baseline/build", "sims/verilator/generated-src",
             "sims/verilator/output", ".classpath_cache", ".java_tmp", "target",
             "project/target", "project/project/target")
    found = [relative for relative in known
             if (root / relative).exists() or (root / relative).is_symlink()]
    for config in CONFIGURATIONS:
        found.extend(str(path.relative_to(root)) for path in
                     (root / "sims/verilator").glob("simulator-*-" + config + "*"))
    return sorted(set(found))


def make_output_dir(root):
    output = root / "nova-out"
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise ValueError("unsafe campaign output root")
    output.mkdir(mode=0o700, exist_ok=True)
    if output.resolve(strict=True) != output or not output.is_relative_to(root):
        raise ValueError("campaign output root escapes checkout")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = output / ("g1-campaign-" + stamp)
    directory.mkdir(mode=0o700)
    return directory


class CampaignStop(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status


def _safe_prefix(env, name):
    raw = env.get(name, "")
    if (not isinstance(raw, str) or not raw or any(ord(char) < 32 for char in raw)
            or "\\" in raw or ".." in Path(raw).parts):
        raise CampaignStop("blocked", name + " must identify an existing absolute prepared prefix")
    path = Path(raw)
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        raise CampaignStop("blocked", name + " must identify an existing absolute prepared prefix")
    return path.resolve(strict=True)


def _require_source(snapshot):
    if (not isinstance(snapshot, dict) or snapshot.get("clean") is not True
            or not isinstance(snapshot.get("revision"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", snapshot["revision"])
            or not isinstance(snapshot.get("tree"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", snapshot["tree"])
            or not SHA256.fullmatch(str(snapshot.get("state_digest", "")))
            or not SHA256.fullmatch(str(snapshot.get("checkout_identity_sha256", "")))
            or not isinstance(snapshot.get("lock_hashes"), dict)
            or not isinstance(snapshot.get("source_inputs"), dict)
            or not isinstance(snapshot.get("submodules"), list)):
        raise CampaignStop("blocked", "source checkout and submodule identity must be complete and clean")


def _remaining(deadline):
    _check_cancellation()
    seconds = math.floor(deadline - time.monotonic() - CLEANUP_RESERVE_SECONDS)
    if seconds < 1:
        raise CampaignStop("blocked", "aggregate wall-clock budget exhausted; remaining workloads not run")
    return seconds


def _safe_logs(directory, stage):
    """Bind retained separate streams to the engine's recorded hashes."""
    paths = []
    for stream in ("stdout", "stderr"):
        name = stage.get(stream)
        recorded = stage.get(stream + "_sha256")
        if (not isinstance(name, str) or not name or Path(name).name != name
                or name in {".", ".."} or not SHA256.fullmatch(str(recorded))):
            raise CampaignStop("failed", "execution did not retain safely named, hashed separate streams")
        path = directory / name
        actual = capture_file(directory, path, max_bytes=MAX_LOG_BYTES)
        if (actual["sha256"] != recorded or type(stage.get(stream + "_bytes")) is not int
                or actual["size_bytes"] != stage[stream + "_bytes"]):
            raise CampaignStop("failed", "execution stream changed after it was recorded")
        paths.append(path)
    if paths[0] == paths[1]:
        raise CampaignStop("failed", "stdout and stderr must be distinct retained files")
    return paths


def _stage(root, directory, name, argv, requested, deadline, resources, env, cwd=None):
    seconds = min(requested, _remaining(deadline))
    result = run_command(cwd or root, directory, name, argv, seconds,
                         min_free_gib=resources["min_free_gib"], env=env,
                         max_log_bytes=resources["max_log_bytes"])
    if not isinstance(result, dict):
        raise CampaignStop("failed", "execution engine returned no stage record")
    if result.get("command") != list(argv):
        raise CampaignStop("failed", "execution engine command differs from the declared stage")
    return {"id": name, "timeout_seconds": seconds, **result}


def _require_command_passed(directory, result):
    if result.get("status") == "blocked":
        raise CampaignStop("blocked", result.get("reason") or "command was blocked")
    _safe_logs(directory, result)
    if (result.get("status") != "passed" or type(result.get("exit_code")) is not int
            or result["exit_code"] != 0 or result.get("timed_out") or result.get("reason")):
        raise CampaignStop("failed", result.get("reason") or "build or pinned-input check did not pass")


def _new_record(resources, *, observe_target_exit=False):
    record = {
        "schema_version": 1, "kind": "nova-g1-campaign", "status": "blocked",
        "source_before": None, "source_after": None, "plan_sha256": None,
        "declared_plan": None, "execution_paths": None, "elapsed_seconds": None,
        "profile_sha256": None, "workloads_sha256": None,
        "provenance_before": None, "provenance_after": None, "inventory": None,
        "inventory_after": None, "profile_after": None,
        "resource_limits": resources, "common_stages": [], "profiles": [],
        "started_utc": utc_now(), "finished_utc": None,
        "hardware_qualified": False, "g1_gate_passed": False,
        "reference_comparison": "not_run", "limitations": list(LIMITATIONS),
        "preflight": {}, "reasons": [],
    }
    if observe_target_exit:
        record.update(schema_version=2, target_exit_observer=None)
    return record


def _prepare_rows(record, plan):
    for profile in plan["profiles"]:
        record["profiles"].append({
            "configuration": profile["configuration"],
            "build": {"status": "not_run"},
            "artifacts": {"status": "blocked", "artifacts": [], "reasons": ["profile not built"]},
            "workloads": [{"id": row["id"], "binary": None,
                           "binary_origin": row["binary_origin"],
                           "binary_after": None, "simulator_sha256": None,
                           "simulator_sha256_after": None,
                           "stage": {"status": "not_run"}, "assessment": None}
                          for row in profile["workloads"]],
        })
        if record["schema_version"] == 2:
            for row in record["profiles"][-1]["workloads"]:
                row["target_exit"] = {"status": "not_run"}


def _preflight(root, directory, plan, record, deadline, env):
    forbidden = sorted(FORBIDDEN_ENV.intersection(env) |
                       {name for name in env if name.startswith("NOVA_HTIF_")})
    if forbidden:
        raise CampaignStop("blocked", "inherited profile/build overrides must be unset: " + ", ".join(forbidden))
    _require_source(record["source_before"])
    stale = stale_products(root)
    observer_output = root / Path(OBSERVER_MANIFEST_PATH).parent
    if (record["schema_version"] == 2
            and (observer_output.exists() or observer_output.is_symlink())):
        stale.append(str(observer_output.relative_to(root)))
    if stale:
        raise CampaignStop("blocked", "stale generated products require a separate fresh checkout: " + ", ".join(stale))
    riscv = _safe_prefix(env, "RISCV")
    record["execution_paths"]["riscv_prefix"] = str(riscv)
    prefix = _safe_prefix(env, "CONDA_PREFIX")
    if not (root / "env.sh").is_file():
        raise CampaignStop("blocked", "prepared env.sh is absent; setup is never run automatically")
    if shutil.disk_usage(root).free < record["resource_limits"]["min_free_gib"] * 1024 ** 3:
        raise CampaignStop("blocked", "available disk is below the approved floor")
    _remaining(deadline)
    profile = inspect_profile(root, env=env)
    record["preflight"]["profile"] = profile
    if (not isinstance(profile, dict) or profile.get("status") != "ready"
            or profile.get("profile") != "g1-chisel6-rocket"
            or profile.get("known_prerequisites_present") is not True
            or profile.get("toolchain_version_inputs_verified") is not True
            or profile.get("hardware_qualified") is not False
            or profile.get("g1_gate_passed") is not False or profile.get("blockers") != []):
        raise CampaignStop("blocked", "exact G1 profile known-prerequisite inspection is not ready")
    _remaining(deadline)
    inventory = inspect_inventory(root / CONDA_LOCK, prefix)
    record["inventory"] = inventory
    expected_lock = record["source_before"]["lock_hashes"].get(CONDA_LOCK)
    if (not isinstance(inventory, dict) or inventory.get("status") != "matched"
            or inventory.get("blockers") != [] or not SHA256.fullmatch(str(expected_lock))
            or inventory.get("lock_sha256") != expected_lock
            or inventory.get("metadata_only") is not True
            or inventory.get("hardware_qualified") is not False
            or inventory.get("g1_gate_passed") is not False):
        raise CampaignStop("blocked", "installed Conda inventory does not match the pinned source lock")
    _remaining(deadline)
    record["provenance_before"] = collect_provenance(root)
    if (not isinstance(record["provenance_before"], dict)
            or record["provenance_before"].get("capture_complete") is not True):
        raise CampaignStop("blocked", "pre-execution legacy provenance capture is incomplete")
    checker = _stage(root, directory, "pinned-input-check",
                     [sys.executable, "-B", "scripts/nova/check.py"], 120, deadline,
                     record["resource_limits"], env)
    record["preflight"]["checker"] = checker
    _require_command_passed(directory, checker)
    # Every exact installed ISA input is checked before expensive builds.
    for workload in plan["profiles"][0]["workloads"]:
        if workload["binary_origin"] == "riscv_prefix":
            capture_file(riscv, riscv / workload["binary"], kind="riscv_elf")
    _remaining(deadline)
    return riscv


def _verify_observer(root, record, env):
    """Capture once, then revalidate every recorded observer build identity."""
    _check_cancellation()
    previous = record["target_exit_observer"]
    try:
        current = build_observer_metadata(root / OBSERVER_MANIFEST_PATH,
                                          root=root, environ=env)
        validate_observer_metadata(current)
        if current["manifest_path"] != OBSERVER_MANIFEST_PATH:
            raise ValueError("observer manifest differs from the declared fixed path")
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        status = "blocked" if previous is None else "failed"
        raise CampaignStop(status, "observer build evidence unavailable: " + str(exc)) from exc
    if previous is None:
        record["target_exit_observer"] = current
    elif current != previous:
        raise CampaignStop("failed", "observer build metadata changed during campaign")
    _check_cancellation()


def _exit_binding(record, configuration, workload_id, binary_sha256,
                  simulator_sha256, run_id):
    source = record["source_before"]
    binding = {
        "schema_version": 1, "configuration": configuration,
        "workload_id": workload_id, "run_id": run_id,
        "binary_sha256": binary_sha256, "simulator_sha256": simulator_sha256,
        "observer_manifest_sha256": record["target_exit_observer"]["manifest_sha256"],
        "source_revision": source["revision"], "source_tree": source["tree"],
        "source_state_digest": source["state_digest"],
        "max_cycles": record["resource_limits"]["max_cycles"],
        "seed": record["resource_limits"]["seed"],
    }
    for field in ("run_id", "binary_sha256", "simulator_sha256",
                  "observer_manifest_sha256", "source_state_digest"):
        if type(binding[field]) is not str or SHA256.fullmatch(binding[field]) is None:
            raise CampaignStop("failed", "invalid observer binding identity: " + field)
    if any(type(binding[field]) is not int for field in ("schema_version", "max_cycles", "seed")):
        raise CampaignStop("failed", "observer binding resource values must be integers")
    return binding


def _binding_digest(binding):
    return hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def _capture_witness(directory, path):
    return capture_file(directory, path, kind="htif_exit_witness", max_bytes=MAX_WITNESS_BYTES)


def _fail_exit_assessment(target_exit, reason):
    """A failed capture/recheck must not retain an optimistic observer flag."""
    previous = target_exit.get("assessment")
    if not isinstance(previous, dict):
        previous = {}
    reasons = previous.get("reasons")
    reasons = list(reasons) if isinstance(reasons, list) else []
    if reason not in reasons:
        reasons.append(reason)
    target_exit["assessment"] = {
        "status": "failed", "target_exit_observed": False,
        "target_completion_verified": False, "hardware_qualified": False,
        "g1_gate_passed": False, "reasons": reasons,
        "witness_sha256": previous.get("witness_sha256"),
        "witness_bytes": previous.get("witness_bytes"), "event": previous.get("event"),
    }


def _assess_target_exit(directory, path, row, workload):
    target_exit = row["target_exit"]
    binding = target_exit["binding"]
    try:
        _check_cancellation()
        # Even a missing or unsafe file gets the parser's diagnostic assessment;
        # an unsuccessful independent capture can never authorize its result.
        capture_error = None
        try:
            target_exit["witness"] = _capture_witness(directory, path)
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            capture_error = exc
        assessment = assess_exit(path, run_id=binding["run_id"],
                                 binding_sha256=_binding_digest(binding),
                                 expected_target_exit=workload["expected_target_exit"])
        target_exit["assessment"] = assessment
        if capture_error is not None:
            raise CampaignStop("failed", "dedicated HTIF witness could not be safely captured")
        if _capture_witness(directory, path) != target_exit["witness"]:
            raise CampaignStop("failed", "dedicated HTIF witness changed during assessment")
        witness = target_exit["witness"]
        if (not isinstance(assessment, dict) or assessment.get("status") != "observed"
                or assessment.get("target_exit_observed") is not True
                or assessment.get("target_completion_verified") is not True
                or assessment.get("hardware_qualified") is not False
                or assessment.get("g1_gate_passed") is not False
                or assessment.get("reasons") != []
                or assessment.get("witness_sha256") != witness["sha256"]
                or type(assessment.get("witness_bytes")) is not int
                or assessment["witness_bytes"] != witness["size_bytes"]):
            raise CampaignStop("failed", "dedicated HTIF target exit not verified: " + workload["id"])
        _check_cancellation()
    except CampaignStop as exc:
        _fail_exit_assessment(target_exit, str(exc))
        raise
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        reason = "dedicated HTIF witness evidence unavailable: " + str(exc)
        _fail_exit_assessment(target_exit, reason)
        raise CampaignStop("failed", reason) from exc


def _recheck_witnesses(directory, record):
    for profile in record["profiles"]:
        for row in profile["workloads"]:
            _check_cancellation()
            target_exit = row["target_exit"]
            witness = target_exit.get("witness")
            if witness is None:
                continue
            try:
                name = witness["path"]
                if (not isinstance(name, str) or not name or Path(name).name != name
                        or name in {".", ".."}):
                    raise ValueError("witness path is not a retained basename")
                if _capture_witness(directory, directory / name) != witness:
                    raise ValueError("witness content changed")
            except (OSError, ValueError, TypeError, KeyError, RuntimeError):
                reason = "dedicated HTIF witness changed before finalization: " + row["id"]
                _fail_exit_assessment(target_exit, reason)
                # A mismatch must not prevent the remaining retained witnesses
                # from losing stale completion flags. Retain failure immediately
                # so a later cancellation cannot downgrade it to blocked.
                record["status"] = "failed"
                record["reasons"].append("post-execution observer evidence: " + reason)


def _run_workload(root, directory, profile, workload, row, simulator, riscv,
                  simulator_digest, binary_digest, deadline, resources, env,
                  *, observer_record=None, run_ids=None):
    if observer_record is not None:
        _verify_observer(root, observer_record, env)
    base = root if workload["binary_origin"] == "repository" else riscv
    binary = base / workload["binary"]
    row["binary"] = capture_file(base, binary, kind="riscv_elf")
    if row["binary"]["sha256"] != binary_digest:
        raise CampaignStop("failed", "declared workload binary changed between shared build and profile execution")
    before = capture_file(root, simulator, kind="simulator")
    row["simulator_sha256"] = before["sha256"]
    if before["sha256"] != simulator_digest:
        raise CampaignStop("failed", "simulator changed between profile build and workload")
    name = profile["configuration"] + "-" + workload["id"]
    argv = simulator_argv(root, profile["configuration"], binary,
                          max_cycles=resources["max_cycles"], seed=resources["seed"])
    stage_env = env
    witness_path = None
    if observer_record is not None:
        run_id = secrets.token_hex(32)
        if (type(run_id) is not str or SHA256.fullmatch(run_id) is None
                or run_ids is None or run_id in run_ids):
            raise CampaignStop("failed", "observer run identifier is invalid or reused")
        run_ids.add(run_id)
        binding = _exit_binding(observer_record, profile["configuration"], workload["id"],
                                row["binary"]["sha256"], before["sha256"], run_id)
        witness_path = directory / (name + ".htif-exit.json")
        if witness_path.exists() or witness_path.is_symlink():
            raise CampaignStop("failed", "dedicated HTIF witness path is not fresh")
        row["target_exit"] = {"witness": None, "binding": binding, "assessment": None}
        stage_env = {**env, "NOVA_HTIF_WITNESS_PATH": str(witness_path),
                     "NOVA_HTIF_RUN_ID": run_id,
                     "NOVA_HTIF_BINDING_SHA256": _binding_digest(binding)}
    row["stage"] = _stage(root, directory, name, argv,
                          profile["simulation_limits"]["timeout_seconds"],
                          deadline, resources, stage_env, cwd=Path(profile["simulation_cwd"]))
    if witness_path is not None:
        # Retain bytes from a failed process when safe, without assessing them
        # as target completion or letting capture errors override process status.
        try:
            row["target_exit"]["witness"] = _capture_witness(directory, witness_path)
        except (OSError, ValueError, TypeError, RuntimeError):
            pass
        _check_cancellation()
    row["binary_after"] = capture_file(base, binary, kind="riscv_elf")
    after = capture_file(root, simulator, kind="simulator")
    row["simulator_sha256_after"] = after["sha256"]
    if row["binary"] != row["binary_after"] or before != after:
        raise CampaignStop("failed", "workload or simulator binary changed while executing")
    stage = row["stage"]
    if stage.get("status") == "blocked" or stage.get("interrupted"):
        raise CampaignStop("blocked", stage.get("reason") or "workload execution blocked")
    logs = _safe_logs(directory, stage)
    if (stage.get("status") not in {"passed", "failed"}
            or type(stage.get("exit_code")) is not int or stage.get("timed_out")
            or stage.get("reason") not in {None, "", "command exited unsuccessfully"}):
        raise CampaignStop("failed", stage.get("reason") or "workload did not produce an intact process result")
    if stage["exit_code"] == 125:
        raise CampaignStop("failed", "workload process reported reserved observer failure 125")
    negative = workload["expected_target_exit"] != 0
    if negative:
        if (stage["status"] != "failed" or stage["exit_code"] == 0
                or stage.get("reason") != "command exited unsuccessfully"):
            raise CampaignStop("failed", "negative control lacks an ordinary nonzero process result")
    elif stage["status"] != "passed" or stage["exit_code"] != 0 or stage.get("reason"):
        raise CampaignStop("failed", "positive workload process did not finish successfully")
    # Nonzero host failure alone is not evidence of the deliberate target fail.
    row["assessment"] = assess_workload(logs[0], logs[1], stage["exit_code"], workload,
                                        max_cycles=resources["max_cycles"])
    assessment = row["assessment"]
    if not isinstance(assessment, dict):
        raise CampaignStop("failed", "workload assessment is unavailable")
    for stream in ("stdout", "stderr"):
        for suffix in ("_sha256", "_bytes"):
            if assessment.get(stream + suffix) != stage.get(stream + suffix):
                raise CampaignStop("failed", "workload assessment is not bound to the retained execution streams")
    _safe_logs(directory, stage)
    completion = ("expected_target_failure_verified" if workload["expected_target_exit"]
                  else "completion_protocol_observed")
    if (not isinstance(assessment, dict) or assessment.get("status") != "passed"
            or assessment.get("expectation_met") is not True
            or assessment.get(completion) is not True
            or assessment.get("target_completion_verified") is not False
            or assessment.get("hardware_qualified") is not False
            or assessment.get("g1_gate_passed") is not False or assessment.get("reasons") != []):
        raise CampaignStop("failed", "declared workload expectation not verified: " + workload["id"])
    if observer_record is not None:
        _verify_observer(root, observer_record, env)
        _assess_target_exit(directory, witness_path, row, workload)


def _retain_final_state(record, deadline, *, refresh_clock=True):
    """Reconcile acceptance after bounded final work, without endless rewrites."""
    before = (record["status"], len(record["reasons"]))
    now = time.monotonic()
    if now > deadline:
        reason = "aggregate wall-clock deadline exceeded; campaign is not accepted"
        if reason not in record["reasons"]:
            record["reasons"].append(reason)
        if record["status"] != "failed":
            record["status"] = "blocked"
    _retain_cancellation(record)
    if refresh_clock or before != (record["status"], len(record["reasons"])):
        record["elapsed_seconds"] = round(now - (
            deadline - record["resource_limits"]["total_timeout_seconds"]), 6)
        record["finished_utc"] = utc_now()
        _retain_cancellation(record)
    return before != (record["status"], len(record["reasons"]))


def _write_record(stream, record):
    """Reuse the exclusively created descriptor, including for corrections."""
    stream.seek(0)
    stream.truncate()
    json.dump(record, stream, sort_keys=True, indent=2, allow_nan=False)
    stream.write("\n")
    stream.flush()


def _finalize(root, record, deadline, env, *, directory=None):
    """Retain post-run identity even on failure; never manufacture success."""
    try:
        _check_cancellation()
        record["source_after"] = capture_source(root)
        _check_cancellation()
        if record["source_before"] is not None and record["source_after"] != record["source_before"]:
            raise CampaignStop("failed", "source identity, pinned inputs, or submodule state changed during campaign")
        _require_source(record["source_after"])
    except (OSError, ValueError, RuntimeError, CampaignStop) as exc:
        record["reasons"].append("post-execution source capture: " + str(exc))
        if record["status"] != "failed":
            record["status"] = exc.status if isinstance(exc, CampaignStop) else "blocked"
    try:
        # If environment preflight stopped early, missing provenance stays
        # explicit. Do not run version probes under rejected JVM overrides.
        _check_cancellation()
        if record["provenance_before"] is None:
            raise CampaignStop("blocked", "provenance was not captured because preflight did not complete")
        record["provenance_after"] = collect_provenance(root)
        _check_cancellation()
        if (not isinstance(record["provenance_after"], dict)
                or record["provenance_after"].get("capture_complete") is not True):
            raise CampaignStop("blocked", "post-execution legacy provenance capture is incomplete")
        if (record["provenance_before"] is not None
                and record["provenance_before"] != record["provenance_after"]):
            raise CampaignStop("failed", "tool/lock/submodule provenance changed during campaign")
    except (OSError, ValueError, RuntimeError, CampaignStop) as exc:
        record["reasons"].append(str(exc))
        if record["status"] != "failed":
            record["status"] = exc.status if isinstance(exc, CampaignStop) else "blocked"
    try:
        _check_cancellation()
        if record["provenance_before"] is None:
            raise CampaignStop("blocked", "post-execution profile/inventory not probed because preflight did not complete")
        record["profile_after"] = inspect_profile(root, env=env)
        _check_cancellation()
        prefix = _safe_prefix(env, "CONDA_PREFIX")
        record["inventory_after"] = inspect_inventory(root / CONDA_LOCK, prefix)
        _check_cancellation()
        if record["profile_after"] != record["preflight"].get("profile"):
            raise CampaignStop("failed", "known profile or installed runtime collateral changed during campaign")
        if record["inventory_after"] != record["inventory"]:
            raise CampaignStop("failed", "installed Conda inventory changed during campaign")
    except (OSError, ValueError, RuntimeError, CampaignStop) as exc:
        record["reasons"].append(str(exc))
        if record["status"] != "failed":
            record["status"] = exc.status if isinstance(exc, CampaignStop) else "blocked"
    if record["schema_version"] == 2 and record["target_exit_observer"] is not None:
        try:
            _verify_observer(root, record, env)
            _recheck_witnesses(directory, record)
        except (OSError, ValueError, TypeError, KeyError, RuntimeError, CampaignStop) as exc:
            record["reasons"].append("post-execution observer evidence: " + str(exc))
            if record["status"] != "failed":
                record["status"] = exc.status if isinstance(exc, CampaignStop) else "failed"
    _retain_final_state(record, deadline)


def _execute(root, args, env=None, *, restore_handlers):
    """Return (record, path), retaining blocked/failed valid execution attempts."""
    if getattr(args, "approved_budget", False) is not True:
        raise ValueError("execution requires --approved-budget")
    resources = resource_limits(args)
    observe_target_exit = getattr(args, "observe_target_exit", False)
    if type(observe_target_exit) is not bool:
        raise ValueError("observe_target_exit must be boolean")
    root = Path(root).resolve(strict=True)
    if root != ROOT.resolve(strict=True):
        raise ValueError("execution root must be the checkout containing this runner and its helpers")
    env = dict(os.environ if env is None else env)
    deadline = time.monotonic() + resources["total_timeout_seconds"]
    record = _new_record(resources, observe_target_exit=observe_target_exit)
    record["execution_paths"] = {
        "repository": str(root), "riscv_prefix": None, "python": sys.executable,
    }
    directory = make_output_dir(root)
    run_ids = set()
    try:
        _check_cancellation()
        record["source_before"] = capture_source(root)
        _check_cancellation()
        observer_options = {"observe_target_exit": True} if observe_target_exit else {}
        plan = build_plan(root, jobs=resources["jobs"], java_heap=resources["java_heap"],
                          **observer_options)
        record["plan_sha256"] = plan_digest(plan, root)
        record["declared_plan"] = normalized_plan(plan, root)
        record["profile_sha256"] = capture_file(root, root / PROFILE_PATH)["sha256"]
        record["workloads_sha256"] = capture_file(root, root / WORKLOADS_PATH)["sha256"]
        _prepare_rows(record, plan)
        riscv = _preflight(root, directory, plan, record, deadline, env)
        for stage in plan["common_build_stages"]:
            observed = _stage(root, directory, stage["id"], stage["argv"],
                              stage["timeout_seconds"], deadline, resources, env)
            record["common_stages"].append(observed)
            _require_command_passed(directory, observed)
            if observe_target_exit:
                if (record["target_exit_observer"] is None
                        and stage["id"] != "htif-observer-prepare"):
                    raise CampaignStop("failed", "observer preparation must be the first common stage")
                _verify_observer(root, record, env)
        binary_digests = {}
        for workload in plan["profiles"][0]["workloads"]:
            base = root if workload["binary_origin"] == "repository" else riscv
            binary_digests[workload["id"]] = capture_file(
                base, base / workload["binary"], kind="riscv_elf")["sha256"]
        for profile, result in zip(plan["profiles"], record["profiles"]):
            if observe_target_exit:
                _verify_observer(root, record, env)
            build = profile["build"]
            result["build"] = _stage(root, directory, build["id"], build["argv"],
                                      build["timeout_seconds"], deadline, resources, env)
            _require_command_passed(directory, result["build"])
            if observe_target_exit:
                _verify_observer(root, record, env)
            artifacts = capture_profile_artifacts(root, profile["configuration"])
            result["artifacts"] = artifacts
            if (not isinstance(artifacts, dict) or artifacts.get("status") != "captured"
                    or not isinstance(artifacts.get("artifacts"), list)
                    or not artifacts["artifacts"] or artifacts.get("reasons") != []):
                raise CampaignStop("blocked", "required profile RTL, DTS, map, or simulator artifacts are missing")
            simulator = Path(profile["simulator"])
            simulator_digest = capture_file(root, simulator, kind="simulator")["sha256"]
            for workload, row in zip(profile["workloads"], result["workloads"]):
                observer_options = ({"observer_record": record, "run_ids": run_ids}
                                    if observe_target_exit else {})
                _run_workload(root, directory, profile, workload, row, simulator, riscv,
                              simulator_digest, binary_digests[workload["id"]], deadline, resources, env,
                              **observer_options)
            if capture_profile_artifacts(root, profile["configuration"]) != artifacts:
                raise CampaignStop("failed", "profile artifacts changed during workload execution")
        record["status"] = "workloads_observed"
        _check_cancellation()
    except CampaignStop as exc:
        record["status"] = exc.status
        record["reasons"].append(str(exc))
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        record["status"] = "blocked"
        record["reasons"].append("required campaign evidence unavailable: " + str(exc))
    except KeyboardInterrupt:
        record["status"] = "blocked"
        record["reasons"].append("campaign interrupted; remaining workloads not run")
    finally:
        _finalize(root, record, deadline, env, directory=directory)
        path = directory / "record.json"
        with path.open("x", encoding="utf-8") as stream:
            _retain_cancellation(record)
            _write_record(stream, record)
            # Restoration can itself receive the last campaign-owned signal.
            # Reconcile it and elapsed evidence I/O while this descriptor is
            # still open; subsequent signals belong to the caller's handlers.
            restore_handlers()
            _retain_final_state(record, deadline)
            while True:
                _write_record(stream, record)
                # A corrective serialization/flush can also cross the budget.
                # Rewrite only for a newly retained failure, not the continually
                # advancing clock. Cancellation and deadline reasons are latched.
                if not _retain_final_state(record, deadline, refresh_clock=False):
                    break
    return record, path


def execute(root, args, env=None):
    """Execute only this checkout, with scoped cooperative signal cancellation."""
    with _cancellation_scope() as restore_handlers:
        return _execute(root, args, env, restore_handlers=restore_handlers)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="read-only default; execute no tools")
    mode.add_argument("--execute", action="store_true", help="run in an already prepared clean environment")
    parser.add_argument("--approved-budget", action="store_true")
    parser.add_argument("--observe-target-exit", action="store_true",
                        help="require a separately bound HTIF target-exit witness for each workload")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--java-heap", default="4G")
    parser.add_argument("--total-timeout-seconds", type=int, default=7200)
    parser.add_argument("--min-free-gib", type=int, default=10)
    args = parser.parse_args(argv)
    if args.execute and not args.approved_budget:
        parser.error("--execute requires --approved-budget")
    if args.approved_budget and not args.execute:
        parser.error("--approved-budget is meaningful only with --execute")
    try:
        root = args.root.resolve(strict=True)
        resources = resource_limits(args)
        if not args.execute:
            observer_options = {"observe_target_exit": True} if args.observe_target_exit else {}
            plan = build_plan(root, jobs=args.jobs, java_heap=args.java_heap, **observer_options)
            result = {"kind": "nova-g1-campaign-plan", "resource_limits": resources,
                      "plan_sha256": plan_digest(plan, root),
                      "plan": normalized_plan(plan, root),
                      "hardware_qualified": False, "g1_gate_passed": False,
                      "reference_comparison": "not_run", "limitations": LIMITATIONS}
            print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
            return 0
        record, path = execute(root, args)
        print("G1 campaign: " + record["status"] + ". Record: " + str(path.relative_to(root)))
        print("Hardware qualification: false; G1 gate passed: false; reference comparison: not run.")
        for reason in record["reasons"]:
            print("Reason: " + reason)
        return {"workloads_observed": 0, "blocked": 2, "failed": 1}[record["status"]]
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print("Blocked: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
