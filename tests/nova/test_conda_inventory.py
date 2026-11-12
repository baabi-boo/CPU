"""Offline fixtures for metadata agreement, never package or CPU qualification."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nova_conda_inventory", ROOT / "scripts/nova/conda_inventory.py"
)
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)

HEADER = """version: 1
metadata:
  content_hash:
    linux-64: {digest}
  channels:
  - url: ucb-bar
    used_env_vars: []
  - url: conda-forge
    used_env_vars: []
  - url: litex-hub
    used_env_vars: []
  platforms:
  - linux-64
  sources:
  - ../chipyard-base.yaml
  - ../docs.yaml
  - ../riscv-tools.yaml
package:
""".format(digest="a" * 64)


def package(name="tool", version="1.2.3", build="h123_0"):
    return (f"- name: {name}\n  version: '{version}'\n  manager: conda\n"
            "  platform: linux-64\n  dependencies:\n    __glibc: '>=2.17,<3.0.a0'\n"
            f"  url: https://conda.anaconda.org/conda-forge/linux-64/{name}-{version}-{build}.conda\n"
            f"  hash:\n    md5: {'b' * 32}\n    sha256: {'c' * 64}\n"
            "  category: main\n  optional: false\n")


class CondaInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.lock = self.root / "locked.yml"
        self.lock.write_text(HEADER + package(), encoding="utf-8")
        self.prefix = self.root / "prefix"
        self.meta = self.prefix / "conda-meta"
        self.meta.mkdir(parents=True)
        self.record = inventory.read_lock_packages(self.lock)["tool"]
        self.record_path = self.meta / "tool-1.2.3-h123_0.json"
        self.write_record()

    def write_record(self, record=None, path=None):
        (path or self.record_path).write_text(
            json.dumps(record if record is not None else self.record), encoding="utf-8"
        )

    def inspect(self):
        return inventory.inspect_inventory(self.lock, self.prefix)

    def test_exact_metadata_matches_without_hardware_or_binary_claims(self):
        result = self.inspect()
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["package_count"], 1)
        self.assertEqual(result["matching_package_count"], 1)
        self.assertTrue(result["metadata_only"])
        self.assertFalse(result["installed_binary_contents_verified"])
        self.assertFalse(result["lock_origin_verified"])
        self.assertFalse(result["hardware_qualified"])
        self.assertFalse(result["g1_gate_passed"])
        self.assertEqual(len(result["lock_sha256"]), 64)

    def test_actual_imported_lock_is_supported_and_known_versions_preserved(self):
        packages = inventory.read_lock_packages(inventory.DEFAULT_LOCK)
        self.assertEqual(len(packages), 165)
        self.assertEqual(packages["verilator"]["version"], "5.022")
        self.assertEqual(packages["sysroot_linux-64"]["version"], "2.34")
        self.assertEqual(packages["riscv-tools"]["version"], "1.0.10")
        self.assertNotIn("cmake", packages)

    def test_missing_and_unexpected_packages_block(self):
        self.record_path.unlink()
        result = self.inspect()
        self.assertEqual(result["missing"], ["tool"])
        self.assertEqual(result["status"], "blocked")
        self.write_record()
        extra = dict(self.record, name="extra", url=self.record["url"].replace("tool-", "extra-"))
        self.write_record(extra, self.meta / "extra-1.2.3-h123_0.json")
        result = self.inspect()
        self.assertEqual(result["unexpected"], ["extra"])
        self.assertEqual(result["status"], "blocked")

    def test_identity_and_checksum_mismatches_block(self):
        changes = {"version": "9.0", "build": "other_0", "url":
                   self.record["url"].replace("conda-forge", "ucb-bar"),
                   "md5": "d" * 32, "sha256": "d" * 64}
        for key, value in changes.items():
            with self.subTest(key=key):
                altered = dict(self.record, **{key: value})
                path = self.meta / "{name}-{version}-{build}.json".format(**altered)
                self.record_path.unlink(missing_ok=True)
                self.write_record(altered, path)
                result = self.inspect()
                self.assertEqual(result["status"], "blocked")
                self.assertIn(key, result["mismatched"][0]["fields"])
                path.unlink()
                self.write_record()

    def test_missing_checksum_is_not_assumed_from_the_lock(self):
        for field in ("md5", "sha256", "url", "build", "version", "name"):
            with self.subTest(field=field):
                altered = dict(self.record)
                del altered[field]
                self.write_record(altered)
                self.assertEqual(self.inspect()["status"], "blocked")

    def test_duplicate_lock_names_fields_and_metadata_are_rejected(self):
        cases = [HEADER + package() + package(),
                 (HEADER + package()).replace("  manager: conda", "  manager: conda\n  manager: conda"),
                 (HEADER + package()).replace("metadata:\n", "metadata:\nmetadata:\n"),
                 (HEADER + package()).replace("  hash:\n", "  hash:\n    md5: " + "b" * 32 + "\n")]
        for body in cases:
            with self.subTest(body=body[:80]):
                self.lock.write_text(body, encoding="utf-8")
                with self.assertRaises(inventory.InventoryError):
                    inventory.read_lock_packages(self.lock)

    def test_unsupported_yaml_features_or_platforms_fail_closed(self):
        base = HEADER + package()
        for old, new in (("manager: conda", "manager: pip"),
                         ("platform: linux-64", "platform: linux-aarch64"),
                         ("version: '1.2.3'", "version: &alias 1.2.3"),
                         ("dependencies:\n", "dependencies: *alias\n"),
                         ("optional: false", "optional: true"),
                         ("category: main", "category: dev"),
                         ("    used_env_vars: []", "    used_env_vars: [TOKEN]"),
                         ("version: 1\n", "version: 2\n")):
            with self.subTest(new=new):
                self.lock.write_text(base.replace(old, new), encoding="utf-8")
                with self.assertRaises(inventory.InventoryError):
                    inventory.read_lock_packages(self.lock)

    def test_archive_identity_or_untrusted_url_forms_are_rejected(self):
        for replacement in ("https://user:secret@conda.anaconda.org/", "http://conda.anaconda.org/",
                            "https://other.example/", "https://conda.anaconda.org/../"):
            self.lock.write_text((HEADER + package()).replace(
                "https://conda.anaconda.org/", replacement), encoding="utf-8")
            with self.assertRaises(inventory.InventoryError):
                inventory.read_lock_packages(self.lock)
        self.lock.write_text((HEADER + package()).replace("tool-1.2.3-", "different-1.2.3-"),
                             encoding="utf-8")
        with self.assertRaises(inventory.InventoryError):
            inventory.read_lock_packages(self.lock)

    def test_empty_dependency_map_is_supported_but_duplicate_dependency_is_not(self):
        body = (HEADER + package()).replace("dependencies:\n    __glibc: '>=2.17,<3.0.a0'",
                                             "dependencies: {}")
        self.lock.write_text(body, encoding="utf-8")
        self.assertEqual(len(inventory.read_lock_packages(self.lock)), 1)
        self.lock.write_text((HEADER + package()).replace("    __glibc: '>=2.17,<3.0.a0'",
                             "    __glibc: ''\n    __glibc: ''"), encoding="utf-8")
        with self.assertRaises(inventory.InventoryError):
            inventory.read_lock_packages(self.lock)

    def test_invalid_duplicate_json_and_nonfinite_values_block(self):
        for body in ("{broken", "[]", "{}", '{"name":"a","name":"b"}',
                     json.dumps(self.record)[:-1] + ',"bad":NaN}'):
            with self.subTest(body=body[:50]):
                self.record_path.write_text(body, encoding="utf-8")
                self.assertEqual(self.inspect()["status"], "blocked")

    def test_duplicate_installed_package_name_blocks(self):
        other = dict(self.record, build="other_0")
        self.write_record(other, self.meta / "tool-1.2.3-other_0.json")
        self.assertEqual(self.inspect()["status"], "blocked")

    def test_missing_prefix_does_not_create_directories_or_disclose_paths(self):
        absent = self.root / "private-not-created"
        result = inventory.inspect_inventory(self.lock, absent)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(absent.exists())
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn("private-not-created", json.dumps(result))

    def test_symlink_lock_prefix_metadata_directory_and_record_are_rejected(self):
        link = self.root / "alias.yml"
        link.symlink_to(self.lock)
        with self.assertRaises(inventory.InventoryError):
            inventory.read_lock_packages(link)
        prefix_link = self.root / "prefix-alias"
        prefix_link.symlink_to(self.prefix, target_is_directory=True)
        self.assertEqual(inventory.inspect_inventory(self.lock, prefix_link)["status"], "blocked")
        raw = self.record_path.read_text(encoding="utf-8")
        self.record_path.unlink()
        outside = self.root / "outside.json"
        outside.write_text(raw, encoding="utf-8")
        self.record_path.symlink_to(outside)
        self.assertEqual(self.inspect()["status"], "blocked")
        self.record_path.unlink()
        self.meta.rmdir()
        outside_meta = self.root / "other-meta"
        outside_meta.mkdir()
        self.meta.symlink_to(outside_meta, target_is_directory=True)
        self.assertEqual(self.inspect()["status"], "blocked")

    def test_traversal_inputs_are_rejected_without_resolution(self):
        candidate = self.root / "prefix" / ".." / "locked.yml"
        with self.assertRaises(inventory.InventoryError):
            inventory.read_lock_packages(candidate)

    def test_size_and_count_limits_fail_closed(self):
        with patch.object(inventory, "MAX_LOCK_BYTES", 10):
            self.assertEqual(self.inspect()["status"], "blocked")
        with patch.object(inventory, "MAX_RECORD_BYTES", 10):
            self.assertEqual(self.inspect()["status"], "blocked")
        with patch.object(inventory, "MAX_TOTAL_METADATA_BYTES", 10):
            self.assertEqual(self.inspect()["status"], "blocked")
        with patch.object(inventory, "MAX_PACKAGES", 0):
            self.assertEqual(self.inspect()["status"], "blocked")
        with patch.object(inventory, "MAX_DIRECTORY_ENTRIES", 0):
            self.assertEqual(self.inspect()["status"], "blocked")

    def test_non_utf8_truncated_empty_and_long_line_locks_are_rejected(self):
        for body in (b"\xff\n", (HEADER + package()).encode()[:-1], HEADER.encode(),
                     (HEADER + package()).replace("\n  manager:", "\v  manager:").encode(),
                     (HEADER + "x" * 5000 + "\n").encode()):
            self.lock.write_bytes(body)
            with self.assertRaises(inventory.InventoryError):
                inventory.read_lock_packages(self.lock)

    def test_readonly_plan_and_inventory_cli(self):
        before = self.lock.read_bytes(), self.record_path.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            code = inventory.main(["--json", "--lock", str(self.lock)])
        result = json.loads(stream.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["package_count"], 1)
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            code = inventory.main(["--json", "--lock", str(self.lock), "--prefix", str(self.prefix)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stream.getvalue())["status"], "matched")
        self.assertEqual(before, (self.lock.read_bytes(), self.record_path.read_bytes()))

    def test_blocked_cli_exit_and_text_are_explicit(self):
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            code = inventory.main(["--lock", str(self.lock), "--prefix", str(self.root / "absent")])
        self.assertEqual(code, 2)
        self.assertIn("blocked", stream.getvalue())
        self.assertNotIn(str(self.root), stream.getvalue())


if __name__ == "__main__":
    unittest.main()
