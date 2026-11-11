# NOVA-M1 evidence-gated roadmap

This roadmap defines research deliverables, not a promise of Apple compatibility,
Apple-level performance, fabrication access, or a delivery date. Current evidence
is recorded in [STATUS.md](STATUS.md). Requirements, subsystem specifications, and
verification plans must evolve together; a diagram or configuration name is not
an implemented and qualified chip.

## Gate policy

- Milestone states: `planned`, `in_progress`, `blocked`, `passed`, `failed`.
- G0 is `in_progress`; G1–G9 are `planned` at project bootstrap.
- Each gate decision records the reviewed revision, responsible maintainer,
  reviewer, prerequisites, requirement/test IDs, failures, exclusions, artifact
  locations, and one of **go**, **conditional go**, or **no-go**.
- Conditional research may continue with explicit blockers, but the milestone
  remains unpassed until its exit requirements are met. A waiver does not turn an
  unrun test into a pass or qualify a capability outside the tested configuration.
- Preserve exact Git/submodule/toolchain versions, commands, resource limits,
  seeds, timeouts, expected/observed results, exit codes, logs, and artifact hashes.
- Research can run in parallel. Integration acceptance follows the dependencies
  below; invalidating a dependency reopens affected downstream gates.
- Any power or energy-efficiency claim requires scoped `REQ-PWR-001` /
  `T-POWER-001` evidence when the claim is made, even before G8. Record these
  claim-dependent tests in the gate decision; their later ownership gate is not
  permission to defer validation of an earlier claim.
- Reviewers are engineering roles until maintainers assign real people. An
  automated agent review is assistance, not independent silicon signoff.

| Gate | Outcome | Acceptance dependencies | Initial state |
| --- | --- | --- | --- |
| G0 | Engineering foundation | None | in_progress |
| G1 | Reproducible Rocket baseline | G0 | planned |
| G2 | Verified heterogeneous CPU platform | G1 | planned |
| G3 | Coherent memory and Linux platform | G2 | planned |
| G4 | Measured original CPU improvement | G2; G3 for OS workloads | planned |
| G5 | AI subsystem integration | G3 | planned |
| G6 | GPU and shared-memory research | G3 | planned |
| G7 | Real FPGA prototype | G2 and G3; G5/G6 if included | planned |
| G8 | ASIC feasibility study | Selected RTL qualification gates | planned |
| G9 | Research release / fabrication decision | Chosen release profile | planned |

## G0 — Engineering foundation

**Prerequisite:** preserve the Chipyard baseline and all existing dependency pins.

**Work:** establish the project charter, architecture boundaries, requirements,
status ledger, risk register, development instructions, review procedures, and
lightweight CI. Keep upstream attribution and a readable original README.

**Exit evidence:** repository validators, documentation links, metadata checks,
and tooling unit tests pass from a clean checkout. Record the bootstrap change,
which checks were run, known toolchain gaps, and the first hardware backlog.
Document proposed branch protections separately from actual repository settings.

**Go/no-go:** no-go if docs imply untested hardware success or the setup silently
changes dependency pins. Passing G0 establishes repository infrastructure only;
it does not establish HDL elaboration, CPU execution, or an original CPU design.

## G1 — Reproducible single-core baseline

**Prerequisite:** G0. Reserve an explicit toolchain/runtime resource budget.

**Work:** initialize the pinned required submodules, reproduce the upstream
toolchain environment, and elaborate/build unmodified `RocketConfig`. Validate
the named `NovaM1BaselineConfig` derivative separately. Retain a frozen reference
configuration and baseline workload artifacts for later regression comparison.

**Exit evidence:** a fresh-checkout build generates RTL and a working simulator;
bare-metal hello and a declared set of supported ISA tests execute correctly.
Archive the generated device tree/address map, ISA/MMU/cache parameters, actual
memory model, simulator commands, tool versions, and all exclusions. Reproduce
the result on a second clean build, not merely by reusing an old executable.

**Go/no-go:** no-go on unexplained build differences, simulator errors, or missing
logs. A compiler invocation or test-suite listing is not execution evidence.
Passing G1 does not certify all RISC-V extensions or heterogeneous execution.

## G2 — Heterogeneous CPU platform

