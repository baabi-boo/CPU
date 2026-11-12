# NOVA-M1 G1: single-core Rocket baseline runbook

**Status: procedure only; no NOVA hardware build, simulator execution, or G1
acceptance is established by this document.** The first actionable task is
[NOVA-001](BACKLOG.md), preparing the pinned toolchain. NOVA-002 then runs the
unmodified Rocket reference; NOVA-003 qualifies the separately named NOVA
configuration. Keep these achievements distinct.

The campaign tooling is implemented and offline-tested; its hardware procedure
has not been executed here. This runbook covers the fixed Linux x86-64/Chisel 6
profile, not a general Chipyard installation promise. Follow the
[development guide](DEVELOPMENT.md),
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
python3 -B scripts/nova/g1_profile.py --json
python3 -B scripts/nova/conda_inventory.py --json
python3 -B scripts/nova/g1_campaign.py --plan
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
explicit migration review. This selector behavior does not itself prove that a
glibc 2.41 host cannot use the older 2.34 sysroot; a pin-preserving preparation
procedure still needs separate review and validation.

The upstream lean setup also initializes many optional Git submodules with
`--full`; the word *lean* does not imply limited downloads. A selective
dependency/Conda setup is only a proposal until validated, including nested
gitlinks, `env.sh`, `RISCV`, the HTIF toolchain, and CIRCT. Never use host tools
or changed pins silently to get a green result. See
[DEVELOPMENT](DEVELOPMENT.md) for the opt-in setup entry point and its risks.

The [G1 profile](../../nova/g1-profile.json) enumerates known required source
gitlinks, provisioning sources, optional-generator inventory, and tool/runtime
checks. It is **not a complete proven dependency closure**: nested sources,
JVM dependencies, and actual build compatibility remain unqualified. The default
Chisel 6 path rejects `USE_CHISEL7` even when its value is empty or `0`.
Neither the plan nor these diagnostics installs a toolchain or initializes
submodules. Without `--prefix`, the Conda command above only inspects the lock;
it does not inspect an installed environment.

## 3. Qualify the prepared environment

After a separately approved, pinned setup, activate the recorded environment
and require the strict diagnostic to pass:

```bash
source ./env.sh
make -f nova.mk doctor-strict
python3 -B scripts/nova/g1_profile.py --strict --json
python3 -B scripts/nova/conda_inventory.py --prefix "$CONDA_PREFIX" --json
```

Confirm the initialized required gitlinks are at the committed SHAs and check
both tracked and relevant ignored changes. For this G1 workload, the Verilator
simulator unconditionally uses `tools/DRAMSim2`; the `hello` linker script uses
`toolchains/libgloss`. `cmake`, `verilator`, `firtool`, a compatible Java/sbt
stack, and the matching RISC-V toolchain must be available. A successful
diagnostic is still **not** evidence of RTL elaboration or execution. The profile
checks Verilator/firtool version inputs and runtime collateral, including the
compiler-resolved installed `htif.ld` against the pinned libgloss source.
The Conda inventory compares installed metadata with the unchanged lean lock's
165 packages; `matched` does not authenticate installed binary contents.

The lean lock does not include CMake, and strict inventory rejects unexpected
packages. Do not add CMake to that locked prefix as an undocumented workaround.
Supplementary tools require separately reviewed, provenanced placement outside
the prefix or an explicit dependency migration.

Both `RISCV` and `CONDA_PREFIX` must identify prepared absolute directories, and
the reviewed `env.sh` must already exist. Stop on missing inputs or mismatches.
Do not unset a required environment setting merely to bypass a rejection: the
runner rejects enumerated profile/build overrides, not every possible influence
of an arbitrary local environment.

## 4. Review the exact workload contract

The [workload manifest](../../nova/g1-workloads.json) fixes **15 workloads per
configuration**. The runner separately builds `RocketConfig` and
`NovaM1BaselineConfig`, then uses the same target binaries for each. Thirty
declared observations are not thirty already-executed tests.

| Workload | Expected observation, not qualification |
| --- | --- |
| `hello` | Exact inherited Rocket hello line plus the simulator completion protocol; its printed core number is hard-coded, not runtime hart identification |
| `nova-baseline` | Exact `NOVA_BASELINE_V1 PASS hart=0 checks=8` record after eight deterministic target checks, plus the completion protocol |
| `nova-baseline-fail` | Exact expected-failure target record and SimTSI code-7 assertion, with an ordinary nonzero simulator result; an arbitrary crash, timeout, or nonzero exit is insufficient |
| Twelve ISA workloads | Every exact binary below is mandatory; each requires the completion protocol |

```text
rv64ui-p-simple  rv64ui-p-add  rv64ui-p-sub  rv64ui-p-beq
rv64ui-p-jalr    rv64ui-p-ld   rv64ui-p-sd
rv64um-p-mul    rv64um-p-div
rv64mi-p-csr    rv64mi-p-illegal    rv64mi-p-scall
```

ISA binaries are selected from the declared relative directory within `RISCV`;
missing inputs block the campaign rather than becoming empty wildcards or skips.
The expected target failure code is not assumed to equal the simulator's host
exit status. The negative workload reaches code 7 only after its eight checks.

This subset does not qualify F, D, A, C, MMU behavior, full ISA compliance,
per-instruction differential checking, or heterogeneous execution. These are
coverage exclusions, not promises that no runtime instruction uses those
extensions. Pinned ISA programs also contain conditional internal checks;
executing every named binary does not prove every internal assertion ran. Spike
comparison scope remains unresolved and `reference_comparison` remains `not_run`.

## 5. Run one explicitly approved campaign

