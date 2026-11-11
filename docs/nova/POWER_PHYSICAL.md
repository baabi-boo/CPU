# Power and physical implementation

## Status and scope

This document defines future implementation work. NOVA has no qualified FPGA
profile, implemented DVFS policy, measured power result, or ASIC signoff evidence.
The inherited simulation harness and clock-frequency parameters are not a
physical implementation. See [STATUS](STATUS.md) and [ARCHITECTURE](ARCHITECTURE.md).

G7 qualifies a specific FPGA profile; G8 investigates a specified ASIC technology.
Neither gate implies authorization to order hardware or fabricate silicon.
Board, process node, operating frequency, voltage, package, and power targets
remain decisions requiring feasibility evidence—not promises in this plan.

## FPGA selection and capacity gate

Before acquiring or selecting a board, record an architecture decision containing:

- Exact board revision, FPGA part, accessible memory, clock sources, I/O, debug,
  programming interface, tool/version requirements, and permitted IP licenses.
- The selected NOVA profile and included/excluded CPU, GPU, and NPU blocks.
- Synthesis estimates for LUTs, registers, block RAM, DSPs, clock resources, and
  routing pressure; reserve explicit headroom approved by the implementation lead.
- Memory capacity/bandwidth needs, boot storage, host interface, and software stack.
- Tool, board, accessory, runtime, and access costs with maintainer authorization.

An upstream board shell is only a candidate integration. Fit and timing must be
established for the exact NOVA design. If the full system does not fit, define a
named reduced profile and its validation limits; do not present that result as
qualification of omitted cores or accelerators. No procurement is implicit here.

## Clock, reset, and timing contract

Maintain an inventory of domains, sources, generated clocks, reset polarity,
reset assertion/deassertion behavior, crossings, and domain dependencies.
Constraints must cover real external interfaces, clock uncertainty, input/output
delays, and asynchronous relationships. Review every false-path and multicycle
exception against a design justification; exceptions must not hide failing paths.

Qualify CDC/RDC structures and reset sequencing, including reset during traffic,
stopped clocks, wake-up, memory initialization, and accelerator completion.
Require no unexplained unconstrained paths, timing failures, or crossing warnings.
Record tool coverage and reviewed waivers rather than treating a quiet report as
proof of safety. FPGA implementations use supported clock-control resources;
simulation clock models are not physical clock networks.

The board acceptance run must reproduce the bitstream, boot repeatedly, verify
every included hart, stress physical memory, and exercise interrupts, backpressure,
faults, and recovery. Keep the bitstream hash, constraints, timing/utilization
reports, firmware image hashes, and instrumented board logs together.

## Physical memory and I/O boundary

The current AXI interface and SimDRAM harness do not supply a qualified DDR/LPDDR
controller, PHY, or package interface. A real platform needs a compatible
controller/PHY pair, initialization and training firmware, clocking, calibration,
pinout, electrical constraints, and supported memory devices.

Specify capacity, channels, address mapping, refresh, error handling, reset, and
any claimed ECC behavior. Validate data integrity across address/data patterns,
bursts, contention, and recovery using the board's documented operating limits.
An FPGA vendor memory IP result does not qualify an ASIC PHY implementation.
ASIC memory and I/O require technology-specific IP rights, characterization,
integration views, and appropriate physical/electrical signoff ownership.

## Power architecture and measurement

Clock gating, power domains, retention, isolation, voltage/frequency transitions,
and software power policy are future features, not consequences of mixing cores.
Before implementation, define legal states and transitions, idle detection,
outstanding-transaction draining, wake sources, reset behavior, retained state,
isolation sequencing, and firmware responsibilities. Verify transitions under
CPU/DMA contention and faults; do not lose interrupts or silently corrupt state.

Any DVFS study must specify regulator/clock support, safe operating points,
transition latency, dependencies, and the enforcement mechanism. A changed
simulation clock parameter is not a validated voltage or power transition.

| Evidence class | Required method | Claim boundary |
| --- | --- | --- |
| Simulation activity | Workload, duration, toggles/counters, memory model | Activity or cycles, not watts |
| FPGA measurement | Named rail/board boundary, instrument, calibration, idle baseline, sampling and workload | FPGA/board power only |
| ASIC estimate | Technology/library corners, voltage, temperature, parasitics, activity coverage, tool and assumptions | Estimated silicon power |
| Manufactured silicon | Device/sample identity, rails, instrumentation, voltage/temperature, workload and uncertainty | Measured results for tested samples |

Report leakage/dynamic contributions where available, full-system boundaries,
transfer overhead, throughput, and energy per completed correct workload.
Keep baseline/candidate methodology matched. FPGA watts cannot establish ASIC
efficiency, and no such result establishes Apple parity without a valid comparison.

## ASIC feasibility and signoff gate

Freeze the RTL/configuration, PDK revision, standard-cell libraries, SRAM macros,
I/O cells, controller/PHY IP, tool versions, and permitted artifact-distribution
scope. Document missing views or restricted assets; do not substitute generic
models for foundry-qualified implementation evidence.

The implementation plan must assign responsible review roles for:

- Synthesis, equivalence strategy, floorplan, macro placement, power distribution,
  clock-tree synthesis, routing, extracted parasitics, and multi-corner timing.
- Setup/hold closure, CDC/RDC, physical rule checking (DRC), layout-versus-schematic
  checking (LVS), antenna/electrical checks, and unresolved tool limitations.
- Power integrity, IR drop, electromigration, package/board interfaces, thermal
  assumptions, cooling, and operating-envelope analysis.
- DFT strategy, scan/memory test where applicable, test coverage, manufacturing
  test access, bring-up observability, and post-silicon validation plans.

Archive reports and explicitly list every unavailable or incomplete signoff item.
Generating a layout or passing one tool does not make a design tapeout-ready.
Fabrication requires a separate G9 decision covering authorized IP/foundry access,
budget, packaging, test, logistics, responsible reviewers, and residual risks.

## Requirements and acceptance evidence

| Requirement | Tests | Required acceptance evidence |
| --- | --- | --- |
| `REQ-FPGA-001` | `T-FPGA-001`, `T-CDC-001` | Exact board/profile, reproducible bitstream, timing and crossings review, physical execution logs |
| `REQ-PHY-001` | `T-PHY-001` | Selected memory/I/O IP, constraints, training/calibration records, sustained data-integrity and recovery results |
| `REQ-PWR-001` | `T-POWER-001` | Implemented state machine and transition tests; explicitly classified power evidence |
| `REQ-ASIC-001` | `T-ASIC-001` | Pinned technology flow, constraints, reports, signoff owners and all unresolved gaps |
| `REQ-REL-002` | `T-AUTH-001` | Research release: explicit no-fabrication-authorization record. Fabrication proposal: separate documented authorization and signoff review |

All tests above are planned. Store revisions, commands, workload hashes, seeds,
limits, expected/observed outcomes, and reviewable artifacts under the
[verification plan](VERIFICATION.md). Update [project state](../../nova/project.json)
only when the claimed evidence level is actually achieved.
