# NOVA-M1 engineering rules

NOVA-M1 is a research RISC-V SoC built on Chipyard. Read `README.md`,
`docs/nova/STATUS.md`, and the relevant subsystem specification before changing it.

## Preserve the foundation

- Keep Chipyard and dependency copyright notices, licenses, and gitlink pins.
- Keep NOVA additions isolated in `docs/nova`, `scripts/nova`, `tests/nova`,
  `nova`, and clearly named `Nova*` configuration classes where practical.
- Do not update submodules, toolchain locks, or unrelated upstream files without
  an explicit migration task and reproducibility evidence.
- Do not use force pushes, destructive git resets, or unrequested external writes.

## Engineering evidence

- Separate proposed, implemented, simulated, FPGA-validated, and silicon-measured
  capabilities. Documentation/metadata checks are not RTL or hardware validation.
- Never claim Apple instruction compatibility, Apple performance parity, measured
  energy efficiency, coherent GPU memory, or tapeout readiness without evidence.
- A Rocket/BOOM combination is a heterogeneous experiment, not a measured P/E pair.
- Trace requirements to tests and recorded evidence. Mark unrun tests as not run.
- Keep baseline and candidate comparisons on identical workload/tool configurations.
- Record failures and uncertainty; do not weaken acceptance criteria to get a pass.

## Development discipline

- Make small, reviewable changes. Use a topic branch and pull request for subsequent
  development; repository protections are an administrator setting, not this file.
- Run `make -f nova.mk check` for NOVA changes once the bootstrap tooling exists.
- Run the relevant HDL/software tests when changing hardware or target software.
- Local checks must be offline, non-destructive, and must not install dependencies.
- Keep expensive simulation, FPGA, or ASIC jobs explicit and resource-bounded.
- Do not introduce paid services, runner requirements, secrets, or device access
  without maintainer authorization.
- Parallel agents must have disjoint file ownership. Only the integrating agent
  commits, changes shared interfaces, or publishes the integrated result.
