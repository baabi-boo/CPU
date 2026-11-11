# Verification and evidence plan

This is the qualification plan, not a hardware test report. At bootstrap, only
the repository check is available in the [test register](../../nova/requirements.json);
hardware test descriptors are planned and their commands are not implemented.
Current claims must agree with [STATUS](STATUS.md) and the [roadmap](ROADMAP.md).

## Evidence ladder

| Level | Required observation | What it does not establish |
| --- | --- | --- |
| Repository | Metadata, provenance, local links, and project-tool tests pass | HDL correctness, processor execution, or implementation timing |
| Elaborated RTL | Expected topology, parameters, RTL, map, and simulator build | Correct instruction execution or physical feasibility |
| Architectural simulation | Declared ISA/trap tests and reference comparisons execute on each relevant hart | Complete ISA compliance, coherence, or untested extensions |
| System simulation | Multicore memory, firmware/Linux, and included accelerators pass scoped tests | Real memory PHY behavior or FPGA operation |
| FPGA | Named board executes the qualified profile with reviewed constraints | ASIC frequency, ASIC power, or manufacturing readiness |
| Physical implementation | Technology-specific timing/physical reports and explicit signoff closure | Fabricated functionality, yield, or measured silicon behavior |
| Silicon | Identified devices pass an approved bring-up and measurement campaign | Untested operating corners, workloads, or product certification |

Evidence does not automatically transfer between configurations, dependency
revisions, simulators, boards, technologies, or operating conditions. Reuse needs
a documented impact assessment and the relevant regression reruns. A successful
upstream demonstration is not NOVA integration evidence.

## Test matrix and execution order

Stable requirement IDs map to the following existing test descriptors. Implement
the test before claiming its result, and record actual commands in the register
only when they exist. Narrow tests may be useful without closing a whole gate.

| Gate/scope | Test IDs | Minimum campaign |
| --- | --- | --- |
| G0 foundation | `T-REPO-001` | Offline metadata/link/provenance checks, tooling unit tests, negative fixtures, clean-checkout reproduction |
| G1 baseline | `T-BUILD-001`, `T-ISA-001` | Repeated Rocket and named-baseline builds; hello, declared ISA/trap/MMU cases; pinned reference comparison |
| G2 every hart | `T-HART-001`, `T-ISA-001`, `T-RESET-001` | Expected hart inventory, per-hart execution and identity, reset/interrupt/trap behavior, bounded completion |
| G3 memory/platform | `T-MAP-001`, `T-COH-001`, `T-ORDER-001`, `T-LINUX-001` | Generated map agreement, dirty-line exchange, eviction/false sharing, atomics/LR-SC, litmus tests, repeated SMP boot |
| G4 CPU experiments | `T-CPU-PERF-001`, `T-ISA-001`, `T-POWER-001` | Matched baseline/candidate correctness and performance; scoped power evidence when claimed |
| G5 AI integration | `T-NPU-NUM-001`, `T-NPU-MEM-001`, `T-DMA-001` | Reference numerics, boundaries/overflow, command completion, dirty buffers, transfer cost, reset/fault recovery |
| G6 GPU integration | `T-GPU-EXEC-001`, `T-DMA-001` | Integrated submission and completion, reference-checked kernels, selected graphics scope, memory ownership and recovery |
| Claimed protection | `T-ISOLATION-001` | Unauthorized accesses, malformed descriptors, stale mappings, and debug/boot boundary tests |
| G7 FPGA | `T-FPGA-001`, `T-CDC-001`, `T-PHY-001` | Real-board execution, timing/resources, clock/reset crossings, physical memory integrity and recovery |
| G8 physical feasibility | `T-ASIC-001`, `T-POWER-001`, `T-CDC-001` | Pinned technology flow, timing corners, equivalence/physical checks, power-state methodology, explicit gaps |
| G9 decisions | `T-RELEASE-001`, `T-AUTH-001` | Profile-qualified release review; research release records no fabrication authorization; actual fabrication proposal requires separate authorization and readiness review |

Protection tests apply whenever a protection claim is introduced, not only at
G7. Physical-memory tests must be adapted and requalified for the actual board or
ASIC technology; an FPGA result does not qualify an ASIC PHY.

