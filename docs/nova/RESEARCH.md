# Research-to-engineering workflow

Research must produce a testable engineering decision, not a feature claim copied
from a paper, project README, or chip diagram. NOVA's current evidence remains in
[STATUS](STATUS.md); milestone acceptance is defined by [ROADMAP](ROADMAP.md).

## From question to implementation

1. **Frame a bounded question.** Name the gate, requirement/test IDs, target
   configuration, observed problem, resource budget, and decision to be made.
   Separate a missing capability from an optimization of an existing one.
2. **Collect primary evidence.** Prefer the applicable specification, pinned RTL,
   matching tool documentation, original paper, and reproducible upstream test.
   Record URL/path, revision or publication version, access date, relevant section,
   license, assumptions, and conflicts with other sources.
3. **Write a falsifiable hypothesis.** State what should change, the baseline,
   workload, expected observable effect, correctness constraints, and conditions
   that would reject the idea. Numerical targets are hypotheses until measured.
4. **Propose an architecture decision.** Compare viable alternatives, interfaces,
   dependencies, software implications, verification effort, risks, and rollback.
   Use the [ADR process](adr/README.md); dependency changes need separate review.
5. **Run the smallest useful experiment.** Keep the reference configuration intact.
   Pin every source/tool version, bound runtime/resources, and change one controlled
   variable. Begin with a small workload and reference result, not a full SoC sweep.
6. **Verify and retain evidence.** Include negative tests, correctness regressions,
   excluded cases, failed hypotheses, actual commands, hashes, and raw results.
   Follow [VERIFICATION](VERIFICATION.md), [BENCHMARKS](BENCHMARKS.md), and
   [REPRODUCIBILITY](REPRODUCIBILITY.md). An unrun experiment is `not_run`.
7. **Decide and integrate.** Record adopt, revise, defer, or reject with the reason.
   Accepted work becomes a scoped implementation task with tests, documentation,
   and requirement links. Research approval alone does not close a hardware gate.

## Primary-source map

These are research entry points, not endorsements of unverified NOVA capabilities.
The [upstream lock](../../nova/upstream-lock.json) identifies imported revisions;
[.gitmodules](../../.gitmodules) supplies locations, not version selection.

