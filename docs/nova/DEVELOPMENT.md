# Development and local bring-up

Start with [STATUS](STATUS.md), [CONFIGURATIONS](CONFIGURATIONS.md), and the
[verification plan](VERIFICATION.md). This guide separates inexpensive repository
checks from opt-in hardware-toolchain work. The hardware commands below are
inspected entry points, **not successful NOVA build or execution evidence**.
The end-to-end G1 evidence and acceptance checklist is in the
[single-core baseline runbook](BASELINE_RUNBOOK.md).

The optional HTIF observer and reusable native host probe are implemented; their
[current evidence](evidence/G1-HTIF-OBSERVER-2026-11-25.md) does not establish a
CPU or RTL run. **G1 remains blocked pending the prepared environment, two
independent clean CPU campaign builds, and review.**

## 1. Work on the repository without a hardware toolchain

Requirements: Git, GNU Make, and Python 3.10 or newer. The NOVA check scripts use
only the Python standard library. No recursive submodule clone is needed for
documentation, metadata, and tooling tests.

```bash
git clone https://github.com/baabi-boo/CPU.git nova-m1 &&
cd nova-m1 &&
make -f nova.mk check
```

Run all commands in this guide from the repository root unless stated otherwise.
The check validates project metadata, requirement/test references, local link
targets, configuration aliases, preserved attribution, dependency gitlinks, and
Python tooling tests. It does not run HDL elaboration or processor simulation.

Useful narrower commands are:

```bash
make -f nova.mk help
make -f nova.mk validate
make -f nova.mk test
make -f nova.mk doctor
python3 -B scripts/nova/doctor.py --json
python3 -B scripts/nova/bootstrap_preflight.py --json
make -f nova.mk g1-profile
make -f nova.mk conda-plan
make -f nova.mk g1-campaign-plan
make -f nova.mk g1-observed-plan
```

`doctor` is a non-mutating diagnostic: it does not install tools, initialize
submodules, source `env.sh`, or build hardware. Normal mode reports missing
prerequisites without failing. Use the following when a nonzero exit is required:

```bash
make -f nova.mk doctor-strict
```

Strict mode checks known prerequisites, not complete compatibility or hardware
correctness. Optional/nested submodules can still be required by a selected
configuration. Initialized submodules are checked for tracked and untracked local
changes, but ignored files and complete nested dependency trees are not qualified.
Record recursive submodule status and local changes separately for qualified runs;
see [REPRODUCIBILITY](REPRODUCIBILITY.md).

`bootstrap_preflight.py` is a separate, non-mutating NOVA-001 safety check. It
inspects the host, pinned source inputs, and known setup risks without creating a
Conda environment, downloading dependencies, initializing gitlinks, or building
hardware. Run it before proposing a toolchain installation. Its findings are
diagnostics, **not** approval to run setup or evidence of a working processor.

The preferred campaign preflight is `g1_profile.py`. Use
`make -f nova.mk g1-profile-strict` for a nonzero exit on blockers. It checks the fixed Linux
x86-64/Chisel 6 profile's enumerated source/tool/runtime prerequisites, including
the installed HTIF linker script. A `ready` result does not establish complete
nested/Maven dependency closure, trustworthy installed binaries, or successful
linking. `conda-plan` reads the unchanged 165-package lean inventory without
creating an environment; matching installed `conda-meta` records later is only
metadata agreement. The [current preparation record](evidence/G1-PREPARATION-2026-11-12.md)
documents the observed blocked host, not a successful hardware run.

`g1-observed-plan` prints the optional schema-2 campaign with dedicated HTIF
target-exit observation. `g1-campaign-plan` retains the legacy schema-1
protocol-only plan. Both are read-only and neither prepares observer outputs
nor establishes that the full build environment is ready.

## 2. Prepare an explicitly approved hardware environment

Use a Linux development environment with maintainer-approved host, RAM, disk,
CPU parallelism, network access, wall-time and monetary-cost budget, including
GNU coreutils `timeout`. A command timeout and `-j2` alone do not constrain
peak RAM, disk usage, or total host CPU consumption. The pinned setup
selects Linux x86-64 or AArch64 Conda lockfiles; this guide does not claim a
validated NOVA host-platform matrix.
Install/activate the prerequisite Conda environment using the pinned upstream
[setup guidance](../Chipyard-Basics/Initial-Repo-Setup.rst) and inspect
[`scripts/build-setup.sh`](../../scripts/build-setup.sh) before running it.

