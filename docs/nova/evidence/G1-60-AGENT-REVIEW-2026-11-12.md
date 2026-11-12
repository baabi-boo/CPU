# G1 preparation — 60-assignment review ledger

**Record date:** 2026-11-12. **Record state:** All ten waves closed;
all sixty distinct worker assignments completed and their reports integrated.

This ledger records ten sequential waves of six distinct automated worker
assignments. At most six workers operate alongside the integrating agent.
Workers have disjoint editing ownership or read-only review scopes; the
integrator owns shared-interface integration, commits, and publication. An
assignment is an automated task, **not an independent human reviewer or a gate
signoff**. The count describes delegated work, not sixty people or sixty
independent hardware qualification decisions.

The deliverable is tested **G1 preparation and evidence tooling**. G1 remains
`blocked`; G0 remains `in_progress`; G2–G9 remain `planned`. No CPU campaign,
NOVA RTL elaboration, target cross-build, pinned-reference comparison, second
clean hardware build, FPGA result, or silicon result is established by this
ledger. Repository-tool tests do not satisfy `T-BUILD-001` or `T-ISA-001`.

## Observed integration checkpoint

| Field | Observation |
| --- | --- |
| Repository | `baabi-boo/CPU` |
| Local checkpoint reviewed in Wave 9 | `d5471c4968fc5a03420b09b966bf78afb5839eed` |
| Checkpoint Git tree | `b1993b53cd06ed1480b39bc22c9de21465c88a93` |
| Checkpoint description | Integrated preparation tooling, documentation, and legacy runner cancellation fixes |
| Fresh local clone check, reported by assignment 49 | `make -f nova.mk check`: exit 0; 532 tests in 23.095 seconds; full command wall time 23.685 seconds |
| Clone cleanliness | Tracked/untracked porcelain status clean before and after; one ignored Python bytecode cache was observed after testing |
| Plan inspection | `RocketConfig`: 15 workloads; `NovaM1BaselineConfig`: 15 workloads; plan only |
| Publication state at this snapshot | Pending; no claim here that the final integrated tree has moved `main` |
| Final-revision remote CI | Not established by this snapshot; must be checked against the eventual published SHA |
| Acceptance | No human maintainer gate decision recorded by these automated assignments |

Assignment 49 used a fresh **local** clone without hardlinks or submodule
initialization. This tests repository-tool reproducibility, not a second
independent hardware build or reproduction of a remote checkout. Its observed
ignored file was `scripts/nova/__pycache__/campaign_exec.cpython-312.pyc`;
tracked/untracked cleanliness does not imply that no ignored files were created.
The cancellation fixture imports the module in a child Python process. The
integrator subsequently added `-B` to that fixture's child invocation and
reported all 34 execution-engine tests passing in 2.762 seconds. No assertions
were weakened. This later fixture change is outside the checkpoint identity
above. Assignment 57 subsequently verified it in another fresh local checkout,
as recorded in the final-review section below.

The checkpoint and timings identify reported worker/integrator results, not
new test executions performed by the ledger author. Full raw execution logs are
not embedded or asserted to be an immutable evidence bundle. No generated CPU
binary, RTL, waveform, or hardware run log resulted from these checks. Later
changes and final checks must be recorded separately rather than relabeling this
checkpoint as the eventual release revision.

## Assignment roster

The names identify the actual delegated task scopes. Completed entries summarize
the integration history and final review reports. Findings and fixes
were integrated across waves, so a row does not imply that its worker alone
authored every related change.

### Wave 1 — baseline inspection and acceptance scope

| No. | Assignment | Scope / contribution | State |
| ---: | --- | --- | --- |
| 1 | `w01_toolchain` | Inspect pinned toolchain requirements and preparation risks | Completed |
| 2 | `w01_dependencies` | Inspect dependency/submodule requirements and preservation boundary | Completed |
| 3 | `w01_runner` | Inspect the existing baseline runner and execution-evidence gaps | Completed |
| 4 | `w01_target_tests` | Define target-test and failure-control needs | Completed |
| 5 | `w01_ci` | Review lightweight CI and repository-only validation scope | Completed |
| 6 | `w01_acceptance` | Review G1 acceptance conditions and unrun hardware evidence | Completed |

Outcome: implementation work was scoped around an explicit, pinned,
two-configuration baseline campaign. Missing host prerequisites remained
blockers, not an implicit processor pass or authorization to provision a host.

### Wave 2 — contracts, target source, and preparation modules

