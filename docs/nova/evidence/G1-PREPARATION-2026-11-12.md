# G1 preparation observation — blocked, not hardware qualification

**Observation date:** 2026-11-12

**Evidence level:** local repository tooling and environment-prerequisite
inspection only. **Outcome:** G1 execution preparation is `blocked`; processor
build and execution are `not_run`.

This record describes an unprepared development host and the new campaign
tooling. It does not close NOVA-001, NOVA-002, NOVA-003, `T-BUILD-001`,
`T-ISA-001`, G0, or G1. No dependency provisioning, RTL elaboration, simulator
build, target cross-compilation, CPU execution, reference-model comparison, or
second clean hardware build was performed for this observation.

## Source identity and scope

| Field | Observation |
| --- | --- |
| Repository and working directory | `baabi-boo/CPU`, commands run at its repository root |
| Local integration checkpoint | `a4228b3628949af92a6622a8f09710ce4828c2e0` |
| Checkpoint Git tree | `9a0746de6c89deea59938267da66ae34b3abc66e` |
| Same-tree GitHub publication object | [`edf31943a299052258b56f575b4b26e06b939b43`](https://github.com/baabi-boo/CPU/commit/edf31943a299052258b56f575b4b26e06b939b43); created by the integrator after collection with the exact checkpoint tree, before moving `main` |
| Working-tree state at diagnosis | Clean: `git status --short` produced no output; bootstrap preflight reported `dirty: false` |
| Subsequent state | Parallel Wave 7 documentation edits follow this snapshot; this record is not an assertion about the eventual published commit |
| Earlier main used for preservation comparison | `97d7eff6b6f8ba604502c84bfdb08ac6469b0bbb` |
| Gitlinks | All 57 root gitlink path/SHA rows unchanged from that earlier main; all 57 currently uninitialized |
| Profile | Default Chisel 6, Linux x86-64, planned `RocketConfig` and `NovaM1BaselineConfig` campaigns |
| Requirements/tests concerned | Preparation for `REQ-BUILD-001`, `REQ-CPU-001`, `T-BUILD-001`, and `T-ISA-001`; executed checks are repository-level only |
| Reviewer status | Automated evidence collection and integration review; actual human maintainer acceptance remains pending |

The checkpoint is a **local development identity**, not a claim that this commit
was already published or accepted. Earlier main foundation CI was reported as
passed by the integrating agent. That result applies to its earlier revision,
not this unpublished checkpoint. This observation did not query or establish a
new remote CI result; publication and its CI result require a separate check.

## Commands and observed results

These commands were actually run without installation, environment activation,
network-dependent setup, or hardware compilation. No `--execute` invocation was
made for the new G1 campaign.

| Command | Exit | Observed result |
| --- | ---: | --- |
| `git log -1 --format='%H%n%T%n%s'` | 0 | Checkpoint and tree shown above |
| `git status --short` | 0 | No output at diagnosis |
| `python3 -B scripts/nova/check.py` | 0 | Repository checks passed; explicitly not HDL/hardware qualification |
| `python3 -B scripts/nova/bootstrap_preflight.py --json` | 0 | Informational report: six blockers, glibc 2.41, unsafe automatic sysroot selection, all nine imported Conda inputs matched |
| `python3 -B scripts/nova/g1_profile.py --strict --json` | 2 | `status: blocked`, 38 known-prerequisite blockers |
| `python3 -B scripts/nova/conda_inventory.py` | 0 | Read-only plan for 165 locked packages; no installed-prefix comparison performed |
| `python3 -B scripts/nova/conda_inventory.py --json` | 0 | Same 165-package plan, `status: planned`, `metadata_only: true` |
| `python3 -B scripts/nova/g1_campaign.py --plan` | 0 | Two separate configuration plans, 15 workloads each; no commands executed by the plan |
| `git submodule status --recursive` | 0 | 57 entries with the uninitialized `-` prefix |
| `git diff --exit-code 97d7eff6b6f8ba604502c84bfdb08ac6469b0bbb HEAD -- conda-reqs .gitmodules` | 0 | No changes to the preserved Conda inputs or `.gitmodules` |
| `sha256sum nova/upstream-lock.json nova/g1-profile.json nova/g1-workloads.json` | 0 | Manifest hashes retained below |
| `make -f nova.mk check` during parallel documentation editing | 2 | Validation stopped on four links to the completion-protocol record before that peer-owned file existed; this invocation did not reach the test runner |

A read-only comparison of the `160000` rows from `git ls-tree -r` for the earlier
main and checkpoint returned **57 rows, equal**. SHA-256 of the checkpoint's
Git-ordered rows, joined with newlines and one final newline:
`e7c0eb5f84cf8e7393935a37258c550f94f70adc461979d3d0a94c33cb855542`.

The integrating agent separately recorded `make -f nova.mk check` passing
**523 offline tooling tests in 19.305 seconds** during Wave 6 integration,
together with repository, managed-text whitespace, and diff checks. That is a
repository-tool regression result, not a CPU result or a new run performed by
this evidence collector. Later integration/final-publication checks must be
reported against their own revision.

The documentation-time link failure is retained rather than suppressed. It
describes the intermediate parallel-edit state, not a CPU failure; the
integrating agent reran the full check after all Wave 7 documents existed.
That integrated run passed **523 tests in 18.011 seconds**, repository/link
validation, managed-text whitespace, and diff checks. A concurrent earlier run
had exposed a timing assumption in the repeated-signal fixture: it assumed the
first handler ran during a fixed sleep. The fixture now waits for observed
cleanup entry before sending further signals, retaining its child-cleanup,
actual-exit, and first-handled-signal assertions. This is a test synchronization
correction, not a hardware result or a suppressed failure.

Individual diagnostic UTC start/end times and immutable full raw JSON/stdout
logs were not retained in this record. This is a curated, reproducible-command
blocker summary, **not** a complete build/run evidence bundle. The JSON package
plan was inspected for its scope/count; its entire package listing is not
duplicated here. No hardware log, binary, RTL, device tree, address map, waveform,
target trace, or cycle measurement exists from these commands.

## Observed blockers and environment

| Category | Count | Observation |
| --- | ---: | --- |
| Required source gitlinks | 21 | All enumerated required G1 sources are uninitialized |
| Required tool availability | 9 | Verilator, firtool, CMake, dtc, four RISC-V compiler/binutils commands, and Spike unavailable |
| Prepared toolchain prefix | 1 | No usable absolute `RISCV` directory |
| Installed FESVR/RISC-V collateral | 4 | Required headers and libraries unavailable |
| HTIF collateral | 3 | Nano specs, pinned source linker, and compiler-resolved installed linker unavailable |
| **Strict profile total** | **38** | Missing prerequisites, not executed CPU failures |

The four unavailable cross-tool commands are `riscv64-unknown-elf-gcc`,
`riscv64-unknown-elf-g++`, `riscv64-unknown-elf-objdump`, and
`riscv64-unknown-elf-readelf`. Conda is also absent according to the separate
bootstrap preflight. Its six blockers and the historical doctor's 27 blockers
are **different diagnostic scopes**, not alternative counts of this profile.

The profile retained `known_prerequisites_present: false`,
`dependency_closure_qualified: false`, `hardware_qualified: false`, and
`g1_gate_passed: false`. Its `toolchain_version_inputs_verified: true` means the
expected Verilator/firtool version inputs match the preserved lock/CIRCT
definitions; it does not mean either tool is installed or working.

The observed host is Linux x86-64 with glibc 2.41 and nine logical CPUs.
Bootstrap diagnosis reported 10,475,802,624 bytes of host physical RAM and
63,266,398,208 bytes of free disk at that instant. Physical RAM is **not** a
cgroup/effective-memory guarantee, and free disk is a transient observation.
These values do not establish a supported-host matrix or approve a heavy run.

The imported environment pins `sysroot_linux-64=2.34`; the upstream automatic
selection would choose 2.39 on this glibc 2.41 host and regenerate tracked locks.
That is a pin-preservation blocker, **not evidence that glibc 2.41 is intrinsically
incompatible with binaries built against a 2.34 sysroot**. A reviewed
pin-preserving installation procedure remains unvalidated here. No setup was
run, no lock was rewritten, and no network restriction or approval was bypassed.

## Retained input identities

| Manifest | SHA-256 |
| --- | --- |
| `nova/upstream-lock.json` | `933619455d6fbb7f6d209a00124284392a3beba901e3db059badcc4f247b6baf` |
| `nova/g1-profile.json` | `d5d932060bffb917f9351fd6e9c3193474b901d1d0ab6398c605cdd88153e4d6` |
| `nova/g1-workloads.json` | `634bb734f335ed973a39bab57e2152199e3e678cd6a1d3b7cebaa69ffe9a9b4f` |

All nine entries below reported `matches_imported_blob: true` in the actual
bootstrap preflight. Paths beginning `conda-lock-reqs/` are relative to
`conda-reqs/`, as are the other filenames.

| Preserved Conda input | SHA-256 |
| --- | --- |
| `chipyard-base.yaml` | `6dc8119ea8eb1c97f133ef64ad5dccf2eaeef3b895279f865e4fb2c4ffa30857` |
| `chipyard-extended.yaml` | `6879cb4f09e944cae2d5e5690c305a2fdc51727782f9d5701dfe4209f25ca2c1` |
| `circt.json` | `4e93fdaec228bf840ffde67620fa750e3e215d6b7a63bec583143f5012b78dc7` |
| `conda-lock-reqs/conda-requirements-riscv-tools-linux-64-lean.conda-lock.yml` | `4bba9e60c6274b03066c8f861e298f0a74e5e4b7f82b013d93e5460db3bcbe0f` |
| `conda-lock-reqs/conda-requirements-riscv-tools-linux-64.conda-lock.yml` | `a396fd20ef84fe259b68263dc22364351b870517784f1aa74a380d0e77af6f8d` |
| `conda-lock-reqs/conda-requirements-riscv-tools-linux-aarch64-lean.conda-lock.yml` | `c5684b8f66f5b18079131d985defe69dafb94fbde87ac3511ea3aaead748dc36` |
| `conda-lock-reqs/conda-requirements-riscv-tools-linux-aarch64.conda-lock.yml` | `e86c80b7fc9f0e96843e82fe4d220bd604abe6d2a02512aaacae529ce2414498` |
| `docs.yaml` | `7878d307c2e673a266ea2b09f2d33cec5b7b511f8b1f1a6427b55ccab8e37011` |
| `riscv-tools.yaml` | `baa76379f13cebd345cfbbf5b8a95be3e1433fb0555bbc4320fd4bf92e9aa2c2` |

## Plan inspected, not executed

The checkout-normalized campaign plan hash was
`5bac843981ec9ca9e1b12047c15cc5efb510e9604297d73b89c05cedecce5a89`.
Each of `RocketConfig` and `NovaM1BaselineConfig` declares these 15 workloads:

- `hello`, `nova-baseline`, `nova-baseline-fail`;
- `rv64ui-p-simple`, `rv64ui-p-add`, `rv64ui-p-sub`, `rv64ui-p-beq`,
  `rv64ui-p-jalr`, `rv64ui-p-ld`, `rv64ui-p-sd`;
- `rv64um-p-mul`, `rv64um-p-div`;
- `rv64mi-p-csr`, `rv64mi-p-illegal`, `rv64mi-p-scall`.

The default **proposed** limits are two build jobs, a 4G Java heap, a 7,200-second
aggregate acceptance budget, 10 GiB disk floor, 64 MiB per log stream,
10,000,000 simulation cycles, and seed 1. These are neither approved resource
allocations nor measured usage. Sampled disk/log limits and cooperative
cancellation are not peak-memory quotas or an instantaneous whole-process
deadline. Explicit builds can resolve JVM dependencies; the read-only plan
does not prove an offline dependency closure.

Even a future `workloads_observed` result would describe retained protocol
observations, not target-originated exit attestation or G1 acceptance. The
[completion-protocol finding](G1-COMPLETION-PROTOCOL-2026-11-12.md) records why
the pinned HTIF/TestDriver success path is insufficient for the stronger claim.
A `consistent` comparison likewise means matching unauthenticated record
identities, not proof of independent execution or hardware reproduction.

## Review and next action

- G0 remains `in_progress` pending an accountable maintainer decision. G1 is
  `blocked`; `T-BUILD-001` and `T-ISA-001` remain planned and unexecuted.
- No human gate signoff, heavy setup/resource/network/cost approval, paid runner,
  or dependency migration is established by this record. Automated reviews do
  not stand in for those decisions.
- First provide a reviewed, prepared pinned environment with the required
  source/runtime collateral and supplementary tools. Validate source and
  resolved dependency closure without changing the preserved pins silently.
- Establish independently observable target completion, run both declared
  profiles with retained authentic artifacts, repeat from a second clean build,
  resolve the scoped reference comparison, and obtain the gate review. Do not
  turn synthetic tooling fixtures or protocol-only observations into CPU passes.

See [STATUS](../STATUS.md), [BACKLOG](../BACKLOG.md),
[BASELINE_RUNBOOK](../BASELINE_RUNBOOK.md), and
[REPRODUCIBILITY](../REPRODUCIBILITY.md) for the ongoing acceptance contract.