The upstream script downloads dependencies, creates an environment, initializes
submodules, prepares the toolchain, and can compile sources. It is not part of
the lightweight offline checks. **Before running it**, capture the source
revision and tracked lockfile hashes, run the non-mutating bootstrap preflight,
and inspect the result for expected lockfile regeneration. Stop if changing a
pin would require an unapproved migration. In a clean working copy on an
approved compatible host, the initial lean setup entry point is below. The
example sends TERM after two hours and allows a further 30 seconds before KILL;
choose an approved setup budget before starting. Interrupting setup can leave a
partial environment.

```bash
timeout --kill-after=30s 2h ./build-setup.sh --use-lean-conda --skip-clean riscv-tools &&
source ./env.sh &&
make -f nova.mk doctor-strict
```

Lean setup omits FireSim and FireMarshal; Linux-workload preparation is therefore
a later explicit step. However, the script still invokes
`init-submodules-no-riscv-tools.sh --full`, which fetches optional dependencies
well beyond the minimum known Rocket baseline. Budget and record those downloads
or choose a reviewed, narrower initialization plan. `--skip-clean` prevents the
setup's repository-cleanup stage. Do not use `--use-unpinned-deps` or replace
locked dependencies with latest versions to bypass a failure. Record blockers
and propose a reviewed migration. Do not pass tokens on command lines or enable
verbose tracing around credentials.

The pinned setup also checks host glibc and can rewrite
`conda-reqs/chipyard-base.yaml` and regenerate lockfiles even without
`--use-unpinned-deps`. For example, the imported file pins
`sysroot_linux-64=2.34`, but on a glibc **2.41** Linux host the current setup
logic selects **2.39**, changes the tracked YAML and regenerates locks. That
is **not** a reproduction of the untouched pin. Review this path before
execution, record pre/post lock hashes and source diffs, and treat any change
as a proposed dependency migration. Do not continue qualification with an
unreviewed regenerated lock. The automatic selector's rewrite is the observed
integrity problem; glibc 2.41 by itself does not establish incompatibility with
the older pinned 2.34 sysroot.

For a pin-preserving NOVA-001 experiment, prefer an approved host for which
the setup script keeps the selected sysroot unchanged. Another possible
approach is to provision the exact existing lock manually, initialize only the
reviewed required gitlinks at their recorded SHAs, and skip the automatic Conda
and submodule setup stages. **That selective path is a proposal, not a verified
build procedure:** it must be reviewed for nested dependencies, runtime
compatibility, generated `env.sh`/`RISCV` settings and missing tools before use.
In particular, the lean lock does not itself establish the availability of
`cmake`; the first `hello` test uses HTIF headers, linker inputs, and toolchain
collateral. Mark any missing prerequisite `blocked` instead of silently
substituting the host toolchain. Account for supplementary tools separately in
the reviewed environment; adding packages to the frozen Conda prefix changes
the exact inventory and cannot silently be treated as the original lock.

The build needs the selected Java, Verilator, FIRRTL/CIRCT `firtool`, C/C++ build
tools, and RISC-V toolchain. The default sbt invocation uses Java and
`scripts/sbt-launch.jar`; a standalone `sbt` executable is not required. A generic
RISC-V compiler alone may lack Chipyard's HTIF headers, specs, and libraries.
The campaign never provisions this environment or initializes source gitlinks.
Its explicit Make/sbt builds can nevertheless resolve JVM dependencies, so
approved network access or a separately verified offline dependency cache is
still required. The runner does not establish an offline build closure.

The observed campaign also requires exact pinned Spike source/header bytes, a
matching installed `RISCV/include/fesvr/htif.h`, the installed
`RISCV/include/fesvr/config.h`, and an ordinary static
`RISCV/lib/libfesvr.a`. Missing or mismatched inputs block observer preparation;
shared-only libraries and thin archives are rejected. The generated observer
uses a source overlay without changing the pinned submodule and links its
object before the explicit archive. Captured hashes identify these bytes, not
their ABI compatibility or authenticated provenance. The native host fixture
below uses a synthetic configuration and its own source-built archive; those
products cannot satisfy the prepared-toolchain campaign prerequisites.

