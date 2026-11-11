# Contributing to NOVA-M1

NOVA-M1 is an early-stage RISC-V SoC research project built on Chipyard. Read the
[charter](docs/nova/CHARTER.md), [status](docs/nova/STATUS.md),
[engineering rules](AGENTS.md), and relevant subsystem specification first.
The preserved [Chipyard contribution policy](docs/nova/upstream/CONTRIBUTING.chipyard.md)
applies to work submitted to that upstream project; this guide covers NOVA work.

## Propose a bounded change

1. Describe the problem, affected requirement IDs, scope, and acceptance tests in
   a NOVA issue or pull request. Use existing IDs from
   [the requirements register](nova/requirements.json); allocate new IDs there
   when introducing new requirements rather than renumbering existing ones.
2. For architecture, public interface, memory-contract, dependency, or toolchain
   changes, include an [architecture decision record](docs/nova/adr/README.md)
   and an impact assessment before implementation expands the scope.
3. Estimate runtime, storage, and external resources for expensive experiments.
   Maintainer approval is required before paid services, purchases, new runners,
   licensed IP, fabrication, secrets, or physical-device access are introduced.

Keep each PR small enough to review. Separate mechanical formatting, dependency
updates, and functional changes when practical. Preserve unrelated work.

## Branch and review workflow

- Create a topic branch from the current `main`; submit subsequent changes by PR.
- Explain what changed, why, which requirements it addresses, and how to reproduce
  verification. Include known failures, exclusions, and tests not run.
- Do not force-push shared branches, rewrite published history, or use destructive
  resets to resolve another contributor's changes. Coordinate overlapping work.
- Request review of the affected hardware, software, and verification interfaces.
  See [governance](docs/nova/GOVERNANCE.md) for responsibilities and gate decisions.
- The maintainer decides when to merge. This written policy does not configure or
  prove GitHub branch protection, required reviews, or required status checks.

For parallel work, assign disjoint file ownership. Only the integrating owner
changes shared interfaces, commits the combined work, or publishes it. Agent
review is useful assistance, not independent hardware or manufacturing signoff.

## Checks and evidence

Run the lightweight repository checks from the repository root:

```bash
make -f nova.mk check
git diff --check
```

These checks validate project infrastructure; they do not compile, elaborate,
simulate, or qualify a processor. Hardware or target-software changes also need
the appropriate tests in the [verification plan](docs/nova/VERIFICATION.md).
Use the [development guide](docs/nova/DEVELOPMENT.md) for explicit setup commands.
Do not make dependency installation a side effect of a local check command.

Every verification record must identify the requirement/test, Git revision,
dirty state, configuration, dependency and tool versions, workload, command,
seed where relevant, resource limits, exit status, expected/observed result,
and retrievable logs/artifacts. See
[reproducibility](docs/nova/REPRODUCIBILITY.md) for the evidence contract.

Report missing prerequisites as blocked or not run, never passed. Preserve
negative results. Do not weaken tests or acceptance criteria to hide a failure.
Do not use passing documentation CI as evidence of RTL correctness, measured
efficiency, unified accelerator coherence, FPGA operation, or tapeout readiness.

## Dependency and attribution discipline

- Preserve existing copyright headers, licenses, and notices. Read
  [third-party notices](THIRD_PARTY_NOTICES.md) before copying or modifying code.
- Keep NOVA additions isolated where practical; identify reused upstream IP and
  original contributions separately.
- `.gitmodules` identifies dependency locations; gitlinks pin exact revisions.
  Do not update dependencies to an unrecorded "latest" version.
- A dependency/toolchain update must include its source, old/new pins, reason,
  compatibility and license review, regression evidence, and rollback strategy.
  Update the applicable lock/provenance records in the same reviewed change.
- Do not replace the root license or assume it grants rights to every submodule,
  PDK, memory macro, vendor tool, workload, or hardware IP block.

## Reporting problems

Report NOVA bugs in [this repository](https://github.com/baabi-boo/CPU/issues),
with a minimal reproducer and sanitized logs. Establish whether a problem is
upstream before reporting it to Chipyard or a dependency maintainer.
For suspected vulnerabilities, follow [SECURITY.md](SECURITY.md); do not post
secrets or sensitive exploit details in a public issue.
