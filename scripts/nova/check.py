#!/usr/bin/env python3
"""Offline NOVA repository checks; never hardware qualification or gate signoff."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

STATES = {"planned", "in_progress", "blocked", "passed", "failed"}
LEVELS = {"repository", "elaboration", "simulation", "fpga", "physical_design", "review"}
SHA = re.compile(r"^[0-9a-f]{40}$")
CONFIG_PATH = "generators/chipyard/src/main/scala/config/NovaM1Configs.scala"
ROOT_DOCS = ("README.md", "CONTRIBUTING.md", "AGENTS.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md")
PRESERVED = {
    "README.chipyard.md", "docs/nova/upstream/CONTRIBUTING.chipyard.md", "LICENSE", "LICENSE.SiFive",
    "conda-reqs/chipyard-base.yaml", "conda-reqs/chipyard-extended.yaml", "conda-reqs/circt.json",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-64-lean.conda-lock.yml",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-64.conda-lock.yml",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-aarch64-lean.conda-lock.yml",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-aarch64.conda-lock.yml",
    "conda-reqs/docs.yaml", "conda-reqs/riscv-tools.yaml",
}


def nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def member(value, choices):
    return isinstance(value, str) and value in choices


def repo_path(root, value):
    """Resolve a metadata path without allowing traversal or symlink escape."""
    if not nonblank(value) or "\\" in value or "\0" in value:
        raise ValueError("invalid repository-relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("path must be repository-relative without '..'")
    try:
        resolved = (root / path).resolve()
    except RuntimeError as exc:
        raise ValueError("path contains a symlink loop") from exc
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("path escapes repository")
    return resolved


def load_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if not key.strip():
                raise ValueError("blank JSON key")
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError(f"non-finite JSON constant: {value}")
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=reject_constant)
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("expected object with schema_version 1")
    return data


def rows_by_id(value, label, pattern, errors):
    result = {}
    if not isinstance(value, list) or not value:
        errors.append(f"{label}: expected nonempty list")
        return result
    for row in value:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not re.fullmatch(pattern, row["id"]):
            errors.append(f"{label}: invalid row/id")
            continue
        key = row["id"]
        if key in result:
            errors.append(f"{label}: duplicate id {key}")
        result[key] = row
    return result


def strings(value, label, errors, nonempty=False):
    if not isinstance(value, list) or any(not nonblank(x) for x in value):
        errors.append(f"{label}: expected string list")
        return []
    if len(value) != len(set(value)) or (nonempty and not value):
        errors.append(f"{label}: empty or duplicate entries")
    return value


def check_evidence(row, root, label, errors, required=False):
    evidence = strings(row.get("evidence", []), f"{label} evidence", errors)
    if required and not evidence:
        errors.append(f"{label}: passed/qualified status requires local evidence")
    for value in evidence:
        try:
            path = repo_path(root, value)
            if not path.is_file():
                raise ValueError("evidence file missing")
            # Reject accidental template references, including renamed copies.
            # This is a completeness guard, not semantic review of a test result.
            with path.open("rb") as source:
                prefix = source.read(8192)
            if required and not prefix.strip():
                raise ValueError("empty file is not executed evidence")
            header = prefix.decode("utf-8", errors="replace")
            template_name = re.search(r"(?:^|[._-])template(?:[._-]|$)", path.name, re.IGNORECASE)
            template_marker = re.search(
                r"(?im)^\s*(?:#{1,6}\s*)?(?:\*{1,2})?"
                r"(?:TEMPLATE(?:\s+ONLY\b|\s*[/—:-]\s*NOT[ _-]+EXECUTED\b)"
                r"|Evidence\s+record\s+template\b)",
                header,
            )
            if template_name or template_marker:
                raise ValueError("template is not executed evidence")
        except (OSError, ValueError) as exc:
            errors.append(f"{label}: {value}: {exc}")


def validate_project(data, root):
    errors = []
    if data.get("name") != "NOVA-M1" or not isinstance(data.get("baseline_commit"), str) or not SHA.fullmatch(data["baseline_commit"]):
        errors.append("project: invalid name or baseline commit")
    gates = rows_by_id(data.get("milestones"), "milestones", r"G[0-9]", errors)
    if set(gates) != {f"G{i}" for i in range(10)}:
        errors.append("project: expected gates G0 through G9")
    graph = {}
    for key, gate in gates.items():
        if not member(gate.get("status"), STATES) or not nonblank(gate.get("title")):
            errors.append(f"{key}: invalid status/title")
        graph[key] = strings(gate.get("depends_on"), f"{key} dependencies", errors)
        check_evidence(gate, root, key, errors, gate.get("status") == "passed")
        for dep in graph[key]:
            if dep not in gates:
                errors.append(f"{key}: unknown dependency {dep}")
            elif gate.get("status") == "passed" and gates[dep].get("status") != "passed":
                errors.append(f"{key}: passed before prerequisite {dep}")
    active, done = set(), set()
    def visit(key):
        if key in active:
            errors.append(f"milestone dependency cycle at {key}")
            return
        if key in done:
            return
        active.add(key)
        for dep in graph.get(key, []):
            if dep in graph:
                visit(dep)
        active.remove(key)
        done.add(key)
    for key in graph:
        visit(key)
    configs = data.get("configurations")
    if not isinstance(configs, list) or not configs:
        errors.append("project: configurations must be a nonempty list")
        configs = []
    names = set()
    for item in configs:
        if not isinstance(item, dict):
            errors.append("project: invalid configuration")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"Nova\w+Config", name) or name in names:
            errors.append("project: invalid or duplicate configuration name")
        else:
            names.add(name)
        if not isinstance(item.get("upstream"), str) or not re.fullmatch(r"\w+Config", item["upstream"]):
            errors.append(f"{name}: invalid upstream configuration")
        state = item.get("status")
        if not member(state, {"planned", "implemented_unverified", "elaborated", "simulated", "fpga_validated", "silicon_measured"}):
            errors.append(f"{name}: invalid configuration status")
        check_evidence(item, root, str(name), errors, not member(state, {"planned", "implemented_unverified"}))
    return errors


def validate_requirements(data, project, root):
    errors = []
    gate_rows = project.get("milestones", [])
    gates = {g["id"] for g in gate_rows if isinstance(g, dict) and isinstance(g.get("id"), str)} if isinstance(gate_rows, list) else set()
    passed_gates = {g["id"] for g in gate_rows if isinstance(g, dict) and isinstance(g.get("id"), str) and g.get("status") == "passed"} if isinstance(gate_rows, list) else set()
    tests = rows_by_id(data.get("tests"), "tests", r"T-[A-Z0-9]+(?:-[A-Z0-9]+)*", errors)
    reqs = rows_by_id(data.get("requirements"), "requirements", r"REQ-[A-Z0-9]+(?:-[A-Z0-9]+)*", errors)
    for key, test in tests.items():
        if not member(test.get("level"), LEVELS) or not nonblank(test.get("description")):
            errors.append(f"{key}: invalid test level/description")
        implementation = test.get("implementation")
        if not member(implementation, {"planned", "available"}):
            errors.append(f"{key}: invalid implementation state")
        elif implementation == "available" and not nonblank(test.get("command")):
            errors.append(f"{key}: available test requires command")
        elif implementation == "planned" and test.get("command") is not None:
            errors.append(f"{key}: planned test command must be null")
    for key, req in reqs.items():
        if not member(req.get("gate"), gates) or not member(req.get("priority"), {"must", "should"}) or not member(req.get("status"), STATES):
            errors.append(f"{key}: invalid gate/priority/status")
        if not nonblank(req.get("title")) or not nonblank(req.get("owner_role")):
            errors.append(f"{key}: missing title/owner role")
        try:
            if not repo_path(root, req.get("design_doc")).is_file():
                raise ValueError("design document missing")
        except (OSError, ValueError) as exc:
            errors.append(f"{key}: {exc}")
        refs = strings(req.get("tests"), f"{key} tests", errors, nonempty=True)
        for ref in refs:
            if ref not in tests:
                errors.append(f"{key}: unknown test {ref}")
            elif req.get("status") == "passed" and tests[ref].get("implementation") != "available":
                errors.append(f"{key}: passed requirement references planned test {ref}")
        check_evidence(req, root, key, errors, req.get("status") == "passed")
    # Gate acceptance cannot outrun its mandatory requirement records. This
    # checks only mapped requirements; profile-specific review remains required.
    for gate in sorted(passed_gates):
        mandatory = [(key, req) for key, req in reqs.items()
                     if req.get("gate") == gate and req.get("priority") == "must"]
        if not mandatory:
            errors.append(f"{gate}: passed gate has no mapped must requirements")
        for key, req in mandatory:
            if req.get("status") != "passed":
                errors.append(f"{gate}: passed before must requirement {key}")
    return errors


def markdown_targets(text):
    """Extract ordinary inline links and reference definitions, excluding code."""
    text = re.sub(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$", "", text)
    text = re.sub(r"`[^`\n]*`", "", text)
    for match in re.finditer(r"!?\[[^\]\n]*\]\(\s*(<[^>]*>|[^\s)]+)(?:\s+[^)]*)?\)", text):
        yield match.group(1).strip("<>")
    for match in re.finditer(r"(?m)^\s*\[[^\]]+\]:\s*(<[^>]*>|\S+)", text):
        yield match.group(1).strip("<>")


def validate_links(root, documents):
    errors = []
    for document in documents:
        try:
            source = repo_path(root, document)
            for target in markdown_targets(source.read_text(encoding="utf-8")):
                parsed = urlsplit(target)
                if parsed.scheme in {"https", "http", "mailto"} or parsed.netloc:
                    continue
                if parsed.scheme:
                    raise ValueError(f"unsupported link scheme: {target}")
                if not parsed.path:
                    continue  # Heading anchors are outside this lightweight check.
                path = unquote(parsed.path)
                destination = ((root / path.lstrip("/")) if path.startswith("/") else source.parent / path).resolve()
                if not destination.is_relative_to(root.resolve()) or "\\" in path or "\0" in path:
                    errors.append(f"{document}: link escapes repository: {target}")
                elif not destination.exists():
                    errors.append(f"{document}: missing link target: {target}")
        except (OSError, ValueError, UnicodeError, RuntimeError) as exc:
            errors.append(f"{document}: {exc}")
    return errors


def git_blob_sha(content):
    return hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()


def indexed_gitlinks(root):
    result = subprocess.run(["git", "ls-files", "--stage", "-z"], cwd=root, capture_output=True, check=True, timeout=20)
    links = {}
    output = result.stdout.decode("utf-8")
    if output and not output.endswith("\0"):
        raise ValueError("truncated git index output")
    seen = set()
    for entry in output.split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        mode, sha, stage = meta.split()
        if (not re.fullmatch(r"[0-7]{6}", mode) or not SHA.fullmatch(sha)
                or stage not in {"0", "1", "2", "3"} or not nonblank(path)):
            raise ValueError("malformed git index record")
        if stage != "0":
            raise ValueError(f"unmerged index entry: {path}")
        if path in seen:
            raise ValueError(f"duplicate git index path: {path}")
        seen.add(path)
        if mode == "160000":
            repo_path(root, path)
            links[path] = sha
    return links


def validate_upstream(data, root, gitlinks=None):
    errors = []
    upstream = data.get("upstream")
    if not isinstance(upstream, dict) or not SHA.fullmatch(str(upstream.get("commit", ""))) or upstream.get("repository") != "https://github.com/ucb-bar/chipyard":
        errors.append("upstream: invalid repository/commit")
    preserved = data.get("preserved_blobs")
    if not isinstance(preserved, dict) or not PRESERVED.issubset(preserved):
        errors.append("upstream: required preserved blobs missing")
        preserved = preserved if isinstance(preserved, dict) else {}
    for name, expected in preserved.items():
        try:
            actual = git_blob_sha(repo_path(root, name).read_bytes())
            if not isinstance(expected, str) or not SHA.fullmatch(expected) or actual != expected:
                errors.append(f"upstream: preserved blob changed: {name}")
        except (OSError, ValueError) as exc:
            errors.append(f"upstream: {name}: {exc}")
    expected_links = {}
    rows = data.get("submodules")
    if not isinstance(rows, list) or not rows:
        errors.append("upstream: submodules must be a nonempty list")
        rows = []
    for item in rows:
        try:
            if not isinstance(item, dict):
                raise ValueError("invalid submodule record")
            path, sha = item.get("path"), item.get("commit")
            repo_path(root, path)
            if path in expected_links or not isinstance(sha, str) or not SHA.fullmatch(sha):
                raise ValueError("duplicate submodule path or invalid SHA")
            expected_links[path] = sha
        except (OSError, ValueError) as exc:
            errors.append(f"upstream: {exc}")
    try:
        actual_links = indexed_gitlinks(root) if gitlinks is None else gitlinks
        if actual_links != expected_links:
            errors.append("upstream: indexed submodule pins differ from upstream-lock.json")
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        errors.append(f"upstream: cannot inspect git index: {exc}")
    return errors


def validate_configs(project, root):
    try:
        source = repo_path(root, CONFIG_PATH).read_text(encoding="utf-8")
    except (OSError, ValueError, UnicodeError) as exc:
        return [f"configurations: {exc}"]
    # Ignore examples inside strings as well as comments. This remains a narrow
    # source contract check, not a Scala parser or elaboration test.
    source = re.sub(r'(?s)""".*?"""|"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*', "", source)
    errors = []
    configs = project.get("configurations", [])
    for item in configs if isinstance(configs, list) else []:
        if not isinstance(item, dict) or not nonblank(item.get("name")) or not nonblank(item.get("upstream")):
            continue
        pattern = rf"\bclass\s+{re.escape(item['name'])}\s+extends\s+Config\s*\(\s*new\s+{re.escape(item['upstream'])}\s*\)"
        matches = re.findall(pattern, source)
        declarations = re.findall(rf"\bclass\s+{re.escape(item['name'])}\b", source)
        if len(matches) != 1 or len(declarations) != 1:
            errors.append(f"configurations: expected exactly one alias {item['name']} -> {item['upstream']}")
    return errors


def validate(root):
    data, errors = {}, []
    for name in ("project", "requirements", "upstream-lock"):
        try:
            data[name] = load_json(repo_path(root, f"nova/{name}.json"))
        except (OSError, ValueError, UnicodeError) as exc:
            errors.append(f"{name}.json: {exc}")
    if "project" in data:
        errors += validate_project(data["project"], root)
        errors += validate_configs(data["project"], root)
    if "requirements" in data and "project" in data:
        errors += validate_requirements(data["requirements"], data["project"], root)
    if "upstream-lock" in data:
        errors += validate_upstream(data["upstream-lock"], root)
        upstream = data["upstream-lock"].get("upstream")
        if "project" in data and isinstance(upstream, dict) and data["project"].get("baseline_commit") != upstream.get("commit"):
            errors.append("project baseline differs from upstream lock")
    documents = list(ROOT_DOCS)
    try:
        # Contain the search root before enumeration, not only each found file.
        directory = repo_path(root, "docs/nova")
        if not directory.is_dir():
            raise ValueError("documentation directory missing or not a directory")
        documents.extend(str(path.relative_to(root)) for path in sorted(directory.rglob("*.md"))
                         if "upstream" not in path.relative_to(directory).parts)
    except (OSError, ValueError, RuntimeError) as exc:
        errors.append(f"docs/nova: {exc}")
    errors += validate_links(root, documents)
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    try:
        errors = validate(args.root.resolve())
    except (OSError, ValueError, RuntimeError) as exc:
        errors = [f"repository root: {exc}"]
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        print(f"NOVA repository checks failed ({len(errors)} errors).", file=sys.stderr)
        return 1
    print("NOVA repository checks passed. This is not HDL or hardware qualification.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
