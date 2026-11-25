"""Offline overlay and make-fragment tests; no CPU or RTL execution evidence.

Synthetic fixtures patch the pin constants only inside these unit tests. The
production helper has no CLI/environment path for substituting source hashes.
"""

from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("nova_htif_observer", ROOT / "scripts/nova/htif_observer.py")
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)

SYNTHETIC_HTIF = b'''// Synthetic unit-test input, not upstream execution evidence.
#include "config.h"
#include "htif.h"
#include "rfb.h"
#include "elfloader.h"
#include "platform.h"
#include "byteorder.h"
#include "trap.h"
#include "../riscv/common.h"
#include <getopt.h>

void htif_t::stop()
{
  stopped = true;
}

void htif_t::clear_chunk() {}
'''
SYNTHETIC_OVERLAY = SYNTHETIC_HTIF.replace(
    b'#include "../riscv/common.h"', b'#include "common.h"').replace(
    b"#include <getopt.h>", b'#include <getopt.h>\n#include "nova_htif_exit.h"').replace(
    b"  stopped = true;", b"  stopped = true;\n"
    b"  nova_htif_observe_stop(this, exitcode.has_value(), exitcode.value_or(0), signal_exit);")


def put(root, path, data):
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return destination


def static_archive(data=b"synthetic object", name=b"htif.o/"):
    header = (name.ljust(16) + b"0".ljust(12) + b"0".ljust(6) + b"0".ljust(6)
              + b"100644".ljust(8) + str(len(data)).encode().ljust(10) + b"`\n")
    return b"!<arch>\n" + header + data + (b"\n" if len(data) % 2 else b"")


class ObserverFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.root = self.directory / "repository"
        self.prefix = self.directory / "riscv"
        self.env = {"RISCV": str(self.prefix)}
        self.output = self.root / observer.DEFAULT_OUTPUT_REL
        self.manifest_path = self.output / "manifest.json"
        self.source = put(self.root, observer.SPIKE_REL + "/fesvr/htif.cc", SYNTHETIC_HTIF)
        source_hashes = {}
        for relative in observer.SOURCE_HEADERS:
            data = ("// synthetic pinned header " + relative + "\n").encode()
            put(self.root, observer.SPIKE_REL + "/" + relative, data)
            source_hashes[relative] = hashlib.sha256(data).hexdigest()
        put(self.prefix, "include/fesvr/htif.h",
            (self.root / observer.SPIKE_REL / "fesvr/htif.h").read_bytes())
        put(self.prefix, "include/fesvr/config.h", "// synthetic configured header\n")
        put(self.prefix, "lib/libfesvr.a", static_archive())
        put(self.root, observer.NATIVE_REL, "// synthetic native recorder source\n")
        put(self.root, observer.HEADER_REL,
            "void nova_htif_observe_stop(const void *, bool, int, bool);\n")
        for relative in observer.INPUT_PATHS.values():
            put(self.root, relative, (ROOT / relative).read_bytes())
        for name, value in (
            ("PINNED_HTIF_SHA256", hashlib.sha256(SYNTHETIC_HTIF).hexdigest()),
            ("GENERATED_HTIF_SHA256", hashlib.sha256(SYNTHETIC_OVERLAY).hexdigest()),
            ("SOURCE_HEADERS", source_hashes),
        ):
            replacement = patch.object(observer, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)

    def prepare(self):
        return observer.prepare_observer(self.root, self.output, environ=self.env)

    def read(self, **kwargs):
        return observer.read_manifest(self.manifest_path, root=self.root, environ=self.env, **kwargs)


