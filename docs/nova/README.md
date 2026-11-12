# NOVA-M1 engineering documentation

Start with the [project charter](CHARTER.md), [current status](STATUS.md), and
[gated roadmap](ROADMAP.md). Planned work is not a demonstrated capability.

## First contribution

1. Read the [project overview](../../README.md) for scope and present limitations.
2. Follow [DEVELOPMENT](DEVELOPMENT.md) for offline checks, preflight diagnostics,
   and the separately approved hardware-toolchain workflow.
   Use the non-mutating `make -f nova.mk preflight`, `g1-profile`, `conda-plan`,
   and `g1-campaign-plan` targets to inspect setup risks, known prerequisites,
   the preserved inventory, and the proposed campaign. They do not install
   dependencies or verify a processor.
3. Check [CONFIGURATIONS](CONFIGURATIONS.md) before selecting a source profile;
   both NOVA profiles still require elaboration and execution evidence.
4. Start with NOVA-001 in the [actionable backlog](BACKLOG.md). Its prerequisite
   approvals and acceptance evidence determine what can be attempted next. Use
   the [G1 baseline campaign runbook](BASELINE_RUNBOOK.md) for its bounded sequence
   and reproducibility requirements after those approvals are recorded.

## Current G1 preparation checkpoint

The profile/inventory inspectors, RV64 target sources, two-configuration campaign
runner, and record comparator are implemented and covered by offline tooling
tests. Their 15 workloads per configuration have not run on NOVA hardware or its
simulator. G1 is blocked, and both named NOVA configurations remain unverified.

Read the [current preparation evidence](evidence/G1-PREPARATION-2026-11-12.md)
for observed host blockers and preserved pins. The
[completion-protocol investigation](evidence/G1-COMPLETION-PROTOCOL-2026-11-12.md)
explains why an observed simulator success signal is not independent proof of
target-originated completion. Matching campaign JSON is likewise not proof of
execution or independent build reproduction.

The [automated review ledger](evidence/G1-60-AGENT-REVIEW-2026-11-12.md)
records the ten-wave development/review sequence and clean-checkout tooling
checks. Automated review is not human gate acceptance or processor validation.

## Design and qualification

- [System architecture](ARCHITECTURE.md)
- [CPU subsystem](CPU.md)
- [Memory and coherence](MEMORY.md)
- [AI and GPU accelerators](ACCELERATORS.md)
- [Firmware, operating system, and I/O](PLATFORM.md)
- [Power, FPGA, and physical implementation](POWER_PHYSICAL.md)
- [Verification plan](VERIFICATION.md)
- [Configuration profiles](CONFIGURATIONS.md)

## Engineering workflow

- [Developer setup](DEVELOPMENT.md)
- [G1 baseline campaign runbook](BASELINE_RUNBOOK.md): opt-in preparation,
  two-profile execution, stop conditions, and evidence; not a completed hardware
  result.
- [CI scope](CI.md)
- [Bootstrap review and executed checks](BOOTSTRAP_REVIEW.md)
- [Reproducibility and evidence](REPRODUCIBILITY.md)
- [Evidence record template](evidence/TEMPLATE.md): copy for a real attempt;
  the unexecuted template is not a qualifying result.
- [Benchmark methodology](BENCHMARKS.md)
- [Risk register](RISKS.md)
- [Research and source evaluation](RESEARCH.md)
- [Actionable backlog](BACKLOG.md)
- [Governance and review](GOVERNANCE.md)
- [Release process](RELEASES.md)
- [Architecture decision records](adr/README.md)

Structured project state is kept in [project.json](../../nova/project.json);
requirement/test traceability is in [requirements.json](../../nova/requirements.json).
The [upstream lock](../../nova/upstream-lock.json) records the imported baseline,
dependency gitlinks, and preserved notices.

See the root [contribution guide](../../CONTRIBUTING.md) and
[third-party notices](../../THIRD_PARTY_NOTICES.md) before submitting changes.
