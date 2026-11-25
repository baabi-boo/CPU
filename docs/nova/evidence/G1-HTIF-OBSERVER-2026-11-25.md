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
| Native experiment 14 | Historical CLI snapshot: nineteen build/inspection commands and twelve bounded native processes passed; original identities and results retained below |
| Latest native experiment 50 | Frozen final implementation: 31 commands, including twelve native cases, assessed as expected in 6.281061 seconds; six actual code-seven command failures remain recorded |
| Make/native experiment 18 | Actual copied upstream Makefiles parsed; quoting, header closure, static archive order, and one native `direct0` case checked |
| First committed observer integration | Fresh-checkout repository-only check: 752 tests passed; later integration results must be recorded separately |
| Subsequent committed checkpoint | Fresh-checkout repository-only check: 801 tests passed; this is a checkpoint, not the final evolving suite total |
| Recorder/parser/manifest repair checkpoint | Published `3520f99a`: fresh-checkout repository-only check passed 822 tests in 39.673 seconds; later repairs are outside this checkpoint |
| Current source integration checkpoint 05 | Local `52161a0b`, byte-identical published `0e471171`: fresh-checkout repository-only check passed 836 tests in 40.355 seconds |
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

### Frozen transform and historical native input identity

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

These are the historical experiment-14 executed native input identities from
[nova-inputs.json](htif-native-2026-11-25/nova-inputs.json), the original source
manifest, and the unchanged original
[artifact inventory](htif-native-2026-11-25/artifacts.json). They are not a
promise that every later repository revision has identical bytes. Later recorder,
parser, manifest-validator, and native-finalization repairs are not retroactively
covered by this run. The separately retained latest native replay below records
the current executed identities and results. The complete overlay is recorded
as `nova_htif.cc` in the native
experiment; campaign preparation writes its corresponding overlay as `htif.cc`
under the observer output directory.

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
Missing/invalid environment, a second callback, or recording failure terminates
with status 125 and attempts the fixed fatal diagnostic. Diagnostic delivery is
best effort: stderr is temporarily nonblocking, SIGPIPE is blocked, and write
retries are bounded. A full pipe can receive no diagnostic. Cleanup attempts
truncation only through the exclusively created descriptor still owned by the
recorder; it never unlinks any pathname, reopens a failed witness, or retries a
failed close. An empty file may remain, and truncation or close errors can leave
partial or complete bytes. **Host status 125 is authoritative even if retained
bytes form a valid witness**; they cannot make that failure an accepted negative
test.

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

## Latest native replay (experiment 50)

