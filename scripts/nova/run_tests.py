#!/usr/bin/env python3
"""Run NOVA's offline Python tests, rejecting an empty discovered suite."""

import argparse
from pathlib import Path
import sys
import unittest


DEFAULT_START_DIRECTORY = Path(__file__).resolve().parents[2] / "tests/nova"


def run_tests(start_directory):
    """Use unittest's sorted, fixed-pattern discovery and return a process code."""
    # Direct invocation must not create bytecode beside source or fixture files.
    sys.dont_write_bytecode = True
    try:
        directory = Path(start_directory).resolve(strict=True)
        if not directory.is_dir():
            raise ValueError("path is not a directory")
        suite = unittest.TestLoader().discover(
            start_dir=str(directory), pattern="test_*.py",
            top_level_dir=str(directory),
        )
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        print(f"ERROR: cannot discover tests in {start_directory}: {error}",
              file=sys.stderr)
        return 1

    count = suite.countTestCases()
    if count == 0:
        print(f"ERROR: zero tests discovered in {directory}; refusing a pass",
              file=sys.stderr)
        return 1

    # Import errors become unittest failure cases and therefore fail this run.
    print(f"Discovered {count} NOVA tooling tests; no hardware qualification.",
          file=sys.stderr)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-directory", type=Path, default=DEFAULT_START_DIRECTORY,
        help="local test directory (default: this checkout's tests/nova)",
    )
    args = parser.parse_args(argv)
    return run_tests(args.start_directory)


if __name__ == "__main__":
    raise SystemExit(main())
