# G1 HTIF observer — implementation and 60-worker review ledger

**Record date: 2026-11-25. All 60 distinct workers completed their assigned
scopes.** The integrating agent reconciled their actual reports, including
worker 60's independent publication review, before closing this ledger.

The work implements optional observation of the actual pinned HTIF exit state,
bounded campaign integration, and retained-evidence checks. **G1 remains
blocked.** No Rocket/NOVA CPU, RISC-V instruction, Verilator/TestDriver, RTL,
FPGA, or silicon execution is established by these assignments. G0 remains
`in_progress`; G2–G9 remain `planned`. The
[master observer evidence](G1-HTIF-OBSERVER-2026-11-25.md),
[baseline runbook](../BASELINE_RUNBOOK.md), and [status](../STATUS.md) govern the
remaining hardware work. The [November 12 ledger](G1-60-AGENT-REVIEW-2026-11-12.md)
remains a separate historical record and is unchanged.

## Accounting and evidence boundary

Each started assignment is a distinct automated worker created with
`fork_turns=none`, with an explicit scope and a separate report. At most three
workers ran concurrently alongside the integrating agent. The table uses actual
assignment numbers and task names, sorted numerically; numbers 53 and 56 were
started later than their numeric neighbors. The integrating agent is separate
from the sixty-worker target.

`Complete` means the assigned implementation, experiment, documentation, or
review scope was reported complete. It does not mean every worker wrote code,
reran a suite, independently authenticated execution, or accepted a gate.
Review scopes and focused tests overlap. Their counts must not be added to
the integrated suite or native-case totals. These are automated assignments,
not sixty human reviewers or sixty independent hardware qualifications.