**Prerequisite:** G1. Use a small two-hart target before increasing core counts.

**Work:** qualify `NovaM1MinimalConfig`, initially a named derivative of the pinned
`LargeBoomAndRocketConfig`: one BOOM v3 core, one Rocket core, and inherited
interconnect/cache infrastructure. Establish hart identity, boot participation,
interrupt routing, per-hart ISA/MMU capabilities, and reset sequencing.

**Exit evidence:** generate the expected two harts and verify each executes its
assigned workload. Run per-hart instruction/exception tests, simultaneous boot,
interrupt delivery, barriers, repeated reset, and bounded forward-progress tests.
Use differential checking against a pinned reference where supported and record
the exact comparison scope. Prove errors are detected with negative tests.

**Go/no-go:** no-go if only hart 0 is tested. Adapt or replace inherited tests that
assume four harts; their presence does not verify this configuration. BOOM/Rocket
roles remain performance-oriented/efficiency-oriented hypotheses, not measured
P/E properties. This is integration of existing cores, not new CPU RTL.

## G3 — Coherent memory and Linux platform

**Prerequisite:** G2 and an approved memory/firmware contract.

**Work:** specify the authoritative address map, cacheability, memory ordering,
atomic operations, fault behavior, firmware handoff, and boot artifacts. Integrate
the selected firmware/Linux stack, device tree, timer, interrupts, and console.
Keep CPU coherence distinct from accelerator coherence and shared virtual memory.

**Exit evidence:** both harts pass dirty-line exchange, eviction/false-sharing
stress, atomic contention, LR/SC, message-passing, and declared memory-order litmus
tests. Linux repeatedly boots, enumerates both harts, schedules work on each, and
reports devices matching the generated map. Include concurrent load, fault, and
reboot tests with bounded timeouts and reproducible image/build hashes.

**Go/no-go:** no-go on unexplained deadlocks, forbidden outcomes, or inconsistent
address maps. One successful boot is insufficient. A simulated AXI memory port is
not a physical DDR/LPDDR controller or PHY; CPU coherence does not qualify a GPU.

## G4 — Measured original CPU development

**Prerequisite:** G2; G3 whenever results depend on Linux or system services.

**Work:** identify a bottleneck with counters/traces; select one original change
to prediction, execution, caching, or scheduling. Record an architecture decision
with a falsifiable hypothesis, expected trade-offs, and rollback criteria. Keep
the unchanged upstream baseline available and separate from the experiment.

**Exit evidence:** baseline and candidate run identical workloads, inputs, ISA,
toolchain, memory model, and measurement methodology. Preserve correctness and
report distributions, regressions, execution cycles, and relevant area/timing
estimates. Publish unsuccessful hypotheses as well as improvements. Report energy
only with a declared, calibrated estimation method or direct measurements.
CPU performance-only experiments require `T-CPU-PERF-001` and `T-ISA-001`;
power or energy-efficiency claims additionally require `T-POWER-001` evidence.

**Go/no-go:** no-go on cherry-picked workloads or hidden configuration changes.
An accepted experiment may be a well-characterized negative result. Simulated
cycles and synthesis estimates cannot establish Apple-level performance per watt.

## G5 — AI subsystem

**Prerequisite:** G3. Approve the accelerator interface and ownership contract.

**Work:** integrate a pinned Gemmini configuration and its matching software stack.
Specify supported data types, tensor shapes, quantization, accumulation/overflow,
command submission, memory access, completion, and error recovery. Establish
software fallback behavior and explicit CPU/accelerator buffer ownership.

**Exit evidence:** compare kernels against a software reference using declared
numerical tolerances; include randomized shapes, boundary conditions, overflow,
backpressure, dirty CPU buffers, invalid accesses, reset, and timeout recovery.
Run an end-to-end inference workload with published inputs and expected output.
Report transfer/setup cost separately from kernel execution and end-to-end time.

**Go/no-go:** no-go if an upstream demo substitutes for NOVA integration evidence.
Reject unsupported claims of CPU–NPU coherence, isolation, or model compatibility.
The existence of a Gemmini submodule does not satisfy this gate.

## G6 — GPU and shared-memory research

**Prerequisite:** G3. GPU selection and driver feasibility require an ADR first.

