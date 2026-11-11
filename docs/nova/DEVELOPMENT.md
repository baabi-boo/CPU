# Development and local bring-up

Start with [STATUS](STATUS.md), [CONFIGURATIONS](CONFIGURATIONS.md), and the
[verification plan](VERIFICATION.md). This guide separates inexpensive repository
checks from opt-in hardware-toolchain work. The hardware commands below are
inspected entry points, **not successful NOVA build or execution evidence**.

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

## 2. Prepare an explicitly approved hardware environment

Use a Linux development environment with an approved RAM, disk, CPU-parallelism,
network, and wall-time budget, including GNU coreutils `timeout`. The pinned setup
selects Linux x86-64 or AArch64 Conda lockfiles; this guide does not claim a
validated NOVA host-platform matrix.
Install/activate the prerequisite Conda environment using the pinned upstream
[setup guidance](../Chipyard-Basics/Initial-Repo-Setup.rst) and inspect
[`scripts/build-setup.sh`](../../scripts/build-setup.sh) before running it.

The upstream script downloads dependencies, creates an environment, initializes
submodules, prepares the toolchain, and can compile sources. It is not part of
the lightweight offline checks. In a clean working copy, after approving that
work, the initial lean setup entry point is below. The example sends TERM after
two hours and allows a further 30 seconds before KILL; choose an approved setup
budget before starting. Interrupting setup can leave a partial environment.

```bash
timeout --kill-after=30s 2h ./build-setup.sh --use-lean-conda --skip-clean riscv-tools &&
source ./env.sh &&
make -f nova.mk doctor-strict
```

Lean setup omits FireSim and FireMarshal; Linux-workload preparation is therefore
a later explicit step. `--skip-clean` prevents the setup's repository-cleanup
stage. Do not use `--use-unpinned-deps` or replace locked dependencies with latest
versions to bypass a failure. Record blockers and propose a reviewed migration.
Do not pass tokens on command lines or enable verbose tracing around credentials.

The pinned setup also checks host glibc and can rewrite
`conda-reqs/chipyard-base.yaml` and regenerate lockfiles even without
`--use-unpinned-deps`. Review this path before execution, record pre/post lock
hashes and source diffs, and treat any changed lock as a dependency migration,
not a reproduction of the untouched pin. Do not continue qualification with an
unreviewed regenerated lock.

The build needs the selected Java, Verilator, FIRRTL/CIRCT `firtool`, C/C++ build
tools, and RISC-V toolchain. The default sbt invocation uses Java and
`scripts/sbt-launch.jar`; a standalone `sbt` executable is not required. A generic
RISC-V compiler alone may lack Chipyard's HTIF headers, specs, and libraries.

## 3. Establish the single-hart baseline

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
timeout --kill-after=30s 10m cmake -S tests -B tests/build &&
timeout --kill-after=30s 10m cmake --build tests/build --target hello --parallel 2 &&
timeout --kill-after=30s 300s make -C sims/verilator CONFIG=RocketConfig run-binary \
  BINARY="$PWD/tests/build/hello.riscv"
```

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