Run the script from its own clean, prepared checkout. Execution with `--root`
pointing to another checkout is rejected, so that the recorded source also owns
the running helper code. A read-only relocated plan is allowed. Known stale
generated products and source changes, including visibility-hiding Git index
flags, block execution. Use a fresh checkout; the runner does not delete outputs.

The following values are examples matching the defaults, **not an approval of
this host or a previously successful hardware command**. Use them only after
the budget in section 1 has actually been recorded:

```bash
python3 -B scripts/nova/g1_campaign.py --execute --approved-budget \
  --jobs 2 --java-heap 4G --total-timeout-seconds 7200 --min-free-gib 10
```

`--approved-budget` acknowledges that prior decision; it does not grant access,
cost, network, or hardware-run authority. The runner does not provision a
toolchain or initialize submodules. Explicit Make/sbt builds can still resolve
JVM dependencies over the network: the prepared profile is not an offline
dependency closure, and network policy must cover any such approved access.

The default envelope is two build jobs, a 4 GB Java heap, a 7,200-second aggregate
acceptance budget, 10 GiB minimum free disk, 64 MiB per stdout/stderr stage log,
10,000,000 simulator cycles, and seed 1. Active stages receive the remaining
time budget. Disk/log checks are sampled and repeated after exit; they are not
kernel quotas or a peak-RAM guarantee. Cleanup and bounded evidence probes can
overrun the aggregate deadline, but an overrun invalidates campaign acceptance.
Scoped SIGINT/SIGTERM handling terminates the runner's child process group and
retains interrupted status and actual exit information. This trusted-build
runner is not a security sandbox or a cleanup guarantee for SIGKILL or programs
deliberately escaping their process group.

The runner retains separate logs and `record.json` under ignored
`nova-out/g1-campaign-*/`. Records bind the declared plan to actual commands,
pre/post source and toolchain observations, target/simulator hashes, generated
RTL/DTS/JSON identities, limits, and workload assessment. Runtime collateral and
Conda metadata are rechecked after execution. Capture of DTS/JSON files does not
semantically validate an address map, cache/MMU parameters, or hart inventory.

## 6. Interpret the result without upgrading the claim

| Campaign result | CLI exit | Meaning |
| --- | --- | --- |
| `workloads_observed` | 0 | All declared raw process/protocol expectations and integrity checks were observed; not a hardware qualification |
| `failed` | 1 | An executed build/workload or integrity condition failed its expectation |
| `blocked` | 2 | Required preparation, evidence, authority acknowledgment, or resource conditions were unavailable; remaining rows are not run |

Successful positive assessments set `completion_protocol_observed: true` but
keep `target_completion_verified: false`. The pinned HTIF path can report zero
success after `signal_exit` shutdown without a target-originated exit value;
therefore even authentic TestDriver PASS text and host exit zero do not settle
the exit cause. This is a source-confirmed ambiguity, **not a reproduced CPU
result**. See the [completion-protocol investigation](evidence/G1-COMPLETION-PROTOCOL-2026-11-12.md).
Independent target-terminal observability is still required for that stronger
claim. Runner-owned interruption or timeout always invalidates the observation.

`hardware_qualified` and `g1_gate_passed` stay false. Neither this procedure nor a
synthetic unit-test fixture closes `T-BUILD-001`, `T-ISA-001`, or G1.

## 7. Reproduce, compare, retain evidence, and review

G1 requires an independent **second clean-checkout build**, not a rerun of an
existing executable. Prepare the same reviewed revision in a fresh checkout,
invoke that checkout's own runner, and repeat the entire procedure. Do not copy
simulators or generated build products between them. Separately record/isolate
relevant caches and their contents: different checkout paths and Git cleanliness
do not prove independence or absence of ignored/nested/shared cache reuse.

Once both records exist, compare them read-only, replacing the two example paths
with the exact retained `record.json` files:

```bash
python3 -B scripts/nova/compare_campaigns.py \
  /absolute/path/to/first/record.json /absolute/path/to/second/record.json
```

The comparator returns `consistent` (exit 0), `different` (exit 1), or `blocked`
(exit 2). It validates record consistency, command binding, bounds, pre/post
identity, and declared artifacts. `consistent` means agreement between
**unauthenticated JSON records**, not proof of execution, trustworthy logs,
independent clean builds, target completion, or reproducible hardware. Review
build-log differences and every unexplained artifact/result difference; do not
discard inconvenient fields or sanitize raw evidence into apparent agreement.

For a G1 review, retain and independently inspect:

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

Keep raw logs/records private in ignored `nova-out/` or an approved restricted
artifact store. Commands and diagnostic output may contain local paths or other
sensitive data; automatic redaction is not promised. Preserve original hashes
and evidence for authorized review, and publish only separately curated,
sanitized summaries under [evidence](evidence/TEMPLATE.md) or an approved
retention service. Raw local paths alone are not durable evidence.

Report `blocked` for missing authority, incompatible locked dependencies,
unavailable software/IP, or exhausted resources; report `failed` for an executed
test or build that did not meet its stated expectation. Record `not_run` when a
test was not attempted. Never relabel these outcomes as `passed` to advance a
gate. Only a reviewed, reproducible campaign can support a G1 decision.

## Legacy single-profile helper

`python3 -B scripts/nova/rocket_baseline.py --plan` remains available for the
earlier Rocket-only smoke sequence. Its opt-in execution mode and
`hello_marker_observed_unqualified` result are intentionally limited: no named
NOVA profile, complete declared workload campaign, independent target-completion
proof, second clean build, or G1 acceptance follows from it. Use the two-profile
campaign above for further G1 preparation. The mixed BOOM/Rocket configuration
belongs to G2 and must later validate both harts.
