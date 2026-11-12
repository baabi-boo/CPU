# Initial engineering backlog

These are **repository-local tickets**, not created GitHub issues, assigned
personnel, or completed milestones. NOVA-001 execution is `blocked`; NOVA-002
through NOVA-012 remain `planned`. Preparation tooling and target source now
exist, but no hardware ticket is complete. Owner names remain unassigned.
P0 is bring-up priority, P1 follows it,
and P2 is a later investigation. Research may overlap, but acceptance follows
the [roadmap gates](ROADMAP.md) and [requirement register](../../nova/requirements.json).

## Next exact task: NOVA-001

Run `make -f nova.mk check`, the non-mutating
`python3 -B scripts/nova/bootstrap_preflight.py --json`,
`python3 -B scripts/nova/g1_profile.py --strict --json`, and
`make -f nova.mk g1-campaign-plan` in a clean checkout. A nonzero strict diagnosis
is a recorded blocker, not a reason to relax the checks. Record missing
prerequisites without attempting an unapproved installation.
Before heavyweight setup, obtain maintainer agreement on host, RAM/disk capacity,
network access, CPU parallelism, wall-time limit, and any monetary cost. Then use
the pinned, opt-in procedure in [DEVELOPMENT](DEVELOPMENT.md); preserve pins and
disable the setup script's cleanup stage as documented there. Before running
upstream setup, compare host glibc with the pinned `sysroot_linux-64` input:
`scripts/build-setup.sh` can rewrite `conda-reqs/chipyard-base.yaml` and
regenerate locks even without `--use-unpinned-deps`. On a host where that
rewrite would occur, stop and select a reviewed pin-preserving procedure or
propose a separate dependency migration; do not execute setup blindly.

**Observed preparation state, 2026-11-12:** NOVA-001 execution and G1 are
**blocked**, as recorded in the
[current preparation evidence](evidence/G1-PREPARATION-2026-11-12.md).
This checkout has 57 uninitialized gitlinks, including 21 known required for the
default Chipyard/Chisel 6 build path. The new strict G1 profile reports 38
blockers and exits 2. The older doctor's 27 blockers belong to a separate
[2026-11-11 diagnostic](evidence/NOVA-001-PREFLIGHT-2026-11-11.md).
All nine pinned Conda inputs and all gitlink pins remain unchanged. Host glibc
2.41 is not intrinsically incompatible with pinned sysroot 2.34, but the imported
automatic setup would choose 2.39 and rewrite the locks. Do not treat that path
as an unchanged-pinned reproduction. G0 acceptance, a reviewed pin-preserving
environment, and the heavy-setup resource approval remain outstanding.

The new `g1_campaign.py` runner, profile/inventory inspectors, target source,
protocol assessment, and record comparator have offline regression coverage.
The declared workload set is three smoke/control programs plus twelve exact
ISA tests for each of `RocketConfig` and `NovaM1BaselineConfig`: all thirty
hardware executions remain **not run**. No simulated execution or independent
hardware reproduction is implied by a green tooling suite. The comparator
checks recorded identities, not authenticated execution.

Before accepting positive workload completion, add and validate independent
target-exit observability. Source review found that pinned HTIF can report zero
success after signal-induced shutdown without a target exit; TestDriver PASS
text and a zero host exit do not distinguish that path. Current positive records
therefore keep `target_completion_verified: false`. This finding has not been
reproduced in a CPU simulation here. After environment preparation, execute both
profiles, repeat in a second clean checkout, resolve the supported pinned
reference-comparison scope, and obtain a recorded maintainer decision. See the
[baseline runbook](BASELINE_RUNBOOK.md) for exact commands and evidence limits.

Record the superproject revision, all gitlink pins, and SHA-256 hashes of the
nine tracked Conda definition/lock inputs before and after any approved setup.
Confirm the selected pinned package versions and tool availability. The Rocket
Verilator target unconditionally builds `tools/DRAMSim2/libdramsim.a`, while the
repository's CMake `hello` target uses `tests/htif.ld` linked into
`toolchains/libgloss`. Both dependency paths must be available at their
recorded pins before the corresponding build/test; passing a prerequisite
diagnostic is not itself proof that all nested build inputs are present.

Stop and record `blocked` on missing authorization/access, exhausted resources,
unexpected dependency changes, unavailable required IP, or inconsistent tool
versions. A failed command or timeout must retain its exit status and diagnostics.
Do not replace a pinned dependency, suppress a mismatch, or loosen a gate merely
to obtain a green result. No FPGA purchase or paid runner is authorized here.

## Bring-up tickets

### NOVA-001 — Reproduce the pinned Rocket toolchain

