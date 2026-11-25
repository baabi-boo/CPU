#!/usr/bin/env python3
"""Verify retained G1 files and reported protocols without executing a command.

Only the supplied record and its own directory's named stdout, stderr, and
dedicated witness files are inspected. Source, toolchain, simulator, workload,
and observer-build identities are checked as metadata by the record validator;
their external paths are never opened. An intact bundle is not authenticated
execution, independent reproduction, hardware qualification, or G1 acceptance.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat


def _sibling(name):
    specification = importlib.util.spec_from_file_location(
        "nova_bundle_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


compare = _sibling("compare_campaigns")
MAX_LOG_BYTES = 64 * 1024 * 1024
MAX_LOG_LINES = 1000000
MAX_WITNESS_BYTES = 4096
MAX_STAGES = 64
MAX_FILES = 160
MAX_BUNDLE_BYTES = 256 * 1024 * 1024
# The record is captured twice. All JSON, log, and witness parsers consume
# captured snapshots without additional I/O.
MAX_READ_BYTES = MAX_BUNDLE_BYTES + compare.MAX_RECORD_BYTES
MAX_REASONS = 80
LIMITATIONS = [
    "Intact means retained file bytes and reported protocol assessments agree with the supplied record.",
    "Files, hashes, process results, and observer events do not authenticate execution or independent builds.",
    "Source, toolchain, binaries, and observer build inputs are metadata only; their external files are not inspected.",
    "Legacy schema-1 evidence is completion protocol only and cannot verify target completion.",
    "No hardware, G1, ISA, or reference-model qualification is awarded.",
]


class _BundleFailure(ValueError):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _open_directory(path):
    """Anchor every component without following a directory symlink."""
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


def _record_path(value):
    if (os.name != "posix" or not all(hasattr(os, flag) for flag in
            ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC"))):
        raise _BundleFailure("blocked", "verification requires no-follow directory support")
    value = os.fspath(value)
    if type(value) is not str or not value or "\x00" in value:
        raise _BundleFailure("blocked", "record path is invalid")
    path = Path(value)
    if ".." in path.parts:
        raise _BundleFailure("blocked", "record path contains parent traversal")
    return path.absolute()


def _basename(value):
    if not compare._relative(value, basename=True):
        return False
    try:
        return len(value.encode("utf-8")) <= 255
    except UnicodeError:
        return False


def _capture(directory, name, limit, budget, *, expected=None, retain=False):
    """Hash one bounded stable regular leaf through an anchored directory."""
    descriptor = None
    try:
        before = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise _BundleFailure("failed", "retained file must be regular and must not be a symlink")
        if not 0 <= before.st_size <= limit:
            raise _BundleFailure("failed", "retained file exceeds its bounded byte limit")
        if expected is not None and before.st_size != expected["size_bytes"]:
            raise _BundleFailure("failed", "retained file size differs from its recorded identity")
        if budget["bytes"] + before.st_size > MAX_READ_BYTES:
            raise _BundleFailure("blocked", "bundle exceeds the total read byte budget")
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        descriptor = os.open(name, flags, dir_fd=directory)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(before):
            raise _BundleFailure("failed", "retained file changed before its bounded read")
        digest = hashlib.sha256()
        length = 0
        chunks = []
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - length))
            if not chunk:
                break
            length += len(chunk)
            budget["bytes"] += len(chunk)
            if length > limit or budget["bytes"] > MAX_READ_BYTES:
                raise _BundleFailure("failed", "retained file grew beyond its bounded read")
            digest.update(chunk)
            if retain:
                chunks.append(chunk)
        after = os.fstat(descriptor)
        current = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (not _identity(before) == _identity(opened) == _identity(after) == _identity(current)
                or length != before.st_size):
            raise _BundleFailure("failed", "retained file changed during its bounded read")
        sha256 = digest.hexdigest()
        if expected is not None and sha256 != expected["sha256"]:
            raise _BundleFailure("failed", "retained file SHA256 differs from its recorded identity")
        return {"identity": _identity(after), "size_bytes": length, "sha256": sha256,
                "data": b"".join(chunks) if retain else None}
    except _BundleFailure:
        raise
    except (OSError, ValueError, TypeError):
        raise _BundleFailure("failed", "retained file is missing, unreadable, or unsafe") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _unchanged(directory, name, snapshot):
    try:
        current = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if _identity(current) != snapshot["identity"]:
            raise _BundleFailure("failed", "retained file changed during bundle verification")
    except OSError:
        raise _BundleFailure("failed", "retained file disappeared during bundle verification") from None


def _same_directory(path, directory):
    current = None
    try:
        current = _open_directory(path)
        original, reopened = os.fstat(directory), os.fstat(current)
        if (original.st_dev, original.st_ino) != (reopened.st_dev, reopened.st_ino):
            raise _BundleFailure("failed", "record directory changed during bundle verification")
    except OSError:
        raise _BundleFailure("failed", "record directory became unavailable or unsafe") from None
    finally:
        if current is not None:
            os.close(current)


def _stages(record, record_name, record_bytes):
    stages = [(record["preflight"]["checker"], None, None)]
    stages.extend((stage, None, None) for stage in record["common_stages"])
    for profile in record["profiles"]:
        stages.append((profile["build"], None, None))
        stages.extend((row["stage"], profile, row) for row in profile["workloads"])
    if len(stages) > MAX_STAGES:
        raise _BundleFailure("blocked", "record exceeds the retained stage count limit")
    names = {record_name}
    total = record_bytes
    for stage, _profile, row in stages:
        references = [(stage[stream], stage[stream + "_bytes"], MAX_LOG_BYTES)
                      for stream in ("stdout", "stderr")]
        if row is not None and record["schema_version"] == 2:
            witness = row["target_exit"]["witness"]
            references.append((witness["path"], witness["size_bytes"], MAX_WITNESS_BYTES))
        for name, size, limit in references:
            if not _basename(name):
                raise _BundleFailure("blocked", "retained references must be safe single basenames")
            if name in names:
                raise _BundleFailure("blocked", "retained file reference is reused or names the record")
            names.add(name)
            if type(size) is not int or not 0 <= size <= limit:
                raise _BundleFailure("blocked", "retained reference has an invalid byte bound")
            total += size
    if len(names) > MAX_FILES or total > MAX_BUNDLE_BYTES:
        raise _BundleFailure("blocked", "record exceeds the aggregate retained file or byte budget")
    return stages


def _protocol_assessment(module, paths, snapshots, row, max_cycles):
    """Use the unchanged protocol grammar on actual bounded log snapshots.

    The module is private to this invocation. Its reader adapter cannot open
    paths, and the parser cannot reopen a directory replaced after capture.
    No shared module or reader used by another caller is modified.
    """
    def read(path):
        snapshot = snapshots.get(os.fspath(path))
        if snapshot is None:
            raise module.evidence._LogFailure("is not a captured bundle log")
        data = snapshot["data"]
        if data and not data.endswith(b"\n"):
            raise module.evidence._LogFailure("has an incomplete final line")
        if b"\x00" in data:
            raise module.evidence._LogFailure("contains binary NUL bytes")
        # The existing grammar uses splitlines(). Bound its object count as
        # well as the input bytes, including adversarial one-byte blank lines.
        # bytes.splitlines() splits bare CR and LF, with CRLF forming one
        # boundary. Count without allocating the potentially large line list.
        line_count = data.count(b"\n") + data.count(b"\r") - data.count(b"\r\n")
        if line_count > MAX_LOG_LINES:
            raise module.evidence._LogFailure("exceeds the protocol parser line-count budget")
        try:
            data.decode("utf-8")
        except UnicodeError:
            raise module.evidence._LogFailure("is not valid UTF-8 text") from None
        return {"data": data, "identity": snapshot["identity"][:2],
                "bytes": snapshot["size_bytes"], "sha256": snapshot["sha256"]}

    module.evidence._read_log = read
    computed = module.assess_workload(
        paths[0], paths[1], row["stage"]["exit_code"],
        module.workload_contract(row["id"]), max_cycles)
    if computed["status"] != "passed" or computed["expectation_met"] is not True:
        raise _BundleFailure("failed", "retained workload protocol failed: "
                             + "; ".join(computed["reasons"][:3]))
    # Older protocol-only records did not always retain evidence_scope. Every
    # substantive result field must still equal the independently parsed logs.
    recorded = row["assessment"]
    fields = set(computed) - {"evidence_scope"}
    if "evidence_scope" in recorded:
        fields.add("evidence_scope")
    if not compare._same_contract({key: recorded.get(key) for key in fields},
                                  {key: computed[key] for key in fields}):
        raise _BundleFailure("failed", "retained logs contradict the recorded workload assessment")


def _binding(record, profile, row):
    source = record["source_before"]
    return {
        "schema_version": 1, "configuration": profile["configuration"],
        "workload_id": row["id"], "run_id": row["target_exit"]["binding"]["run_id"],
        "binary_sha256": row["binary"]["sha256"],
        "simulator_sha256": row["simulator_sha256"],
        "observer_manifest_sha256": record["target_exit_observer"]["manifest_sha256"],
        "source_revision": source["revision"], "source_tree": source["tree"],
        "source_state_digest": source["state_digest"],
        "max_cycles": record["resource_limits"]["max_cycles"],
        "seed": record["resource_limits"]["seed"],
    }


def _witness_assessment(module, path, snapshot, record, profile, row):
    binding = _binding(record, profile, row)
    extension = row["target_exit"]
    if not compare._same_contract(binding, extension["binding"]):
        raise _BundleFailure("failed", "witness binding differs from its recomputed campaign context")

    def read(requested):
        if os.fspath(requested) != os.fspath(path):
            raise module._WitnessFailure("is not the captured bundle witness")
        return snapshot["data"]

    # This fresh parser instance also consumes only captured bytes. assess_exit
    # still checks exact JSON, run identity, binding, target code, and flags.
    module._read_witness = read
    computed = module.assess_exit(
        path, run_id=binding["run_id"],
        binding_sha256=hashlib.sha256(compare._canonical(binding)).hexdigest(),
        expected_target_exit=7 if row["id"] == "nova-baseline-fail" else 0)
    if (computed["status"] != "observed" or computed["target_completion_verified"] is not True
            or not compare._same_contract(computed, extension["assessment"])):
        raise _BundleFailure("failed", "retained witness is invalid, replayed, or contradicts its recorded assessment")


def _result(status, reasons, progress):
    return {
        "schema_version": 1, "kind": "nova-campaign-bundle-verification",
        "status": status, "reasons": reasons[:MAX_REASONS],
        "verification_scope": "retained_files_and_reported_protocol_only",
        "hardware_qualified": False, "g1_gate_passed": False,
        "reference_comparison_qualified": False, "target_completion_verified": False,
        "limitations": list(LIMITATIONS), **progress,
    }


def verify_bundle(record_path):
    """Read-only retained-evidence verification with no execution-path reads.

    ``intact`` means all required retained bytes and protocols agree. ``blocked``
    means the record, references, or budget cannot support verification. ``failed``
    means a retained file is missing, unsafe, changed, or contradicts the record.
    Only complete successful campaign records can produce an intact result;
    process failures, cancellations, and timeouts remain authoritative.
    """
    directory = None
    progress = {"record_schema_version": None, "record_sha256": None,
                "retained_files_checked": 0, "retained_bytes_checked": 0,
                "workload_protocols_checked": 0, "witnesses_checked": 0}
    try:
        path = _record_path(record_path)
        try:
            directory = _open_directory(path.parent)
        except OSError:
            raise _BundleFailure("blocked", "record directory is missing, unreadable, or unsafe") from None
        budget = {"bytes": 0}
        try:
            original = _capture(directory, path.name, compare.MAX_RECORD_BYTES, budget, retain=True)
            record = compare.parse_record_bytes(original.pop("data"))
            _same_directory(path.parent, directory)
            _unchanged(directory, path.name, original)
        except (_BundleFailure, compare.RecordError) as error:
            raise _BundleFailure("blocked", "record cannot be safely loaded: " + str(error)) from None
        version = record.get("schema_version") if type(record) is dict else None
        progress.update(record_schema_version=version if type(version) is int and version in (1, 2) else None,
                        record_sha256=original["sha256"])
        errors = compare._validate(record)
        if errors:
            return _result("blocked", ["record: " + reason for reason in errors], progress)
        stages = _stages(record, path.name, original["size_bytes"])
        captures = {path.name: original}
        identities = {original["identity"][:2]}
        # Each parser imports its own evidence module; snapshot adapters never
        # mutate the runner's, comparator's, or another verifier's module state.
        workload_parser = _sibling("workload_assessment")
        witness_parser = _sibling("htif_exit_evidence") if record["schema_version"] == 2 else None

        def capture(name, limit, expected, retain):
            snapshot = _capture(directory, name, limit, budget, expected=expected, retain=retain)
            if snapshot["identity"][:2] in identities:
                raise _BundleFailure("failed", "multiple retained references alias the same file identity")
            identities.add(snapshot["identity"][:2])
            captures[name] = {key: value for key, value in snapshot.items() if key != "data"}
            progress["retained_files_checked"] += 1
            progress["retained_bytes_checked"] += snapshot["size_bytes"]
            return snapshot

        for stage, profile, row in stages:
            try:
                snapshots = {}
                paths = []
                for stream in ("stdout", "stderr"):
                    name = stage[stream]
                    retained_path = path.parent / name
                    paths.append(retained_path)
                    snapshots[str(retained_path)] = capture(
                        name, MAX_LOG_BYTES,
                        {"size_bytes": stage[stream + "_bytes"], "sha256": stage[stream + "_sha256"]},
                        row is not None)
                if row is not None:
                    _protocol_assessment(workload_parser, paths, snapshots, row,
                                         record["resource_limits"]["max_cycles"])
                    progress["workload_protocols_checked"] += 1
                    if witness_parser is not None:
                        witness = row["target_exit"]["witness"]
                        snapshot = capture(witness["path"], MAX_WITNESS_BYTES, witness, True)
                        _witness_assessment(witness_parser, path.parent / witness["path"],
                                            snapshot, record, profile, row)
                        progress["witnesses_checked"] += 1
            except _BundleFailure as error:
                raise _BundleFailure(error.status, stage["name"] + ": " + str(error)) from None
        # Rehash the record, including its raw formatting, after all evidence.
        current = _capture(directory, path.name, compare.MAX_RECORD_BYTES, budget)
        if (current["identity"] != original["identity"]
                or current["sha256"] != original["sha256"]):
            raise _BundleFailure("failed", "record changed during bundle verification")
        for name, snapshot in captures.items():
            _unchanged(directory, name, snapshot)
        _same_directory(path.parent, directory)
        return _result("intact", [], progress)
    except _BundleFailure as error:
        return _result(error.status, [str(error)], progress)
    except (compare.RecordError, OSError, ValueError, TypeError, KeyError,
            IndexError, AttributeError, OverflowError, RecursionError):
        return _result("blocked", ["record or retained evidence cannot be safely verified"], progress)
    finally:
        if directory is not None:
            os.close(directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True,
                        help="retained campaign JSON beside its log and witness files")
    args = parser.parse_args(argv)
    result = verify_bundle(args.record)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return {"intact": 0, "failed": 1, "blocked": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
