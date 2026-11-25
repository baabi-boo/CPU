# Initial engineering backlog

These are **repository-local tickets**, not created GitHub issues, assigned
personnel, or completed milestones. NOVA-001 execution is `blocked`; NOVA-002
through NOVA-012 remain `planned`. Preparation tooling, target source, optional
HTIF exit observation, strict schema-2 comparison, and retained-bundle verification
now exist, but no hardware ticket is complete. Owner names remain unassigned.
P0 is bring-up priority, P1 follows it,
and P2 is a later investigation. Research may overlap, but acceptance follows
the [roadmap gates](ROADMAP.md) and [requirement register](../../nova/requirements.json).

## Next exact task: NOVA-001

Run `make -f nova.mk check`, the non-mutating
`python3 -B scripts/nova/bootstrap_preflight.py --json`,
`python3 -B scripts/nova/g1_profile.py --strict --json`, and
`make -f nova.mk g1-observed-plan` in a clean checkout. A nonzero strict diagnosis
is a recorded blocker, not a reason to relax the checks. Record missing
prerequisites without attempting an unapproved installation.
Before heavyweight setup, obtain maintainer agreement on host, RAM/disk capacity,
network access, CPU parallelism, wall-time limit, and any monetary cost. The next
engineering deliverable is an implemented and validated **selective
toolchain/runtime preparation procedure**, as specified in
[DEVELOPMENT](DEVELOPMENT.md#next-nova-001-task-implement-selective-preparation).
That procedure remains unimplemented and unverified; the broad lean example
there is an inherited reference, not a fixed-G1 recipe. Preserve pins and avoid
the setup script's cleanup stage. Before selecting setup steps, compare host
glibc with the pinned `sysroot_linux-64` input:
[`scripts/build-setup.sh`](../../scripts/build-setup.sh) can rewrite
`conda-reqs/chipyard-base.yaml` and regenerate locks even without
`--use-unpinned-deps`. On a host where that rewrite would occur, stop and develop
the pin-preserving procedure or propose a separate dependency migration; do not
execute setup blindly.

Matching the selected sysroot alone is insufficient. Lean setup leaves step 2's
`--full` [initialization](../../scripts/init-submodules-no-riscv-tools-nolog.sh)
enabled for all 14 optional generators; [`build.sbt`](../../build.sbt) includes
initialized generators in the compiled source graph, and the
[fixed G1 inspector](../../scripts/nova/g1_profile.py) rejects any. Skipping
automatic Conda and submodule stages still leaves step 3's
[`build-toolchain-extra.sh`](../../scripts/build-toolchain-extra.sh), which
unconditionally initializes Gemmini/`software/libgemmini` for `riscv-tools`
and builds other extras. The selective procedure must address all three setup
stages, preserve the unchanged lock and zero optional-generator inventory, and
produce the required runtime/HTIF/observer inputs with recorded environment
activation, supplementary tools, nested dependencies, and bounded setup jobs.
No tested replacement command follows from the current diagnostics.

**Observed preparation state, 2026-11-25:** NOVA-001 execution and G1 are
**blocked**, as recorded in the
[preparation evidence](evidence/G1-PREPARATION-2026-11-12.md) and
[current observer evidence](evidence/G1-HTIF-OBSERVER-2026-11-25.md).
This checkout has 57 uninitialized gitlinks, including 21 known required for the
default Chipyard/Chisel 6 build path. The current strict G1 profile reports 38
blockers and exits 2. The older doctor's 27 blockers belong to a separate
[2026-11-11 diagnostic](evidence/NOVA-001-PREFLIGHT-2026-11-11.md).
All nine pinned Conda inputs and all gitlink pins remain unchanged. Host glibc
2.41 is not intrinsically incompatible with pinned sysroot 2.34, but the imported
automatic setup would choose 2.39 and rewrite the locks. Do not treat that path
as an unchanged-pinned reproduction. G0 acceptance, a reviewed pin-preserving
environment, and the heavy-setup resource approval remain outstanding.

The `g1_campaign.py` runner, profile/inventory inspectors, target source,
protocol assessment, optional observer, strict schema-2 comparator, and retained
raw-bundle verifier have offline regression coverage.
The declared workload set is three smoke/control programs plus twelve exact
ISA tests for each of `RocketConfig` and `NovaM1BaselineConfig`: all thirty
hardware executions remain **not run**. No simulated execution or independent
hardware reproduction is implied by a green tooling suite. The comparator
checks recorded identities, not authenticated execution.

Independent target-exit observability is implemented and exercised by twelve
native host cases using real pinned HTIF/FESVR source. Signal-only shutdown
returned `done=true` and code 0 without a target exit; the generated overlay
recorded the absent exit value and the parser rejected it. This is native host
evidence only; TestDriver PASS text and a zero host exit still do not distinguish
that path. Legacy `target_completion_verified` flags remain false. Only schema-2 nested
`target_exit.assessment` can verify a matching supplied observer event, and
neither witnesses nor hashes authenticate execution.

After environment preparation, use `--observe-target-exit` for the full
two-by-fifteen campaign in a fresh checkout. Retain raw logs, witnesses, and build
identities, verify each bundle, repeat in a second independent clean build,
compare the records, resolve the supported pinned reference-comparison scope,
and obtain a recorded maintainer decision. Fresh campaign builds reject existing
products; standalone observer Make reuse is not qualified. See the
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
- **Area:** inherited [setup](../../scripts/build-setup.sh) and [extra-toolchain](../../scripts/build-toolchain-extra.sh) behavior, `conda-reqs`, `nova/upstream-lock.json`, [fixed G1 profile](../../nova/g1-profile.json), diagnostic tooling, and the missing selective preparation procedure.
- **State:** blocked. Inspectors are implemented; selective toolchain/runtime preparation remains unimplemented and unverified, and the prepared environment and actual setup evidence are absent.
- **Acceptance:** implement and validate the selective procedure in an approved clean environment, initializing required pinned dependencies (including DRAMSim2 for the selected Verilator target) while keeping all 14 optional generators uninitialized. Record setup commands and effective resource bounds, host glibc/sysroot compatibility, resolved versions and all diagnostic gaps. No unreviewed lock/gitlink drift. The CMake `hello` test also requires an available, pinned `toolchains/libgloss` linker script and suitable HTIF-capable RISC-V toolchain. Verify that the selected compiler resolves the installed `htif.ld` to content matching the preserved source, and retain matching package metadata plus runtime-collateral and observed-mode prerequisite observations. These are test prerequisites, not evidence of execution or complete dependency closure.
- **Evidence:** `REQ-BUILD-001` / `T-BUILD-001`; exact source/gitlink manifest, SHA-256 of all nine tracked Conda inputs before/after setup, preflight report, setup command, host budget, exit status, sanitized log. Tool availability alone does not close G1.

### NOVA-002 — Execute the unmodified Rocket baseline

- **P0 · G1 · owner:** build maintainer, unassigned. **Depends on:** NOVA-001.
- **Area:** `sims/verilator`, `scripts/nova/g1_campaign.py`, `nova/g1-workloads.json`, `software/nova/baseline`, inherited `hello`, and the declared ISA subset.
- **State:** planned; runner, manifest, target source, optional HTIF observer, strict schema-2 comparison, and retained-bundle verifier are implemented, but the hardware campaign is not run.
- **Acceptance:** run a fresh `--observe-target-exit` campaign that builds `RocketConfig`, cross-compiles the inherited hello and NOVA positive/negative targets, and executes all fifteen declared workloads without silently skipping a missing binary. Retain dedicated witnesses that distinguish a target-originated terminal exit from signal-induced HTIF shutdown, alongside normal process/protocol checks; the observer's native host evidence does not qualify this simulator path. Resolve the supported pinned reference-model comparison scope and exclusions, preserve actual negative-control diagnostics, and reproduce on a second independent clean build. A passing `hello` smoke test is not ISA, exception, or MMU qualification, and its hard-coded `core 0` text is not a hart-identity observation.
- **Evidence:** `REQ-BUILD-001`, `REQ-CPU-001` / `T-BUILD-001`, `T-ISA-001`; generated RTL/map, simulator and binary hashes, exact commands/exit codes, actual memory model, raw logs and dedicated exit witnesses, observed hello/ISA results, negative failure diagnostics and exclusions. Bundle integrity and record agreement do not authenticate execution or accept G1.

### NOVA-003 — Qualify the named configuration entry points

- **P0 · G1/G2 · owner:** CPU integration lead, unassigned. **Depends on:** NOVA-002.
- **Area:** `NovaM1Configs.scala` under `generators/chipyard/src/main/scala/config`.
- **State:** planned; both aliases remain implemented but unverified source scaffolds.
- **Acceptance:** elaborate/build `NovaM1BaselineConfig` separately under G1 and rerun the same fifteen declared workload binaries with the observer and retained raw evidence, then repeat in the second independent clean build. Qualify `NovaM1MinimalConfig` separately under G2; its source selects one BOOM v3 plus one Rocket. Capture actual hart IDs and ISA/cache parameters. The single-core campaign does not complete the mixed-profile portion of this ticket.
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
