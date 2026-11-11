# Architecture decision records

An ADR records why an architectural choice was made, its alternatives, and the
evidence needed to keep or reverse it. It is not a test report or a gate pass.

## Register

| ID | Decision | State |
| --- | --- | --- |
| [0001](0001-riscv-chipyard-foundation.md) | RISC-V/Chipyard and inherited baseline profiles | Accepted for bootstrap direction |
| [0002](0002-simulation-first-evidence.md) | Simulation-first development and separate evidence levels | Accepted for bootstrap direction |

These bootstrap choices implement the requested project direction. Their state
does not assert independent human review, verified RTL, or hardware signoff.
Hardware progress remains governed by [STATUS](../STATUS.md) and the
[roadmap](../ROADMAP.md).

## Process

1. Copy [TEMPLATE](TEMPLATE.md) to the next numbered, descriptive filename.
2. Start as `proposed`; identify requirement IDs, alternatives, interfaces,
   acceptance tests, resource implications, and rollback conditions.
3. Review through a pull request with affected subsystem roles. Record actual
   reviewers when assigned; do not invent staffed roles or completed approvals.
4. Mark `accepted` when adopted within its stated scope and record the decision
   authority/reference. Acceptance selects a design direction, not a test result.
5. Mark an obsolete decision `superseded` and link its replacement in both files.
   Keep historical rationale; do not silently rewrite the original decision.

GPU selection, accelerator coherence, virtual-memory interfaces, P/E role
classification, physical memory IP, and power-domain changes require their own
ADRs before adoption. Update requirements, tests, risks, and affected evidence
with each decision. An ADR cannot waive a failing test into a pass or authorize
spending, manufacturing, or access to unavailable IP.
