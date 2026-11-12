# G1 completion protocol — source-confirmed limitation

**This is a source-level review, not a reproduced CPU/simulator result.** No
Rocket or NOVA target was executed for this record. It explains why the current
log grammar cannot independently verify a target-originated exit, even when the
expected simulator completion record is present.

## Identity and scope

| Field | Observation |
| --- | --- |
| Record date and author role | 2026-11-12; automated source review, assignment 42 |
| Reviewed NOVA code checkpoint | `a4228b3628949af92a6622a8f09710ce4828c2e0` |
| Reviewed checkpoint tree | `9a0746de6c89deea59938267da66ae34b3abc66e` |
| Requirements and tests affected | `REQ-CPU-001`, `T-ISA-001`; completion evidence used by the G1 baseline campaign |
| Configuration scope | The pinned SimTSI/HTIF success path used by the proposed Rocket and named NOVA baseline campaign |
| Evidence level | Source inspection and logical inference from the connected termination path |
| Outcome | Limitation confirmed in source; corresponding real-simulator experiment `not_run` |
| Gate decision | None; this record grants no G0/G1 acceptance or hardware qualification |

The checkpoint identifies the inspected implementation, not a claim that this
documentation file existed in that tree or that the checkpoint had passed remote
CI. Other documentation was being integrated concurrently. The dependency pins
below were not changed, and no upstream source patch was applied.

## Pinned primary sources

The source inspection used these exact revisions and files:

