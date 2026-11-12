#!/usr/bin/env python3
"""Opt-in, bounded RocketConfig build/smoke runner; never closes a NOVA gate.

The default --plan mode only prints intended commands. Execution requires an
explicit resource-budget acknowledgement and an already prepared, pinned
toolchain. It does not install dependencies or initialize submodules.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[2]
OUT_NAME = "nova-out"
HEAP = re.compile(r"[1-8]G\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
MAX_STAGE_LOG_BYTES = 64 * 1024 * 1024


def stages(root, jobs, java_heap, build_timeout, test_timeout):
    """Return immutable argv sequences and strict time budgets for G1 smoke."""
    binary = str(root / "tests/build/hello.riscv")
    return [
        ("rocket-build", build_timeout, [
            "make", "-C", "sims/verilator", "CONFIG=RocketConfig",
            f"JAVA_HEAP_SIZE={java_heap}", f"-j{jobs}",
        ]),
        ("hello-configure", min(600, build_timeout), [
            "cmake", "-S", "tests", "-B", "tests/build",
            "-DCMAKE_SYSTEM_NAME=Generic",
            "-DCMAKE_C_COMPILER=riscv64-unknown-elf-gcc",
            "-DCMAKE_CXX_COMPILER=riscv64-unknown-elf-g++",
            "-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY",
        ]),
        ("hello-build", min(600, build_timeout), [
            "cmake", "--build", "tests/build", "--target", "hello",
            "--parallel", str(jobs),
        ]),
        ("hello-simulate", test_timeout, [
            "make", "-C", "sims/verilator", "CONFIG=RocketConfig",
            f"JAVA_HEAP_SIZE={java_heap}", "run-binary-fast", f"BINARY={binary}",
        ]),
    ]


def command(argv, root):
    """Bounded local read-only command, never a shell."""
    try:
        return subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, errors="replace",
                              timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def clean_source(root):
    """Require a real repository top and a clean index/worktree and submodules."""
    top = command(["git", "rev-parse", "--show-toplevel"], root)
    revision = command(["git", "rev-parse", "HEAD"], root)
    status = command(["git", "status", "--porcelain=v1", "--untracked-files=normal",
                      "--ignore-submodules=none"], root)
    if not all(result and result.returncode == 0
               for result in (top, revision, status)):
        return None
    if Path(top.stdout.strip()).resolve() != root or status.stdout:
        return None
    sha = revision.stdout.strip()
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def stale_build_artifacts(root):
    """Find known ignored products that could invalidate a fresh smoke run.

    No files are removed automatically: the maintainer must inspect and
    prepare a separate clean checkout when these artifacts are present.
    This list is conservative, not a proof that every build cache is absent.
    """
    known = (
        root / "tests/build", root / "sims/verilator/generated-src",
        root / "sims/verilator/output",
    )
    if any(path.exists() or path.is_symlink() for path in known):
        return True
    try:
        return any((root / "sims/verilator").glob("simulator-*-RocketConfig*"))
    except OSError:
        return True


def safe_hello_binary(root):
    """Return a contained, non-symlink target ELF path, or None."""
    path = root / "tests/build/hello.riscv"
    try:
        if path.is_symlink() or not path.is_file():
            return None
        resolved = path.resolve(strict=True)
        return path if resolved.is_relative_to(root.resolve(strict=True)) else None
    except (OSError, RuntimeError, ValueError):
        return None


def validate_execution(root, min_free_gib):
    """Stop before creating output unless the approved environment is prepared."""
    # build.sbt selects Chisel 7 by presence, even for an empty value or "0".
    # This runner describes the pinned default Chisel 6 baseline only.
    if "USE_CHISEL7" in os.environ:
        return None, "USE_CHISEL7 must be unset for the pinned Chisel 6 baseline"
    revision = clean_source(root)
    if revision is None:
        return None, "source checkout or submodules are not clean"
    if stale_build_artifacts(root):
        return None, "stale or ignored Rocket build artifacts are present; use a fresh checkout"
    riscv = os.environ.get("RISCV", "")
    if not riscv or not Path(riscv).is_dir() or not (root / "env.sh").is_file():
        return None, "activate the approved pinned RISCV environment first"
    if not shutil.which("timeout"):
        return None, "GNU timeout is required for bounded execution"
    doctor = command([sys.executable, "-B", "scripts/nova/doctor.py", "--strict"], root)
    if not doctor or doctor.returncode != 0:
        return None, "NOVA prerequisite doctor reports missing or invalid dependencies"
    provenance = command([sys.executable, "-B", "scripts/nova/check.py"], root)
    if not provenance or provenance.returncode != 0:
        return None, "NOVA source and pinned-input validation failed"
    try:
        free_space = shutil.disk_usage(root).free
    except OSError:
        return None, "available disk capacity cannot be verified"
    if free_space < min_free_gib * 1024 ** 3:
        return None, "available disk is below approved minimum"
    return revision, None


def collect_provenance(root):
    """Capture bounded public build inputs; never copy the caller's environment.

    These diagnostics are best-effort evidence metadata, not a new source of
    hardware qualification.  Missing data is explicit, never silently replaced
    by guessed tool versions or submodule revisions.
    """
    snapshot = {
        "host": {
            "os": platform.system(), "architecture": platform.machine(),
            "glibc": None, "pinned_sysroot": None,
            "setup_selected_sysroot": None, "unsafe_upstream_setup": None,
        },
        "tool_versions": {}, "lock_hashes": {}, "submodules": [],
        "capture_complete": False,
        "limitations": [
            "Known gitlinks and local tool probes do not establish full nested dependency closure.",
            "Source and smoke logs are not retained evidence until independently reviewed and archived.",
            "Tool versions were observed, not matched to an approved pinned environment.",
        ],
        "toolchain_versions_verified": False,
    }

    def read_report(script):
        result = command([sys.executable, "-B", script, "--json"], root)
        if not result or result.returncode != 0 or not isinstance(result.stdout, str):
            return None
        if len(result.stdout) > 1024 * 1024:
            return None
        try:
            parsed = json.loads(result.stdout)
            return parsed if isinstance(parsed, dict) else None
        except (ValueError, TypeError):
            return None

    preflight = read_report("scripts/nova/bootstrap_preflight.py")
    doctor = read_report("scripts/nova/doctor.py")
    if preflight:
        host = snapshot["host"]
        for field, key in (("glibc", "host_glibc"),
                           ("pinned_sysroot", "pinned_sysroot"),
                           ("setup_selected_sysroot", "setup_selected_sysroot")):
            value = preflight.get(key)
            if isinstance(value, str) and len(value) <= 64:
                host[field] = value
        unsafe = preflight.get("unsafe_upstream_setup")
        if isinstance(unsafe, bool):
            host["unsafe_upstream_setup"] = unsafe
        locks = preflight.get("lock_hashes")
        if isinstance(locks, dict):
            for path, entry in sorted(locks.items()):
                if (isinstance(path, str) and path.startswith("conda-reqs/")
                        and len(path) <= 180 and isinstance(entry, dict)
                        and entry.get("matches_imported_blob") is True
                        and isinstance(entry.get("sha256"), str)
                        and SHA256.fullmatch(entry["sha256"])):
                    snapshot["lock_hashes"][path] = entry["sha256"]
    else:
        snapshot["limitations"].append("Pinned-input preflight JSON could not be captured.")

    if doctor:
        tool_rows = doctor.get("tools")
        if isinstance(tool_rows, list):
            for row in tool_rows[:32]:
                if not isinstance(row, dict):
                    continue
                name, version = row.get("name"), row.get("version")
                if (isinstance(name, str) and name in {"java", "verilator", "firtool", "make", "cmake",
                             "riscv64-unknown-elf-gcc"} and isinstance(version, str)
                        and len(version) <= 240):
                    snapshot["tool_versions"][name] = version.replace(str(root), "<repo>")
        modules = doctor.get("submodules")
        if isinstance(modules, list):
            for row in modules[:256]:
                if not isinstance(row, dict):
                    continue
                path, pin, state = row.get("path"), row.get("pin"), row.get("state")
                if (isinstance(path, str) and len(path) <= 180
                        and re.fullmatch(r"[A-Za-z0-9_./-]+", path)
                        and isinstance(pin, str) and SHA1.fullmatch(pin)
                        and isinstance(state, str)
                        and state in {"at_pin", "dirty", "mismatch", "conflict",
                                      "uninitialized", "unreadable", "invalid_path"}):
                    snapshot["submodules"].append({
                        "path": path, "pin": pin, "state": state,
                        "required": row.get("required") is True,
                    })
    else:
        snapshot["limitations"].append("Prerequisite doctor JSON could not be captured.")

    required_versions = {"java", "verilator", "firtool", "make", "cmake",
                         "riscv64-unknown-elf-gcc"}
    snapshot["capture_complete"] = bool(
        preflight and doctor and len(snapshot["lock_hashes"]) == 9
        and all(entry["state"] == "at_pin" for entry in snapshot["submodules"]
                if entry["required"])
        and any(entry["required"] for entry in snapshot["submodules"])
        and required_versions.issubset(snapshot["tool_versions"])
    )
    if not snapshot["capture_complete"]:
        snapshot["limitations"].append(
            "Toolchain/submodule/lock provenance is incomplete; no reproduction claim is supported.")
    return snapshot


def make_output_dir(root):
    """Keep raw logs in the ignored repository-local output area only."""
    out = root / OUT_NAME
    if out.is_symlink() or (out.exists() and not out.is_dir()):
        raise OSError("unsafe output root")
    out.mkdir(exist_ok=True)
    if out.resolve() != (root / OUT_NAME).resolve() or not out.resolve().is_relative_to(root):
        raise OSError("unsafe output root")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run = out / f"rocket-baseline-{stamp}"
    run.mkdir(mode=0o700)
    return run


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            hasher.update(block)
    return hasher.hexdigest()


def is_riscv64_elf(path):
    """Check the target class/endian/machine before treating a binary as RISC-V."""
    try:
        with path.open("rb") as stream:
            header = stream.read(20)
    except OSError:
        return False
    return (len(header) == 20 and header[:4] == b"\x7fELF"
            and header[4] == 2 and header[5] == 1 and header[6] == 1
            and int.from_bytes(header[18:20], "little") == 243)


def log_contains_hello(path):
    """Verify real target output in a bounded trace-free simulator log."""
    marker = b"Hello world from core 0"
    carry = b""
    scanned = 0
    try:
        with path.open("rb") as stream:
            while scanned < 64 * 1024 * 1024:
                block = stream.read(min(65536, 64 * 1024 * 1024 - scanned))
                if not block:
                    return False
                scanned += len(block)
                if marker in carry + block:
                    return True
                carry = block[-len(marker):]
    except OSError:
        return False
    return False


def stop_process_group(process):
    """Stop a timed-out simulator wrapper and its child processes."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # The timeout is still a failure; do not hang the evidence writer.
            pass


