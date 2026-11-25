# G1 HTIF observer — source, implementation, and native evidence

**G1 remains blocked.** The optional target-exit observer is implemented and
the signal-only completion ambiguity is reproduced with real pinned HTIF/FESVR
code on a native host. No Rocket/NOVA CPU, RISC-V instruction, Verilator,
TestDriver, RTL, FPGA, or silicon execution is established by this record.

| Field | Evidence state |
| --- | --- |
| Record date | 2026-11-25 |
| Requirement scope | `REQ-CPU-001`, `T-BUILD-001`, and `T-ISA-001` preparation; no hardware test acceptance |
| Original Spike pin | `9c190a07c6838f6392bafa4ad83acea462c7f759` |
| Native experiment 08 | Six modes in original and observed builds: twelve bounded native processes passed |
| Native experiment 14 | Reusable CLI: nineteen build/inspection commands and twelve bounded native processes passed |
| Make/native experiment 18 | Actual copied upstream Makefiles parsed; quoting, header closure, static archive order, and one native `direct0` case checked |
| First committed observer integration | Fresh-checkout repository-only check: 752 tests passed; later integration results must be recorded separately |
| Subsequent committed checkpoint | Fresh-checkout repository-only check: 801 tests passed; this is a checkpoint, not the final evolving suite total |
| Hardware environment | Strict G1 profile blocked with 38 reported blockers; hardware campaign not run |
| Foundation preservation | Fifty-seven gitlink pins and nine imported Conda inputs unchanged |
| Gate decision | None; hardware and G1 qualification remain false |

This record extends the earlier
[source-level completion finding](G1-COMPLETION-PROTOCOL-2026-11-12.md).
The [baseline runbook](../BASELINE_RUNBOOK.md), [status](../STATUS.md), and
[verification policy](../VERIFICATION.md) retain the remaining campaign and
maintainer acceptance requirements.

## Exact source audit

The observer is tied to the existing Spike gitlink, not a newer upstream API.
Its [source manifest](htif-native-2026-11-25/source-manifest.json) records the
exact pinned URLs, byte counts, and SHA256 values for all 24 native build inputs:
seven FESVR translation units, sixteen headers, and the original license.
The primary sources establishing the terminal-state behavior are:

