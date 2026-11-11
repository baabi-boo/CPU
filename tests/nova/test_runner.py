"""Bounded subprocess regressions for the nonempty NOVA test runner."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/nova/run_tests.py"
PASSING_TEST = (
    "import unittest\n"
    "class Fixture(unittest.TestCase):\n"
    "    def test_pass(self):\n"
    "        self.assertEqual(2 + 2, 4)\n"
)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="nova-test-runner-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.tests = self.directory / "fixture-tests"
        self.tests.mkdir()

    def write_test(self, filename, contents):
        (self.tests / filename).write_text(contents, encoding="utf-8")

    def run_fixture(self, directory=None):
        return subprocess.run(
            [sys.executable, "-B", str(RUNNER), "--start-directory",
             str(self.tests if directory is None else directory)],
            cwd=self.directory, capture_output=True, text=True,
            errors="replace", timeout=20, check=False,
            env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C",
                 "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def assert_exit(self, result, expected):
        self.assertEqual(result.returncode, expected,
                         result.stdout + result.stderr)

    def test_single_passing_test_and_no_bytecode(self):
        self.write_test("test_fixture.py", PASSING_TEST)
        result = self.run_fixture()
        self.assert_exit(result, 0)
        self.assertIn("Discovered 1 NOVA tooling tests", result.stderr)
        self.assertIn("Ran 1 test", result.stderr)
        self.assertIn("no hardware qualification", result.stderr)
        self.assertFalse(list(self.directory.rglob("__pycache__")))

    def test_empty_directory_is_not_a_pass(self):
        result = self.run_fixture()
        self.assert_exit(result, 1)
        self.assertIn("zero tests discovered", result.stderr)

    def test_non_matching_files_are_not_counted(self):
        self.write_test("helper.py", PASSING_TEST)
        result = self.run_fixture()
        self.assert_exit(result, 1)
        self.assertIn("zero tests discovered", result.stderr)

    def test_custom_loader_returning_empty_suite_is_not_a_pass(self):
        self.write_test("test_fixture.py", PASSING_TEST +
                        "def load_tests(loader, tests, pattern):\n"
                        "    return unittest.TestSuite()\n")
        result = self.run_fixture()
        self.assert_exit(result, 1)
        self.assertIn("zero tests discovered", result.stderr)

    def test_missing_directory_and_file_are_rejected(self):
        not_directory = self.directory / "not-a-directory"
        not_directory.write_text("fixture\n", encoding="utf-8")
        for path in (self.directory / "missing", not_directory):
            with self.subTest(path=path.name):
                result = self.run_fixture(path)
                self.assert_exit(result, 1)
                self.assertIn("ERROR: cannot discover tests", result.stderr)
        self.assertFalse((self.directory / "missing").exists())

    def test_import_error_is_not_a_pass(self):
        self.write_test("test_fixture.py", "raise ImportError('fixture error')\n")
        result = self.run_fixture()
        self.assert_exit(result, 1)
        self.assertIn("fixture error", result.stderr)
        self.assertIn("FAILED (errors=1)", result.stderr)

    def test_failing_test_is_not_a_pass(self):
        self.write_test("test_fixture.py",
                        PASSING_TEST.replace("2 + 2, 4", "2 + 2, 5"))
        result = self.run_fixture()
        self.assert_exit(result, 1)
        self.assertIn("FAILED (failures=1)", result.stderr)

    def test_discovery_order_is_deterministic(self):
        for name in ("test_zulu.py", "test_alpha.py"):
            self.write_test(name, PASSING_TEST)
        result = self.run_fixture()
        self.assert_exit(result, 0)
        self.assertIn("Ran 2 tests", result.stderr)
        self.assertLess(result.stderr.index("test_alpha.Fixture"),
                        result.stderr.index("test_zulu.Fixture"))

    def test_make_target_uses_nonempty_runner(self):
        makefile = (ROOT / "nova.mk").read_text(encoding="utf-8")
        self.assertIn("test:\n\t$(PYTHON) -B scripts/nova/run_tests.py\n", makefile)
        self.assertNotIn("-m unittest discover", makefile)


if __name__ == "__main__":
    unittest.main()
