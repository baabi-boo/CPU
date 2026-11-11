# NOVA-M1 G1: single-core Rocket baseline runbook

**Status: procedure only; no NOVA hardware build, simulator execution, or G1
acceptance is established by this document.** The first actionable task is
[NOVA-001](BACKLOG.md), preparing the pinned toolchain. NOVA-002 then runs the
unmodified Rocket reference; NOVA-003 qualifies the separately named NOVA
configuration. Keep these achievements distinct.

This runbook is for a bounded Linux host experiment, not a general Chipyard
installation promise. Follow the [development guide](DEVELOPMENT.md),
[reproducibility contract](REPRODUCIBILITY.md), [verification plan](VERIFICATION.md),
and [G0/G1 gates](ROADMAP.md) if they impose additional requirements.

## 1. Record approval and a resource envelope

Before starting setup, the maintainer must record:

| Item | Required decision or observation |
| --- | --- |
| Gate dependency | G0 maintainer acceptance and its evidence location |
| Host | Linux distribution, architecture, glibc, clean checkout revision |
| Memory | Available/effective RAM and swap; monitoring and stop threshold |
| Storage | Free disk, budget for dependencies and generated outputs, stop threshold |
| Execution | CPU-job limit, elapsed-time cap and timeout/termination behavior |
| Access | Network destinations, license/IP prerequisites and credential policy |
| Cost | Authorized spending limit, including explicit zero if no paid runner |
| Accountability | Person approving the run and person reviewing its results |

Do not infer approval from a healthy diagnostic. Two Make jobs and a command
timeout **do not** cap peak RAM, disk usage, or total host CPU consumption. The
current project has no qualified minimum-host matrix. Stop on an exhausted budget
instead of suppressing an error or silently increasing resources.

## 2. Run non-mutating preflight before installation

From a clean, separate checkout of the intended pinned revision:

```bash
make -f nova.mk check
make -f nova.mk doctor
python3 -B scripts/nova/bootstrap_preflight.py --json
git rev-parse HEAD
git status --porcelain=v1 --untracked-files=all --ignore-submodules=none
git submodule status --recursive
```

The repository check is metadata/tooling verification, not processor execution.
Normal doctor and bootstrap preflight diagnose known prerequisites; an initially
blocked strict diagnostic is expected on a host without the toolchain. Record
the exact output, exit codes, missing prerequisites, nine pinned Conda input
SHA-256 hashes, source gitlinks, and manifest-vs-blob checks. Do not publish a
complete environment dump or raw credential-bearing logs.

**Pin-change stop condition:** Inspect the host glibc and the imported
`sysroot_linux-64` selection before running upstream setup. The inherited
[`scripts/build-setup.sh`](../../scripts/build-setup.sh) can rewrite
`conda-reqs/chipyard-base.yaml` and regenerate lockfiles even without requesting
unpinned dependencies. For example, glibc 2.41 selects sysroot 2.39 while the
imported file pins 2.34. This is a proposed dependency migration, **not** an
unchanged-pinned reproduction. Do not execute the rewriting path without an
explicit migration review.

The upstream lean setup also initializes many optional Git submodules with
`--full`; the word *lean* does not imply limited downloads. A selective
dependency/Conda setup is only a proposal until validated, including nested
gitlinks, `env.sh`, `RISCV`, the HTIF toolchain, and CIRCT. Never use host tools
or changed pins silently to get a green result. See
[DEVELOPMENT](DEVELOPMENT.md) for the opt-in setup entry point and its risks.

The known gitlinks checked by `doctor-strict` are **not a complete proven
dependency closure** for a Rocket build. The pinned `build.sbt` always-on
Chipyard classpath also references `generators/bar-fetchers`,
`generators/constellation`, `generators/icenet`, `generators/rerocc`,
`generators/rocket-chip-blocks`, and `generators/shuttle`. The default Chisel 6
path brings in `tools/firrtl2`, `tools/dsptools`, and
`tools/rocket-dsp-utils`, with additional transitive dependencies such as
`tools/fixedpoint`. BOOM/HardFloat integration can require other components,
including `generators/pmu` and FireSim-provided utility sources. Establish the
actual selected configuration's pinned source and nested dependency closure
before approving a selective initialization; do not infer it from a green
diagnostic alone.

## 3. Qualify the prepared environment

After a separately approved, pinned setup, activate the recorded environment
and require the strict diagnostic to pass:

```bash
source ./env.sh
make -f nova.mk doctor-strict
```

Confirm the initialized required gitlinks are at the committed SHAs and check
both tracked and relevant ignored changes. For this G1 workload, the Verilator
simulator unconditionally uses `tools/DRAMSim2`; the `hello` linker script uses
`toolchains/libgloss`. `cmake`, `verilator`, `firtool`, a compatible Java/sbt
stack, and the matching RISC-V toolchain must be available. A successful
diagnostic is still **not** evidence of RTL elaboration or execution.

## 4. Build and execute the upstream Rocket reference

The commands below are inspected entry points, **not previously observed
successes**. The two-hour build, ten-minute target-build, and five-minute smoke
timeouts are examples; use the approved caps and preserve every exit code.
Keep the selected Java heap within the approved memory envelope—the inherited
default is 8 GB—and record any override.

