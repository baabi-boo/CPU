"""Unit tests for offline repository checks; none simulate hardware."""

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("nova_check", ROOT / "scripts/nova/check.py")
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


class RepositoryCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "design.md").write_text("# Design\n", encoding="utf-8")
        self.project = {
            "schema_version": 1, "name": "NOVA-M1", "baseline_commit": "a" * 40,
            "configurations": [{"name": "NovaM1BaselineConfig", "upstream": "RocketConfig", "status": "implemented_unverified"}],
            "milestones": [{"id": f"G{i}", "title": f"Gate {i}", "status": "planned", "depends_on": [f"G{i - 1}"] if i else [], "evidence": []} for i in range(10)],
        }
        self.requirements = {
            "schema_version": 1,
            "tests": [{"id": "T-REPO-001", "description": "Repository test", "level": "repository", "implementation": "available", "command": "make check"}],
            "requirements": [{"id": "REQ-REPO-001", "title": "Requirement", "gate": "G0", "priority": "must", "owner_role": "maintainer", "status": "planned", "design_doc": "design.md", "tests": ["T-REPO-001"], "evidence": []}],
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_project_and_requirements(self):
        self.assertEqual(check.validate_project(self.project, self.root), [])
        self.assertEqual(check.validate_requirements(self.requirements, self.project, self.root), [])

    def test_duplicate_gate_id(self):
        self.project["milestones"].append(copy.deepcopy(self.project["milestones"][0]))
        self.assertTrue(any("duplicate id" in e for e in check.validate_project(self.project, self.root)))

    def test_unknown_dependency_and_cycle(self):
        self.project["milestones"][0]["depends_on"] = ["G1", "G99"]
        errors = check.validate_project(self.project, self.root)
        self.assertTrue(any("cycle" in e for e in errors))
        self.assertTrue(any("unknown dependency" in e for e in errors))

    def test_pass_requires_evidence_and_prerequisites(self):
        self.project["milestones"][1]["status"] = "passed"
        errors = check.validate_project(self.project, self.root)
        self.assertTrue(any("requires local evidence" in e for e in errors))
        self.assertTrue(any("before prerequisite" in e for e in errors))

    def test_valid_pass_with_local_evidence(self):
        self.project["milestones"][0].update(status="passed", evidence=["design.md"])
        self.assertEqual(check.validate_project(self.project, self.root), [])

    def test_passed_gate_requires_completed_mandatory_requirements(self):
        self.project["milestones"][0].update(status="passed", evidence=["design.md"])
        for status in ("planned", "in_progress", "blocked", "failed"):
            with self.subTest(status=status):
                self.requirements["requirements"][0]["status"] = status
                errors = check.validate_requirements(self.requirements, self.project, self.root)
                self.assertTrue(any("passed before must requirement REQ-REPO-001" in e for e in errors))
        self.requirements["requirements"][0].update(status="passed", evidence=["design.md"])
        self.assertEqual(check.validate_requirements(self.requirements, self.project, self.root), [])

    def test_passed_gate_cannot_remove_all_mandatory_coverage(self):
        self.project["milestones"][0].update(status="passed", evidence=["design.md"])
        self.requirements["requirements"][0]["priority"] = "should"
        errors = check.validate_requirements(self.requirements, self.project, self.root)
        self.assertTrue(any("no mapped must requirements" in e for e in errors))

    def test_optional_planned_requirement_does_not_block_gate(self):
        self.project["milestones"][0].update(status="passed", evidence=["design.md"])
        mandatory = self.requirements["requirements"][0]
        optional = dict(mandatory, id="REQ-REPO-002", priority="should")
        self.requirements["requirements"].append(optional)
        mandatory.update(status="passed", evidence=["design.md"])
        self.assertEqual(check.validate_requirements(self.requirements, self.project, self.root), [])

    def test_template_filename_cannot_qualify_gate_requirement_or_config(self):
        (self.root / "TEMPLATE.md").write_text("# Filled in later\n", encoding="utf-8")
        self.project["milestones"][0].update(status="passed", evidence=["TEMPLATE.md"])
        self.project["configurations"][0].update(status="simulated", evidence=["TEMPLATE.md"])
        self.requirements["requirements"][0].update(status="passed", evidence=["TEMPLATE.md"])
        errors = check.validate_project(self.project, self.root)
        self.assertEqual(sum("template is not executed evidence" in e for e in errors), 2)
        self.assertTrue(any("template is not executed evidence" in e for e in
                            check.validate_requirements(self.requirements, self.project, self.root)))

    def test_renamed_template_marker_is_rejected(self):
        for text in ("# Evidence record template — NOT EXECUTED\n", "**TEMPLATE ONLY. Not a run.**\n"):
            with self.subTest(text=text):
                (self.root / "run.md").write_text(text, encoding="utf-8")
                self.project["milestones"][0].update(status="passed", evidence=["run.md"])
                self.assertTrue(any("template is not executed evidence" in e for e in
                                    check.validate_project(self.project, self.root)))

    def test_real_record_may_describe_unexecuted_exclusions(self):
        (self.root / "run.md").write_text(
            "# Run record\nDeclared test passed.\n"
            "Excluded extensions were not executed and are not qualified.\n"
            "Template expansion is an operation tested by this run.\n", encoding="utf-8")
        self.project["milestones"][0].update(status="passed", evidence=["run.md"])
        self.assertEqual(check.validate_project(self.project, self.root), [])

    def test_empty_record_cannot_qualify_pass(self):
        (self.root / "empty.md").write_bytes(b"")
        self.project["milestones"][0].update(status="passed", evidence=["empty.md"])
        self.assertTrue(any("empty file is not executed evidence" in e for e in
                            check.validate_project(self.project, self.root)))

    def test_missing_and_duplicate_test_references(self):
        self.requirements["requirements"][0]["tests"] = ["T-MISSING-001", "T-MISSING-001"]
        errors = check.validate_requirements(self.requirements, self.project, self.root)
        self.assertTrue(any("unknown test" in e for e in errors))
        self.assertTrue(any("duplicate entries" in e for e in errors))

    def test_planned_test_cannot_have_command_or_support_pass(self):
        self.requirements["tests"][0]["implementation"] = "planned"
        self.requirements["requirements"][0].update(status="passed", evidence=["design.md"])
        errors = check.validate_requirements(self.requirements, self.project, self.root)
        self.assertTrue(any("command must be null" in e for e in errors))
        self.assertTrue(any("references planned test" in e for e in errors))

    def test_available_test_requires_command(self):
        self.requirements["tests"][0]["command"] = None
        self.assertTrue(any("requires command" in e for e in check.validate_requirements(self.requirements, self.project, self.root)))

    def test_traversal_and_symlink_escape(self):
        for name in ("../outside", "/absolute", "dir/../file", "dir\\file"):
            with self.assertRaises(ValueError):
                check.repo_path(self.root, name)
        (self.root / "escape").symlink_to(self.root.parent)
        with self.assertRaises(ValueError):
            check.repo_path(self.root, "escape/file")

    def test_links_existing_missing_external_and_code(self):
        (self.root / "links.md").write_text(
            "[ok](design.md#title) [remote](https://example.invalid/x)\n"
            "```text\n[example](ignored.md)\n```\n[missing](absent.md)\n", encoding="utf-8")
        errors = check.validate_links(self.root, ["links.md"])
        self.assertEqual(len(errors), 1)
        self.assertIn("absent.md", errors[0])

    def test_links_escape_and_reference_definition(self):
        (self.root / "links.md").write_text("[x](../outside)\n[ref]: missing.md\n", encoding="utf-8")
        errors = check.validate_links(self.root, ["links.md"])
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("escapes repository" in e for e in errors))

    def test_duplicate_json_keys_and_invalid_schema(self):
        path = self.root / "bad.json"
        path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            check.load_json(path)
        for value in ([], {"schema_version": True}, {"schema_version": 2}):
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ValueError):
                check.load_json(path)

    def test_malformed_rows_report_errors(self):
        self.project["milestones"] = [None, {}, {"id": "G0", "depends_on": 1}]
        self.assertTrue(check.validate_project(self.project, self.root))
        self.requirements["tests"] = [None]
        self.assertTrue(check.validate_requirements(self.requirements, self.project, self.root))

    def test_malformed_scalar_types_report_errors(self):
        self.project["milestones"][0]["status"] = []
        self.project["configurations"][0]["status"] = {}
        self.assertTrue(check.validate_project(self.project, self.root))
        self.requirements["tests"][0].update(level=[], implementation={})
        self.requirements["requirements"][0].update(gate=[], priority={}, status=[])
        self.assertTrue(check.validate_requirements(self.requirements, self.project, self.root))
        self.project["milestones"] = 42
        self.assertTrue(check.validate_requirements(self.requirements, self.project, self.root))

    def test_preserved_blobs_and_gitlinks(self):
        preserved = {}
        for name in check.PRESERVED:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"preserved\n")
            preserved[name] = check.git_blob_sha(b"preserved\n")
        lock = {"upstream": {"repository": "https://github.com/ucb-bar/chipyard", "commit": "a" * 40}, "preserved_blobs": preserved, "submodules": [{"path": "generators/core", "commit": "b" * 40}]}
        self.assertEqual(check.validate_upstream(lock, self.root, {"generators/core": "b" * 40}), [])
        (self.root / "LICENSE").write_bytes(b"changed\n")
        errors = check.validate_upstream(lock, self.root, {"generators/core": "c" * 40})
        self.assertTrue(any("preserved blob changed" in e for e in errors))
        self.assertTrue(any("pins differ" in e for e in errors))

    def test_config_aliases_must_be_real_not_comments(self):
        path = self.root / check.CONFIG_PATH
        path.parent.mkdir(parents=True)
        alias = "class NovaM1BaselineConfig extends Config(new RocketConfig)"
        path.write_text(alias, encoding="utf-8")
        self.assertEqual(check.validate_configs(self.project, self.root), [])
        path.write_text("// " + alias, encoding="utf-8")
        self.assertTrue(check.validate_configs(self.project, self.root))


if __name__ == "__main__":
    unittest.main()
