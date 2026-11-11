# Continuous integration scope

NOVA's initial CI checks repository engineering infrastructure. It does **not**
elaborate RTL, execute RISC-V instructions, boot Linux, or qualify an FPGA/ASIC.
A green foundation job cannot close hardware gates G1–G9.

## Lightweight foundation workflow

[`nova-foundation.yml`](../../.github/workflows/nova-foundation.yml) is configured
for pushes to `main`, pull requests, and manual dispatch. Its single hosted
Ubuntu 24.04 job has a five-minute timeout and cancels superseded runs for the
same branch or PR. It uses read-only repository permission, a commit-pinned
checkout action, no persisted checkout credentials, and no submodule downloads.

The runner's Git, Python 3, and GNU Make execute the same entry point used locally:

```bash
make -f nova.mk check
```

| Target | Scope |
| --- | --- |
| `validate` | Structured project/requirement checks, local documentation targets, source configuration scaffolds, and preserved upstream provenance |
| `test` | Python-standard-library tests of NOVA tooling, with a nonempty-discovery guard |
| `whitespace` | NOVA-managed text files, including committed files, plus `git diff --check` |
| `check` | All three checks above |

These checks do not install a toolchain, publish a package, contact a cloud
service, fetch optional hardware dependencies, or use project secrets. External
web-link availability and hardware functional correctness are outside their
scope. A declared test or configuration name is not execution evidence.

The guarded test runner rejects zero discovered tests, discovery/import errors,
and failing tests. Removing the test directory cannot silently produce a green
foundation job.

The managed-text check rejects trailing whitespace and missing final newlines in
NOVA documentation, metadata, tooling, configuration scaffolds, and selected CI
files. It excludes preserved upstream documents and licenses. Unlike a working
tree diff alone, it also checks a clean CI checkout. Small workflow text-contract
tests guard the pinned action, read-only permissions, bounded job, and upstream
entry-point restrictions; they do not replace GitHub's YAML/workflow validation.

The workflow file establishes intended automation, not proof that GitHub has
executed it. Record an actual run URL/revision and result when available. Failures
and missing evidence must remain visible; do not mark hardware milestones passed
in response to repository-only checks.

## Local diagnosis is separate

The diagnostic preflight is deliberately not a CI gate: lightweight CI is not
expected to contain the hardware toolchain or initialized generator submodules.

```bash
make -f nova.mk doctor
make -f nova.mk doctor-strict
# Equivalent strict invocation:
python3 scripts/nova/doctor.py --strict
```

Diagnosis must remain non-mutating. Follow [DEVELOPMENT](DEVELOPMENT.md) for
explicit, authorized setup and simulation commands. A clean diagnostic result
still does not prove HDL build or target-program execution.

## Preserved upstream workflows

The inherited Chipyard PR dispatcher and scheduled/manual container publisher are
guarded by `github.repository == 'ucb-bar/chipyard'`. Their definitions remain
available for provenance, but NOVA does not automatically invoke their costly
generator/FireSim matrix or publish the upstream-style GHCR image. Downstream
reusable jobs in the PR dispatcher depend on the guarded entry job and are skipped
when it is skipped. Other reusable workflow definitions are preserved unchanged.

Porting any of that infrastructure to NOVA requires a separate review of image
provenance, runner resources, dependency pins, credentials, publishing authority,
runtime/storage limits, and untrusted-PR isolation. Do not simply remove the
guard to obtain a badge or trigger an unaudited container build.

## Future hardware CI

Introduce separate, explicitly named jobs only after a reproducible baseline and
resource budget exist. Begin with bounded single-core RTL elaboration/execution,
then per-hart mixed-core checks, before adding larger regressions. Pin tools and
workloads, preserve diagnostic logs, set timeouts, and document exclusions.
FPGA and ASIC jobs need target-specific tools, licenses/IP, device or runner
access, and appropriate authorization; none is provisioned by this workflow.

Required status checks and branch protection are repository-administrator
settings. This file does not enable them or assert that they are enforced. See
[GOVERNANCE](GOVERNANCE.md), [VERIFICATION](VERIFICATION.md), and
[STATUS](STATUS.md) for acceptance and evidence rules.