def stage_log_integrity(path):
    """Hash a stable regular log with a strict read bound, or return an error.

    The resource-monitor thread can miss a stage that exits before its first
    poll. This check is therefore mandatory after the writer is closed. It
    also rejects missing/replaced logs rather than treating a zero exit as
    adequate execution evidence.
    """
    try:
        first = path.lstat()
        if not stat.S_ISREG(first.st_mode):
            return None, "stage log is not a regular file"
        if first.st_size > MAX_STAGE_LOG_BYTES:
            return None, "stage log exceeded configured byte limit"
        flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino) != (first.st_dev, first.st_ino)):
                return None, "stage log changed before integrity capture"
            hasher = hashlib.sha256()
            size = 0
            while True:
                block = stream.read(min(65536, MAX_STAGE_LOG_BYTES + 1 - size))
                if not block:
                    break
                size += len(block)
                if size > MAX_STAGE_LOG_BYTES:
                    return None, "stage log exceeded configured byte limit"
                hasher.update(block)
            final = os.fstat(stream.fileno())
        current = path.lstat()
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if (identity(opened) != identity(final) or identity(final) != identity(current)
                or size != final.st_size):
            return None, "stage log changed during integrity capture"
        return hasher.hexdigest(), None
    except (OSError, ValueError):
        return None, "stage log is unavailable or unreadable"


