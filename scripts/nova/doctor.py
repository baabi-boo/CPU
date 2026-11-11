#!/usr/bin/env python3
"""Offline, read-only prerequisite diagnostics; never hardware qualification."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


DEFAULT_ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 5
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_SUBMODULES = frozenset({
    "generators/boom", "generators/rocket-chip", "generators/hardfloat",
    "generators/diplomacy", "generators/testchipip",
    "generators/rocket-chip-inclusive-cache", "tools/cde",
})
TOOLS = {
    "java": ["-version"], "verilator": ["--version"],
    "firtool": ["--version"], "make": ["--version"],
    "cmake": ["--version"], "riscv64-unknown-elf-gcc": ["--version"],
}


def run_command(argv, cwd, timeout=TIMEOUT_SECONDS):
    """Run only explicit argv, with no shell or network operations."""
    try:
        env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
        result = subprocess.run(
            argv, cwd=cwd, env=env, capture_output=True, text=True,
            errors="replace", timeout=timeout, check=False,
        )
        return {"ok": result.returncode == 0, "returncode": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr,
                "error": None if result.returncode == 0 else "nonzero exit"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except OSError:
        return {"ok": False, "error": "command unavailable or invalid directory"}


def git(root, *args):
    return run_command(["git", "--no-optional-locks", "-C", str(root), *args], root)


def parse_gitlinks(output):
    """Read index gitlinks without initializing or contacting submodule remotes."""
    if output and not output.endswith("\0"):
        raise ValueError("truncated index output")
    links = []
    for entry in output.split("\0"):
        if not entry:
            continue
        header, separator, path = entry.partition("\t")
        fields = header.split()
        if not separator or len(fields) != 3 or not path:
            raise ValueError("malformed index record")
        if fields[0] == "160000":
            if not COMMIT_SHA.fullmatch(fields[1]) or fields[2] not in {"0", "1", "2", "3"}:
                raise ValueError("malformed gitlink metadata")
            links.append({"path": path, "pin": fields[1], "stage": fields[2]})
    return sorted(links, key=lambda item: item["path"])


def is_repository_top(root, result):
    value = result.get("stdout", "").strip()
    try:
        return bool(result["ok"] and value and Path(value).is_absolute()
                    and Path(value).resolve() == root)
    except (OSError, ValueError, RuntimeError):
        return False


def worktree_state(output):
    """Read NUL-delimited porcelain without reporting potentially private names."""
    if not output:
        return False, False
    if not output.endswith("\0"):
        raise ValueError("truncated worktree status")
    records = iter(output[:-1].split("\0"))
    conflicted = False
    for record in records:
        if len(record) < 4 or record[2] != " " or any(c not in " MTADRCU?!" for c in record[:2]):
            raise ValueError("malformed worktree status")
        conflicted |= record[:2] in {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}
        if "R" in record[:2] or "C" in record[:2]:
            if not next(records, ""):
                raise ValueError("truncated rename status")
    return True, conflicted


def submodule_status(root, link):
    path = link["path"]
    result = {"path": path, "pin": link["pin"],
              "required": path in REQUIRED_SUBMODULES, "state": "uninitialized",
              "dirty": None}
    try:
        target = (root / path).resolve()
        if not target.is_relative_to(root):
            result["state"] = "invalid_path"
        elif link["stage"] != "0":
            result["state"] = "conflict"
        elif (target / ".git").exists():
            top = git(target, "rev-parse", "--show-toplevel")
            if not is_repository_top(target, top):
                result["state"] = "unreadable"
            else:
                head = git(target, "rev-parse", "HEAD")
                if not head["ok"] or not COMMIT_SHA.fullmatch(head.get("stdout", "").strip()):
                    result["state"] = "unreadable"
                else:
                    result["head"] = head["stdout"].strip()
                    status = git(target, "status", "--porcelain=v1", "-z",
                                 "--untracked-files=normal", "--ignore-submodules=none")
                    if not status["ok"]:
                        result["state"] = "unreadable"
                    else:
                        result["dirty"], conflicted = worktree_state(status.get("stdout", ""))
                        result["state"] = (
                            "conflict" if conflicted else
                            "mismatch" if result["head"] != link["pin"] else
                            "dirty" if result["dirty"] else "at_pin")
    except (OSError, ValueError, RuntimeError):
        result["state"] = "unreadable"
    return result


def tool_status(name, args, root):
    executable = shutil.which(name)
    if not executable:
        return {"name": name, "available": False, "version": None, "error": "not on PATH"}
    result = run_command([executable, *args], root)
    lines = (result.get("stdout", "") + "\n" + result.get("stderr", "")).splitlines()
    # Java may echo JAVA_TOOL_OPTIONS. Do not expose that environment content.
    lines = [line.strip() for line in lines if line.strip()
             and not line.lstrip().startswith(("Picked up ", "NOTE: Picked up "))]
    version = lines[0][:240] if result["ok"] and lines else None
    return {"name": name, "available": bool(result["ok"]), "version": version,
            "error": result.get("error")}


def collect(root, environ=None):
    environ = os.environ if environ is None else environ
    report = {
        "schema_version": 1, "scope": "prerequisite diagnostics only",
        "hardware_qualified": False,
        "repository": {"valid": False, "revision": None, "dirty": None},
        "submodules": [],
        "files": {}, "tools": [], "blockers": [],
        "riscv": {"set": bool(environ.get("RISCV", "")), "directory_exists": None},
        "prerequisites_present": False,
        "limitations": [
            "Known prerequisite checks are not a complete toolchain compatibility test.",
            "No environment file is sourced, dependencies installed, or hardware built.",
            "Optional dependencies and nested submodules may be needed by a chosen profile.",
            "Submodule status includes tracked/untracked changes, not ignored files or complete nested-dependency qualification.",
        ],
    }
    try:
        root = Path(root).resolve()
    except (OSError, ValueError, RuntimeError):
        # Do not expose the supplied path or exception text, or run probes from
        # an unresolvable root. Unknown values must not be reported as checked.
        report["blockers"].append("root could not be resolved safely")
        report["limitations"].append(
            "Root resolution failed; remaining prerequisite checks were not run.")
        return report
    top = git(root, "rev-parse", "--show-toplevel")
    valid_repo = is_repository_top(root, top)
    if not valid_repo:
        report["repository"] = {"valid": False, "revision": None, "dirty": None}
        report["blockers"].append("root is not a readable repository root")
    else:
        revision = git(root, "rev-parse", "HEAD")
        valid_revision = revision["ok"] and COMMIT_SHA.fullmatch(revision.get("stdout", "").strip())
        status = git(root, "status", "--porcelain=v1", "--untracked-files=normal")
        report["repository"] = {
            "valid": True, "revision": revision["stdout"].strip() if valid_revision else None,
            "dirty": bool(status.get("stdout")) if status["ok"] else None,
        }
        if not valid_revision or not status["ok"]:
            report["blockers"].append("repository revision or dirty state could not be read")
        index = git(root, "ls-files", "--stage", "-z")
        if not index["ok"]:
            report["blockers"].append("submodule index could not be read")
        else:
            try:
                links = parse_gitlinks(index.get("stdout", ""))
            except ValueError:
                report["blockers"].append("submodule index output is malformed")
                links = []
            report["submodules"] = [submodule_status(root, link) for link in links]
            present = {entry["path"] for entry in report["submodules"]}
            for path in sorted(REQUIRED_SUBMODULES - present):
                report["blockers"].append("required submodule absent from index: " + path)
            for entry in report["submodules"]:
                if entry["required"] and entry["state"] != "at_pin":
                    report["blockers"].append(entry["path"] + ": " + entry["state"])
    for relative in ("env.sh", "scripts/sbt-launch.jar"):
        exists = (root / relative).is_file()
        report["files"][relative] = exists
        if not exists:
            report["blockers"].append("missing " + relative)
    riscv = environ.get("RISCV", "")
    riscv_exists = bool(riscv) and Path(riscv).is_dir()
    report["riscv"] = {"set": bool(riscv), "directory_exists": riscv_exists}
    if not riscv_exists:
        report["blockers"].append("RISCV is unset or does not name an existing directory")
    report["tools"] = [tool_status(name, args, root) for name, args in TOOLS.items()]
    for tool in report["tools"]:
        if not tool["available"]:
            report["blockers"].append(tool["name"] + ": " + str(tool["error"]))
    report["prerequisites_present"] = not report["blockers"]
    return report


def render_text(report):
    repo = report["repository"]
    lines = ["NOVA-M1 prerequisite diagnostics (not hardware verification)",
             "Revision: " + str(repo.get("revision")),
             "Working tree dirty: " + str(repo.get("dirty"))]
    for name, exists in report["files"].items():
        lines.append(name + ": " + ("present" if exists else "missing"))
    riscv_exists = report["riscv"]["directory_exists"]
    lines.append("RISCV directory: " + (
        "not checked" if riscv_exists is None else "present" if riscv_exists else "missing"))
    for tool in report["tools"]:
        lines.append(tool["name"] + ": " + (tool["version"] or str(tool["error"])))
    lines.append("Submodules (required = known baseline/mixed-core prerequisite):")
    for entry in report["submodules"]:
        kind = "required" if entry["required"] else "optional"
        lines.append("  " + entry["path"] + ": " + entry["state"] + " (" + kind + ")")
    lines.append("Known prerequisite blockers: " + str(len(report["blockers"])))
    lines.extend("  - " + value for value in report["blockers"])
    lines.extend("Note: " + value for value in report["limitations"])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--json", action="store_true", help="emit structured diagnostics")
    parser.add_argument("--strict", action="store_true", help="fail if known prerequisites are missing")
    args = parser.parse_args(argv)
    report = collect(args.root)
    print(json.dumps(report, indent=2) if args.json else render_text(report))
    return 1 if args.strict and report["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
