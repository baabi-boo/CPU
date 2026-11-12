#!/usr/bin/env python3
"""Bounded, read-only provenance capture for the G1 campaign.

Hashes and ELF structure are observations, not authenticity, execution, device
inventory, address-map correctness, or hardware qualification. This module never
runs a captured binary, a build, a Git hook, or a dependency fetch.
"""

import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import signal
import stat
import struct
import subprocess
import time


MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_INPUT_BYTES = 1024 * 1024
MAX_PROFILE_BYTES = 2 * 1024 * 1024 * 1024
MAX_PROFILE_FILES = 8192
MAX_DIRECTORY_ENTRIES = 20000
MAX_DIRECTORY_DEPTH = 20
MAX_SUBMODULES = 512
MAX_SUBMODULE_DEPTH = 16
MAX_GIT_BYTES = 8 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 20
CONFIGURATIONS = frozenset({"RocketConfig", "NovaM1BaselineConfig"})
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
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


class ArtifactError(ValueError):
    """A local capture could not be safely and completely performed."""


def _relative(value):
    if (not isinstance(value, str) or not value or len(value) > 4096
            or "\\" in value or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
            or PurePosixPath(value).is_absolute()
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ArtifactError("unsafe relative path")
    return value


def _root(value):
    try:
        path = Path(value)
        if ".." in path.parts:
            raise ArtifactError("unsafe root path")
        path = Path(os.path.abspath(path))
        descriptor = _open_directory(path)
        os.close(descriptor)
        return path
    except (OSError, TypeError, ValueError) as error:
        if isinstance(error, ArtifactError):
            raise
        raise ArtifactError("root is not a nonsymlink directory") from None


def _open_directory(path):
    """Open every directory component without following any symlinks."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            following = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _file_path(root, path):
    try:
        value = os.fspath(path)
        if not isinstance(value, str):
            raise ArtifactError("file path must be text")
        candidate = Path(value)
        if candidate.is_absolute():
            value = candidate.relative_to(root).as_posix()
        return _relative(value)
    except (TypeError, ValueError):
        raise ArtifactError("file path is outside the capture root or unsafe") from None


def _open_file(root, relative):
    parent = _open_directory(root / PurePosixPath(relative).parent)
    try:
        return os.open(PurePosixPath(relative).name,
                       os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                       dir_fd=parent)
    finally:
        os.close(parent)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _elf(descriptor, size, kind, mode):
    """Validate ELF64 headers, load extents and the file-backed entry point."""
    header = os.pread(descriptor, 64, 0)
    if len(header) != 64:
        raise ArtifactError("ELF header is truncated")
    (ident, elf_type, machine, version, entry, phoff, shoff, _flags,
     ehsize, phentsize, phnum, shentsize, shnum, shstrndx) = struct.unpack(
         "<16sHHIQQQIHHHHHH", header)
    expected_machine = 243 if kind == "riscv_elf" else 62
    allowed_types = {2} if kind == "riscv_elf" else {2, 3}
    if (ident[:7] != b"\x7fELF\x02\x01\x01" or version != 1
            or machine != expected_machine or elf_type not in allowed_types
            or ehsize != 64 or ident[7] not in {0, 3}):
        raise ArtifactError("ELF is not the required little-endian executable architecture")
    if kind == "simulator" and not mode & 0o111:
        raise ArtifactError("simulator has no executable permission bit")
    if (phoff < 64 or phentsize != 56 or not 1 <= phnum <= 4096
            or phoff + phnum * phentsize > size):
        raise ArtifactError("ELF program-header table is invalid or truncated")
    # Extended section counts are deliberately unsupported rather than guessed.
    if shoff:
        if (shoff < 64 or shentsize != 64 or not 1 <= shnum < 0xff00
                or shoff + shnum * shentsize > size
                or shstrndx >= shnum):
            raise ArtifactError("ELF section-header table is invalid or truncated")
        for number in range(shnum):
            section = os.pread(descriptor, 64, shoff + number * 64)
            if len(section) != 64:
                raise ArtifactError("ELF section header is truncated")
            _name, section_type, _flags, _addr, offset, length, *_rest = struct.unpack(
                "<IIQQQQIIQQ", section)
            if section_type not in {0, 8} and offset + length > size:
                raise ArtifactError("ELF section contents are out of bounds")
    elif shnum or shstrndx:
        raise ArtifactError("ELF section count has no section table")
    executable_entry = False
    loads = 0
    for number in range(phnum):
        program = os.pread(descriptor, 56, phoff + number * 56)
        if len(program) != 56:
            raise ArtifactError("ELF program header is truncated")
        ptype, flags, offset, address, _physical, filesz, memsz, align = struct.unpack(
            "<IIQQQQQQ", program)
        if offset + filesz > size:
            raise ArtifactError("ELF program contents are out of bounds")
        if ptype != 1:
            continue
        loads += 1
        if (filesz > memsz or address + memsz > 1 << 64
                or (align > 1 and (align & (align - 1) or offset % align != address % align))):
            raise ArtifactError("ELF load segment has invalid extents or alignment")
        if flags & 1 and address <= entry < address + filesz:
            executable_entry = True
    if not loads or not executable_entry:
        raise ArtifactError("ELF has no file-backed executable entry point")


def _capture(root, path, kind, max_bytes, retain=False):
    if type(max_bytes) is not int or max_bytes < 1 or max_bytes > MAX_FILE_BYTES:
        raise ArtifactError("invalid file capture limit")
    if not isinstance(kind, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", kind):
        raise ArtifactError("invalid artifact kind")
    root = _root(root)
    relative = _file_path(root, path)
    descriptor = None
    try:
        descriptor = _open_file(root, relative)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ArtifactError("capture requires a regular file")
        if before.st_size > max_bytes:
            raise ArtifactError("file exceeds the capture limit")
        if kind in {"riscv_elf", "simulator"}:
            _elf(descriptor, before.st_size, kind, before.st_mode)
        digest = hashlib.sha256()
        chunks = []
        length = 0
        while True:
            chunk = os.read(descriptor, min(65536, max_bytes - length + 1))
            if not chunk:
                break
            length += len(chunk)
            if length > max_bytes:
                raise ArtifactError("file grew beyond the capture limit")
            digest.update(chunk)
            if retain:
                chunks.append(chunk)
        after = os.fstat(descriptor)
        if length != before.st_size or _identity(before) != _identity(after):
            raise ArtifactError("file changed during capture")
        reopened = _open_file(root, relative)
        try:
            if _identity(os.fstat(reopened)) != _identity(after):
                raise ArtifactError("file path changed during capture")
        finally:
            os.close(reopened)
        record = {"path": relative, "size_bytes": length,
                  "sha256": digest.hexdigest(), "kind": kind}
        return record, b"".join(chunks) if retain else None
    except OSError:
        raise ArtifactError("file is missing, unreadable, or a symlink") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def capture_file(root, path, kind="artifact", max_bytes=MAX_FILE_BYTES):
    """Hash one stable, contained regular file without executing it."""
    return _capture(root, path, kind, max_bytes)[0]


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactError("duplicate JSON key")
        result[key] = value
    return result


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ArtifactError("nonfinite JSON value")
    return number


def _json(data):
    try:
        return json.loads(data, object_pairs_hook=_unique,
                          parse_float=_finite_float,
                          parse_constant=lambda _value: (_ for _ in ()).throw(
                              ArtifactError("nonfinite JSON value")))
    except (ValueError, UnicodeError, RecursionError):
        raise ArtifactError("invalid bounded JSON input") from None


def _git(root, *args):
    """Run only the caller's fixed read-only Git commands, with bounded output."""
    argv = ["git", "--no-pager", "--no-optional-locks", "-c", "core.fsmonitor=false",
            "-c", "core.hooksPath=/dev/null", "-c", "core.untrackedCache=false",
            "-c", "fetch.recurseSubmodules=false", "-c", "protocol.allow=never",
            "-C", str(root), *args]
    env = {"PATH": os.environ.get("PATH", os.defpath), "LC_ALL": "C",
           "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1",
           "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null"}
    process = None
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=env, start_new_session=True)
        deadline = time.monotonic() + GIT_TIMEOUT_SECONDS
        chunks = []
        size = 0
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, True)
            selector.register(process.stderr, selectors.EVENT_READ, False)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ArtifactError("local Git capture timed out")
                for key, _events in selector.select(min(remaining, 0.2)):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    size += len(data)
                    if size > MAX_GIT_BYTES:
                        raise ArtifactError("local Git output exceeds the capture limit")
                    if key.data:
                        chunks.append(data)
        process.wait(timeout=max(0.01, deadline - time.monotonic()))
        if process.returncode != 0:
            raise ArtifactError("local read-only Git capture failed")
        return b"".join(chunks)
    except (OSError, subprocess.TimeoutExpired):
        raise ArtifactError("local read-only Git capture unavailable") from None
    finally:
        if process is not None:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()


