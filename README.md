# NOVA-M1

**An open RISC-V system-on-chip research project, built on Chipyard.**

NOVA-M1 explores heterogeneous CPU clusters, shared memory, graphics, and AI
acceleration as an integrated computing platform. Its inspiration is the
system-level integration of Apple's M-series—not Apple's instruction set,
proprietary designs, software compatibility, or performance claims.

The long-term goal is a verifiable SoC architecture with reproducible simulation,
measured design trade-offs, an FPGA prototype, and a separately reviewed path
toward physical implementation.

## Current status: G1 preparation implemented; hardware qualification blocked

This repository contains the engineering foundation and tested tooling for the
first reproducible single-core campaign. **G1 remains blocked; no NOVA-specific
RTL build, CPU execution, or hardware qualification is established by this work.**

| Area | Current evidence |
| --- | --- |
| Chipyard foundation | Inherited source and pinned dependency references |
| NOVA documentation and tooling | Implemented foundation with repository-only tests; see the status record |
| G1 campaign preparation | Pinned-profile/inventory checks, target sources, bounded runner, and evidence comparison implemented; hardware campaign not run |
| NOVA configuration classes | Source scaffolds; HDL elaboration and execution unverified |
| Mixed-core correctness and Linux boot | Not yet demonstrated for NOVA |
| GPU/NPU integration and coherent accelerator memory | Planned, not validated integrations |
| FPGA, ASIC, power, and performance results | No NOVA measurements or qualification |

See [STATUS](docs/nova/STATUS.md) for the authoritative evidence state and
[ROADMAP](docs/nova/ROADMAP.md) for milestone acceptance criteria. Passing
repository checks does **not** establish processor correctness, achieved clock
frequency, energy efficiency, or tapeout readiness.

**Next hardware task: NOVA-001 (blocked).** The first goal is a reproducible,
pinned Rocket toolchain and then a genuine single-core simulation. The current
bootstrap host lacks required toolchain dependencies. Its upstream automatic
glibc/sysroot selection would regenerate pinned Conda locks; this does not show
that the newer host glibc is intrinsically incompatible with the preserved
sysroot. G0 still needs maintainer acceptance, and heavyweight setup requires an
approved host/resource/network/time/cost budget.
No Rocket/NOVA CPU execution has been demonstrated by these tooling changes;
see the [current G1 preparation record](docs/nova/evidence/G1-PREPARATION-2026-11-12.md).

The implemented campaign declares 15 workloads for each of `RocketConfig` and
`NovaM1BaselineConfig`: hello, an eight-check NOVA target, its deliberate failure
control, and 12 ISA tests. These hardware runs remain **not run**. The pinned
simulator's success signal can also follow HTIF signal-induced shutdown, so
observing its completion protocol is not independently verified target exit;
see the [completion-protocol finding](docs/nova/evidence/G1-COMPLETION-PROTOCOL-2026-11-12.md).

## Architecture direction

| Subsystem | Initial approach | Engineering boundary |
| --- | --- | --- |
| CPU complex | Rocket baseline, then a BOOM v3 + Rocket configuration | Reuse upstream cores first; validate every hart |
| Memory system | Chipyard coherent CPU interconnect and shared-cache infrastructure | Record the generated map and actual simulation model |
| AI acceleration | Investigate Gemmini integration | Require numerical correctness and a defined memory contract |
| GPU | Evaluate an open GPU, including Vortex | Selection, integration, drivers, and coherence remain research work |
| Platform | Boot firmware, interrupts, debug, and basic I/O | Establish reproducible bare-metal execution before system expansion |
| Power and physical design | Later FPGA and technology-specific ASIC studies | FPGA operation and estimated power are not measured ASIC performance |

BOOM and Rocket are candidate roles for heterogeneous computing. They are not
a demonstrated Apple-like performance/efficiency pair. In particular, the
inherited mixed-core configuration uses a large Rocket configuration; calling it
an “efficiency core” requires area, power, and workload evidence.

Shared physical DRAM is only one part of a unified-memory design. CPU–GPU
coherence, DMA ownership, address translation, isolation, and driver behavior
must each be specified and tested.

Read the [architecture specification](docs/nova/ARCHITECTURE.md) and
[project charter](docs/nova/CHARTER.md) before changing the design.

## Initial configuration scaffolds

These names establish stable NOVA entry points while minimizing upstream
divergence. They do not represent original CPU microarchitectures.

