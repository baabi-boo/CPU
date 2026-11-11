# ADR 0001: RISC-V/Chipyard foundation

- Date: 2026-11-11
- Status: accepted for bootstrap architectural direction
- Authority: implementation of the requested NOVA-M1 project setup; subsequent
  architectural changes follow the [ADR process](README.md)
- Human hardware approval: none asserted

## Context and decision

The repository starts from Chipyard commit
`a7946ede9bd625204435715dc40c750e2f8a251f`. NOVA-M1 explores M-series-inspired
system integration, not Apple instruction compatibility or proprietary designs.

Retain RISC-V and pinned Chipyard infrastructure. Establish two thin named
profiles: `NovaM1BaselineConfig` derives from `RocketConfig`, and
`NovaM1MinimalConfig` derives from `LargeBoomAndRocketConfig`. Preserve upstream
licenses and dependency pins. These source aliases remain unverified until
their own elaboration and execution evidence exists.

## Alternatives and consequences

| Alternative | Reason not selected for bootstrap |
| --- | --- |
| Arm/Apple-compatible clone | Not provided by this RISC-V foundation; introduces a different ISA, IP, platform, and software scope |
| New CPU microarchitecture first | Defers a trustworthy integration/reference baseline and expands initial verification risk |
| GPU/NPU-first integration | Adds interface and software complexity before baseline execution is established |

Reusing established cores minimizes initial divergence and enables controlled
experiments. It does not make their design NOVA-original. The initial large
Rocket configuration is not a measured efficiency core; P/E classification and
original CPU improvements require later experiments and decisions.

## Interfaces, verification, and reversal

Preserve inherited CPU/fabric/memory interfaces initially. Qualify the generated
hart inventory, common ISA/ABI, map, interrupts, reset, atomics, and coherence;
see [ARCHITECTURE](../ARCHITECTURE.md) and [CPU](../CPU.md).

Trace to `REQ-REPO-001`, `REQ-BUILD-001`, `REQ-CPU-001`, and `REQ-CPU-002`.
G1 requires reproducible baseline execution; G2 requires every heterogeneous
hart to participate. Neither gate has passed through this ADR.

If reproducibility, integration feasibility, or measured trade-offs invalidate
the choice, propose a superseding ADR with migration costs and affected tests.
Keep the pinned upstream reference and qualified artifacts available for
comparison; revert experiments with reviewable commits, not destructive resets.
