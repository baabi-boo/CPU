"""Offline synthetic capture fixtures; these tests do not qualify real RTL."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nova_campaign_artifacts", ROOT / "scripts/nova/campaign_artifacts.py")
artifacts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(artifacts)


def put(root, relative, data, executable=False):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    if executable:
        path.chmod(0o755)
    return path


def elf(machine=243, elf_type=2, entry=0x80000078, flags=5,
        offset=0, filesz=128, memsz=128, alignment=4096):
    ident = b"\x7fELF\x02\x01\x01" + bytes(9)
    header = struct.pack("<16sHHIQQQIHHHHHH", ident, elf_type, machine, 1,
                         entry, 64, 0, 0, 64, 56, 1, 0, 0, 0)
    program = struct.pack("<IIQQQQQQ", 1, flags, offset, 0x80000000,
                          0x80000000, filesz, memsz, alignment)
    # Synthetic instruction bytes only. Nobody executes this fixture.
    return header + program + b"\x13\x00\x00\x00" * 2


def git(root, *args):
    env = {"PATH": os.environ.get("PATH", os.defpath), "LC_ALL": "C",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
         "-c", "user.name=Local capture fixture", "-c", "user.email=fixture@example.invalid",
         "-C", str(root), *args], env=env, check=True, capture_output=True).stdout.decode().strip()


def source_fixture(root):
    git(root, "init", "-q", "-b", "main")
    manifest = {"schema_version": 1, "submodules": [], "preserved_blobs": {}}
    for relative in artifacts.CONDA_INPUTS:
        data = ("synthetic input " + relative + "\n").encode()
        put(root, relative, data)
        manifest["preserved_blobs"][relative] = hashlib.sha1(
            b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    for relative in artifacts.SOURCE_INPUTS:
        put(root, relative, "synthetic source input\n")
    put(root, "nova/upstream-lock.json", json.dumps(manifest))
    put(root, ".gitignore", "generated/\nnova-out/\n")
    put(root, "tracked.txt", "source\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "Synthetic source fixture")
    return manifest


class FileCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_regular_file_record_is_relative_and_hashed(self):
        path = put(self.root, "outputs/test.bin", b"observed bytes")
        expected = {"path": "outputs/test.bin", "kind": "artifact", "size_bytes": 14,
                    "sha256": hashlib.sha256(b"observed bytes").hexdigest()}
        self.assertEqual(artifacts.capture_file(self.root, path), expected)
        self.assertEqual(artifacts.capture_file(self.root, "outputs/test.bin"), expected)
        self.assertNotIn(str(self.root), json.dumps(expected))

    def test_traversal_and_outside_paths_rejected(self):
        put(self.root, "a", b"a")
        for relative in ("../a", "sub/../a", "./a", "a\n", "a\\b", "/etc/passwd"):
            with self.subTest(path=relative), self.assertRaises(artifacts.ArtifactError):
                artifacts.capture_file(self.root, relative)

    def test_symlink_leaf_parent_and_root_rejected(self):
        put(self.root, "real/a", b"a")
        (self.root / "alias").symlink_to("real", target_is_directory=True)
        (self.root / "link").symlink_to("real/a")
        for root, relative in ((self.root, "alias/a"), (self.root, "link"),
                               (self.root / "alias", "a")):
            with self.subTest(path=relative), self.assertRaises(artifacts.ArtifactError):
                artifacts.capture_file(root, relative)

    def test_fifo_directory_missing_and_oversize_rejected(self):
        os.mkfifo(self.root / "pipe")
        (self.root / "directory").mkdir()
        put(self.root, "large", b"12345")
        for path in ("pipe", "directory", "missing", "large"):
            with self.subTest(path=path), self.assertRaises(artifacts.ArtifactError):
                artifacts.capture_file(self.root, path, max_bytes=4)

    def test_limits_and_kind_are_checked(self):
        put(self.root, "a", b"a")
        for limit in (0, -1, True, "1", artifacts.MAX_FILE_BYTES + 1):
            with self.subTest(limit=limit), self.assertRaises(artifacts.ArtifactError):
                artifacts.capture_file(self.root, "a", max_bytes=limit)
        with self.assertRaises(artifacts.ArtifactError):
            artifacts.capture_file(self.root, "a", kind="/unsafe")

    def test_modification_and_path_replacement_during_hash_rejected(self):
        real_read = os.read
        for replace in (False, True):
            put(self.root, "file", b"1234")
            changed = False

            def mutate(descriptor, size):
                nonlocal changed
                data = real_read(descriptor, size)
                if not changed:
                    changed = True
                    if replace:
                        replacement = put(self.root, "replacement", b"5678")
                        replacement.replace(self.root / "file")
                    else:
                        put(self.root, "file", b"5678")
                return data

            with self.subTest(replacement=replace), patch.object(artifacts.os, "read", side_effect=mutate):
                with self.assertRaises(artifacts.ArtifactError):
                    artifacts.capture_file(self.root, "file")

    def test_complete_riscv_elf_is_structurally_accepted_without_execution(self):
        put(self.root, "target", elf())
        result = artifacts.capture_file(self.root, "target", kind="riscv_elf")
        self.assertEqual(result["size_bytes"], 128)
        self.assertEqual(result["kind"], "riscv_elf")

    def test_native_simulator_must_be_executable_x86_64_elf(self):
        put(self.root, "simulator", elf(machine=62, elf_type=3), executable=True)
        self.assertEqual(artifacts.capture_file(self.root, "simulator", "simulator")["kind"], "simulator")
        (self.root / "simulator").chmod(0o644)
        with self.assertRaises(artifacts.ArtifactError):
            artifacts.capture_file(self.root, "simulator", "simulator")
        put(self.root, "simulator", elf(), executable=True)
        with self.assertRaises(artifacts.ArtifactError):
            artifacts.capture_file(self.root, "simulator", "simulator")

    def test_fake_or_invalid_elf_headers_and_segments_rejected(self):
        samples = [elf()[:20], elf()[:63], elf(machine=62), elf(elf_type=1),
                   elf(entry=0), elf(flags=4), elf(filesz=129), elf(memsz=127),
                   elf(offset=1), elf(alignment=3)]
        for offset, value, format_ in ((5, 2, "B"), (32, 1000, "Q"), (52, 20, "H"),
                                       (54, 1, "H"), (56, 0, "H"), (56, 4097, "H"),
                                       (40, 500, "Q"), (60, 1, "H")):
            data = bytearray(elf())
            struct.pack_into("<" + format_, data, offset, value)
            samples.append(bytes(data))
        for index, data in enumerate(samples):
            put(self.root, "bad", data)
            with self.subTest(index=index), self.assertRaises(artifacts.ArtifactError):
                artifacts.capture_file(self.root, "bad", "riscv_elf")

    def test_section_extent_checked_when_table_present(self):
        data = bytearray(elf())
        struct.pack_into("<Q", data, 40, 128)
        struct.pack_into("<HHH", data, 58, 64, 1, 0)
        data.extend(struct.pack("<IIQQQQIIQQ", 0, 1, 0, 0, 1000, 1, 0, 0, 1, 0))
        put(self.root, "bad", bytes(data))
        with self.assertRaises(artifacts.ArtifactError):
            artifacts.capture_file(self.root, "bad", "riscv_elf")


@unittest.skipUnless(shutil.which("git"), "local Git is required for source fixtures")
class SourceCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = source_fixture(self.root)

    def commit_manifest(self):
        put(self.root, "nova/upstream-lock.json", json.dumps(self.manifest))
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "Update synthetic pin fixture")

    def test_complete_snapshot_stable_and_no_absolute_paths(self):
        before = artifacts.capture_source(self.root)
        self.assertTrue(before["clean"])
        self.assertEqual(set(before["lock_hashes"]), artifacts.CONDA_INPUTS)
        self.assertEqual(set(before["source_inputs"]), artifacts.SOURCE_INPUTS)
        self.assertEqual(before["submodules"], [])
        put(self.root, "generated/ignored.v", "ignored build output\n")
        self.assertEqual(artifacts.capture_source(self.root), before)
        self.assertNotIn(str(self.root), json.dumps(before))

    def test_dirty_source_changes_digest_without_claiming_qualification(self):
        before = artifacts.capture_source(self.root)
        put(self.root, "tracked.txt", "modified\n")
        after = artifacts.capture_source(self.root)
        self.assertFalse(after["clean"])
        self.assertNotEqual(after["state_digest"], before["state_digest"])
        self.assertEqual(after["revision"], before["revision"])
        self.assertNotIn("hardware_qualified", after)

    def test_root_index_visibility_flags_rejected_even_before_hidden_edit(self):
        for flag in ("assume-unchanged", "skip-worktree"):
            with self.subTest(flag=flag):
                git(self.root, "update-index", "--" + flag, "tracked.txt")
                try:
                    with self.assertRaisesRegex(artifacts.ArtifactError, "index.*flags"):
                        artifacts.capture_source(self.root)
                    put(self.root, "tracked.txt", "hidden source change\n")
                    self.assertEqual(git(self.root, "status", "--porcelain"), "")
                    with self.assertRaisesRegex(artifacts.ArtifactError, "index.*flags"):
                        artifacts.capture_source(self.root)
                finally:
                    git(self.root, "update-index", "--no-" + flag, "tracked.txt")
                    put(self.root, "tracked.txt", "source\n")
        self.assertTrue(artifacts.capture_source(self.root)["clean"])

    def test_nine_input_hashes_observe_changes(self):
        before = artifacts.capture_source(self.root)
        changed = sorted(artifacts.CONDA_INPUTS)[0]
        put(self.root, changed, "changed locked input\n")
        after = artifacts.capture_source(self.root)
        self.assertFalse(after["clean"])
        self.assertNotEqual(after["lock_hashes"][changed], before["lock_hashes"][changed])

    def test_checkout_identity_diagnostic_not_part_of_source_digest(self):
        before = artifacts.capture_source(self.root)
        with tempfile.TemporaryDirectory() as other:
            destination = Path(other) / "copy"
            shutil.copytree(self.root, destination)
            after = artifacts.capture_source(destination)
        self.assertNotEqual(before["checkout_identity_sha256"], after["checkout_identity_sha256"])
        self.assertEqual(before["state_digest"], after["state_digest"])

    def test_uninitialized_gitlinks_explicit_not_fetched(self):
        pin = "a" * 40
        self.manifest["submodules"] = [{"path": "deps/library", "commit": pin}]
        git(self.root, "update-index", "--add", "--cacheinfo", "160000," + pin + ",deps/library")
        # Do not git add -A here: an absent gitlink is intentionally present in the index.
        (self.root / "deps/library").mkdir(parents=True)
        self.commit_manifest()
        source = artifacts.capture_source(self.root)
        self.assertEqual(source["submodules"], [{"path": "deps/library", "pin": pin,
                         "revision": None, "initialized": False, "clean": None,
                         "state": "uninitialized"}])
        self.assertTrue(source["clean"])
        self.assertFalse((self.root / "deps/library/.git").exists())

    def nested_fixture(self):
        child = self.root / "deps/library"
        nested = child / "deps/nested"
        nested.mkdir(parents=True)
        git(nested, "init", "-q", "-b", "main")
        put(nested, "nested.txt", "nested source\n")
        git(nested, "add", ".")
        git(nested, "commit", "-qm", "Synthetic nested source")
        nested_pin = git(nested, "rev-parse", "HEAD")
        git(child, "init", "-q", "-b", "main")
        put(child, "child.txt", "child source\n")
        git(child, "add", ".")
        git(child, "commit", "-qm", "Synthetic child source")
        pin = git(child, "rev-parse", "HEAD")
        self.manifest["submodules"] = [{"path": "deps/library", "commit": pin}]
        self.commit_manifest()
        return child, nested, nested_pin

    def test_recursive_initialized_gitlinks_and_dirty_nested_state(self):
        _child, nested, nested_pin = self.nested_fixture()
        before = artifacts.capture_source(self.root)
        self.assertEqual([row["path"] for row in before["submodules"]],
                         ["deps/library", "deps/library/deps/nested"])
        self.assertEqual(before["submodules"][1]["pin"], nested_pin)
        self.assertTrue(all(row["state"] == "at_pin" for row in before["submodules"]))
        put(nested, "nested.txt", "changed nested source\n")
        after = artifacts.capture_source(self.root)
        self.assertFalse(after["clean"])
        self.assertEqual(after["submodules"][1]["state"], "dirty")

    def test_index_visibility_flags_rejected_in_child_and_nested_submodules(self):
        child, nested, _pin = self.nested_fixture()
        for directory, filename, original in (
                (child, "child.txt", "child source\n"),
                (nested, "nested.txt", "nested source\n")):
            for flag in ("assume-unchanged", "skip-worktree"):
                with self.subTest(path=filename, flag=flag):
                    git(directory, "update-index", "--" + flag, filename)
                    try:
                        put(directory, filename, "hidden submodule change\n")
                        self.assertEqual(git(directory, "status", "--porcelain"), "")
                        with self.assertRaisesRegex(artifacts.ArtifactError, "index.*flags"):
                            artifacts.capture_source(self.root)
                    finally:
                        git(directory, "update-index", "--no-" + flag, filename)
                        put(directory, filename, original)
        self.assertTrue(artifacts.capture_source(self.root)["clean"])

    def test_invalid_lock_pin_mismatch_and_unsafe_input_rejected(self):
        for mutate in (lambda: self.manifest["preserved_blobs"].pop(sorted(artifacts.CONDA_INPUTS)[0]),
                       lambda: self.manifest["submodules"].append({"path": "../unsafe", "commit": "a" * 40}),
                       lambda: self.manifest["submodules"].append({"path": "missing", "commit": "a" * 40})):
            original = json.loads(json.dumps(self.manifest))
            mutate()
            put(self.root, "nova/upstream-lock.json", json.dumps(self.manifest))
            with self.assertRaises(artifacts.ArtifactError):
                artifacts.capture_source(self.root)
            self.manifest = original

    def test_git_output_limit_enforced_while_reading(self):
        with patch.object(artifacts, "MAX_GIT_BYTES", 8):
            with self.assertRaisesRegex(artifacts.ArtifactError, "output exceeds"):
                artifacts.capture_source(self.root)

    def test_git_policy_disables_fetch_and_hooks(self):
        original = artifacts.subprocess.Popen
        calls = []

        def inspect(argv, **kwargs):
            calls.append((argv, kwargs))
            return original(argv, **kwargs)

        with patch.object(artifacts.subprocess, "Popen", side_effect=inspect):
            artifacts.capture_source(self.root)
        self.assertTrue(calls)
        for argv, kwargs in calls:
            self.assertIn("protocol.allow=never", argv)
            self.assertIn("core.hooksPath=/dev/null", argv)
            self.assertEqual(kwargs["env"]["GIT_NO_LAZY_FETCH"], "1")
            self.assertEqual(kwargs["env"]["GIT_OPTIONAL_LOCKS"], "0")
            self.assertNotIn("shell", kwargs)


class ProfileCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = "NovaM1BaselineConfig"
        self.long_name = "chipyard.harness.TestHarness." + self.config
        self.generated = "sims/verilator/generated-src/" + self.long_name
        self.simulator = "sims/verilator/simulator-chipyard.harness-" + self.config
        put(self.root, self.simulator, elf(machine=62), executable=True)
        put(self.root, self.generated + "/gen-collateral/TestHarness.sv", "module TestHarness; endmodule\n")
        put(self.root, self.generated + "/" + self.long_name + ".dts", "/dts-v1/; / {};\n")
        put(self.root, self.generated + "/top_module_hierarchy.json", '{"name":"TestHarness"}')

    def test_exact_profile_artifacts_retained_without_semantic_claim(self):
        result = artifacts.capture_profile_artifacts(self.root, self.config)
        self.assertEqual(result["status"], "captured")
        self.assertEqual(result["reasons"], [])
        self.assertEqual({row["kind"] for row in result["artifacts"]},
                         {"simulator", "rtl", "device_tree", "metadata"})
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn("address_map_verified", result)

    def test_different_configuration_cannot_reuse_artifacts(self):
        result = artifacts.capture_profile_artifacts(self.root, "RocketConfig")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["artifacts"], [])

    def test_missing_each_category_is_blocked(self):
        paths = [self.generated + "/gen-collateral/TestHarness.sv",
                 self.generated + "/" + self.long_name + ".dts",
                 self.generated + "/top_module_hierarchy.json"]
        for path in paths:
            saved = (self.root / path).read_bytes()
            (self.root / path).unlink()
            result = artifacts.capture_profile_artifacts(self.root, self.config)
            self.assertEqual(result["status"], "blocked")
            self.assertTrue(result["reasons"])
            put(self.root, path, saved)

    def test_json_scalar_duplicates_nonfinite_and_invalid_dts_blocked(self):
        metadata = self.generated + "/top_module_hierarchy.json"
        for text in ('"not metadata"', '{"a":1,"a":2}', '{"a":NaN}', '{', '{}', '[]'):
            put(self.root, metadata, text)
            self.assertEqual(artifacts.capture_profile_artifacts(self.root, self.config)["status"], "blocked")
        put(self.root, metadata, '{"name":"TestHarness"}')
        put(self.root, self.generated + "/" + self.long_name + ".dts", "not a DTS\n")
        self.assertEqual(artifacts.capture_profile_artifacts(self.root, self.config)["status"], "blocked")

    def test_json_numeric_overflow_blocks_actual_metadata_capture(self):
        metadata = self.generated + "/top_module_hierarchy.json"
        for text in ('{"value":1e999}', '{"value":-1e999}',
                     '{"nested":[{"value":1e999}]}', '[1,-1e999]'):
            with self.subTest(text=text):
                with self.assertRaises(artifacts.ArtifactError):
                    artifacts._json(text.encode())
                put(self.root, metadata, text)
                result = artifacts.capture_profile_artifacts(self.root, self.config)
                self.assertEqual(result["status"], "blocked")
                self.assertTrue(result["reasons"])

    def test_finite_json_exponents_remain_supported(self):
        text = '{"values":[1e308,-1e308,1e-308,0.0]}'
        self.assertEqual(artifacts._json(text.encode()),
                         {"values": [1e308, -1e308, 1e-308, 0.0]})
        put(self.root, self.generated + "/top_module_hierarchy.json", text)
        self.assertEqual(artifacts.capture_profile_artifacts(self.root, self.config)["status"], "captured")

    def test_symlink_and_nonregular_entries_blocked(self):
        extra = self.root / self.generated / "extra"
        extra.symlink_to("top_module_hierarchy.json")
        self.assertEqual(artifacts.capture_profile_artifacts(self.root, self.config)["status"], "blocked")
        extra.unlink()
        os.mkfifo(extra)
        self.assertEqual(artifacts.capture_profile_artifacts(self.root, self.config)["status"], "blocked")

    def test_traversal_file_count_and_aggregate_bytes_bounded(self):
        for constant, limit in (("MAX_DIRECTORY_ENTRIES", 2), ("MAX_PROFILE_FILES", 2),
                                 ("MAX_DIRECTORY_DEPTH", 0), ("MAX_PROFILE_BYTES", 128)):
            with self.subTest(limit=constant), patch.object(artifacts, constant, limit):
                result = artifacts.capture_profile_artifacts(self.root, self.config)
                self.assertEqual(result["status"], "blocked")

    def test_unsupported_configurations_are_blocked_with_no_path_leak(self):
        for config in ("../RocketConfig", "/tmp/secret", "OtherConfig", None, []):
            result = artifacts.capture_profile_artifacts(self.root, config)
            self.assertEqual(result["status"], "blocked")
            self.assertNotIn("/tmp/secret", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
