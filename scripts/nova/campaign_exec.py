#!/usr/bin/env python3
"""Bounded, direct-argv execution for approved, trusted NOVA build commands.

This is an evidence runner, not a sandbox or a resource-approval mechanism.
Timeout cleanup adds at most CLEANUP_GRACE_SECONDS, then integrity capture reads
at most MAX_LOG_BYTES per log. Callers must reserve that overhead in aggregate
budgets. Log/disk limits are sampled during execution and checked after exit;
an over-limit log is rejected, never truncated into apparently complete evidence.
Only the new session's process group is signalled. A program that deliberately
escapes its session is outside this trusted-build runner's containment model.
"""

from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import threading
import time


MAX_LOG_BYTES = 64 * 1024 * 1024
MAX_TIMEOUT_SECONDS = 7200
CLEANUP_GRACE_SECONDS = 2.0
TERM_GRACE_SECONDS = 0.5
POLL_SECONDS = 0.05
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _number(value, lower, upper):
    return (type(value) in (int, float) and lower <= value <= upper
            and math.isfinite(value))


def _safe_directory(value):
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("directory must be absolute and traversal-free")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("symlink directory is not accepted")
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("directory is not a directory")
    return path, (info.st_dev, info.st_ino)


def _disk_issue(cwd, output_dir, minimum_bytes):
    try:
        for path in {cwd, output_dir}:
            free = shutil.disk_usage(path).free
            if type(free) is not int or free < minimum_bytes:
                return "available disk is below the configured floor"
    except OSError:
        return "available disk could not be verified"
    return None


def _group_alive(pid):
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _signal_group(pid, signum):
    try:
        os.killpg(pid, signum)
    except ProcessLookupError:
        pass
    except OSError:
        return False
    return True


def _stop_group(process):
    """Terminate only the session group created for this direct child."""
    deadline = time.monotonic() + CLEANUP_GRACE_SECONDS
    _signal_group(process.pid, signal.SIGTERM)
    term_deadline = min(deadline, time.monotonic() + TERM_GRACE_SECONDS)
    while time.monotonic() < term_deadline:
        process.poll()
        if not _group_alive(process.pid):
            break
        time.sleep(min(POLL_SECONDS, max(0, term_deadline - time.monotonic())))
    if _group_alive(process.pid):
        _signal_group(process.pid, signal.SIGKILL)
    try:
        process.wait(timeout=max(0, deadline - time.monotonic()))
    except (subprocess.TimeoutExpired, OSError):
        return False
    return True


def _log_issue(streams, maximum):
    try:
        for stream in streams.values():
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                return "stage log is not a regular file"
            if info.st_size > maximum:
                return "stage log exceeded configured byte limit"
    except OSError:
        return "stage log size could not be verified"
    return None


