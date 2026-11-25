#!/usr/bin/env python3
"""Assess a bounded, dedicated HTIF terminal-state witness without executing it.

A matching supplied observer event can verify the reported target completion
for the caller's run and binding. It does not authenticate execution, qualify
hardware, or accept a NOVA gate. The campaign must separately check the real
process result, normal output, artifact identities, and capture invariants.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat


MAX_WITNESS_BYTES = 4096
INT32_MAX = (1 << 31) - 1
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
EVENT_FIELDS = frozenset({
    "schema_version", "kind", "run_id", "binding_sha256",
    "target_exit_present", "raw_exit_code", "target_exit_code", "signal_exit",
})


class _WitnessFailure(ValueError):
    """An unusable witness, with no paths or underlying OS details exposed."""


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _open_directory(path):
    """Walk an absolute path using no-follow directory descriptors."""
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


def _open_leaf(path):
    parent = _open_directory(path.parent)
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        return os.open(path.name, flags, dir_fd=parent)
    finally:
        os.close(parent)


def _read_witness(value):
    """Read at most 4096 bytes from one stable nonsymlink regular file.

    Both the initial traversal and the final path recheck reject symlinks in
    every component. Nonblocking opens prevent a replaced leaf from hanging on
    a FIFO. These checks do not promise immutability after this call returns.
    """
    parent = descriptor = reopened = None
    try:
        if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
                or not hasattr(os, "O_DIRECTORY")):
            raise _WitnessFailure("witness requires no-follow file support")
        value = os.fspath(value)
        if not isinstance(value, str) or not value or "\x00" in value:
            raise _WitnessFailure("witness path is invalid")
        path = Path(value)
        if ".." in path.parts:
            raise _WitnessFailure("witness path must not contain parent traversal")
        path = path.absolute()
        parent = _open_directory(path.parent)
        before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise _WitnessFailure("witness must be a regular nonsymlink file")
        if before.st_size > MAX_WITNESS_BYTES:
            raise _WitnessFailure("witness exceeds the 4096-byte limit")
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        descriptor = os.open(path.name, flags, dir_fd=parent)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(before):
            raise _WitnessFailure("witness changed before it could be read")
        chunks = []
        length = 0
        while True:
            chunk = os.read(descriptor, MAX_WITNESS_BYTES + 1 - length)
            if not chunk:
                break
            length += len(chunk)
            if length > MAX_WITNESS_BYTES:
                raise _WitnessFailure("witness exceeds the 4096-byte limit")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if _identity(before) != _identity(after) or length != before.st_size:
            raise _WitnessFailure("witness changed while it was being read")
        reopened = _open_leaf(path)
        current = os.fstat(reopened)
        if (not stat.S_ISREG(current.st_mode)
                or _identity(before) != _identity(current)
                or _identity(before) != _identity(os.fstat(descriptor))):
            raise _WitnessFailure("witness path changed while it was being read")
        return b"".join(chunks)
    except _WitnessFailure:
        raise
    except (OSError, RuntimeError, TypeError, ValueError):
        raise _WitnessFailure("witness is missing, unreadable, or unsafe") from None
    finally:
        for opened in (reopened, descriptor, parent):
            if opened is not None:
                os.close(opened)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _WitnessFailure("witness contains a duplicate JSON key")
        result[key] = value
    return result


def _integer(value):
    if value == "-0":
        raise _WitnessFailure("witness contains a noncanonical JSON integer")
    return int(value)


def _reject_number(_value):
    raise _WitnessFailure("witness numeric fields must be canonical JSON integers")


def _parse_event(data):
    if not data.endswith(b"\n"):
        raise _WitnessFailure("witness must end with a complete newline")
    try:
        text = data.decode("utf-8")
        # The schema is flat. Reject nested containers before invoking the JSON
        # decoder, so even deeply nested bounded input cannot consume its stack.
        depth = 0
        quoted = escaped = False
        for character in text:
            if quoted:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    quoted = False
            elif character == '"':
                quoted = True
            elif character == "[":
                raise _WitnessFailure("witness must be one flat JSON object")
            elif character == "{":
                depth += 1
                if depth > 1:
                    raise _WitnessFailure("witness must be one flat JSON object")
            elif character == "}":
                depth -= 1
        event = json.loads(text, object_pairs_hook=_unique_object,
                           parse_int=_integer, parse_float=_reject_number,
                           parse_constant=_reject_number)
        if type(event) is not dict:
            raise _WitnessFailure("witness must be one flat JSON object")
        return event
    except _WitnessFailure:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise _WitnessFailure("witness is not valid bounded UTF-8 JSON") from None


def _hex64(value):
    return type(value) is str and HEX64.fullmatch(value) is not None


def assess_exit(path, *, run_id, binding_sha256, expected_target_exit):
    """Assess exactly one supplied observer witness for expected target 0 or 7.

    All failure paths leave both observation flags false. Parsed event fields
    and the safely captured bytes' digest remain available for diagnosis; they
    must never override a failing process or campaign assessment. Invalid caller
    constraints are rejected without reading the filesystem. Replay detection
    here means matching the caller's run ID and binding; campaign-wide nonce
    uniqueness remains the runner and comparator's responsibility.
    """
    result = {
        "status": "failed", "target_exit_observed": False,
        "target_completion_verified": False, "hardware_qualified": False,
        "g1_gate_passed": False, "reasons": [], "witness_sha256": None,
        "witness_bytes": None, "event": None,
    }
    reasons = result["reasons"]
    if not _hex64(run_id):
        reasons.append("run_id must be 64 lowercase hexadecimal characters")
    if not _hex64(binding_sha256):
        reasons.append("binding_sha256 must be 64 lowercase hexadecimal characters")
    if type(expected_target_exit) is not int or expected_target_exit not in {0, 7}:
        reasons.append("expected_target_exit must be the integer 0 or 7")
    if reasons:
        return result
    try:
        data = _read_witness(path)
        result["witness_sha256"] = hashlib.sha256(data).hexdigest()
        result["witness_bytes"] = len(data)
        event = _parse_event(data)
        result["event"] = event
    except _WitnessFailure as error:
        reasons.append(str(error))
        return result
    except OSError:
        # A descriptor close can fail while the reader is unwinding; its raw
        # operating-system details must not escape the assessment interface.
        reasons.append("witness could not be safely read and closed")
        return result
    if set(event) != EVENT_FIELDS:
        reasons.append("witness must contain exactly the observer fields")
        return result
    if type(event["schema_version"]) is not int or event["schema_version"] != 1:
        reasons.append("witness schema_version must be the integer 1")
    if type(event["kind"]) is not str or event["kind"] != "nova-htif-exit":
        reasons.append("witness kind must be nova-htif-exit")
    if not _hex64(event["run_id"]) or event["run_id"] != run_id:
        reasons.append("witness run_id does not match the supplied run")
    if (not _hex64(event["binding_sha256"])
            or event["binding_sha256"] != binding_sha256):
        reasons.append("witness binding_sha256 does not match the supplied binding")
    if type(event["target_exit_present"]) is not bool:
        reasons.append("witness target_exit_present must be a JSON boolean")
    if type(event["signal_exit"]) is not bool:
        reasons.append("witness signal_exit must be a JSON boolean")
    if event["signal_exit"] is not False:
        reasons.append("witness must not report a signal exit")
    if event["target_exit_present"] is not True:
        reasons.append("witness does not report a present target exit")
        if event["raw_exit_code"] is not None or event["target_exit_code"] is not None:
            reasons.append("an absent target exit must have null exit codes")
    else:
        raw = event["raw_exit_code"]
        decoded = event["target_exit_code"]
        raw_valid = type(raw) is int and 1 <= raw <= INT32_MAX and (raw & 1) == 1
        if not raw_valid:
            reasons.append("raw_exit_code must be a positive odd signed32 integer")
        if type(decoded) is not int:
            reasons.append("target_exit_code must be a JSON integer")
        elif raw_valid and decoded != (raw >> 1):
            reasons.append("target_exit_code does not decode raw_exit_code")
        if raw_valid and raw != ((expected_target_exit << 1) | 1):
            reasons.append("raw_exit_code does not match the expected target exit")
        if type(decoded) is int and decoded != expected_target_exit:
            reasons.append("target_exit_code does not match the expected target exit")
    if not reasons:
        result["status"] = "observed"
        result["target_exit_observed"] = True
        result["target_completion_verified"] = True
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--witness", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--binding-sha256", required=True)
    parser.add_argument("--expected-target-exit", type=int, required=True)
    args = parser.parse_args(argv)
    result = assess_exit(args.witness, run_id=args.run_id,
                         binding_sha256=args.binding_sha256,
                         expected_target_exit=args.expected_target_exit)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result["status"] == "observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
