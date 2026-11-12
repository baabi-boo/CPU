#!/usr/bin/env python3
"""Read-only comparison of a pinned-format Conda lock and installed metadata.

This is deliberately not a general YAML reader, package installer, or binary
attestation tool. Only the linux-64, conda-only version-1 lock shape currently
imported by NOVA is supported. Unsupported syntax fails closed. A matched
inventory means that conda-meta *claims* agree with the supplied lock; callers
must separately verify that lock's upstream identity, installed file contents,
supplementary tools, and actual build/runtime behavior.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCK = ROOT / (
    "conda-reqs/conda-lock-reqs/"
    "conda-requirements-riscv-tools-linux-64-lean.conda-lock.yml"
)
MAX_LOCK_BYTES = 2 * 1024 * 1024
MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_TOTAL_METADATA_BYTES = 32 * 1024 * 1024
MAX_PACKAGES = 1024
MAX_DIRECTORY_ENTRIES = 4096
NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z")
VERSION = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.+-]{0,127}\Z")
BUILD = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.]{0,127}\Z")
URL = re.compile(
    r"https://conda\.anaconda\.org/(ucb-bar|conda-forge|litex-hub)/"
    r"(linux-64|noarch)/([A-Za-z0-9_.+-]+\.(?:conda|tar\.bz2))\Z"
)
HASHES = {"md5": re.compile(r"[0-9a-f]{32}\Z"),
          "sha256": re.compile(r"[0-9a-f]{64}\Z")}
LIMITATION = (
    "Metadata agreement does not verify package archive contents, installed "
    "binaries, the supplied lock's upstream authenticity, or runtime compatibility."
)


class InventoryError(ValueError):
    """A bounded input cannot be inspected in the supported form."""


def _safe_path(value):
    """Reject traversal and every existing symlink component before reading."""
    try:
        path = Path(value)
        if ".." in path.parts:
            raise InventoryError("input path contains traversal")
        path = path.absolute()
        for ancestor in [*reversed(path.parents), path]:
            if stat.S_ISLNK(ancestor.lstat().st_mode):
                raise InventoryError("symlink input paths are not supported")
        return path
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        if isinstance(exc, InventoryError):
            raise
        raise InventoryError("input path is unavailable or invalid") from None


def _read_regular(value, limit):
    """Bound input size and avoid following a final-component replacement."""
    path = _safe_path(value)
    descriptor = None
    try:
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise InventoryError("input is not a bounded regular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
        identity = lambda item: (item.st_dev, item.st_ino, item.st_size,
                                 item.st_mtime_ns, item.st_ctime_ns)
        if len(raw) > limit or identity(before) != identity(after):
            raise InventoryError("input exceeded its limit or changed during inspection")
        return raw
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, InventoryError):
            raise
        raise InventoryError("input could not be read safely") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _scalar(value, pattern, allow_empty=False):
    # The pinned serializer uses plain or single-quoted single-line scalars.
    if value.startswith("'") and value.endswith("'") and len(value) >= 2:
        value = value[1:-1]
    if (not isinstance(value, str) or (not value and not allow_empty)
            or not pattern.fullmatch(value)):
        raise InventoryError("unsupported lock scalar")
    return value


def _lock_header(lines):
    expected = [
        "version: 1", "metadata:", "  content_hash:",
        None,
        "  channels:", "  - url: ucb-bar", "    used_env_vars: []",
        "  - url: conda-forge", "    used_env_vars: []",
        "  - url: litex-hub", "    used_env_vars: []",
        "  platforms:", "  - linux-64", "  sources:",
        "  - ../chipyard-base.yaml", "  - ../docs.yaml",
        "  - ../riscv-tools.yaml", "package:",
    ]
    if len(lines) < len(expected):
        raise InventoryError("incomplete lock header")
    for index, wanted in enumerate(expected):
        if wanted is None:
            if not re.fullmatch(r"    linux-64: [0-9a-f]{64}", lines[index]):
                raise InventoryError("unsupported lock content hash")
        elif lines[index] != wanted:
            raise InventoryError("unsupported lock metadata or format")
    return len(expected)


def _parse_lock(raw):
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise InventoryError("lock is not UTF-8 text") from None
    if not text.endswith("\n") or "\x00" in text or "\t" in text or "\r" in text:
        raise InventoryError("unsupported or truncated lock text")
    lines = []
    for line in text.split("\n"):
        if len(line) > 4096:
            raise InventoryError("lock line exceeds its limit")
        if line and not line.startswith("#"):
            lines.append(line)
    index = _lock_header(lines)
    packages = {}

    def take(prefix):
        nonlocal index
        if index >= len(lines) or not lines[index].startswith(prefix):
            raise InventoryError("missing, duplicate, or unsupported lock field")
        value = lines[index][len(prefix):]
        index += 1
        return value

    while index < len(lines):
        if len(packages) >= MAX_PACKAGES:
            raise InventoryError("lock package count exceeds its limit")
        name = _scalar(take("- name: "), NAME)
        if name in packages:
            raise InventoryError("duplicate lock package name")
        version = _scalar(take("  version: "), VERSION)
        if take("  manager: ") != "conda" or take("  platform: ") != "linux-64":
            raise InventoryError("unsupported package manager or platform")
        dependencies = take("  dependencies:")
        if dependencies == "":
            seen_dependencies = set()
            while index < len(lines) and lines[index].startswith("    "):
                row = lines[index]
                index += 1
                match = re.fullmatch(r"    ([A-Za-z0-9_][A-Za-z0-9_.-]*): (.*)", row)
                if not match or match[1] in seen_dependencies:
                    raise InventoryError("unsupported or duplicate lock dependency")
                seen_dependencies.add(match[1])
                _scalar(match[2], re.compile(r"[A-Za-z0-9_.*<>=!,| -]{0,512}\Z"),
                        allow_empty=True)
            if not seen_dependencies:
                raise InventoryError("empty lock dependency map must use braces")
        elif dependencies != " {}":
            raise InventoryError("unsupported lock dependency map")
        url = take("  url: ")
        match = URL.fullmatch(url)
        if not match:
            raise InventoryError("unsupported lock package URL")
        filename = match[3]
        archive_stem = filename[:-6] if filename.endswith(".conda") else filename[:-8]
        expected_prefix = name + "-" + version + "-"
        if not archive_stem.startswith(expected_prefix):
            raise InventoryError("lock URL does not identify the declared package")
        build = _scalar(archive_stem[len(expected_prefix):], BUILD)
        if take("  hash:"):
            raise InventoryError("unsupported lock hash map")
        hashes = {key: _scalar(take("    " + key + ": "), regex)
                  for key, regex in HASHES.items()}
        if take("  category: ") != "main" or take("  optional: ") != "false":
            raise InventoryError("unsupported package category or optionality")
        packages[name] = {
            "name": name, "version": version, "build": build, "url": url,
            "subdir": match[2], **hashes,
        }
    if not packages:
        raise InventoryError("lock contains no packages")
    return packages


def read_lock_packages(path):
    """Return packages keyed by name, or raise a privacy-safe InventoryError.

    The caller supplies the trust boundary for the lock. This function parses
    its supported format; it does not validate it against NOVA's upstream pin.
    """
    return _parse_lock(_read_regular(path, MAX_LOCK_BYTES))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InventoryError("duplicate installed metadata key")
        result[key] = value
    return result


def _read_installed(prefix):
    directory = _safe_path(prefix) / "conda-meta"
    directory = _safe_path(directory)
    if not directory.is_dir():
        raise InventoryError("installed conda-meta directory is missing")
    paths = []
    try:
        with os.scandir(directory) as entries:
            for number, entry in enumerate(entries, 1):
                if number > MAX_DIRECTORY_ENTRIES:
                    raise InventoryError("installed metadata directory exceeds its limit")
                if entry.name.endswith(".json"):
                    paths.append(directory / entry.name)
    except OSError:
        raise InventoryError("installed metadata directory is unreadable") from None
    if len(paths) > MAX_PACKAGES:
        raise InventoryError("installed package count exceeds its limit")
    installed = {}
    total_bytes = 0
    for path in sorted(paths):
        raw = _read_regular(path, MAX_RECORD_BYTES)
        total_bytes += len(raw)
        if total_bytes > MAX_TOTAL_METADATA_BYTES:
            raise InventoryError("installed metadata exceeds its aggregate size limit")
        try:
            record = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                                parse_constant=lambda _: (_ for _ in ()).throw(
                                    InventoryError("nonfinite installed metadata value")))
        except (ValueError, UnicodeError, RecursionError):
            raise InventoryError("installed metadata is invalid or unsupported JSON") from None
        if not isinstance(record, dict):
            raise InventoryError("installed metadata record is not an object")
        fields = {}
        for key, pattern in (("name", NAME), ("version", VERSION), ("build", BUILD),
                             ("url", URL), *HASHES.items()):
            value = record.get(key)
            if not isinstance(value, str) or not pattern.fullmatch(value):
                raise InventoryError("installed metadata has missing or invalid identity fields")
            fields[key] = value
        name = fields["name"]
        if name in installed:
            raise InventoryError("duplicate installed package name")
        if path.name != "{name}-{version}-{build}.json".format(**fields):
            raise InventoryError("installed metadata filename disagrees with its identity")
        url_match = URL.fullmatch(fields["url"])
        if "subdir" in record and record["subdir"] != url_match[2]:
            raise InventoryError("installed metadata subdir disagrees with its URL")
        installed[name] = fields
    return installed


def inspect_inventory(lock_path, prefix):
    """Compare installed package metadata with one supplied immutable lock."""
    result = {
        "schema_version": 1, "status": "blocked", "blockers": [],
        "package_count": 0, "installed_package_count": 0,
        "matching_package_count": 0, "lock_sha256": None,
        "metadata_only": True, "installed_binary_contents_verified": False,
        "lock_origin_verified": False, "hardware_qualified": False,
        "g1_gate_passed": False, "limitation": LIMITATION,
        "missing": [], "unexpected": [], "mismatched": [],
    }
    try:
        lock_raw = _read_regular(lock_path, MAX_LOCK_BYTES)
        expected = _parse_lock(lock_raw)
        result["lock_sha256"] = hashlib.sha256(lock_raw).hexdigest()
        result["package_count"] = len(expected)
        actual = _read_installed(prefix)
        result["installed_package_count"] = len(actual)
    except InventoryError as exc:
        result["blockers"].append(str(exc))
        return result
    result["missing"] = sorted(set(expected) - set(actual))
    result["unexpected"] = sorted(set(actual) - set(expected))
    if result["missing"]:
        result["blockers"].append("locked packages are missing from installed metadata")
    if result["unexpected"]:
        result["blockers"].append("installed metadata contains packages outside the lock")
    for name in sorted(set(expected) & set(actual)):
        changed = [key for key in ("version", "build", "url", "md5", "sha256")
                   if expected[name][key] != actual[name][key]]
        if changed:
            result["mismatched"].append({"name": name, "fields": changed})
        else:
            result["matching_package_count"] += 1
    if result["mismatched"]:
        result["blockers"].append("installed package identities or checksums differ from the lock")
    if not result["blockers"]:
        result["status"] = "matched"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--prefix", type=Path,
                        help="inspect this existing prefix; never create or activate it")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.prefix is not None:
        result = inspect_inventory(args.lock, args.prefix)
    else:
        result = {"schema_version": 1, "status": "planned", "blockers": [],
                  "metadata_only": True, "hardware_qualified": False,
                  "g1_gate_passed": False, "lock_origin_verified": False,
                  "package_count": 0, "packages": [], "limitation": LIMITATION}
        try:
            packages = read_lock_packages(args.lock)
            result["package_count"] = len(packages)
            result["packages"] = [packages[name] for name in sorted(packages)]
        except InventoryError as exc:
            result["status"] = "blocked"
            result["blockers"].append(str(exc))
    if args.json:
        print(json.dumps(result, sort_keys=True, indent=2))
    else:
        print(f"Conda metadata {result['status']}: {result['package_count']} locked packages.")
        for blocker in result["blockers"]:
            print("Blocked: " + blocker)
        print(LIMITATION)
        print("Read-only inspection; no packages installed or environments activated.")
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