## 3. Establish the single-hart baseline

### Preferred two-configuration G1 campaign

After the maintainer has approved a specific host and resource budget, prepared
the pinned toolchain without unreviewed lockfile or submodule changes, and
activated `env.sh`/`RISCV` and `CONDA_PREFIX`, inspect the proposed run
**without executing it**:

```bash
make -f nova.mk g1-observed-plan
```

This read-only mode lists separate `RocketConfig` and `NovaM1BaselineConfig`
builds and the same 15 declared workloads per configuration: inherited hello,
the NOVA eight-check target, its deliberate code-7 failure control, and 12 fixed
ISA binaries. These commands have not been demonstrated on the current host.
The declared execution sequence prepares the observer before the two simulator
builds. The implementation is tooling, not a new CPU architecture or a completed
`T-BUILD-001`/`T-ISA-001` campaign. Omit `--observe-target-exit`, or use the legacy
`g1-campaign-plan` target, only when a protocol-only schema-1 record is intended.

Execution requires the checkout containing the runner and helpers to be clean,
with no hidden-index flags or known stale build products, a prepared `env.sh`,
valid `RISCV`/`CONDA_PREFIX`, a ready fixed profile, and matching Conda metadata.
It rejects enumerated inherited build overrides instead of silently changing the
profile. The running script must belong to that checkout; execution using
`--root` to point another checkout's helper at it is rejected. It never deletes
stale products; use a fresh separate checkout and review remaining ignored
caches. Observed mode rejects existing `nova-out/htif-observer`, generated model
sources, and selected simulator products. Standalone incremental Make reuse is
not qualified: the observer fragment can report success while reusing products
without proving that they were instrumented. After actual maintainer resource
approval and successful preflight, the explicit entry point is:

```bash
python3 -B scripts/nova/g1_profile.py --strict --json
python3 -B scripts/nova/conda_inventory.py --prefix "$CONDA_PREFIX" --json
python3 -B scripts/nova/g1_campaign.py --execute --observe-target-exit --approved-budget \
  --jobs 2 --java-heap 4G --total-timeout-seconds 7200 --min-free-gib 10
```

`--approved-budget` is an acknowledgement of approval already obtained, not a
substitute for it. The defaults permit at most two Make jobs, a 4 GB Java heap,
and a two-hour aggregate acceptance budget. These are initial limits, **not a
validated safe memory/disk/CPU profile**; review and adjust the approved bounds
before execution. The default free-disk floor is 10 GiB, and each stdout/stderr
log is limited to 64 MiB for evidence acceptance. Disk/log limits are sampled;
final evidence/provenance checks can extend elapsed time and invalidate an
over-budget result. These are not kernel quotas or an instantaneous whole-process
deadline. SIGINT/SIGTERM cancellation performs bounded child-group cleanup and
retains an interrupted result; it does not promise cleanup after SIGKILL.

The runner retains separate logs and pre/post source, profile, inventory, binary,
and simulator identities under ignored `nova-out/g1-campaign-*/`. It also binds
recorded executed commands to the declared plan. In observed mode, schema-2
records add observer build metadata and a dedicated witness for every workload,
bound to its unique run ID, source/configuration/workload, binary and simulator
hashes, observer manifest, cycle limit, and seed. The runner supplies the witness
environment; inherited `NOVA_HTIF_*` settings block execution.

`workloads_observed` means all declared process, protocol, integrity, and
mode-specific witness expectations were observed. The ordinary log assessments
retain `target_completion_verified=false` in both schemas. The pinned HTIF path
can signal success after a signal-induced shutdown; this has now been reproduced
in a native host fixture, not a CPU run. See the
[completion finding](evidence/G1-COMPLETION-PROTOCOL-2026-11-12.md) and
[observer evidence](evidence/G1-HTIF-OBSERVER-2026-11-25.md).

Only a matching nested `target_exit.assessment` in schema 2 may report
`target_completion_verified=true`, scoped to the supplied observer event: a
present, nonsignal target exit with expected code 0 or deliberate code 7.
Missing, malformed, incorrectly bound, or signal-only witnesses fail; no witness
overrides process/protocol failure, timeout, cancellation, or input drift.
Legacy schema 1 cannot make this verified-exit claim. `hardware_qualified` and
`g1_gate_passed` remain false in all modes. The reference-model comparison is not
run, and the declared ISA subset does not qualify excluded extensions or every
conditional branch inside upstream tests.

