#!/usr/bin/env python3
"""Plan, or explicitly execute, a bounded native pinned-HTIF comparison.

Default operation only reads inputs and prints JSON. Execution needs an existing
Spike source directory and a fresh output leaf with an existing parent. It uses
native g++/ar/nm serially, synthetic host memory and a synthetic HAVE_INT128
configuration; it never downloads, installs, runs RISC-V instructions, or runs
RTL. This trusted-build evidence runner is not an OS sandbox or resource quota.
"""

import sys

sys.dont_write_bytecode = True  # Even the default plan must not create caches.

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import signal
import stat
import time


SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


observer = _load("nova_host_probe_observer", SCRIPT.with_name("htif_observer.py"))
engine = _load("nova_host_probe_engine", SCRIPT.with_name("campaign_exec.py"))
PIN = observer.PINNED_SPIKE_COMMIT
SOURCE_NAMES = ("htif", "memif", "syscall", "device", "rfb", "elfloader", "term")
# Independently retained pinned-source hashes from the native source audit.
# The source/header copies retain their original notices and the original LICENSE.
SOURCE_HASHES = {
    **observer.SOURCE_HEADERS,
    "fesvr/htif.cc": observer.PINNED_HTIF_SHA256,
    "fesvr/memif.cc": "6cced20eb732a438a907ec2070e4f2be478f415e1427e6f25cbc64c2450c33ab",
    "fesvr/syscall.cc": "371639953ee8edf0bed1e57e5ed894f99948886b9cac63931398aea2b512a78a",
    "fesvr/device.cc": "3feee8c3fb6d8cb29beb79840f2b5be3166b0211977eeb61317c5dbaa67a83cd",
    "fesvr/rfb.cc": "10fc8b6215c382728f6cb871367b13aa05f678168e62e62d40bb83719895a02d",
    "fesvr/elfloader.cc": "29e021317fb8ffe90c68e56a107bfd80bf1b24a059bb48c34b98b075319efa7b",
    "fesvr/term.cc": "ed9bf6a4b7d00262b9cfcce63e6e26b724f48abaf1dc1ca7390d22a895c390c8",
    "fesvr/term.h": "7f8758b6f20f75f37be3f293fdffecc017f88c141203265e1af54ae815d4776a",
    "LICENSE": "c65e436d18972c9c4bd192494fe4870bd2e158179474975b80a3559f27631632",
}
NOVA_INPUTS = (
    "software/nova/observer/htif_host_probe.cc",
    observer.NATIVE_REL, observer.HEADER_REL, observer.GENERATOR_REL,
    "scripts/nova/htif_exit_evidence.py", "scripts/nova/campaign_exec.py",
    "scripts/nova/htif_host_probe.py",
)
MODES = ("direct0", "direct7", "syscall0", "syscall7", "signal-only", "syscall7-signal")
MAX_TOTAL_SECONDS = 300
MAX_LOG_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_ARTIFACT_TOTAL_BYTES = 128 * 1024 * 1024
MAX_ARTIFACT_FILES = 256
MAX_ARTIFACT_ENTRIES = 512
FINALIZE_RESERVE_SECONDS = 3.0
SYNTHETIC_CONFIG = (
    b"// SYNTHETIC native host fixture; not an installed pinned toolchain configuration.\n"
    b"#define HAVE_INT128 1\n"
)
FALSE_FLAGS = {"cpu_execution": False, "rtl_simulation": False,
               "hardware_qualified": False, "g1_gate_passed": False,
               "target_completion_verified": False}
LIMITATIONS = [
    "Memory stimuli originate in the native fixture, not a CPU.",
    "The archive is a native source closure, not installed pinned libfesvr.a.",
    "Synthetic HAVE_INT128 config does not verify an installed toolchain.",
    "No ELF loading, TSI, TestChipIP, Verilator, RTL, or campaign execution.",
    "Nested parser target_completion_verified values describe supplied fixture events only.",
    "Deadlines reserve process cleanup and evidence capture; disk/log limits are sampled, not OS quotas.",
    "Artifact traversal and reads check time/cancellation cooperatively; blocking filesystem calls have no hard time quota.",
    "Elapsed time includes initial metadata writes and handler restoration; final corrective writes, close and return may follow its last sample.",
]


class ProbeError(ValueError):
    """The requested native comparison could not establish complete evidence."""