def _revision(root, selector):
    try:
        value = _git(root, "rev-parse", "--verify", selector).decode("ascii").strip()
    except UnicodeError:
        raise ArtifactError("invalid local Git object identity") from None
    if not SHA1.fullmatch(value):
        raise ArtifactError("invalid local Git object identity")
    return value


def _git_root(root):
    try:
        top = _git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()
        if Path(top) != root:
            raise ArtifactError("capture root is not the Git worktree root")
    except UnicodeError:
        raise ArtifactError("invalid local Git root") from None


def _status(root):
    # Git status honors index flags that can conceal modified tracked inputs.
    # Reject them even when the current file happens to match HEAD: a clean
    # capture must not depend on a developer's index visibility settings.
    # This path is also used for every initialized recursive submodule.
    for entry in _git(root, "ls-files", "--cached", "-v", "-z").split(b"\0"):
        if not entry:
            continue
        if len(entry) < 3 or entry[1:2] != b" ":
            raise ArtifactError("invalid Git index flag record")
        flag = entry[:1]
        if flag.islower() or flag == b"S":
            raise ArtifactError("Git index assume-unchanged or skip-worktree flags are unsupported")
        if flag not in b"HMRCK":
            raise ArtifactError("unsupported Git index flag record")
    return _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all",
                "--ignore-submodules=none")


