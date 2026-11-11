"""The Rocket Make entry point must only print a plan, never execute RTL."""

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]


class RocketMakeTests(unittest.TestCase):
    def test_plan_is_phony_and_separate_from_checks(self):
        makefile = (ROOT / "nova.mk").read_text(encoding="utf-8")
        phony = next(line for line in makefile.splitlines()
                     if line.startswith(".PHONY:"))
        self.assertIn("rocket-plan", phony.split())
        self.assertIn("check: validate test whitespace\n", makefile)
        self.assertIn("rocket-plan:\n\t$(PYTHON) -B scripts/nova/rocket_baseline.py --plan\n", makefile)
        self.assertIn("rocket-plan    Read-only plan", makefile)

    def test_make_dry_run_only_invokes_plan(self):
        result = subprocess.run(
            ["make", "-n", "-f", "nova.mk", "rocket-plan"], cwd=ROOT,
            text=True, capture_output=True, timeout=5, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = [line.strip() for line in result.stdout.splitlines()
                    if not line.startswith("make[") and line.strip()]
        self.assertEqual(commands, ["python3 -B scripts/nova/rocket_baseline.py --plan"])
        for dangerous in ("--execute", "--approved-budget", "build-setup.sh",
                          "git submodule", "conda install", "sims/verilator"):
            self.assertNotIn(dangerous, result.stdout)

    def test_default_targets_do_not_invoke_rocket_runner(self):
        for target in ("check", "preflight", "doctor"):
            with self.subTest(target=target):
                result = subprocess.run(
                    ["make", "-n", "-f", "nova.mk", target], cwd=ROOT,
                    text=True, capture_output=True, timeout=5, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("rocket_baseline.py", result.stdout)


if __name__ == "__main__":
    unittest.main()
