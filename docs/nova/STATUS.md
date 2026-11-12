# NOVA-M1 status

Status date: 2026-11-12. Baseline: Chipyard commit
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
- A fixed Chisel-6 prerequisite profile in `scripts/nova/g1_profile.py`, with
  pinned source/version-input checks, explicit optional-generator handling, and
  installed HTIF/runtime collateral checks. A hypothetical `ready` result means
  only that these enumerated checks passed, not complete dependency closure or
  working hardware. `conda_inventory.py` compares installed package metadata
  with the unchanged 165-package lean lock; metadata agreement does not verify
  installed binary contents.
- A declared campaign in `nova/g1-workloads.json`: inherited hello, an eight-check
  NOVA RV64 smoke program, a deliberate code-7 negative control, and twelve exact
  ISA test names. The plan runs all fifteen workloads separately on `RocketConfig`
  and `NovaM1BaselineConfig`. **These thirty workload executions are planned,
  not observed.** The NOVA C target is implemented source, not a cross-compiled
  or simulated result.
- An opt-in `scripts/nova/g1_campaign.py` runner with a read-only `--plan` mode
  and explicit `--execute --approved-budget` entry point. It requires a prepared
  clean checkout, checks the declared profile and inventory before and after a
  run, retains separate bounded logs, binds binary/source/artifact identities,
  and records interrupted, blocked, and failed attempts. Resource checks are
  bounded or sampled; they are not kernel quotas or a hard whole-process time
  guarantee. Explicit builds may resolve JVM dependencies under the approved
  network policy; the runner does not provision a toolchain or initialize
  submodules.
- Protocol assessment and `compare_campaigns.py`, with offline integration and
  malformed-record regressions. A `consistent` comparison establishes agreement
  between recorded identities, not authenticated execution, independent builds,
  or hardware reproduction. A fresh local checkout passed **532 repository-only
  tooling tests**; none is processor qualification. The
  [automated review ledger](evidence/G1-60-AGENT-REVIEW-2026-11-12.md) identifies
  the checked revisions and later integration checks.
- The earlier single-profile `rocket_baseline.py` helper remains available.
  Its stage-local cancellation handling retains observed subprocess exits
  separately from normalized diagnostic codes and cleans up its process group.
  Its `hello_marker_observed_unqualified` result is not target-completion proof
  and cannot substitute for the full G1 campaign and review.
- Preserved upstream notices, all fifty-seven dependency gitlinks, and hashes for
  the nine imported toolchain definitions/locks.

Executed checks and review findings are recorded in
[BOOTSTRAP_REVIEW.md](BOOTSTRAP_REVIEW.md), the historical
[NOVA-001 preflight](evidence/NOVA-001-PREFLIGHT-2026-11-11.md), and the current
[G1 preparation evidence](evidence/G1-PREPARATION-2026-11-12.md), with subsequent
tooling checks in the
[automated review ledger](evidence/G1-60-AGENT-REVIEW-2026-11-12.md). Follow the
[Rocket baseline runbook](BASELINE_RUNBOOK.md) for the remaining campaign. This
foundation is not a CPU or SoC release. The only available registered test
campaign is `T-REPO-001`; the other twenty-one test descriptors define future
qualification work.

## Gate and environment state

G0 remains `in_progress` for the maintainer's recorded acceptance decision;
its repository infrastructure is implemented and locally checked. **G1 is
`blocked`**, with preparation evidence linked from `nova/project.json`.
G2–G9 remain `planned`. Automated worker reviews do not fabricate an accountable
human reviewer, enable branch protections, or accept a hardware milestone.
`T-BUILD-001` and `T-ISA-001` remain planned: neither a printed execution plan
nor a prerequisite rejection satisfies their hardware test requirements.

In the current unprepared checkout, all fifty-seven submodules are uninitialized.
The new `python3 -B scripts/nova/g1_profile.py --strict --json` inspection reports
**38 blockers and exit status 2**. They include twenty-one known required source
gitlinks, unavailable build/cross-toolchain components, and absent installed
runtime/HTIF collateral. The earlier `doctor-strict` result of 27 blockers is a
different diagnostic snapshot, not the current profile's count. Earlier seven /
thirteen and nine / fifteen gitlink/blocker counts likewise remain historical.
None of these enumerated profiles establishes complete nested or Maven
dependency closure. Normal diagnosis does not install dependencies; strict
diagnosis exits nonzero when its prerequisites are missing.

The separate NOVA-001 preflight identifies a setup-integrity risk on this host:
the inherited automatic setup logic would select sysroot 2.39 for host glibc
2.41 instead of preserving the pinned 2.34, and would regenerate tracked Conda
locks. **glibc 2.41 is not intrinsically incompatible with the older pinned
sysroot**; the stop condition is the unreviewed rewriting path, not that claim.
A pin-preserving preparation procedure still needs review and actual validation.
The prepared Conda/toolchain environment is absent. All nine imported Conda
inputs and all fifty-seven gitlink pins remain unchanged. These are observations
of one unprepared host, not a supported-host matrix, authorization to install
dependencies, or a
guarantee that resolving these findings will make a hardware build succeed.
The recorded NOVA-001 attempt is therefore **blocked pending G0 maintainer
acceptance, an approved host/resource/network/time/cost budget, and a
pin-preserving toolchain**, not completed or failed by a CPU test.

There is also a source-confirmed completion-observability limitation: the pinned
HTIF path can signal zero success after a signal-induced shutdown without a
target-originated exit. A matching TestDriver `PASSED` record and host exit zero
therefore establish only `completion_protocol_observed`, while
`target_completion_verified` remains false. This path was identified by source
review, not reproduced in a CPU simulation here. Independent target-exit
observability remains required before using these observations for acceptance.

## What has not been demonstrated

- No NOVA-specific HDL elaboration, simulation execution, Linux boot, or multicore
  qualification has been completed by this setup change.
- No actual two-profile workload campaign, independent second clean hardware
  build, pinned reference comparison, or target-originated completion evidence
  has been retained. The Spike comparison scope remains unresolved.
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

The next deliverable is a reviewed, pin-preserving prepared environment and an
independently observable target-exit path. Then run the declared upstream and
named-baseline campaigns, repeat the complete build in a second clean checkout,
resolve the supported reference-comparison scope, and retain artifacts for a
maintainer gate decision. The mixed BOOM/Rocket configuration follows under G2;
it must validate every hart. Hart-0-only tests and the inherited four-hart
`mt-hello.c` are not sufficient.