def _gitlinks(root):
    result = {}
    for entry in _git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        try:
            header, path = entry.split(b"\t", 1)
            mode, revision, stage = header.split(b" ")
            if mode != b"160000":
                continue
            relative = _relative(path.decode("utf-8"))
            pin = revision.decode("ascii")
            if stage != b"0" or not SHA1.fullmatch(pin) or relative in result:
                raise ArtifactError("invalid or conflicted local gitlink")
            result[relative] = pin
        except (ValueError, UnicodeError):
            raise ArtifactError("invalid local Git index record") from None
    return result


def _submodules(root, top_links):
    rows = []

    def visit(directory, links, prefix="", depth=0):
        if depth > MAX_SUBMODULE_DEPTH:
            raise ArtifactError("nested gitlink depth exceeds the capture limit")
        for relative, pin in sorted(links.items()):
            if len(rows) >= MAX_SUBMODULES:
                raise ArtifactError("gitlink count exceeds the capture limit")
            path = (PurePosixPath(prefix) / relative).as_posix()
            candidate = directory / relative
            try:
                info = candidate.lstat()
            except FileNotFoundError:
                info = None
            if info is not None and not stat.S_ISDIR(info.st_mode):
                raise ArtifactError("gitlink worktree is not a nonsymlink directory")
            if info is not None:
                # Also reject symlinks in ancestor components of gitlink paths.
                descriptor = _open_directory(candidate)
                os.close(descriptor)
            git_marker = candidate / ".git"
            initialized = git_marker.exists() or git_marker.is_symlink()
            row = {"path": path, "pin": pin, "revision": None,
                   "initialized": False, "clean": None, "state": "uninitialized"}
            rows.append(row)
            if not initialized:
                continue
            if git_marker.is_symlink():
                raise ArtifactError("symlink Git metadata is not a supported worktree")
            _git_root(candidate)
            revision = _revision(candidate, "HEAD")
            clean = not _status(candidate)
            row.update(revision=revision, initialized=True, clean=clean,
                       state="mismatch" if revision != pin else "at_pin" if clean else "dirty")
            visit(candidate, _gitlinks(candidate), path, depth + 1)

    try:
        visit(root, top_links)
    except OSError:
        raise ArtifactError("gitlink worktree cannot be captured safely") from None
    return sorted(rows, key=lambda item: item["path"])


