# Verification and evidence plan

This is the qualification plan, not a hardware test report. Only the repository
check is available as a complete registered campaign in the
[test register](../../nova/requirements.json). G1 preparation, execution, and
record-comparison tooling is implemented, but the hardware descriptors remain
planned: their complete qualification campaigns have not been demonstrated.
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

## G1 Rocket baseline: implemented preparation, unrun qualification

The [baseline runbook](BASELINE_RUNBOOK.md) defines the approved-host procedure;
the [preparation record](evidence/G1-PREPARATION-2026-11-12.md) records the current
blockers. The opt-in [G1 campaign runner](../../scripts/nova/g1_campaign.py)
implements a fixed two-configuration observation campaign. Its offline tests
are not a completed `T-BUILD-001` or `T-ISA-001` campaign. Both descriptors remain
**planned**, and no result from this tooling automatically accepts G1.

The [workload manifest](../../nova/g1-workloads.json) requires 15 workloads for
each of `RocketConfig` and `NovaM1BaselineConfig`: 14 positive expectations
(`hello`, the eight-check NOVA target, and 12 named ISA tests), plus the deliberate
code-7 failure target. Each simulator is built separately; both configurations
must use identical workload binary hashes. A missing workload blocks completion;
it cannot become an empty wildcard, a silent skip, or accepted coverage.

1. **Preflight and preserve pins (`NOVA-001`, `T-BUILD-001`).** Record G0
   acceptance and approval for the host, RAM, disk, network, parallel jobs,
   time, and cost. Inspect `make -f nova.mk check`, `make -f nova.mk preflight`,
   `make -f nova.mk g1-profile-strict`, and `make -f nova.mk g1-campaign-plan`
   before execution. Require the declared Chisel-6 profile, expected source
   graph, tool/version observations, HTIF/FESVR runtime collateral, and matching
   pinned Conda metadata. The installed `htif.ld` must match the pinned libgloss
   source. `ready` and `matched` establish only their enumerated checks, not
   trustworthy installed binary contents, nested/Maven dependency closure, or
   actual build compatibility. Retain all nine Conda input hashes before and
   after setup. Stop before any unreviewed sysroot/lock rewrite; automatic
   setup selection is not proof that the original sysroot is incompatible.
2. **Build both configurations (`NOVA-002`, baseline part of `NOVA-003`).**
   Execute only the runner from its own prepared clean checkout, using the
   separately approved budget. It does not provision a toolchain or initialize
   submodules; invoked build tools may still resolve JVM dependencies under the
   approved network policy. Retain configuration-specific simulator, generated
   RTL, DTS, and metadata hashes. Structural ELF checks and readable DTS/JSON
   are not semantic validation of the address map, hart inventory, ISA/cache
   parameters, or memory model. Review those generated properties separately,
   including the actual DRAMSim2 configuration. Elaboration is not execution.
3. **Observe positive workloads without overstating completion.** The runner
   invokes each simulator directly, retaining its actual exit status and
   separate, bounded stdout/stderr. Positive assessment requires a zero host
   exit, one valid TestDriver completion record within the cycle bound, the
   exact target record where required, and no conflicting terminal/failure
   records. The inherited hello line is hard-coded; it does not measure a hart
   ID. A matching result sets `completion_protocol_observed: true` but keeps
   `target_completion_verified: false`. The pinned HTIF path can produce its
   success signal after `signal_exit` without a target-originated exit value.
   This is a [source-level finding](evidence/G1-COMPLETION-PROTOCOL-2026-11-12.md),
   not a reproduced CPU run. Independent observation of a real target terminal
   event remains required before claiming successful target completion.
4. **Exercise the deliberate failure and harness rejection cases.** The NOVA
   negative target reaches code 7 only after its eight checks. Its observation
   contract requires the exact negative marker, exactly one matching SimTSI
   code-7 assertion, and an ordinary supported nonzero simulator result. Host
   exit status is not assumed to equal target exit code 7. A generic crash,
   timeout, interruption, log-integrity fault, conflicting output, or surviving
   child is not the expected negative outcome. The parser's supported diagnostic
   formats have synthetic-fixture coverage; their actual pinned-simulator
   output still needs observation. This control does not qualify a differential
   reference adapter or prove that injected architectural mismatches are detected.
5. **Qualify the declared architectural scope (`T-ISA-001`).** Preserve the
   exact 12 ISA binary identities, expected outcomes, tested privilege profile,
   reference-model version and comparison scope, exclusions, and per-test
   results. Requiring every listed binary is not proof that each internal
   conditional test path ran. F/D/A/C, MMU, full ISA certification,
   per-instruction differential checking, and heterogeneous execution are not
   qualified by this manifest; incidental runtime instructions do not change
   those exclusions. Spike comparison remains `not_run` with unresolved scope.
   Complete and review the applicable reference/negative comparisons before
   closing the registered descriptor.
6. **Reproduce and review.** Repeat the complete build and workload campaign in
   a second clean checkout with the same declared inputs. Do not reuse generated
   simulators or targets. The runner rejects known stale products and checks
   pre/post source, profile, inventory, binary, simulator, and log identities;
   it does not prove that every ignored or external cache was isolated. The
   [record comparator](../../scripts/nova/compare_campaigns.py) checks metadata
   agreement and contradictions. `consistent` means recorded identities agree,
   not authenticated execution, independent builds, or reproduced hardware.
   Distinct checkout identifiers alone do not establish cache independence.

The campaign's strongest automatic outcome is `workloads_observed`, with
`hardware_qualified: false`, `g1_gate_passed: false`, and reference comparison
`not_run`. `blocked`/`failed` attempts retain unrun rows when the plan was
available; no unrun row is accepted. `hello_marker_observed_unqualified` from
the older [Rocket helper](../../scripts/nova/rocket_baseline.py) remains a still
narrower, single-configuration observation, not an alternative G1 pass.

Use the [record contract](REPRODUCIBILITY.md) to preserve actual commands,
declared working directories, monotonic durations, UTC timestamps, resource
limits, seed, raw and sanitized logs, hashes, failures, and reviewer decisions.
Sampled disk/log checks and process-group cleanup are not hard RAM/disk quotas
or an instantaneous whole-process deadline. Evidence capture can overrun the
aggregate acceptance budget, in which case the campaign is not accepted.
Only complete, executed, reproduced, and reviewed test scope can change the
registered state; maintainer gate acceptance remains separate.

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
