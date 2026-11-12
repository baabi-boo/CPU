# Development and local bring-up

Start with [STATUS](STATUS.md), [CONFIGURATIONS](CONFIGURATIONS.md), and the
[verification plan](VERIFICATION.md). This guide separates inexpensive repository
checks from opt-in hardware-toolchain work. The hardware commands below are
inspected entry points, **not successful NOVA build or execution evidence**.
The end-to-end G1 evidence and acceptance checklist is in the
[single-core baseline runbook](BASELINE_RUNBOOK.md).

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

## 3. Establish the single-hart baseline

### Preferred two-configuration G1 campaign

After the maintainer has approved a specific host and resource budget, prepared
the pinned toolchain without unreviewed lockfile or submodule changes, and
activated `env.sh`/`RISCV` and `CONDA_PREFIX`, inspect the proposed run
**without executing it**:

```bash
make -f nova.mk g1-campaign-plan
```

This read-only mode lists separate `RocketConfig` and `NovaM1BaselineConfig`
builds and the same 15 declared workloads per configuration: inherited hello,
the NOVA eight-check target, its deliberate code-7 failure control, and 12 fixed
ISA binaries. These commands have not been demonstrated on the current host.
The implementation is tooling, not a new CPU architecture or a completed
`T-BUILD-001`/`T-ISA-001` campaign.

Execution requires the checkout containing the runner and helpers to be clean,
with no hidden-index flags or known stale build products, a prepared `env.sh`,
valid `RISCV`/`CONDA_PREFIX`, a ready fixed profile, and matching Conda metadata.
It rejects enumerated inherited build overrides instead of silently changing the
profile. It never deletes stale products; use a separate clean checkout and
review remaining ignored caches. After actual maintainer resource approval and
successful preflight, the explicit entry point is:

```bash
python3 -B scripts/nova/g1_profile.py --strict --json
python3 -B scripts/nova/conda_inventory.py --prefix "$CONDA_PREFIX" --json
python3 -B scripts/nova/g1_campaign.py --execute --approved-budget
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
recorded executed commands to the declared plan.
`workloads_observed` means the declared log protocols were observed, **not** that
target-originated completion, processor correctness, or G1 is qualified. The
pinned HTIF path can signal success after a signal-induced shutdown; see the
[source-level finding](evidence/G1-COMPLETION-PROTOCOL-2026-11-12.md).
`target_completion_verified`, `hardware_qualified`, and `g1_gate_passed` remain
false. The reference-model comparison is not run, and the declared ISA subset
does not qualify excluded extensions or every conditional branch inside upstream
tests.

Repeat the approved campaign from a second clean checkout without sharing
generated build products. `compare_campaigns.py` compares the two retained
records, but `consistent` means agreement between unauthenticated metadata—not
proof of execution, independent caches, or hardware reproduction. Follow the
[runbook](BASELINE_RUNBOOK.md) for the exact comparison command, unresolved
target-exit observability, evidence review, and separate gate acceptance. Curate
raw logs before publication; execution records can contain local paths.

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
