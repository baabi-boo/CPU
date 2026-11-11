"""Imported toolchain provenance contracts; offline and not hardware validation."""

import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("nova_provenance_check", ROOT / "scripts/nova/check.py")
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)

# Captured with git ls-tree at the imported revision, not derived from the lock
# under test. Fixed expectations keep this contract usable in shallow CI clones.
BASELINE = "a7946ede9bd625204435715dc40c750e2f8a251f"
ORIGINAL_BLOBS = {
    "README.chipyard.md": "84e845f14dbf18da23eb4802d0b737f5f0984fb0",
    "docs/nova/upstream/CONTRIBUTING.chipyard.md": "4b602be7b861cc23df3e518080f9d4e554c77a45",
    "LICENSE": "251d54f64481ee8dafed7c356f513227d15c4d5c",
    "LICENSE.SiFive": "7e709337548a437d5ac680af73c15c1a38a28d0e",
}
TOOLCHAIN_BLOBS = {
    "conda-reqs/chipyard-base.yaml": "b9cf66700eb4042b4a911f252286910f54c8b902",
    "conda-reqs/chipyard-extended.yaml": "1c608edbb2f5d5e40cc84405ea533acf3f942b0e",
    "conda-reqs/circt.json": "020fe373a3071bc848c089d9e4e764c31b632a59",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-64-lean.conda-lock.yml": "ef614ffa71068d7b73ae15ad961fd367841e8d67",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-64.conda-lock.yml": "9c964035fe7db0ea8d2d5da3e8bb5850f5793d38",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-aarch64-lean.conda-lock.yml": "1ec7ba3cb523c2392d3618fd64cc9fd5219857b1",
    "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-aarch64.conda-lock.yml": "2c507c7f366ded5a41da772d1921de8b7366fd5e",
    "conda-reqs/docs.yaml": "995864a6a4c7805cac0bb51f9f14cf6b7e322166",
    "conda-reqs/riscv-tools.yaml": "6e1a95593f1bd5c91442ea2fab8d4e973ff0ccf2",
}


class ProvenanceContractTests(unittest.TestCase):
    def setUp(self):
        self.lock = check.load_json(ROOT / "nova/upstream-lock.json")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in self.lock["preserved_blobs"]:
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / name).read_bytes())
        self.gitlinks = {item["path"]: item["commit"] for item in self.lock["submodules"]}

    def test_manifest_hashes_match_the_imported_baseline(self):
        self.assertEqual(self.lock["upstream"]["commit"], BASELINE)
        for name, expected in {**ORIGINAL_BLOBS, **TOOLCHAIN_BLOBS}.items():
            with self.subTest(path=name):
                self.assertEqual(self.lock["preserved_blobs"].get(name), expected)

    def test_toolchain_contents_match_the_imported_baseline(self):
        self.assertEqual(len(TOOLCHAIN_BLOBS), 9)
        for name, expected in TOOLCHAIN_BLOBS.items():
            with self.subTest(path=name):
                self.assertEqual(check.git_blob_sha((ROOT / name).read_bytes()), expected)

    def test_all_imported_toolchain_paths_are_mandatory(self):
        self.assertTrue(set(TOOLCHAIN_BLOBS).issubset(check.PRESERVED))
        self.assertTrue(set(ORIGINAL_BLOBS).issubset(check.PRESERVED))

    def test_unmodified_fixture_passes_provenance_validation(self):
        self.assertEqual(len(self.gitlinks), 57)
        self.assertEqual(check.validate_upstream(self.lock, self.root, self.gitlinks), [])

    def test_omitting_each_toolchain_hash_fails(self):
        for name in TOOLCHAIN_BLOBS:
            with self.subTest(path=name):
                candidate = copy.deepcopy(self.lock)
                del candidate["preserved_blobs"][name]
                self.assertEqual(check.validate_upstream(candidate, self.root, self.gitlinks),
                                 ["upstream: required preserved blobs missing"])

    def test_changing_each_toolchain_file_fails(self):
        for name in TOOLCHAIN_BLOBS:
            with self.subTest(path=name):
                path = self.root / name
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"\nsetup-generated drift\n")
                    self.assertEqual(check.validate_upstream(self.lock, self.root, self.gitlinks),
                                     [f"upstream: preserved blob changed: {name}"])
                finally:
                    path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
