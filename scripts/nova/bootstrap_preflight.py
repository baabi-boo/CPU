#!/usr/bin/env python3
"""Read-only NOVA-001 setup preflight; never installs or qualifies hardware.

The inherited Chipyard setup can rewrite tracked Conda input/lock files when it
selects a host-dependent sysroot. Detect that condition *before* setup, while
keeping paths, credentials, and the caller's environment out of reports.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess


DEFAULT_ROOT = Path(__file__).resolve().parents[2]
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
SYSROOT = re.compile(r"(?m)^\s*-\s*sysroot_linux-64\s*=\s*([0-9.]+)\s*$")
CONDA_INPUTS = frozenset({
    "conda-reqs/chipyard-base.yaml",
    "conda-reqs/chipyard-extended.yaml",
    "conda-reqs/circt.json",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-64-lean.conda-lock.yml",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-64.conda-lock.yml",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-aarch64-lean.conda-lock.yml",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-aarch64.conda-lock.yml",
    "conda-reqs/docs.yaml",
    "conda-reqs/riscv-tools.yaml",
})
# Keep this order synchronized with the upstream setup script's candidate list.
SETUP_SYSROOTS = ("2.39", "2.34", "2.28", "2.17", "2.12.2", "2.12")
SETUP_SYSROOT_LOOP = re.compile(r"(?m)^\s*for version in ([0-9.\s]+);\s*do\s*$")
TOOLS = ("conda", "verilator", "firtool", "cmake", "riscv64-unknown-elf-gcc", "java", "make", "git")
MAX_SETUP_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_PINNED_INPUT_BYTES = 50 * 1024 * 1024


def read_limited(path, limit):
    """Bound each input read even if its size changes after an initial stat."""
    with path.open("rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input exceeds preflight size budget")
    return data


def version_tuple(value):
    """Parse numeric dotted versions, rejecting suffixes and empty fields."""
    # Bound conversion of untrusted values before int() (Python also limits
    # decimal-digit conversions, which otherwise raise ValueError).
    if (not isinstance(value, str) or len(value) > 64 or
            not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", value)):
        return None
    parts = value.split(".")
    if len(parts) > 8 or any(len(part) > 12 for part in parts):
        return None
    try:
        return tuple(int(part) for part in parts)
    except ValueError:
        return None


def chosen_sysroot(host_glibc):
    host = version_tuple(host_glibc)
    if host is None:
        return None
    return next((candidate for candidate in SETUP_SYSROOTS
                 if version_tuple(candidate) <= host), None)


def git(root, *args):
    """Run a bounded local Git query without repository fsmonitor hooks.

    Git's fsmonitor command can otherwise execute arbitrary repository-defined
    programs during ``status``.  Disable hooks, lazy fetching, and prompting as
    defense in depth.  This is still intended for a trusted local checkout.
    """
    try:
        process = subprocess.run(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
             "-c", "core.hooksPath=/dev/null", "-c", "submodule.recurse=false",
             "-C", str(root), *args],
            cwd=root, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0",
                               GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0"),
            capture_output=True, text=True, errors="replace", timeout=5,
            stdin=subprocess.DEVNULL, check=False,
        )
        return process.stdout.strip() if process.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def resolved_input(root, relative):
    """Limit reads to fixed tracked inputs inside the selected repository."""
    if relative not in CONDA_INPUTS:
        raise ValueError("unrecognized pinned input")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("pinned input missing or outside repository")
    return path


def source_snapshot(root, report):
    top = git(root, "rev-parse", "--show-toplevel")
    try:
        valid_top = bool(top and Path(top).resolve() == root)
    except (OSError, RuntimeError, ValueError):
        valid_top = False
    if not valid_top:
        report["blockers"].append("root is not a readable repository top-level")
        return False
    revision = git(root, "rev-parse", "HEAD")
    dirty = git(root, "status", "--porcelain=v1", "--untracked-files=normal")
    if revision is None or not SHA1.fullmatch(revision) or dirty is None:
        report["blockers"].append("source revision or worktree state unavailable")
        return False
    report["repository"] = {"valid": True, "revision": revision, "dirty": bool(dirty)}
    if dirty:
        report["blockers"].append("repository has uncommitted changes; no clean G1 reproduction")
    return True


def check_setup_sysroot_contract(root, report):
    """Fail closed if the checked-in setup script changes its sysroot choices.

    The script must exist even in a fixture repository: otherwise a preflight
    cannot substantiate that its sysroot-selection prediction matches reality.
    """
    try:
        script = root / "scripts/build-setup.sh"
        resolved = script.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError("setup script outside checkout or not a file")
        body = read_limited(resolved, MAX_SETUP_BYTES).decode("utf-8")
        loops = SETUP_SYSROOT_LOOP.findall(body)
        parsed = tuple(loops[0].split()) if len(loops) == 1 else ()
        if parsed != SETUP_SYSROOTS:
            raise ValueError("sysroot selector no longer matches preflight assumptions")
        return True
    except (OSError, UnicodeError, ValueError, RuntimeError):
        report["blockers"].append("upstream setup sysroot selector cannot be verified")
        return False


def locked_inputs(root, report):
    try:
        lock_path = root / "nova/upstream-lock.json"
        if not lock_path.resolve().is_relative_to(root):
            raise ValueError("upstream manifest escapes repository")
        manifest = json.loads(read_limited(lock_path, MAX_MANIFEST_BYTES).decode("utf-8"))
        originals = manifest["preserved_blobs"]
        if not isinstance(originals, dict) or set(originals).intersection(CONDA_INPUTS) != CONDA_INPUTS:
            raise ValueError("upstream manifest omits required inputs")
    except (OSError, UnicodeError, TypeError, KeyError, ValueError, RuntimeError):
        report["blockers"].append("pinned-input manifest unavailable or invalid")
        return

    for relative in sorted(CONDA_INPUTS):
        try:
            expected = originals[relative]
            if not isinstance(expected, str) or not SHA1.fullmatch(expected):
                raise ValueError("invalid expected blob hash")
            pinned_file = resolved_input(root, relative)
            raw = read_limited(pinned_file, MAX_PINNED_INPUT_BYTES)
            actual_blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
            matching = actual_blob == expected
            report["lock_hashes"][relative] = {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "matches_imported_blob": matching,
            }
            if not matching:
                report["blockers"].append("pinned input has changed: " + relative)
        except (OSError, ValueError, RuntimeError):
            report["blockers"].append("pinned input cannot be verified: " + relative)


def resources(root):
    """Best-effort physical host capacity, not cgroup-effective budgets."""
    snapshot = {
        "logical_cpus": os.cpu_count(), "ram_bytes": None,
        "ram_bytes_basis": "host_physical_not_cgroup_limit", "disk_free_bytes": None,
    }
    try:
        snapshot["ram_bytes"] = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, AttributeError):
        pass
    try:
        snapshot["disk_free_bytes"] = shutil.disk_usage(root).free
    except (OSError, ValueError):
        pass
    return snapshot


def collect(root=DEFAULT_ROOT):
    """Return a diagnostic snapshot without mutation or network access."""
    report = {
        "schema_version": 1,
        "scope": "NOVA-001 preflight only; no installation, simulation, or signoff",
        "hardware_qualified": False,
        "repository": {"valid": False, "revision": None, "dirty": None},
        "host_glibc": None,
        "pinned_sysroot": None,
        "setup_selected_sysroot": None,
        "unsafe_upstream_setup": True,
        "lock_hashes": {},
        "tool_availability": {tool: bool(shutil.which(tool)) for tool in TOOLS},
        "resources": {
            "logical_cpus": None, "ram_bytes": None,
            "ram_bytes_basis": "host_physical_not_cgroup_limit", "disk_free_bytes": None,
        },
        "blockers": [], "warnings": [
            "Repository preflight is not a resource approval, hardware test, or milestone decision.",
            "Upstream setup can initialize optional dependencies; review it before using it.",
        ],
    }
    try:
        root = Path(root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("not a directory")
    except (OSError, ValueError, RuntimeError):
        report["blockers"].append("root could not be resolved safely")
        return report
    if not source_snapshot(root, report):
        return report
    report["resources"] = resources(root)
    locked_inputs(root, report)
    selector_verified = check_setup_sysroot_contract(root, report)
    try:
        base = read_limited(resolved_input(root, "conda-reqs/chipyard-base.yaml"),
                            MAX_PINNED_INPUT_BYTES).decode("utf-8")
        match = SYSROOT.search(base)
        if not match or version_tuple(match.group(1)) is None:
            raise ValueError("sysroot pin unavailable")
        report["pinned_sysroot"] = match.group(1)
    except (OSError, UnicodeError, ValueError, RuntimeError):
        report["blockers"].append("pinned sysroot cannot be identified")

    libc, version = platform.libc_ver()
    if selector_verified and libc == "glibc" and version_tuple(version) is not None:
        report["host_glibc"] = version
        report["setup_selected_sysroot"] = chosen_sysroot(version)
    else:
        report["warnings"].append("host glibc is not identifiable by the preflight")
    selected = report["setup_selected_sysroot"]
    pinned = report["pinned_sysroot"]
    report["unsafe_upstream_setup"] = not bool(selected and pinned and selected == pinned)
    if report["unsafe_upstream_setup"]:
        report["blockers"].append("upstream setup may rewrite pinned sysroot/Conda locks")
    for tool in TOOLS:
        if not report["tool_availability"][tool]:
            report["blockers"].append(tool + " is not on PATH")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                        help="repository root for read-only inspection")
    parser.add_argument("--json", action="store_true", help="emit machine-readable report")
    parser.add_argument("--strict", action="store_true",
                        help="exit nonzero when prerequisites are unsafe or unverified")
    args = parser.parse_args(argv)
    result = collect(args.root)
    if args.json:
        print(json.dumps(result, sort_keys=True, indent=2))
    else:
        print("NOVA-001 preflight (not hardware qualification)")
        print("Repository valid:", result["repository"]["valid"])
        print("Host glibc:", result["host_glibc"] or "unknown")
        print("Pinned sysroot:", result["pinned_sysroot"] or "unknown")
        print("Setup-selected sysroot:", result["setup_selected_sysroot"] or "unknown")
        print("Upstream setup may rewrite locks:", result["unsafe_upstream_setup"])
        verified = sum(item["matches_imported_blob"]
                       for item in result["lock_hashes"].values())
        print("Verified pinned inputs:", verified, "of", len(CONDA_INPUTS))
        print("Known blockers:", len(result["blockers"]))
        for blocker in result["blockers"]:
            print(" -", blocker)
        for warning in result["warnings"]:
            print("Note:", warning)
    return 1 if args.strict and (result["blockers"] or result["unsafe_upstream_setup"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
