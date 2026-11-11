"""Adversarial metadata fixtures; these tests do not qualify any hardware."""

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("nova_check_adversarial", ROOT / "scripts/nova/check.py")
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


class AdversarialCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = {
            "name": "NOVA-M1", "baseline_commit": "a" * 40,
            "configurations": [{"name": "NovaM1BaselineConfig", "upstream": "RocketConfig",
                                "status": "implemented_unverified"}],
            "milestones": [{"id": f"G{i}", "title": "Gate", "status": "planned",
                            "depends_on": [], "evidence": []} for i in range(10)],
        }

    def test_nonfinite_json_and_blank_keys_are_rejected(self):
        path = self.root / "metadata.json"
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                path.write_text('{"schema_version":1,"extra":' + value + '}', encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "non-finite JSON"):
                    check.load_json(path)
        for key in ("", " ", "\t"):
            with self.subTest(key=key):
                path.write_text(json.dumps({"schema_version": 1, "nested": {key: 0}}), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "blank JSON key"):
                    check.load_json(path)

    def test_malformed_json_and_wrong_root_types_are_rejected(self):
        path = self.root / "metadata.json"
        for payload in ("{", '{"schema_version":1,}', "null", "42", '"string"',
                        '{"schema_version":1,"nested":{"a":1,"a":2}}'):
            with self.subTest(payload=payload):
                path.write_text(payload, encoding="utf-8")
                with self.assertRaises(ValueError):
                    check.load_json(path)

    def test_symlink_loop_evidence_returns_diagnostics(self):
        (self.root / "loop").symlink_to("loop")
        with self.assertRaises(ValueError):
            check.repo_path(self.root, "loop")
        self.project["milestones"][0].update(status="passed", evidence=["loop"])
        self.assertTrue(check.validate_project(self.project, self.root))

    def test_looped_root_fails_without_traceback(self):
        (self.root / "loop").symlink_to("loop")
        with contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(check.main(["--root", str(self.root / "loop")]), 1)
        self.assertIn("repository root", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    def test_link_loops_and_encoded_escape_are_rejected(self):
        (self.root / "loop").symlink_to("loop")
        source = self.root / "links.md"
        for target in ("loop", "%2e%2e/outside", "%00invalid"):
            with self.subTest(target=target):
                source.write_text(f"[bad]({target})\n", encoding="utf-8")
                self.assertTrue(check.validate_links(self.root, ["links.md"]))

    def test_evidence_escape_and_whitespace_are_rejected(self):
        (self.root / "outside").symlink_to(self.root.parent)
        (self.root / "blank.md").write_text(" \n\t\n", encoding="utf-8")
        for value in ("../outside.md", "outside/record.md", "blank.md", ""):
            with self.subTest(value=value):
                self.project["milestones"][0].update(status="passed", evidence=[value])
                self.assertTrue(check.validate_project(self.project, self.root))

    def test_binary_prefixed_template_does_not_crash_or_qualify(self):
        (self.root / "record.bin").write_bytes(b"\xff\xfe\x00\n# TEMPLATE ONLY. Not a run.\n")
        self.project["milestones"][0].update(status="passed", evidence=["record.bin"])
        errors = check.validate_project(self.project, self.root)
        self.assertTrue(any("template is not executed evidence" in error for error in errors))

    def test_unbounded_invalid_gate_ids_do_not_recurse(self):
        self.project["milestones"] = [
            {"id": f"G{i}", "title": "Gate", "status": "planned", "depends_on": [f"G{i + 1}"]}
            for i in range(1100)
        ]
        self.assertTrue(check.validate_project(self.project, self.root))

    def test_config_strings_duplicates_and_wrong_bases_fail(self):
        path = self.root / check.CONFIG_PATH
        path.parent.mkdir(parents=True)
        alias = "class NovaM1BaselineConfig extends Config(new RocketConfig)"
        other = "class NovaM1BaselineConfig extends Config(new OtherConfig)"
        for source in (f'val example = "{alias}"', f'val example = """{alias}"""',
                       alias + "\n" + alias, alias + "\n" + other, other):
            with self.subTest(source=source):
                path.write_text(source + "\n", encoding="utf-8")
                self.assertTrue(check.validate_configs(self.project, self.root))
        path.write_text('val unrelated = "// not a comment"\n' + alias + "\n", encoding="utf-8")
        self.assertEqual(check.validate_configs(self.project, self.root), [])

    def test_malformed_duplicate_and_truncated_git_index_fail(self):
        entry = "160000 " + "a" * 40 + " 0\tmodule"
        for payload in (entry, entry + "\0" + entry + "\0", "broken\0",
                        "160000 invalid 0\tmodule\0", "160000 " + "a" * 40 + " 0\t \0",
                        "invalid " + "a" * 40 + " 0\tmodule\0"):
            with self.subTest(payload=payload), mock.patch.object(check.subprocess, "run") as run:
                run.return_value = subprocess.CompletedProcess([], 0, payload.encode(), b"")
                with self.assertRaises(ValueError):
                    check.indexed_gitlinks(self.root)
        with mock.patch.object(check.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, (entry + "\0").encode(), b"")
            self.assertEqual(check.indexed_gitlinks(self.root), {"module": "a" * 40})

    def test_nested_malformed_metadata_types_report_errors(self):
        for field in ("depends_on", "evidence", "status", "title"):
            for value in (None, {}, [None], 1):
                with self.subTest(field=field, value=value):
                    project = copy.deepcopy(self.project)
                    project["milestones"][0][field] = value
                    self.assertTrue(check.validate_project(project, self.root))

    def test_gitlink_traversal_and_invalid_utf8_are_rejected(self):
        for payload in (b"\xff\0", ("160000 " + "a" * 40 + " 0\t../escape\0").encode()):
            with self.subTest(payload=payload), mock.patch.object(check.subprocess, "run") as run:
                run.return_value = subprocess.CompletedProcess([], 0, payload, b"")
                with self.assertRaises((ValueError, UnicodeError)):
                    check.indexed_gitlinks(self.root)


if __name__ == "__main__":
    unittest.main()