class _ProbeStopped(ProbeError):
    """A cooperative boundary stopped optional work, preserving prior failure."""

    def __init__(self, reason, *, deadline_exhausted=False):
        super().__init__(reason)
        self.deadline_exhausted = deadline_exhausted


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def limits(total_seconds=180, command_seconds=45, case_seconds=5,
           max_log_bytes=1024 * 1024, min_free_gib=1):
    values = {"total_seconds": total_seconds, "command_seconds": command_seconds,
              "case_seconds": case_seconds, "max_log_bytes": max_log_bytes,
              "min_free_gib": min_free_gib}
    for name, maximum in (("total_seconds", MAX_TOTAL_SECONDS),
                          ("command_seconds", 60), ("case_seconds", 30),
                          ("min_free_gib", 50)):
        value = values[name]
        if type(value) not in (int, float) or not 1 <= value <= maximum or not math.isfinite(value):
            raise ProbeError("invalid " + name)
    if type(max_log_bytes) is not int or not 1 <= max_log_bytes <= MAX_LOG_BYTES:
        raise ProbeError("invalid max_log_bytes")
    return values


def capture_source(source_root, relative, *, retain=False):
    """Accept only a known, non-symlink, bounded file with its exact pinned hash."""
    if relative not in SOURCE_HASHES:
        raise ProbeError("source is outside the pinned native closure")
    record, data = observer._capture(source_root, relative, "spike", retain=retain)
    if record["sha256"] != SOURCE_HASHES[relative]:
        raise ProbeError("pinned source SHA256 mismatch: " + relative)
    record.update(source_pin=PIN, local_path="inputs/spike/" + relative,
                  url=f"https://github.com/riscv-software-src/riscv-isa-sim/blob/{PIN}/{relative}")
    return record, data


def build_commands(output, tools):
    """The plan and execution share these exact direct-argv build commands."""
    output = Path(output)
    source, native = output / "inputs/spike", output / "inputs/nova"
    objects, archive = output / "objects", output / "libfesvr-host-fixture.a"
    flags = ["-std=c++17", "-O0", "-g", "-pthread",
             '-DPREFIX="/nova-native-host-fixture-not-an-installed-toolchain"',
             "-I" + str(output / "synthetic-config"), "-I" + str(source / "fesvr"),
             "-I" + str(source / "riscv"), "-I" + str(source / "softfloat"), "-I" + str(native)]
    commands = [("version-" + key, [tools[key], "--version"]) for key in ("gxx", "ar", "nm")]
    archive_objects = [objects / (name + ".o") for name in SOURCE_NAMES]
    for name, obj in zip(SOURCE_NAMES, archive_objects):
        commands.append(("compile-" + name,
                         [tools["gxx"], *flags, "-c", source / "fesvr" / (name + ".cc"), "-o", obj]))
    commands.extend((("archive", [tools["ar"], "rcsD", archive, *archive_objects]),
                     ("archive-members", [tools["ar"], "t", archive])))
    for name, origin in (("probe", native / "htif_host_probe.cc"),
                         ("nova_htif_exit", native / "nova_htif_exit.cc"),
                         ("nova_htif", output / "nova_htif.cc")):
        commands.append(("compile-" + name, [tools["gxx"], *flags, "-c", origin,
                                             "-o", objects / (name + ".o")]))
    for variant in ("original", "observed"):
        extra = [] if variant == "original" else [objects / "nova_htif.o", objects / "nova_htif_exit.o"]
        commands.append(("link-" + variant,
                         [tools["gxx"], "-pthread", "-o", output / ("probe-" + variant),
                          objects / "probe.o", *extra, archive,
                          "-Wl,-Map," + str(output / (variant + ".map"))]))
        commands.append(("symbols-" + variant,
                         [tools["nm"], "-C", "--defined-only", output / ("probe-" + variant)]))
    return [(name, [str(arg) for arg in argv]) for name, argv in commands]


