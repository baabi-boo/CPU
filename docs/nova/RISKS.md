# Engineering risk register

These are initial qualitative assessments, not measured probabilities. All risks
below are **open**. Likelihood and impact use low/medium/high; they are not combined
into a pseudo-precise score. Owner entries identify responsibilities, not staffed
positions: every listed role is currently **unassigned**.

Review this register at gate entry/exit and after changes to architecture,
dependencies, tools, target hardware, or resource assumptions. The maintainer must
assign a responsible person before accepting a risk-bearing integration task.
See [GOVERNANCE](GOVERNANCE.md), [ROADMAP](ROADMAP.md), and [STATUS](STATUS.md).

## Active risks

| ID | Risk and consequence | Likelihood / impact | Mitigation and required evidence | Owner role | Escalation trigger |
| --- | --- | --- | --- | --- | --- |
| R01 | Toolchain, memory, disk, or runtime needs prevent reproducible builds | High / high | Use pinned locks, explicit resource budgets, preflight, bounded jobs, and two clean baseline builds (`T-BUILD-001`) | Build maintainer — unassigned | Missing prerequisite, out-of-memory event, unexplained build difference, or budget overrun |
| R02 | Inherited CI, unsafe logs, or unreviewed actions expose secrets or spend resources | Medium / high | Read-only lightweight CI; pinned actions; upstream job guards; sanitized allowlisted diagnostics; explicit approval for heavy jobs (`T-REPO-001`) | CI/security maintainer — unassigned | New permissions, external action, self-hosted runner, publication step, or sensitive log field |
| R03 | Dependency drift, restricted IP, or lost notices make results irreproducible or undistributable | Medium / high | Preserve gitlinks/notices; review nested dependencies, licenses, provenance, and old/new regression evidence (`T-REPO-001`, `T-RELEASE-001`) | Dependency maintainer — unassigned | Pin, source URL, license, PDK, macro, or distribution-scope change |
| R04 | Hart-0-only coverage or incompatible hart features create false multicore confidence | High / high | Verify generated hart inventory, common software profile, per-hart execution, reset and interrupts; replace four-hart assumptions (`T-HART-001`, `T-ISA-001`, `T-RESET-001`) | CPU verification lead — unassigned | Missing participant, illegal instruction after migration, or new core configuration |
| R05 | Coherence, atomics, ordering, or reset interaction causes corruption or deadlock | Medium / high | Dirty-line/eviction stress, litmus tests, LR/SC contention, fault traces, and bounded progress (`T-COH-001`, `T-ORDER-001`) | Memory verification lead — unassigned | Forbidden outcome, unexplained timeout, cache/topology change, or memory-model mismatch |
| R06 | Accelerator DMA has stale buffers, unsafe lifetime, or unauthorized access | High / high | Define coherence mode, ownership, cache maintenance, address bounds, completion, translation, and recovery; test dirty buffers and hostile descriptors (`T-DMA-001`, `T-ISOLATION-001`) | Accelerator integration lead — unassigned | New bus master, shared buffer, IOMMU claim, or intermittent transfer result |
| R07 | GPU hardware works alone but driver/runtime/graphics integration is infeasible | High / high | Select a pinned candidate through an ADR; demonstrate integrated compute first; qualify graphics/API scope separately (`T-GPU-EXEC-001`) | GPU integration lead — unassigned | Unsupported runtime feature, resource overflow, integration-only failure, or missed acceptance boundary |
| R08 | NPU quantization, overflow, or transfer costs invalidate correctness or speed claims | Medium / high | Software references, declared tolerances, boundary/random cases, setup/transfer accounting, and fallback comparisons (`T-NPU-NUM-001`, `T-NPU-MEM-001`) | Accelerator verification lead — unassigned | Numerical mismatch, dtype/layout change, or kernel-only claim presented as end-to-end speedup |
| R09 | FPGA capacity or physical DDR/LPDDR controller/PHY access blocks real hardware | High / high | Select an affordable authorized target only after capacity estimates; validate IP rights, constraints, calibration, and memory integrity; name reduced profiles (`T-FPGA-001`, `T-PHY-001`) | Platform hardware lead — unassigned | Insufficient resources/timing, unavailable PHY/IP views, failed training, or procurement request |
| R10 | Power models or nominal clocks are mistaken for achieved efficiency | High / high | Separate simulation activity, FPGA measurements, ASIC estimates, and silicon results; matched workload/rail/temperature boundaries (`T-POWER-001`) | Power implementation lead — unassigned | P/E label, performance-per-watt claim, power-state change, or changed estimation assumptions |
| R11 | Debug, boot, firmware, or DMA trust boundaries are marketed as secure without tests | Medium / high | Publish threat model and absent protections; test each advertised boundary; use confidential reporting for vulnerabilities (`T-ISOLATION-001`) | Security verification lead — unassigned | New protection claim, external exposure, untrusted workload, or vulnerability report |
| R12 | ASIC tools, foundry/IP access, budget, packaging, test, or signoff ownership are missing | High / high | Separate feasibility from tapeout; maintain gap list, named reviewers, authorized costs, and fabrication decision (`T-ASIC-001`, `T-AUTH-001`) | Physical implementation lead / project maintainer — unassigned | Proposed tapeout, inaccessible technology asset, unconstrained path, signoff gap, or spending commitment |

## Response and closure

For an escalation, create a scoped issue referencing the risk ID, affected
requirements, observed evidence, immediate containment, decision owner, and next
review trigger. Record whether work continues as bounded research or stops at an
integration gate. A risk acceptance does not convert an unrun test into a pass.

Close or downgrade a risk only with linked evidence and a reviewed rationale.
Keep the original assessment and decision history; reopen it when assumptions
change. Invalidate affected gate evidence rather than carrying old passes across
new sources, memory models, boards, or technologies.

Source identity, sanitized artifacts, and dependency-migration records follow
[REPRODUCIBILITY](REPRODUCIBILITY.md). Performance investigations follow
[BENCHMARKS](BENCHMARKS.md); security reports follow [SECURITY](../../SECURITY.md).