After each real campaign, preserve `record.json` and every named raw stdout,
stderr, and witness file together with their original bytes and basenames.
Retain generated RTL, binaries, and observer manifests/inputs separately as
build evidence. Repeat the whole approved campaign from a second independent
clean checkout without sharing generated build products, and record/isolate
relevant caches. With both retained bundles available, run:

```bash
python3 -B scripts/nova/verify_campaign_bundle.py \
  --record /absolute/path/to/first/record.json
python3 -B scripts/nova/verify_campaign_bundle.py \
  --record /absolute/path/to/second/record.json
python3 -B scripts/nova/compare_campaigns.py \
  /absolute/path/to/first/record.json /absolute/path/to/second/record.json
```

Inspect both verifier results before comparison. `intact` (exit 0) means the
bounded retained record/log/witness bytes and reassessed protocols agree;
`failed` and `blocked` return 1 and 2. The verifier does not open external source,
toolchain, simulator, workload-binary, or observer-build paths; those identities
remain metadata. The comparator takes two positional paths and reports
`consistent`/`different`/`blocked` with exits 0/1/2. It compares record identities
and stable exit semantics, requires the same schema, and rejects reused
schema-2 run IDs. Neither tool authenticates execution or proves independent
builds, trustworthy toolchain provenance, or hardware reproduction. Follow the
[runbook](BASELINE_RUNBOOK.md) for evidence review, the unresolved pinned
reference-comparison scope, and separate gate acceptance. Preserve failed and
blocked runs, and curate raw logs before publication; records can contain local
paths.

### Optional native HTIF host probe

Use the native probe to inspect the host-side terminal-state behavior separately
from the CPU campaign. Its default mode and explicit `--plan` only read local
inputs and print the proposed serial build commands and twelve process cases:

```bash
python3 -B scripts/nova/htif_host_probe.py --plan
python3 -B scripts/nova/htif_host_probe.py --plan \
  --source-root /absolute/path/to/pinned-spike \
  --output /absolute/path/to/existing-parent/fresh-htif-probe
```

Provide the exact **24 pinned source/header/license files**, including the
original `LICENSE`, locally from Spike commit
`9c190a07c6838f6392bafa4ad83acea462c7f759`; the plan exposes the required hashes.
Without an explicit source path, planning checks the repository's declared
Spike directory. Missing or mismatched inputs are blockers, with no download,
installation, or hash-override fallback. Native `g++`, `ar`, and `nm` must already
be available. Execution requires explicit `--source-root` and `--output`; the
output must be a fresh leaf under an existing parent without symlink components.
After approving this native process budget, the bounded command is:

```bash
python3 -B scripts/nova/htif_host_probe.py --execute \
  --source-root /absolute/path/to/pinned-spike \
  --output /absolute/path/to/existing-parent/fresh-htif-probe \
  --total-seconds 180 --command-seconds 45 --case-seconds 5 \
  --max-log-bytes 1048576 --min-free-gib 1
```

These are the defaults: 180 seconds aggregate, 45 seconds per build command,
5 seconds per case, 1 MiB per log stream, and a 1 GiB free-space floor. Accepted
maxima are 300 aggregate seconds, 60 seconds per build command, 30 seconds per
case, and 4 MiB per stream. Cleanup and final capture reserve time; sampled
disk/log checks are not OS quotas. Final retention is bounded to 256 files,
32 MiB per file, and 128 MiB total.

The two native builds cover six modes each: direct exits 0/7, syscall exits 0/7,
signal-only shutdown, and syscall exit 7 followed by a signal. All **12 cases**
use synthetic host memory and a synthetic `HAVE_INT128` configuration. They
perform no RISC-V CPU execution, TSI/TestDriver/Verilator run, or RTL simulation
and do not qualify the installed pinned toolchain. A successful result describes
native host observations and link/symbol checks only. Top-level completion, CPU/RTL,
hardware, and G1 flags stay false; any nested verified-exit flags refer only to
supplied host-fixture events. Retain the source/license snapshots, manifests,
commands, logs, maps, witnesses, results, and artifact inventory. The
[observer evidence](evidence/G1-HTIF-OBSERVER-2026-11-25.md) records the completed
native probe and its limitations. Both clean CPU campaign builds remain unrun.