def plan_probe(source_root=None, output=None, *, budget=None):
    budget = limits(**(budget or {}))
    source_root = observer._path(source_root or ROOT / observer.SPIKE_REL)
    destination = observer._path(output) if output is not None else None
    tools = {key: shutil.which(name) for key, name in (("gxx", "g++"), ("ar", "ar"), ("nm", "nm"))}
    blockers, sources = [], []
    try:
        observer._root(source_root)
        for relative in sorted(SOURCE_HASHES):
            sources.append(capture_source(source_root, relative)[0])
        for relative in NOVA_INPUTS:
            observer._capture(ROOT, relative, "nova")
    except (ProbeError, observer.ObserverError, OSError) as error:
        blockers.append(str(error))
    for key, path in tools.items():
        if path is None:
            blockers.append("required native tool is unavailable: " + key)
    if destination is not None:
        try:
            observer._root(destination.parent)
            if destination.exists() or destination.is_symlink():
                raise ProbeError("output already exists; a fresh directory is required")
            if shutil.disk_usage(destination.parent).free < budget["min_free_gib"] * 1024 ** 3:
                raise ProbeError("available disk is below the configured floor")
        except (ProbeError, observer.ObserverError, OSError) as error:
            blockers.append(str(error))
    planned_output = destination or Path("{fresh-output}")
    argv_tools = {key: value or {"gxx": "g++", "ar": "ar", "nm": "nm"}[key]
                  for key, value in tools.items()}
    commands = [{"name": name, "argv": argv} for name, argv in build_commands(planned_output, argv_tools)]
    cases = [{"variant": variant, "mode": mode,
              "argv": [str(planned_output / ("probe-" + variant)), mode],
              "expected_host_exit": 7 if "7" in mode else 0,
              "expected_parser_status": ("failed" if "signal" in mode else "observed")
              if variant == "observed" else None}
             for variant in ("original", "observed") for mode in MODES]
    return {"schema_version": 1, "kind": "nova-htif-host-probe", "status": "planned",
            "read_only": True, "source_pin": PIN, "source_root": str(source_root),
            "output": str(destination) if destination else None,
            "ready": not blockers, "blockers": blockers, "limits": budget,
            "tools": tools, "source_files": sources, "required_source_hashes": SOURCE_HASHES,
            "commands": commands, "cases": cases, "native_processes": 12,
            "parallel_jobs": 1, "network": False, "install": False,
            "synthetic_config": SYNTHETIC_CONFIG.decode(), "limitations": LIMITATIONS,
            **FALSE_FLAGS}


def _write_new(path, data):
    descriptor = observer._directory(path.parent)
    try:
        observer._write_exclusive(descriptor, path.name, data)
    finally:
        os.close(descriptor)


def _read_artifact(output, relative, maximum, *, check=None):
    path = output / relative
    check = check or (lambda: None)
    check()
    # The existing capture helper intentionally disallows empty inputs; logs
    # are allowed to be empty and still need a no-follow bounded read.
    parent = observer._directory(path.parent)
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            check()
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > maximum:
                raise ProbeError("artifact is not a bounded regular file: " + relative)
            chunks, count = [], 0
            while True:
                check()
                part = os.read(descriptor, min(65536, maximum + 1 - count))
                check()
                if not part:
                    break
                chunks.append(part)
                count += len(part)
                if count > maximum:
                    raise ProbeError("artifact exceeded its byte limit: " + relative)
            after = os.fstat(descriptor)
            current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            if (observer._identity(before) != observer._identity(after)
                    or observer._identity(after) != observer._identity(current)
                    or count != before.st_size):
                raise ProbeError("artifact changed during capture: " + relative)
            check()
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)


def _artifact_paths(output, check):
    """Stream a capped traversal, including empty directories in the work cap."""
    pending, files, entries_seen = [output], 0, 0
    while pending:
        check()
        directory = pending.pop()
        descriptor = observer._directory(directory)
        try:
            with os.scandir(descriptor) as entries:
                while True:
                    check()
                    try:
                        entry = next(entries)
                    except StopIteration:
                        break
                    check()
                    entries_seen += 1
                    if entries_seen > MAX_ARTIFACT_ENTRIES:
                        raise ProbeError("artifact directory entry limit exceeded")
                    info = entry.stat(follow_symlinks=False)
                    check()
                    path = directory / entry.name
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(path)
                    else:
                        files += 1
                        if files > MAX_ARTIFACT_FILES:
                            raise ProbeError("artifact count limit exceeded")
                        # Symlinks and special files reach the no-follow regular
                        # file check instead of silently disappearing from evidence.
                        yield path, info.st_size
        finally:
            os.close(descriptor)


def _add_reason(result, reason):
    reasons = result.setdefault("reasons", [])
    if reason not in reasons:
        reasons.append(reason)


