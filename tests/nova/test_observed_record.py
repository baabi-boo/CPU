"""Pure synthetic schema-extension checks; never CPU or native execution evidence.

The invented records below provide only the context needed by the extension.
They are not full campaign records and cannot satisfy the core comparator.
Pinned source hashes are labels in these fixtures, not claims to retained files.
"""

import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nova_observed_record_test", ROOT / "scripts/nova/observed_record.py")
observed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observed)
observer = observed._observer


def digest(label):
    return hashlib.sha256(("SYNTHETIC ONLY: " + label).encode()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def synthetic_metadata():
    def identity(scope, path, sha256=None):
        return {"scope": scope, "path": path, "sha256": sha256 or digest(path), "size_bytes": 128}

    manifest = {
        "schema_version": 1, "kind": "nova-htif-observer-build",
        "output_directory": observer.DEFAULT_OUTPUT_REL,
        "source_pin": observer.PINNED_SPIKE_COMMIT,
        "source": identity("repository", observer.SPIKE_REL + "/fesvr/htif.cc", observer.PINNED_HTIF_SHA256),
        "generated": identity("repository", observer.DEFAULT_OUTPUT_REL + "/htif.cc", observer.GENERATED_HTIF_SHA256),
        "native": identity("repository", observer.NATIVE_REL),
        "header": identity("repository", observer.HEADER_REL),
        "archive": identity("riscv", "lib/libfesvr.a"),
        "installed_header": identity("riscv", "include/fesvr/htif.h", observer.SOURCE_HEADERS["fesvr/htif.h"]),
        "installed_config": identity("riscv", "include/fesvr/config.h"),
        "source_headers": {name: identity("repository", observer.SPIKE_REL + "/" + name, sha256)
                           for name, sha256 in observer.SOURCE_HEADERS.items()},
        "inputs": {name: identity("repository", path, observer.SIM_FLAGS_SHA256
                                  if name == "upstream_sim_flags" else None)
                   for name, path in observer.INPUT_PATHS.items()},
        "include_directories": [{"scope": scope, "path": path}
                                for scope, path in observer.INCLUDE_DIRECTORIES],
        "link_order": "overlay-object-before-static-fesvr", "hardware_qualified": False,
        "g1_gate_passed": False,
    }
    data = canonical(manifest)
    return {
        "schema_version": 1, "kind": "nova-htif-observer",
        "manifest_path": observer.DEFAULT_OUTPUT_REL + "/manifest.json",
        "manifest_sha256": hashlib.sha256(data).hexdigest(), "manifest_bytes": len(data),
        **{key: manifest[key] for key in observer.METADATA_COPY_KEYS},
    }


def retain_event(row, raw=None):
    extension = row["target_exit"]
    event = extension["assessment"]["event"]
    data = canonical(event) + b"\n" if raw is None else raw
    sha256 = hashlib.sha256(data).hexdigest()
    extension["witness"].update(sha256=sha256, size_bytes=len(data))
    extension["assessment"].update(witness_sha256=sha256, witness_bytes=len(data))


def rebind(row):
    extension = row["target_exit"]
    event = extension["assessment"]["event"]
    event["run_id"] = extension["binding"]["run_id"]
    event["binding_sha256"] = hashlib.sha256(canonical(extension["binding"])).hexdigest()
    retain_event(row)


def synthetic_record(attempt="first"):
    metadata = synthetic_metadata()
    source = {"revision": "1" * 40, "tree": "2" * 40, "state_digest": digest("source state")}
    resources = {"max_cycles": 10000000, "seed": 1}
    profiles = []
    for config in observed.CONFIGURATIONS:
        simulator = digest(config + " simulator")
        rows = []
        for identifier in observed.WORKLOAD_IDS:
            expected = 7 if identifier == "nova-baseline-fail" else 0
            binary = digest(identifier + " ELF")
            binding = {
                "schema_version": 1, "configuration": config, "workload_id": identifier,
                "run_id": digest(attempt + config + identifier), "binary_sha256": binary,
                "simulator_sha256": simulator, "observer_manifest_sha256": metadata["manifest_sha256"],
                "source_revision": source["revision"], "source_tree": source["tree"],
                "source_state_digest": source["state_digest"], **resources,
            }
            event = {
                "schema_version": 1, "kind": "nova-htif-exit", "run_id": binding["run_id"],
                "binding_sha256": hashlib.sha256(canonical(binding)).hexdigest(),
                "target_exit_present": True, "raw_exit_code": (expected << 1) | 1,
                "target_exit_code": expected, "signal_exit": False,
            }
            row = {
                "id": identifier, "binary": {"sha256": binary}, "simulator_sha256": simulator,
                "assessment": {"target_completion_verified": False, "hardware_qualified": False,
                               "g1_gate_passed": False},
                "target_exit": {
                    "witness": {"path": config + "-" + identifier + ".htif-exit.json",
                                "kind": "htif_exit_witness", "sha256": "", "size_bytes": 0},
                    "binding": binding,
                    "assessment": {
                        "status": "observed", "target_exit_observed": True,
                        "target_completion_verified": True, "hardware_qualified": False,
                        "g1_gate_passed": False, "reasons": [], "witness_sha256": "",
                        "witness_bytes": 0, "event": event,
                    },
                },
            }
            retain_event(row)
            rows.append(row)
        profiles.append({
            "configuration": config,
            "artifacts": {"artifacts": [{
                "kind": "simulator", "path": "sims/verilator/simulator-chipyard.harness-" + config,
                "sha256": simulator,
            }]},
            "workloads": rows,
        })
    return {
        "schema_version": 2, "kind": "nova-g1-campaign", "status": "workloads_observed",
        "hardware_qualified": False, "g1_gate_passed": False,
        "target_exit_observer": metadata, "source_before": source, "source_after": copy.deepcopy(source),
        "resource_limits": resources, "profiles": profiles,
    }


def rows(record):
    return [row for profile in record["profiles"] for row in profile["workloads"]]


class ObservedRecordTests(unittest.TestCase):
    def setUp(self):
        self.record = synthetic_record()

    def assert_rejected(self, record, text=None):
        reasons = observed.validate_extension(record)
        self.assertTrue(reasons)
        self.assertTrue(all(type(reason) is str and reason for reason in reasons))
        self.assertLessEqual(len(reasons), observed.MAX_REASONS)
        if text:
            self.assertTrue(any(text in reason for reason in reasons), reasons)
        self.assertEqual(observed.comparison_view(record), {})
        self.assertEqual(observed.run_ids(record), set())

    def test_complete_synthetic_extension_has_30_distinct_runs_and_expected_exits(self):
        self.assertEqual(observed.validate_extension(self.record), [])
        self.assertEqual(len(observed.run_ids(self.record)), 30)
        for row in rows(self.record):
            expected = 7 if row["id"] == "nova-baseline-fail" else 0
            event = row["target_exit"]["assessment"]["event"]
            self.assertEqual(event["target_exit_code"], expected)
            self.assertEqual(event["raw_exit_code"], 15 if expected else 1)
            self.assertIs(row["assessment"]["target_completion_verified"], False)

    def test_pure_validation_delegates_metadata_without_reading_files(self):
        with patch.object(observer, "validate_build_metadata", wraps=observer.validate_build_metadata) as validate:
            with patch("builtins.open", side_effect=AssertionError("unexpected file read")):
                with patch("os.open", side_effect=AssertionError("unexpected file read")):
                    self.assertEqual(observed.validate_extension(self.record), [])
            validate.assert_called_once_with(self.record["target_exit_observer"])

    def test_schema_and_record_status_cannot_be_coerced_or_upgraded(self):
        for value in (1, True, 2.0, "2", None):
            with self.subTest(schema=value):
                record = copy.deepcopy(self.record)
                record["schema_version"] = value
                self.assert_rejected(record, "schema-2")
        for key, value in (("status", "failed"), ("status", "blocked"), ("kind", "another-record")):
            with self.subTest(key=key, value=value):
                record = copy.deepcopy(self.record)
                record[key] = value
                self.assert_rejected(record, "workloads_observed")

    def test_pending_observer_or_row_cannot_be_compared(self):
        record = copy.deepcopy(self.record)
        record["target_exit_observer"] = None
        self.assert_rejected(record, "metadata")
        for extension in ({"status": "not_run"}, None,
                          {"witness": None, "binding": {}, "assessment": None}):
            with self.subTest(extension=extension):
                record = copy.deepcopy(self.record)
                rows(record)[0]["target_exit"] = extension
                self.assert_rejected(record)

    def test_metadata_missing_extra_and_invalid_pinned_identities_fail(self):
        changes = (
            ("schema_version", True), ("manifest_bytes", True), ("manifest_sha256", "A" * 64),
            ("manifest_bytes", 1),
            ("manifest_bytes", self.record["target_exit_observer"]["manifest_bytes"] - 1),
            ("manifest_path", "../manifest.json"), ("source_pin", "0" * 40),
            ("link_order", "shared-fesvr-first"), ("unreviewed", False),
        )
        for key, value in changes:
            with self.subTest(key=key):
                record = copy.deepcopy(self.record)
                record["target_exit_observer"][key] = value
                self.assert_rejected(record, "metadata")
        for key in self.record["target_exit_observer"]:
            with self.subTest(missing=key):
                record = copy.deepcopy(self.record)
                del record["target_exit_observer"][key]
                self.assert_rejected(record, "metadata")
        for key in ("source", "generated", "installed_header"):
            with self.subTest(pin=key):
                record = copy.deepcopy(self.record)
                record["target_exit_observer"][key]["sha256"] = digest("wrong pin")
                self.assert_rejected(record, "metadata")

    def test_every_extension_object_has_an_exact_shape(self):
        paths = ((), ("witness",), ("binding",), ("assessment",), ("assessment", "event"))
        for path in paths:
            for extra in (False, True):
                with self.subTest(path=path, extra=extra):
                    record = copy.deepcopy(self.record)
                    value = rows(record)[0]["target_exit"]
                    for key in path:
                        value = value[key]
                    if extra:
                        value["unsupported"] = False
                    else:
                        del value[next(iter(value))]
                    self.assert_rejected(record)

    def test_event_fields_have_exact_scalar_types_and_terminal_semantics(self):
        changes = {
            "schema_version": (True, 1.0, "1", None),
            "kind": ("not-htif-exit", [], None),
            "target_exit_present": (False, 1, "true", None),
            "signal_exit": (True, 0, "false", None),
            "raw_exit_code": (True, 1.0, "1", -1, 0, 2, 15, 2147483649, None),
            "target_exit_code": (False, 0.0, "0", -1, 7, None),
            "run_id": ("A" * 64, "f" * 63, digest("different run"), None),
            "binding_sha256": ("A" * 64, digest("different binding"), None),
        }
        for key, values in changes.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    record = copy.deepcopy(self.record)
                    rows(record)[0]["target_exit"]["assessment"]["event"][key] = value
                    self.assert_rejected(record)

    def test_negative_control_requires_raw15_and_decoded7(self):
        for raw, decoded in ((1, 0), (15, 0), (1, 7), (14, 7), (15.0, 7), (15, 7.0)):
            with self.subTest(raw=raw, decoded=decoded):
                record = copy.deepcopy(self.record)
                event = rows(record)[2]["target_exit"]["assessment"]["event"]
                event.update(raw_exit_code=raw, target_exit_code=decoded)
                self.assert_rejected(record, "expected target exit")

    def test_matching_witness_cannot_upgrade_ordinary_assessment(self):
        for value in (True, 0, None):
            with self.subTest(value=value):
                record = copy.deepcopy(self.record)
                rows(record)[0]["assessment"]["target_completion_verified"] = value
                self.assert_rejected(record, "protocol-only")

    def test_assessment_claims_status_reasons_and_types_are_exact(self):
        changes = {
            "status": ("passed", "failed", None), "target_exit_observed": (False, 1, None),
            "target_completion_verified": (False, 1, None), "hardware_qualified": (True, 0),
            "g1_gate_passed": (True, 0), "reasons": (["failure"], None, {}),
            "witness_sha256": (None, "A" * 64, digest("wrong hash")),
            "witness_bytes": (True, 0, 4097, 300.0), "event": (None, [], {}),
        }
        for key, values in changes.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    record = copy.deepcopy(self.record)
                    rows(record)[0]["target_exit"]["assessment"][key] = value
                    self.assert_rejected(record)

    def test_witness_identity_has_fixed_filename_and_bounded_hash_and_size(self):
        changes = {
            "path": ("arbitrary.json", "../escape", "/absolute", "nested/file", None, []),
            "kind": ("stdout", None), "sha256": (None, "A" * 64, "f" * 63, observed.EMPTY_SHA256),
            "size_bytes": (True, 0, -1, 4097, 300.0, None),
        }
        for key, values in changes.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    record = copy.deepcopy(self.record)
                    rows(record)[0]["target_exit"]["witness"][key] = value
                    self.assert_rejected(record, "witness")

    def test_witness_hash_and_bytes_must_match_the_nested_assessment(self):
        for key, value in (("sha256", digest("different raw bytes")), ("size_bytes", 4096)):
            with self.subTest(key=key):
                record = copy.deepcopy(self.record)
                rows(record)[0]["target_exit"]["witness"][key] = value
                self.assert_rejected(record, "not bound")

    def test_impossible_short_witness_is_rejected_even_when_byte_counts_agree(self):
        row = rows(self.record)[0]
        row["target_exit"]["witness"]["size_bytes"] = 1
        row["target_exit"]["assessment"]["witness_bytes"] = 1
        self.assert_rejected(self.record, "too short")

    def test_raw_bytes_are_not_reconstructed_or_authenticated(self):
        # The retained JSON omits raw bytes. Matching hashes only establish
        # agreement between its supplied fields, not genuine witness contents.
        row = rows(self.record)[0]
        invented = digest("unavailable raw witness bytes")
        row["target_exit"]["witness"]["sha256"] = invented
        row["target_exit"]["assessment"]["witness_sha256"] = invented
        self.assertEqual(observed.validate_extension(self.record), [])

    def test_binding_is_row_bound_even_after_a_self_consistent_rehash(self):
        replacements = {
            "schema_version": True, "configuration": "NovaM1BaselineConfig", "workload_id": "nova-baseline",
            "binary_sha256": digest("other ELF"), "simulator_sha256": digest("other simulator"),
            "observer_manifest_sha256": digest("other observer"), "source_revision": "3" * 40,
            "source_tree": "4" * 40, "source_state_digest": digest("other state"),
            "max_cycles": 1, "seed": 2,
        }
        for key, value in replacements.items():
            with self.subTest(key=key):
                record = copy.deepcopy(self.record)
                row = rows(record)[0]
                row["target_exit"]["binding"][key] = value
                rebind(row)
                self.assert_rejected(record, "binding differs")

    def test_binding_numeric_bool_and_float_aliases_are_rejected(self):
        for key, values in (("schema_version", (True, 1.0)), ("max_cycles", (True, 10000000.0)),
                            ("seed", (True, 1.0))):
            for value in values:
                with self.subTest(key=key, value=value):
                    record = copy.deepcopy(self.record)
                    row = rows(record)[0]
                    row["target_exit"]["binding"][key] = value
                    rebind(row)
                    self.assert_rejected(record, "binding differs")

    def test_canonical_binding_digest_is_required(self):
        row = rows(self.record)[0]
        pretty = json.dumps(row["target_exit"]["binding"], sort_keys=True, indent=2).encode()
        row["target_exit"]["assessment"]["event"]["binding_sha256"] = hashlib.sha256(pretty).hexdigest()
        retain_event(row)
        self.assert_rejected(self.record, "canonical binding SHA256")

    def test_binding_run_id_is_strict_hex64(self):
        for value in (None, True, 123, "A" * 64, "a" * 63, "a" * 65):
            with self.subTest(value=value):
                record = copy.deepcopy(self.record)
                row = rows(record)[0]
                row["target_exit"]["binding"]["run_id"] = value
                rebind(row)
                self.assert_rejected(record, "run ID")

    def test_source_drift_and_missing_source_context_fail(self):
        for key in ("revision", "tree", "state_digest"):
            for snapshot in ("source_before", "source_after"):
                with self.subTest(key=key, snapshot=snapshot):
                    record = copy.deepcopy(self.record)
                    record[snapshot][key] = "9" * (64 if key == "state_digest" else 40)
                    self.assert_rejected(record, "source")
        for snapshot in ("source_before", "source_after"):
            for value in (None, [], {}):
                with self.subTest(snapshot=snapshot, value=value):
                    record = copy.deepcopy(self.record)
                    record[snapshot] = value
                    self.assert_rejected(record, "source")

    def test_resources_are_bounded_and_bound_to_each_event(self):
        for key, values in (("max_cycles", (True, 10000000.0, 0, 10000001, 1)),
                            ("seed", (True, 1.0, 0, 2147483648, 2))):
            for value in values:
                with self.subTest(key=key, value=value):
                    record = copy.deepcopy(self.record)
                    record["resource_limits"][key] = value
                    self.assert_rejected(record)

    def test_changed_manifest_identity_invalidates_existing_row_bindings(self):
        self.record["target_exit_observer"]["manifest_sha256"] = digest("another manifest")
        self.assert_rejected(self.record, "binding differs")

    def test_elf_and_simulator_are_bound_to_row_and_captured_profile(self):
        record = copy.deepcopy(self.record)
        rows(record)[0]["binary"]["sha256"] = digest("another ELF")
        self.assert_rejected(record, "binding differs")
        for value in (None, {}, {"sha256": 123}):
            with self.subTest(binary=value):
                record = copy.deepcopy(self.record)
                rows(record)[0]["binary"] = value
                self.assert_rejected(record, "ELF")
        record = copy.deepcopy(self.record)
        rows(record)[0]["simulator_sha256"] = digest("another simulator")
        self.assert_rejected(record, "simulator")
        for key, value in (("sha256", digest("changed captured simulator")), ("path", "different/path")):
            with self.subTest(capture=key):
                record = copy.deepcopy(self.record)
                record["profiles"][0]["artifacts"]["artifacts"][0][key] = value
                self.assert_rejected(record, "simulator")
        record = copy.deepcopy(self.record)
        record["profiles"][0]["artifacts"]["artifacts"] *= 2
        self.assert_rejected(record, "one captured simulator")

    def test_ordered_configuration_and_workload_inventories_are_complete(self):
        for change in ("reverse profiles", "missing profile", "duplicate profile", "bad profile",
                       "reverse rows", "missing row", "duplicate row", "bad row"):
            with self.subTest(change=change):
                record = copy.deepcopy(self.record)
                profiles = record["profiles"]
                workloads = profiles[0]["workloads"]
                if change == "reverse profiles":
                    profiles.reverse()
                elif change == "missing profile":
                    profiles.pop()
                elif change == "duplicate profile":
                    profiles[1] = profiles[0]
                elif change == "bad profile":
                    profiles[0] = []
                elif change == "reverse rows":
                    workloads.reverse()
                elif change == "missing row":
                    workloads.pop()
                elif change == "duplicate row":
                    workloads[1] = workloads[0]
                else:
                    workloads[0] = None
                self.assert_rejected(record, "ordered")

    def test_run_ids_cannot_repeat_within_or_across_profiles(self):
        for index in (1, 15):
            with self.subTest(index=index):
                record = copy.deepcopy(self.record)
                first, later = rows(record)[0], rows(record)[index]
                later["target_exit"]["binding"]["run_id"] = first["target_exit"]["binding"]["run_id"]
                rebind(later)
                self.assert_rejected(record, "run ID is reused")

    def test_witness_filename_reuse_is_rejected(self):
        first, later = rows(self.record)[:2]
        later["target_exit"]["witness"]["path"] = first["target_exit"]["witness"]["path"]
        self.assert_rejected(self.record, "filename is reused")

    def test_completion_claim_exception_has_an_exact_path(self):
        paths = ((), ("target_exit_observer",), ("source_before",), ("resource_limits",))
        for path in paths:
            with self.subTest(path=path):
                record = copy.deepcopy(self.record)
                target = record
                for key in path:
                    target = target[key]
                target["target_completion_verified"] = True
                self.assert_rejected(record, "outside its exact observer assessment")
        record = copy.deepcopy(self.record)
        record["untrusted"] = {"target_exit": {"assessment": {"target_completion_verified": True}}}
        self.assert_rejected(record, "outside its exact observer assessment")

    def test_hardware_and_gate_claims_are_false_everywhere(self):
        for flag in ("hardware_qualified", "g1_gate_passed"):
            for value in (True, 0, 0.0, None):
                with self.subTest(flag=flag, value=value):
                    record = copy.deepcopy(self.record)
                    record["untrusted"] = [{flag: value}]
                    self.assert_rejected(record, "qualification")
            record = copy.deepcopy(self.record)
            del record[flag]
            self.assert_rejected(record, "flags must remain false")

    def test_projection_ignores_fresh_nonces_and_different_valid_raw_encoding(self):
        second = synthetic_record("second")
        for row in rows(second):
            event = row["target_exit"]["assessment"]["event"]
            retain_event(row, json.dumps(event, indent=2).encode() + b"\n")
        self.assertEqual(observed.validate_extension(second), [])
        self.assertTrue(observed.run_ids(self.record).isdisjoint(observed.run_ids(second)))
        self.assertEqual(observed.comparison_view(self.record), observed.comparison_view(second))
        encoded = json.dumps(observed.comparison_view(self.record))
        for row in rows(self.record):
            self.assertNotIn(row["target_exit"]["binding"]["run_id"], encoded)
            self.assertNotIn(row["target_exit"]["assessment"]["event"]["binding_sha256"], encoded)
            self.assertNotIn(row["target_exit"]["witness"]["sha256"], encoded)
        self.assertNotIn("witness_bytes", encoded)
        self.assertNotIn("htif-exit.json", encoded)

    def test_projection_preserves_stable_observer_metadata_and_semantics(self):
        first_view = observed.comparison_view(self.record)
        for profile in first_view["profiles"]:
            self.assertEqual([row["id"] for row in profile["workloads"]], list(observed.WORKLOAD_IDS))
            negative = profile["workloads"][2]["target_exit"]
            self.assertEqual(negative["event"]["raw_exit_code"], 15)
            self.assertEqual(negative["event"]["target_exit_code"], 7)
            self.assertIs(negative["assessment"]["target_completion_verified"], True)
        self.record["target_exit_observer"]["manifest_sha256"] = digest("new stable observer")
        for row in rows(self.record):
            row["target_exit"]["binding"]["observer_manifest_sha256"] = self.record["target_exit_observer"]["manifest_sha256"]
            rebind(row)
        self.assertEqual(observed.validate_extension(self.record), [])
        self.assertNotEqual(first_view, observed.comparison_view(self.record))

    def test_witness_upper_bound_allows_valid_whitespace_without_comparing_raw_bytes(self):
        baseline = observed.comparison_view(self.record)
        row = rows(self.record)[0]
        event = canonical(row["target_exit"]["assessment"]["event"])
        retain_event(row, event + b" " * (4095 - len(event)) + b"\n")
        self.assertEqual(observed.validate_extension(self.record), [])
        self.assertEqual(observed.comparison_view(self.record), baseline)

    def test_public_helpers_do_not_mutate_or_alias_the_input(self):
        original = copy.deepcopy(self.record)
        self.assertEqual(observed.validate_extension(self.record), [])
        view = observed.comparison_view(self.record)
        identities = observed.run_ids(self.record)
        view["target_exit_observer"]["native"]["sha256"] = digest("mutated view")
        view["profiles"][0]["workloads"][0]["target_exit"]["assessment"]["reasons"].append("mutated view")
        identities.clear()
        self.assertEqual(self.record, original)

    def test_corrupt_non_json_deep_cyclic_and_oversized_inputs_return_reasons(self):
        cycle = {}
        cycle["again"] = cycle
        deep = value = {}
        for _ in range(40):
            value["nested"] = {}
            value = value["nested"]
        corrupt = (None, True, 2, "record", [], {}, {1: "non-string key"}, {"bad": b"bytes"},
                   {"bad": ()}, {"bad": {1, 2}}, {"bad": complex(1, 2)}, {"bad": object()},
                   {"bad": math.nan}, {"bad": math.inf}, {"bad": -math.inf}, {"bad": 1 << 8192},
                   cycle, deep, [None] * (observed.MAX_JSON_NODES + 1),
                   {"large": "x" * (observed.MAX_RECORD_BYTES + 1)})
        for index, record in enumerate(corrupt):
            with self.subTest(index=index):
                self.assert_rejected(record)

    def test_corruption_of_nested_shapes_is_bounded_and_fail_closed(self):
        paths = (
            ("source_before",), ("resource_limits",), ("profiles",),
            ("profiles", 0, "artifacts"), ("profiles", 0, "artifacts", "artifacts"),
            ("profiles", 0, "workloads"), ("profiles", 0, "workloads", 0, "assessment"),
            ("profiles", 0, "workloads", 0, "target_exit"),
            ("profiles", 0, "workloads", 0, "target_exit", "binding"),
            ("profiles", 0, "workloads", 0, "target_exit", "witness"),
        )
        for path in paths:
            for replacement in (None, True, 0, 1.0, "invalid", [], {}):
                with self.subTest(path=path, replacement=replacement):
                    record = copy.deepcopy(self.record)
                    target = record
                    for key in path[:-1]:
                        target = target[key]
                    target[path[-1]] = replacement
                    self.assert_rejected(record)

    def test_reason_count_is_bounded_even_before_profile_validation(self):
        self.record["untrusted"] = [{"hardware_qualified": True} for _ in range(100)]
        self.record["profiles"] = None
        self.assert_rejected(self.record)


if __name__ == "__main__":
    unittest.main()
