# Engineering-foundation bootstrap review

Date: 2026-11-11. Imported Chipyard baseline:
`a7946ede9bd625204435715dc40c750e2f8a251f`.

This record concerns repository infrastructure, not an executed NOVA processor,
an accepted hardware gate, or a research release. Source and qualification state
remain in [STATUS](STATUS.md) and the [structured register](../../nova/project.json).

## Review method and accounting

The requested review uses ten sequential waves of six distinct automated worker
assignments, with an integrating agent handling cross-file changes and commits.
All ten waves are complete (60 workers), including the final acceptance review.
The available concurrency limit requires each wave to run in groups of at most
three workers. Read-only audits count as completed assignments when their scope
and findings are returned; an audit need not invent changes to be useful.

These are AI-assisted engineering tasks, not sixty independent human engineers,
a staffed verification team, or qualified silicon signoff. Maintainer acceptance
and later hardware qualification remain separate decisions.

| Wave | Worker IDs | Six assigned scopes | Integrated outcome |
| --- | --- | --- | --- |
| 1 | 01–06 | Architecture; inherited CI; provenance; memory; verification; roadmap | Established the pinned-source baseline and separated existing infrastructure from proposed capabilities |
| 2 | 07–12 | README; charter; roadmap; system architecture; contribution policy; requirements | Created the project identity, scope, gates, and initial traceability register |
| 3 | 13–18 | CPU; memory; accelerators; platform; physical implementation; verification | Defined subsystem interfaces, acceptance evidence, and explicit unverified boundaries |
| 4 | 19–24 | Configuration aliases; validator; CI; diagnostic tool; issue/security policy; provenance records | Added two source scaffolds, offline checks, bounded CI, safe reporting, and preserved upstream records |
| 5 | 25–30 | Development guide; risk/benchmarks; releases; research; backlog; architecture decisions | Added the long-term workflow, measurement rules, twelve proposed tickets, and decision records |
| 6 | 31–36 | Evidence hardening; diagnostic hardening; architecture review; issue hygiene; traceability; CI contracts | Rejected false evidence, improved dirty-state diagnosis, sanitized inherited reporting forms, and added committed-text checks |
| 7 | 37–42 | Adversarial metadata; real-Git diagnosis; workflow review; filesystem checks; runbook review; configuration contracts | Added negative tests, isolated Git fixtures, safe-path checks, bounded commands, and pinned-source assertions |
| 8 | 43–48 | Claim audit; toolchain provenance; CLI integration; documentation navigation; nonempty test runner; physical-scope audit | Protected nine toolchain inputs, exercised command-line behavior, rejected empty test discovery, and aligned release boundaries |
| 9 | 49–54 | Final validator adversarial review; diagnostic audit; clean shallow checkout; root-error repair; traceability; release/CI readiness | Fixed documentation-root containment and diagnostic root errors; reproduced the candidate from a one-commit checkout and reconciled acceptance tables |
| 10 | 55–60 | Handoff/status; dependency/source boundary; final clean checkout; publication readiness; security regression; integrated acceptance | No blocking foundation issues found; final candidate passed 131 tests in a fresh shallow checkout; publication and hardware acceptance remain separate |

## Concrete findings incorporated

- The initial configurations are Rocket and BOOM v3/Rocket derivatives, not
  original CPU designs or a measured performance/efficiency pair.
- Mixed-hart qualification must cover every hart. Hart-0-only test selection and
  the inherited four-hart `mt-hello.c` cannot qualify the proposed two-hart target.
- The pinned harness uses SimDRAM; older descriptions and future multi-channel
  assumptions must not substitute for inspecting the actual generated model.
- Setup can regenerate Conda inputs for host glibc even without requesting
  unpinned dependencies. All nine imported definitions/locks are now mandatory
  provenance records; drift needs a reviewed migration.
- Empty or renamed template evidence, malformed metadata/index data, unsafe
  paths, and zero discovered tests must not produce an accidental pass.
- Diagnostic errors remain structured and privacy-conscious; unavailable tools
  and uninitialized dependencies are blockers, not hardware failures or passes.