```bash
timeout --kill-after=30s 2h make -C sims/verilator CONFIG=RocketConfig -j2
timeout --kill-after=30s 10m cmake -S tests -B tests/build \
  -DCMAKE_SYSTEM_NAME=Generic \
  -DCMAKE_C_COMPILER=riscv64-unknown-elf-gcc \
  -DCMAKE_CXX_COMPILER=riscv64-unknown-elf-g++
timeout --kill-after=30s 10m cmake --build tests/build --target hello --parallel 2
timeout --kill-after=30s 30s riscv64-unknown-elf-readelf -h tests/build/hello.riscv
timeout --kill-after=30s 300s make -C sims/verilator CONFIG=RocketConfig run-binary-fast \
  BINARY="$PWD/tests/build/hello.riscv"
```

Stop after the first nonzero status. The `run-binary-fast` variant avoids a
separate `spike-dasm` dependency. `tests/CMakeLists.txt` sets cross-compiler
variables after `project()`, so the command above explicitly selects the
RISC-V compilers at configure time rather than relying on the host defaults.
Inspect the ELF header: it must identify a 64-bit RISC-V target (ELF machine
243), not a host executable. Check both a genuine target-side
`Hello world from core 0` line and successful simulator/target completion;
neither a zero-exit no-op nor a printed line alone is sufficient. That text is
hard-coded by `tests/hello.c`, so it does not prove hart identity. Preserve
simulator exit status, test output, and completion evidence together. A successful
`hello` run is only a smoke test; it does not establish ISA compliance, traps,
MMU correctness, hart identity, multicore correctness, or original CPU RTL.

Then run and identify a **declared, supported ISA/trap-test subset** with exact
binaries, expected results, hashes, toolchain versions, exclusions, and a
pinned reference comparison where supported. Do not call a discovered but
unexecuted suite a pass, and do not silently filter mismatches.

After archiving the unchanged upstream result, separately build
`NovaM1BaselineConfig`, rerun the same declared workloads, and compare their
generated artifacts and observations. This alias is a source scaffold—not a
distinct implemented processor design. The initial mixed BOOM/Rocket profile
belongs to G2 and requires tests on **both** harts.

An optional local helper, `python3 -B scripts/nova/rocket_baseline.py --plan`,
describes the proposed Rocket command sequence without executing it. The
`--execute --approved-budget` mode is a separate, explicit opt-in for an
already prepared environment. The flag acknowledges a **previously approved**
host/resource budget; it does not grant one. The helper requires a clean checkout,
an activated `RISCV`/`env.sh` environment, valid prerequisites, and no stale
ignored `tests/build` or relevant Verilator build products. It stops rather than
deleting or reusing those artifacts. The default plan limits Make to two jobs,
sets a 4 GB Java heap, reserves a two-hour aggregate wall-time budget, and checks
for at least 10 GiB of free disk before execution. These settings are adjustable
within the script's bounded options and **do not cap peak RAM or total disk use**.

If explicitly executed, the helper retains per-stage logs and a `record.json`
under ignored `nova-out/rocket-baseline-*/`. It enforces a 64 MiB per-stage log
limit, records source/dependency/tool versions, checks the compiled ELF64 RISC-V
header, and observes whether the expected `hello` text appears. Installed tool
versions are *recorded*, not automatically established as compatible with the
pinned Conda/CIRCT environment; that remains an engineering review task.

Even when every runner stage exits zero and the text appears, its result is
`hello_marker_observed_unqualified` with `target_completion_verified: false`.
This is intentionally **not** independent proof of target-side completion: a
printed marker or echoed log text could be misleading. Examine simulator/HTIF
termination semantics and independently retained target evidence before calling
the smoke test successful. The helper never closes `T-BUILD-001`, `T-ISA-001`,
or G1; its partial local record cannot substitute for the separate NOVA alias,
declared ISA suite, second clean build, and human gate review.

## 5. Reproduce, retain evidence, and review

G1 requires an independent **second clean-checkout build**, not a rerun of an
existing executable. In particular, remove or isolate ignored generated outputs
by using a new clean checkout rather than treating a clean Git index as proof
that all compiler/simulator inputs are fresh. Retain for each attempt:

1. Exact superproject SHA, dirty state/patch identity, recursive submodule pins,
   and all nine Conda input hashes before and after setup.
2. Approved host/resource limits; installed tool and reference-model versions;
   exact cross-compiler/CMake selection, command, working directory, start/end
   time, duration, and exit status.
3. Generated RTL, device tree and address map, actual memory model, hart count,
   ISA/privilege/cache settings, test binaries, traces/logs, and SHA-256 hashes.
4. Expected versus observed behavior, timeout/OOM/crash diagnostics, negative
   checks, unsupported cases, and sanitized retrievable artifact locations.
5. Requirement/test scope (`REQ-BUILD-001`, `REQ-CPU-001`, `T-BUILD-001`,
   `T-ISA-001`), exclusions, named reviewer, and recorded go/no-go decision.

Keep large raw outputs in ignored `nova-out/`; only publish curated and
sanitized records under [evidence](evidence/TEMPLATE.md) or an approved
artifact-retention service. Raw local paths alone are not durable evidence.

Report `blocked` for missing authority, incompatible locked dependencies,
unavailable software/IP, or exhausted resources; report `failed` for an executed
test or build that did not meet its stated expectation. Record `not_run` when a
test was not attempted. Never relabel these outcomes as `passed` to advance a
gate. Only a reviewed, reproducible campaign can support a G1 decision.