### Legacy single-profile smoke helper

`python3 -B scripts/nova/rocket_baseline.py --plan` remains available for the
earlier Rocket-only hello sequence. Its opt-in execution can at most report
`hello_marker_observed_unqualified`, with target completion and G1 unverified.
It is not the two-configuration campaign, declared ISA test set, or second clean
build. Prefer the G1 campaign above for the next baseline work.

### Manual commands

The following examples request two parallel Make jobs and send TERM after two
host hours, followed by KILL after a 30-second grace period. These are not RAM,
disk, or whole-host CPU limits; establish those separately and record approved
limits before starting. GNU `timeout` normally reports 124 on timeout, or 137
when KILL is involved; preserve the actual exit status. A timeout is a
failed/blocked run to investigate, not permission to hide a hang. Stop when a
prerequisite command fails; the dependent commands below use `&&` for that reason.

```bash
timeout --kill-after=30s 2h make -C sims/verilator CONFIG=RocketConfig -j2
```

Target programs use the current [CMake build](../../tests/CMakeLists.txt), not an
obsolete `tests/Makefile`. With the configured Chipyard toolchain active:

```bash
timeout --kill-after=30s 10m cmake -S tests -B tests/build \
  -DCMAKE_SYSTEM_NAME=Generic \
  -DCMAKE_C_COMPILER=riscv64-unknown-elf-gcc \
  -DCMAKE_CXX_COMPILER=riscv64-unknown-elf-g++ \
  -DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY &&
timeout --kill-after=30s 10m cmake --build tests/build --target hello --parallel 2 &&
timeout --kill-after=30s 300s make -C sims/verilator CONFIG=RocketConfig run-binary-fast \
  BINARY="$PWD/tests/build/hello.riscv"
```

The CMake options select RISC-V compilers before `project()` configures the
build. Confirm that the resulting binary is ELF64/RISC-V, retain the simulator
status, and separately inspect observed output and completion evidence. A
zero exit and an echoed `hello` marker alone do not establish target completion.
The `run-binary-fast` path avoids the separate `spike-dasm` decoder; choose
`run-binary` explicitly if disassembly traces are required and available.

Archive the baseline result before repeating the build and workload with the
NOVA alias. Both configurations need their own recorded evidence:

```bash
timeout --kill-after=30s 2h make -C sims/verilator CONFIG=NovaM1BaselineConfig -j2 &&
timeout --kill-after=30s 300s make -C sims/verilator CONFIG=NovaM1BaselineConfig run-binary \
  BINARY="$PWD/tests/build/hello.riscv"
```

Hello-world is a bring-up smoke test, not ISA compliance. Follow G1's clean-build,
declared ISA-test, and reference-model requirements before closing that gate.

## 4. Qualify the mixed-core profile separately

After the baseline prerequisites are met:

```bash
timeout --kill-after=30s 2h make -C sims/verilator CONFIG=NovaM1MinimalConfig -j2
```

Do not reuse the inherited four-participant `tests/mt-hello.c` unchanged for this
two-hart profile. Implement a participant-aware test, prove both harts execute,
and bound completion. Hart-0-only suite results do not qualify the mixed system.
Use [CPU](CPU.md), [MEMORY](MEMORY.md), and G2/G3 in [ROADMAP](ROADMAP.md) to define
the remaining boot, interrupt, atomic, coherence, and operating-system tests.

## 5. Capture results and submit changes

Use ignored `nova-out/` for local logs and curated evidence for review. Preserve
exit status when piping output through a logger; a successful `tee` is not a
successful simulator run. Record exact commands, revision/dirty state, gitlinks,
tool versions, configuration, generated map, actual memory model, binaries and
hashes, timeouts, results, and exclusions. Never upload `printenv`, credentials,
private paths, or unreviewed logs. Redact sensitive material before sharing.

Reproduce qualification from a separate clean checkout without deleting local
work or relying on stale binaries. Passing tools do not update milestone states
automatically. Follow [CONTRIBUTING](../../CONTRIBUTING.md) for topic branches,
review, requirement traceability, and dependency changes; [CI](CI.md) explains
which checks run remotely and which hardware work remains explicit.
