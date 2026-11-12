"""Offline profile checks with synthetic local tool/source fixtures only."""

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("nova_g1_profile", ROOT / "scripts/nova/g1_profile.py")
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)


class ProfileFixture:
    def __init__(self, root):
        self.root = root
        self.manifest = json.loads((ROOT / "nova/g1-profile.json").read_text())
        self.lock = json.loads((ROOT / "nova/upstream-lock.json").read_text())
        for path in ["nova/g1-profile.json", "nova/upstream-lock.json",
                     self.manifest["conda_lock"], self.manifest["circt_input"],
                     *self.manifest["source_inputs_sha256"]]:
            dest = root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, dest)
        self.prefix = root / "prefix"
        for paths in profile.COLLATERAL.values():
            target = self.prefix / paths[0]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"synthetic collateral for unit tests only\n")
        specs = self.prefix / "riscv64-unknown-elf/lib/htif_nano.specs"
        specs.parent.mkdir(parents=True)
        specs.write_text("synthetic specs\n")
        self.specs = specs
        linker = root / "toolchains/libgloss/util/htif.ld"
        linker.parent.mkdir(parents=True, exist_ok=True)
        linker.write_text("synthetic linker\n")
        self.installed_linker = specs.with_name("htif.ld")
        self.installed_linker.write_bytes(linker.read_bytes())
        (root / "tests").mkdir(exist_ok=True)
        (root / "tests/htif.ld").symlink_to("../toolchains/libgloss/util/htif.ld")
        self.env = {"PATH": "/synthetic/bin", "RISCV": str(self.prefix)}

    def git(self, root, env, *args):
        if args == ("rev-parse", "--show-toplevel"):
            return str(root) + "\n"
        if args == ("ls-files", "--stage", "-z"):
            return "".join("160000 " + row["commit"] + " 0\t" + row["path"] + "\0"
                           for row in self.lock["submodules"])
        raise AssertionError("unexpected git command: " + repr(args))

    def available_tool(self, name, args, root, env):
        expected = profile.PINNED_VERSIONS.get(name)
        return {"name": name, "available": True, "observed_version": expected or "1.0",
                "expected_version": expected, "version_matches": True if expected else None,
                "identity_verified": False}

    def probe(self, argv, root, env):
        if argv == ["/synthetic/compiler", "-print-file-name=htif_nano.specs"]:
            return str(self.specs) + "\n"
        if argv == ["/synthetic/compiler", "-print-file-name=htif.ld"]:
            return str(self.installed_linker) + "\n"
        raise AssertionError("unexpected compiler probe: " + repr(argv))

    def inspect(self, env=None, source_state="at_pin", tool=None, probe=None):
        state = source_state if callable(source_state) else lambda *args: source_state
        with patch.object(profile, "_git", side_effect=self.git), \
                patch.object(profile, "_source_state", side_effect=state), \
                patch.object(profile, "_tool", side_effect=tool or self.available_tool), \
                patch.object(profile.shutil, "which", return_value="/synthetic/compiler"), \
                patch.object(profile, "_probe", side_effect=probe or self.probe):
            return profile.inspect_profile(self.root, self.env if env is None else env)