class OverlayTests(ObserverFixture):
    def test_exact_three_edits_preserve_complete_source_and_notices(self):
        self.assertEqual(observer.render_overlay(SYNTHETIC_HTIF), SYNTHETIC_OVERLAY)
        self.assertEqual(observer.render_overlay(SYNTHETIC_HTIF), observer.render_overlay(SYNTHETIC_HTIF))
        self.assertEqual(SYNTHETIC_OVERLAY.count(b"nova_htif_observe_stop("), 1)
        self.assertTrue(SYNTHETIC_OVERLAY.startswith(SYNTHETIC_HTIF.split(b"\n", 1)[0]))
        self.assertNotIn(b'../riscv/common.h', SYNTHETIC_OVERLAY)

    def test_unpinned_source_never_reaches_transformation(self):
        for source in (SYNTHETIC_HTIF + b"\n", SYNTHETIC_HTIF.decode(), b"", None):
            with self.subTest(source=type(source).__name__), self.assertRaises(observer.ObserverError):
                observer.render_overlay(source)

    def test_ambiguous_anchor_is_rejected_even_under_a_fixture_pin(self):
        data = SYNTHETIC_HTIF + b"#include <getopt.h>\n"
        with patch.object(observer, "PINNED_HTIF_SHA256", hashlib.sha256(data).hexdigest()):
            with self.assertRaisesRegex(observer.ObserverError, "anchor"):
                observer.render_overlay(data)

    def test_read_only_inspection_never_creates_products(self):
        result = observer.inspect_observer(self.root, environ=self.env)
        self.assertTrue(result["ready"], result)
        self.assertEqual(result["blockers"], [])
        self.assertIs(result["hardware_qualified"], False)
        self.assertIs(result["g1_gate_passed"], False)
        self.assertFalse((self.root / "nova-out").exists())

    def test_prepare_retains_hashes_and_does_not_mutate_inputs(self):
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        manifest = self.prepare()
        self.assertEqual((self.output / "htif.cc").read_bytes(), SYNTHETIC_OVERLAY)
        self.assertEqual(manifest["source"]["sha256"], observer.PINNED_HTIF_SHA256)
        self.assertEqual(manifest["generated"]["sha256"], observer.GENERATED_HTIF_SHA256)
        self.assertEqual(set(path.name for path in self.output.iterdir()), {"htif.cc", "manifest.json"})
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual(self.manifest_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.output / "htif.cc").stat().st_mode & 0o777, 0o600)
        self.assertEqual(manifest, self.read())
        self.assertEqual(manifest, observer.read_manifest(self.manifest_path, environ=self.env))

    def test_manifests_and_metadata_are_relocatable_and_deterministic(self):
        other_root = self.directory / "second-repository"
        other_prefix = self.directory / "second-prefix"
        shutil.copytree(self.root, other_root)
        shutil.copytree(self.prefix, other_prefix)
        first = self.prepare()
        second_output = other_root / observer.DEFAULT_OUTPUT_REL
        second = observer.prepare_observer(other_root, second_output, environ={"RISCV": str(other_prefix)})
        self.assertEqual(first, second)
        self.assertEqual(self.manifest_path.read_bytes(), (second_output / "manifest.json").read_bytes())
        metadata = observer.build_metadata(self.manifest_path, root=self.root, environ=self.env)
        other = observer.build_metadata(second_output / "manifest.json", root=other_root,
                                        environ={"RISCV": str(other_prefix)})
        self.assertEqual(metadata, other)
        self.assertNotIn(str(self.directory), json.dumps(metadata))

    def test_fresh_descendant_is_supported_but_existing_output_is_never_reused(self):
        self.output = self.output / "attempt-1"
        self.manifest_path = self.output / "manifest.json"
        self.prepare()
        before = self.manifest_path.read_bytes()
        with self.assertRaisesRegex(observer.ObserverError, "already exists"):
            self.prepare()
        self.assertEqual(self.manifest_path.read_bytes(), before)

    def test_existing_empty_output_is_also_refused(self):
        self.output.mkdir(parents=True)
        with self.assertRaisesRegex(observer.ObserverError, "already exists"):
            self.prepare()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_output_escape_traversal_and_symlink_ancestors_are_refused(self):
        for path in (self.directory / "outside", self.root / "nova-out/elsewhere",
                     str(self.output) + "/../escape", str(self.output) + " with-space"):
            with self.subTest(path=path), self.assertRaises(observer.ObserverError):
                observer.prepare_observer(self.root, path, environ=self.env)
        outside = self.directory / "outside"
        outside.mkdir()
        (self.root / "nova-out").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(observer.ObserverError):
            self.prepare()
        self.assertEqual(list(outside.iterdir()), [])

    def test_missing_riscv_and_unpinned_source_are_blockers_without_outputs(self):
        self.assertFalse(observer.inspect_observer(self.root, environ={})["ready"])
        self.source.write_bytes(SYNTHETIC_HTIF + b"// changed\n")
        result = observer.inspect_observer(self.root, environ=self.env)
        self.assertFalse(result["ready"])
        self.assertIn("SHA256", result["blockers"][0])
        with self.assertRaises(observer.ObserverError):
            self.prepare()
        self.assertFalse((self.root / "nova-out").exists())

    def test_static_archive_is_mandatory_with_no_shared_fallback(self):
        archive = self.prefix / "lib/libfesvr.a"
        archive.unlink()
        put(self.prefix, "lib/libfesvr.so", b"\x7fELFsynthetic shared library")
        self.assertFalse(observer.inspect_observer(self.root, environ=self.env)["ready"])
        for bad in (b"!<thin>\n", b"\x7fELFshared", b"!<arch>\n", static_archive()[:-4]):
            archive.write_bytes(bad)
            with self.subTest(data=bad[:8]), self.assertRaises(observer.ObserverError):
                self.prepare()

    def test_installed_config_compatibility_and_source_closure_are_required(self):
        candidates = [self.prefix / "include/fesvr/config.h",
                      self.prefix / "include/fesvr/htif.h",
                      self.root / observer.SPIKE_REL / "riscv/encoding.h"]
        for path in candidates:
            data = path.read_bytes()
            path.unlink()
            self.assertFalse(observer.inspect_observer(self.root, environ=self.env)["ready"])
            path.write_bytes(data)
        (self.prefix / "include/fesvr/htif.h").write_text("// incompatible header\n")
        self.assertFalse(observer.inspect_observer(self.root, environ=self.env)["ready"])

    def test_symlink_fifo_empty_and_oversized_inputs_are_rejected(self):
        native = self.root / observer.NATIVE_REL
        original = native.read_bytes()
        native.unlink()
        native.symlink_to(self.source)
        self.assertFalse(observer.inspect_observer(self.root, environ=self.env)["ready"])
        native.unlink()
        os.mkfifo(native)
        self.assertFalse(observer.inspect_observer(self.root, environ=self.env)["ready"])
        native.unlink()
        native.write_bytes(b"")
        self.assertFalse(observer.inspect_observer(self.root, environ=self.env)["ready"])
        native.write_bytes(original)
        with patch.object(observer, "MAX_ARCHIVE_BYTES", 8):
            self.assertFalse(observer.inspect_observer(self.root, environ=self.env)["ready"])

    def test_quote_include_shadows_are_rejected(self):
        for relative in ("fesvr/config.h", "fesvr/common.h", "riscv/nova_htif_exit.h"):
            shadow = put(self.root, observer.SPIKE_REL + "/" + relative, "// wrong include\n")
            self.assertFalse(observer.inspect_observer(self.root, environ=self.env)["ready"])
            shadow.unlink()

    def test_cli_prepare_verify_and_blocked_inspection(self):
        with patch.dict(os.environ, self.env, clear=True), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(observer.main(["--prepare", "--root", str(self.root), "--output", str(self.output)]), 0)
        self.assertEqual(json.loads(output.getvalue())["source_pin"], observer.PINNED_SPIKE_COMMIT)
        with patch.dict(os.environ, self.env, clear=True), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(observer.main(["--verify", "--root", str(self.root)]), 0)
        self.assertEqual(json.loads(output.getvalue())["kind"], "nova-htif-observer")
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(observer.main(["--inspect", "--root", str(self.root)]), 2)
        self.assertFalse(json.loads(output.getvalue())["ready"])
        with patch.dict(os.environ, self.env, clear=True), redirect_stderr(io.StringIO()) as error:
            self.assertEqual(observer.main(["--prepare", "--root", str(self.root)]), 2)
        self.assertIn("fresh directory", error.getvalue())


