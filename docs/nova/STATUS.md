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
  a nonempty test-runner guard, regression tests, and a bounded repository-only
  GitHub Actions workflow. A workflow definition is not a remote execution result.
- Preserved upstream notices, all fifty-seven dependency gitlinks, and hashes for
  the nine imported toolchain definitions/locks.

Executed checks and review findings are recorded in
[BOOTSTRAP_REVIEW.md](BOOTSTRAP_REVIEW.md). This foundation is not a CPU or SoC
release. The only available registered test campaign is `T-REPO-001`; the other
twenty-one test descriptors define future qualification work.

## Gate and environment state

G0 remains `in_progress` for the maintainer's recorded acceptance decision;
its repository infrastructure is implemented and locally checked. G1–G9 remain
`planned`. Automated worker reviews do not fabricate an accountable human
reviewer, enable branch protections, or accept a hardware milestone.

The bootstrap environment has all fifty-seven submodules uninitialized and
thirteen known prerequisite blockers: seven required submodules, `env.sh`, a
valid `RISCV` directory, Verilator, firtool, CMake, and RISC-V GCC. Normal diagnosis
reports these without installing anything; strict diagnosis exits nonzero.
These are observations of this bootstrap environment, not a supported-host matrix
or a guarantee that fixing those items is sufficient for a hardware build.

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