def run_stage(root, directory, name, seconds, argv, min_free_gib=None):
    """Double-bound a process group; monitor log and approved disk floor.

    A pre-stage disk check cannot stop an active compile from filling the
    volume.  Poll its free capacity while the process group is running; if the
    approved minimum cannot be maintained or measured, stop the stage and
    report a resource blocker instead of a hardware failure.
    """
    log = directory / f"{name}.log"
    timed = ["timeout", "--kill-after=30s", f"{seconds}s", *argv]
    started = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    code = None
    error = None
    log_limit_exceeded = threading.Event()
    log_unreadable = threading.Event()
    disk_floor_breached = threading.Event()
    stop_monitor = threading.Event()
    try:
        with log.open("xb") as stream:
            try:
                process = subprocess.Popen(
                    timed, cwd=root, stdin=subprocess.DEVNULL,
                    stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)

                def monitor_resources():
                    while not stop_monitor.wait(0.25):
                        try:
                            if log.stat().st_size > MAX_STAGE_LOG_BYTES:
                                log_limit_exceeded.set()
                                try:
                                    os.killpg(process.pid, signal.SIGKILL)
                                except OSError:
                                    pass
                                return
                        except OSError:
                            log_unreadable.set()
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except OSError:
                                pass
                            return

                        if min_free_gib is not None:
                            try:
                                free = shutil.disk_usage(root).free
                            except OSError:
                                free = None
                            if free is None or free < min_free_gib * 1024 ** 3:
                                disk_floor_breached.set()
                                try:
                                    os.killpg(process.pid, signal.SIGKILL)
                                except OSError:
                                    pass
                                return

                monitor = threading.Thread(target=monitor_resources, daemon=True)
                monitor.start()
                try:
                    code = process.wait(timeout=seconds + 40)
                except subprocess.TimeoutExpired:
                    stop_process_group(process)
                    code = 124
                    error = "outer stage timeout exceeded"
                except KeyboardInterrupt:
                    stop_process_group(process)
                    code = 130
                    error = "operator interrupted stage"
                finally:
                    stop_monitor.set()
                    monitor.join(timeout=2)
            except OSError:
                error = "runner command unavailable"
    except OSError:
        error = "stage log could not be created"
    process_exit_code = code
    # A fast process may finish before either periodic resource check runs.
    # Recheck the final disk floor and complete log unconditionally.
    if min_free_gib is not None:
        try:
            final_free = shutil.disk_usage(root).free
        except OSError:
            final_free = None
        if final_free is None or final_free < min_free_gib * 1024 ** 3:
            disk_floor_breached.set()
    log_hash, log_error = stage_log_integrity(log)
    if log_error or log_unreadable.is_set():
        error = error or log_error or "stage log became unreadable during execution"
        if code == 0:
            code = 1
    if log_limit_exceeded.is_set():
        error = "stage log exceeded 64 MiB limit"
        code = 1
    if disk_floor_breached.is_set():
        error = "disk capacity fell below approved minimum during stage"
        code = 1
    result = {
        "stage": name, "command": timed, "started_utc": started,
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "exit_code": code,
        "process_exit_code": process_exit_code,
        "status": ("blocked" if disk_floor_breached.is_set()
                   else "passed" if code == 0 and log_hash is not None and not error
                   else "failed"),
        "log": log.name if log.exists() else None, "log_sha256": log_hash,
    }
    if error:
        result["error"] = error
    if disk_floor_breached.is_set():
        result["blocked"] = True
    return result