## CPU and heterogeneous-platform traps

The pinned [TestSuites.scala](../../generators/chipyard/src/main/scala/TestSuites.scala)
selects generic suites from tile ID 0. Passing that selection does not prove the
other hart executed or supports the same ISA. Enumerate expected hart IDs from
elaboration, check identities at runtime, and collect per-hart completion records.

The inherited [`mt-hello.c`](../../tests/mt-hello.c) assumes four participants.
It can wait forever on the initial two-hart NOVA profile. Do not count it as a
ready-made NOVA smoke test: use a reviewed participant-aware program and a bounded
simulator timeout. Missing or duplicate participants must fail visibly.

Pin the reference model, ISA specification/profile, supported extensions,
privilege settings, and comparison adapter. Qualify the adapter with deliberately
wrong register, memory, or trap outcomes. Explain unsupported instructions and
nondeterministic events; never silently filter mismatches. Per-hart retirement
comparison does not replace multicore memory-ordering and coherence tests.

Record exact suite selection and exclusions. For example, an upstream fast-test
target is a subset, not comprehensive architectural compliance. A named test,
successful compilation, zero tests discovered, or a skipped job is not a pass.

## Negative tests and coverage

Each test implementation needs both a known-good case and a failure-detection
case appropriate to its level:

- Repository tooling: malformed/duplicate IDs, broken references, illegal states,
  missing evidence, changed preserved notices, and invalid dependency pins.
- Execution harness: nonzero target exit, wrong result, truncated output, missing
  completion, simulator crash, and deterministic timeout diagnostics.
- Memory and accelerators: dirty caches, partial transfers, backpressure, ID reuse,
  invalid addresses/commands, response errors, reset interruption, and recovery.
- Numerical kernels: zero/boundary shapes, overflow, saturation/rounding, random
  seeds, and declared absolute/relative tolerances against a software reference.
- Physical targets: invalid constraints, uncovered crossings, interface errors,
  and documented fault injection where safe and supported by the target.

Publish functional coverage goals, observed coverage, unhit cases, and justified
exclusions. Code coverage is supplemental and cannot prove architectural or
security correctness. Define timeout/fairness assumptions before execution;
investigate deadlocks rather than increasing limits until a run appears green.

## Reproducibility and result records

Follow [REPRODUCIBILITY](REPRODUCIBILITY.md). Each run must record at least:

- Requirement/test IDs, gate, evidence level, scope, expected and observed result.
- Repository commit and dirty state, patch identity if dirty, configuration,
  dependency gitlinks, toolchain/simulator/reference-model versions, and options.
- Workload/input/image hashes, ISA/ABI, firmware, generated map, actual memory
  model and timing parameters, seeds, and relevant environment/resource limits.
- Exact command and working directory, start time, duration, timeout, exit code,
  complete logs, traces when needed, artifact locations, and integrity hashes.
- Status (`passed`, `failed`, `blocked`, or `not_run`), exclusions, failure analysis,
  responsible reviewer, and links to corrective issues or accepted limitations.

Keep simulated target cycles separate from host simulator elapsed time. Nominal
configuration frequency is not achieved FPGA/ASIC frequency. Keep synthesis power
estimates, board power, and measured silicon energy distinct; publish assumptions
and unsuccessful experiments. See [BENCHMARKS](BENCHMARKS.md).

## Gate closure and invalidation

The maintainer and assigned reviewers inspect requirement-to-test coverage,
reproduction, failures, and profile-specific prerequisites before a gate decision.
Scripts may reject incomplete evidence but must not automatically award hardware
qualification. Multiple agents or repeated runs are not independent expert
silicon signoff; disclose who reviewed what and any self-review.

Close only the scope actually demonstrated. Record **go**, **conditional go**, or
**no-go** under [GOVERNANCE](GOVERNANCE.md). A conditional research approval leaves
unmet acceptance criteria unpassed; fabrication authorization is separate.
Preserve failed and superseded evidence. Reopen affected requirements/gates after
changes that invalidate their configuration, assumptions, or dependencies, and
record the regression plan rather than silently carrying old green results.