class ManifestTests(ObserverFixture):
    def test_revalidation_detects_each_bound_input_changed_after_preparation(self):
        self.prepare()
        candidates = [self.source, self.root / observer.NATIVE_REL, self.root / observer.HEADER_REL,
                      self.root / observer.MAKE_REL, self.prefix / "include/fesvr/config.h",
                      self.prefix / "lib/libfesvr.a", self.output / "htif.cc"]
        for path in candidates:
            data = path.read_bytes()
            path.write_bytes(data + b"\n")
            with self.subTest(path=path.name), self.assertRaises(observer.ObserverError):
                self.read()
            path.write_bytes(data)

    def test_manifest_rejects_duplicate_keys_boolean_integers_and_unexpected_fields(self):
        manifest = self.prepare()
        raw = self.manifest_path.read_bytes()
        bad_values = []
        for key, value in (("schema_version", True), ("hardware_qualified", 0),
                           ("g1_gate_passed", True), ("source_pin", "0" * 40),
                           ("extra", "ignored?")):
            bad = copy.deepcopy(manifest)
            bad[key] = value
            bad_values.append(json.dumps(bad).encode())
        bad_values += [b'{"schema_version":1,' + raw[1:], b"{\"a\":NaN}",
                       b"[" * 2000 + b"]" * 2000, b"\xff", b"{" * (observer.MAX_MANIFEST_BYTES + 1)]
        for data in bad_values:
            self.manifest_path.write_bytes(data)
            with self.subTest(data=data[:40]), self.assertRaises(observer.ObserverError):
                self.read()

    def test_manifest_symlink_and_unexpected_output_are_rejected(self):
        self.prepare()
        data = self.manifest_path.read_bytes()
        self.manifest_path.unlink()
        actual = put(self.root, "retained.json", data)
        self.manifest_path.symlink_to(actual)
        with self.assertRaises(observer.ObserverError):
            self.read()
        self.manifest_path.unlink()
        self.manifest_path.write_bytes(data)
        put(self.output, "config.h", "// shadow\n")
        with self.assertRaises(observer.ObserverError):
            self.read()

    def test_pure_metadata_validator_reads_no_files_and_refuses_contradictions(self):
        self.prepare()
        metadata = observer.build_metadata(self.manifest_path, root=self.root, environ=self.env)
        with patch.object(observer.os, "open", side_effect=AssertionError("must not read files")):
            self.assertEqual(observer.validate_build_metadata(metadata), metadata)
        mutations = [
            lambda item: item.update(schema_version=True),
            lambda item: item.update(hardware_qualified=0),
            lambda item: item.update(manifest_bytes=True),
            lambda item: item.update(manifest_path="nova-out/htif-observer/../escape/manifest.json"),
            lambda item: item.update(manifest_sha256="g" * 64),
            lambda item: item["source"].update(sha256="0" * 64),
            lambda item: item["generated"].update(sha256="0" * 64),
            lambda item: item["archive"].update(path="lib/libfesvr.so"),
            lambda item: item["native"].update(size_bytes=True),
            lambda item: item["inputs"].pop("make_fragment"),
            lambda item: item["source_headers"].clear(),
        ]
        for mutate in mutations:
            changed = copy.deepcopy(metadata)
            mutate(changed)
            with self.assertRaises(observer.ObserverError):
                observer.validate_build_metadata(changed)

    def test_metadata_only_read_does_not_authorize_missing_inputs(self):
        manifest = self.prepare()
        (self.prefix / "lib/libfesvr.a").unlink()
        self.assertEqual(self.read(verify_files=False), manifest)
        with self.assertRaises(observer.ObserverError):
            observer.build_metadata(self.manifest_path, root=self.root, environ=self.env)