- Power claims require scoped evidence whenever made. A research release records
  that fabrication is not authorized; fabrication proposals require a separate
  authorization and readiness review.
- Inherited costly CI entry points are guarded for their upstream repository.
  NOVA's foundation workflow has read-only permission and a five-minute limit.

## Executed repository checks

| Scope | Tested source | Observed result |
| --- | --- | --- |
| Clean shallow checkout | `b711347e327b4ac8feba43e48af066e48c8e7da6` | `make -f nova.mk check` exited 0; 120 tests passed, plus metadata/provenance, managed whitespace, and Git diff checks |
| Shallow-history independence | Same candidate, one-commit local clone | Imported baseline object absent; checks still passed; index/worktree clean before and after |
| Final reviewed clean shallow checkout | `c3635cd14d82c0a0a582b72e697e62ba7f2a2002` | `make -f nova.mk check` exited 0; 131 tests passed, plus the same repository checks; one-commit history and absent baseline object again verified |
| Final candidate non-mutation | Same final candidate | Help-only default target and normal/strict diagnosis left worktree and index clean; index SHA-256 unchanged |
| Normal diagnostic | Bootstrap checkout and clean candidate | Exited 0, reported thirteen prerequisite blockers and `hardware_qualified: false` |
| Strict diagnostic | Bootstrap checkout and clean candidate | Exited 1 for the missing prerequisites, as intended |
| Workflow/form syntax review | Changed and inherited relevant YAML | Sixteen files parsed with an already available YAML parser; structural checks passed, not complete GitHub workflow validation |

The clean candidate contains 57 indexed gitlinks, all uninitialized. Tests use
the Python standard library and disposable local fixtures; no hardware toolchain
installation, external dependency download, paid service, or device operation was
performed. Temporary test fixtures do not constitute processor simulations.

The final six workers returned a go recommendation for publishing the foundation
only. The integrating agent finalized this review ledger afterward; that does not
substitute for maintainer acceptance, administrator configuration, or hardware
evidence. No reviewer was represented as a human signoff authority.

The commit IDs in the table identify the local review history. Authenticated
publication through the connected GitHub integration creates different commit
IDs. The final reviewed candidate's complete Git tree is
`727018fa015a88d8b8dc3b73c02d0d8fe35f23f3`, verified identical to its
[GitHub-created equivalent](https://github.com/baabi-boo/CPU/commit/613e4afc145577c14a8a43a07439633200fbd02e).
The final publication adds this completed review ledger to that candidate; it
does not change the tested tooling, requirements, configuration code, or pins.

Remote CI execution is separate from this local record. Consult the
[NOVA foundation workflow](https://github.com/baabi-boo/CPU/actions/workflows/nova-foundation.yml)
for an actual run, its exact revision, and its conclusion. Do not infer a remote
pass from the existence of the workflow file or from these local results.

## Remaining acceptance and limitations

- G0 needs the maintainer's recorded acceptance; G1–G9 remain planned. No
  configuration has elaboration, simulation, Linux, FPGA, or silicon evidence.
- Branch protection and private vulnerability reporting are administrator
  settings; this bootstrap does not configure or assert them. At the pre-push
  repository check, `main` protection was reported disabled.
- Local link checks cover file targets, not external-site availability or Markdown
  heading semantics. Source-contract tests are not Scala compilation. YAML parsing
  is not a GitHub run. Evidence-path checks are not semantic hardware signoff.
- Required-submodule diagnosis is a known-prerequisite check, not complete nested
  dependency, ignored-file, tool compatibility, or selected-profile qualification.
- No performance, frequency, area, power, energy-efficiency, Apple compatibility,
  production security, cost, process-node, or manufacturing claim is established.

The next implementation task is NOVA-001 in the [backlog](BACKLOG.md): prepare an
explicitly resourced, pinned hardware environment, then reproduce the unchanged
Rocket baseline and the named NOVA derivative under the
[development procedure](DEVELOPMENT.md).
