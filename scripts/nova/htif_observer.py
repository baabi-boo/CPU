#!/usr/bin/env python3
"""Prepare a hash-pinned, local HTIF stop observer without changing upstream.

This helper does not download, install, build, execute a target, or qualify
hardware. An ordinary static FESVR archive and compatible prepared inputs are
required. Their recorded hashes identify bytes; they do not authenticate their
compiler, ABI, execution, or provenance. All stored paths are relocatable.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


DEFAULT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_REL = "nova-out/htif-observer"
SPIKE_REL = "toolchains/riscv-tools/riscv-isa-sim"
NATIVE_REL = "software/nova/observer/nova_htif_exit.cc"
HEADER_REL = "software/nova/observer/nova_htif_exit.h"
MAKE_REL = "software/nova/observer/observer.mk"
GENERATOR_REL = "scripts/nova/htif_observer.py"
PINNED_SPIKE_COMMIT = "9c190a07c6838f6392bafa4ad83acea462c7f759"
PINNED_HTIF_SHA256 = "c669e8352c6e21d61118849b0b969d291b84100e83343659f3d08979ae89a11d"
GENERATED_HTIF_SHA256 = "1a6383e8d9b7bfc4d44c2e674fafe1d8067d826c3c2cd0dae7e20a27e08aef84"
SIM_FLAGS_SHA256 = "d489786f193bc7269b0f953a680a8195ece8dec11f3249ea4edf07757fa8bb8a"
SOURCE_HEADERS = {
    "fesvr/htif.h": "5aec4e8516d1ccc72941af7a728556027a9da88d199978c9434e0996e55be608",
    "fesvr/memif.h": "483a03f681fa03d43afc28c15b6f3c75be444463fd1efcc1980334ab81546461",
    "fesvr/syscall.h": "ef19c0fb7f9f59f99002e267bb545fab682926eadfc2b9ac1727922df67e689b",
    "fesvr/device.h": "14bef783e6b9f8b403bfa91410b6e3250ffd766332d46da47738cb5436ef989e",
    "fesvr/byteorder.h": "af2a8f9dbbbbcfe892bfe464a7b21d34894ae303dbccc2caa1c06b7fac449492",
    "fesvr/rfb.h": "63e1a1ab02d8085e37856c44adc121d4e27f4775faaa7cffa9342bdf17c1f73b",
    "fesvr/elfloader.h": "abbdad19a0a0e9375848e82db9c5a8149dbea48c897934197cad5087c16d4ce0",
    "fesvr/elf.h": "13e82d26bad50fe0fde7e3d999a3d569faa480f9f8c21cb94905b5dfb53c42ca",
    "riscv/platform.h": "91d623c9cafdd44c5883cc06dc6b1904508b05db1bd9518c7c02ede8a5405d1a",
    "riscv/common.h": "0290c94d4315ba6b256b474d64c812f93028b68600bb49916f84ad2f4e5995c1",
    "riscv/trap.h": "7f9e68be8a51994b5d2d76d39b4457f40c683a61706bea410769b68e868abccd",
    "riscv/cfg.h": "a0ea7f5348484f6684f8144ac0cd336ff1ea154a02de60618b15fb4665693427",
    "riscv/decode.h": "463d860f0617520c0d725d2fe18f65388de4d5d942a28a776e1a03d7c90696a1",
    "riscv/encoding.h": "0b1cab26010ad4de8791aa7ac9eea0aae54dc1abe62640c4e242e2d3ca9228e5",
    "softfloat/softfloat_types.h": "b7daff9a2a5d82a569d6cc37ae52231bd20a4b3fc53e7dc24db4d51de23138cc",
}
MAX_INPUT_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 4096
MAX_MANIFEST_BYTES = 64 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SAFE_PATH = re.compile(r"[A-Za-z0-9_./+-]+\Z")
INCLUDE_DIRECTORIES = (
    ("repository", SPIKE_REL + "/fesvr"),
    ("repository", SPIKE_REL + "/riscv"),
    ("repository", SPIKE_REL + "/softfloat"),
    ("riscv", "include/fesvr"),
    ("repository", "software/nova/observer"),
)
IDENTITY_KEYS = {"scope", "path", "sha256", "size_bytes"}
INPUT_PATHS = {
    "generator": GENERATOR_REL,
    "make_fragment": MAKE_REL,
    "upstream_sim_flags": "sims/common-sim-flags.mk",
}
MANIFEST_KEYS = {
    "schema_version", "kind", "source_pin", "output_directory", "source",
    "generated", "native", "header", "archive", "installed_header",
    "installed_config", "source_headers", "inputs", "include_directories",
    "link_order", "hardware_qualified", "g1_gate_passed",
}
METADATA_COPY_KEYS = (
    "source_pin", "source", "generated", "native", "header", "archive",
    "installed_header", "installed_config", "source_headers", "inputs",
    "link_order", "hardware_qualified", "g1_gate_passed",
)
METADATA_KEYS = set(METADATA_COPY_KEYS) | {
    "schema_version", "kind", "manifest_path", "manifest_sha256", "manifest_bytes",
}


class ObserverError(ValueError):
    """The requested local observer could not be prepared or verified safely."""


def _path(value, *, absolute=False):
    try:
        text = os.fspath(value)
    except TypeError:
        raise ObserverError("path must be text") from None
    if (not isinstance(text, str) or not text or len(text) > 4096
            or SAFE_PATH.fullmatch(text) is None
            or any(part in {".", ".."} for part in text.split("/"))):
        raise ObserverError("path is unsafe for the observer make fragment; spaces are unsupported")
    path = Path(text)
    if absolute:
        if not path.is_absolute():
            raise ObserverError("an absolute path is required")
    else:
        path = Path(os.path.abspath(path))
    return path


def _directory(path):
    """Open all directory components without following symlinks."""
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


def _root(value):
    path = _path(value)
    try:
        descriptor = _directory(path)
        os.close(descriptor)
    except OSError:
        raise ObserverError("root is not a nonsymlink directory") from None
    return path


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _archive(descriptor, size):
    """Require a bounded ordinary ar, never a thin archive or linker script."""
    if os.pread(descriptor, 8, 0) != b"!<arch>\n":
        raise ObserverError("libfesvr.a must be an ordinary static archive (thin/shared files rejected)")
    offset = 8
    members = 0
    objects = 0
    while offset < size:
        members += 1
        if members > MAX_ARCHIVE_MEMBERS:
            raise ObserverError("static archive has too many members")
        header = os.pread(descriptor, 60, offset)
        if len(header) != 60 or header[58:] != b"`\n":
            raise ObserverError("static archive member header is malformed")
        raw_size = header[48:58].strip()
        if not raw_size or not raw_size.isdigit():
            raise ObserverError("static archive member size is malformed")
        length = int(raw_size)
        offset += 60
        if offset + length > size:
            raise ObserverError("static archive member is truncated")
        name = header[:16].strip()
        if name not in {b"/", b"//", b"/SYM64/"} and length:
            objects += 1
        offset += length
        if offset % 2:
            if os.pread(descriptor, 1, offset) != b"\n":
                raise ObserverError("static archive padding is malformed")
            offset += 1
    if offset != size or not objects:
        raise ObserverError("static archive has no object members")


def _capture(base, relative, scope, *, retain=False, archive=False, limit=MAX_INPUT_BYTES):
    path = base / relative
    descriptor = parent = None
    try:
        parent = _directory(path.parent)
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        descriptor = os.open(path.name, flags, dir_fd=parent)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise ObserverError("input is not a nonempty bounded regular file")
        if archive:
            _archive(descriptor, before.st_size)
        digest = hashlib.sha256()
        chunks = []
        length = 0
        while True:
            data = os.read(descriptor, min(65536, limit - length + 1))
            if not data:
                break
            length += len(data)
            if length > limit:
                raise ObserverError("input grew beyond its size limit")
            digest.update(data)
            if retain:
                chunks.append(data)
        after = os.fstat(descriptor)
        if length != before.st_size or _identity(before) != _identity(after):
            raise ObserverError("input changed while being hashed")
        other_parent = _directory(path.parent)
        try:
            final = os.stat(path.name, dir_fd=other_parent, follow_symlinks=False)
        finally:
            os.close(other_parent)
        if _identity(final) != _identity(after):
            raise ObserverError("input path changed while being hashed")
        record = {"scope": scope, "path": relative, "size_bytes": length,
                  "sha256": digest.hexdigest()}
        return record, b"".join(chunks) if retain else None
    except OSError:
        raise ObserverError("input is unavailable or has a symlink component: " + relative) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent is not None:
            os.close(parent)


def render_overlay(source):
    """Return the complete translation unit after exactly three pinned edits."""
    if not isinstance(source, bytes) or hashlib.sha256(source).hexdigest() != PINNED_HTIF_SHA256:
        raise ObserverError("htif.cc does not match the pinned original SHA256")
    edits = (
        (b'#include "../riscv/common.h"\n', b'#include "common.h"\n'),
        (b"#include <getopt.h>\n", b'#include <getopt.h>\n#include "nova_htif_exit.h"\n'),
        (b"  stopped = true;\n}\n\nvoid htif_t::clear_chunk",
         b"  stopped = true;\n"
         b"  nova_htif_observe_stop(this, exitcode.has_value(), exitcode.value_or(0), signal_exit);\n"
         b"}\n\nvoid htif_t::clear_chunk"),
    )
    result = source
    for old, new in edits:
        if result.count(old) != 1:
            raise ObserverError("pinned htif.cc edit anchor is not unique")
        result = result.replace(old, new, 1)
    if hashlib.sha256(result).hexdigest() != GENERATED_HTIF_SHA256:
        raise ObserverError("generated htif.cc does not match the frozen adapter transform")
    return result


def _prefix(environ):
    env = os.environ if environ is None else environ
    value = env.get("RISCV")
    if not value:
        raise ObserverError("RISCV must name the prepared absolute installation prefix")
    return _root(_path(value, absolute=True))


def _output(root, output):
    path = _path(output)
    boundary = root / DEFAULT_OUTPUT_REL
    if path != boundary and not path.is_relative_to(boundary):
        raise ObserverError("output must be within the repository nova-out/htif-observer directory")
    return path


def _check_include_resolution(root, prefix, output=None):
    # Verify the quoted includes in the generated translation unit resolve to
    # the recorded source/config/native files, not an earlier shadowing file.
    expected = {
        "config.h": prefix / "include/fesvr/config.h",
        "htif.h": root / SPIKE_REL / "fesvr/htif.h",
        "rfb.h": root / SPIKE_REL / "fesvr/rfb.h",
        "elfloader.h": root / SPIKE_REL / "fesvr/elfloader.h",
        "platform.h": root / SPIKE_REL / "riscv/platform.h",
        "byteorder.h": root / SPIKE_REL / "fesvr/byteorder.h",
        "trap.h": root / SPIKE_REL / "riscv/trap.h",
        "common.h": root / SPIKE_REL / "riscv/common.h",
        "nova_htif_exit.h": root / HEADER_REL,
    }
    directories = [output] if output is not None else []
    directories += [(root if scope == "repository" else prefix) / path
                    for scope, path in INCLUDE_DIRECTORIES]
    for name, required in expected.items():
        for directory in directories:
            candidate = directory / name
            if os.path.lexists(candidate):
                if candidate != required:
                    raise ObserverError("unexpected include shadows the recorded input: " + name)
                break
        else:
            raise ObserverError("required quoted include cannot be resolved: " + name)


def _collect(root, prefix):
    records = {}
    specifications = {
        "source": (root, SPIKE_REL + "/fesvr/htif.cc", "repository", PINNED_HTIF_SHA256),
        "native": (root, NATIVE_REL, "repository", None),
        "header": (root, HEADER_REL, "repository", None),
        "archive": (prefix, "lib/libfesvr.a", "riscv", None),
        "installed_header": (prefix, "include/fesvr/htif.h", "riscv", SOURCE_HEADERS["fesvr/htif.h"]),
        "installed_config": (prefix, "include/fesvr/config.h", "riscv", None),
    }
    for name, (base, relative, scope, expected) in specifications.items():
        record, _ = _capture(base, relative, scope, archive=name == "archive",
                             limit=MAX_ARCHIVE_BYTES if name == "archive" else MAX_INPUT_BYTES)
        if expected is not None and record["sha256"] != expected:
            raise ObserverError("input SHA256 differs from the pinned source: " + relative)
        records[name] = record
    records["source_headers"] = {}
    for relative, expected in sorted(SOURCE_HEADERS.items()):
        record, _ = _capture(root, SPIKE_REL + "/" + relative, "repository")
        if record["sha256"] != expected:
            raise ObserverError("source header SHA256 differs from the pinned source: " + relative)
        records["source_headers"][relative] = record
    records["inputs"] = {}
    for name, relative in sorted(INPUT_PATHS.items()):
        record, _ = _capture(root, relative, "repository")
        if name == "upstream_sim_flags" and record["sha256"] != SIM_FLAGS_SHA256:
            raise ObserverError("upstream simulator link expression has changed; adapter needs review")
        records["inputs"][name] = record
    _check_include_resolution(root, prefix)
    return records


def inspect_observer(root, *, environ=None):
    """Read-only readiness check; ready is neither a build nor a hardware pass."""
    result = {"ready": False, "blockers": [], "source_pin": PINNED_SPIKE_COMMIT,
              "hardware_qualified": False, "g1_gate_passed": False}
    try:
        repository = _root(root)
        prefix = _prefix(environ)
        result.update(_collect(repository, prefix))
        result["ready"] = True
    except (ObserverError, TypeError, ValueError) as error:
        result["blockers"].append(str(error))
    return result


def _create_output(root, output):
    descriptor = _directory(root)
    try:
        components = output.relative_to(root).parts
        for number, component in enumerate(components):
            try:
                os.mkdir(component, 0o700, dir_fd=descriptor)
            except FileExistsError:
                if number == len(components) - 1:
                    raise ObserverError("observer output already exists; a fresh directory is required") from None
            following = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        result = descriptor
        descriptor = None
        return result
    except OSError:
        raise ObserverError("output cannot be created through nonsymlink directories") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _write_exclusive(directory, name, data):
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=directory)
    try:
        remaining = memoryview(data)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise ObserverError("observer output write made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def prepare_observer(root, output, *, environ=None):
    """Create one exclusive overlay directory and its deterministic manifest."""
    repository = _root(root)
    prefix = _prefix(environ)
    destination = _output(repository, output)
    records = _collect(repository, prefix)
    source_record, source = _capture(repository, SPIKE_REL + "/fesvr/htif.cc", "repository", retain=True)
    if source_record != records["source"]:
        raise ObserverError("source changed during observer preparation")
    generated = render_overlay(source)
    relative_output = destination.relative_to(repository).as_posix()
    manifest = {
        "schema_version": 1, "kind": "nova-htif-observer-build",
        "source_pin": PINNED_SPIKE_COMMIT, "output_directory": relative_output,
        **records,
        "generated": {"scope": "repository", "path": relative_output + "/htif.cc",
                      "sha256": hashlib.sha256(generated).hexdigest(), "size_bytes": len(generated)},
        "include_directories": [{"scope": scope, "path": path} for scope, path in INCLUDE_DIRECTORIES],
        "link_order": "overlay-object-before-static-fesvr",
        "hardware_qualified": False, "g1_gate_passed": False,
    }
    payload = (json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ObserverError("observer manifest exceeds its size bound")
    directory = _create_output(repository, destination)
    try:
        _write_exclusive(directory, "htif.cc", generated)
        _write_exclusive(directory, "manifest.json", payload)
        os.fsync(directory)
    except OSError:
        raise ObserverError("observer output could not be written; incomplete directory retained") from None
    finally:
        os.close(directory)
    # This also detects changed inputs and an output-directory swap before the
    # caller can use the result. Failed/partial products are never overwritten.
    return read_manifest(destination / "manifest.json", root=repository, environ=environ)


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ObserverError("duplicate observer manifest key")
        result[key] = value
    return result


def _bad_constant(_value):
    raise ObserverError("nonfinite observer manifest value")


def _manifest_root(path, root):
    if root is not None:
        return _root(root)
    positions = [number for number in range(len(path.parts) - 1)
                 if path.parts[number:number + 2] == ("nova-out", "htif-observer")]
    if len(positions) != 1:
        raise ObserverError("manifest root is ambiguous; supply root explicitly")
    return _root(Path(*path.parts[:positions[0]]))


def _record_shape(record, scope, path, expected=None, *, limit=MAX_INPUT_BYTES):
    if (type(record) is not dict or set(record) != IDENTITY_KEYS
            or record.get("scope") != scope or record.get("path") != path
            or not isinstance(record.get("sha256"), str)
            or SHA256.fullmatch(record["sha256"]) is None
            or type(record.get("size_bytes")) is not int
            or not 0 < record["size_bytes"] <= limit
            or (expected is not None and record["sha256"] != expected)):
        raise ObserverError("invalid observer input identity: " + path)


def _manifest_shape(manifest, output_relative):
    if (type(manifest) is not dict or set(manifest) != MANIFEST_KEYS
            or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1
            or manifest.get("kind") != "nova-htif-observer-build"
            or manifest.get("source_pin") != PINNED_SPIKE_COMMIT
            or manifest.get("output_directory") != output_relative
            or manifest.get("hardware_qualified") is not False
            or manifest.get("g1_gate_passed") is not False
            or manifest.get("link_order") != "overlay-object-before-static-fesvr"
            or manifest.get("include_directories") != [
                {"scope": scope, "path": path} for scope, path in INCLUDE_DIRECTORIES]):
        raise ObserverError("observer manifest does not match the frozen build contract")
    for key, scope, relative_path, expected, limit in (
        ("source", "repository", SPIKE_REL + "/fesvr/htif.cc", PINNED_HTIF_SHA256, MAX_INPUT_BYTES),
        ("generated", "repository", output_relative + "/htif.cc", GENERATED_HTIF_SHA256, MAX_INPUT_BYTES),
        ("native", "repository", NATIVE_REL, None, MAX_INPUT_BYTES),
        ("header", "repository", HEADER_REL, None, MAX_INPUT_BYTES),
        ("archive", "riscv", "lib/libfesvr.a", None, MAX_ARCHIVE_BYTES),
        ("installed_header", "riscv", "include/fesvr/htif.h", SOURCE_HEADERS["fesvr/htif.h"], MAX_INPUT_BYTES),
        ("installed_config", "riscv", "include/fesvr/config.h", None, MAX_INPUT_BYTES),
    ):
        _record_shape(manifest[key], scope, relative_path, expected, limit=limit)
    if type(manifest["source_headers"]) is not dict or set(manifest["source_headers"]) != set(SOURCE_HEADERS):
        raise ObserverError("observer source-header inventory differs")
    for relative_path, expected in SOURCE_HEADERS.items():
        _record_shape(manifest["source_headers"][relative_path], "repository", SPIKE_REL + "/" + relative_path, expected)
    if type(manifest["inputs"]) is not dict or set(manifest["inputs"]) != set(INPUT_PATHS):
        raise ObserverError("observer build-input inventory differs")
    for name, relative_path in INPUT_PATHS.items():
        _record_shape(manifest["inputs"][name], "repository", relative_path,
                      SIM_FLAGS_SHA256 if name == "upstream_sim_flags" else None)


def read_manifest(path, *, root=None, verify_files=True, environ=None):
    """Read a bounded strict manifest; normally rehash all recorded inputs.

    verify_files=False validates the record's complete shape and pinned hashes
    only. It is for inspecting retained metadata, never build authorization.
    """
    if type(verify_files) is not bool:
        raise ObserverError("verify_files must be boolean")
    manifest_path = _path(path)
    repository = _manifest_root(manifest_path, root)
    destination = _output(repository, manifest_path.parent)
    if manifest_path.name != "manifest.json":
        raise ObserverError("observer manifest must be named manifest.json")
    relative = manifest_path.relative_to(repository).as_posix()
    _, data = _capture(repository, relative, "repository", retain=True, limit=MAX_MANIFEST_BYTES)
    try:
        manifest = json.loads(data.decode("utf-8"), object_pairs_hook=_json_object,
                              parse_constant=_bad_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise ObserverError("observer manifest is not bounded strict UTF-8 JSON") from None
    output_relative = destination.relative_to(repository).as_posix()
    _manifest_shape(manifest, output_relative)
    if verify_files:
        prefix = _prefix(environ)
        current = _collect(repository, prefix)
        for key, value in current.items():
            if manifest[key] != value:
                raise ObserverError("observer input changed since preparation: " + key)
        generated_record, _ = _capture(repository, output_relative + "/htif.cc", "repository")
        if generated_record != manifest["generated"]:
            raise ObserverError("generated observer changed since preparation")
        descriptor = _directory(destination)
        try:
            with os.scandir(descriptor) as entries:
                seen = set()
                for entry in entries:
                    seen.add(entry.name)
                    if len(seen) > 2:
                        break
            if seen != {"manifest.json", "htif.cc"}:
                raise ObserverError("observer output contains unexpected products")
        finally:
            os.close(descriptor)
        _check_include_resolution(repository, prefix, destination)
    return manifest


def validate_build_metadata(metadata):
    """Validate retained record metadata without reading any local files.

    This verifies shape, fixed paths, and pinned source/overlay/header hashes.
    It does not establish that a recorded build or execution actually occurred.
    """
    if (type(metadata) is not dict or set(metadata) != METADATA_KEYS
            or type(metadata.get("schema_version")) is not int or metadata["schema_version"] != 1
            or metadata.get("kind") != "nova-htif-observer"
            or not isinstance(metadata.get("manifest_sha256"), str)
            or SHA256.fullmatch(metadata["manifest_sha256"]) is None
            or type(metadata.get("manifest_bytes")) is not int
            or not 0 < metadata["manifest_bytes"] <= MAX_MANIFEST_BYTES):
        raise ObserverError("invalid observer build metadata")
    path = metadata["manifest_path"]
    if (not isinstance(path, str) or len(path) > 4096 or SAFE_PATH.fullmatch(path) is None
            or not path.startswith(DEFAULT_OUTPUT_REL + "/")
            or not path.endswith("/manifest.json")
            or any(part in {"", ".", ".."} for part in path.split("/"))):
        raise ObserverError("invalid observer manifest metadata path")
    _manifest_shape({
        "schema_version": 1, "kind": "nova-htif-observer-build",
        "output_directory": path.rsplit("/", 1)[0],
        "include_directories": [{"scope": scope, "path": relative}
                                for scope, relative in INCLUDE_DIRECTORIES],
        **{key: metadata[key] for key in METADATA_COPY_KEYS},
    }, path.rsplit("/", 1)[0])
    return metadata


def build_metadata(manifest_path, *, root=None, environ=None):
    """Return relocatable record metadata after revalidating the build inputs."""
    path = _path(manifest_path)
    repository = _manifest_root(path, root)
    _output(repository, path.parent)
    if path.name != "manifest.json":
        raise ObserverError("observer manifest must be named manifest.json")
    before, _ = _capture(repository, path.relative_to(repository).as_posix(), "repository", limit=MAX_MANIFEST_BYTES)
    manifest = read_manifest(path, root=repository, environ=environ)
    after, _ = _capture(repository, path.relative_to(repository).as_posix(), "repository", limit=MAX_MANIFEST_BYTES)
    if before != after:
        raise ObserverError("observer manifest changed during metadata capture")
    return validate_build_metadata({
        "schema_version": 1, "kind": "nova-htif-observer",
        "manifest_path": before["path"], "manifest_sha256": before["sha256"],
        "manifest_bytes": before["size_bytes"],
        **{key: manifest[key] for key in METADATA_COPY_KEYS},
    })


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--output")
    arguments = parser.parse_args(argv)
    try:
        root = _root(arguments.root)
        output = arguments.output or str(root / DEFAULT_OUTPUT_REL)
        if arguments.inspect:
            result = inspect_observer(root)
            status = 0 if result["ready"] else 2
        elif arguments.prepare:
            result = prepare_observer(root, output)
            status = 0
        else:
            result = build_metadata(_output(root, output) / "manifest.json", root=root)
            status = 0
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
        return status
    except (ObserverError, OSError, TypeError, ValueError) as error:
        print("HTIF observer blocked: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
