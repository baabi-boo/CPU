"""Compile and run the real recorder as a native fixture, never RTL/CPU evidence.

The fixture's linker hooks supply deterministic host-I/O failures. The recorder
itself contains no test hook. A kernel file-size limit also exercises real failed
writes. No dependency is installed, target compiled, or simulator launched.
"""

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
OBSERVER = ROOT / "software/nova/observer"
DRIVER = ROOT / "tests/nova/fixtures/htif_observer/native_driver.cc"
COMPILER = shutil.which("g++")
FATAL = b"NOVA HTIF observer fatal: witness recording failed\n"
RUN_ID = "0123456789abcdef" * 4
BINDING = "abcdef0123456789" * 4
ENV_KEYS = ("NOVA_HTIF_WITNESS_PATH", "NOVA_HTIF_RUN_ID",
            "NOVA_HTIF_BINDING_SHA256")


@unittest.skipUnless(COMPILER, "native observer fixture requires existing g++; never installed")
class NativeHtifObserverFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="nova-native-observer-build-")
        cls.addClassCleanup(temporary.cleanup)
        cls.build_root = Path(temporary.name).resolve()
        cls.executable = cls.build_root / "native-observer-fixture"
        wrappers = ("openat", "write", "fsync", "fstat", "fchmod", "close")
        # Exercise fortified libc declarations in this same build on Linux.
        # Clear any compiler default first to avoid macro-redefinition warnings.
        fortify = (["-U_FORTIFY_SOURCE", "-D_FORTIFY_SOURCE=2"]
                   if sys.platform.startswith("linux") else [])
        command = [COMPILER, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                   *fortify,
                   "-I", str(OBSERVER), str(OBSERVER / "nova_htif_exit.cc"),
                   str(DRIVER), *(f"-Wl,--wrap={name}" for name in wrappers),
                   "-o", str(cls.executable)]
        result = subprocess.run(
            command, cwd=cls.build_root, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=30, check=False,
            env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C"},
        )
        if result.returncode != 0:
            raise AssertionError("native recorder fixture compilation failed:\n" +
                                 result.stderr.decode("utf-8", errors="replace"))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="nova-native-observer-run-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.witness = self.root / "witness.json"

    def environment(self, path=None, updates=None, remove=()):
        result = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C",
                  "NOVA_HTIF_WITNESS_PATH": str(self.witness if path is None else path),
                  "NOVA_HTIF_RUN_ID": RUN_ID, "NOVA_HTIF_BINDING_SHA256": BINDING}
        result.update(updates or {})
        for key in remove:
            result.pop(key, None)
        return result

    def run_native(self, mode="positive", fault="none", path=None, updates=None, remove=()):
        return subprocess.run(
            [str(self.executable), mode, fault], cwd=self.root,
            stdin=subprocess.DEVNULL, capture_output=True, timeout=5, check=False,
            env=self.environment(path, updates, remove),
        )

    def assert_fatal(self, result):
        self.assertEqual(result.returncode, 125, result.stderr)
        self.assertEqual(result.stderr, FATAL)
        self.assertEqual(result.stdout, b"")

    def assert_witness(self, path=None, *, present=True, raw=1, signal_exit=False):
        path = self.witness if path is None else path
        data = path.read_bytes()
        self.assertTrue(data.endswith(b"\n"))
        self.assertEqual(data.count(b"\n"), 1)
        self.assertLessEqual(len(data), 4096)
        info = path.lstat()
        self.assertTrue(stat.S_ISREG(info.st_mode))
        self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
        self.assertEqual(info.st_nlink, 1)
        self.assertEqual(json.loads(data), {
            "schema_version": 1, "kind": "nova-htif-exit", "run_id": RUN_ID,
            "binding_sha256": BINDING, "target_exit_present": present,
            "raw_exit_code": raw if present else None,
            "target_exit_code": raw >> 1 if present else None,
            "signal_exit": signal_exit,
        })

    def test_native_positive_raw_one_records_target_zero(self):
        result = self.run_native()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        self.assert_witness()

    def test_native_negative_control_raw_fifteen_records_target_seven(self):
        result = self.run_native("negative-control")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        self.assert_witness(raw=15)

    def test_absent_target_records_nulls_without_inventing_zero(self):
        result = self.run_native("absent")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_witness(present=False)

    def test_signal_only_snapshot_preserves_absent_target(self):
        result = self.run_native("signal")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_witness(present=False, signal_exit=True)

    def test_signal_and_target_are_both_retained_for_reader_rejection(self):
        result = self.run_native("target-and-signal")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_witness(signal_exit=True)

    def test_invalid_target_values_are_recorded_faithfully_for_reader_rejection(self):
        for mode, raw in (("raw-zero", 0), ("raw-even", 14), ("raw-negative", -1),
                          ("raw-max", 2147483647), ("raw-min", -2147483648)):
            with self.subTest(mode=mode):
                path = self.root / (mode + ".json")
                result = self.run_native(mode, path=path)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_witness(path, raw=raw)

    def test_each_missing_environment_variable_fails_before_output_creation(self):
        for key in ENV_KEYS:
            with self.subTest(key=key):
                self.assert_fatal(self.run_native(remove=(key,)))
                self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_hex_environment_fails_before_output_creation(self):
        for key in ENV_KEYS[1:]:
            for value in ("", "0" * 63, "0" * 65, "A" * 64, "g" * 64,
                          "0" * 63 + "\n", "\"" * 64, "0" * 4096):
                with self.subTest(key=key, value=value[:70]):
                    self.assert_fatal(self.run_native(updates={key: value}))
                    self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_absolute_path_forms_fail_before_output_creation(self):
        paths = ("", "relative.json", "/", "//witness.json", str(self.root) + "//w.json",
                 str(self.root) + "/./w.json", str(self.root) + "/../w.json",
                 str(self.root) + "/w.json/", "/" + "x" * 4096)
        for path in paths:
            with self.subTest(path=path[:100]):
                self.assert_fatal(self.run_native(path=path))
                self.assertEqual(list(self.root.iterdir()), [])

    def test_missing_parent_is_not_created(self):
        self.assert_fatal(self.run_native(path=self.root / "absent" / "witness.json"))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_regular_file_is_never_overwritten(self):
        for original in (b"", b"pre-existing content\n"):
            with self.subTest(original=original):
                self.witness.write_bytes(original)
                self.assert_fatal(self.run_native())
                self.assertEqual(self.witness.read_bytes(), original)

    def test_existing_hardlinked_output_preserves_both_links(self):
        self.witness.write_bytes(b"existing hardlinked file\n")
        alias = self.root / "alias.json"
        os.link(self.witness, alias)
        self.assert_fatal(self.run_native())
        self.assertEqual(alias.read_bytes(), b"existing hardlinked file\n")
        self.assertEqual(self.witness.stat().st_nlink, 2)

    def test_existing_directory_fifo_and_leaf_symlinks_fail_without_blocking(self):
        directory = self.root / "directory"
        directory.mkdir()
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        original = self.root / "original"
        original.write_bytes(b"must be preserved\n")
        alias = self.root / "alias"
        alias.symlink_to(original)
        dangling = self.root / "dangling"
        dangling.symlink_to(self.root / "not-created")
        for path in (directory, fifo, alias, dangling):
            with self.subTest(path=path.name):
                self.assert_fatal(self.run_native(path=path))
        self.assertEqual(original.read_bytes(), b"must be preserved\n")
        self.assertFalse((self.root / "not-created").exists())
        self.assertTrue(alias.is_symlink())
        self.assertTrue(dangling.is_symlink())

    def test_parent_symlink_is_rejected_without_creating_the_referent(self):
        real = self.root / "real"
        real.mkdir()
        alias = self.root / "parent-alias"
        alias.symlink_to(real, target_is_directory=True)
        self.assert_fatal(self.run_native(path=alias / "witness.json"))
        self.assertEqual(list(real.iterdir()), [])

    def test_regular_file_parent_is_rejected_without_changes(self):
        parent = self.root / "not-a-directory"
        parent.write_bytes(b"parent remains unchanged\n")
        self.assert_fatal(self.run_native(path=parent / "witness.json"))
        self.assertEqual(parent.read_bytes(), b"parent remains unchanged\n")

    def test_second_stop_same_or_different_instance_is_always_host_failure(self):
        for mode in ("duplicate", "second-instance"):
            with self.subTest(mode=mode):
                path = self.root / (mode + ".json")
                self.assert_fatal(self.run_native(mode, path=path))
                # A first event remains immutable; mandatory status 125 forbids
                # accepting the process even when that first event was valid.
                self.assert_witness(path)

    def test_short_writes_and_eintr_are_completed_synchronously(self):
        for fault in ("short-write", "write-eintr"):
            with self.subTest(fault=fault):
                path = self.root / (fault + ".json")
                result = self.run_native(fault=fault, path=path)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_witness(path)

    def test_write_sync_stat_mode_and_close_failures_never_report_success(self):
        faults = ("write-error", "write-zero", "partial-write-error", "fsync-error",
                  "fstat-error", "fchmod-error", "close-error", "close-eintr",
                  "late-mode-change")
        for fault in faults:
            with self.subTest(fault=fault):
                path = self.root / (fault + ".json")
                self.assert_fatal(self.run_native(fault=fault, path=path))
                self.assertFalse(path.exists(), "failed owned witness must be discarded")

    def test_real_kernel_write_failure_invalidates_partial_witness(self):
        self.assert_fatal(self.run_native(fault="kernel-write-error"))
        self.assertFalse(self.witness.exists())

    def test_initial_and_late_multiple_links_are_rejected_and_invalidated(self):
        for fault in ("early-hardlink", "late-hardlink"):
            with self.subTest(fault=fault):
                parent = self.root / fault
                parent.mkdir()
                path = parent / "witness.json"
                self.assert_fatal(self.run_native(fault=fault, path=path))
                self.assertFalse(path.exists())
                self.assertEqual((parent / "native-extra-link").read_bytes(), b"")

    def test_replaced_leaf_is_rejected_without_deleting_foreign_replacement(self):
        self.assert_fatal(self.run_native(fault="replace-leaf"))
        self.assertEqual(self.witness.read_bytes(), b"foreign replacement\n")

    def test_late_parent_symlink_is_rejected_and_owned_output_is_discarded(self):
        parent = self.root / "watched"
        parent.mkdir()
        path = parent / "witness.json"
        self.assert_fatal(self.run_native(fault="replace-parent-with-symlink", path=path))
        self.assertTrue(parent.is_symlink())
        self.assertEqual(list((self.root / "watched.moved").iterdir()), [])

    def test_exact_private_mode_is_preserved_under_restrictive_umask(self):
        result = self.run_native(fault="restrictive-umask")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_witness()

    def test_broken_stderr_cannot_replace_required_fatal_exit_with_sigpipe(self):
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        try:
            result = subprocess.run(
                [str(self.executable), "positive", "none"], cwd=self.root,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=write_fd,
                timeout=5, check=False,
                env=self.environment(remove=("NOVA_HTIF_RUN_ID",)),
            )
        finally:
            os.close(write_fd)
        self.assertEqual(result.returncode, 125)
        self.assertEqual(result.stdout, b"")
        self.assertFalse(self.witness.exists())


if __name__ == "__main__":
    unittest.main()