| No. | Assignment | Scope / contribution | State |
| ---: | --- | --- | --- |
| 7 | `w02_runner_hardening` | Harden legacy baseline execution and evidence handling | Completed |
| 8 | `w02_completion_parser` | Implement bounded completion-protocol assessment | Completed |
| 9 | `w02_target_workload` | Implement the RV64 eight-check target and deliberate code-7 control | Completed |
| 10 | `w02_profile` | Implement the fixed Chisel-6 prerequisite profile | Completed |
| 11 | `w02_conda_inventory` | Implement comparison against the preserved lean package inventory | Completed |
| 12 | `w02_campaign_plan` | Declare exact configuration/workload and command-plan contracts | Completed |

Outcome: 313 repository-tool tests passed at integration. Target C source and
build definitions were added; target cross-compilation and execution remained
not run. Package-metadata comparison was not presented as binary attestation.

### Wave 3 — bounded campaign and retained-record implementation

| No. | Assignment | Scope / contribution | State |
| ---: | --- | --- | --- |
| 13 | `w03_execution_engine` | Implement direct-argv bounded execution and retained logs | Completed |
| 14 | `w03_artifacts` | Implement source, binary, and artifact identity collection | Completed |
| 15 | `w03_workload_assessment` | Implement positive and expected-failure workload assessment | Completed |
| 16 | `w03_orchestrator` | Implement opt-in campaign orchestration and blocked-attempt records | Completed |
| 17 | `w03_reproduction` | Implement strict comparison of retained campaign-record identities | Completed |
| 18 | `w03_reference_scope` | Review reference scope and target-completion observability | Completed |

Outcome: 459 repository-tool tests passed at integration. Source review exposed
the pinned HTIF signal-shutdown ambiguity. Protocol observation, independently
verified target exit, and hardware acceptance were consequently kept distinct.
Record agreement alone does not prove authentic execution or independent builds.

### Wave 4 — independent implementation audits

| No. | Assignment | Scope / contribution | State |
| ---: | --- | --- | --- |
| 19 | `w04_orchestrator_audit` | Audit execution inputs, checkout identity, and lifecycle assumptions | Completed |
| 20 | `w04_execution_audit` | Audit cancellation and descendant cleanup | Completed |
| 21 | `w04_artifact_audit` | Audit source visibility, bounded records, and artifact integrity | Completed |
| 22 | `w04_comparator_audit` | Audit post-state, command, resource, and timing comparisons | Completed |
| 23 | `w04_target_audit` | Audit contradictory target records and failure-control grammar | Completed |
| 24 | `w04_profile_audit` | Audit profile validation and resolved runtime/HTIF collateral | Completed |

Outcome: concrete gaps were retained for repair, including build-variable and
foreign-checkout inputs, SIGTERM cleanup, hidden Git index flags, non-finite JSON,
ignored post-state fields, contradictory terminal records, and prerequisite
identity checks. These audits did not execute a CPU or qualify a dependency
closure.

### Wave 5 — audit findings and regression fixes

| No. | Assignment | Scope / contribution | State |
| ---: | --- | --- | --- |
| 25 | `w05_execution_fix` | Repair execution cancellation and process-group lifecycle handling | Completed |
| 26 | `w05_artifact_fix` | Repair provenance visibility and bounded artifact/JSON validation | Completed |
| 27 | `w05_target_fix` | Reject contradictory and malformed target terminal records | Completed |
| 28 | `w05_profile_fix` | Strengthen profile and compiler-resolved HTIF identity checks | Completed |
| 29 | `w05_orchestrator_fix` | Bind execution to the intended checkout, inputs, and post-state | Completed |
| 30 | `w05_comparator_fix` | Enforce retained-record command, resource, and post-state contracts | Completed |

Outcome: 508 repository-tool tests passed at integration. Fixes retained the
non-provisioning default and fail-closed qualification state; no dependency pins
were migrated to make tests pass.

### Wave 6 — cross-module regressions and contract rechecks

| No. | Assignment | Scope / contribution | State |
| ---: | --- | --- | --- |
| 31 | `w06_integration_tests` | Exercise planner/orchestrator/assessment/record comparison integration | Completed |
| 32 | `w06_cancellation_review` | Independently recheck scoped cancellation and cleanup behavior | Completed |
| 33 | `w06_record_contract_tests` | Add malformed-record and strict-schema regressions | Completed |
| 34 | `w06_profile_review` | Recheck prerequisite and inventory contract boundaries | Completed |
| 35 | `w06_provenance_review` | Recheck source and retained-artifact provenance consistency | Completed |
| 36 | `w06_workload_review` | Recheck exact workload and terminal-record contracts | Completed |

Outcome: 523 repository-tool tests passed. Integration also closed a negative
marker namespace issue, huge-integer conversion failure, and collector/comparator
artifact-limit mismatch. Expensive source/tool/hardware boundaries in integration
tests were explicitly synthetic; those fixtures did not run a compiler or CPU.