The final native replay invoked the delivered
[native CLI](../../../scripts/nova/htif_host_probe.py) exactly once from a clean,
isolated checkout of local commit
`52161a0b395f0644d693c132433ea9246deab712`. Its exact source tree is
`609d280a87e6b14d1c01c934d74f8fe51a9a8f3e`, independently matched to published
commit
[0e4711713ca82da8d55ee03f742a91d6f5db116e](https://github.com/baabi-boo/CPU/commit/0e4711713ca82da8d55ee03f742a91d6f5db116e).
The retained [checkout provenance](htif-native-final-2026-11-25/checkout-provenance.json)
identifies the isolated checkout and exact input hashes. Concurrent documentation
edits in the shared checkout did not alter the frozen execution inputs.

From `/tmp/nova-cpu-1f6d25e13e37-a50-mxjy7xht/CPU`, the exact invocation was:

```bash
python3 -B scripts/nova/htif_host_probe.py --execute \
  --source-root /workspace/scratch/1f6d25e13e37/coordination/a08-native/run-01/inputs/spike \
  --output /tmp/nova-cpu-1f6d25e13e37-a50-mxjy7xht/run-01
```

The [invocation record](htif-native-final-2026-11-25/invocation.json) reports
exit 0, empty stderr, and an outer wall time of 6.359713 seconds, from
`2026-11-25T21:40:25.002684+00:00` to `2026-11-25T21:40:31.362472+00:00`.
The persisted [results](htif-native-final-2026-11-25/results.json) report
**status `passed`, 31 commands, twelve fresh native processes, and 6.281061
seconds**. CLI stdout matches the persisted result after removing only its
added absolute `output` field. No timeout, interruption, incomplete-artifact
flag, or failure reason occurs in that aggregate result.

The original and observed builds each ran the same six modes. Fixture stdout
facts, ordinary stderr, and actual host status matched within every pair.

| Mode | Host exit, original / observed | Seconds, original / observed | Exit present | Raw / decoded | Signal | Overlay parser |
| --- | --- | --- | --- | --- | --- | --- |
| `direct0` | 0 / 0 | 0.003789 / 0.003835 | true | 1 / 0 | false | observed |
| `direct7` | 7 / 7 | 0.003788 / 0.003742 | true | 15 / 7 | false | observed |
| `syscall0` | 0 / 0 | 0.003633 / 0.003772 | true | 1 / 0 | false | observed |
| `syscall7` | 7 / 7 | 0.003656 / 0.003857 | true | 15 / 7 | false | observed |
| `signal-only` | 0 / 0 | 0.003655 / 0.003783 | false | null / null | true | failed |
| `syscall7-signal` | 7 / 7 | 0.003835 / 0.003805 | true | 15 / 7 | true | failed |

The signal-only processes again returned `done=true` and host exit zero without
an exit value. The observer parser rejected both signal-bearing modes, including
the mixed mode with raw 15 / decoded 7. The only nonempty runtime stderr was the
unchanged `*** FAILED *** (tohost = 7)` line in both `direct7` cases.
The [raw command records](htif-native-final-2026-11-25/commands.json) preserve
all six code-seven processes as engine **`status=failed`, actual exit 7, and
reason `command exited unsuccessfully`**, with `expected_exit_observed=true`.
The expected native-case assessment does not normalize those command facts or
make the rejected signal witnesses successful completion evidence.

### Applied guards and native scope

The retained [plan](htif-native-final-2026-11-25/plan.json) and invocation apply
the delivered defaults without limit overrides:

| Guard | Applied value |
| --- | --- |
| Aggregate deadline | 180 seconds |
| Each build/inspection command | 45 seconds |
| Each fresh native process | 5 seconds |
| Each stdout/stderr stream | 1 MiB |
| Sampled free-space floor | 1 GiB |
| Parallel jobs | One; command timestamps independently verified as serial |
| Cleanup / final capture reserve | 2 seconds per command / 3 seconds before launch |
| Optional artifact capture | 256 files, 512 entries including directories, 32 MiB per file, 128 MiB total |

Free space was 1,407,537,152 bytes immediately before execution and
1,391,030,272 bytes afterward. No command was blocked by the unchanged floor.
These remain cooperative/sampled trusted-process guards, not OS quotas or a
hard bound on synchronous filesystem calls.

The tools were native
[g++ 14.2.0](htif-native-final-2026-11-25/logs/version-gxx.stdout.log),
[GNU ar 2.44](htif-native-final-2026-11-25/logs/version-ar.stdout.log), and
[GNU nm 2.44](htif-native-final-2026-11-25/logs/version-nm.stdout.log).
The retained [synthetic config](htif-native-final-2026-11-25/synthetic-config/config.h)
contains only its identifying host-fixture comment and `#define HAVE_INT128 1`.
The real pinned FESVR code receives synthetic native host-memory stimuli.
No ELF loading, RISC-V instruction execution, TSI, TestChipIP, TestDriver,
Verilator, processor campaign, RTL, or installed pinned-toolchain qualification
was performed. All top-level `cpu_execution`, `rtl_simulation`,
`target_completion_verified`, `hardware_qualified`, and `g1_gate_passed` flags
remain **false**. Nested completion flags describe supplied host fixture events.

### Independent verification and current source identity

The [independent verification](htif-native-final-2026-11-25/verification.json)
records the following post-run checks, separately from the CLI's assessment:

| Material checked | Independently verified result |
| --- | --- |
| Command records | 31/31 matched the aggregate and individual raw records, exact planned argv/order, and serial timestamps; nineteen build/inspection commands returned zero |
| Command log streams | 62/62 byte counts and SHA256 hashes matched; all streams remained within 1 MiB; runtime JSON and stderr matched their result rows |
| Pinned source closure | 24/24 source/header/LICENSE inputs, totaling 261,107 bytes, matched original and captured inputs at the unchanged Spike pin |
| Observer witnesses | 6/6 byte counts, hashes, unique 64-character run IDs, modes, native binary identities, and recomputed bindings matched; no original-build witness exists |
| Original artifact inventory | 152/152 entries, totaling 16,008,634 bytes, rehashed with zero mismatches; every full-output file except the inventory itself is covered |

The ten native compile commands shared identical flags. Seven real FESVR units
formed the archive, in the order shown by the retained
[archive member log](htif-native-final-2026-11-25/logs/archive-members.stdout.log).
Both links used the same fixture object. Full-map inspection found original
archive `htif.o` in the original link and excluded it from the observed link;
the overlay and recorder preceded the archive. Each full symbol log defined
exactly one `htif_t::stop()`, and only the observed binary defined exactly one
`nova_htif_observe_stop(...)`. No duplicate-definition or interposition allowance
appears in the actual link argv. The
[original map excerpt](htif-native-final-2026-11-25/excerpts/original.map.excerpt.txt),
[observed map excerpt](htif-native-final-2026-11-25/excerpts/observed.map.excerpt.txt),
[original symbol excerpt](htif-native-final-2026-11-25/excerpts/original.symbols.excerpt.txt),
and [observed symbol excerpt](htif-native-final-2026-11-25/excerpts/observed.symbols.excerpt.txt)
preserve exact selected line ranges and full-source hashes. Excerpts alone do
not establish the full-map absence check; that check is recorded in the
independent verification.

All seven executed NOVA inputs matched their exact commit blobs, isolated
checkout, captured execution inputs, and current repository bytes when this
record was integrated. Their separate
[input manifest](htif-native-final-2026-11-25/nova-inputs.json) preserves the
executed identities; the experiment-14 table above remains historical.

| Current code / executed input | Executed SHA256 |
| --- | --- |
| [Host fixture](../../../software/nova/observer/htif_host_probe.cc) | `127b7041bd4322625e63752c8ce15036c24288360c9de9473ba4969dc2728df5` |
| [Recorder](../../../software/nova/observer/nova_htif_exit.cc) | `d10369310beea25776a22f6df472b30f35f13f3440b75d3659f73649b00b71f7` |
| [Recorder header](../../../software/nova/observer/nova_htif_exit.h) | `6351e13842a4b6a3a98980ef6b8c08cc0c665c1dda5b4da399bc4142db9dcfb9` |
| [Overlay generator](../../../scripts/nova/htif_observer.py) | `c7c660c24e7c201638ebf2398625837eb1ca124d897af398ba75ff94662e0967` |
| [Witness parser](../../../scripts/nova/htif_exit_evidence.py) | `7b459fad18df011fca37dcf8e949f601f71de34d98b3e129e51d4e2274732ab8` |
| [Command engine](../../../scripts/nova/campaign_exec.py) | `b642779102b990c76ae691224e591ddc5c151e3bce8df5f546b5c958ff920dd7` |
| [Native CLI](../../../scripts/nova/htif_host_probe.py) | `40a669624f038f4e8dec645a8a5eb7b02e05839b9de5c9e230f9b112ecbfab6a` |

### Latest replay retention

The separate `htif-native-final-2026-11-25` selection contains **55 files /
309,321 bytes**: fifty full-file copies, four declared line excerpts, and its
[retention manifest](htif-native-final-2026-11-25/retention-manifest.json).
All 55 selected files were copied byte for byte from the verified compact
handoff and rehashed after repository retention. The manifest retains its
original selection/output paths, nonces, bindings, JSON, and log bytes; its
absolute `selection` field describes the handoff location, not this repository
directory. It hashes the other 54 files, not itself.

**108 full-run files / 15,869,518 bytes are explicitly omitted**, including
binaries, ten objects, the archive, source/header/LICENSE snapshots, generated
overlay source, full maps/symbol dumps, redundant per-command JSON, and other
build logs. The full temporary output comprised 153 regular files totaling
16,031,721 bytes. This compact selection is not a complete replay bundle. The
unchanged [original inventory](htif-native-final-2026-11-25/artifacts.json)
records omitted identities without asserting those files are retained here.
The [pinned source manifest](htif-native-final-2026-11-25/source-manifest.json)
preserves revision and upstream URLs; the original LICENSE SHA256 remains
`c65e436d18972c9c4bd192494fe4870bd2e158179474975b80a3559f27631632`.
The explicitly synthetic config is the only retained source-like file.

| Latest retained artifact | SHA256 |
| --- | --- |
| [results.json](htif-native-final-2026-11-25/results.json) | `b270d7c0c36a2644194e823ce74f8936638e77a7a776b848f3e28319b0a3217c` |
| [commands.json](htif-native-final-2026-11-25/commands.json) | `39a94deb3f92e6135a219a22fb760cebbb76b74f13f33d3620b268d7131a50cb` |
| [artifacts.json](htif-native-final-2026-11-25/artifacts.json) | `f87321c38476ac12a75bbadb008fd92e19f4120d79b92742fe37b2e99d5b5af5` |
| [verification.json](htif-native-final-2026-11-25/verification.json) | `29fb7e4011c4cf6a62b546a107ada64227af0a8912dc473a3b519203cececb58` |
| [retention-manifest.json](htif-native-final-2026-11-25/retention-manifest.json) | `fa47392bf0702654258b47075262084746d90cae19d3122e9d709768a5e155f9` |

## Historical native results

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

At the experiment-14 snapshot, the CLI ran nineteen serial build/inspection
commands and twelve fresh host fixture processes with these configured guards:

| Bound | Experiment-14 default | Maximum accepted at that snapshot |
| --- | --- | --- |
| Aggregate time | 180 seconds | 300 seconds |
| Each build/inspection command | 45 seconds | 60 seconds |
| Each fixture process | 5 seconds | 30 seconds |
| Each stdout/stderr stream | 1 MiB | 4 MiB |
| Required free space | 1 GiB | Configurable positive floor, checked at bounded sampling points |
| Final artifact capture | 256 files, 32 MiB per file, 128 MiB total | Fixed limits |

The CLI reserves runner cleanup and final-capture time before launch. The current
enumeration and finalization controls are described separately below; this
historical table does not establish their execution. These are
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

### Recorder cleanup and bounded fatal output

The current [recorder](../../../software/nova/observer/nova_htif_exit.cc) removes
the identity-check-then-unlink cleanup path: a pathname can change after its
identity check. Descriptor-only truncation preserves foreign replacements while
invalidating the owned inode when the filesystem permits it. The
[native regressions](../../../tests/nova/test_htif_native.py) include replacement
at the former unlink race and immediately before truncation, real full stderr
pipes in blocking and nonblocking modes, and retained complete bytes after a
close error. The pre-repair controls reproduced deletion of a foreign file and
a five-second timeout on a full blocking pipe; the repaired controls returned
125 without those outcomes.

Fatal diagnostic short-write/EINTR handling has a finite 64-attempt budget;
stderr flag-setting retries are also bounded. Ordinary writable streams retain
the exact diagnostic and their original flags. Because `O_NONBLOCK` belongs to
the shared open-file description, the temporary change can affect inherited
descriptors. Concurrent flag mutation or a permanent restoration error is outside
the tested restoration guarantee. The witness write loop and synchronous device
or filesystem calls do not acquire a general signal-storm or wall-clock bound.

### Witness descriptor ownership and complete manifest bounds

The [witness reader](../../../scripts/nova/htif_exit_evidence.py) transfers
directory ownership before closing the prior directory and retains an opened
leaf while its parent is closed. Cleanup attempts to close each independently
owned descriptor once; a failed close is never retried against a possibly reused
descriptor number. Cleanup preserves an earlier read, validation, or interruption failure
and attempts the remaining independent closes. An otherwise successful read
with a close failure returns the sanitized safe-read failure with all observation
and qualification flags false and null witness metadata. The
[parser regressions](../../../tests/nova/test_htif_exit_evidence.py) exercise real
kernel closes followed by injected errors and descriptor-number reuse. The
existing no-follow traversal and inclusive 4096-byte witness limit remain.

Pure [observer metadata validation](../../../scripts/nova/htif_observer.py) now
reconstructs the complete manifest, checks its strict shape, and rejects
`manifest_bytes` below that object's compact ASCII JSON length. This minimum
depends on the supplied paths and integer widths; the existing 65,536-byte
maximum remains. Validation does not open files or infer a raw manifest digest
from a canonical serialization. Different key order, whitespace, and omission
of a trailing newline remain valid when the actual raw size and hash are retained.
The [manifest regressions](../../../tests/nova/test_htif_observer.py) cover those
boundaries. This rejects impossible metadata without authenticating a build or
execution.

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

### Native probe enumeration and terminal persistence

Current [native probe finalization](../../../scripts/nova/htif_host_probe.py)
streams directory entries and stops at the first excess file or entry. The
bounds are **512 entries including directories**, **256 captured files**,
32 MiB per file, and 128 MiB total. Only captured rows are sorted. Directory
access is no-follow; regular-file validation rejects symlinks and special files.
Cancellation/deadline checks run during enumeration, around artifact
capture, and before and after every 64 KiB read; executable, log, and linkage-map
reads use the same checks. Each read is further capped by the remaining aggregate
capture allowance. Previously retained raw files and rows survive a later stop.

`results.json` and `artifacts.json` are each created exclusively once. Their
owned descriptors remain open through initial persistence and handler restoration
so late interruption, deadline crossing, and metadata time can be reconciled
without reopening a pathname. Corrections refresh the result hash in the
inventory; each metadata file's first write error is retained. A previous failure
stays failed while interruption/deadline facts are added. The
[native finalization regressions](../../../tests/nova/test_htif_host_probe.py)
cover actual SIGTERM, virtual deadlines, bounded enumeration/read controls,
descriptor closure, and saved-byte/hash agreement. Those controls executed no
native cases. The separately retained experiment-50 replay above exercised the
current native CLI in twelve fresh processes.

Synchronous filesystem calls can still exceed the sampled deadline. Essential
terminal metadata is attempted after optional capture stops; the last successful
corrective write, close, and return can follow the last elapsed-time sample.
Persistence is not transactional or crash/SIGKILL recovery, and persistent I/O
failure can prevent complete evidence retention.

### Inherited build overrides and read-only CLI imports

Both campaign modes reject inherited `ASPECTS`, `ASPECT_ARGS`, and `MAKE`, even
when empty, before profile/provenance checks or commands. They can change the
generator aspects or recursive Make invocation. The retained rejection names
the setting without copying its value, and all unstarted rows remain `not_run`.
Read-only plans remain unchanged by those settings. The
[campaign regressions](../../../tests/nova/test_g1_campaign.py) also retain
ordinary `PATH`, `RISCV`, and `CONDA_PREFIX` forwarding; this enumerated policy
does not authenticate arbitrary environment influences.

The campaign, comparator, and retained-bundle CLI entrypoints now disable Python
bytecode writing before sibling imports, matching the native probe convention.
Their read-only routes remain free of sibling `__pycache__` writes even when
called without `-B`. Isolated cold-cache controls exercised the default campaign
plan and missing-record comparator/verifier routes with and without `-B`: patched
routes created no files or child executions and preserved complete stdout and
exit codes. This establishes the audited CLI behavior, not execution provenance.

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

Checkout-relative metadata does not establish binary determinism across checkout
or installation paths. The [observer recipe](../../../software/nova/observer/observer.mk)
embeds the actual `RISCV` prefix through `PREFIX` and an absolute runtime library
search path (`rpath`); the
[simulator link recipe](../../../sims/common-sim-flags.mk) also retains that
runtime path. Different paths can therefore produce `different`.
Exact ELF, simulator, generated-artifact, archive, and manifest hashes remain in
comparison; preserve and investigate differences rather than normalize their
bytes or weaken hash equality. A fixed-path or prefix-remapping procedure still
needs its own review and real build evidence.

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

The later published checkpoint
[3520f99a4939ed97fb002ec4c91debb8e7d7b06a](https://github.com/baabi-boo/CPU/commit/3520f99a4939ed97fb002ec4c91debb8e7d7b06a)
includes the documentation integration and the recorder, witness-parser, and
complete-manifest size repairs described above. Its fresh-checkout
`make -f nova.mk check` passed **822 tests in 39.673 seconds**. The later native
finalization, inherited-override, and read-only CLI repairs have the separately
recorded checkpoint below; 822 remains the earlier checkpoint's total.

The integrating agent's **checkpoint 05** ran `make -f nova.mk check` from fresh
checkout `/tmp/nova-cpu-1f6d25e13e37-checkpoint-05`, at local commit
`52161a0b395f0644d693c132433ea9246deab712`, tree
`609d280a87e6b14d1c01c934d74f8fe51a9a8f3e`. The byte-identical published commit
is [0e4711713ca82da8d55ee03f742a91d6f5db116e](https://github.com/baabi-boo/CPU/commit/0e4711713ca82da8d55ee03f742a91d6f5db116e).
The repository metadata check, **836 tests in 40.355 seconds**, managed-text
whitespace check, and `git diff --check` passed. The observed original log is
`/workspace/scratch/1f6d25e13e37/coordination/checkpoint-05-check.log`, SHA256
`71b5e110ec7573ff7bab85e5f57a71080e164639e1c5a75e30ea988f457a6387`;
its exact lines 848 and 850 are `Ran 836 tests in 40.355s` and `OK`.
This is repository-only verification of that source snapshot, separate from
experiment 50's twelve native cases. The test and native counts are not added,
and this record claims no completed worker total or human gate acceptance.

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

The subsequent
[run 45701410807](https://github.com/baabi-boo/CPU/actions/runs/45701410807)
passed for the fortify repair at
[24d00430796e3dd09a31af6f91364056edda0137](https://github.com/baabi-boo/CPU/commit/24d00430796e3dd09a31af6f91364056edda0137).
The [run for `3520f99a`, 45703875662](https://github.com/baabi-boo/CPU/actions/runs/45703875662)
also completed successfully, checked at 21:41 UTC on 2026-11-25. These remote
results apply to their named commits.
The fortify-repair hash above is also historical: the later descriptor-only
cleanup changes the recorder again, without changing experiment 14's retained
inputs or results.

The integrating agent also observed the source-complete published commit
[0e4711713ca82da8d55ee03f742a91d6f5db116e](https://github.com/baabi-boo/CPU/commit/0e4711713ca82da8d55ee03f742a91d6f5db116e)
complete successfully in
[GitHub Actions run 45706964047](https://github.com/baabi-boo/CPU/actions/runs/45706964047),
checked at **21:50 UTC on 2026-11-25**. This remote result applies to that exact
published source commit, alongside the separate local 836-test checkpoint.
Subsequent documentation-only commits require their own validation; no later
remote result is asserted here.

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

## Historical evidence retention

The earlier `htif-native-2026-11-25` compact directory contains 55 files totaling
237,313 bytes: selected
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
