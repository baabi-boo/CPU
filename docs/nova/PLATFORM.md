# NOVA-M1 platform and software contract

This specification describes planned qualification work. No NOVA firmware/Linux
boot, physical peripheral, secure-boot chain, or isolation boundary is qualified
by the project-foundation change. See [STATUS](STATUS.md).

## Initial platform boundary

The inherited [AbstractConfig](../../generators/chipyard/src/main/scala/config/AbstractConfig.scala)
selects boot-ROM infrastructure, SerialTL simulation loading, UART, debug/SBA,
and interrupt infrastructure. These source selections are not evidence that a
NOVA configuration boots. Simulation loading and console adapters must not be
described as physical board interfaces or production boot mechanisms.

The first targets are `NovaM1BaselineConfig`, then `NovaM1MinimalConfig`.
The latter must execute software on both harts; a successful hart-0 console
message does not demonstrate SMP operation. Keep the unmodified Rocket baseline
available to distinguish integration regressions from toolchain failures.

## Boot progression

1. **Bare-metal baseline:** document reset entry, ROM image, executable loading,
   memory initialization, entry point, stack, trap handler, and completion path.
   Run a bounded single-hart program with an expected result and exit status.
2. **Mixed-hart bring-up:** establish actual hart IDs, boot-hart selection,
   secondary-hart entry, per-hart stacks, synchronization, timer/interrupt routing,
   and reset recovery. Prove that every expected hart reaches the test barriers.
3. **Firmware and Linux:** select and pin the machine-mode firmware/SBI contract,
   kernel, root filesystem, and any loader in an architecture decision. OpenSBI
   is a candidate, not an already integrated NOVA component. Record payload
   placement, privilege transitions, device-tree handoff, and secondary-hart
   startup before attempting repeatable Linux SMP qualification.
4. **Physical boot:** separately specify board reset, clock/memory initialization,
   nonvolatile image storage, recovery mode, and authenticated boot policy where
   implemented. A simulation loader is not a substitute for this chain.

For each stage, document the failure path and timeout. A boot log alone must not
hide missing secondary harts, disabled drivers, failed probes, or recovery hangs.

## Address map and device tree

Generate the address map and device tree from each elaborated configuration;
retain hashes with the matching RTL and software images. The platform inventory
must identify hart IDs and capabilities, RAM and reserved ranges, boot regions,
MMIO regions, cacheability, interrupts, timer frequency, clock/reset dependencies,
and driver compatibility strings. Reject overlaps and stale copied device trees.

Firmware, linker scripts, loaders, drivers, and test models must agree on that
inventory. Changes to addresses, interrupt numbers, cacheability, or boot handoff
require interface review and regression tests. Do not publish inherited example
addresses as a final NOVA hardware map; see [MEMORY](MEMORY.md).

## ISA, ABI, and scheduling

Record the generated ISA, privilege/MMU facilities, and relevant extensions for
each hart. Choose a baseline compiler ISA and ABI supported by every hart on
which a binary may run. Do not infer a common execution contract merely because
both CPU families are RISC-V.

If future harts expose different extensions, define capability discovery,
dispatch/affinity rules, context preservation, and unsupported-instruction
behavior before allowing migration. Test floating-point/vector state where
enabled. BOOM/Rocket roles do not imply validated OS energy-aware scheduling or
measured performance/efficiency classes. Arm binaries and macOS compatibility
are outside this project's platform contract.

## Peripheral and driver contracts

| Interface | Required specification and tests |
| --- | --- |
| Console/UART | Register map, polling/interrupt operation, buffering, reset, and distinction between simulated console and physical pins |
| Timers and interrupts | Sources, targets, polarity/trigger behavior, acknowledge/clear sequence, per-hart delivery, masking, and concurrent events |
| Debug | Access rights, halt/resume, reset interaction, system-bus access, and the explicitly supported development threat model |
| Future storage/network/display | Pinned IP and driver revisions, bus transactions, DMA ownership, interrupts, timeouts, recovery, and real-platform dependencies |
| Future GPU/NPU | Submission/completion, memory ownership, faults, process lifetime, and validated userspace/runtime ABI |

New I/O blocks require an interface specification, driver, reference test, and
fault/reset tests before being advertised. USB, PCIe, display, and physical
DDR/LPDDR support are not established by generic AXI or TileLink connectivity.

## Security boundaries

Treat the initial platform as a trusted development environment, not a secure
product. Debug/SBA and simulation loading may provide privileged access; do not
run untrusted workloads while claiming isolation that has not been tested.

Before any security claim, define assets, attackers, privilege boundaries,
debug exposure, firmware update/rollback policy, recovery behavior, and DMA
reachability. A future verified-boot design needs a specified root of trust and
key lifecycle; loading a signed file or booting Linux alone does not establish
it. CPU page tables do not automatically isolate accelerator DMA. IOMMU support,
secure memory, and debug lock-down require separate implementation and tests.

## Reproducible software and acceptance

Build target software from pinned sources with recorded compiler/linker versions,
ISA/ABI flags, firmware/kernel configuration, rootfs manifest, and dependency
hashes. Record build commands, configuration, image hashes, loader parameters,
console/exit logs, seeds, timeouts, failures, and exclusions. Keep secrets out of
images and evidence. Rebuild from a clean environment before release acceptance.

| Requirement | Test IDs | Required result before qualification |
| --- | --- | --- |
| `REQ-CPU-002` | `T-HART-001`, `T-RESET-001`, `T-ISA-001` | Every expected hart participates; per-hart architectural behavior, interrupts, traps, boot/reset and bounded recovery pass |
| `REQ-MEM-001` | `T-MAP-001` | Generated map agrees with firmware, kernel, and device descriptions |
| `REQ-PLAT-001` | `T-LINUX-001` | Rebuilt images boot repeatedly; Linux enumerates and schedules both harts; concurrent load and reboot tests pass |
| `REQ-SEC-001` | `T-ISOLATION-001` | Every advertised protection rejects unauthorized accesses; absent protections remain documented |

These test descriptors are planned, not execution evidence. Apply the gate and
artifact rules in [VERIFICATION](VERIFICATION.md) and [ROADMAP](ROADMAP.md).