### Wave 7 — truthful status, runbooks, and curated evidence

| No. | Assignment | Scope / contribution | State |
| ---: | --- | --- | --- |
| 37 | `w07_status_docs` | Align gate/status/backlog metadata with implemented and blocked work | Completed |
| 38 | `w07_runbook_docs` | Document prepared-host, bounded execution, and reproduction procedure | Completed |
| 39 | `w07_host_evidence` | Record actual prerequisite observations and preserved input identities | Completed |
| 40 | `w07_verification_docs` | Align verification and reproducibility claims with observed evidence | Completed |
| 41 | `w07_entry_docs` | Update project entry points and development guidance | Completed |
| 42 | `w07_protocol_ci_docs` | Document the completion-protocol limitation and CI scope | Completed |

Outcome: integrated documentation and all 523 tests passed after the complete
document set existed. An intermediate missing-link failure and a signal-test
timing assumption were not suppressed. The latter was fixed by waiting for a
cleanup acknowledgement rather than assuming handler order after a fixed sleep.
See the [preparation observation](G1-PREPARATION-2026-11-12.md) for those historical
results and the [completion-protocol record](G1-COMPLETION-PROTOCOL-2026-11-12.md)
for the source-confirmed, not simulator-reproduced, limitation.

### Wave 8 — legacy lifecycle, preservation, and publication-scope checks

| No. | Assignment | Scope / contribution | State |
| ---: | --- | --- | --- |
| 43 | `w08_legacy_runner_fix` | Repair scoped legacy SIGINT/SIGTERM handling, actual exits, and surviving descendants | Completed |
| 44 | `w08_claims_audit` | Audit capability and evidence claims for unsupported promotion | Completed |
| 45 | `w08_runbook_audit` | Check documented commands, prerequisites, and execution scopes | Completed |
| 46 | `w08_preservation_audit` | Check upstream pins, locks, notices, and tracked change boundaries | Completed |
| 47 | `w08_signal_stability` | Repeat the synchronized signal fixture and execution-engine suite | Completed |
| 48 | `w08_evidence_privacy` | Review tracked evidence for accidental sensitive or generated outputs | Completed |

Outcome: nine legacy lifecycle regressions and all 64 Rocket-tool tests passed;
the full integrated check passed 532 tests in 25.065 seconds. Assignment 47
reported ten of ten isolated repetitions of the synchronized signal fixture and
all 34 execution-engine tests passing. Bounded disposable local processes are
tooling evidence, not simulation results or a universal scheduling guarantee.

The preservation audit at `d114b6f0842c45e8e30664d2e6209ddb1ad60955` found all 57
root gitlink path/SHA pairs, nine Conda inputs, thirteen manifest-preserved blobs,
28 upstream Makefiles/`.mk` files, and 24 Scala configuration files unchanged.
Later changes still require their own integration check. Scoped privacy scans
found no publication blocker; they are limited safeguards, not authentication
of records or proof that arbitrary content contains no sensitive data.

### Wave 9 — fresh local checkout and final integration preparation

| No. | Assignment | Scope / contribution | State |
| ---: | --- | --- | --- |
| 49 | `w09_clean_checkout` | Reproduce the repository check in a fresh local clone and inspect the read-only plan | Completed; 532 tests passed at the checkpoint above |
| 50 | `w09_legacy_review` | Independently inspect scoped legacy cancellation, exit truthfulness, and cleanup | Completed; nine cancellation tests and all 64 Rocket tests passed |
| 51 | `w09_cli_contract` | Verify safe defaults, help/plan entry points, and exact workload declarations | Completed; four read-only targets and declared counts checked |
| 52 | `w09_package_scope` | Audit runtime imports, discovery, and lightweight Linux CI assumptions | Completed; 49 Python files checked against Python 3.10 grammar, 532 tests discovered |
| 53 | `w09_acceptance_review` | Check gate/test/evidence traceability and non-qualification claims | Completed; no blocking contradiction reported |
| 54 | `w09_review_ledger` | Prepare this factual roster, checkpoint summary, and pending-release record | Completed; final-wave and publication updates remain with integrator |

Assignment 50 reported no reproducible defect in its requested legacy lifecycle
scope at the checkpoint above. Its nine cancellation tests passed in 5.674
seconds; all 64 Rocket-tool tests passed in 7.724 seconds. Scoped handler
restoration, separate observed process status, and cleanup of same-group
descendants were reviewed. SIGKILL handling and signals outside the legacy
`run_stage` scope were not claimed supported.