class G1ProfileTests(unittest.TestCase):
    def test_manifest_matches_existing_known_source_list_and_pins(self):
        manifest = json.loads((ROOT / "nova/g1-profile.json").read_text())
        lock = json.loads((ROOT / "nova/upstream-lock.json").read_text())
        spec = importlib.util.spec_from_file_location("profile_doctor", ROOT / "scripts/nova/doctor.py")
        doctor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(doctor)
        self.assertEqual(set(manifest["required_source_gitlinks"]), doctor.REQUIRED_SUBMODULES)
        pins = {row["path"] for row in lock["submodules"]}
        self.assertTrue(set(manifest["provisioning_source_gitlinks"]).issubset(pins))
        self.assertEqual(manifest["expected_initialized_optional_generators"], [])
        profile._validate_profile(manifest)

    def test_synthetic_ready_is_never_hardware_or_closure_qualification(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProfileFixture(Path(folder))
            result = fixture.inspect()
            self.assertEqual(result["blockers"], [])
            self.assertEqual(result["status"], "ready")
            self.assertTrue(result["known_prerequisites_present"])
            for key in ("hardware_qualified", "g1_gate_passed", "dependency_closure_qualified"):
                self.assertFalse(result[key])
            self.assertEqual(result["nested_dependency_closure"], "unqualified")
            self.assertEqual(result["maven_artifact_closure"], "unqualified")
            self.assertTrue(all(tool["identity_verified"] is False for tool in result["tools"]))
            installed = result["collateral"]["htif_installed_linker"]
            self.assertTrue(installed["available"])
            self.assertTrue(installed["matches_pinned"])
            self.assertEqual(installed["sha256"], result["collateral"]["htif_linker"]["sha256"])

    def test_chisel7_presence_is_rejected_even_empty_or_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProfileFixture(Path(folder))
            for value in ("", "0", "1"):
                with self.subTest(value=value):
                    result = fixture.inspect(dict(fixture.env, USE_CHISEL7=value))
                    self.assertEqual(result["status"], "blocked")
                    self.assertTrue(any("USE_CHISEL7" in item for item in result["blockers"]))

    def test_optional_initialized_generator_changes_graph_and_blocks(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProfileFixture(Path(folder))
            optional = fixture.root / "generators/gemmini"
            optional.mkdir(parents=True)
            (optional / ".git").write_text("gitdir: synthetic\n")
            result = fixture.inspect()
            self.assertEqual(result["initialized_optional_generators"], ["gemmini"])
            self.assertEqual(result["status"], "blocked")

    def test_different_host_architecture_does_not_reuse_linux64_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProfileFixture(Path(folder))
            with patch.object(profile.platform, "machine", return_value="aarch64"):
                result = fixture.inspect()
            self.assertIn("this profile declares only the Linux x86-64 lean lock", result["blockers"])

    def test_missing_or_dirty_required_sources_block(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProfileFixture(Path(folder))
            for state in ("uninitialized", "dirty", "checkout_pin_mismatch", "unreadable"):
                with self.subTest(state=state):
                    result = fixture.inspect(source_state=state)
                    self.assertEqual(result["status"], "blocked")
                    self.assertEqual(len(result["source_gitlinks"]), 21)
                    self.assertTrue(any("generators/rocket-chip: " + state == b for b in result["blockers"]))

    def test_existing_riscv_prefix_without_fesvr_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProfileFixture(Path(folder))
            (fixture.prefix / "lib/libfesvr.a").unlink()
            result = fixture.inspect()
            self.assertFalse(result["collateral"]["fesvr_library"]["available"])
            self.assertIn("installed collateral missing or unsafe: fesvr_library", result["blockers"])

    def test_provisioning_sources_allow_only_at_pin_or_uninitialized(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProfileFixture(Path(folder))
            for state in ("at_pin", "uninitialized", "invalid_repository", "invalid_path",
                          "unreadable", "missing_pin", "index_pin_mismatch",
                          "checkout_pin_mismatch", "dirty", "unknown_future_state"):
                with self.subTest(state=state):
                    def source(root, path, pin, index, env):
                        return state if path in profile.PROVISIONING_SOURCE_GITLINKS else "at_pin"
                    result = fixture.inspect(source_state=source)
                    allowed = state in {"at_pin", "uninitialized"}
                    self.assertEqual(result["status"], "ready" if allowed else "blocked")
                    self.assertEqual(result["known_prerequisites_present"], allowed)
                    integrity = [item for item in result["blockers"]
                                 if item.startswith("provisioning source integrity: ")]
                    self.assertEqual(len(integrity), 0 if allowed else 3)
                    self.assertTrue(all(item.endswith(": " + state) for item in integrity))

    def test_linker_must_resolve_to_pinned_libgloss_path(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProfileFixture(Path(folder))
            (fixture.root / "tests/htif.ld").unlink()
            (fixture.root / "tests/htif.ld").write_text("different script\n")
            result = fixture.inspect()
            self.assertFalse(result["collateral"]["htif_linker"]["available"])

    def test_installed_linker_missing_or_nonregular_blocks(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProfileFixture(Path(folder))
            fixture.installed_linker.unlink()
            for directory in (False, True):
                with self.subTest(directory=directory):
                    if directory:
                        fixture.installed_linker.mkdir()
                    result = fixture.inspect()
                    self.assertEqual(result["status"], "blocked")
                    self.assertFalse(result["collateral"]["htif_installed_linker"]["available"])
                    self.assertIn("HTIF linker script does not resolve inside the recorded RISCV prefix",
                                  result["blockers"])

    def test_installed_linker_wrong_prefix_or_unresolved_name_blocks(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as other:
            fixture = ProfileFixture(Path(folder))
            external = Path(other) / "htif.ld"
            external.write_bytes(fixture.installed_linker.read_bytes())
            for observed in (None, "htif.ld\n", str(external) + "\n"):
                with self.subTest(observed=observed):
                    def probe(argv, root, env):
                        if argv[-1] == "-print-file-name=htif.ld":
                            return observed
                        return fixture.probe(argv, root, env)
                    result = fixture.inspect(probe=probe)
                    self.assertEqual(result["status"], "blocked")
                    self.assertFalse(result["collateral"]["htif_installed_linker"]["available"])
                    self.assertNotIn(str(external), json.dumps(result))

    def test_installed_linker_symlink_outside_prefix_blocks(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as other:
            fixture = ProfileFixture(Path(folder))
            external = Path(other) / "htif.ld"
            external.write_bytes(fixture.installed_linker.read_bytes())
            fixture.installed_linker.unlink()
            fixture.installed_linker.symlink_to(external)
            result = fixture.inspect()
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["collateral"]["htif_installed_linker"]["available"])
            self.assertNotIn(str(external), json.dumps(result))

    def test_installed_linker_content_must_match_preserved_source(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProfileFixture(Path(folder))
            fixture.installed_linker.write_text("different installed linker\n")
            result = fixture.inspect()
            installed = result["collateral"]["htif_installed_linker"]
            self.assertTrue(installed["available"])
            self.assertFalse(installed["matches_pinned"])
            self.assertEqual(result["status"], "blocked")
            self.assertIn("installed HTIF linker script differs from the pinned libgloss target",
                          result["blockers"])

    def test_missing_gxx_and_jq_fail_known_prerequisites(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProfileFixture(Path(folder))
            def tool(name, args, root, env):
                value = fixture.available_tool(name, args, root, env)
                if name in {"riscv64-unknown-elf-g++", "jq"}:
                    value["available"] = False
                return value
            result = fixture.inspect(tool=tool)
            self.assertIn("tool unavailable: jq", result["blockers"])
            self.assertIn("tool unavailable: riscv64-unknown-elf-g++", result["blockers"])

    def test_wrong_installed_pinned_versions_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProfileFixture(Path(folder))
            def tool(name, args, root, env):
                value = fixture.available_tool(name, args, root, env)
                if name in profile.PINNED_VERSIONS:
                    value["observed_version"] = "9.9.9"
                    value["version_matches"] = False
                return value
            result = fixture.inspect(tool=tool)
            self.assertIn("pinned tool version mismatch: verilator", result["blockers"])
            self.assertIn("pinned tool version mismatch: firtool", result["blockers"])

    def test_pinned_tool_source_drift_is_not_installed_version_success(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProfileFixture(Path(folder))
            (fixture.root / fixture.manifest["circt_input"]).write_text('{"version":"firtool-9.0.0"}\n')
            result = fixture.inspect()
            self.assertIn("pinned Verilator/firtool source identity could not be verified", result["blockers"])

    def test_source_graph_hash_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = ProfileFixture(Path(folder))
            (fixture.root / "build.sbt").write_text("changed graph\n")
            result = fixture.inspect()
            self.assertFalse(result["source_inputs"]["build.sbt"]["matches_profile"])
            self.assertEqual(result["status"], "blocked")

    def test_symlink_outside_prefix_is_not_collateral(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as other:
            fixture = ProfileFixture(Path(folder))
            external = Path(other) / "private-file"
            external.write_bytes(b"do not read as evidence\n")
            library = fixture.prefix / "lib/libriscv.a"
            library.unlink()
            library.symlink_to(external)
            result = fixture.inspect()
            self.assertFalse(result["collateral"]["riscv_library"]["available"])
            self.assertNotIn(str(external), json.dumps(result))

    def test_profile_validation_rejects_unsafe_or_weakened_contract(self):
        good = json.loads((ROOT / "nova/g1-profile.json").read_text())
        cases = []
        for field, value in (("schema_version", True), ("closure_qualified", True),
                             ("expected_tool_versions", {"verilator": "latest"}),
                             ("expected_initialized_optional_generators", ["gemmini"]),
                             ("conda_lock", "../../outside")):
            case = copy.deepcopy(good)
            case[field] = value
            cases.append(case)
        case = copy.deepcopy(good)
        case["required_source_gitlinks"][0] = "../outside"
        cases.append(case)
        case = copy.deepcopy(good)
        case["required_source_gitlinks"][0] = "generators/invented"
        cases.append(case)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                profile._validate_profile(case)

    def test_version_parser_does_not_accept_generic_llvm_as_firtool(self):
        self.assertEqual(profile._version("verilator", "Verilator 5.022 2024-02-24"), "5.022")
        self.assertEqual(profile._version("firtool", "CIRCT firtool-1.75.0"), "1.75.0")
        self.assertIsNone(profile._version("firtool", "LLVM version 1.75.0"))
        self.assertEqual(profile._version("java", "Picked up JAVA_TOOL_OPTIONS: secret42.12\nopenjdk version 20.0.2"), "20.0.2")

    def test_malformed_gitlink_index_fails_closed(self):
        for data in (None, "160000 bad 0\tdep\0", "160000 " + "a" * 40 + " 1\tdep\0",
                     "160000 " + "a" * 40 + " 0\t../dep\0", "truncated"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                profile._gitlink_index(data)

    def test_invalid_root_does_not_run_commands_or_leak_path(self):
        with patch.object(profile, "_git") as git:
            result = profile.inspect_profile("/absent/private/profile-root", {"SECRET": "sensitive"})
            git.assert_not_called()
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn("private", json.dumps(result))
        self.assertNotIn("sensitive", json.dumps(result))

    def test_cli_strict_exit_and_normal_diagnostic(self):
        report = {"status": "blocked", "blockers": ["fixture"], "limitations": []}
        for args, expected in ((["--json"], 0), (["--strict", "--json"], 2)):
            with self.subTest(args=args), patch.object(profile, "inspect_profile", return_value=report), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(profile.main(args), expected)
                self.assertEqual(json.loads(output.getvalue()), report)


if __name__ == "__main__":
    unittest.main()
