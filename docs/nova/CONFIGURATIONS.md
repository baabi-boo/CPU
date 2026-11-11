# NOVA configuration profiles

## Evidence status

The configurations in
[`NovaM1Configs.scala`](../../generators/chipyard/src/main/scala/config/NovaM1Configs.scala)
are thin, named derivatives of pinned Chipyard configurations. They establish
stable experiment entry points, not original CPU microarchitectures. Both are
**implemented source scaffolds with unverified elaboration and execution**.
See [STATUS](STATUS.md) and the [architecture specification](ARCHITECTURE.md).

| NOVA configuration | Upstream source | Expected source-selected harts | Purpose |
| --- | --- | --- | --- |
| `NovaM1BaselineConfig` | [`RocketConfig`](../../generators/chipyard/src/main/scala/config/RocketConfigs.scala) | One Rocket via `WithNHugeCores(1)` | Reproduce the single-core reference |
| `NovaM1MinimalConfig` | [`LargeBoomAndRocketConfig`](../../generators/chipyard/src/main/scala/config/HeteroConfigs.scala) | One BOOM v3 via `WithNLargeBooms(1)` and one Rocket via `WithNHugeCores(1)` | Qualify heterogeneous execution |

The mixed configuration inherits a 128-bit system bus and `AbstractConfig`.
Its Rocket core is a large configuration, not a measured low-power core.
Performance/efficiency roles remain hypotheses requiring workload, area, and
energy evidence. Hart IDs and their mapping to core types must be confirmed
from elaborated artifacts and runtime observations, not assumed from mixin order.

These profiles add no GPU, NPU, custom ISA extension, additional core, physical
memory controller, or power-management mechanism. Inherited framework facilities
must still be validated in the selected profile. The package is `chipyard`, so
the existing Makefile configuration package is sufficient.

## Explicit build entry points

First complete the pinned toolchain and required-submodule preparation in
[DEVELOPMENT](DEVELOPMENT.md). From the repository root, activate the generated
environment:

```bash
source ./env.sh
```

The Verilator simulator rule has an unconditional dependency on
`tools/DRAMSim2/libdramsim.a` (built from the pinned `tools/DRAMSim2` submodule).
Prepare that submodule even for the single-core baseline; do not interpret its
previously optional diagnostic classification as evidence that the simulator
can build without it. The CMake `hello` target also needs the pinned RISC-V
toolchain's HTIF headers/specs and the `toolchains/libgloss` linker-script
target. See the prerequisite checks and exceptions in [DEVELOPMENT](DEVELOPMENT.md).

Build and qualify the unchanged upstream baseline before the named derivative:

```bash
timeout --kill-after=30s 2h make -C sims/verilator CONFIG=RocketConfig -j2 &&
timeout --kill-after=30s 2h make -C sims/verilator CONFIG=NovaM1BaselineConfig -j2
```

After the baseline's exit criteria are met, build the mixed-core profile:

```bash
timeout --kill-after=30s 2h make -C sims/verilator CONFIG=NovaM1MinimalConfig -j2
```

These are inspected build entry points, **not commands demonstrated to succeed
by this foundation change**. Set an approved memory, disk, runtime, and parallelism
budget before execution. These examples use GNU `timeout`: TERM after two host
hours, then KILL after a 30-second grace period. This does not cap RAM, disk, or
whole-host CPU usage. Stop if a prerequisite fails; the paired baseline commands
use `&&` to avoid continuing after a failed upstream build. Builds can download
dependencies through the upstream build system; the lightweight repository checks
do not do so.

The inherited Make configuration defaults to `JAVA_HEAP_SIZE=8G` for the Scala
generator. A low-memory host may require a separately approved, smaller heap
(for example `JAVA_HEAP_SIZE=4G` passed to Make), but that setting is not a
verified compatible profile and cannot guarantee the build will fit. Record the
chosen heap setting, available RAM/swap, memory observations, parallelism, and
any OOM or timeout result in the execution evidence. Do not silently retry with
different resources and present the new attempt as the same reproduction.

With the Chipyard toolchain active and its test binary present, a first bounded,
trace-free smoke invocation on the unchanged upstream baseline is:

```bash
timeout --kill-after=30s 300s make -C sims/verilator CONFIG=RocketConfig run-binary-fast \
  BINARY="$RISCV/riscv64-unknown-elf/share/riscv-tests/isa/rv64ui-p-simple"
```

`run-binary-fast` avoids the separate `spike-dasm` dependency and preserves the
simulator pipeline's failure status. Once the upstream baseline works, repeat
the declared test with `CONFIG=NovaM1BaselineConfig`. Use `run-binary` when
instruction-disassembly output is needed and `spike-dasm` is available; record
which path ran. Neither invocation has been demonstrated to pass for NOVA by
this foundation change.

The timeout is an initial host-runtime limit, not a CPU performance target.
Record a timeout as failure or blockage; do not silently increase it to hide a
hang. Successful execution of this one test would establish only that test's
scope, not comprehensive ISA compliance or two-hart operation.

## Qualification and change control

For each profile, retain exact revision and dependency pins, build commands,
tool versions, generated RTL, device tree/address map, actual memory model,
hart inventory, ISA/privilege/cache parameters, test binaries, and run logs.
See [VERIFICATION](VERIFICATION.md) for required evidence and exclusions.

The mixed-core profile requires participant-aware per-hart tests. The inherited
[`mt-hello.c`](../../tests/mt-hello.c) expects four cores and is not suitable
unchanged for this two-hart configuration. Hart-0-only test selection also cannot
qualify every hart. Define bounded completion and failure diagnostics before
using a new multicore workload for acceptance.

Keep these reference profiles stable. Add separately named experimental profiles
for architectural changes and record their assumptions in an architecture
decision. Changing the upstream basis, dependency pins, ISA exposure, memory
topology, or core count invalidates affected evidence and requires renewed tests.
Neither a configuration name nor successful Scala compilation is a hardware gate
pass.

For the next bounded implementation task and its acceptance evidence, start with
NOVA-001 in the [actionable backlog](BACKLOG.md).
