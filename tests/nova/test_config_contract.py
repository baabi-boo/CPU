"""Pinned source-contract assertions only; no Scala/HDL compilation or execution.

These deliberately small bootstrap contracts must be reviewed when a profile is
extended. They do not infer generated hart IDs, ISA features, or hardware health.
"""

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "generators/chipyard/src/main/scala/config"
PARENTS = {
    "NovaM1BaselineConfig": "RocketConfig",
    "NovaM1MinimalConfig": "LargeBoomAndRocketConfig",
}


def source(name):
    text = (CONFIG_DIR / name).read_text(encoding="utf-8")
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.DOTALL)


def compact(text):
    return re.sub(r"\s+", "", text)


def class_body(text, name):
    """Select a known, simple top-level configuration, not arbitrary Scala."""
    body = text.split(f"class {name} extends Config(", 1)[1]
    return body.split("\nclass ", 1)[0]


class ConfigurationContractTests(unittest.TestCase):
    def setUp(self):
        self.nova = source("NovaM1Configs.scala")
        self.project = json.loads((ROOT / "nova/project.json").read_text(encoding="utf-8"))

    def test_package_and_config_import_remain_explicit(self):
        lines = [line.strip() for line in self.nova.splitlines() if line.strip()]
        self.assertEqual(lines[:2], ["package chipyard", "import org.chipsalliance.cde.config.Config"])
        self.assertEqual(sum(line.startswith("import ") for line in lines), 1)

    def test_profile_metadata_matches_the_two_declared_derivatives(self):
        actual = {item["name"]: item["upstream"] for item in self.project["configurations"]}
        self.assertEqual(actual, PARENTS)
        declarations = re.findall(r"(?m)^class (\w+) extends Config\(", self.nova)
        self.assertEqual(declarations, list(PARENTS))

    def test_nova_profiles_add_no_core_or_accelerator_mixins(self):
        expected = "package chipyard\nimport org.chipsalliance.cde.config.Config\n"
        expected += "\n".join(
            f"class {name} extends Config(new {parent})" for name, parent in PARENTS.items())
        self.assertEqual(compact(self.nova), compact(expected))

    def test_rocket_reference_is_one_inherited_huge_core(self):
        body = class_body(source("RocketConfigs.scala"), "RocketConfig")
        self.assertEqual(compact(body), compact("""
            new freechips.rocketchip.rocket.WithNHugeCores(1) ++
            new chipyard.config.AbstractConfig)
        """))

    def test_mixed_reference_keeps_boom_v3_one_rocket_and_128_bit_bus(self):
        body = class_body(source("HeteroConfigs.scala"), "LargeBoomAndRocketConfig")
        self.assertEqual(compact(body), compact("""
            new boom.v3.common.WithNLargeBooms(1) ++
            new freechips.rocketchip.rocket.WithNHugeCores(1) ++
            new chipyard.config.WithSystemBusWidth(128) ++
            new chipyard.config.AbstractConfig)
        """))

    def test_bootstrap_profiles_are_explicitly_unverified(self):
        self.assertEqual(len(self.project["configurations"]), 2)
        for profile in self.project["configurations"]:
            with self.subTest(profile=profile["name"]):
                self.assertEqual(profile["status"], "implemented_unverified")
                self.assertFalse(profile.get("evidence"))


if __name__ == "__main__":
    unittest.main()
