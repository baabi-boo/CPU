# CPU subsystem specification

This specification defines intended contracts and qualification work. No NOVA CPU
elaboration, execution, or efficiency measurement is established by this document.
See [STATUS](STATUS.md), [ARCHITECTURE](ARCHITECTURE.md), and the
[requirement register](../../nova/requirements.json).

## Source profiles and reuse boundary

| Profile | Pinned upstream basis | Intended role |
| --- | --- | --- |
| `NovaM1BaselineConfig` | `RocketConfig`: `WithNHugeCores(1)` + `AbstractConfig` | Single-hart reproduction and debug reference |
| `NovaM1MinimalConfig` | `LargeBoomAndRocketConfig`: `WithNLargeBooms(1)` + `WithNHugeCores(1)` + 128-bit system bus + `AbstractConfig` | Two-hart BOOM v3/Rocket integration experiment |

The initial profiles reuse existing CPU designs. Their named configuration
scaffolds do not constitute original CPU RTL. Sources are
[RocketConfigs](../../generators/chipyard/src/main/scala/config/RocketConfigs.scala),
[HeteroConfigs](../../generators/chipyard/src/main/scala/config/HeteroConfigs.scala),
and [BoomConfigs](../../generators/chipyard/src/main/scala/config/BoomConfigs.scala)
at the recorded Chipyard baseline. Preserve the BOOM v3 starting point; changing
generation or dependency pins requires compatibility review and renewed evidence.

BOOM and Rocket are candidate performance/efficiency roles, not a measured P/E
pair. The inherited Rocket is the `WithNHugeCores` configuration, not a minimal
low-power core. Neither core count nor nominal frequency proves energy efficiency.

## Hart and software contract

Each elaborated profile must produce a checked inventory containing:

- Expected and observed hart count, unique hart IDs, core type, and boot role.
- XLEN, exact ISA extensions, supported privilege modes, CSR behavior, and debug
  capabilities. Record generated metadata and runtime observations separately.
- MMU mode, virtual/physical address widths, page sizes, access/dirty-bit behavior,
  PMP configuration, TLB behavior, and instruction/data-cache parameters.
- Interrupt source/context mapping, timer/software-interrupt routes, reset entry,
  reset synchronization, and secondary-hart start/park protocol.
- Toolchain ISA/ABI settings, firmware assumptions, and workload compatibility.

Do not infer hart-to-core ordering from the textual order of configuration mixins.
Confirm it from elaborated topology and per-hart identity observations. Boot must
account for every expected hart exactly once and reject unexpected participants.

The initial goal is a common 64-bit software profile, but the qualified extension
set must be the verified intersection of participating harts. A workload that can
migrate between harts must not silently depend on an extension absent on one hart.
Explicit affinity/dispatch, if introduced later, needs separate scheduling and
illegal-instruction tests. Do not assume vector, hypervisor, or advanced privilege
features from generic RISC-V or upstream project descriptions.

Linux support additionally requires a documented firmware/ISA/MMU contract and
device-tree agreement. A configuration's existence is not evidence that the
selected heterogeneous profile boots Linux. See [PLATFORM](PLATFORM.md).

## Reset, interrupts, and progress

Specify cold reset, repeated reset, boot ordering, secondary-hart release, pending
interrupt handling, and recovery from a reset during concurrent traffic. Each
hart needs trap-entry/return and interrupt-delivery coverage, including masked and
pending sources. Define observable completion markers and timeouts in the test
harness; an infinite wait must fail with hart IDs and diagnostic traces.

Cross-hart barriers and atomics must follow the declared memory-ordering contract.
Test interference, contention, and LR/SC retry behavior without assuming that an
individual SC must succeed. Require bounded system-level progress under the
documented test conditions. Coherence and ordering are separate from instruction
correctness; see [MEMORY](MEMORY.md).

## Qualification matrix

All hardware tests below are planned until their implementation and run evidence
are recorded. A test identifier is a specification, not a passing test result.

| Requirement | Test IDs | Required acceptance evidence |
| --- | --- | --- |
| `REQ-BUILD-001` | `T-BUILD-001` | Repeated clean-checkout RTL/simulator builds and generated profile inventory |
| `REQ-CPU-001` | `T-ISA-001` | Declared ISA, exceptions, privilege/MMU cases; reference comparisons and exclusions |
| `REQ-CPU-002` | `T-HART-001`, `T-ISA-001`, `T-RESET-001` | Every expected hart executes; unique identities, interrupt/reset behavior, bounded recovery |
| `REQ-MEM-002` | `T-COH-001`, `T-ORDER-001` | Cross-hart coherence, atomics, ordering litmus outcomes, and contention progress |
| `REQ-CPU-004` | `T-CPU-PERF-001`, `T-ISA-001`; also `T-POWER-001` for power/efficiency claims | Matched baseline/candidate results with correctness; power claims additionally need a scoped power methodology |

The pinned [TestSuites.scala](../../generators/chipyard/src/main/scala/TestSuites.scala)
selects generic suites from tile ID 0. That selection cannot establish coverage
of the other heterogeneous hart. The inherited
[`mt-hello.c`](../../tests/mt-hello.c) hardcodes four participating cores and can
wait forever on a two-hart profile. Do not use it unchanged for NOVA acceptance;
provide a reviewed participant-aware test with a bounded harness timeout.

The existing `MediumBoomV3CosimConfig` demonstrates `WithCospike` and `WithTraceIO`
composition. It is a reference, not a verified NOVA differential-test setup.
Qualify a NOVA-specific composition, pin the reference model, identify unsupported
features, and inject known mismatches to verify the comparison detects errors.
Per-hart instruction comparison does not replace multicore memory-model testing.

## Measurement and original architecture work

Start with cycles, retired instructions, cache/branch events, and stall reasons
where supported. Record counter definitions, width, overflow, privilege filtering,
measurement windows, warm-up, and interrupt effects. Validate counters against a
small known workload before using them for design decisions.

Potential original experiments include branch prediction, cache/prefetch behavior,
issue scheduling, and configuration/resource trade-offs. Change one controlled
dimension at a time; retain the upstream reference and record an ADR, falsifiable
hypothesis, implementation diff, tests, and rollback criteria. Preserve failed
hypotheses and workload regressions rather than reporting only speedups.

Compare identical binaries, inputs, toolchains, memory models, and measurement
windows. Keep simulated cycles, synthesis estimates, FPGA measurements, and
silicon measurements distinct. P/E classification requires documented area,
performance, and energy evidence; no Apple-level equivalence follows from a
benchmark score. See [BENCHMARKS](BENCHMARKS.md) and [VERIFICATION](VERIFICATION.md).