| Pinned primary source | Finding and consequence |
| --- | --- |
| [Spike HTIF declaration](https://github.com/riscv-software-src/riscv-isa-sim/blob/9c190a07c6838f6392bafa4ad83acea462c7f759/fesvr/htif.h) | The exit value is a private `std::optional<int>`. `done()` and `exit_code()` are nonvirtual; there is no public exit-presence accessor. Overriding a similarly named method does not recover that information. |
| [Spike HTIF implementation](https://github.com/riscv-software-src/riscv-isa-sim/blob/9c190a07c6838f6392bafa4ad83acea462c7f759/fesvr/htif.cc) | A handled SIGINT/SIGTERM can set `signal_exit` without setting the optional. `should_exit()` accepts either cause; `run()` calls `stop()`; `stop()` sets `stopped`. `exit_code()` defaults an absent value to zero before shifting, so `done=true` and decoded zero do not establish a target exit. |
| [Spike syscall implementation](https://github.com/riscv-software-src/riscv-isa-sim/blob/9c190a07c6838f6392bafa4ad83acea462c7f759/fesvr/syscall.cc) | An odd direct tohost payload assigns the private optional through friendship and bypasses `htif_exit()`. Proxy syscall 93 separately calls `htif_exit(code << 1 \| 1)`. Observing only that function misses the direct route. |
| [libgloss target exit](https://github.com/ucb-bar/libgloss-htif/blob/177ce07db657bd674286d4aa06443166d33135e5/sys/exit.c) | The pinned target `_exit(code)` repeatedly writes the encoded direct tohost payload. The planned negative control therefore follows the direct raw-15 route for target code seven. |

The downstream connection remains a **source inference**: pinned
[TSI](https://github.com/riscv-software-src/riscv-isa-sim/blob/9c190a07c6838f6392bafa4ad83acea462c7f759/fesvr/tsi.cc)
calls HTIF `run()`;
[testchip TSI](https://github.com/ucb-bar/testchipip/blob/555ff3fbc12f81a8feff7a4801930fb384ddd2ae/src/main/resources/testchipip/csrc/testchip_tsi.h)
inherits that implementation;
[SimTSI C++](https://github.com/ucb-bar/testchipip/blob/555ff3fbc12f81a8feff7a4801930fb384ddd2ae/src/main/resources/testchipip/csrc/SimTSI.cc)
encodes a done result from the decoded exit code; and
[SimTSI Scala](https://github.com/ucb-bar/testchipip/blob/555ff3fbc12f81a8feff7a4801930fb384ddd2ae/src/main/scala/tsi/SimTSI.scala)
treats encoded one as success. The harness forwards that success to the pinned
[Rocket TestDriver](https://github.com/chipsalliance/rocket-chip/blob/ece7b9ad544b07df39cd13b6fd7236562a26355d/src/main/resources/vsrc/TestDriver.v).
No experiment here executed those bridges or TestDriver. The earlier
[completion finding](G1-COMPLETION-PROTOCOL-2026-11-12.md) records the connected
source path and its conditional nature.

### Frozen transform and native input identity

The generator verifies the original source hash before exactly three edits:
rewrite the source-relative `common.h` include for the recorded include search
path, include the NOVA recorder header, and add the callback immediately after
`stopped = true` inside `htif_t::stop()`. The callback reads the real optional
presence, raw exit value, and separate signal flag from their original scope.
It does not replace the upstream signal handler or alter normal HTIF decoding.
The complete generated translation unit must match the frozen output hash.
The original submodule source is never edited.

| Executed input or output | SHA256 |
| --- | --- |
| Original pinned `fesvr/htif.cc` | `c669e8352c6e21d61118849b0b969d291b84100e83343659f3d08979ae89a11d` |
| Generated complete HTIF overlay | `1a6383e8d9b7bfc4d44c2e674fafe1d8067d826c3c2cd0dae7e20a27e08aef84` |
| `software/nova/observer/htif_host_probe.cc` | `127b7041bd4322625e63752c8ce15036c24288360c9de9473ba4969dc2728df5` |
| `software/nova/observer/nova_htif_exit.cc` | `67f50419be6d8e8e0f1845ff68fe9012d2bf44f061d7c432f72c18165191cf3e` |
| `software/nova/observer/nova_htif_exit.h` | `6351e13842a4b6a3a98980ef6b8c08cc0c665c1dda5b4da399bc4142db9dcfb9` |
| `scripts/nova/htif_observer.py` | `086c63ed49bac0344c1be75ff3a35ed85017ef97cdd668ed43ba3ab2c973a206` |
| `scripts/nova/htif_exit_evidence.py` | `8a51c52fbe80f2f7d4461f0e46bb26f5928e6487c3b9f65bb1364aa5e207cfc4` |
| `scripts/nova/campaign_exec.py` | `b642779102b990c76ae691224e591ddc5c151e3bce8df5f546b5c958ff920dd7` |
| `scripts/nova/htif_host_probe.py` | `9396e26c79bae06ee5f5b502d97757de2b015c15672b47710f8d7cf2b108d8ff` |

These are executed native input identities from
[nova-inputs.json](htif-native-2026-11-25/nova-inputs.json), the original source
manifest, and the unchanged original
[artifact inventory](htif-native-2026-11-25/artifacts.json). They are not a
promise that every later repository revision has identical bytes. The complete
overlay is recorded as `nova_htif.cc` in the native experiment; campaign
preparation writes its corresponding overlay as `htif.cc` under the observer
output directory.

## Implemented observation and its boundary

| Repository module | Implemented responsibility |
| --- | --- |
| [htif_observer.py](../../../scripts/nova/htif_observer.py) | Verifies pinned source/header inputs, installed configuration/header and static archive prerequisites; creates a fresh hash-bound overlay manifest and verifies retained build inputs. |
| [observer.mk](../../../software/nova/observer/observer.mk) | Loads after the upstream Verilator Makefile, adds the overlay and recorder sources/include flags, and replaces the `-lfesvr` lookup with the explicit static archive while retaining the surrounding upstream link order. |
| [nova_htif_exit.cc](../../../software/nova/observer/nova_htif_exit.cc) and [header](../../../software/nova/observer/nova_htif_exit.h) | Synchronously records one dedicated terminal-state witness per process; observer I/O or contract failures terminate with host status 125. |
| [htif_exit_evidence.py](../../../scripts/nova/htif_exit_evidence.py) | Reads and validates bounded witness bytes and exact exit semantics independently of stdout/stderr. |
| [g1_campaign.py](../../../scripts/nova/g1_campaign.py) and [campaign_plan.py](../../../scripts/nova/campaign_plan.py) | Opt-in `--observe-target-exit` preparation, schema-2 plan/record, per-workload binding and witness capture, authoritative process/protocol checks, and final input/witness rechecks. |
| [observed_record.py](../../../scripts/nova/observed_record.py) and [compare_campaigns.py](../../../scripts/nova/compare_campaigns.py) | Validate the exact observer extension and compare recorded build/exit semantics while separating run-specific identities. |
| [verify_campaign_bundle.py](../../../scripts/nova/verify_campaign_bundle.py) | Checks retained raw log/witness bytes against a captured record and reruns protocol/witness assessment through bounded anchored reads. |
| [htif_host_probe.py](../../../scripts/nova/htif_host_probe.py) and [host fixture](../../../software/nova/observer/htif_host_probe.cc) | Reproduce the bounded native original/overlay comparison from exact local pinned sources without provisioning a toolchain. |

The runner supplies a fresh absolute witness path plus independent 64-character
lowercase hexadecimal `NOVA_HTIF_RUN_ID` and `NOVA_HTIF_BINDING_SHA256` values.
The recorder walks parent directories with no-follow descriptors, creates the
leaf exclusively with mode 0600, writes one newline-terminated JSON object,
syncs/checks it, and checks close errors. It never overwrites an existing leaf.
Missing/invalid environment, a second callback, or recording failure produces
the fixed fatal diagnostic and status 125. A matching witness cannot convert
that host failure into an accepted negative test.

The eight exact witness fields are `schema_version`, `kind`, `run_id`,
`binding_sha256`, `target_exit_present`, `raw_exit_code`, `target_exit_code`, and
`signal_exit`. The parser requires exact JSON types, rejects duplicate or extra
keys and malformed/oversized input, and bounds the file to 4096 bytes. A matching
event requires presence true, signal false, a positive odd signed-32-bit raw
value, and agreement between raw, decoded, and expected exit. The supported
campaign expectations are raw 1 / decoded 0 and raw 15 / decoded 7. An absent
exit has null raw and decoded values; it never verifies completion.

The canonical binding contains schema version, configuration, workload ID,
run ID, target ELF hash, simulator hash, observer-manifest hash, source revision,
source tree, source-state digest, cycle limit, and seed. All thirty workload
run IDs must be unique, and compared campaigns must have disjoint IDs. Ordinary
process/protocol assessment remains authoritative for host failure, timeout,
cancellation, changed inputs, and malformed output. In schema 2, only the
validated nested `target_exit.assessment` may set
`target_completion_verified=true`. Schema-1 protocol assessment, top-level
hardware/G1 flags, and comparison/bundle-verifier qualification remain false.

This records the HTIF terminal state supplied by the instrumented process. It
does not authenticate execution or attest which chip supplied it. The callback
accepts an instance pointer, but the recorder currently ignores that pointer
and permits only one stop per process; there is no SimTSI-map or chip-ID check.
The native fixture therefore does not establish SimTSI instance identity. The
full pinned
[Spike simulator](https://github.com/riscv-software-src/riscv-isa-sim/blob/9c190a07c6838f6392bafa4ad83acea462c7f759/riscv/sim.cc)
also has host-driven termination uses of HTIF, so the observer is not a general
proof of target instruction execution in arbitrary Spike configurations.

## Native result

The exact original HTIF implementation received a real `SIGTERM` from the host
fixture without receiving a target-exit command. It returned `done=true`,
decoded exit code zero, and host process status zero. The generated overlay
preserved those values but separately recorded exit absence and the signal.
The real witness parser rejected that event. This reproduces the ambiguous
native HTIF state; it does not reproduce the later SimTSI/TestDriver path.

Both native experiments produced the same six-mode result. Each mode ran once
per original/observed implementation in a fresh process, for twelve processes
per experiment. Ordinary stdout fixture facts, stderr, and host status matched
across the two implementations.

| Host fixture mode | Host status in both variants | Observed exit present | Raw value | Decoded value | Signal | Observer assessment |
| --- | --- | --- | --- | --- | --- | --- |
| `direct0` | 0 | true | 1 | 0 | false | observed |
| `direct7` | 7 | true | 15 | 7 | false | observed |
| `syscall0` | 0 | true | 1 | 0 | false | observed |
| `syscall7` | 7 | true | 15 | 7 | false | observed |
| `signal-only` | 0 | false | null | null | true | failed |
| `syscall7-signal` | 7 | true | 15 | 7 | true | failed |

Evidence: [experiment 14 results](htif-native-2026-11-25/results.json),
[commands](htif-native-2026-11-25/commands.json), and
[experiment 08 results](htif-native-2026-11-25/experiment-08/results.json).
The fixture's `main()` returns the HTIF result, so its status seven is not a
measurement of the real Verilator assertion/abort status. The mixed signal
case remains rejected even though a valid target exit value is present.

### What actually ran

Both native builds used the real pinned FESVR implementations of
[HTIF](https://github.com/riscv-software-src/riscv-isa-sim/blob/9c190a07c6838f6392bafa4ad83acea462c7f759/fesvr/htif.cc),
[memory interface](https://github.com/riscv-software-src/riscv-isa-sim/blob/9c190a07c6838f6392bafa4ad83acea462c7f759/fesvr/memif.cc),
[syscalls](https://github.com/riscv-software-src/riscv-isa-sim/blob/9c190a07c6838f6392bafa4ad83acea462c7f759/fesvr/syscall.cc),
[devices](https://github.com/riscv-software-src/riscv-isa-sim/blob/9c190a07c6838f6392bafa4ad83acea462c7f759/fesvr/device.cc),
[RFB](https://github.com/riscv-software-src/riscv-isa-sim/blob/9c190a07c6838f6392bafa4ad83acea462c7f759/fesvr/rfb.cc),
[ELF loader](https://github.com/riscv-software-src/riscv-isa-sim/blob/9c190a07c6838f6392bafa4ad83acea462c7f759/fesvr/elfloader.cc),
and [terminal](https://github.com/riscv-software-src/riscv-isa-sim/blob/9c190a07c6838f6392bafa4ad83acea462c7f759/fesvr/term.cc).
Those seven objects formed a normal native static archive. No HTIF, syscall,
device, memory-interface, or ELF-loader implementation was stubbed.

The fixture derives from `htif_t`, uses `{"none"}`, overrides startup to supply
tohost/fromhost symbols, and supplies a bounded 4096-byte host-memory array.
The actual `run()` loop, command dispatcher, memory interface, terminal state,
and stop path execute. The direct paths insert raw tohost values 1 or 15; the
proxy paths invoke the real syscall 93 dispatcher and check the real fromhost
acknowledgement. The fixture never calls the recorder directly. Its startup
override means the linked ELF loader is not exercised; linking it is not ELF
loading evidence. Memory stimuli originate in host C++, not a RISC-V CPU.

The configuration is explicitly synthetic: an identifying comment plus
`#define HAVE_INT128 1`. This is not a configuration generated by an installed
pinned toolchain. Both variants use the same compiled probe object and native
`-std=c++17 -O0 -g -pthread` flags, recorded include paths, and a fixture-only
`PREFIX`. The recorded tools were
[g++ 14.2.0](htif-native-2026-11-25/logs/version-gxx.stdout.log),
[GNU ar 2.44](htif-native-2026-11-25/logs/version-ar.stdout.log), and
[GNU nm 2.44](htif-native-2026-11-25/logs/version-nm.stdout.log).

The [archive member log](htif-native-2026-11-25/logs/archive-members.stdout.log)
lists the seven real objects. The
[original map excerpt](htif-native-2026-11-25/excerpts/original.map.excerpt.txt)
shows the original archive `htif.o` extraction; the
[observed map excerpt](htif-native-2026-11-25/excerpts/observed.map.excerpt.txt)
shows the complete overlay/recorder before the archive and the extracted
remaining members. The original and observed
[symbol](htif-native-2026-11-25/excerpts/original.symbols.excerpt.txt)
[excerpts](htif-native-2026-11-25/excerpts/observed.symbols.excerpt.txt) show one
defined `htif_t::stop()` per executable and the recorder only in the observed
one. These are explicitly partial text excerpts; the full originals' hashes
and selected line ranges are retained. The full-map absence check itself was
performed by the native probe and recorded in `results.json`. No duplicate
definition allowance, whole-archive workaround, or shared interposition was
used.

### Separate experiments and bounded replay

Experiment 08 used a session probe script and completed the twelve-process
comparison before the reusable CLI was added. Its original command was:

```bash
python3 -B /workspace/scratch/1f6d25e13e37/coordination/a08-native/run_probe.py --output /workspace/scratch/1f6d25e13e37/coordination/a08-native/run-01
```

Its [results](htif-native-2026-11-25/experiment-08/results.json),
[command records](htif-native-2026-11-25/experiment-08/commands.json),
[source manifest](htif-native-2026-11-25/experiment-08/source-manifest.json), and
[NOVA input identities](htif-native-2026-11-25/experiment-08/nova-inputs.json)
are preserved unchanged. The session script and compiled products are omitted
from the compact selection; the repository CLI is the supported replay entry.

Experiment 14 executed the delivered CLI once, returned status zero, and
recorded elapsed time **6.879953 seconds**:

```bash
python3 -B scripts/nova/htif_host_probe.py --execute \
  --source-root /workspace/scratch/1f6d25e13e37/coordination/a08-native/run-01/inputs/spike \
  --output /tmp/nova-cpu-1f6d25e13e37-a14-run-01 \
  --total-seconds 180
```

These are original commands, not portable instructions with fabricated paths.
A new run needs a prepared local source root matching the exact manifest and a
fresh output leaf under an existing parent. Default/`--plan` operation is
read-only. Explicit `--execute --source-root ... --output ...` verifies and
captures those local bytes; it does not download sources, install dependencies,
initialize submodules, or cross-compile target software. The second experiment
reused the audited source collection from the first; neither is an independent
clean hardware campaign.

The CLI runs nineteen serial build/inspection commands and twelve fresh host
fixture processes, with these resource guards:

| Bound | Executed default | Maximum accepted by CLI |
| --- | --- | --- |
| Aggregate time | 180 seconds | 300 seconds |
| Each build/inspection command | 45 seconds | 60 seconds |
| Each fixture process | 5 seconds | 30 seconds |
| Each stdout/stderr stream | 1 MiB | 4 MiB |
| Required free space | 1 GiB | Configurable positive floor, checked at bounded sampling points |
| Final artifact capture | 256 files, 32 MiB per file, 128 MiB total | Fixed limits |

The CLI reserves runner cleanup and final-capture time before launch. These are
trusted-process guards, not OS quotas, a sandbox, or a hard wall-clock guarantee.
Actual code-7 child returns remain `status=failed`/exit 7 in engine records; the
higher-level expected-exit interpretation never changes the observed status or
conceals cancellation/resource failure. The separate
[rejection controls](htif-native-2026-11-25/cli-rejection-controls.json) record
exit 2 and no launched command for existing output, a one-second exhausted
aggregate budget, and a rejected 301-second budget.

## Actual Make and native archive probes

Experiment 18 used unchanged copies of the actual upstream Makefiles in an
isolated fixture root. Its
[summary](htif-native-2026-11-25/experiment-18/summary.json) and
[commands](htif-native-2026-11-25/experiment-18/commands.json) preserve the
observations. It established the following limited facts:

- Loading the NOVA fragment after the upstream Makefile preserves the default
  goal, expands the overlay/recorder sources and include flags, and adds manifest
  verification to the model and simulator targets.
- The actual expanded compiler flags survived the normal shell quoting and a
  second native Makefile shell. A compiled native check recovered the exact
  `PREFIX` string. The same flags compiled the pinned overlay and recorder.
- Compiler dependency output contained the generated translation unit and all
  seventeen recorded headers: fifteen pinned source headers, synthetic
  installed-style `fesvr/config.h`, and the recorder header. An extra shadowing
  `fesvr/platform.h` was rejected.
- Expanded link flags retained upstream ordering, including `-lriscv`, explicit
  `libfesvr.a`, and `-ldramsim`, with no `-lfesvr` lookup. A bounded native link
  using experiment 14's probe object and native archive succeeded; original
  archive `htif.o` was not extracted, and one real native `direct0` process
  emitted presence true, raw 1, decoded 0, signal false.
- Verification rejected a subsequent mutation of a recorded generator input.

The probe supplied `TIMESCALE_OPTS=` to avoid the upstream parse-time Verilator
version subprocess. No Verilator binary or generated simulator makefile was
executed. The native link did not link `libriscv` or DRAMSim and did not establish
installed-toolchain ABI compatibility.

The audit also reproduced a **standalone incremental reuse limitation**. With
existing model/simulator sentinel products newer than observer inputs, the
actual Make target returned zero, reran manifest verification, and did not
rebuild those products. Make's `-o` option suppressed unrelated prerequisites
for that controlled probe; the sentinels were not represented as real
simulators. Thus the fragment alone does not establish that an existing product
was instrumented. The intended campaign rejects pre-existing generated sources,
selected simulator products, and observer output before preparation; a runtime
witness is also mandatory. Fresh observed campaign builds remain the supported
scope. Standalone incremental reuse needs an observer-specific build identity
before it can be qualified.

## Audit findings incorporated into the tooling

### Cancellation and final evidence

[campaign_exec.py](../../../scripts/nova/campaign_exec.py) now reconciles
cancellation latched during finishing and restoration of scoped signal
handlers. The regression exercises real native children returning 0, 7, and
-15 at three finish/restoration boundaries, plus ordinary controls. Actual
child exit values and captured stream identities remain intact; a late
campaign-owned interruption cannot leave the record passed.

The outer [campaign finalization](../../../scripts/nova/g1_campaign.py) also
restores handlers while retaining the cancellation latch and the exclusively
created record descriptor, then reconciles and rewrites that record. It checks
aggregate deadline crossing after JSON serialization/explicit flushing and
rechecks every retained witness rather than stopping after the first mismatch.
Each changed witness loses its completion flags, and a known failure is not
downgraded by a later cancellation. The focused
[finalization regressions](../../../tests/nova/test_g1_campaign_observer.py)
cover these boundaries with synthetic campaign orchestration and real bounded
file operations.

Signal ownership returns to the caller separately as each original handler is
restored. After both are restored, later signals are outside campaign-owned
cancellation. The last deadline check precedes close/teardown/return; the
record writer is not a transactional publisher, crash/SIGKILL recovery system,
or hard deadline mechanism. Concurrent readers must not treat an in-progress
record write as a committed result.

### Pinned code-seven and crash diagnostics

The negative-control grammar in
[workload_assessment.py](../../../scripts/nova/workload_assessment.py) now
permits zero or one exact pinned stderr diagnostic
`*** FAILED *** (tohost = 7)` before the required code-7 SimTSI assertion. This
does not replace the target marker or assertion. Duplicate, late, wrong-code,
wrong-stream, noncanonical, and conflicting terminal text remains rejected.
The direct native code-seven cases independently produced that diagnostic;
the real generated Verilator assertion/trailer formatting is still unrun.
Host statuses -6, 134, or 255 are not target code seven; the pinned HTIF SIGABRT
handler explains the possible `exit(-1)`/255 form. Positive protocol assessment
also rejects the specific segmentation-fault diagnostic on either stream.
See the [source-shaped parser regressions](../../../tests/nova/test_protocol_source_regressions.py).

### Seven comparator consistency checks and schema 2

The legacy [comparator](../../../scripts/nova/compare_campaigns.py) was hardened
in seven concrete areas: required marker byte bounds; artifact namespace/type
and minimum ELF structural size; exact fixed plan semantics; type-preserving
JSON comparison; explicitly false inspector qualification fields; source-state
digest binding; and consistency of any retained detailed ready-profile rows.
The [consistency regressions](../../../tests/nova/test_comparator_consistency.py)
include coherent-looking mutations to both input records. Recomputed hashes do
not make a boolean an integer, a contradictory profile ready, or impossible
artifact metadata evidence of a real build.

Schema 2 additionally checks the fixed observer preparation/build contract,
manifest and source bindings, exact nested witness assessment, run-ID uniqueness,
and no nonce reuse across compared campaigns. It compares stable exit semantics
and observer build identities while excluding run-specific nonce/binding/raw
witness differences from cross-run equality. Mixed schemas and retained
downgrade extensions fail closed. A `consistent` result still describes supplied
records; it does not verify independent execution, actual ELF contents, or
hardware/reference-comparison qualification.

### Retained-file and parser fixes

The [bundle verifier](../../../scripts/nova/verify_campaign_bundle.py) now
counts bare CR and LF delimiters consistently with `bytes.splitlines()`, treating
CRLF as one line. The original LF-only count could accept a CR-heavy log above
the parser's line budget. A small reproduced example and boundary regressions
exercise the fix without a large allocation.

The verifier also parses the bytes already captured through its anchored
directory descriptor. It no longer invokes a path-based shared reader that
could reopen `record.json` through a substituted parent symlink. The comparator's
new `parse_record_bytes()` shares bounded decoding/complexity validation while
preserving its existing path-reader API. The bundle retains final file identity
and rehash checks. A subsequent repair also gives the standalone comparator
reader anchored no-follow directory and leaf access, pre-read identity checks,
bounded reads, and final parent identity checks. Its deterministic parent-swap
test failed before the fix for both symlink and directory replacements; eight
new path/cleanup tests and six existing reader tests passed afterward. Neither
reader guarantees immutability after verification returns. See the
[retained-bundle regressions](../../../tests/nova/test_verify_campaign_bundle.py)
and [standalone reader regressions](../../../tests/nova/test_record_reader_paths.py).

## Repository-only verification checkpoints

The first committed observer integration had source tree
`0cb2b42b61eb1a6048c5e1cfe8753edc0daf383f`. Its local commit was
`e9f4b9470f2f9e9e066250c5264d089b5353b4da`; the byte-identical published commit is
[7daf663829b98faad619d2bba42ac022dadf7398](https://github.com/baabi-boo/CPU/commit/7daf663829b98faad619d2bba42ac022dadf7398).
The integrating agent ran `make -f nova.mk check` from a fresh checkout:
**752 tests passed in 35.241 seconds**, with metadata and managed-text whitespace
checks passing. This is the first integration checkpoint, not a retroactive
count of the later suite or hardware validation.

The subsequent published checkpoint
[66f3eb1eb182732d12be883ad24f2282e5bcfa1f](https://github.com/baabi-boo/CPU/commit/66f3eb1eb182732d12be883ad24f2282e5bcfa1f),
tree `b86289a6a1f825ba34e579ab995cfec812e30699`, includes core observer tooling,
CI coverage, the bundle verifier, and campaign finalization fixes. Its separate
fresh-checkout `make -f nova.mk check` passed **801 tests in 37.726 seconds**,
including metadata and managed-text whitespace checks. These measured checkpoints
do not assert a final suite total or remote GitHub Actions success. Their
[check excerpts](htif-native-2026-11-25/checkpoints/checkpoint-01.excerpt.txt)
and [subsequent check excerpt](htif-native-2026-11-25/checkpoints/checkpoint-02.excerpt.txt)
retain the exact log lines and identify the full original log hashes in the
retention manifest.

The reusable native CLI also passed
[fourteen focused tests](htif-native-2026-11-25/focused-tests.stderr.log), covering
pinned-source rejection, exact command/link planning, limits, explicit execution,
fresh output, expected nonzero status, and map/symbol checks. These counts overlap
the full suite; they must not be added to produce an invented aggregate total.
No total-worker completion or human gate acceptance is claimed here.

### Observed CI portability failure and repair

The [GitHub Actions run for `66f3eb1e`](https://github.com/baabi-boo/CPU/actions/runs/45699683466)
failed in the foundation validation step. Its native fixture class could not
compile because Ubuntu's fortified libc marks `ftruncate` with
`warn_unused_result`; casting the call to `void` did not satisfy the existing
`-Werror` policy. The run reported 777 tests and one class-setup error, rather
than execution of the 24 native fixture cases. This was an actual CI failure,
not a missing runner, hardware failure, or successful 801-test remote run.

The repair stores and explicitly discards the cleanup result without changing
best-effort invalidation or fatal status 125. The existing single Linux fixture
build now explicitly enables fortify level 2 with its warnings still treated
as errors. The original source reproduced the warning under both fortify
levels 2 and 3 on the local compiler; the repaired source compiled at both
levels, and all 24 native fixture tests passed. The repaired recorder SHA256 is
`d6322b49c9acbfbbe4e5a15fff0c41c17b83310347bc49e64e01b7527ae7adfa`.
The earlier native input table and retained observations continue to identify
their original executed snapshot. Later remote results must be recorded against
their actual tested commit.

## Remaining G1 work

A read-only `python3 -B scripts/nova/g1_profile.py --strict --json` recheck on
this host returned status `blocked`, **38 blockers**, and exit 2. All 57 gitlink
entries and all nine imported Conda file Git blob identities matched
[upstream-lock.json](../../../nova/upstream-lock.json). No dependency migration,
toolchain installation, or submodule initialization was performed for this
evidence. Missing prerequisites are blockers, not a CPU test failure or success.

The hardware work still requires a reviewed pin-preserving prepared environment,
an approved execution budget, and a genuine observed fifteen-workload campaign
for each of `RocketConfig` and `NovaM1BaselineConfig`, including the real negative
control and bounded interruption cases. Retain raw logs, witnesses, ELF/simulator
and build identities; repeat the full campaign in a second independent clean
build; verify the bundles and compare their records. Resolve the supported
pinned-reference comparison scope and obtain a maintainer's evidence-based
decision. None of the native or repository checks in this record accepts G1,
`T-BUILD-001`, or `T-ISA-001`.

## Evidence retention

The compact directory contains 55 files totaling 237,313 bytes: selected
original observations, copied byte for byte, explicitly identified excerpts,
and the selection's retention manifest. Its
[retention manifest](htif-native-2026-11-25/retention-manifest.json) gives original
paths, byte counts, SHA256 values, excerpt line ranges, and omitted material.
Recorded absolute execution paths and random run identities are preserved.
They describe the original runs and are not rewritten into portable paths.

This selection is not a complete replay bundle: source/header snapshots,
objects, archives, executables, full link maps, and most per-command logs are
omitted. The unchanged original artifact inventory identifies their recorded
hashes; an inventory entry does not assert that its file is included here.
No upstream source is copied into this compact selection. Hash agreement and
record consistency provide integrity checks, not execution authentication.

| Retained original observation | SHA256 |
| --- | --- |
| Experiment 14 `results.json` | `d69c4b3b05854ceac7a3909317581379b6b60ad1e92ee2f34e04806ff7fecc02` |
| Experiment 14 `commands.json` | `9d13c930267999f440954fe0866cb21e326695dc9f7339a93a0ddd9054c5e3e9` |
| Experiment 14 original `artifacts.json` | `38c37db56a83a9dc345c497b183b411c79528e32853655b417814eab9224afa5` |
| Experiment 08 `results.json` | `f1251ccde54f96cbc4e4e94efaf6445cb843dc6ef4609bfe0df8b23403ba685e` |
| Selection `retention-manifest.json` | `053cd9aabc5308f511e16456db959da6db9fb7abaf2cae46e1deb0832a66a9f6` |

All 48 full-file copies were byte-compared with their original observations.
The six excerpts were reconstructed from their declared source line ranges and
checked against their retained hashes. The original inventory is intentionally
not rewritten to suggest that its omitted files are present. Full binary/source
reproduction requires the separately prepared pinned inputs described above.