Assignment 51 confirmed two configurations with fifteen workloads each, the
38-blocker profile, and 165-package plan. Assignment 52 also reported twelve CI
contract tests and nine test-runner tests passing. Parsing with an older grammar
is a static compatibility check, not execution under every Python version.
Assignment 53 found the gate/test/evidence states consistent. The integrator
reported no blocking defect from assignments 49–53 and retained the ignored-cache
observation and subsequent fixture correction rather than claiming a pristine
hardware reproduction.

### Wave 10 — final source/tooling publication review

| No. | Assignment | Review scope / result | State |
| ---: | --- | --- | --- |
| 55 | `w10_final_code` | Cross-module contracts; 43 targeted integration/record/workload tests passed | Completed |
| 56 | `w10_final_docs` | Documentation/CLI/evidence claims; validator and whitespace checks passed | Completed |
| 57 | `w10_ci_readiness` | Fresh local checkout; 532 tests passed with no ignored cache output | Completed |
| 58 | `w10_gate_consistency` | Gate/test state; 27 target-evidence and 54 comparator tests passed | Completed |
| 59 | `w10_final_integrity` | Preserved pins/inputs/notices and scoped tracked-content publication checks | Completed |
| 60 | `w10_release_review` | Sixty-entry roster, source/tooling scope, and non-forced publication plan | Completed |

## Final review closeout

All six final reviewers examined local commit
`30e1178eeddcc1fbc8a571b785b6ddd5d493b0bd`, Git tree
`f95bc537f4eda51efc81de2f49bd2f02017c068a`. They reported no blocking defect
within their bounded review scopes; this is not proof that every possible defect
is absent. The only subsequent integration edit at closeout is this ledger's
completion and evidence summary.

| Final local observation | Result |
| --- | --- |
| Integrator's pre-checkpoint full check | 532 tests passed in 24.050 seconds; repository/whitespace/diff checks passed |
| Assignment 57's fresh local clone | No hardlinks or initialized submodules; exact commit/tree above |
| Full command | `make -f nova.mk check`; exit 0 |
| Test result | 532 tests passed in 24.607 seconds |
| Full-command wall time | 25.208 seconds |
| Cleanliness before and after | Tracked, untracked, and ignored status all empty |
| Fixture cleanup | The earlier ignored bytecode output did not recur after the `-B` correction |
| Preserved foundation | All 57 gitlinks, nine Conda inputs, thirteen preserved blobs, 28 upstream Makefiles/`.mk` files, and 24 Scala configurations unchanged |
| Remote CI | Not asserted by this local record; inspect the run for the exact publication commit |

These are tooling checks on Python 3.12.14, not a supported-host matrix,
processor run, independent hardware build, or human acceptance decision.
No new hardware or reference-comparison result was produced in the final wave.

### Publication boundary

The integrating agent must rerun the integrated check after this ledger-only
closeout and verify the committed tree before publication. The publication
transaction is separate from these historical local observations: preserve the
existing history, compare the created GitHub tree with the tested local tree,
and use a non-forced expected-head update of `main`. Stop if the expected head
has changed or a protected workflow rejects the update.

Local checkpoint `a4228b3628949af92a6622a8f09710ce4828c2e0` and GitHub code
checkpoint `edf31943a299052258b56f575b4b26e06b939b43` share Git tree
`9a0746de6c89deea59938267da66ae34b3abc66e`; they are distinct commits, not
interchangeable revision identifiers. The final publication adds the reviewed
documentation and lifecycle fixes to that code checkpoint. Object creation
alone does not move a branch. Verify the final branch and its exact-SHA CI
separately; neither an earlier green run nor this ledger certifies remote CI.
This publishes source/tooling, not an accepted NOVA hardware release.

## Unclosed engineering work

- Provide and review a prepared, pin-preserving toolchain and source/runtime
  collateral under an approved host/resource/network/time/cost budget. The
  current strict profile reports 38 prerequisite blockers, not 38 CPU failures.
- Establish an independently observable target-originated exit. The current
  pinned HTIF/TestDriver completion protocol alone is insufficient; the concrete
  interruption behavior still requires a real prepared-simulator experiment.
- Execute all fifteen workloads separately for both declared configurations,
  retain authentic source/binary/artifact/log identities, and validate the actual
  positive and deliberate-failure output formats.
- Repeat the full hardware build and campaign independently, resolve the pinned
  reference-comparison scope, and obtain an accountable maintainer gate decision.

No hardware step in this list is represented as executed by this record. Follow
the [status](../STATUS.md), [baseline runbook](../BASELINE_RUNBOOK.md), and
[verification policy](../VERIFICATION.md) when completing or reviewing the next
stage. Automated review count is a work-accounting fact, not a quality score or
a substitute for hardware evidence.
