# Reproducibility and evidence contract

This document defines records required for future engineering work. It does not
report a successful build, simulation, FPGA test, or silicon measurement.
See [STATUS](STATUS.md), [VERIFICATION](VERIFICATION.md), and
[ROADMAP](ROADMAP.md) for the qualification boundaries.

## Identify the complete source state

Every run must identify the superproject commit, configuration, and effective
source contents. A branch name or the word “latest” is not a reproducible pin.

```bash
git rev-parse HEAD
git status --porcelain=v1 --untracked-files=all --ignore-submodules=none
git submodule status --recursive
```

These are local inspection commands, not dependency initialization commands.
Record uninitialized submodules, SHA mismatches, and submodule-local changes.
The diagnostic is a convenience, not proof that all relevant working trees are
clean. Recursive submodule status identifies commits, not complete local file
contents. Inspect tracked modifications, untracked files, and relevant ignored
build inputs in every selected dependency, including nested dependencies;
superproject status alone does not identify all their contents.

[.gitmodules](../../.gitmodules) supplies dependency locations. Git tree gitlinks
pin exact dependency revisions. The [upstream lock](../../nova/upstream-lock.json)
records the imported Chipyard baseline and original dependency pins. Nested
dependencies also need their actual initialized revisions in run evidence.

For a dirty run, retain a reviewable patch and identify relevant untracked files
and local dependency modifications, with content hashes. If the effective source
cannot be shared or reconstructed, label the reproducibility limitation; do not
describe a dirty checkout as the clean named commit. Do not publish credentials
or confidential source in patches or logs.

## Toolchain and environment

Preserve the selected platform-specific lock under
[`conda-reqs/conda-lock-reqs`](../../conda-reqs/conda-lock-reqs), its content hash,
setup options, and resolved package/tool versions. Record the relevant CIRCT
selection from [`conda-reqs/circt.json`](../../conda-reqs/circt.json).
Changing a lock is a reviewed dependency migration, not routine setup cleanup.
Capture lock hashes before and after setup: the pinned setup can regenerate locks
after adjusting its sysroot for host glibc even when unpinned-dependency mode is
disabled. Record and review that diff before calling a run a pinned reproduction.

The upstream lock records baseline Git blob hashes for all nine tracked
`conda-reqs` definitions and locks, including `circt.json`. The NOVA checker
requires each record and rejects missing or changed files. A post-setup rewrite
therefore fails the provenance check until a dependency migration is explicitly
reviewed; do not remove a record or replace its hash merely to make setup pass.
Review the changed definitions, regenerated locks, resolved dependencies, and
affected evidence together under the migration procedure below.

### NOVA-001 pre-setup provenance gate

Before running heavyweight setup, record maintainer approval for the specific
host, available RAM and disk space, network use, maximum CPU parallelism, wall
time, and monetary cost. In a clean checkout, first run the non-mutating
repository checks and bootstrap preflight:

```bash
make -f nova.mk check
make -f nova.mk doctor-strict
python3 -B scripts/nova/bootstrap_preflight.py --json
```

The strict doctor is expected to fail while required tools or submodules are
missing; retain that result as `blocked`, not as a successful environment check.
Preflight is a source and host diagnostic, not permission to execute setup and
not hardware qualification. An unavailable preflight implementation must also
be recorded honestly rather than counted as a pass.

Record the host's actual glibc version alongside the pinned
`sysroot_linux-64` value in `conda-reqs/chipyard-base.yaml` and the sysroot that
`scripts/build-setup.sh` would select. On a glibc 2.41 host, for example, the
current setup script selects 2.39 instead of the imported 2.34 and can rewrite
tracked Conda inputs and regenerate lockfiles **without**
`--use-unpinned-deps`. Treat that as a proposed dependency migration, not a
successful reproduction of the original pins; stop before the rewrite unless a
reviewed migration explicitly authorizes it.

For each attempt, calculate and retain SHA-256 digests of **all nine** tracked
Conda definitions and locks named under `preserved_blobs` in
`nova/upstream-lock.json`, both immediately before and after setup. Preserve the
Git blob IDs from the manifest as separate provenance information: a Git blob
SHA-1 is not a file-content SHA-256. Compare pre/post hashes and relevant
working-tree diffs, including ignored build inputs and nested submodule state.
No unreviewed lock, Git gitlink, or generated tool input drift is acceptable.
Likewise, record precisely which required and optional submodules were
initialized; a `--use-lean-conda` run may still initialize optional projects
through an upstream `--full` submodule step.

Record host OS/architecture, Java, Scala/sbt selection, compiler/linker, Verilator,
firtool, firmware builders, reference model, FPGA/ASIC tools as applicable,
and their exact options. Include parallelism, memory/disk limits, timeouts,
locale or other settings that materially affect the run. A container tag is not
immutable: record an image digest and build provenance when a container is used.

Use a minimal allowlist of relevant environment information. Never attach a full
`env` or `printenv` dump, tokens, passwords, private URLs, license-server secrets,
or unrelated user data. Sanitize logs before sharing and document any redaction
that affects reproducibility. Do not expose secrets merely to hash or identify
an environment. See [SECURITY](../../SECURITY.md) for sensitive reports.

## Run record

For each executed or attempted test, retain:

