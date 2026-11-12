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
| `test` | Standard-library test harness for NOVA tooling, including bounded local fixtures, with a nonempty-discovery guard |
| `whitespace` | NOVA-managed text files, including committed files, plus `git diff --check` |
| `check` | All three checks above |

The `doctor`/`doctor-strict`, `preflight`/`preflight-strict`, and
`g1-profile`/`g1-profile-strict` targets are opt-in local diagnostics, not members
of `check`. `conda-plan` inspects the pinned package inventory without installing
it. The `rocket-plan`, `g1-plan`, and `g1-campaign-plan` targets are also opt-in;
they print proposed commands and their limits without executing a build or
workload. An environment missing the RISC-V toolchain should not fail the
repository-only CI job merely because it cannot build a processor. Conversely,
a green `check` does not waive an unsafe bootstrap preflight or establish a
hardware result.

These checks do not install a toolchain, publish a package, contact a cloud
service, fetch optional hardware dependencies, or use project secrets. External
web-link availability and hardware functional correctness are outside their
scope. A declared test or configuration name is not execution evidence.

The guarded test runner rejects zero discovered tests, discovery/import errors,
and failing tests. Removing the test directory cannot silently produce a green
foundation job.

The G1 tooling tests cover fixed workload plans, prerequisite and installed
metadata inspection, bounded ELF/artifact capture, source and post-run identity
checks, completion-log parsing, and producer-to-comparator record contracts.
Their simulator logs, target observations, and prepared-toolchain identities are
explicitly synthetic fixtures, not retained hardware results. Process-lifecycle
tests launch bounded local fixture children to check cancellation and cleanup;
temporary Git repositories exercise provenance rules. Host C syntax checks do
not cross-compile or execute the RV64 workload. Passing these tests cannot turn
the declared 15-workload, two-configuration campaign into an executed campaign.

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

Keep workflow, job, and step outcomes distinct. A cancelled or unscheduled job
with no executed steps does not establish a code/test failure, and it does not
establish why execution was unavailable. Missing logs are missing evidence, not
permission to infer a scheduling, billing, or source-code cause. No current remote
CI success is asserted by this document.

## Local diagnosis and setup preflight are separate

The local diagnostics are deliberately not CI gates: lightweight CI is not
expected to contain the hardware toolchain or initialized generator submodules.

```bash
make -f nova.mk doctor
make -f nova.mk doctor-strict
python3 -B scripts/nova/bootstrap_preflight.py --json
python3 -B scripts/nova/bootstrap_preflight.py --strict
make -f nova.mk rocket-plan
make -f nova.mk g1-profile
make -f nova.mk g1-profile-strict
make -f nova.mk conda-plan
make -f nova.mk g1-plan
make -f nova.mk g1-campaign-plan
# Equivalent strict invocation:
python3 scripts/nova/doctor.py --strict
```

These diagnostics must remain non-mutating. `doctor` reports known required
submodules and installed tools; `bootstrap_preflight.py` additionally checks
tracked Conda input hashes and whether the current host's glibc would cause the
upstream setup script to rewrite the pinned sysroot and regenerate locks. The
bootstrap preflight does not install Conda, initialize submodules, reserve
compute resources, or approve a migration. The strict forms return nonzero on
blockers, which is expected on a toolchain-free checkout. Follow
[DEVELOPMENT](DEVELOPMENT.md) for explicit, authorized setup and simulation
commands. A clean diagnostic result still does not prove HDL build or
target-program execution. The plan targets do not initialize submodules, create
a Conda environment, compile RTL, or reserve resources. The G1 profile checks
enumerated prerequisites and runtime collateral, not complete nested/Maven
dependency closure. A matching Conda inventory compares installed metadata
claims with the lock; it does not authenticate installed binary contents.

The preferred [`g1_campaign.py`](../../scripts/nova/g1_campaign.py) runner has a
read-only default plan and a separate `--execute --approved-budget` mode. Neither
that execution mode nor a hardware bootstrap belongs in the foundation job.
Execution requires the runner's own clean, prepared checkout and an already
approved host/resource/network/cost budget. It separately builds `RocketConfig`
and `NovaM1BaselineConfig` and attempts the same fixed 15 workloads for each;
missing prerequisites or workloads block the campaign instead of silently
reducing it. It does not provision the toolchain or initialize submodules, but
explicit build tools can resolve JVM dependencies under the approved network
policy. It is not an offline build-closure guarantee.

The possible result `workloads_observed` describes retained protocol observations,
not hardware qualification. The pinned HTIF/SimTSI path can signal success after
a signal-induced shutdown without a target exit value; see the
[source-level completion review](evidence/G1-COMPLETION-PROTOCOL-2026-11-12.md).
Positive observations therefore keep `target_completion_verified: false` even
when `completion_protocol_observed: true`. The deliberate failure control has
its own exact code-7 assertion contract; arbitrary nonzero exits do not satisfy
it. Runner-owned interruption, timeouts, or evidence-integrity failures cannot
be reclassified as successful workload observations.

[`compare_campaigns.py`](../../scripts/nova/compare_campaigns.py) is also read-only.
Its `consistent` result means that the supplied record identities agree; it does
not authenticate execution, prove independent clean builds, validate shared-cache
absence, or close a gate. Hardware and G1 qualification flags remain false in all
these helpers. See the [baseline runbook](BASELINE_RUNBOOK.md) for the operator
procedure and the [preparation record](evidence/G1-PREPARATION-2026-11-12.md) for
the observed blocked host state.

The narrower legacy [`rocket_baseline.py`](../../scripts/nova/rocket_baseline.py)
runner has an execution mode requiring both `--execute` and
`--approved-budget`. This is **not a GitHub Actions entry point**: it requires
an already prepared pinned toolchain, a clean checkout, and explicit maintainer
approval of host, memory, disk, parallelism, wall time, network access, and
costs. The runner builds only the upstream `RocketConfig` and runs a bounded
bare-metal `hello` smoke test, checks the RISC-V ELF and target output, and
retains local per-stage logs. Its possible `hello_marker_observed_unqualified`
result does not independently verify target completion and does not qualify
`NovaM1BaselineConfig`, the ISA campaign, independent clean-build reproduction,
or G1 acceptance.

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

Do **not** add a Chipyard bootstrap, recursive submodule initialization,
Verilator compilation, or a hardware pass badge to the existing five-minute
foundation job. Those operations may download substantial dependency trees,
change lock inputs on some hosts, and exceed its runtime/memory budget. An
approved hardware workflow needs a separately identified and budgeted runner,
an immutable toolchain and dependency manifest, explicit resource/timeout
limits, selected tests with failure detection (including target-output,
binary-architecture, and independently observed target-exit checks), retained
logs and generated RTL, and a recorded
link from the tested commit to its evidence. A skipped,
timed-out, or unrun job must remain `not_run`, `blocked`, or `failed` as
appropriate, not `passed`. Running it on a hosted runner would not itself
constitute maintainer G1 acceptance.

Required status checks and branch protection are repository-administrator
settings. This file does not enable them or assert that they are enforced. See
[GOVERNANCE](GOVERNANCE.md), [VERIFICATION](VERIFICATION.md), and
[STATUS](STATUS.md) for acceptance and evidence rules.