@unittest.skipUnless(shutil.which("make"), "host make is unavailable; no installation attempted")
class MakeFragmentTests(ObserverFixture):
    def make_probe(self, *arguments):
        upstream = put(self.root, "probe.mk", "\n".join([
            "base_dir := " + str(self.root),
            "sim_dir := " + str(self.root / "sim"),
            "dramsim_dir := " + str(self.root / "dram"),
            "GEN_COLLATERAL_DIR := " + str(self.root / "generated"),
            "model_mk := model.mk", "model_mk_debug := debug.mk",
            "sim := simulation", "sim_debug := simulation-debug",
            "EXTRA_SIM_SOURCES := upstream.cc", "EXTRA_SIM_CXXFLAGS := -DNOVA_UPSTREAM=1",
            "EXTRA_SIM_LDFLAGS := -lpthread",
            "include " + str(self.root / "sims/common-sim-flags.mk"),
            ".PHONY: show", "show:",
            '\t@printf "CXX=%s\\n" "$(SIM_CXXFLAGS)"',
            '\t@printf "LD=%s\\n" "$(SIM_LDFLAGS)"',
            '\t@printf "SRC=%s\\n" "$(EXTRA_SIM_SOURCES)"', "",
        ]))
        return subprocess.run(
            ["make", "--no-print-directory", "-s", "-f", str(upstream), "-f",
             str(ROOT / observer.MAKE_REL), "show", *arguments], cwd=self.root,
            env={"PATH": os.environ.get("PATH", os.defpath), "RISCV": str(self.prefix), "LC_ALL": "C"},
            capture_output=True, text=True, timeout=10, check=False)

    def test_fragment_preserves_flags_and_static_archive_position(self):
        result = self.make_probe("SIM_LDFLAGS=-lfesvr")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = dict(line.split("=", 1) for line in result.stdout.splitlines())
        flags = shlex.split(rows["LD"])
        self.assertEqual(flags, ["-L" + str(self.prefix / "lib"),
                                "-Wl,-rpath," + str(self.prefix / "lib"),
                                "-L" + str(self.root / "sim"), "-L" + str(self.root / "dram"),
                                "-lriscv", str(self.prefix / "lib/libfesvr.a"), "-ldramsim", "-lpthread"])
        self.assertNotIn("-lfesvr", flags)
        self.assertEqual(shlex.split(rows["SRC"]), ["upstream.cc", str(self.output / "htif.cc"),
                                                   str(self.root / observer.NATIVE_REL)])
        cxx = shlex.split(rows["CXX"])
        self.assertIn("-DNOVA_UPSTREAM=1", cxx)
        self.assertIn('-DPREFIX="' + str(self.prefix) + '"', cxx)
        self.assertEqual(cxx.count("-iquote"), len(observer.INCLUDE_DIRECTORIES))

    def test_hidden_fesvr_or_source_override_is_rejected(self):
        for arguments in (("EXTRA_SIM_LDFLAGS=-lfesvr",), ("LDFLAGS=/tmp/libfesvr.so",),
                          ("EXTRA_SIM_SOURCES=unobserved.cc",), ("EXTRA_SIM_CXXFLAGS=-I/untrusted",)):
            result = self.make_probe(*arguments)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("NOVA observer", result.stderr)

    @unittest.skipUnless(shutil.which("g++"), "host g++ unavailable; no installation attempted")
    def test_prefix_survives_verilator_and_generated_make_shell_stages(self):
        result = self.make_probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = dict(line.split("=", 1) for line in result.stdout.splitlines())
        flags = shlex.split(rows["CXX"])
        source = put(self.root, "prefix.cc", '#include <cstring>\nint main(int n, char **v) {\n'
                     '  return n != 2 || std::strcmp(PREFIX, v[1]);\n}\n')
        program = self.root / "prefix-probe"
        built = subprocess.run([shutil.which("g++"), *flags, str(source), "-o", str(program)],
                               capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(built.returncode, 0, built.stderr)
        ran = subprocess.run([str(program), str(self.prefix)], capture_output=True, timeout=5, check=False)
        self.assertEqual(ran.returncode, 0, ran.stderr)


if __name__ == "__main__":
    unittest.main()
