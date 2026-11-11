# NOVA-M1 project charter

Charter revision: 1. Status: engineering foundation; hardware qualification pending.

## Purpose

NOVA-M1 develops an inspectable, reproducible RISC-V system-on-chip research
platform on Chipyard. Its long-term direction is heterogeneous CPU compute,
specialized acceleration, a well-defined shared-memory system, and documented
power/performance/area trade-offs. The M-series inspiration is the integration
philosophy, not a claim about implementation, compatibility, or performance.

NOVA-M1 is independent of Apple. It is not an Apple silicon clone, an Arm
processor, or a promise to run macOS or Apple binaries. Apple-like performance,
energy efficiency, packaging, manufacturing technology, and product readiness
are not acceptance criteria for the initial research platform.

The authoritative current capability record is [STATUS.md](STATUS.md).
The [roadmap](ROADMAP.md) defines gates; the [architecture](ARCHITECTURE.md)
defines interfaces and configurations. Aspirations never override those records.

## Measurable engineering objectives

| Objective | Evidence required before claiming success |
| --- | --- |
| Reproducible development | A clean-checkout procedure, pinned revisions, explicit prerequisites, bounded commands, and archived results |
| Correct CPU execution | Declared ISA subset, executed tests, reference-model comparisons, negative cases, and all exclusions recorded |
| Correct heterogeneous operation | Every hart identified and exercised; reset, interrupts, synchronization, atomics, and cache behavior checked |
| Useful acceleration | Correct results against a software reference, documented memory ownership, and reproducible end-to-end measurements |
| Explainable architectural improvement | Baseline and candidate measured with the same workload and tool conditions, with correctness regressions closed |
| Traceable claims | Every accepted requirement linked to a verification method, exact revision, result, and reviewable artifacts |
| Maintainable upstream relationship | Preserved licenses and provenance, isolated NOVA additions, reviewed dependency updates, and documented local changes |

Do not set clock-rate, power, bandwidth, or benchmark headline targets before a
workload definition, technology assumption, and measurement method are approved.
Simulation configuration frequencies are not achieved FPGA or ASIC frequencies.

## Starting architecture and reuse boundary

The first hardware baseline is an inherited Rocket configuration. The first
heterogeneous experiment reuses one BOOM v3 core and one Rocket core through
Chipyard's existing `LargeBoomAndRocketConfig`. At the pinned baseline this uses
`WithNLargeBooms(1)` and `WithNHugeCores(1)`; the latter is not evidence of an
energy-efficient core. See the inherited
[configuration source](../../generators/chipyard/src/main/scala/config/HeteroConfigs.scala).

"Performance" and "efficiency" are provisional research roles. Any P/E
classification must follow comparable workload, area, and power evidence.

Chipyard, Rocket, BOOM, and their dependencies remain upstream work. Naming a
configuration or integrating an existing accelerator does not make its internal
microarchitecture an original NOVA design. Original contributions should be
identified separately: integration logic, new or modified microarchitecture,
verification, software interfaces, experiments, and engineering tooling.

## First release contract: engineering foundation

The first release is a repository foundation, not a hardware release. Its scope:

- A project-specific README, charter, architecture, requirements, and gated plan.
- Explicit current/planned status and the preserved Chipyard provenance.
- An offline repository-check command and diagnostic environment preflight.
- Named source configuration scaffolds, clearly marked unverified until run.
- Contribution, review, evidence, and dependency-change procedures.
- Lightweight CI that distinguishes repository checks from RTL verification.

Acceptance requires reproducible repository checks, reviewed documentation and
metadata, valid local documentation links, and preserved upstream licenses and
dependency pins. It does not require or imply an HDL build, successful program
execution, Linux boot, an FPGA bitstream, or a manufactured chip. Those remain
separate gates even if the foundation release passes.

## Progression and scope boundaries

1. **Simulation:** Establish the unmodified baseline, then elaborate and test the
   NOVA configurations. Archive generated interfaces and memory-map artifacts.
   Validate per-hart execution and memory behavior before system software or
   additional accelerators expand the debug surface.
2. **System integration:** Add CPU improvements, AI, GPU, and software in separate
   experiments. Each block needs an interface contract, reference tests, error
   recovery, dependency review, and a measurable benefit or research question.
3. **FPGA:** Select a board and a reduced configuration only after resource and
   interface estimates. Require board-specific clocks, resets, constraints,
   memory integration, timing closure, and physical test records.
4. **ASIC feasibility:** Evaluate a selected process, libraries, memory macros,
   I/O, and implementation flow. A layout experiment is not tapeout approval.
   Fabrication requires a separately approved budget, foundry/IP access,
   packaging, test plan, signoff ownership, and manufacturing readiness review.

The following are explicitly outside the first release:

| Area | Boundary and later decision |
| --- | --- |
| Unified memory | A shared address range or DRAM device does not establish CPU/GPU coherence, shared virtual addresses, or isolation. Specify each DMA contract and verify ownership transitions. |
| DDR/LPDDR | A simulated AXI memory port is not a physical controller or PHY. Board or ASIC memory IP, training, timing, and access terms need separate evaluation. |
| Graphics | A GPU candidate is not an integrated desktop graphics stack. Drivers, command submission, memory safety, display output, and API support require separate proof. |
| AI | Upstream Gemmini availability is not successful NOVA integration, numerical qualification, or application-level speedup. |
| Power | Clock gating, power domains, DVFS, and energy claims need design, technology assumptions, and validation; heterogeneous core names provide no proof. |
| Security/media/I/O | Secure boot, isolation, codecs, high-speed links, and controllers are independent workstreams, not capabilities implied by the SoC label. |
| Silicon | Synthesis or routed GDS alone is insufficient: timing corners, CDC/RDC, equivalence, DRC/LVS, power integrity, DFT, packaging, and test require accountable signoff. |

## Roles and authority

Roles describe responsibilities, not an existing staffed organization. Named
assignments are currently unassigned unless recorded by the repository maintainer.

| Role | Responsibility |
| --- | --- |
| Maintainer | Accept changes, assign accountable owners, authorize resources and releases |
| Architecture owner | Approve interface contracts, architectural decisions, and requirement changes |
| Subsystem owner | Implement changes, maintain tests, document risks and dependencies |
| Verification reviewer | Examine evidence, exclusions, failures, and regression completeness |
| Platform/physical-design owner | Own board or technology constraints and later implementation signoff |

One person may hold multiple roles, but the review record must disclose that fact;
automated checks or agent reviews are not substitutes for required independent
hardware or manufacturing signoff.

## Decision and resource discipline

- Architecture changes require a written decision, alternatives, and impacts on
  requirements, software, verification, dependencies, and resources.
- A gate may be passed only with its required evidence. Missing tools, omitted
  tests, and uncertain results remain visible blockers; do not redefine a gate
  after a failure simply to obtain a pass.
- Paid compute, purchases, external runners, fabrication, licensed IP, secrets,
  device access, and publication outside this repository require explicit
  maintainer authorization. No standing unlimited budget is implied.
- Record resource estimates before expensive jobs and bound execution time,
  parallelism, and storage. Prefer small reproducible experiments before scaling.
- Review goals after each gate. Stop or revise a workstream when correctness,
  tooling, access, or resource constraints invalidate its assumptions.

No calendar promise or full-chip completion claim follows from this charter.
Progress is measured by accepted evidence and reproducible deliverables.
