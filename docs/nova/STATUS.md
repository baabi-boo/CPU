# NOVA-M1 status

Status date: 2026-11-11. Baseline: Chipyard commit
`a7946ede9bd625204435715dc40c750e2f8a251f`.

## What exists

- The inherited Chipyard code and pinned dependency references.
- An implemented NOVA-M1 engineering foundation: charter, subsystem
  specifications, ten acceptance gates, twenty requirements, twenty-two test
  descriptors, twelve proposed backlog tickets, and contribution procedures.
- Two thin source configuration aliases: `NovaM1BaselineConfig` and
  `NovaM1MinimalConfig`. Neither has elaboration or execution evidence.
- Offline metadata/link/provenance checks, non-mutating prerequisite diagnosis,
  a separate NOVA-001 bootstrap preflight, a nonempty test-runner guard,
  regression tests, and a bounded repository-only GitHub Actions workflow.
  The bootstrap preflight checks pinned Conda inputs and host setup risks; it
  does not install dependencies or run HDL. A workflow definition is not a
  remote execution result.
- An opt-in, resource-bounded `scripts/nova/rocket_baseline.py` runner with a
  read-only `--plan` mode and explicit `--execute --approved-budget` gate. Its
  plan was inspected locally, and execution on this unprepared checkout stopped
  at its prerequisites before starting a hardware build. The runner is tooling,
  **not** evidence that Rocket RTL elaborated or a test binary executed. Even
  its possible `hello_marker_observed_unqualified` result would mean only that
  the marker was seen, not that target completion was independently verified or
  G1 passed. At least 191 repository-only tooling tests have passed during this
  development effort; none is processor qualification.
- Preserved upstream notices, all fifty-seven dependency gitlinks, and hashes for
  the nine imported toolchain definitions/locks.

Executed checks and review findings are recorded in
[BOOTSTRAP_REVIEW.md](BOOTSTRAP_REVIEW.md), with the current host's
[blocked NOVA-001 preflight](evidence/NOVA-001-PREFLIGHT-2026-11-11.md)
and the next [Rocket baseline runbook](BASELINE_RUNBOOK.md). This foundation is
not a CPU or SoC release. The only available registered test campaign is
`T-REPO-001`; the other
twenty-one test descriptors define future qualification work.

## Gate and environment state

G0 remains `in_progress` for the maintainer's recorded acceptance decision;
its repository infrastructure is implemented and locally checked. G1–G9 remain
`planned`. Automated worker reviews do not fabricate an accountable human
reviewer, enable branch protections, or accept a hardware milestone.
`T-BUILD-001` and `T-ISA-001` remain planned: neither a printed execution plan
nor a prerequisite rejection satisfies their hardware test requirements.

In the current unconfigured bootstrap checkout, all fifty-seven submodules are
uninitialized. The updated diagnostic checks an expanded set of known G1
prerequisites, including `tools/DRAMSim2` (unconditionally linked by the
Verilator build), `toolchains/libgloss` (needed by the documented HTIF-linked
`hello` test), and the direct Chipyard/Chisel dependencies referenced in
`build.sbt`. It also checks `env.sh`, a valid `RISCV` directory, Verilator,
firtool, CMake, and RISC-V GCC. At the time of this update the diagnostic
reports **twenty-one known required gitlinks and twenty-seven blockers** on
this host. The earlier bootstrap review's seven required
gitlinks / thirteen blockers, and the intermediate nine / fifteen diagnostic,
are historical snapshots, not a complete dependency-closure analysis. The
current count is obtained by running `make -f nova.mk doctor-strict`. Normal
diagnosis reports missing prerequisites without installing anything; strict
diagnosis exits nonzero. A passing strict diagnostic would establish known
prerequisite presence, not prove that nested dependencies and elaboration work.

The separate NOVA-001 preflight finds a setup-integrity blocker on this host:
glibc 2.41 causes the inherited setup logic to select sysroot 2.39 instead of
the pinned 2.34 and regenerate tracked Conda locks. Conda and other required
build tools are also absent. All nine imported Conda inputs match their pinned
source blobs at this preflight. These are observations of one unprepared host,
not a supported-host matrix, authorization to install dependencies, or a
guarantee that resolving these findings will make a hardware build succeed.
The recorded NOVA-001 attempt is therefore **blocked pending G0 maintainer
acceptance, an approved host/resource/network/time/cost budget, and a
pin-preserving toolchain**, not completed or failed by a CPU test.

## What has not been demonstrated

- No NOVA-specific HDL elaboration, simulation execution, Linux boot, or multicore
  qualification has been completed by this setup change.
- GPU/NPU integration, unified coherent accelerator memory, custom original CPU
  microarchitecture, measured P/E efficiency, DVFS, FPGA validation, and ASIC
  implementation remain planned work.
- A source configuration and passing repository checks are not a hardware pass.

## Evidence states

Use `planned`, `in_progress`, `blocked`, `passed`, or `failed` for milestone
progress. Every `passed` milestone requires exact revision, commands, results,
and reviewable artifacts. A missing environment is `blocked` or `not_run` in the
test record, never an implicit pass. Hardware claims must identify the evidence
level: source, elaborated RTL, simulation, FPGA, or silicon.

The first hardware task is a reproducible single-core Rocket baseline, followed
by the NOVA mixed BOOM/Rocket configuration. The latter must validate every hart;
hart-0-only tests and the inherited four-hart `mt-hello.c` are not sufficient.