def _retain_error(result, error, *, finalization=False):
    if isinstance(error, _ProbeStopped):
        if result["status"] != "failed":
            result["status"] = "blocked"
        if error.deadline_exhausted:
            result["deadline_exhausted"] = True
    elif finalization or result["status"] not in {"blocked", "failed"}:
        result["status"] = "failed"
    _add_reason(result, str(error))


def _check_remaining(deadline, cancellation, *, reserve=0):
    if cancellation["signal"] is not None:
        raise _ProbeStopped("native comparison interrupted")
    remaining = deadline - time.monotonic() - reserve
    if remaining < 0.001:
        raise _ProbeStopped("total native comparison deadline exhausted", deadline_exhausted=True)
    return remaining


def _terminal_state(result):
    return (result["status"], tuple(result.get("reasons", ())), result.get("interrupted"),
            result.get("interruption_signal"), result.get("deadline_exhausted"),
            result.get("artifacts_incomplete"))


def _retain_final_state(result, started, deadline, cancellation, *, refresh_clock=True):
    """Latch terminal facts; a known failure is never downgraded to blocked."""
    before = _terminal_state(result)
    now = time.monotonic()
    if now >= deadline:
        _retain_error(result, _ProbeStopped("total native comparison deadline exhausted",
                                           deadline_exhausted=True))
    if cancellation["signal"] is not None:
        _retain_error(result, _ProbeStopped("native comparison interrupted"))
        result.update(interrupted=True, interruption_signal=cancellation["signal"])
    changed = before != _terminal_state(result)
    if refresh_clock or changed:
        result["elapsed_seconds"] = round(now - started, 6)
    return changed


def _write_owned(descriptor, data):
    """Correct only a descriptor created exclusively by this finalization."""
    os.lseek(descriptor, 0, os.SEEK_SET)
    os.ftruncate(descriptor, 0)
    remaining = memoryview(data)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise ProbeError("native evidence write made no progress")
        remaining = remaining[written:]
    os.fsync(descriptor)


def _finalize_probe(output, result, started, deadline, cancellation, restore_handlers):
    """Retain partial evidence and reconcile late events before closing our FDs.

    Optional capture stops at cooperative boundaries. Terminal metadata still
    gets a bounded best-effort write after a stop. This is not a transactional
    publisher: concurrent readers must wait for this call to finish, and a
    filesystem call, SIGKILL or a crash can prevent complete persistence.
    """
    artifacts, total = [], 0
    check = lambda: _check_remaining(deadline, cancellation)
    try:
        for path, size in _artifact_paths(output, check):
            check()
            relative = str(path.relative_to(output))
            remaining = MAX_ARTIFACT_TOTAL_BYTES - total
            if size > remaining:
                raise ProbeError("aggregate artifact byte limit exceeded")
            data = _read_artifact(output, relative, min(MAX_ARTIFACT_BYTES, remaining), check=check)
            total += len(data)
            digest = _sha(data)
            check()
            artifacts.append({"path": relative, "bytes": len(data), "sha256": digest})
    except (ProbeError, observer.ObserverError, OSError) as error:
        _retain_error(result, error, finalization=True)
        result["artifacts_incomplete"] = True
    artifacts.sort(key=lambda item: item["path"])

    directory, descriptors, metadata, failed_writes = None, {}, {}, set()

    def write_failed(name, error):
        # First failure per file is retained once, so retries cannot create an
        # unbounded sequence of reasons or timestamp-only corrective writes.
        if name not in failed_writes:
            failed_writes.add(name)
            _retain_error(result, ProbeError("could not retain " + name + ": " + str(error)),
                          finalization=True)
        result["artifacts_incomplete"] = True
        metadata.pop(name, None)

    def inventory():
        return artifacts + [metadata[name] for name in ("commands.json", "results.json") if name in metadata]

    def persist():
        for name in ("results.json", "artifacts.json"):
            if name not in descriptors:
                continue
            try:
                data = _json(result if name == "results.json" else inventory())
                _write_owned(descriptors[name], data)
                metadata[name] = {"path": name, "bytes": len(data), "sha256": _sha(data)}
            except (ProbeError, observer.ObserverError, OSError) as error:
                write_failed(name, error)

    try:
        try:
            data = _json(result["commands"])
            _write_new(output / "commands.json", data)
            metadata["commands.json"] = {"path": "commands.json", "bytes": len(data), "sha256": _sha(data)}
        except (ProbeError, observer.ObserverError, OSError) as error:
            write_failed("commands.json", error)
        try:
            directory = observer._directory(output)
        except (observer.ObserverError, OSError) as error:
            write_failed("evidence directory", error)
        if directory is not None:
            for name in ("results.json", "artifacts.json"):
                try:
                    descriptors[name] = os.open(
                        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                        0o600, dir_fd=directory)
                except OSError as error:
                    write_failed(name, error)
        _retain_final_state(result, started, deadline, cancellation)
        persist()
        # Signals caught during either initial write or restoration still belong
        # to us. After restoration, new signals belong to the caller's handlers.
        restore_handlers()
        _retain_final_state(result, started, deadline, cancellation)
        while True:
            before = _terminal_state(result)
            persist()
            _retain_final_state(result, started, deadline, cancellation,
                                refresh_clock=before != _terminal_state(result))
            if before == _terminal_state(result):
                break
            # Only a first write error or the first deadline observation can
            # change state here. The clock alone never triggers another pass.
    finally:
        restore_handlers()
        for descriptor in descriptors.values():
            os.close(descriptor)
        if directory is not None:
            os.close(directory)


