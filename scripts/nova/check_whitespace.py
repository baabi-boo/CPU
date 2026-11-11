#!/usr/bin/env python3
"""Check NOVA-managed text, including committed files in a clean checkout."""

import argparse
from pathlib import Path


ROOT_FILES = (
    "README.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md",
    "THIRD_PARTY_NOTICES.md", "nova.mk", ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/workflows/nova-foundation.yml",
    "generators/chipyard/src/main/scala/config/NovaM1Configs.scala",
)
PATTERNS = (
    "nova/*.json", "scripts/nova/*.py", "tests/nova/*.py",
    ".github/ISSUE_TEMPLATE/*.yml",
)


def managed_paths(root):
    resolved_root = root.resolve()

    def check_directory(path):
        if not path.resolve().is_relative_to(resolved_root):
            raise ValueError("managed directory escapes repository: " + str(path.relative_to(root)))

    paths = {root / name for name in ROOT_FILES}
    for pattern in PATTERNS:
        # Check the search directory before globbing, not only each result.
        check_directory((root / pattern).parent)
        paths.update(root.glob(pattern))
    check_directory(root / "docs/nova")
    paths.update(path for path in (root / "docs/nova").rglob("*.md")
                 if "upstream" not in path.relative_to(root / "docs/nova").parts)
    return sorted(paths)


def check_text(text, label):
    errors = []
    if text and not text.endswith("\n"):
        errors.append(f"{label}: missing final newline")
    for number, line in enumerate(text.splitlines(), 1):
        if line != line.rstrip():
            errors.append(f"{label}:{number}: trailing whitespace")
    return errors


def validate(root):
    try:
        root = Path(root).resolve()
        paths = managed_paths(root)
    except (OSError, RuntimeError, ValueError) as exc:
        return [f"managed paths: {exc}"]
    errors = []
    for path in paths:
        label = str(path.relative_to(root))
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                raise ValueError("managed path escapes repository")
            text = resolved.read_bytes().decode("utf-8")
            errors.extend(check_text(text, label))
        except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
            errors.append(f"{label}: {exc}")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    errors = validate(args.root)
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    print("NOVA managed-text whitespace checks passed (including committed files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