- Spike `9c190a07c6838f6392bafa4ad83acea462c7f759`:
  [HTIF implementation](https://github.com/riscv-software-src/riscv-isa-sim/blob/9c190a07c6838f6392bafa4ad83acea462c7f759/fesvr/htif.cc),
  [TSI implementation](https://github.com/riscv-software-src/riscv-isa-sim/blob/9c190a07c6838f6392bafa4ad83acea462c7f759/fesvr/tsi.cc),
  and [TSI inheritance](https://github.com/riscv-software-src/riscv-isa-sim/blob/9c190a07c6838f6392bafa4ad83acea462c7f759/fesvr/tsi.h).
- Testchipip `555ff3fbc12f81a8feff7a4801930fb384ddd2ae`:
  [testchip TSI inheritance](https://github.com/ucb-bar/testchipip/blob/555ff3fbc12f81a8feff7a4801930fb384ddd2ae/src/main/resources/testchipip/csrc/testchip_tsi.h),
  [SimTSI C++ bridge](https://github.com/ucb-bar/testchipip/blob/555ff3fbc12f81a8feff7a4801930fb384ddd2ae/src/main/resources/testchipip/csrc/SimTSI.cc),
  and [Scala success decoding](https://github.com/ucb-bar/testchipip/blob/555ff3fbc12f81a8feff7a4801930fb384ddd2ae/src/main/scala/tsi/SimTSI.scala).
- Rocket Chip `ece7b9ad544b07df39cd13b6fd7236562a26355d`:
  [TestDriver](https://github.com/chipsalliance/rocket-chip/blob/ece7b9ad544b07df39cd13b6fd7236562a26355d/src/main/resources/vsrc/TestDriver.v).
- The local [HarnessBinders](../../../generators/chipyard/src/main/scala/harness/HarnessBinders.scala)
  at the reviewed NOVA checkpoint connects SimTSI success to `chiptopSuccess`.

The selected pins remain recorded in
[`nova/upstream-lock.json`](../../../nova/upstream-lock.json). Read-only source
retrieval and inspection are not dependency initialization or simulator builds.

## Connected termination path

| Stage | Source observation | Consequence |
| --- | --- | --- |
| HTIF signal handling | The constructor installs handlers for SIGINT/SIGTERM; a first handled signal can set `signal_exit` | Shutdown can be requested without setting a target exit value |
| HTIF run loop | `should_exit()` accepts either the signal flag or an available exit value; leaving the loop calls `stop()` | The run loop can stop for either cause |
| HTIF completion query | `stop()` sets `stopped`; `done()` returns that state; `exit_code()` defaults an absent exit value to zero before decoding it | Signal-only shutdown can appear done with decoded exit code zero |
| TSI connection | `testchip_tsi_t` inherits `tsi_t`; `tsi_t` inherits HTIF and its host coroutine calls `run()` | The bridge retains that HTIF completion behavior |
| SimTSI bridge | A done result is encoded from the exit code with the low bit set; Scala treats encoded value one as success | The signal-only zero case maps to the success value |
| Harness and TestDriver | The harness forwards success; TestDriver's verbose success branch prints its completion record and requests finish | The same printed protocol can be reached without an independently observed target exit |

This conclusion is conditional: HTIF must receive the signal and its coroutine
must advance to the termination check. It is **not** a claim that every
interruption takes this path. SIGKILL cannot invoke that handler; repeated
signals and SIGABRT have other handling. No timing window, cycle count, frequency,
or real host exit status was measured here.

The logical finding is that the supplied TestDriver completion grammar does not
encode whether HTIF actually received a target terminal event. Requiring a
reported process exit of zero and an exact target output line is useful checking,
but does not add that missing exit-cause observation.

## Consequences for implemented tooling

[`target_evidence.py`](../../../scripts/nova/target_evidence.py) and
[`workload_assessment.py`](../../../scripts/nova/workload_assessment.py) describe
their result as observed protocol only. A positive match may set
`completion_protocol_observed: true`; `target_completion_verified` remains
false. Hardware and G1 qualification also remain false. Conflicting terminal
records, malformed or changed logs, nonzero positive process exits, and explicit
failure/timeout indicators are rejected.

The expected negative-control path is separate: its exact target marker and
SimTSI code-7 assertion must agree with a supported nonzero process result. This
specific signal-only zero-success ambiguity does not produce code seven. That
does not independently authenticate the supplied logs, and the real generated
assertion/trailer formatting still needs validation on the pinned simulator.

[`campaign_exec.py`](../../../scripts/nova/campaign_exec.py) and
[`g1_campaign.py`](../../../scripts/nova/g1_campaign.py) retain their own
interruption/timeout/resource-failure observations and cannot accept such a stage
merely because PASS text later appears. Scoped runner SIGINT/SIGTERM cleanup is
covered by bounded local process fixtures. Those tests are not the real HTIF
experiment, and runner cancellation handling does not identify an external
signal swallowed solely inside the simulator.

[`compare_campaigns.py`](../../../scripts/nova/compare_campaigns.py) rejects
unsupported target-completion or hardware claims. Its `consistent` result checks
agreement of unauthenticated record identities, not independent execution or
reproduction. Repeating the ambiguous protocol in two records does not remove
the ambiguity.

## Work still required before target-completion qualification

On a separately approved, prepared, pinned simulation host:

1. Design and review a target-terminal-event observation that distinguishes an
   actual target-originated HTIF exit from host signal shutdown. Record its
   implementation and exact source/configuration identity; do not silently
   replace upstream pins or infer the event from a printed line.
2. Bind that observation to the retained target ELF, simulator, workload, source,
   limits, and separate immutable logs. Define positive and expected-failure
   behavior before execution.
3. Run the real positive and deliberate code-7 workloads and bounded interruption
   controls. Show that interrupted/no-target-exit cases cannot acquire verified
   target completion, while the expected target terminal event is observable.
4. Repeat the declared campaign for both configurations and a second independent
   clean build. Resolve the supported pinned-reference comparison scope,
   document exclusions, and obtain the maintainer's evidence-based gate decision.

These are pending engineering tasks, not a supplied adapter, approved resource
budget, simulation result, or human signoff. G1 remains blocked as summarized in
the [preparation record](G1-PREPARATION-2026-11-12.md) and
[current status](../STATUS.md). Follow the [baseline runbook](../BASELINE_RUNBOOK.md)
and [verification policy](../VERIFICATION.md); this source review does not replace
their unrun hardware evidence.