def command_matches(record, expected):
    """Never normalize an expected status 7 into a successful engine record."""
    return (record.get("exit_code") == expected and not record.get("timed_out")
            and not record.get("interrupted")
            and bool(record.get("stdout_sha256")) and bool(record.get("stderr_sha256"))
            and ((expected == 0 and record.get("status") == "passed" and not record.get("reason"))
                 or (expected != 0 and record.get("status") == "failed"
                     and record.get("reason") == "command exited unsuccessfully")))


def verify_linkage(output, members, original_symbols, observed_symbols, *, check=None):
    expected = [name + ".o" for name in SOURCE_NAMES]
    if members.splitlines() != expected:
        raise ProbeError("archive does not contain exactly the seven real source objects")
    archive_member = str(output / "libfesvr-host-fixture.a") + "(htif.o)"
    original_map = _read_artifact(output, "original.map", MAX_ARTIFACT_BYTES, check=check).decode()
    observed_map = _read_artifact(output, "observed.map", MAX_ARTIFACT_BYTES, check=check).decode()
    if archive_member not in original_map or archive_member in observed_map:
        raise ProbeError("link maps do not prove the original htif.o was excluded only for the overlay")
    for symbols in (original_symbols, observed_symbols):
        if sum(line.endswith(" htif_t::stop()") for line in symbols.splitlines()) != 1:
            raise ProbeError("binary does not define exactly one htif_t::stop()")
    if ("nova_htif_observe_stop(" in original_symbols or "nova_htif_observe_stop" not in observed_map
            or sum(" T nova_htif_observe_stop(" in line for line in observed_symbols.splitlines()) != 1):
        raise ProbeError("observer definition/linkage is not exclusive to the overlay")
    return {"archive_members": expected, "overlay_precedes_archive": True,
            "original_htif_member_extracted_in_original": True,
            "original_htif_member_extracted_in_observed": False}