def capture_source(root):
    """Observe source/pin state; ignored build outputs do not enter its digest.

    ``clean`` is Git cleanliness, not proof that optional or required submodules
    are initialized. Prerequisite qualification remains a separate check.
    """
    root = _root(root)
    _git_root(root)
    revision = _revision(root, "HEAD")
    tree = _revision(root, "HEAD^{tree}")
    status = _status(root)
    _, raw_lock = _capture(root, "nova/upstream-lock.json", "source", MAX_INPUT_BYTES, True)
    manifest = _json(raw_lock)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("preserved_blobs"), dict):
        raise ArtifactError("invalid source pin manifest")
    lock_paths = {path for path in manifest["preserved_blobs"] if path.startswith("conda-reqs/")}
    if lock_paths != CONDA_INPUTS:
        raise ArtifactError("source pin manifest must retain all nine Conda inputs")
    expected_links = {}
    if not isinstance(manifest.get("submodules"), list):
        raise ArtifactError("invalid source pin list")
    for row in manifest["submodules"]:
        if not isinstance(row, dict):
            raise ArtifactError("invalid source pin row")
        path = _relative(row.get("path"))
        pin = row.get("commit")
        if not isinstance(pin, str) or not SHA1.fullmatch(pin) or path in expected_links:
            raise ArtifactError("invalid or repeated source pin")
        expected_links[path] = pin
    links = _gitlinks(root)
    if links != expected_links:
        raise ArtifactError("indexed gitlinks do not match the preserved source pins")
    submodules = _submodules(root, links)
    lock_hashes = {path: capture_file(root, path, "source", MAX_INPUT_BYTES)["sha256"]
                   for path in sorted(CONDA_INPUTS)}
    source_inputs = {path: capture_file(root, path, "source", MAX_INPUT_BYTES)["sha256"]
                     for path in sorted(SOURCE_INPUTS)}
    # The manifest used above must be exactly the bytes included in the snapshot.
    if source_inputs["nova/upstream-lock.json"] != hashlib.sha256(raw_lock).hexdigest():
        raise ArtifactError("source pin manifest changed during capture")
    if (revision != _revision(root, "HEAD") or tree != _revision(root, "HEAD^{tree}")
            or status != _status(root) or links != _gitlinks(root)):
        raise ArtifactError("Git source state changed during capture")
    clean = not status and all(row["state"] not in {"dirty", "mismatch"} for row in submodules)
    result = {"revision": revision, "tree": tree, "clean": clean,
              "lock_hashes": lock_hashes, "source_inputs": source_inputs,
              "submodules": submodules}
    state = dict(result, status_sha256=hashlib.sha256(status).hexdigest())
    result["state_digest"] = hashlib.sha256(json.dumps(
        state, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    info = root.stat()
    # This is a diagnostic discriminator, not an independent-run or trust proof.
    result["checkout_identity_sha256"] = hashlib.sha256(
        (str(root) + "\0" + str(info.st_dev) + "\0" + str(info.st_ino)).encode()).hexdigest()
    return result


def _generated_files(root, relative):
    """Walk only this configuration's generated directory, with hard bounds."""
    start = root / relative
    descriptor = _open_directory(start)
    os.close(descriptor)
    pending = [(relative, 0)]
    count = 0
    selected = []
    while pending:
        current, depth = pending.pop()
        if depth > MAX_DIRECTORY_DEPTH:
            raise ArtifactError("generated directory depth exceeds the capture limit")
        descriptor = _open_directory(root / current)
        try:
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    count += 1
                    if count > MAX_DIRECTORY_ENTRIES:
                        raise ArtifactError("generated directory count exceeds the capture limit")
                    child = _relative((PurePosixPath(current) / entry.name).as_posix())
                    if entry.is_symlink():
                        raise ArtifactError("generated directory contains a symlink")
                    if entry.is_dir(follow_symlinks=False):
                        pending.append((child, depth + 1))
                    elif entry.is_file(follow_symlinks=False):
                        suffix = PurePosixPath(child).suffix
                        if suffix in {".v", ".sv", ".dts", ".json"}:
                            selected.append(child)
                            if len(selected) > MAX_PROFILE_FILES:
                                raise ArtifactError("artifact count exceeds the capture limit")
                    else:
                        raise ArtifactError("generated directory contains a nonregular entry")
        finally:
            os.close(descriptor)
    return sorted(selected)


def capture_profile_artifacts(root, configuration):
    """Capture exact-profile artifacts; ``captured`` is not semantic validation.

    Paths follow variables.mk's build_dir/GEN_COLLATERAL_DIR and the Verilator
    Makefile's simulator naming. JSON is retained as metadata, never described
    as a verified address map or parameter inventory.
    """
    artifacts = []
    reasons = []
    try:
        if configuration not in CONFIGURATIONS:
            raise ArtifactError("unsupported campaign configuration")
        root = _root(root)
        simulator = f"sims/verilator/simulator-chipyard.harness-{configuration}"
        artifacts.append(capture_file(root, simulator, "simulator"))
        long_name = f"chipyard.harness.TestHarness.{configuration}"
        relative = f"sims/verilator/generated-src/{long_name}"
        total = artifacts[0]["size_bytes"]
        for path in _generated_files(root, relative):
            if len(artifacts) >= MAX_PROFILE_FILES:
                raise ArtifactError("artifact count exceeds the capture limit")
            if total >= MAX_PROFILE_BYTES:
                raise ArtifactError("profile artifacts exceed the aggregate byte limit")
            suffix = PurePosixPath(path).suffix
            kind = "rtl" if suffix in {".v", ".sv"} else "device_tree" if suffix == ".dts" else "metadata"
            limit = MAX_INPUT_BYTES if kind in {"device_tree", "metadata"} else MAX_FILE_BYTES
            limit = min(limit, MAX_PROFILE_BYTES - total)
            record, data = _capture(root, path, kind, limit, kind != "rtl")
            total += record["size_bytes"]
            if total > MAX_PROFILE_BYTES:
                raise ArtifactError("profile artifacts exceed the aggregate byte limit")
            if record["size_bytes"] == 0:
                raise ArtifactError("generated artifact is empty")
            if kind == "metadata":
                value = _json(data)
                if not isinstance(value, (dict, list)) or not value:
                    raise ArtifactError("generated JSON metadata must be a nonempty object or array")
            elif kind == "device_tree" and b"/dts-v1/;" not in data:
                raise ArtifactError("generated device tree has no DTS version marker")
            artifacts.append(record)
        kinds = {item["kind"] for item in artifacts}
        for missing in sorted({"simulator", "rtl", "device_tree", "metadata"} - kinds):
            reasons.append("missing configuration-specific " + missing + " artifact")
    except (ArtifactError, OSError, TypeError) as error:
        # Error text is fixed by this module: no absolute paths or external logs.
        reasons.append(str(error) if isinstance(error, ArtifactError)
                       else "configuration artifacts are missing or unreadable")
    return {"status": "blocked" if reasons else "captured", "artifacts": artifacts,
            "reasons": reasons}