| Topic | Start here | Evidence to extract |
| --- | --- | --- |
| SoC composition | [Pinned heterogeneous guide](../Customization/Heterogeneous-SoCs.rst), [Chipyard](https://github.com/ucb-bar/chipyard), [framework documentation](https://chipyard.readthedocs.io/) | Configuration composition, interfaces, harness assumptions, version-specific examples |
| ISA and privilege | [RISC-V ISA manual](https://github.com/riscv/riscv-isa-manual), [Spike reference model](https://github.com/riscv-software-src/riscv-isa-sim) | Selected specification release, extension status, allowed behavior, reference-model limitations |
| CPU microarchitecture | [BOOM source](https://github.com/riscv-boom/riscv-boom), [Rocket Chip source](https://github.com/chipsalliance/rocket-chip), [pinned BOOM guide](../Generators/BOOM.rst) | Exact core generation, pipeline/counter behavior, parameter constraints, verification hooks |
| Memory and DMA | [Pinned memory guide](../Customization/Memory-Hierarchy.rst), [DMA guide](../Customization/DMA-Devices.rst), [AbstractConfig source](../../generators/chipyard/src/main/scala/config/AbstractConfig.scala) | Actual selected memory model, coherence path, ordering, ownership and error contracts |
| AI acceleration | [Gemmini](https://github.com/ucb-bar/gemmini), [pinned integration guide](../Generators/Gemmini.rst), [RoCC guide](../Customization/RoCC-Accelerators.rst) | Matching hardware/software revision, precision, supported shapes, command and memory semantics |
| GPU candidates | [Radiance](https://github.com/ucb-bar/radiance), [Vortex](https://github.com/vortexgpgpu/vortex), [NOVA accelerator plan](ACCELERATORS.md) | Revision-specific host/SoC interface, runtime and driver needs, tested compute/graphics scope, resources |
| FPGA and ASIC | [Local FPGA support](../../fpga), [Hammer guide](../VLSI/Hammer.rst), [OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD), [local OpenROAD tutorial](../VLSI/Sky130-OpenROAD-Tutorial.rst) | Target/tool/PDK compatibility, constraints, memory macros, physical checks, implementation gaps |

The RISC-V manual, OpenROAD, and Radiance entry-point URLs were checked during
bootstrap on 2026-11-11. That check establishes source availability only; it does
not qualify a candidate revision, implementation, API, or manufacturing flow.

## Questions for each development stage

| Gates | Bounded research question | Required decision or experiment |
| --- | --- | --- |
| G1–G2 CPU | What ISA/privilege intersection and hart mapping does the selected BOOM/Rocket configuration actually expose? | Elaborated inventory plus per-hart execution; resolve `REQ-CPU-001` / `REQ-CPU-002` before workload migration assumptions |
| G3 memory | Which coherence agent owns each line, and what outcomes are allowed under the declared ordering model? | Map and protocol review, dirty-line/atomic stress, and ordering litmus campaign for `REQ-MEM-001` / `REQ-MEM-002` |
| G4 CPU improvement | Which measured stall dominates, and does one predictor/cache/execution change improve the full workload set? | Controlled baseline/candidate experiment for `REQ-CPU-004`, retaining correctness and regressions |
| G5 AI | Which numeric and transfer constraints determine end-to-end benefit for one fixed workload? | Reference-checked kernels, dirty-buffer ownership and full inference measurements for `REQ-NPU-001` / `REQ-NPU-002` |
| G6 GPU | Which candidate can meet a bounded compute/graphics scope with maintainable drivers and a specified memory contract? | Candidate comparison ADR, minimal command/result prototype, and `REQ-GPU-001` / `REQ-DMA-001` tests |
| G7–G8 power/physical | Does the selected profile fit the actual target, and what assumptions dominate timing and power estimates? | Capacity/timing/CDC study, qualified memory interface, and declared power methodology for `REQ-FPGA-001`, `REQ-PHY-001`, `REQ-PWR-001`, `REQ-ASIC-001` |

## Source conflicts and claim boundaries

- A current upstream branch can differ from NOVA's pinned revision. Inspect the
  selected source and matching software before adopting a feature description.
  Pin external candidates before experiments; Vortex is not presently a NOVA pin.
- Papers describe particular implementations and conditions. Record technology,
  configuration, workload, simulator, and measurement method before comparison.
  A citation is not a reproducibility result or a license to claim those numbers.
- Resolve source/documentation conflicts explicitly. For example, NOVA must record
  the instantiated memory model rather than inherit outdated prose about it.
- Keep simulation cycles, host simulator runtime, FPGA behavior, ASIC estimates,
  and silicon measurements separate. FPGA watts cannot establish ASIC energy;
  nominal frequency parameters cannot establish timing closure.
- Public Apple material may inform system-level questions. Do not copy proprietary
  RTL, restricted implementation details, or assets without rights. Independent
  RISC-V design does not imply Arm/macOS compatibility or Apple affiliation.
- Verify dependency, model, dataset, EDA, PDK, standard-cell, SRAM, and interface-IP
  rights before importing or redistributing them. Availability online is not a
  manufacturing entitlement; confidential materials must not enter this repository.
- Escalate missing licenses, unavailable primary evidence, excessive resources, or
  contradictory results. Document the blocker instead of substituting a guess.

## Minimum research note

Store a concise note with the relevant ADR or experiment evidence: question and
IDs; source/version table; facts versus inference; hypothesis; alternatives;
experiment plan and limits; observed results or `not_run`; uncertainties;
decision/reviewer; and the next implementation or rejection action. A useful
negative result is retained. Avoid collecting links without extracting decisions.
