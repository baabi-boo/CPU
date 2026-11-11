# NOVA-M1 accelerator specification

## Status and scope

AI and GPU integration are **planned**, not demonstrated NOVA capabilities.
Neither initial NOVA CPU profile instantiates a qualified NOVA NPU or GPU.
An upstream dependency or successful upstream demonstration is not integration
evidence. See [STATUS](STATUS.md), [ARCHITECTURE](ARCHITECTURE.md), and the
[requirement register](../../nova/requirements.json).

| Candidate | Repository evidence | Investigation boundary |
| --- | --- | --- |
| Gemmini | Gitlink `b82d49cca798a59f010488a6f6de7243f0616536`; `build.sbt` project | Preferred initial AI investigation; inspect this revision's supported configurations and software |
| Radiance | Gitlink `917c95cdb6d698c4fd267ccab2602e283d2ca6c3`; `build.sbt` project depending on Rocket Chip, Gemmini, and TestChipIP | Evaluate existing integration opportunities; dependency presence does not establish supported graphics APIs or NOVA compatibility |
| Vortex | External candidate; no NOVA dependency pin or integration | Evaluate hardware, host interface, runtime, and exact release before selection |

The source facts above are recorded in [upstream-lock.json](../../nova/upstream-lock.json)
and [build.sbt](../../build.sbt). This specification does not transfer features
advertised by current upstream branches to the pinned versions. No Apple GPU,
Neural Engine, Metal compatibility, performance, or efficiency equivalence is
claimed. GPU compute, graphics acceleration, and display output are distinct
deliverables.

## AI integration contract — G5

Before implementation, record a reviewed configuration and interface contract:

1. **Instantiation:** selected Gemmini parameters, precision, array dimensions,
   local memories, supported operations, dependency/toolchain pins, and resource
   budget. The unaccelerated CPU baseline must remain selectable.
2. **Hart attachment:** explicitly name which tile owns the accelerator. The
   inherited [RoCC fragments](../../generators/chipyard/src/main/scala/config/fragments/RoCCFragments.scala)
   provide `WithMultiRoCC` and `WithMultiRoCCFromBuildRoCC`; composition order and
   generated tile IDs require review and elaboration checks. Do not accidentally
   instantiate an accelerator on every hart or assume tile IDs equal software's
   expectations without checking generated artifacts.
3. **Instruction routing:** allocate custom opcodes without conflicts with other
   RoCC users. Specify supported instructions, operands, privilege, completion,
   busy behavior, errors, and what occurs on a non-owning hart. Unsupported use
   must have a defined outcome rather than silently hanging.
4. **Memory:** declare address width/translation, access permissions, cache
   participation, transaction ordering, DMA alignment, outstanding limits,
   buffer ownership, and completion visibility. Verify the actual selected
   configuration instead of assuming all Gemmini configurations behave alike.
5. **Software:** pin the matching instruction definitions and runtime; document
   allocation, submission, synchronization, error recovery, and fallback.
   Multitasking requires ownership/context rules or an explicitly exclusive
   execution mode; a bare-metal demo does not prove Linux process isolation.
6. **Recovery:** define bounded waits, fault reporting, cancellation or reset,
   in-flight transfer handling, and when software may safely reuse a buffer.

### Numerical and end-to-end acceptance

`REQ-NPU-001` / `T-NPU-NUM-001` requires a trusted software reference with declared
integer overflow/saturation rules or floating-point tolerances. Cover zero and
identity cases, signed extrema, non-square shapes, tile boundaries, tails,
strides, quantization/scaling, accumulation, and randomized reproducible inputs.
Test unsupported dimensions and data types as errors, not unspecified results.

`REQ-NPU-002` / `T-NPU-MEM-001` and `T-DMA-001` require dirty-buffer handoffs,
backpressure, concurrent CPU traffic, invalid accesses, reset interruption,
timeout handling, and subsequent successful work. Include one complete inference
workload with fixed input/model hashes and expected output. Report transfer,
setup, kernel, and end-to-end costs separately; kernel-only timing is not
application speedup.

## GPU selection and integration contract — G6

Selection requires an architecture decision comparing at least the viable
inherited option and the external candidate. Evaluate the exact checked-out
revision rather than a project name or screenshot:

| Review axis | Required artifact |
| --- | --- |
| Compute and graphics scope | Enumerated supported operations, tested APIs, known limitations, and reference workloads |
| SoC integration | Host command interface, memory ports, adapters, clock/reset domains, interrupts, and resource estimates |
| Software feasibility | Compiler/runtime/driver revisions, build procedure, submission ABI, and process ownership |
| Memory behavior | Cache/coherence specification, translation and DMA isolation requirements, buffer lifecycle |
| Provenance and deployment | License/notices inventory, dependency pins, FPGA/ASIC portability gaps, and tool/IP availability |

Do not equate an FPGA accelerator host interface with an already integrated
on-chip GPU. Define queue/descriptor formats, command validation, completion and
interrupt semantics, timeout/reset behavior, and error propagation before bridge
implementation. Validate buffers and descriptor ranges before device access.
Qualify compute first; graphics APIs and physical display output require their
own drivers, hardware, and tests.

`REQ-GPU-001` / `T-GPU-EXEC-001` requires correct kernel submission/completion,
reference-result comparisons, concurrent submissions where supported, invalid
commands, resource exhaustion, faults, and bounded recovery. A graphics claim
requires a reproducible graphics workload exercising the claimed path, not
software rendering displayed beside an unrelated hardware test.

## Shared-memory and security rules

Apply [MEMORY](MEMORY.md): shared physical DRAM is not CPU–accelerator cache
coherence, shared virtual addressing, or isolation. Every integration chooses
one explicit coherence contract. Noncoherent DMA requires supported cache
maintenance or uncached buffers and ownership transitions; a generic CPU fence
does not flush dirty cache lines. Coherent DMA requires a correct protocol
participant and contention/dirty-line evidence.

`REQ-DMA-001` / `T-DMA-001` covers CPU-to-device-to-CPU visibility, partial
transfers, ordering, transaction-ID reuse, and simultaneous traffic. Where
isolation is claimed, `REQ-SEC-001` / `T-ISOLATION-001` adds unauthorized-address,
hostile-descriptor, and cross-process tests. If no IOMMU or process protection is
implemented, document a trusted-workload-only boundary; do not advertise secure
multi-tenant execution.

## Required evidence and stop conditions

Record exact profile/revisions, generated interfaces, software/model hashes,
commands, numerical policy, seeds, limits, logs, traces, failures, and exclusions.
All test descriptors above remain planned until executable tests and reviewed
evidence exist. Passing documentation checks cannot close G5 or G6.

Stop integration acceptance for unexplained mismatches, stale-cache behavior,
unbounded waits, unresolved opcode conflicts, undocumented memory semantics,
unreviewed dependency/license changes, or resource requirements exceeding the
approved target. Retain the CPU-only profile and the last reproducible result.