def execute_probe(source_root, output, *, budget=None):
    started = time.monotonic()
    budget = limits(**(budget or {}))
    deadline = started + budget["total_seconds"]
    plan = plan_probe(source_root, output, budget=budget)
    result = {"schema_version": 1, "kind": "nova-htif-host-probe-result",
              "scope": "native-host-only real pinned HTIF/FESVR with synthetic memory",
              "source_pin": PIN, "status": "blocked", "cases": [], "commands": [],
              "limits": budget, "limitations": LIMITATIONS, **FALSE_FLAGS}
    if not plan["ready"]:
        result["reasons"] = plan["blockers"]
        return result
    source_root, output = Path(plan["source_root"]), Path(plan["output"])
    cancellation = {"signal": None}
    previous = {}
    created = False

    def cancel(signum, _frame):
        if cancellation["signal"] is None:
            cancellation["signal"] = signum

    def check():
        return _check_remaining(deadline, cancellation,
                                reserve=engine.CLEANUP_GRACE_SECONDS + FINALIZE_RESERVE_SECONDS)

    def restore_handlers():
        for signum, previous_handler in list(previous.items()):
            signal.signal(signum, previous_handler)
            del previous[signum]

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, cancel)
        check()
        parent = observer._directory(output.parent)
        try:
            os.mkdir(output.name, 0o700, dir_fd=parent)
        finally:
            os.close(parent)
        created = True
        result["status"] = "running"
        for name in ("logs", "records", "objects", "synthetic-config", "temporary", "inputs/spike", "inputs/nova"):
            (output / name).mkdir(mode=0o700, parents=True, exist_ok=True)
        _write_new(output / "plan.json", _json(plan))
        sources, nova = [], []
        for relative in sorted(SOURCE_HASHES):
            check()
            record, data = capture_source(source_root, relative, retain=True)
            path = output / record["local_path"]
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _write_new(path, data)
            sources.append(record)
        for relative in NOVA_INPUTS:
            check()
            record, data = observer._capture(ROOT, relative, "nova", retain=True)
            record["local_path"] = "inputs/nova/" + Path(relative).name
            _write_new(output / record["local_path"], data)
            nova.append(record)
        _write_new(output / "source-manifest.json", _json(sources))
        _write_new(output / "nova-inputs.json", _json(nova))
        _write_new(output / "synthetic-config/config.h", SYNTHETIC_CONFIG)
        native = output / "inputs/nova"
        generator = _load("nova_host_snapshot_generator", native / "htif_observer.py")
        assessor = _load("nova_host_snapshot_assessor", native / "htif_exit_evidence.py")
        runner = _load("nova_host_snapshot_runner", native / "campaign_exec.py")
        _write_new(output / "nova_htif.cc", generator.render_overlay(
            _read_artifact(output, "inputs/spike/fesvr/htif.cc", observer.MAX_INPUT_BYTES, check=check)))
        # Explicit minimal environment avoids ambient include paths, compiler
        # options, and an inherited witness configuration. No shell is used.
        environment = {"PATH": os.defpath, "LC_ALL": "C", "LANG": "C",
                       "TMPDIR": str(output / "temporary")}

        def run(name, argv, expected=0, *, case=False, extra_env=None):
            remaining = check()
            record = runner.run_command(
                output, output / "logs", name, argv,
                min(remaining, budget["case_seconds" if case else "command_seconds"]),
                min_free_gib=budget["min_free_gib"],
                max_log_bytes=budget["max_log_bytes"], env={**environment, **(extra_env or {})})
            record["cwd"] = str(output)
            record["expected_native_exit"] = expected
            record["expected_exit_observed"] = command_matches(record, expected)
            for channel in ("stdout", "stderr"):
                if record[channel] is not None:
                    record[channel] = "logs/" + record[channel]
            result["commands"].append(record)
            if record.get("interrupted") and cancellation["signal"] is None:
                cancellation["signal"] = record.get("interruption_signal") or signal.SIGINT
            _write_new(output / "records" / (name + ".json"), _json(record))
            if not record["expected_exit_observed"]:
                result["status"] = "blocked" if record["status"] == "blocked" else "failed"
                raise ProbeError(name + ": " + record.get("reason", "unexpected native process status"))
            captured = []
            for channel in ("stdout", "stderr"):
                data = _read_artifact(output, record[channel], budget["max_log_bytes"], check=check)
                if _sha(data) != record[channel + "_sha256"]:
                    raise ProbeError("captured command log hash changed")
                captured.append(data)
            return record, *captured

        build_logs = {}
        for name, argv in build_commands(output, plan["tools"]):
            record, stdout, stderr = run(name, argv)
            if name.startswith("version-") or name in {"archive-members", "symbols-original", "symbols-observed"}:
                build_logs[name] = stdout.decode()
        check()
        result.update(verify_linkage(output, build_logs["archive-members"],
                                     build_logs["symbols-original"], build_logs["symbols-observed"], check=check))
        result["tool_versions"] = {key: build_logs["version-" + key].splitlines()[0]
                                   for key in ("gxx", "ar", "nm")}
        baseline = {}
        for variant in ("original", "observed"):
            binary = output / ("probe-" + variant)
            binary_hash = _sha(_read_artifact(output, binary.name, MAX_ARTIFACT_BYTES, check=check))
            for mode in MODES:
                expected = 7 if "7" in mode else 0
                identity = secrets.token_hex(32)
                binding_record = {"scope": "native-host-fixture-only", "mode": mode,
                                  "binary_sha256": binary_hash, "run_id": identity}
                binding = _sha(json.dumps(binding_record, sort_keys=True, separators=(",", ":")).encode())
                witness = output / ("probe-" + variant + "-" + mode + ".json")
                extra = ({"NOVA_HTIF_WITNESS_PATH": str(witness), "NOVA_HTIF_RUN_ID": identity,
                          "NOVA_HTIF_BINDING_SHA256": binding} if variant == "observed" else {})
                record, stdout, stderr = run(variant + "-" + mode, [str(binary), mode], expected,
                                            case=True, extra_env=extra)
                fixture = json.loads(stdout)
                expected_stderr = b"*** FAILED *** (tohost = 7)\n" if mode == "direct7" else b""
                if (type(fixture) is not dict or fixture.get("fixture_checks_passed") is not True
                        or fixture.get("done") is not True
                        or fixture.get("run_return") != expected or fixture.get("exit_code") != expected
                        or fixture.get("scope") != "native-host-only" or fixture.get("mode") != mode
                        or stderr != expected_stderr):
                    raise ProbeError("native fixture facts did not match: " + variant + " " + mode)
                row = {"variant": variant, "mode": mode, "host_status": record["exit_code"],
                       "fixture": fixture, "stderr": stderr.decode(), "command": record["name"]}
                result["cases"].append(row)
                if variant == "observed":
                    assessment = assessor.assess_exit(witness, run_id=identity, binding_sha256=binding,
                                                      expected_target_exit=expected)
                    row.update(witness=witness.name, fixture_binding=binding_record, assessment=assessment)
                    event = assessment.get("event") or {}
                    present, signal_exit = mode != "signal-only", "signal" in mode
                    if (event.get("target_exit_present") is not present
                            or event.get("signal_exit") is not signal_exit
                            or event.get("raw_exit_code") != ((expected << 1 | 1) if present else None)
                            or event.get("target_exit_code") != (expected if present else None)
                            or assessment["status"] != ("failed" if signal_exit else "observed")
                            or assessment["target_completion_verified"] is not (not signal_exit)
                            or assessment["hardware_qualified"] is not False
                            or assessment["g1_gate_passed"] is not False):
                        raise ProbeError("observer/parser facts did not match: " + mode)
                    if (fixture, record["exit_code"], stderr) != baseline[mode]:
                        raise ProbeError("overlay changed ordinary native behavior: " + mode)
                else:
                    if witness.exists() or witness.is_symlink():
                        raise ProbeError("unmodified binary unexpectedly created a witness")
                    baseline[mode] = (fixture, record["exit_code"], stderr)
        check()
        result.update(status="passed", native_processes=12, signal_only_rejection_observed=True,
                      mixed_signal_rejection_observed=True, synthetic_config="synthetic-config/config.h")
    except (ProbeError, observer.ObserverError, OSError, ValueError, RuntimeError) as error:
        _retain_error(result, error)
    finally:
        try:
            if created:
                _finalize_probe(output, result, started, deadline, cancellation, restore_handlers)
            else:
                restore_handlers()
                _retain_final_state(result, started, deadline, cancellation)
        finally:
            restore_handlers()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="read-only inspection (default)")
    mode.add_argument("--execute", action="store_true", help="explicitly build and run twelve native processes")
    parser.add_argument("--source-root", type=Path, help="existing Spike directory at the pinned source hashes")
    parser.add_argument("--output", type=Path, help="fresh output leaf; its parent must already exist")
    parser.add_argument("--total-seconds", type=float, default=180, help="aggregate deadline, maximum 300 seconds")
    parser.add_argument("--command-seconds", type=float, default=45, help="per-build-command deadline, maximum 60")
    parser.add_argument("--case-seconds", type=float, default=5, help="per-native-case deadline, maximum 30")
    parser.add_argument("--max-log-bytes", type=int, default=1024 * 1024, help="per-stream sampled limit, maximum 4 MiB")
    parser.add_argument("--min-free-gib", type=float, default=1, help="sampled disk floor, minimum 1 GiB")
    arguments = parser.parse_args(argv)
    if arguments.execute and (arguments.source_root is None or arguments.output is None):
        parser.error("--execute requires explicit --source-root and --output")
    try:
        budget = limits(arguments.total_seconds, arguments.command_seconds, arguments.case_seconds,
                        arguments.max_log_bytes, arguments.min_free_gib)
        result = (execute_probe if arguments.execute else plan_probe)(
            arguments.source_root, arguments.output, budget=budget)
    except (ProbeError, observer.ObserverError, OSError) as error:
        result = {"status": "blocked", "reasons": [str(error)], **FALSE_FLAGS}
    if arguments.execute and arguments.output is not None:
        result["output"] = str(arguments.output.absolute())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"planned", "passed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
