#!/usr/bin/env python3
"""Read-only G1/Chisel-6 prerequisite profile; never a build or gate pass.

``ready`` means only that the enumerated local checks succeeded. It does not
qualify nested source closure, installed package identity, JVM dependencies,
actual linking, target execution, or compatibility of the complete toolchain.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess


DEFAULT_ROOT = Path(__file__).resolve().parents[2]
PROFILE = "g1-chisel6-rocket"
MAX_INPUT_BYTES = 1024 * 1024
MAX_COLLATERAL_BYTES = 256 * 1024 * 1024
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
PINNED_VERSIONS = {"verilator": "5.022", "firtool": "1.75.0"}
REQUIRED_SOURCE_GITLINKS = frozenset({
    "generators/bar-fetchers", "generators/boom", "generators/constellation",
    "generators/diplomacy", "generators/hardfloat", "generators/icenet",
    "generators/pmu", "generators/rerocc", "generators/rocket-chip",
    "generators/rocket-chip-blocks", "generators/rocket-chip-inclusive-cache",
    "generators/shuttle", "generators/testchipip", "sims/firesim",
    "toolchains/libgloss", "tools/DRAMSim2", "tools/cde", "tools/dsptools",
    "tools/firrtl2", "tools/fixedpoint", "tools/rocket-dsp-utils",
})
PROVISIONING_SOURCE_GITLINKS = frozenset({
    "toolchains/riscv-tools/riscv-isa-sim", "toolchains/riscv-tools/riscv-tests",
    "tools/install-circt",
})
OPTIONAL_GENERATORS = frozenset({
    "ara", "caliptra-aes-acc", "compress-acc", "cva6", "fft-generator",
    "gemmini", "ibex", "mempress", "nvdla", "radiance", "riscv-sodor",
    "saturn", "tacit", "vexiiriscv",
})
SOURCE_INPUT_PATHS = frozenset({
    "build.sbt", "project/build.properties", "project/plugins.sbt", "variables.mk",
    "common.mk", "sims/verilator/Makefile", "sims/common-sim-flags.mk",
    "generators/chipyard/src/main/scala/config/NovaM1Configs.scala",
})
CONDA_LOCK = "conda-reqs/conda-lock-reqs/conda-requirements-riscv-tools-linux-64-lean.conda-lock.yml"
CIRCT_INPUT = "conda-reqs/circt.json"
TOOLS = {
    "java": ["-version"], "verilator": ["--version"],
    "firtool": ["--version"], "make": ["--version"],
    "cmake": ["--version"], "gcc": ["--version"], "g++": ["--version"],
    "ar": ["--version"], "jq": ["--version"], "dtc": ["--version"],
    "riscv64-unknown-elf-gcc": ["--version"],
    "riscv64-unknown-elf-g++": ["--version"],
    "riscv64-unknown-elf-objdump": ["--version"],
    "riscv64-unknown-elf-readelf": ["--version"], "spike": ["--version"],
}
COLLATERAL = {
    "fesvr_header": ["include/fesvr/htif.h"],
    "riscv_header": ["include/riscv/processor.h"],
    "fesvr_library": ["lib/libfesvr.a", "lib/libfesvr.so"],
    "riscv_library": ["lib/libriscv.a", "lib/libriscv.so"],
}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _relative(value):
    return (isinstance(value, str) and bool(value)
            and re.fullmatch(r"[A-Za-z0-9_./-]+", value) is not None
            and not PurePosixPath(value).is_absolute()
            and all(part not in {"", ".", ".."} for part in value.split("/")))


def _read(root, relative, limit=MAX_INPUT_BYTES):
    if not _relative(relative):
        raise ValueError("invalid source path")
    path = root / relative
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or not stat.S_ISREG(resolved.stat().st_mode):
        raise ValueError("source is not a contained regular file")
    if resolved.stat().st_size > limit:
        raise ValueError("source exceeds size limit")
    with resolved.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("source exceeds size limit")
    return data


def _json(root, relative):
    return json.loads(_read(root, relative), object_pairs_hook=_unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def _probe(argv, root, env):
    # No shell, environment sourcing, setup commands, remote requests or lazy
    # Git fetches. Version probes do not inherit arbitrary JAVA_TOOL_OPTIONS.
    process_env = {"PATH": env.get("PATH", os.defpath), "LC_ALL": "C",
                   "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1"}
    for name in ("LD_LIBRARY_PATH", "JAVA_HOME"):
        if isinstance(env.get(name), str):
            process_env[name] = env[name]
    try:
        result = subprocess.run(argv, cwd=root, env=process_env, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=5, check=False)
        if len(result.stdout) + len(result.stderr) > MAX_INPUT_BYTES:
            return None
        if result.returncode != 0:
            return None
        return (result.stdout + result.stderr).decode("utf-8", errors="replace")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _git(root, env, *args):
    return _probe(["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
                   "-c", "core.untrackedCache=false", "-C", str(root), *args], root, env)


def _validate_profile(profile):
    if not isinstance(profile, dict) or type(profile.get("schema_version")) is not int:
        raise ValueError("invalid profile schema")
    if (profile["schema_version"] != 1 or profile.get("profile") != PROFILE
            or profile.get("chisel_mode") != "default-6"
            or profile.get("configurations") != ["RocketConfig", "NovaM1BaselineConfig"]
            or profile.get("pin_source") != "nova/upstream-lock.json"
            or profile.get("closure_qualified") is not False
            or profile.get("expected_tool_versions") != PINNED_VERSIONS
            or profile.get("expected_initialized_optional_generators") != []):
        raise ValueError("unsupported G1 profile contract")
    for field, expected in (("required_source_gitlinks", REQUIRED_SOURCE_GITLINKS),
                            ("provisioning_source_gitlinks", PROVISIONING_SOURCE_GITLINKS),
                            ("optional_generators", OPTIONAL_GENERATORS)):
        values = profile.get(field)
        if (not isinstance(values, list) or len(values) != len(expected)
                or not all(_relative(path) for path in values)
                or set(values) != expected):
            raise ValueError("invalid source-role inventory")
    inputs = profile.get("source_inputs_sha256")
    if (not isinstance(inputs, dict) or set(inputs) != SOURCE_INPUT_PATHS
            or any(not _relative(path) or not isinstance(digest, str)
                   or not SHA256.fullmatch(digest) for path, digest in inputs.items())):
        raise ValueError("invalid source-input inventory")
    if profile.get("conda_lock") != CONDA_LOCK or profile.get("circt_input") != CIRCT_INPUT:
        raise ValueError("invalid toolchain-input paths")


def _gitlink_index(output):
    if output is None or (output and not output.endswith("\0")):
        raise ValueError("unreadable or truncated gitlink index")
    result = {}
    for entry in output.split("\0"):
        if not entry:
            continue
        header, separator, path = entry.partition("\t")
        fields = header.split()
        if not separator or len(fields) != 3:
            raise ValueError("malformed index")
        if fields[0] != "160000":
            continue
        if not _relative(path) or not SHA1.fullmatch(fields[1]) or path in result or fields[2] != "0":
            raise ValueError("invalid or conflicted gitlink")
        result[path] = fields[1]
    return result


def _source_state(root, path, pin, index, env):
    if index.get(path) != pin:
        return "index_pin_mismatch"
    target = root / path
    try:
        target = target.resolve(strict=True)
        if not target.is_relative_to(root) or not target.is_dir():
            return "invalid_path"
        if not (target / ".git").exists():
            return "uninitialized"
        top = _git(target, env, "rev-parse", "--show-toplevel")
        if top is None or Path(top.strip()).resolve() != target:
            return "invalid_repository"
        head = _git(target, env, "rev-parse", "HEAD")
        if head is None or head.strip() != pin:
            return "checkout_pin_mismatch"
        dirty = _git(target, env, "status", "--porcelain=v1", "-z",
                     "--untracked-files=normal", "--ignore-submodules=none")
        return "unreadable" if dirty is None else "dirty" if dirty else "at_pin"
    except (OSError, ValueError, RuntimeError):
        return "unreadable"


def _version(name, output):
    if not isinstance(output, str):
        return None
    if name == "verilator":
        match = re.search(r"\bVerilator\s+(\d+\.\d+(?:\.\d+)?)\b", output)
    elif name == "firtool":
        match = re.search(r"\bfirtool(?:-|\s+(?:version\s+)?)(\d+\.\d+\.\d+)\b", output)
    else:
        # Return only a numeric version, never arbitrary diagnostic/environment
        # text or paths which a tool could emit alongside its version.
        lines = [line for line in output.splitlines() if not line.startswith(("Picked up ", "NOTE: Picked up "))]
        match = re.search(r"\b(\d+\.\d+(?:\.\d+){0,2})\b", "\n".join(lines))
    return match.group(1)[:32] if match else None


def _tool(name, args, root, env):
    executable = shutil.which(name, path=env.get("PATH", os.defpath))
    output = _probe([executable, *args], root, env) if executable else None
    observed = _version(name, output)
    expected = PINNED_VERSIONS.get(name)
    return {"name": name, "available": output is not None,
            "observed_version": observed, "expected_version": expected,
            "version_matches": (observed == expected) if expected else None,
            "identity_verified": False}


def _collateral(prefix, paths):
    for path in paths:
        try:
            if not _relative(path):
                continue
            resolved = (prefix / path).resolve(strict=True)
            before = resolved.stat()
            if (not resolved.is_relative_to(prefix) or not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= MAX_COLLATERAL_BYTES):
                continue
            digest = hashlib.sha256()
            size = 0
            with resolved.open("rb") as stream:
                for block in iter(lambda: stream.read(65536), b""):
                    size += len(block)
                    if size > MAX_COLLATERAL_BYTES:
                        raise ValueError("collateral grew beyond size limit")
                    digest.update(block)
            after = resolved.stat()
            if (size != before.st_size or after.st_size != before.st_size
                    or after.st_mtime_ns != before.st_mtime_ns
                    or (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)):
                continue
            return {"available": True, "path": path, "bytes": size,
                    "sha256": digest.hexdigest()}
        except (OSError, ValueError, RuntimeError):
            pass
    return {"available": False, "path": None, "bytes": None, "sha256": None}


def inspect_profile(root, env=None):
    """Inspect known G1 inputs without installing, fetching or building anything."""
    env = dict(os.environ if env is None else env)
    report = {"schema_version": 1, "profile": PROFILE, "status": "blocked",
              "hardware_qualified": False, "g1_gate_passed": False,
              "known_prerequisites_present": False, "dependency_closure_qualified": False,
              "toolchain_version_inputs_verified": False,
              "host": {"system": platform.system(), "architecture": platform.machine()},
              "nested_dependency_closure": "unqualified", "maven_artifact_closure": "unqualified",
              "source_inputs": {}, "source_gitlinks": [], "provisioning_sources": [],
              "initialized_optional_generators": [], "tools": [], "collateral": {},
              "blockers": [], "limitations": [
                  "Ready means enumerated local prerequisites only, not build or CPU verification.",
                  "Nested source and resolved Maven/Coursier closure remain unqualified.",
                  "Conda package, supplementary CMake and installed executable identity need separate review.",
                  "Version strings and collateral hashes are observations, not trusted package attestations.",
                  "No environment file is sourced and no dependencies are installed or initialized.",
              ]}
    blocked = report["blockers"]
    try:
        root = Path(root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("not a directory")
        top = _git(root, env, "rev-parse", "--show-toplevel")
        if not top or Path(top.strip()).resolve() != root:
            raise ValueError("not a repository root")
        profile = _json(root, "nova/g1-profile.json")
        _validate_profile(profile)
        lock = _json(root, profile["pin_source"])
        if (not isinstance(lock, dict) or not isinstance(lock.get("submodules"), list)
                or not isinstance(lock.get("preserved_blobs"), dict)):
            raise ValueError("invalid upstream lock structure")
        pins = {}
        for entry in lock["submodules"]:
            path, pin = entry["path"], entry["commit"]
            if not _relative(path) or not isinstance(pin, str) or not SHA1.fullmatch(pin) or path in pins:
                raise ValueError("invalid upstream pins")
            pins[path] = pin
        index = _gitlink_index(_git(root, env, "ls-files", "--stage", "-z"))
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        blocked.append("repository/profile/pin metadata is missing, malformed or unsafe")
        return report

    if "USE_CHISEL7" in env:
        blocked.append("USE_CHISEL7 must be absent for the default Chisel-6 profile")
    if report["host"] != {"system": "Linux", "architecture": "x86_64"}:
        blocked.append("this profile declares only the Linux x86-64 lean lock")
    for path, expected in profile["source_inputs_sha256"].items():
        try:
            actual = hashlib.sha256(_read(root, path)).hexdigest()
        except (OSError, ValueError, RuntimeError):
            actual = None
        report["source_inputs"][path] = {"sha256": actual, "matches_profile": actual == expected}
        if actual != expected:
            blocked.append("source-graph input is missing or differs from profile: " + path)
    for field, destination, mandatory in (("required_source_gitlinks", "source_gitlinks", True),
                                          ("provisioning_source_gitlinks", "provisioning_sources", False)):
        for path in profile[field]:
            pin = pins.get(path)
            state = _source_state(root, path, pin, index, env) if pin else "missing_pin"
            report[destination].append({"path": path, "pin": pin, "state": state})
            if mandatory and state != "at_pin":
                blocked.append(path + ": " + state)
            elif not mandatory and state not in {"at_pin", "uninitialized"}:
                blocked.append("provisioning source integrity: " + path + ": " + state)
    for name in profile["optional_generators"]:
        try:
            path = root / "generators" / name
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                raise ValueError("outside source")
            if (path / ".git").exists() or (path / ".git").is_symlink():
                report["initialized_optional_generators"].append(name)
        except (OSError, ValueError, RuntimeError):
            blocked.append("optional generator inventory unreadable: " + name)
    if report["initialized_optional_generators"]:
        blocked.append("unexpected initialized optional generators change the compiled source graph")

    # Expected versions are bound to the original imported blobs, not inferred
    # from the host's PATH or silently updated to whatever is installed.
    try:
        sources = {}
        for path in (profile["conda_lock"], profile["circt_input"]):
            data = _read(root, path)
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if lock["preserved_blobs"].get(path) != blob:
                raise ValueError("toolchain source changed")
            sources[path] = data
        versions = re.findall(rb"(?m)^- name: verilator\n  version: ['\"]?([0-9.]+)['\"]?\s*$",
                              sources[profile["conda_lock"]])
        circt = json.loads(sources[profile["circt_input"]], object_pairs_hook=_unique_object)
        if versions != [b"5.022"] or circt.get("version") != "firtool-1.75.0":
            raise ValueError("unsupported toolchain versions")
        report["toolchain_version_inputs_verified"] = True
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        blocked.append("pinned Verilator/firtool source identity could not be verified")
    report["tools"] = [_tool(name, args, root, env) for name, args in TOOLS.items()]
    for tool in report["tools"]:
        if not tool["available"]:
            blocked.append("tool unavailable: " + tool["name"])
        elif tool["expected_version"] and not tool["version_matches"]:
            blocked.append("pinned tool version mismatch: " + tool["name"])

    try:
        raw = env.get("RISCV", "")
        prefix = Path(raw)
        if not raw or not prefix.is_absolute():
            raise ValueError("missing or relative prefix")
        prefix = prefix.resolve(strict=True)
        if not prefix.is_dir():
            raise ValueError("not a prefix directory")
    except (OSError, ValueError, RuntimeError, TypeError):
        prefix = None
        blocked.append("RISCV must identify an existing absolute toolchain directory")
    for name, paths in COLLATERAL.items():
        item = _collateral(prefix, paths) if prefix else {"available": False}
        report["collateral"][name] = item
        if not item["available"]:
            blocked.append("installed collateral missing or unsafe: " + name)
    specs = None
    compiler = shutil.which("riscv64-unknown-elf-gcc", path=env.get("PATH", os.defpath))
    if prefix and compiler:
        observed = _probe([compiler, "-print-file-name=htif_nano.specs"], root, env)
        try:
            path = Path(observed.strip()) if observed else Path("")
            resolved = path.resolve(strict=True)
            if not path.is_absolute() or not resolved.is_relative_to(prefix):
                raise ValueError("specs outside toolchain")
            specs = _collateral(prefix, [str(resolved.relative_to(prefix))])
        except (OSError, ValueError, RuntimeError):
            pass
    report["collateral"]["htif_specs"] = specs or {"available": False}
    if not specs or not specs["available"]:
        blocked.append("HTIF nano specs do not resolve inside the recorded RISCV prefix")
    try:
        target = root / "toolchains/libgloss/util/htif.ld"
        if (root / "tests/htif.ld").resolve(strict=True) != target.resolve(strict=True):
            raise ValueError("unexpected linker target")
        linker = _collateral(root, ["toolchains/libgloss/util/htif.ld"])
    except (OSError, ValueError, RuntimeError):
        linker = {"available": False}
    report["collateral"]["htif_linker"] = linker
    if not linker["available"]:
        blocked.append("HTIF linker script is missing or not the pinned libgloss target")
    # The inherited hello target passes -T htif.ld to the selected compiler.
    # Checking only tests/htif.ld does not establish what that invocation will
    # resolve from the installed toolchain's library search path.
    installed_linker = None
    if prefix and compiler:
        observed = _probe([compiler, "-print-file-name=htif.ld"], root, env)
        try:
            path = Path(observed.strip()) if observed else Path("")
            resolved = path.resolve(strict=True)
            if not path.is_absolute() or not resolved.is_relative_to(prefix):
                raise ValueError("linker outside toolchain")
            installed_linker = _collateral(prefix, [str(resolved.relative_to(prefix))])
        except (OSError, ValueError, RuntimeError):
            pass
    installed_linker = installed_linker or {"available": False}
    installed_linker["matches_pinned"] = bool(
        installed_linker["available"] and linker["available"]
        and installed_linker["sha256"] == linker["sha256"])
    report["collateral"]["htif_installed_linker"] = installed_linker
    if not installed_linker["available"]:
        blocked.append("HTIF linker script does not resolve inside the recorded RISCV prefix")
    elif not installed_linker["matches_pinned"]:
        blocked.append("installed HTIF linker script differs from the pinned libgloss target")
    report["known_prerequisites_present"] = not blocked
    report["status"] = "blocked" if blocked else "ready"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    report = inspect_profile(args.root)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("G1 profile: " + report["status"] + " (known prerequisites only; not hardware qualification)")
        for blocker in report["blockers"]:
            print("- " + blocker)
        for note in report["limitations"]:
            print("Note: " + note)
    return 2 if args.strict and report["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
