#!/usr/bin/env python3
"""Read-only checks of the pinned direct-simulator completion protocol.

The caller must supply separate stdout/stderr from the directly executed,
identified simulator and its real exit status.  A matching record proves only
that this protocol was observed in the supplied files: it does not authenticate
the executable, establish provenance, qualify an ISA, or accept a NOVA gate.

At the pinned Rocket TestDriver.v revision, +verbose prints the stderr PASSED
record after io_success. The pinned SimTSI/HTIF path can also signal success
after a signal-induced shutdown without a target exit value. This grammar
therefore cannot attest to a target-originated terminal event. See the pins in
nova/upstream-lock.json; this parser never installs or executes those tools.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat


MAX_LOG_BYTES = 64 * 1024 * 1024
MAX_CYCLE_COUNT = (1 << 64) - 1
COMPLETION = re.compile(
    rb"\*\*\* PASSED \*\*\* Completed after[ \t]+([1-9][0-9]{0,19}) simulation cycles\n"
)
COMPLETION_WORDING = re.compile(rb"\bpassed\b|\bcompleted[ \t]+after\b", re.IGNORECASE)
FAILURE_INDICATOR = re.compile(
    rb"\b(?:fail|failed|fatal|timeout|timed[ \t]+out)\b|%Error(?:\b|:)", re.IGNORECASE
)


class _LogFailure(Exception):
    """A fixed, privacy-conscious explanation of unusable evidence."""


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _read_log(value):
    """Read at most one bounded, stable regular file, without following links.

    O_NONBLOCK ensures a changed leaf cannot turn a read into a blocking FIFO
    operation.  Both the pre-open path and opened descriptor must refer to the
    same regular file.  Parent links are rejected too; this is not a substitute
    for the caller retaining immutable, post-process artifacts.
    """
    try:
        path = Path(value).absolute()
        for part in (path, *path.parents):
            if stat.S_ISLNK(part.lstat().st_mode):
                raise _LogFailure("must not use symbolic links")
        before = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise _LogFailure("must be a regular file")
        if before.st_size > MAX_LOG_BYTES:
            raise _LogFailure("exceeds the log byte limit")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(before):
                raise _LogFailure("changed before it could be read")
            data = stream.read(MAX_LOG_BYTES + 1)
            after = os.fstat(stream.fileno())
        # Re-stat the named leaf as well: replacement while its former inode is
        # open must not leave a digest apparently describing a different file.
        current = path.stat(follow_symlinks=False)
        if (_identity(before) != _identity(after)
                or _identity(before) != _identity(current)
                or not stat.S_ISREG(current.st_mode)
                or len(data) != before.st_size):
            raise _LogFailure("changed while it was being read")
        if len(data) > MAX_LOG_BYTES:
            raise _LogFailure("exceeds the log byte limit")
        if data and not data.endswith(b"\n"):
            raise _LogFailure("has an incomplete final line")
        if b"\x00" in data:
            raise _LogFailure("contains binary NUL bytes")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise _LogFailure("is not valid UTF-8 text") from None
        return {
            "data": data, "identity": (after.st_dev, after.st_ino),
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        }
    except _LogFailure:
        raise
    except (OSError, RuntimeError, TypeError, ValueError):
        raise _LogFailure("is missing, unreadable, or invalid") from None


def assess_simulation(stdout_path, stderr_path, exit_code, expected_marker=None,
                      max_cycles=10000000):
    """Assess supplied direct-simulator logs without executing or writing.

    A passed result means exactly one valid, newline-terminated TestDriver
    completion was observed on stderr, the optional exact target record was
    observed once on stdout, and no conflicting failure was observed.  It is a
    protocol check only.  The caller must separately bind these logs and exit
    status to the hashed simulator/target, capture limits and source provenance.
    """
    result = {
        "status": "failed", "target_completion_verified": False,
        "completion_protocol_observed": False,
        "cycles": None, "reasons": [], "hardware_qualified": False,
        "g1_gate_passed": False, "evidence_scope": "observed_completion_protocol_only",
        "stdout_bytes": None, "stdout_sha256": None,
        "stderr_bytes": None, "stderr_sha256": None,
    }
    reasons = result["reasons"]
    if type(exit_code) is not int or exit_code != 0:
        reasons.append("simulator exit status is not the integer zero")
    if type(max_cycles) is not int or not 1 <= max_cycles <= MAX_CYCLE_COUNT:
        reasons.append("max_cycles must be an integer within 1..2^64-1")
    marker = None
    if expected_marker is not None:
        if (not isinstance(expected_marker, str) or not expected_marker
                or any(char in expected_marker for char in "\r\n\x00")):
            reasons.append("expected_marker must be a nonempty single text line")
        else:
            try:
                marker = expected_marker.encode("utf-8") + b"\n"
            except UnicodeEncodeError:
                reasons.append("expected_marker must be valid UTF-8 text")
    # Invalid caller constraints must not trigger filesystem reads.
    if reasons:
        return result

    logs = {}
    for label, path in (("stdout", stdout_path), ("stderr", stderr_path)):
        try:
            logs[label] = _read_log(path)
            result[label + "_bytes"] = logs[label]["bytes"]
            result[label + "_sha256"] = logs[label]["sha256"]
        except _LogFailure as error:
            reasons.append(label + " " + str(error))
    if len(logs) != 2:
        return result
    if logs["stdout"]["identity"] == logs["stderr"]["identity"]:
        reasons.append("stdout and stderr must be separate files")

    stdout = logs["stdout"]["data"]
    stderr = logs["stderr"]["data"]
    for label, data in (("stdout", stdout), ("stderr", stderr)):
        if FAILURE_INDICATOR.search(data):
            reasons.append(label + " contains a failure, fatal, or timeout indicator")
    if COMPLETION_WORDING.search(stdout):
        reasons.append("simulator completion wording appeared on stdout")
    matches = []
    for line in stderr.splitlines(keepends=True):
        complete = COMPLETION.fullmatch(line)
        if complete is not None:
            matches.append(int(complete.group(1)))
        elif COMPLETION_WORDING.search(line):
            reasons.append("stderr contains malformed or prefixed completion wording")
    if len(matches) != 1:
        reasons.append("stderr must contain exactly one valid TestDriver completion record")
    elif not 1 <= matches[0] <= max_cycles:
        reasons.append("observed completion cycle count exceeds the declared bound")
    else:
        result["cycles"] = matches[0]
    if marker is not None:
        count = sum(line == marker for line in stdout.splitlines(keepends=True))
        if count != 1:
            reasons.append("stdout must contain exactly one exact expected target record")
    if not reasons:
        result["status"] = "passed"
        result["completion_protocol_observed"] = True
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdout", type=Path, required=True, help="direct simulator stdout log")
    parser.add_argument("--stderr", type=Path, required=True, help="direct simulator stderr log")
    parser.add_argument("--exit-code", type=int, required=True, help="real direct simulator exit status")
    parser.add_argument("--expected-marker", help="one exact target stdout line, without newline")
    parser.add_argument("--max-cycles", type=int, default=10000000)
    args = parser.parse_args(argv)
    result = assess_simulation(args.stdout, args.stderr, args.exit_code,
                               args.expected_marker, args.max_cycles)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