**Work:** evaluate a pinned open GPU candidate such as Vortex; assess interfaces,
license/provenance, runtime, toolchain, resource needs, and graphics/API coverage.
Implement the bridge, submission/completion protocol, interrupts, and driver.
Choose a documented coherent or explicitly managed noncoherent memory model.

**Exit evidence:** real integrated compute kernels complete with reference-checked
results; demonstrate a bounded graphics workload only when the selected stack
supports it. Test CPU↔GPU dirty-buffer exchange, concurrent accesses, outstanding
transactions, errors, timeouts, invalid commands, and reset recovery. Verify any
claimed translation/isolation feature separately with hostile DMA inputs.

**Go/no-go:** no-go if only a standalone GPU simulator works. Shared DRAM alone is
not unified coherent memory; CPU fences alone do not flush/invalidate caches.
Do not infer desktop graphics API conformance or Apple GPU compatibility.

## G7 — FPGA prototype

**Prerequisite:** G2/G3, and G5/G6 for accelerators included in the selected profile.

**Work:** select and authorize a concrete board and toolchain; fit a reduced SoC
profile to it. Integrate board memory, I/O, clock/reset crossings, constraints,
boot firmware, and a documented debug/security policy. Separate omitted features
from the full research architecture instead of silently reducing claimed scope.

**Exit evidence:** record board/FPGA part, tool versions, bitstream hash, resources,
timing constraints and closure, CDC/RDC review, memory tests, physical boot logs,
both-hart workload results, repeated reset, and recovery from induced faults.
Accelerators included in the profile rerun their integration acceptance tests.

**Go/no-go:** no-go without real board observations. Emulation and simulation are
not FPGA validation. FPGA frequency/power are not estimates of an advanced-node
ASIC unless a separately justified model explicitly connects them.

## G8 — ASIC feasibility

**Prerequisite:** qualification of every included RTL block and explicit approval
for the selected technology, IP access, compute resources, and investigation cost.

**Work:** choose a realizable PDK/library/macro set; assess memory, analog/PHY,
clocking, power domains, I/O, packaging, DFT, and tool availability. Run a reduced
synthesis/place-and-route trial and maintain the outstanding signoff checklist.
Use Hammer/OpenROAD or another approved flow only within its supported scope.

**Exit evidence:** pinned technology provenance, constraints/corners, synthesized
and physical artifacts, area/timing results, equivalence strategy, CDC/RDC review,
DRC/LVS results or explicit blockers, power methodology, and manufacturability
risks. Identify which results are educational estimates versus foundry-qualified.

**Go/no-go:** no-go on unlicensed/inaccessible IP, unconstrained paths, missing
macro/PHY assumptions, or unsupported manufacturability claims. A GDS file does
not establish tapeout readiness, yield, packaging feasibility, or silicon success.

## G9 — Research release and separate fabrication decision

**Prerequisite:** declare a release profile and its required earlier gates. A
simulation-only research release does not require G7/G8, but must say so clearly.
Any fabrication proposal requires G8 and closure of its technology-specific gaps.

**Work:** freeze a release candidate, resolve regressions, publish reproducible
artifacts and limitations, and review maintenance/security obligations. For an
ASIC proposal, separately secure real IP/foundry access, packaging/test plans,
DFT/signoff reviews, manufacturing budget, ownership, and explicit authorization.

**Exit evidence:** independently reviewed requirement coverage, clean-checkout
reproduction, tagged source/dependency/toolchain manifests, known-issues list,
release notes, and named acceptance. A fabrication decision additionally records
foundry-appropriate signoff, responsible engineers, and approved logistics.

**Go/no-go:** release only the evidence-qualified profile. Do not describe research
release acceptance as permission to order silicon. Post-silicon bring-up and
measured performance require a new validation campaign after fabricated parts
exist; neither G8 nor G9 provides that evidence.

## Maintaining this plan

Review gate dependencies after each architecture or dependency change. Split
oversized work into scoped issues with a requirement, owner role, acceptance
test, evidence destination, and blocker. Prioritize G1 reproducibility and G2
per-hart correctness before expanding core counts or promising additional IP.
Use [VERIFICATION.md](VERIFICATION.md) for test strategy and
[ARCHITECTURE.md](ARCHITECTURE.md) for the intended subsystem boundaries.
