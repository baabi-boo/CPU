# ADR 0002: Simulation-first, evidence-gated development

- Date: 2026-11-11
- Status: accepted for bootstrap architectural direction
- Authority: implementation of the requested NOVA-M1 project setup
- Human hardware approval: none asserted

## Context and decision

An integrated SoC has coupled hardware, firmware, driver, physical-IP, and
verification risks. A successful repository check cannot establish CPU behavior.

Use the [roadmap](../ROADMAP.md) gates and separate evidence levels: repository,
elaborated RTL, architectural/system simulation, FPGA, physical implementation,
and manufactured silicon. Begin with an unchanged Rocket baseline, then the
named NOVA profiles. Perform integration acceptance in simulation before FPGA
qualification; physical feasibility research may run in parallel without
claiming a passed downstream gate.

## Alternatives and consequences

| Alternative | Reason not selected |
| --- | --- |
| FPGA-first full SoC | Adds board, timing, and physical-memory faults before a reproducible functional baseline |
| One universal green CI status | Conflates documentation/tooling checks with hardware correctness and physical validation |
| Feature-count or calendar-based completion | Gives no falsifiable requirement-level evidence and can hide unrun work |

Cheap offline checks are the default feedback loop. Hardware simulation, FPGA,
and ASIC jobs remain explicit and resource-bounded. This adds record-keeping and
review effort, but makes failures and unsupported claims visible.

## Verification, interfaces, and reversal

Trace to `REQ-REPO-002`, `REQ-BUILD-001`, `REQ-FPGA-001`, `REQ-ASIC-001`, and
`REQ-REL-001`. Follow [VERIFICATION](../VERIFICATION.md) and
[REPRODUCIBILITY](../REPRODUCIBILITY.md). Record exact source/configuration,
commands, tool versions, expected/observed outcomes, artifacts, and exclusions.

Gate acceptance requires scoped review, not automatic self-certification.
Simulation cycles are not achieved silicon frequency; an FPGA measurement is
not ASIC power. Shared addresses do not prove coherent accelerator memory.
No NOVA RTL execution, physical validation, or fabrication authorization is
established by adopting this workflow.

When evidence becomes invalid, reopen affected gates and retain prior reports
with their limitations. A changed verification strategy requires a superseding
ADR and coverage impact review; do not weaken criteria merely to obtain a pass.
