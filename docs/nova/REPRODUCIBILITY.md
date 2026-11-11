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
| Source | Commit, dirty status/patch identity, dependency revisions and lock hashes |
| Inputs | Workload, binary/image/data hashes, ISA/ABI, firmware, random seed |
| Model | Generated hart inventory/map, memory model, timing/cache parameters and clock assumptions |
| Invocation | Exact command and working directory, tool versions, relevant options |
| Resources | Host/target identity, limits, parallelism, start/end time and timeout policy |
| Outcome | Expected versus observed behavior, exit code, status and failure diagnostics |
| Artifacts | Logs, traces, generated reports and cryptographic content hashes |
| Review | Reviewer/role, exclusions, unresolved issues, reproducibility and gate decision |

Use explicit test outcomes: `not_run`, `blocked`, `failed`, or `passed`. A missing
tool, skipped job, absent completion marker, or zero discovered tests cannot be
reported as a pass. Preserve failed commands and timeouts, not only the eventual
successful invocation. A passing test closes only its stated scope.

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