def _capture_log(directory_fd, filename, expected_inode, maximum):
    """Return hash/size only for the same stable, private, bounded regular log."""
    try:
        before = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or (before.st_dev, before.st_ino) != expected_inode):
            return None, None, "stage log was replaced or is not private and regular"
        if before.st_size > maximum:
            return None, before.st_size, "stage log exceeded configured byte limit"
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        with os.fdopen(os.open(filename, flags, dir_fd=directory_fd), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if _identity(before) != _identity(opened):
                return None, None, "stage log changed before integrity capture"
            hasher = hashlib.sha256()
            size = 0
            while True:
                block = stream.read(min(65536, maximum + 1 - size))
                if not block:
                    break
                size += len(block)
                if size > maximum:
                    return None, size, "stage log exceeded configured byte limit"
                hasher.update(block)
            after = os.fstat(stream.fileno())
        current = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
        if (_identity(opened) != _identity(after)
                or _identity(after) != _identity(current)
                or current.st_nlink != 1 or size != current.st_size):
            return None, size, "stage log changed during integrity capture"
        return hasher.hexdigest(), size, None
    except (OSError, ValueError):
        return None, None, "stage log integrity could not be captured"


class _ExecutionInterrupted(Exception):
    """Cancellation observed at a safe boundary, never raised by a handler."""


def run_command(cwd, output_dir, name, argv, timeout_seconds, min_free_gib=10,
                env=None, max_log_bytes=MAX_LOG_BYTES):
    """Execute an argv without a shell, recording actual parent exit and logs.

The caller supplies existing absolute non-symlink directories. Each log is
created exclusively with mode 0600; existing files are never overwritten.
The environment is passed to Popen but is never copied into evidence metadata.
Nonzero target exits remain failed even when a higher layer expects failure.
Execution must run on the main thread so scoped SIGINT/SIGTERM handlers can
request bounded cleanup. They never raise inside Popen or cleanup: repeated
signals cannot abandon the child group. Original handlers are restored on return.
This scope does not handle signals delivered outside run_command or SIGKILL.
"""
    cancellation = {"signal": None, "unavailable": False}
    previous_handlers = {}

    def request_cancellation(signum, _frame):
        if cancellation["signal"] is None:
            cancellation["signal"] = signum

    try:
        if threading.current_thread() is not threading.main_thread():
            cancellation["unavailable"] = True
        else:
            try:
                for signum in (signal.SIGINT, signal.SIGTERM):
                    previous_handlers[signum] = signal.getsignal(signum)
                    signal.signal(signum, request_cancellation)
            except (OSError, RuntimeError, ValueError):
                cancellation["unavailable"] = True
        return _run_command(cwd, output_dir, name, argv, timeout_seconds,
                            min_free_gib, env, max_log_bytes, cancellation)
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def _run_command(cwd, output_dir, name, argv, timeout_seconds, min_free_gib,
                 env, max_log_bytes, cancellation):
    started = time.monotonic()
    result = {
        "name": name if isinstance(name, str) and NAME.fullmatch(name) else None,
        "status": "blocked", "exit_code": None, "command": [],
        "stdout": None, "stderr": None,
        "stdout_sha256": None, "stderr_sha256": None,
        "stdout_bytes": None, "stderr_bytes": None,
        "started_utc": _now(), "finished_utc": None, "elapsed_seconds": 0,
        "timed_out": False, "hardware_qualified": False, "g1_gate_passed": False,
        "cleanup_grace_seconds": CLEANUP_GRACE_SECONDS,
    }

    def finish(reason=None):
        if cancellation["signal"] is not None:
            result["status"] = "blocked"
            result["interrupted"] = True
            result["interruption_signal"] = cancellation["signal"]
            reason = "command execution interrupted"
        if reason:
            result["reason"] = reason
        result["finished_utc"] = _now()
        result["elapsed_seconds"] = round(time.monotonic() - started, 6)
        return result

    if cancellation["unavailable"]:
        return finish("command execution requires main-thread cancellation handling")
    if cancellation["signal"] is not None:
        return finish("command execution interrupted")
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        return finish("POSIX process groups and no-follow log creation are required")
    if not isinstance(name, str) or not NAME.fullmatch(name):
        return finish("invalid stage name")
    if (not isinstance(argv, (list, tuple)) or not 1 <= len(argv) <= 256
            or any(not isinstance(arg, str) or len(arg) > 16384
                   or any(char in arg for char in "\x00\r\n") for arg in argv)
            or not argv[0] or argv[0].startswith("-")
            or sum(map(len, argv)) > 65536):
        return finish("invalid direct command arguments")
    if not _number(timeout_seconds, 0.001, MAX_TIMEOUT_SECONDS):
        return finish("invalid stage timeout")
    if not _number(min_free_gib, 1, 50):
        return finish("invalid disk floor")
    if type(max_log_bytes) is not int or not 1 <= max_log_bytes <= MAX_LOG_BYTES:
        return finish("invalid log byte limit")
    if env is not None and (not isinstance(env, dict) or any(
            not isinstance(key, str) or not key or "=" in key or "\x00" in key
            or not isinstance(value, str) or "\x00" in value
            for key, value in env.items())):
        return finish("invalid command environment")
    result.update(command=list(argv), timeout_seconds=timeout_seconds,
                  min_free_gib=min_free_gib, max_log_bytes=max_log_bytes)
    try:
        cwd, cwd_inode = _safe_directory(cwd)
        output_dir, output_inode = _safe_directory(output_dir)
    except (TypeError, ValueError, OSError):
        return finish("working and output directories must be existing safe absolute paths")
    minimum_bytes = int(min_free_gib * 1024 ** 3)
    issue = _disk_issue(cwd, output_dir, minimum_bytes)
    if issue:
        return finish(issue)
    if cancellation["signal"] is not None:
        return finish("command execution interrupted")

    directory_fd = None
    streams = {}
    inodes = {}
    process = None
    reason = None
    try:
        directory_fd = os.open(output_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(directory_fd)
        if (info.st_dev, info.st_ino) != output_inode:
            raise ValueError("output identity changed")
        for channel in ("stdout", "stderr"):
            filename = f"{name}.{channel}.log"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
            descriptor = os.open(filename, flags, 0o600, dir_fd=directory_fd)
            try:
                stream = os.fdopen(descriptor, "wb", buffering=0)
            except BaseException:
                os.close(descriptor)
                raise
            streams[channel] = stream
            info = os.fstat(stream.fileno())
            inodes[channel] = (info.st_dev, info.st_ino)
            result[channel] = filename
        if (_safe_directory(cwd)[1] != cwd_inode
                or _safe_directory(output_dir)[1] != output_inode):
            raise ValueError("directory identity changed")
        if cancellation["signal"] is not None:
            raise _ExecutionInterrupted
        deadline = time.monotonic() + timeout_seconds
        process = subprocess.Popen(
            list(argv), cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=streams["stdout"], stderr=streams["stderr"],
            env=dict(env) if env is not None else None,
            shell=False, start_new_session=True, close_fds=True,
        )
        result["status"] = "failed"
        while process.poll() is None:
            if cancellation["signal"] is not None:
                raise _ExecutionInterrupted
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                result["timed_out"] = True
                reason = "stage deadline exceeded"
                _stop_group(process)
                break
            reason = _log_issue(streams, max_log_bytes)
            if reason:
                _stop_group(process)
                break
            reason = _disk_issue(cwd, output_dir, minimum_bytes)
            if reason:
                result["status"] = "blocked"
                _stop_group(process)
                break
            try:
                process.wait(timeout=min(POLL_SECONDS, remaining))
            except subprocess.TimeoutExpired:
                pass
        if cancellation["signal"] is not None:
            raise _ExecutionInterrupted
        if not reason and time.monotonic() >= deadline:
            result["timed_out"] = True
            reason = "stage deadline exceeded"
            _stop_group(process)
        if not reason and _group_alive(process.pid):
            reason = "command exited with surviving group descendants"
            _stop_group(process)
        result["exit_code"] = process.poll()
        if result["exit_code"] is None:
            reason = reason or "command could not be reaped within cleanup grace"
        elif result["exit_code"] != 0:
            reason = reason or "command exited unsuccessfully"
        elif not reason:
            result["status"] = "passed"
    except (KeyboardInterrupt, _ExecutionInterrupted):
        if cancellation["signal"] is None:
            cancellation["signal"] = signal.SIGINT
        result["status"] = "blocked"
        result["interrupted"] = True
        reason = "command execution interrupted"
        if process is not None:
            _stop_group(process)
            result["exit_code"] = process.poll()
    except (OSError, RuntimeError, TypeError, ValueError):
        result["status"] = "blocked" if process is None else "failed"
        reason = "command launch or exclusive log creation failed"
        if process is not None:
            _stop_group(process)
            result["exit_code"] = process.poll()
    finally:
        for stream in streams.values():
            try:
                stream.close()
            except OSError:
                reason = reason or "stage log could not be closed"
                result["status"] = "failed"

    try:
        try:
            if (_safe_directory(cwd)[1] != cwd_inode
                    or _safe_directory(output_dir)[1] != output_inode):
                raise ValueError("directory identity changed")
        except (OSError, ValueError):
            reason = "working or output directory changed during execution"
            result["status"] = "failed"
        issue = _disk_issue(cwd, output_dir, minimum_bytes)
        if issue:
            reason = issue
            result["status"] = "blocked"
        if directory_fd is not None:
            for channel, inode in inodes.items():
                digest, size, issue = _capture_log(
                    directory_fd, result[channel], inode, max_log_bytes)
                result[f"{channel}_sha256"] = digest
                result[f"{channel}_bytes"] = size
                if issue:
                    if not reason or reason == "command exited unsuccessfully":
                        reason = issue
                    if result["status"] == "passed":
                        result["status"] = "failed"
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
    if result["status"] == "passed" and (reason or result["exit_code"] != 0
            or not result["stdout_sha256"] or not result["stderr_sha256"]):
        result["status"] = "failed"
    return finish(reason)
