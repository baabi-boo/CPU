"""Bounded record-path capture regressions; no campaign or hardware is run."""

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nova_record_reader_paths_test", ROOT / "scripts/nova/compare_campaigns.py")
compare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compare)


@unittest.skipUnless(os.name == "posix" and all(hasattr(os, flag) for flag in
                    ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC")),
                    "requires no-follow directory support")
class RecordReaderPathTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="nova-record-reader-paths-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "retained"
        self.directory.mkdir()
        self.path = self.directory / "record.json"
        self.path.write_bytes(b'{"inside":true}')

    def assert_closed(self, descriptors):
        self.assertTrue(descriptors)
        for descriptor in descriptors:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_relative_pathlike_and_json_value_types_remain_supported(self):
        class RecordPath:
            def __fspath__(inner):
                return str(self.path)

        for value in ({"inside": True}, [1, None], "text", False, 3):
            with self.subTest(value=value):
                self.path.write_text(json.dumps(value), encoding="utf-8")
                self.assertEqual(compare.read_record(RecordPath()), value)
                previous = os.getcwd()
                try:
                    os.chdir(self.directory)
                    self.assertEqual(compare.read_record(self.path.name), value)
                finally:
                    os.chdir(previous)
        for value in (None, 1, True, b"record.json"):
            with self.subTest(invalid_path=value), self.assertRaises(compare.RecordError):
                compare.read_record(value)
        with self.assertRaises(compare.RecordError):
            compare.read_record(self.directory / ".." / "retained" / self.path.name)

    def test_parent_swap_cannot_open_an_external_record(self):
        outside = self.root / "outside"
        outside.mkdir()
        outside_path = outside / self.path.name
        outside_path.write_bytes(b'{"outside":true}')
        outside_info = outside_path.stat()
        parked = self.root / "original"
        original_stat, original_open = os.stat, os.open
        original_is_symlink = Path.is_symlink

        for replacement in ("symlink", "directory"):
            with self.subTest(replacement=replacement):
                swapped, external_opens, opened, symlink_checks = [], [], [], []

                def check_symlink(candidate):
                    symlink_checks.append(True)
                    try:
                        return original_is_symlink(candidate)
                    finally:
                        symlink_checks.pop()

                def swap_before_leaf_stat(candidate, *args, **kwargs):
                    if candidate in (self.path, self.path.name) and not swapped and not symlink_checks:
                        self.directory.rename(parked)
                        if replacement == "symlink":
                            self.directory.symlink_to(outside, target_is_directory=True)
                        else:
                            outside.rename(self.directory)
                        swapped.append(True)
                    return original_stat(candidate, *args, **kwargs)

                def track_open(candidate, flags, *args, **kwargs):
                    descriptor = original_open(candidate, flags, *args, **kwargs)
                    opened.append(descriptor)
                    info = os.fstat(descriptor)
                    if (info.st_dev, info.st_ino) == (outside_info.st_dev, outside_info.st_ino):
                        external_opens.append(descriptor)
                    return descriptor

                try:
                    with patch.object(Path, "is_symlink", side_effect=check_symlink, autospec=True), \
                         patch.object(compare.os, "stat", side_effect=swap_before_leaf_stat), \
                         patch.object(compare.os, "open", side_effect=track_open):
                        with self.assertRaises(compare.RecordError):
                            compare.read_record(self.path)
                    self.assertEqual(swapped, [True])
                    self.assertEqual(external_opens, [])
                    self.assert_closed(opened)
                finally:
                    if swapped:
                        if replacement == "symlink":
                            self.directory.unlink()
                        else:
                            self.directory.rename(outside)
                        parked.rename(self.directory)

    def test_directory_swap_before_component_open_is_not_followed(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / self.path.name).write_bytes(b'{"outside":true}')
        parked = self.root / "original"
        original_open = os.open
        swapped, opened, leaf_opens = [], [], []

        def swap_before_open(candidate, flags, *args, **kwargs):
            if candidate == self.directory.name and flags & os.O_DIRECTORY and not swapped:
                self.directory.rename(parked)
                self.directory.symlink_to(outside, target_is_directory=True)
                swapped.append(True)
            descriptor = original_open(candidate, flags, *args, **kwargs)
            opened.append(descriptor)
            if candidate in (self.path, self.path.name):
                leaf_opens.append(descriptor)
            return descriptor

        with patch.object(compare.os, "open", side_effect=swap_before_open):
            with self.assertRaises(compare.RecordError):
                compare.read_record(self.path)
        self.assertEqual(swapped, [True])
        self.assertEqual(leaf_opens, [])
        self.assert_closed(opened)

    def test_leaf_swap_is_rejected_before_reading_symlink_fifo_or_replacement(self):
        outside = self.root / "outside.json"
        outside.write_bytes(b'{"outside":true}')
        parked = self.directory / "original.json"
        original_open = os.open

        for replacement in ("symlink", "fifo", "regular"):
            with self.subTest(replacement=replacement):
                swapped, opened = [], []

                def swap_before_open(candidate, flags, *args, **kwargs):
                    if candidate in (self.path, self.path.name) and not swapped:
                        self.path.rename(parked)
                        if replacement == "symlink":
                            self.path.symlink_to(outside)
                        elif replacement == "fifo":
                            self.assertTrue(flags & os.O_NONBLOCK)
                            os.mkfifo(self.path)
                        else:
                            self.path.write_bytes(b'{"outside":true}')
                        swapped.append(True)
                    descriptor = original_open(candidate, flags, *args, **kwargs)
                    opened.append(descriptor)
                    return descriptor

                try:
                    with patch.object(compare.os, "open", side_effect=swap_before_open), \
                         patch.object(compare.os, "read", side_effect=AssertionError("unsafe read")) as reader:
                        with self.assertRaises(compare.RecordError):
                            compare.read_record(self.path)
                    self.assertEqual(swapped, [True])
                    reader.assert_not_called()
                    self.assert_closed(opened)
                finally:
                    if swapped:
                        self.path.unlink()
                        parked.rename(self.path)

    def test_leaf_replacement_during_read_is_rejected(self):
        original_read = os.read
        replaced = []

        def replace_after_read(descriptor, size):
            data = original_read(descriptor, size)
            if not replaced:
                self.path.rename(self.directory / "original.json")
                self.path.write_bytes(data)
                replaced.append(True)
            return data

        with patch.object(compare.os, "read", side_effect=replace_after_read):
            with self.assertRaises(compare.RecordError):
                compare.read_record(self.path)
        self.assertEqual(replaced, [True])

    def test_growth_cannot_exceed_the_bounded_read(self):
        original_read = os.read
        reads = []
        limit = 32

        def grow_before_read(descriptor, size):
            if not reads:
                with self.path.open("ab") as stream:
                    stream.write(b" " * (limit + 20))
            data = original_read(descriptor, size)
            reads.append((size, len(data)))
            return data

        with patch.object(compare, "MAX_RECORD_BYTES", limit), \
             patch.object(compare.os, "read", side_effect=grow_before_read):
            with self.assertRaises(compare.RecordError):
                compare.read_record(self.path)
        self.assertEqual(reads, [(limit + 1, limit + 1)])

    def test_short_reads_are_accumulated(self):
        original_read = os.read
        with patch.object(compare.os, "read", side_effect=lambda fd, size: original_read(fd, min(size, 2))):
            self.assertEqual(compare.read_record(self.path), {"inside": True})

    def test_descriptors_close_after_success_parse_io_and_interrupt_failures(self):
        original_open, original_read, original_close = os.open, os.read, os.close
        for failure in (None, "parse", "walk", "leaf", "read", "final_walk", "interrupt",
                        "walk_close", "leaf_close"):
            with self.subTest(failure=failure):
                self.path.write_bytes(b"{" if failure == "parse" else b'{"inside":true}')
                opened, directory_walks, leaves, close_errors = [], [], [], []

                def track_open(candidate, flags, *args, **kwargs):
                    if candidate == self.directory.name and flags & os.O_DIRECTORY:
                        directory_walks.append(True)
                        if failure == "walk" or failure == "final_walk" and len(directory_walks) == 2:
                            raise OSError("synthetic directory open failure")
                    if failure == "leaf" and candidate in (self.path, self.path.name):
                        raise OSError("synthetic leaf open failure")
                    descriptor = original_open(candidate, flags, *args, **kwargs)
                    opened.append(descriptor)
                    if candidate in (self.path, self.path.name):
                        leaves.append(descriptor)
                    return descriptor

                def fail_read(descriptor, size):
                    if failure == "read":
                        raise OSError("synthetic read failure")
                    if failure == "interrupt":
                        raise KeyboardInterrupt()
                    return original_read(descriptor, size)

                def fail_close(descriptor):
                    original_close(descriptor)
                    if not close_errors and (failure == "walk_close" or
                                             failure == "leaf_close" and descriptor in leaves):
                        close_errors.append(True)
                        raise OSError("synthetic completed close failure")

                with patch.object(compare.os, "open", side_effect=track_open), \
                     patch.object(compare.os, "read", side_effect=fail_read), \
                     patch.object(compare.os, "close", side_effect=fail_close):
                    if failure is None:
                        self.assertEqual(compare.read_record(self.path), {"inside": True})
                    else:
                        expected = KeyboardInterrupt if failure == "interrupt" else compare.RecordError
                        with self.assertRaises(expected):
                            compare.read_record(self.path)
                if failure in ("walk_close", "leaf_close"):
                    self.assertEqual(close_errors, [True])
                self.assert_closed(opened)


if __name__ == "__main__":
    unittest.main()
