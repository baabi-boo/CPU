"""Offline text-contract checks for safe issue reporting; not a YAML parser."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FORMS = ROOT / ".github/ISSUE_TEMPLATE"


def unsafe_environment_requests(text):
    """Flag dump commands and affirmative requests, while allowing warnings."""
    findings = []
    for line in text.splitlines():
        lower = line.lower()
        if re.search(r"\bprintenv\b|`env`|`set`|/proc/self/environ", lower):
            findings.append(line)
        elif re.search(r"(?:full|complete) (?:shell )?environment dumps?", lower):
            if not re.search(r"\b(?:do not|never|must not)\b", lower):
                findings.append(line)
    return findings


class IssuePolicyTests(unittest.TestCase):
    def test_detects_unsafe_examples(self):
        for example in ("Include output of `printenv`", "Please attach a full environment dump",
                        "Paste `env`", "Upload /proc/self/environ"):
            with self.subTest(example=example):
                self.assertTrue(unsafe_environment_requests(example))

    def test_accepts_explicit_safety_warnings(self):
        self.assertFalse(unsafe_environment_requests(
            "Never attach full environment dumps.\nDo not publish complete shell environment dumps."))

    def test_forms_do_not_request_environment_dumps(self):
        for path in FORMS.glob("*.yml"):
            with self.subTest(form=path.name):
                self.assertEqual(unsafe_environment_requests(path.read_text(encoding="utf-8")), [])

    def test_framework_forms_route_nova_first(self):
        for name in ("bug-report.yml", "feature-request.yml"):
            text = (FORMS / name).read_text(encoding="utf-8")
            with self.subTest(form=name):
                self.assertIn("https://github.com/baabi-boo/CPU/issues", text)
                self.assertIn("isolated reproducer", text)
                self.assertIn("NOVA-M1", text)

    def test_no_obsolete_example_revision(self):
        text = (FORMS / "bug-report.yml").read_text(encoding="utf-8")
        self.assertNotIn("Release: 1.5.0", text)
        self.assertNotIn("Hash: a6a6a6", text)
        self.assertIn("Full NOVA Git SHA", text)

    def test_contact_policy_does_not_assume_private_reporting(self):
        text = (FORMS / "config.yml").read_text(encoding="utf-8")
        self.assertIn("NOVA-M1 development guide", text)
        self.assertIn("/CPU/blob/main/SECURITY.md", text)
        self.assertIn("private reporting availability is not assumed", text)


if __name__ == "__main__":
    unittest.main()
