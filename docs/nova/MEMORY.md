# Memory, coherence, and accelerator ownership

## Status and inherited baseline

This specification defines qualification work, not completed memory validation.
See [STATUS](STATUS.md), [ARCHITECTURE](ARCHITECTURE.md), and the structured
[requirements register](../../nova/requirements.json).

At baseline commit `a7946ede9bd625204435715dc40c750e2f8a251f`,
[`AbstractConfig.scala`](../../generators/chipyard/src/main/scala/config/AbstractConfig.scala)
selects the following source-level facilities:

| Facility | Pinned selection | Qualification boundary |
| --- | --- | --- |
| CPU fabric | `WithCoherentBusTopology` | Coherent hierarchy selected; NOVA transactions untested |
| Last-level cache | `WithInclusiveCache` | Generated capacity, banks, line size, and clients must be recorded |
| Backing-memory interface | `WithNMemoryChannels(1)` | One AXI4 channel; not a physical DDR controller or PHY |
| Simulation backing memory | `WithBlackBoxSimMem` / SimDRAM | Record actual elaborated model and timing parameters |
| On-chip scratchpad | `WithMbusScratchpad`, 64 KiB at `0x08000000` | Source default, not a substitute for the complete generated map |

The mixed-core configuration selects a 128-bit system bus. Neither that width nor
the inherited bus-frequency parameters establish measured memory bandwidth.
Older upstream prose describing single-cycle `SimAXIMem` must not override the
selected source/harness model. Simulated memory and physical DDR/LPDDR remain
separate targets with separate evidence.

Before increasing the channel count, audit per-channel address mapping. The
pinned [harness](../../generators/chipyard/src/main/scala/harness/HarnessBinders.scala)
contains an upstream TODO noting that each SimDRAM currently contains the entire
memory space. A multi-channel parameter change therefore requires explicit
mapping, aliasing, and cross-channel traffic tests, not an assumed bandwidth gain.

## Authoritative map and access contract

For every qualified configuration, generate and archive the address map and device
tree with the elaborated RTL. Review them together with firmware and drivers.
The map must identify:

- Region base, extent, alignment, address width, aliasing, and overlap checks.
- Owning device, access sizes, cacheability, executable permissions, and privilege.
- Reset contents, reserved regions, boot storage, scratchpads, DRAM, and MMIO.
- Atomic-operation support and unsupported or misaligned access behavior.
- Every bus master that can access a region, including debug and future DMA.

No driver may rely on an unreviewed example address. A map change requires impact
review across RTL, firmware, device tree, drivers, tests, and documentation.
Reserve future accelerator apertures only through a reviewed interface decision;
this document does not allocate them.

## CPU coherence is not memory ordering

Coherence governs visibility of individual cache lines. Architectural ordering
governs relationships among operations and synchronization across harts. Verify
both against the declared RISC-V profile and its applicable memory model.

The CPU contract must cover dirty-line ownership, eviction/writeback, false
sharing, atomics, LR/SC behavior, acquire/release publication, fences, and
instruction-cache synchronization after executable-memory changes. Coherent
hardware does not remove software synchronization requirements. Hart-0-only
execution does not qualify the two-hart memory system.

Test forward progress under documented fairness assumptions and bounded timeouts.
Record stalled transactions and participating harts when a timeout occurs; do not
silently increase limits until a failing workload appears to pass.

## GPU, NPU, and DMA integration contract

Each accelerator port must declare its coherence mode before integration. Sharing
physical RAM, using AXI, or sharing a software pointer does not establish CPU–GPU
coherence, shared virtual addressing, or isolation.

| Integration mode | Required contract |
| --- | --- |
| Coherent participant | Identify coherence agent/protocol path, supported operations, ordering, completion visibility, and dirty-line interactions |
| Managed noncoherent DMA | Define ownership transfer, supported cache clean/invalidate operations or uncached allocation, synchronization, and forbidden concurrent access |
| Private/local accelerator storage | Define explicit transfers, address translation, lifetime, completion, and staging-buffer ownership |

For managed noncoherent buffers, specify this full lifecycle: CPU owns and prepares
the buffer; the driver performs required cache maintenance and publishes work;
the device owns it while executing; completion becomes observable; the driver
performs required synchronization/invalidation; the CPU reacquires ownership.
Pinning and lifetime rules must prevent premature unmap or reuse. Partial cache
lines and aliased mappings need explicit treatment. A generic CPU fence alone is
**not** a cache flush or invalidate operation.

Every command/DMA interface must also specify address and length bounds, alignment,
burst limits, byte enables, outstanding transaction limits, ID allocation/reuse,
backpressure, response ordering, and reset cancellation. Define propagation of
denied/corrupt TileLink responses and AXI decode/slave errors where applicable;
do not report successful completion after a partial or failed transfer. Include
fault reporting, interrupt/completion ordering, timeout, and recovery behavior.

## Translation, protection, and physical implementation

CPU virtual memory, device address translation, IOMMU protection, shared virtual
addressing, and per-process accelerator isolation are distinct features. None is
currently qualified for NOVA by this document. A future translation design must
cover mappings and permissions, invalidation ordering, in-flight DMA, page faults,
context switches, stale translations, and unauthorized descriptors. Report absent
protection honestly; an early trusted-software experiment is not a secure system.

Moving from a simulated AXI endpoint to real memory requires a selected controller
and PHY, board/process constraints, calibration, clock/reset crossings, memory
training, data-integrity tests, and error handling. See [POWER_PHYSICAL](POWER_PHYSICAL.md).

## Planned acceptance matrix

All hardware tests below are planned in the requirements register, not passed.

| Requirement | Tests | Minimum acceptance evidence |
| --- | --- | --- |
| `REQ-MEM-001` | `T-MAP-001` | Generated map/device tree agree with RTL and software; no unexplained overlaps or access attributes |
| `REQ-MEM-002` | `T-COH-001`, `T-ORDER-001` | Both harts pass dirty-line exchange, eviction, false sharing, contended atomics, LR/SC, publication and declared litmus tests |
| `REQ-NPU-002`, `REQ-DMA-001` | `T-NPU-MEM-001`, `T-DMA-001` | Correct CPU→device→CPU exchange with dirty caches, partial transfers, concurrent traffic, backpressure, ID pressure, errors and reset interruption |
| `REQ-SEC-001` | `T-ISOLATION-001` | Claimed translation/protection boundaries reject unauthorized and stale accesses; limitations explicit |
| `REQ-PHY-001` | `T-PHY-001` | Real selected memory interface passes calibration, sustained integrity and fault/recovery tests on its declared target |

Archive exact revisions, configurations, generated artifacts, memory-model
parameters, tool versions, workload hashes, seeds, timeouts, expected/observed
outcomes, traces, exclusions, and reviewer decisions. Report bandwidth and latency
only for the measured model or physical target; simulation results are not silicon
measurements. Follow [VERIFICATION](VERIFICATION.md) for gate decisions.
