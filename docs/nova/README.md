# NOVA-M1 engineering documentation

Start with the [project charter](CHARTER.md), [current status](STATUS.md), and
[gated roadmap](ROADMAP.md). Planned work is not a demonstrated capability.

## First contribution

1. Read the [project overview](../../README.md) for scope and present limitations.
2. Follow [DEVELOPMENT](DEVELOPMENT.md) for offline checks, preflight diagnostics,
   and the separately approved hardware-toolchain workflow.
3. Check [CONFIGURATIONS](CONFIGURATIONS.md) before selecting a source profile;
   both NOVA profiles still require elaboration and execution evidence.
4. Start with NOVA-001 in the [actionable backlog](BACKLOG.md). Its prerequisite
   approvals and acceptance evidence determine what can be attempted next.

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
