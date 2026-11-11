"""Keep NOVA setup preflight opt-in and distinct from repository-only checks."""

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = ROOT / "nova.mk"


class PreflightMakeTests(unittest.TestCase):
    def test_named_targets_are_phony_and_not_part_of_check(self):
        contents = MAKEFILE.read_text(encoding="utf-8")
        phony_line = next(line for line in contents.splitlines()
                          if line.startswith(".PHONY:"))
        self.assertIn("preflight", phony_line.split())
        self.assertIn("preflight-strict", phony_line.split())
        self.assertIn("check: validate test whitespace\n", contents)
        self.assertNotIn("check: preflight", contents)

    def test_opt_in_targets_only_invoke_read_only_preflight(self):
        for target, strict in (("preflight", False), ("preflight-strict", True)):
            with self.subTest(target=target):
                run = subprocess.run(["make", "-n", "-f", "nova.mk", target],
                                     cwd=ROOT, capture_output=True, text=True,
                                     timeout=5, check=False)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertIn("python3 -B scripts/nova/bootstrap_preflight.py", run.stdout)
                self.assertEqual("--strict" in run.stdout, strict)
                for unsafe in ("build-setup.sh", "submodule update", "conda install",
                               "pip install", "sims/verilator"):
                    self.assertNotIn(unsafe, run.stdout)

    def test_default_check_does_not_run_preflight(self):
        run = subprocess.run(["make", "-n", "-f", "nova.mk", "check"],
                             cwd=ROOT, capture_output=True, text=True,
                             timeout=5, check=False)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn("bootstrap_preflight.py", run.stdout)


if __name__ == "__main__":
    unittest.main()
