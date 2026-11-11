# NOVA-001 preflight observation — blocked

**Observation date:** 2026-11-11 (UTC)

**Evidence level:** repository/environment prerequisite diagnostics only

**Outcome:** `blocked` for toolchain preparation; **not a hardware-test failure or pass**

This is a historical observation of one temporary, unprepared development host.
It does not close NOVA-001, `T-BUILD-001`, `T-ISA-001`, G0, or G1. No toolchain
was installed, submodule initialized, RTL elaborated, simulator built, target
binary executed, or hardware measured as part of this observation.

## Source and environment

| Field | Observed value |
| --- | --- |
| Repository | `baabi-boo/CPU`, inspected from its root |
| Base superproject revision | `97d7eff6b6f8ba604502c84bfdb08ac6469b0bbb` |
| Working tree | **Dirty**: parallel NOVA tooling/documentation edits and new files present; no clean-checkout reproduction |
| Tracked diff identity | SHA-256 of `git diff --binary HEAD`: `1b772c76f01d538691f9dc382f25a65df2f6b9ac28bc27065f197a3d26a08df0` at observation time |
| Identity limitation | The diff hash excludes untracked files and may change with subsequent edits; it is **not** a complete source snapshot or reproducible run revision |
| Indexed dependency gitlinks | 57, all uninitialized in this checkout; 21 currently classified as known G1 prerequisites, not a verified full transitive closure |
| Imported Conda inputs | All nine tracked definitions/locks matched the imported Git blob hashes; the preflight computed per-input SHA-256 values, but no immutable raw JSON log was retained |
| Host | Linux x86-64, glibc 2.41, approximately 9.7 GiB physical RAM, no swap, approximately 59 GiB free disk, nine logical CPUs |
| Resource approval | No approved heavyweight installation/build budget or paid runner was recorded; only lightweight diagnostics were executed |

The imported `conda-reqs/chipyard-base.yaml` pins
`sysroot_linux-64=2.34`. On this host, the inherited
`scripts/build-setup.sh` logic would select `2.39` and regenerate tracked
Conda locks. Running that setup unreviewed would invalidate pinned-source
reproduction. Git, Java and GNU Make were present; Conda, Verilator, `firtool`,
CMake, and RISC-V GCC were unavailable. `env.sh` and an active `RISCV` directory
were absent.

## Commands and observed results

All commands were executed at the repository root without package installation,
network-dependent setup, or hardware compilation. The diagnostic tools are
non-mutating; their exit codes describe prerequisite availability only.

| Command | Exit code | Observation |
| --- | ---: | --- |
| `python3 -B scripts/nova/bootstrap_preflight.py --json` | 0 | Informational report with seven blockers; all nine imported Conda inputs matched |
| `python3 -B scripts/nova/bootstrap_preflight.py --strict --json` | 1 | Strict mode rejected the dirty source, unsafe lock rewrite, and missing tools |
| `python3 -B scripts/nova/doctor.py --strict --json` | 1 | Twenty-seven known blockers: 21 uninitialized required gitlinks plus six environment/toolchain prerequisites |

The expected strict-mode outcome for these missing prerequisites was nonzero,
and both strict checks behaved accordingly. The commands' per-stage UTC
timestamps, CPU/memory utilization and full sanitized JSON outputs were not
retained; this is a curated blocker summary, **not** a complete reproducibility
or acceptance artifact. No binary, RTL, device-tree, waveform, simulator log,
target instruction trace, ISA reference comparison, or test coverage exists
from this preflight.

## Exclusions, review and next action

- `T-BUILD-001` and `T-ISA-001` remain **planned/not executed**. No target
  execution or architectural verification was attempted.
- G0 remains `in_progress` pending maintainer acceptance; G1 remains `planned`.
  No `go` or gate-pass decision was made here.
- No human maintainer or independent qualification reviewer signed off this
  observation. Automated worker checks are not hardware signoff.
- Before NOVA-001 installation/build, obtain the required host/RAM/disk/network/
  parallelism/wall-time/cost approval, choose a pin-preserving compatible setup
  or review a formal lock migration, and verify the complete build dependency
  closure. Preserve exact clean-source, toolchain, build, workload and log
  artifacts for any subsequent real Rocket experiment.

For the acceptance contract see [BACKLOG](../BACKLOG.md),
[BASELINE_RUNBOOK](../BASELINE_RUNBOOK.md),
[REPRODUCIBILITY](../REPRODUCIBILITY.md), and
[VERIFICATION](../VERIFICATION.md).
