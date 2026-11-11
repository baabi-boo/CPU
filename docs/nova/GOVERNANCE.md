# Governance and engineering review

This document defines responsibilities and evidence-based decisions. It does
not assert that a staffed team, branch protection, or a security response service
already exists. Named role assignments are unassigned until the repository
maintainer explicitly records them.

## Responsibilities

| Role | Responsibility | Required review focus |
| --- | --- | --- |
| Maintainer | Accept scope, assign owners, merge changes, authorize resources/releases | Authority, maintainability, and unresolved blockers |
| Architecture owner | Maintain interfaces, requirements, and architecture decisions | ISA/platform contracts, coherence, compatibility, and scope |
| Subsystem owner | Implement bounded work and maintain tests/documentation | Local correctness and cross-subsystem effects |
| Verification reviewer | Assess tests, reproducibility, exclusions, and evidence | False passes, missing coverage, and regression risk |
| Platform/physical owner | Own board or process constraints and implementation studies | Timing, power methodology, external IP, and later signoff |

One person can hold several roles, but a review record must disclose that fact.
Do not describe self-review, automated checks, or multiple AI agents as qualified
independent silicon signoff. No CODEOWNERS entries or reviewer identities should
be fabricated to make the process appear staffed.

## Requirements and architecture changes

The [requirements register](../../nova/requirements.json) is the stable mapping
from requirement IDs to design intent, verification methods, and evidence.
Keep IDs stable; record replacements and rationale instead of recycling IDs.
The [roadmap](ROADMAP.md) supplies gates G0 through G9.

Use an [ADR](adr/README.md) for changes to architectural direction, interfaces,
memory/DMA ownership, ISA assumptions, dependency/toolchain baselines, or
technology choices. Record context, alternatives, the decision, consequences,
affected requirement IDs, validation, and rollback or migration needs.
Draft decisions remain proposed until the maintainer records acceptance.

Requirement or acceptance changes must explain why the previous criterion is
inadequate and what coverage remains. A failed experiment is not justification
for silently lowering the criterion or deleting the failure record.

## Pull-request acceptance

A review should answer:

1. Is the change bounded, attributable, and consistent with approved interfaces?
2. Are relevant requirement IDs and affected gates identified?
3. Are tests reproducible, with failures, exclusions, and unrun tests visible?
4. Are claims limited to the demonstrated evidence level?
5. Are dependency pins, notices, documentation, and risk records updated?
6. Are cost, runtime, storage, secrets, devices, and external access authorized?

Follow the root [contribution guide](../../CONTRIBUTING.md). Future changes use
topic branches and PRs. Maintainers should configure suitable protections and
required checks separately; until verified, record those settings as unconfirmed.
Do not bypass a protected workflow or approval requirement.

## Gate decisions and status

The authoritative current state is [STATUS.md](STATUS.md). Milestones use
`planned`, `in_progress`, `blocked`, `passed`, or `failed`. Test records distinguish
passed/failed from blocked/not run. A source implementation is not automatically
an elaborated, simulated, FPGA-validated, or silicon-measured capability.

For each gate decision record:

- Gate ID, revision/configuration, scope, date, and accountable reviewer.
- Requirement/test coverage, artifact locations/hashes, and reproducibility.
- Failed, excluded, blocked, and unrun checks with their consequences.
- Open risks, resource assumptions, decision, and next actions.

**Go** means the stated gate criteria are met. **Conditional go** authorizes
specified follow-on investigation while blockers remain; it does not mark an
unmet gate passed. **No-go** pauses dependent acceptance until corrective work
or a formally reviewed scope change resolves the problem.

A documentation/metadata pass can satisfy only its foundation criteria.
Manufacturing readiness and post-silicon qualification require their own
accountable reviews, not inherited confidence from simulation or a layout image.

## Resource, risk, and release control

Keep the [risk register](RISKS.md) current after significant design or dependency
changes. Assign responsible roles and concrete mitigation triggers; do not imply
a risk has vanished because it has a document entry.

Expensive or external work must have a bounded plan and explicit maintainer
authorization where required: paid compute, hardware purchases, new runners,
credentials, licensed IP, fabrication, and physical-device access. No unlimited
budget follows from a roadmap item. Stop at permission and protected-workflow
boundaries and report what approval is missing.

Release decisions follow [RELEASES.md](RELEASES.md), identify the evidence level,
and disclose unresolved limitations. Security handling follows
[SECURITY.md](../../SECURITY.md). Neither a release label nor an agent count is
evidence that the chip meets its electrical, architectural, or security goals.