| Configuration | Upstream basis | Intended use |
| --- | --- | --- |
| `NovaM1BaselineConfig` | `RocketConfig` | Single-core build and execution baseline |
| `NovaM1MinimalConfig` | `LargeBoomAndRocketConfig` | One BOOM v3 + one Rocket heterogeneous experiment |

**Both NOVA configurations are unverified until their elaboration and execution
evidence is recorded.** A successful Scala compilation would not, by itself,
qualify either configuration.

## Getting started

Clone the project without initializing every optional hardware dependency:

```bash
git clone https://github.com/baabi-boo/CPU.git nova-m1 &&
cd nova-m1 &&
make -f nova.mk check
```

The lightweight check target is intended for repository metadata, documentation,
and project-tool tests. It does not install a hardware toolchain or simulate a
processor. Its result must be kept separate from hardware validation.

Inspect the current host and the proposed two-configuration campaign without
installing dependencies or starting a simulation:

```bash
make -f nova.mk preflight
make -f nova.mk g1-profile
make -f nova.mk conda-plan
make -f nova.mk g1-campaign-plan
```

These commands report setup risks, known prerequisites, the preserved package
inventory, and an execution plan only. A ready profile is not complete dependency
closure, permission to install, or proof that the hardware builds. The unchanged
lean lock contains 165 package records; metadata agreement does not authenticate
installed binaries or supply missing CMake/HTIF/runtime prerequisites.

For toolchain preparation, diagnostic preflight, source configurations, and
explicit simulation commands, follow [DEVELOPMENT](docs/nova/DEVELOPMENT.md).
Expensive simulation, FPGA, and ASIC jobs are opt-in and resource-bounded.
The campaign does not provision a toolchain or initialize submodules; an explicit
sbt build can still resolve JVM dependencies under the approved network budget.

The first hardware milestone is a reproducible Rocket baseline. The next is
the mixed-core configuration with verified hart IDs, per-hart execution,
interrupts, reset behavior, atomic operations, and memory coherence. A test
that runs only on hart 0 cannot qualify a heterogeneous system.

## Engineering documentation

- [Complete documentation index](docs/nova/README.md): subsystem specifications,
  development workflow, evidence templates, and the first-contribution route.
- [Charter and scope](docs/nova/CHARTER.md): goals, non-goals, and success criteria.
- [Roadmap](docs/nova/ROADMAP.md): gated deliverables and go/no-go decisions.
- [Architecture](docs/nova/ARCHITECTURE.md): subsystem contracts and design boundaries.
- [Development guide](docs/nova/DEVELOPMENT.md): reproducible local workflow.
- [G1 baseline campaign runbook](docs/nova/BASELINE_RUNBOOK.md): NOVA-001 setup
  blockers, the two-configuration workload sequence, resource approval, and
  evidence/reproduction requirements.
- [Verification strategy](docs/nova/VERIFICATION.md): requirements, tests, and evidence.
- [Status](docs/nova/STATUS.md): what is planned, implemented, and demonstrated.
- [Bootstrap review](docs/nova/BOOTSTRAP_REVIEW.md): review scope, executed checks,
  findings, and remaining qualification limits.
- [Contributing](CONTRIBUTING.md): review, change control, and attribution rules.

A capability claim must identify its revision, configuration, dependencies,
commands, result, and reviewable artifacts. Simulation, FPGA validation, and
silicon measurements are separate evidence levels.

## Contributing and reporting problems

Use small topic branches and pull requests, preserve dependency pins, and include
test evidence and known limitations. Read [CONTRIBUTING](CONTRIBUTING.md) and
[AGENTS](AGENTS.md) before working in the repository.

Report NOVA-specific problems in [this repository's issue tracker](https://github.com/baabi-boo/CPU/issues).
Do not send unisolated NOVA integration problems to upstream projects.

## Chipyard provenance and licensing

NOVA-M1 starts from [UC Berkeley Chipyard](https://github.com/ucb-bar/chipyard)
at commit `a7946ede9bd625204435715dc40c750e2f8a251f`.
The original [Chipyard README](README.chipyard.md), including its acknowledgements
and research bibliography, is preserved. The existing [LICENSE](LICENSE),
[LICENSE.SiFive](LICENSE.SiFive), and dependency notices remain applicable to
their respective materials; the root license is not a blanket license for all
submodules.

See [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md) for attribution and dependency
provenance. The [Chipyard documentation](https://chipyard.readthedocs.io/) is a
reference for the underlying framework; pinned source and NOVA evidence govern
this project's claims.

NOVA-M1 is independent of Apple. “M-series-inspired” describes a research
direction, not affiliation, endorsement, Arm/macOS compatibility, or a promise
of comparable performance.