- **P0 · G1 · owner:** build maintainer, unassigned. **Depends on:** G0 acceptance and resource approval.
- **Area:** `scripts/build-setup.sh`, `conda-reqs`, `nova/upstream-lock.json`, diagnostic tooling.
- **State:** blocked. Inspectors are implemented; the prepared environment and actual setup evidence are absent.
- **Acceptance:** an approved clean environment initializes the required pinned dependencies (including DRAMSim2 for the selected Verilator target); record host glibc/sysroot compatibility, resolved versions and all diagnostic gaps. No unreviewed lock/gitlink drift. The CMake `hello` test also requires an available, pinned `toolchains/libgloss` linker script and suitable HTIF-capable RISC-V toolchain. Verify that the selected compiler resolves the installed `htif.ld` to content matching the preserved source, and retain matching package metadata plus runtime-collateral observations. These are test prerequisites, not evidence of execution or complete dependency closure.
- **Evidence:** `REQ-BUILD-001` / `T-BUILD-001`; exact source/gitlink manifest, SHA-256 of all nine tracked Conda inputs before/after setup, preflight report, setup command, host budget, exit status, sanitized log. Tool availability alone does not close G1.

### NOVA-002 — Execute the unmodified Rocket baseline

- **P0 · G1 · owner:** build maintainer, unassigned. **Depends on:** NOVA-001.
- **Area:** `sims/verilator`, `scripts/nova/g1_campaign.py`, `nova/g1-workloads.json`, `software/nova/baseline`, inherited `hello`, and the declared ISA subset.
- **State:** planned; runner, manifest, assessment, and target source are implemented, but the hardware campaign is not run.
- **Acceptance:** build `RocketConfig`, cross-compile the inherited hello and NOVA positive/negative targets, and execute all fifteen declared workloads without silently skipping a missing binary. Independently distinguish a target-originated terminal exit from signal-induced HTIF shutdown; the current completion-protocol parser alone cannot do this. Resolve the supported pinned reference-model comparison scope and exclusions, preserve actual negative-control diagnostics, and reproduce on a second clean build. A passing `hello` smoke test is not ISA, exception, or MMU qualification, and its hard-coded `core 0` text is not a hart-identity observation.
- **Evidence:** `REQ-BUILD-001`, `REQ-CPU-001` / `T-BUILD-001`, `T-ISA-001`; generated RTL/map, simulator and binary hashes, exact commands/exit codes, actual memory model, observed hello/ISA results, negative failure diagnostics and exclusions.

### NOVA-003 — Qualify the named configuration entry points

- **P0 · G1/G2 · owner:** CPU integration lead, unassigned. **Depends on:** NOVA-002.
- **Area:** `NovaM1Configs.scala` under `generators/chipyard/src/main/scala/config`.
- **State:** planned; both aliases remain implemented but unverified source scaffolds.
- **Acceptance:** elaborate/build `NovaM1BaselineConfig` separately under G1 and rerun the same declared workload binaries with retained evidence. Qualify `NovaM1MinimalConfig` separately under G2; its source selects one BOOM v3 plus one Rocket. Capture actual hart IDs and ISA/cache parameters. The single-core campaign does not complete the mixed-profile portion of this ticket.
- **Evidence:** `REQ-BUILD-001`, `REQ-CPU-002` / `T-BUILD-001`, `T-HART-001`; generated inventory and logs. Elaboration does not establish execution.

### NOVA-004 — Implement a bounded two-hart smoke test

- **P0 · G2 · owner:** CPU verification lead, unassigned. **Depends on:** NOVA-003.
- **Area:** a new NOVA target program and simulator harness; review inherited `tests/mt-hello.c` only as a reference.
- **Acceptance:** both expected harts report identity and unique completion; missing/duplicate participants fail within a declared timeout. Do not use the inherited four-hart barrier unchanged.
- **Evidence:** `REQ-CPU-002` / `T-HART-001`, `T-RESET-001`; positive and injected-failure logs, participant mapping, reset and interrupt observations.

### NOVA-005 — Add per-hart architectural differential checking

- **P0 · G2 · owner:** CPU verification lead, unassigned. **Depends on:** NOVA-004.
- **Area:** NOVA trace/cosimulation composition, pinned reference-model adapter, per-hart test selection.
- **Acceptance:** compare supported instruction, trap, and privilege behavior for each hart; injected register/trap mismatches are detected. Enumerate unsupported cases rather than filtering them silently.
- **Evidence:** `REQ-CPU-001`, `REQ-CPU-002` / `T-ISA-001`, `T-RESET-001`; reference versions, seeds, comparison scope, traces and exclusions. Hart-0-only suites are insufficient.

### NOVA-006 — Stress atomics, ordering, and CPU coherence

- **P0 · G3 · owner:** memory verification lead, unassigned. **Depends on:** NOVA-004; G2 acceptance before G3 closure.
- **Area:** shared-cache test workloads, memory-model configuration, timeout diagnostics.
- **Acceptance:** dirty-line exchange, false sharing, eviction, LR/SC, contended atomics, publication and declared litmus tests pass with bounded system progress under stated assumptions.
- **Evidence:** `REQ-MEM-002` / `T-COH-001`, `T-ORDER-001`; allowed/observed outcomes, seeds, traces, memory model and negative tests.