def execute(root, args, steps):
    revision, error = validate_execution(root, args.min_free_gib)
    if error:
        print("Blocked: " + error, file=sys.stderr)
        return 2
    provenance = collect_provenance(root)
    try:
        output = make_output_dir(root)
    except OSError:
        print("Blocked: unsafe or unavailable local output directory", file=sys.stderr)
        return 2
    record = {
        "schema_version": 1, "scope": "G1 RocketConfig smoke only",
        "hardware_qualified": False, "g1_gate_passed": False,
        "revision": revision, "approved_budget_acknowledged": True,
        "evidence_scope": {
            "gate": "G1", "requirements": ["REQ-BUILD-001"],
            "tests": ["T-BUILD-001"], "qualification": "partial_smoke_only",
        },
        "provenance": provenance,
        "observations": {
            "expected_hello_marker": "Hello world from core 0",
            "hello_marker_observed": False,
            "riscv64_elf_verified": False,
            "target_completion_verified": False,
        },
        "resource_limits": {
            "jobs": args.jobs, "java_heap": args.java_heap,
            "build_timeout_seconds": args.build_timeout,
            "test_timeout_seconds": args.test_timeout,
            "total_timeout_seconds": args.total_timeout,
            "min_free_gib": args.min_free_gib,
            "note": "time/jobs and sampled disk floor do not cap peak RAM or instantaneous disk usage",
        },
        "stages": [], "status": "in_progress",
    }
    if not isinstance(provenance, dict) or provenance.get("capture_complete") is not True:
        record["status"] = "blocked"
        record["blocker"] = "pre-run source/toolchain provenance is incomplete"
        pending_steps = ()
    elif not steps:
        record["status"] = "blocked"
        record["blocker"] = "no smoke stages were declared"
        pending_steps = ()
    else:
        pending_steps = steps
    run_started = time.monotonic()
    for name, seconds, argv in pending_steps:
        remaining = args.total_timeout - int(time.monotonic() - run_started)
        if remaining < 60:
            record["status"] = "blocked"
            record["blocker"] = "approved total wall-time budget exhausted"
            break
        try:
            free_space = shutil.disk_usage(root).free
        except OSError:
            free_space = None
        if free_space is None or free_space < args.min_free_gib * 1024 ** 3:
            record["status"] = "blocked"
            record["blocker"] = "disk unavailable or below approved minimum before a stage"
            break
        # Reserve GNU timeout's grace, the outer wait and bounded cleanup.
        result = run_stage(root, output, name, min(seconds, remaining - 55), argv,
                           min_free_gib=args.min_free_gib)
        record["stages"].append(result)
        if result.get("exit_code") != 0 or result.get("status") != "passed":
            record["status"] = "blocked" if result.get("blocked") else "failed"
            break
        reported_hash = result.get("log_sha256")
        expected_log = f"{name}.log"
        log_hash, log_error = stage_log_integrity(output / expected_log)
        if (result.get("log") != expected_log or not isinstance(reported_hash, str)
                or not SHA256.fullmatch(reported_hash) or log_error
                or reported_hash != log_hash):
            result["status"] = "failed"
            result["error"] = "stage log integrity was not verified"
            record["status"] = "failed"
            break
        if name == "hello-build":
            safe_binary = safe_hello_binary(root)
            valid_elf = bool(safe_binary and is_riscv64_elf(safe_binary))
            record["observations"]["riscv64_elf_verified"] = valid_elf
            if not valid_elf:
                result["status"] = "failed"
                result["error"] = "hello binary was not a contained RISC-V ELF64 executable"
                record["status"] = "failed"
                break
            try:
                record["hello_binary_sha256_before_simulation"] = digest(safe_binary)
            except OSError:
                result["status"] = "failed"
                result["error"] = "hello binary could not be hashed before simulation"
                record["status"] = "failed"
                break
        if name == "hello-simulate":
            observed_marker = log_contains_hello(output / result["log"])
            record["observations"]["hello_marker_observed"] = observed_marker
            if not observed_marker:
                result["status"] = "failed"
                result["error"] = "expected target hello output not observed"
                record["status"] = "failed"
                break
    else:
        # The inherited trace-free Make path has no independent target
        # completion attestation.  This only establishes the observed marker.
        if record["status"] == "in_progress":
            record["status"] = "hello_marker_observed_unqualified"
    binary = safe_hello_binary(root)
    if binary:
        try:
            record["hello_binary_sha256"] = digest(binary)
        except OSError:
            record["warnings"] = ["hello binary disappeared before hash capture"]
    # No successful smoke result survives missing or changed source/pin/tool
    # metadata. A valid output marker never excuses incomplete provenance.
    record["revision_after"] = clean_source(root)
    record["provenance_after"] = collect_provenance(root)
    integrity_errors = []
    after = record["provenance_after"]
    if not isinstance(provenance, dict) or provenance.get("capture_complete") is not True:
        integrity_errors.append("pre-run source/toolchain provenance is incomplete")
    if record["revision_after"] != revision:
        integrity_errors.append("source revision or checkout cleanliness changed during execution")
    if not isinstance(after, dict) or after.get("capture_complete") is not True:
        integrity_errors.append("post-run source/toolchain provenance is incomplete")
    if isinstance(provenance, dict) and isinstance(after, dict):
        for field in ("host", "tool_versions", "lock_hashes", "submodules"):
            if provenance.get(field) != after.get(field):
                integrity_errors.append(f"{field} changed during execution")
    if record["status"] == "hello_marker_observed_unqualified":
        before_hash = record.get("hello_binary_sha256_before_simulation")
        if not before_hash or before_hash != record.get("hello_binary_sha256"):
            integrity_errors.append("hello binary changed or became unavailable after compilation")
    record["provenance_unchanged"] = not integrity_errors
    record["integrity_errors"] = integrity_errors
    if integrity_errors and record["status"] == "hello_marker_observed_unqualified":
        record["status"] = "blocked"
        record["blocker"] = "source, binary, or provenance integrity was not retained"
    record["finished_utc"] = datetime.now(timezone.utc).isoformat()
    try:
        with (output / "record.json").open("x", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except OSError:
        print("Failed: local evidence could not be safely retained", file=sys.stderr)
        return 1
    print(f"Run status: {record['status']}; local evidence: {OUT_NAME}/{output.name}/record.json")
    print("Raw logs require security review before any publication.")
    return 0 if record["status"] == "hello_marker_observed_unqualified" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="show bounded commands (default)")
    mode.add_argument("--execute", action="store_true", help="run with approved budget")
    parser.add_argument("--approved-budget", action="store_true",
                        help="acknowledge maintainer-approved host/resource/network/cost limits")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--java-heap", default="4G")
    parser.add_argument("--build-timeout", type=int, default=7200)
    parser.add_argument("--test-timeout", type=int, default=300)
    parser.add_argument("--total-timeout", type=int, default=7200)
    parser.add_argument("--min-free-gib", type=int, default=10)
    args = parser.parse_args(argv)
    if not 1 <= args.jobs <= 2 or not HEAP.fullmatch(args.java_heap):
        parser.error("jobs must be 1..2 and java-heap must be 1G..8G")
    if not 60 <= args.build_timeout <= 7200 or not 30 <= args.test_timeout <= 600:
        parser.error("timeouts must be within the documented bounded ranges")
    if not 300 <= args.total_timeout <= 7200:
        parser.error("total-timeout must be within 300..7200 seconds")
    if not 1 <= args.min_free_gib <= 50:
        parser.error("min-free-gib must be 1..50")
    steps = stages(ROOT, args.jobs, args.java_heap, args.build_timeout,
                   args.test_timeout)
    if not args.execute:
        print(json.dumps({
            "scope": "G1 RocketConfig smoke plan only; no hardware qualification",
            "execute_requires_approved_budget": True,
            "source_must_be_clean": True,
            "does_not_install_or_initialize_dependencies": True,
            "total_timeout_seconds": args.total_timeout,
            "stages": [{"name": name, "timeout_seconds": seconds, "argv": command}
                       for name, seconds, command in
                       ((name, seconds, [part.replace(str(ROOT), "<repo>") for part in command])
                        for name, seconds, command in steps)],
        }, sort_keys=True, indent=2))
        return 0
    if not args.approved_budget:
        parser.error("--execute requires explicit --approved-budget")
    return execute(ROOT, args, steps)


if __name__ == "__main__":
    raise SystemExit(main())