| Evidence | Recorded observation and limit |
| --- | --- |
| Source-complete publication | `0e4711713ca82da8d55ee03f742a91d6f5db116e`; byte-identical to local `52161a0b395f0644d693c132433ea9246deab712`, tree `609d280a87e6b14d1c01c934d74f8fe51a9a8f3e`. Later evidence/ledger edits are separate. |
| Repository checkpoint 05 | Fresh-checkout `make -f nova.mk check`: **836 tests passed in 40.355 seconds**, plus metadata and whitespace checks. Repository tooling evidence only. |
| Final actual native replay, worker 50 | One delivered CLI invocation; 19 build/inspection commands and **12 native cases** in 6.281061 seconds. Real pinned HTIF/FESVR, synthetic host memory/configuration; no target CPU execution. Six expected code-seven commands retain actual failed engine status and exit 7. |
| Synthetic integration, worker 51 | Two relocated synthetic producer bundles passed actual verifier CLIs, each checking 106 evidence files, 30 protocols and 30 witnesses; actual comparator returned `consistent`. A coherent raw-signal corruption failed bundle verification while record-only comparison remained `consistent`, as specified. No real campaign or independent hardware build occurred. |
| Exact source-commit CI | Integrator observed [run 45706964047](https://github.com/baabi-boo/CPU/actions/runs/45706964047) pass for `0e4711713ca82da8d55ee03f742a91d6f5db116e` at 21:50 UTC. This does not assert later documentation-commit CI. |
| Preservation | Worker 52 verified all **57 gitlinks**, **nine Conda inputs**, and 13 required preserved blobs unchanged; no upstream implementation or RTL edit in its audited change set. |
| Final checkout review, worker 56 | Local `a5ebc3515138e358de9f43e352b32b8c87669a1f`, tree `c24e3fc83bbe994c387347effc3b505718e14505`: one check, **836 passed, zero skips/failures/errors**, in 37.508 seconds (38.346745 seconds whole command). Clean before/after; all 110 retained evidence files present and all 108 manifest-listed payloads hash-checked. Published byte-identical commit [f8c428195da4d64cea8d3736e9eaa5e7903d0301](https://github.com/baabi-boo/CPU/commit/f8c428195da4d64cea8d3736e9eaa5e7903d0301) was independently verified by worker 60. |
| Publication review, worker 60 | GitHub GET-only inspection confirmed published `main` at `f8c42819`, its exact tested tree, unchanged source since `0e471171`, the source-commit CI success, all 110 retained native files and 108 payload hashes, and the 60-entry assignment registry. No blocking publication or handoff issue found. |
| Reviewed publication CI | Integrator observed [run 45709224803](https://github.com/baabi-boo/CPU/actions/runs/45709224803) return `completed / success` for `f8c428195da4d64cea8d3736e9eaa5e7903d0301`. This exact-commit result is separate from the source checkpoint and the later ledger closeout. |
| Hardware state | Strict profile has 38 reported prerequisite blockers. Real two-configuration campaigns, second independent clean hardware build, reference comparison, and maintainer acceptance remain outstanding. |

The master record identifies checkpoint revisions and retains the actual CI
failure and fortify repair. Earlier 752-, 801-, and 822-test checkpoints retain
their original identities. The latest native
[results](htif-native-final-2026-11-25/results.json),
[independent verification](htif-native-final-2026-11-25/verification.json), and
[retention manifest](htif-native-final-2026-11-25/retention-manifest.json) describe
55 selected files, 309,321 bytes, and explicit omissions. This compact selection
is not a complete replay bundle or a guarantee that omitted temporary files
remain available.

Worker 56's [complete unchanged check log](checkpoints/FINAL-CHECK-2026-11-25.log)
is 135,657 bytes and 852 lines, SHA256
`004b549e1076fabb3ca41674db6894c54c824d0419e63c3e8d793e8969492aed`.
Its fresh detached working tree and index shared local Git objects with the
source repository; no dependencies were downloaded or initialized. Its 29
native recorder fixtures are included within the 836 tests. It did not repeat
worker 50's twelve-case pinned replay. Only documentation differed from the
published source commit; the subsequent ledger itself is outside that tested
tree.

## Actual assignment roster

Rows summarize substantive contributions and findings. Follow-up repairs are
identified separately from the workers who found the defects.

| No. | Actual task | State | Contribution / reviewed result |
| ---: | --- | --- | --- |
| 01 | `a01_exit_design` | Complete | Audited exact pinned APIs and both exit routes; designed the hash-checked stop overlay and static-link approach. |
| 02 | `a02_campaign_audit` | Complete | Reproduced lost finish-time cancellation and accepted positive crash wording; defined runner integration constraints. |
| 03 | `a03_evidence_audit` | Complete | Demonstrated seven comparator consistency gaps; specified observer identity, binding, and freshness requirements. |
| 04 | `a04_native_observer` | Complete | Implemented one-shot native recorder, exclusive witness creation, and host fault fixtures. |
| 05 | `a05_overlay_generator` | Complete | Implemented deterministic exact-pin overlay, manifest validation, static Make adapter, and relocation/quoting checks. |
| 06 | `a06_cancellation_fix` | Complete | Repaired execution-engine cancellation during final timestamps and handler restoration; retained actual child exits. |
| 07 | `a07_exit_parser` | Complete | Implemented bounded strict witness parser with identity, type, raw-code, signal, and safe-file checks. |
| 08 | `a08_pinned_htif_native` | Complete | Ran twelve actual pinned native original/observed cases; reproduced signal-only false success and observer rejection. |
| 09 | `a09_protocol_fix` | Complete | Accepted only the reviewed pinned code-seven diagnostic; rejected contradictory positive segmentation-fault text. |
| 10 | `a10_observed_plan` | Complete | Added opt-in schema-2 plan and `g1-observed-plan`; preserved the default schema-1 plan. |
| 11 | `a11_runner_observer` | Complete | Integrated bound per-workload witnesses, nonce uniqueness, observer rechecks, and process-failure precedence. |
| 12 | `a12_comparator_contract` | Complete | Repaired seven legacy record-consistency areas, strict types, source digests, and structurally valid synthetic fixtures. |
| 13 | `a13_observed_record_contract` | Complete | Added pure schema-2 extension validation and stable semantic projection across all thirty workload rows. |
| 14 | `a14_native_probe_cli` | Complete | Built reusable bounded native CLI; ran twelve real pinned cases with retained commands and link evidence. |
| 15 | `a15_compare_observed` | Complete | Integrated schema-2 comparison, source/build bindings, cross-record nonce disjointness, and downgrade rejection. |
| 16 | `a16_verify_bundle` | Complete | Implemented read-only raw-bundle verification with bounded anchored capture and protocol/witness reassessment. |
| 17 | `a17_runner_review` | Complete | Reproduced outer late cancellation, serialization deadline, and first-mismatch witness-finalization gaps. |
| 18 | `a18_make_review` | Complete | Checked actual upstream Make parsing, quoting/header closure and native archive order; exposed unqualified standalone reuse. |
| 19 | `a19_campaign_finalization_fix` | Complete | Repaired outer cancellation/persistence, deadline reconciliation, and all-witness drift invalidation. |
| 20 | `a20_ci_whitespace` | Complete | Required preinstalled native compiler in bounded CI; added managed observer-source whitespace coverage and documentation. |
| 21 | `a21_bundle_review` | Complete | Fixed bare-CR parser-budget bypass and unsafe record pathname reread; preserved anchored captured-byte parsing. |
| 22 | `a22_current_status_docs` | Complete | Updated current status/backlog/project evidence without promoting blocked hardware or gate states. |
| 23 | `a23_runbook_docs` | Complete | Documented observed/native commands, fresh products, raw verification before comparison, and exact CLI forms. |
| 24 | `a24_observer_evidence` | Complete | Authored master evidence and first 55-file native selection; checked copied bytes, excerpts, links, and preservation. |
| 25 | `a25_record_reader_fix` | Complete | Confined standalone record reads through no-follow descriptors; covered parent swaps, bounds, and cleanup. |
| 26 | `a26_architecture_audit` | Complete | Confirmed thin unverified CPU aliases and every-hart limits; prioritized G1 and identified documentation discoverability gaps. |
| 27 | `a27_native_fortify_fix` | Complete | Reproduced actual CI fortified-libc compilation failure and repaired it while retaining warnings as errors. |
| 28 | `a28_doc_index_verification` | Complete | Updated documentation index and verification policy for observed plans, raw bundles, and scoped completion claims. |
| 29 | `a29_native_recorder_review` | Complete | Reproduced foreign-file deletion during cleanup and fatal termination blocked by a full stderr pipe. |
| 30 | `a30_exit_parser_review` | Complete | Demonstrated descriptor leaks/retry hazards after close errors; found no wire acceptance bypass in reviewed paths. |
| 31 | `a31_observer_generator_review` | Complete | Proved impossible one-byte manifest metadata was accepted; reviewed source stability and bounded generator behavior. |
| 32 | `a32_recorder_failure_fix` | Complete | Replaced pathname unlink with owned-descriptor invalidation; bounded nonblocking fatal reporting and preserved foreign files. |
| 33 | `a33_parser_cleanup_fix` | Complete | Repaired close-error ownership transfer, independent cleanup, and descriptor-reuse safety with real-descriptor fault regressions. |
| 34 | `a34_manifest_size_fix` | Complete | Enforced complete-manifest minimum byte size without filesystem reads or false raw-hash reconstruction. |
| 35 | `a35_target_abi_audit` | Complete | Reviewed RV64 target/HTIF ABI, exact 15-workload contract, negative grammar, and ISA/hart scope; no new defect. |
| 36 | `a36_native_probe_limits` | Complete | Reproduced capture/terminal-write deadline gaps and swallowed late SIGTERM in native probe finalization. |
| 37 | `a37_schema_boundary_review` | Complete | Reviewed strict claim paths, complete bindings, nonce uniqueness, and semantic projection; no new concrete defect. |
| 38 | `a38_environment_review` | Complete | Proved inherited `ASPECTS`, `ASPECT_ARGS`, and recursive `MAKE` could alter fixed builds. |
| 39 | `a39_native_finalization_fix` | Complete | Added streaming traversal limits, cooperative chunk checks, exclusive terminal persistence, and late-stop reconciliation. |
| 40 | `a40_make_override_fix` | Complete | Rejected the three inherited Make/aspect overrides, including empty values, before probes or commands. |
| 41 | `a41_bootstrap_nextstep_audit` | Complete | Found broad lean setup conflicts: lock rewriting, all optional generators, and extra-stage Gemmini initialization. |
| 42 | `a42_selective_setup_docs` | Complete | Corrected bootstrap guidance; made the missing selective preparation procedure and fixed-profile constraints explicit. |
| 43 | `a43_readonly_plan_review` | Complete | Reproduced cold-cache writes in three bare Python CLIs; checked safe defaults and unchanged legacy plan. |
| 44 | `a44_readonly_cli_fix` | Complete | Suppressed sibling import caches before imports; isolated replay preserved stdout/exits and created no files. |
| 45 | `a45_native_fix_review` | Complete | Independently reviewed settled native finalization repair and boundary tests; no new confirmed issue. |
| 46 | `a46_cross_checkout_audit` | Complete | Confirmed exact artifact hashes survive relocation; documented path-sensitive binary differences and independent-build limits. |
| 47 | `a47_artifact_binding_audit` | Complete | Reviewed ELF structure, source-state capture, observer inputs, and before/after binary binding; no new finding. |
| 48 | `a48_retained_evidence_audit` | Complete | Independently checked all 55 historical retained files, hashes, excerpts, source identities, and checkpoint mappings. |
| 49 | `a49_final_claims_docs` | Complete | Integrated current failure/finalization/override semantics and reproduction limits while preserving historical native identities. |
| 50 | `a50_final_native_replay` | Complete | Executed frozen final-code twelve-case native replay; rehashed 152 artifacts, 62 logs, 24 inputs, and six witnesses. |
| 51 | `a51_bundle_flow_review` | Complete | Exercised relocated synthetic producer-to-verifier-to-comparator CLIs and one coherent raw-witness corruption control. |
| 52 | `a52_preservation_audit` | Complete | Verified pins, Conda inputs, licenses/preserved blobs, unchanged RTL/upstream implementation, and allowed change scope. |
| 53 | `a53_final_native_evidence` | Complete | Retained latest 55-file selection byte for byte; integrated final-code hashes, 836-test checkpoint, and exact CI observation. |
| 54 | `a54_operator_handoff_review` | Complete | Checked documented command forms, status mappings, fresh-output requirements, and selective preparation handoff; no blocking defect. |
| 55 | `a55_integrated_change_review` | Complete | Reviewed cross-component state observation, binding, process authority, consumers, and claims; no new material defect. |
| 56 | `a56_final_checkout_check` | Complete | Ran exact frozen fresh-checkout check: 836 passed, zero skips/errors/failures; verified all 110 retained evidence files. |
| 57 | `a57_next_step_spec` | Complete | Specified selective fixed-G1 preparation interfaces, stage/input/write boundaries, negative controls, and actual-execution acceptance. |
| 58 | `a58_traceability_review` | Complete | Checked stable final-native page, evidence levels, gate/test references, failure semantics, and links; no concrete contradiction. |
| 59 | `a59_review_ledger` | Complete | Reconciled actual assignment reports into this ledger; separated evidence levels, reported checkpoints, and integrator closeout. |
| 60 | `a60_publication_review` | Complete | Independently verified published ref/tree equality, exact source CI, 110 retained native files and 108 payload hashes, ledger assignments, and operator handoff; no blocking issue. |

## Material fixes and source traceability

| Audit-to-fix group | Current implementation and focused evidence |
| --- | --- |
| Actual exit observation: 01, 04–05, 07–08, 14, 18, 50 | [Overlay generator](../../../scripts/nova/htif_observer.py), [Make adapter](../../../software/nova/observer/observer.mk), [native probe](../../../scripts/nova/htif_host_probe.py), [generator tests](../../../tests/nova/test_htif_observer.py), and the retained latest native results above. |
| Cancellation/finalization: 02→06, 17→19, 36→39; review 45 | [Execution engine](../../../scripts/nova/campaign_exec.py), [campaign](../../../scripts/nova/g1_campaign.py), [late-cancellation regressions](../../../tests/nova/test_campaign_exit_cancellation.py), [campaign finalization regressions](../../../tests/nova/test_g1_campaign_observer.py), [native CLI regressions](../../../tests/nova/test_htif_host_probe.py). |
| Recorder/parser safety: 27, 29→32, 30→33 | [Native recorder](../../../software/nova/observer/nova_htif_exit.cc), [witness parser](../../../scripts/nova/htif_exit_evidence.py), [native fault fixtures](../../../tests/nova/test_htif_native.py), [parser cleanup regressions](../../../tests/nova/test_htif_exit_evidence.py). Status 125 remains authoritative even if bytes survive. |
| Strict supplied-record consistency: 03→12, 13, 15, 31→34 | [Comparator](../../../scripts/nova/compare_campaigns.py), [observed contract](../../../scripts/nova/observed_record.py), [consistency regressions](../../../tests/nova/test_comparator_consistency.py), [schema-2 integration tests](../../../tests/nova/test_compare_observed_campaigns.py). |
| Retained-byte confinement: 16, 21, 25, 51 | [Bundle verifier](../../../scripts/nova/verify_campaign_bundle.py), [bundle regressions](../../../tests/nova/test_verify_campaign_bundle.py), [record-reader regressions](../../../tests/nova/test_record_reader_paths.py). Raw verification precedes comparison; neither authenticates execution. |
| Protocol/environment/defaults: 09, 20, 38→40, 43→44 | [Protocol regressions](../../../tests/nova/test_protocol_source_regressions.py), [campaign tests](../../../tests/nova/test_g1_campaign.py), [CI contract](../../../tests/nova/test_ci_contract.py). Exact negative diagnostics, inherited-build rejection, and read-only CLI behavior retain their scoped meanings. |

## Integrating agent and publication closeout

The integrating agent owns shared-contract decisions, cross-file fixture
integration, aggregate checks, Git staging/commits, publication, and remote CI
observation. It preserved original native bytes, explicitly retained selected
ignored logs, checked local/published tree equality, and used non-forced
expected-head publication. Those activities are not an extra worker or an
independent human review.

The source checkpoint and reviewed documentation commit above are published,
with separate observed CI successes. Worker 60 completed its review without a
blocking finding. All sixty assignment reports are complete and reconciled.
The containing commit publishes this completed ledger, the unchanged final
check log, and documentation links as a separate documentation-only closeout.
Its identity is available in this file's Git history; the delivery summary
reports the final published revision and its separately observed CI outcome.
Neither earlier CI result is transferred to that later commit. Worker 59, the
ledger author, ran no suite, native build, network operation, or publication.

## Next engineering step

Workers 26, 35, 41, 42, and 57 converge on **NOVA-001: implement and validate
selective, pin-preserving environment preparation**, as specified in the
[backlog](../BACKLOG.md) and [development guide](../DEVELOPMENT.md). The broad
lean setup is not that procedure: its stages can regenerate locks, initialize
all fourteen optional generators, and initialize Gemmini through extra-toolchain
work. A suitable procedure must preserve the 57 pins and nine Conda inputs,
the fixed Chisel-6 profile and zero optional generators; establish exact source
and nested/JVM closure, unchanged-lock installation, supplementary tools,
HTIF/FESVR/runtime/ISA collateral, activation provenance, and effective bounds.
The read-only specification is preparation for implementation, not an executed
installation recipe or proof of compatibility.

After actual environment validation, run all fifteen declared workloads on each
single-core configuration using fresh observed builds; retain real positive,
negative, and interruption evidence and generated-hardware identities. Repeat
the full campaign in a second independent clean build, verify both raw bundles,
compare records, resolve the pinned-reference scope, and obtain the maintainer's
gate decision. The native and repository results here do not satisfy
`T-BUILD-001` or `T-ISA-001` or authorize expansion to a qualified mixed-core SoC.