### NOVA-007 — Freeze the generated map and firmware handoff contract

- **P0 · G3 · owner:** platform software lead, unassigned. **Depends on:** NOVA-003 and G2 acceptance.
- **Area:** elaborated device tree/map, boot ROM, firmware configuration, timer/interrupt and UART descriptions.
- **Acceptance:** no unexplained region overlaps or mismatched permissions/cacheability; firmware agrees with actual hart inventory and secondary-hart startup protocol.
- **Evidence:** `REQ-MEM-001`, `REQ-PLAT-001` / `T-MAP-001`, `T-LINUX-001`; reviewed generated artifacts, firmware source/build hashes and handoff record.

### NOVA-008 — Reproduce mixed-hart Linux SMP boot

- **P1 · G3 · owner:** platform software lead, unassigned. **Depends on:** NOVA-006 and NOVA-007.
- **Area:** explicitly selected firmware/Linux workload flow; lean bootstrap does not prepare FireMarshal.
- **Acceptance:** repeated cold/warm boots enumerate both harts, schedule work on each, match devices to the generated map, and recover through declared reboot/fault tests.
- **Evidence:** `REQ-PLAT-001` / `T-LINUX-001`; reproducible images, console logs, per-hart workload results, timeouts and known limitations.

## Controlled extensions

### NOVA-009 — Evaluate one original CPU architecture change

- **P1 · G4 · owner:** CPU architecture lead, unassigned. **Depends on:** G2; NOVA-008 for OS workloads.
- **Area:** one separately named experimental configuration or owned microarchitecture change, counters and benchmark harness.
- **Acceptance:** a reviewed ADR states a falsifiable bottleneck hypothesis; matched baseline/candidate experiments retain correctness and publish regressions as well as improvements.
- **Evidence:** `REQ-CPU-004` / `T-CPU-PERF-001`, `T-ISA-001`; follow [BENCHMARKS](BENCHMARKS.md). Any power or energy-efficiency claim additionally requires `REQ-PWR-001` / `T-POWER-001` evidence at that time, not only at G8.

### NOVA-010 — Define and prototype Gemmini integration

- **P1 · G5 · owner:** accelerator integration lead, unassigned. **Depends on:** G3; a bounded standalone research spike may precede integration.
- **Area:** pinned Gemmini configuration/runtime, per-hart RoCC attachment, opcode allocation and memory ownership.
- **Acceptance:** a reviewed interface contract precedes integration; reference-checked kernels cover shapes, overflow, dirty buffers, completion, faults and recovery, followed by one end-to-end inference case.
- **Evidence:** `REQ-NPU-001`, `REQ-NPU-002` / `T-NPU-NUM-001`, `T-NPU-MEM-001`, `T-DMA-001`; standalone upstream results do not close G5.

### NOVA-011 — Select a GPU and prove an integration path

- **P1 · G6 · owner:** GPU integration lead, unassigned. **Depends on:** G3 for integrated acceptance; candidate investigation may run earlier.
- **Area:** Radiance/Vortex candidate review, bridge, driver/runtime, command completion and shared-buffer contract.
- **Acceptance:** compare pinned candidates and resource/license constraints in an ADR; demonstrate integrated reference-checked compute with error recovery. Qualify graphics separately if supported.
- **Evidence:** `REQ-GPU-001`, `REQ-DMA-001` / `T-GPU-EXEC-001`, `T-DMA-001`; dirty-cache exchanges and declared coherence mode, not shared-address assumptions.

### NOVA-012 — Select a feasible FPGA profile without purchasing prematurely

- **P2 · G7 · owner:** FPGA integration lead, unassigned. **Depends on:** G2/G3 and included accelerator gates for board qualification.
- **Area:** board/part comparison, resource estimates, clock/reset constraints, memory-controller/PHY and boot plan.
- **Acceptance:** review fit, tool/IP access, omitted features and costs before authorizing acquisition or synthesis; later close timing and execute the profile on the named real board.
- **Evidence:** `REQ-FPGA-001`, `REQ-PHY-001`, `REQ-SEC-001` / `T-FPGA-001`, `T-CDC-001`, `T-PHY-001`, `T-ISOLATION-001`; distinguish planning estimates from observed hardware results.

Every completed ticket links a scoped record under the [evidence process](REPRODUCIBILITY.md)
and updates the requirement/test register through review. Ticket completion is not
automatic gate acceptance. ASIC feasibility and fabrication remain separate G8/G9
work under [POWER_PHYSICAL](POWER_PHYSICAL.md) and [RELEASES](RELEASES.md).