| Field | Required content |
| --- | --- |
| Identity | Requirement/test IDs, gate, evidence level, exact scope and configuration |
| Source | Commit, dirty status/patch identity (including relevant ignored inputs), recursive dependency revisions and pre/post hashes for all nine tracked Conda inputs |
| Inputs | Workload, binary/image/data hashes, ISA/ABI, firmware, random seed |
| Model | Generated hart inventory/map, memory model, timing/cache parameters and clock assumptions |
| Invocation | Exact command and working directory, tool versions, relevant options |
| Resources | Approved host/target identity, glibc and pinned sysroot, RAM/disk/network budget, monetary cost, parallelism, start/end time and enforced timeout/resource limits |
| Outcome | Expected versus observed behavior, exit code, status and failure diagnostics |
| Artifacts | Logs, traces, generated reports and cryptographic content hashes |
| Review | Reviewer/role, exclusions, unresolved issues, reproducibility and gate decision |

Use explicit test outcomes: `not_run`, `blocked`, `failed`, or `passed`. A missing
tool, skipped job, absent completion marker, or zero discovered tests cannot be
reported as a pass. Preserve failed commands and timeouts, not only the eventual
successful invocation. If an approval is absent or the host would rewrite pinned
inputs, record the blocked setup step, offending prerequisites, and the exact
unexecuted commands; do not claim those commands ran. A passing test closes only
its stated scope.

### Bounded Rocket smoke runner: partial evidence only

The opt-in [Rocket baseline runner](../../scripts/nova/rocket_baseline.py) is a
convenience for the first `RocketConfig` smoke campaign. Review its intended
commands without a toolchain or side effects:

```bash
make -f nova.mk rocket-plan
```

Only after the maintainer has accepted G0, approved the resource budget, and
prepared the pinned toolchain should an operator consider the separate
`--execute --approved-budget` mode. This mode does **not** install Conda,
initialize submodules, or authorize itself. It requires a clean checkout and
the strict prerequisite/source checks, and stops on a failed stage or exceeded
budget. The [G1 baseline runbook](BASELINE_RUNBOOK.md) describes the broader
setup and independent qualification procedure.

An executed attempt writes a local `nova-out/rocket-baseline-*/record.json`
and separate stage logs. The record retains stage commands, time budgets,
exit codes, timestamps, log hashes, and a smoke-only outcome. A zero exit is
not sufficient: the `hello` binary must be an ELF64 little-endian RISC-V
executable, and the simulator log must contain the actual target's expected
`Hello world from core 0` output. That text is hard-coded by the inherited
single-core test and **does not identify a hart**. An output marker is still
only smoke evidence, not proof of architectural correctness. Preserve actual
completion/termination diagnostics and reject missing output, wrong binaries,
timeouts, and unexpected simulator behavior.

The runner result `hello_marker_observed_unqualified` explicitly records
`target_completion_verified=false` and is not a G1 pass. It covers only one
upstream Rocket smoke path; it does not execute the named
`NovaM1BaselineConfig`, a declared architectural ISA/trap/MMU suite,
reference comparisons, or a second clean reproduction. `T-BUILD-001` and
`T-ISA-001` remain planned until their complete campaigns are implemented and
run. The local runner record must be supplemented with exact recursive gitlink
state, pinned lock hashes before/after setup, tool versions, source patches,
generated RTL/device tree/hart and memory-model data, negative tests,
independent-build artifacts, exclusions, and a recorded reviewer decision.
Treat absent fields or unavailable artifacts as unverified, never inferred.

Record generated RTL, device tree/address map, actual memory-model parameters,
and each hart's observed capabilities for simulation qualification. Reference
models require pinned versions, comparison adapters, supported feature sets, and
explicit mismatch/exclusion policy. Hardware evidence additionally needs board
or device identity, constraints, bitstream/layout hashes, and measurement setup.

## Artifact handling

Use ignored `nova-out/` for local logs and generated output. A local path alone
is not retrievable review evidence: attach artifacts to a retained run or publish
approved, sanitized records with stable locations and hashes. Small curated
records may be committed under `docs/nova/evidence/`; do not commit large waveforms,
build trees, proprietary PDK/IP, or secrets by default.

An evidence index should state retention/access constraints and distinguish raw
logs from summaries. Hashes establish content identity, not that a test actually
executed correctly. Review must relate the command, expected result, output, and
claimed capability. Repository checks cannot perform hardware signoff.

## Dependency migration and comparison

1. Propose the source, old/new revision, motivation, affected requirements, and
   license/compatibility impact in a bounded PR and architectural decision.
2. Preserve a reproducible old baseline; update gitlinks, applicable toolchain
   locks, provenance records, and documented assumptions together.
3. Run relevant baseline and candidate tests on controlled workloads and inputs.
   Record differences, failures, exclusions, and any changed measurement model.
4. Invalidate affected earlier evidence explicitly. Reopen dependent gates when
   their assumptions no longer hold; a pin update does not inherit old passes.
5. Review results and a rollback plan before accepting the migration.

Keep target cycles separate from host simulator runtime; keep simulation,
synthesis estimates, FPGA measurements, and silicon measurements separate.
Comparisons must disclose changed binaries, memory models, compiler options, or
operating conditions. Follow [BENCHMARKS](BENCHMARKS.md) for performance studies.
