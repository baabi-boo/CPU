# Research release and fabrication decisions

This is a future release procedure. No NOVA release, qualified hardware profile,
or fabrication authorization is established by this document. Follow
[STATUS](STATUS.md), [ROADMAP](ROADMAP.md), and [GOVERNANCE](GOVERNANCE.md).

## Declare the release profile first

A release publishes a specific evidence-qualified scope, not every item in the
long-term architecture. G9 review must record all applicable prerequisites,
including conditional requirements not represented by the minimum dependency
list in [project.json](../../nova/project.json).

| Profile | Required earlier evidence | Claims excluded unless separately qualified |
| --- | --- | --- |
| Engineering foundation | G0 repository checks and provenance | HDL execution, CPU correctness, FPGA or silicon |
| Single-core simulation | G0–G1 for the named configuration | Multicore, accelerators, physical hardware |
| Heterogeneous system simulation | G0–G3 | GPU/NPU, physical memory, FPGA operation |
| CPU experiment | G2 and G4; G3 for OS workloads | General performance or efficiency beyond measured scope |
| Accelerator simulation | G3 plus G5 and/or G6 for included blocks | Unincluded accelerators, untested graphics APIs or coherence |
| FPGA prototype | G7, its G2/G3 prerequisites, and included accelerator gates | ASIC timing/power or fabrication readiness |
| ASIC feasibility study | G8 and every included block's qualification | Tapeout readiness, yield, or measured silicon |

Every profile also needs the scoped `REQ-REL-001` / `T-RELEASE-001` review.
`REQ-REL-002` / `T-AUTH-001` must record that a research release grants **no
fabrication authorization**; an actual fabrication proposal requires the
additional decision described below. An omitted capability must appear in the
release limitations, not disappear from the architecture without explanation.

## Release-candidate workflow

1. Open a bounded release PR identifying profile, exact configuration, included
   blocks, required gates, requirement coverage, and unresolved defects/risks.
2. Freeze the candidate commit, dependency gitlinks, toolchain locks, workload
   inputs, and build instructions. Identify any non-reproducible or restricted
   inputs; reject unexplained dirty working-tree results as clean evidence.
3. Reproduce from a clean checkout. Run `make -f nova.mk check` and every
   profile-relevant hardware/software test. Keep failures, exclusions, seeds,
   timeouts, and raw results; a skipped job or unavailable tool is not a pass.
4. Assemble the artifact manifest below and validate every download and checksum.
   Reconcile README, status, requirement records, and release notes with evidence.
5. Assign an actual human maintainer and reviewer, record their names and review
   date, and resolve blocking findings. Roles are currently unassigned; agent
   reviews assist but do not constitute independent hardware or silicon signoff.
6. Record `go`, `conditional go`, or `no-go`. A conditional research decision
   must state its restrictions and does not mark unmet gates passed. Publish only
   the approved scope after explicit release approval.
7. Create the approved immutable tag and publish the reviewed source/artifacts,
   checksums, reproduction instructions, known issues, and evidence index. Record
   which source commit the tag resolves to; do not infer evidence from a tag name.

## Required release artifact manifest

For each file, record its name, purpose, byte size, SHA-256, immutable location,
source revision, build command, evidence level, and distribution/license status.
The release should include:

- Source revision and recursive dependency manifest, plus toolchain/lock hashes.
- Qualified configuration, generated topology/map, workload/input identities,
  firmware/image hashes, and exact reproduction commands where applicable.
- Test matrix, logs/results, coverage and exclusions, resource limits, and human
  review records. Use the [evidence template](evidence/TEMPLATE.md) for real runs.
- FPGA constraints/bitstream or ASIC reports only for the applicable profile,
  with target identity and clear generated/estimated/measured labels.
- [Third-party notices](../../THIRD_PARTY_NOTICES.md), applicable licenses,
  source obligations, and a list of omitted restricted artifacts.

Never publish credentials, proprietary PDK/IP, restricted models, or private
logs merely to make a release look complete. Restricted evidence must have an
approved access and retention plan. A checksum proves content identity, not that
a test ran or a design works; reviewers must verify the evidence-to-claim link.

## Versioning, withdrawal, and rollback

Use explicit prerelease labels for research candidates and document incompatible
configuration, driver, ABI, or artifact-format changes. No stable ABI is promised
by the initial project foundation. Do not reuse or silently move published tags.
Correct source through a reviewed revert/fix and publish a new version. Mark a
defective release superseded or withdrawn, retain its diagnostic history where
safe, identify affected users/artifacts, and document migration or rollback.
Never recommend flashing a rollback without checking board/firmware compatibility.

## Separate fabrication authorization

A research release or G8 feasibility result is not permission to order silicon.
An actual proposal requires G8 gap closure, qualified technology/IP access,
foundry-appropriate DRC/LVS/timing/power/DFT and other signoff, packaging and test
plans, responsible human engineers, approved budget, logistics, and explicit
maintainer authorization. Record unresolved risks and who accepts them.
Fabrication acceptance still does not prove silicon functionality: physical
parts require a separately reviewed bring-up and measurement campaign.
