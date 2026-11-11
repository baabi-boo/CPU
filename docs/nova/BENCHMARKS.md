# Benchmark and measurement protocol

This is a methodology for future experiments. It contains no NOVA performance,
power, efficiency, or Apple-comparison results. See [STATUS](STATUS.md),
[VERIFICATION](VERIFICATION.md), and [REPRODUCIBILITY](REPRODUCIBILITY.md).

## State the question before running

Each experiment needs a falsifiable hypothesis, requirement/test IDs, baseline,
candidate, workload set, correctness oracle, measurement window, resource budget,
timeout policy, and acceptance/rollback criteria. Declare exclusions and sampling
rules before observing results. Preserve negative results and regressions.

For CPU-only architecture changes, use the same workload binary and input hashes,
ISA/ABI, compiler flags, firmware, operating-system configuration, and measurement
boundaries. Hold the memory system/model and clock assumptions constant unless
one is the declared experimental variable. Record exact source and dependency
revisions, tool versions, generated configuration, and dirty-source identity.

If compiler, runtime, algorithm, or memory changes are intentional, label the
comparison a system-level experiment and identify every changed dimension. Do
not attribute its entire gain to a CPU feature. Use an unchanged control profile
to detect unrelated toolchain or environment drift.

## Memory and clock model

The pinned `AbstractConfig` selects `WithBlackBoxSimMem` / SimDRAM. Record the
actual elaborated model, configuration, memory timing, channels, cache sizes,
banking, line sizes, and warm-state policy for every run. Do not substitute older
prose describing single-cycle `SimAXIMem` for the selected source. A model change
starts a new comparison series unless separately controlled and explained.

Target execution cycles and host simulator elapsed time are different metrics.
Host runtime measures simulation cost, not processor speed. Report the relevant
clock domain for cycle counters; for multiple domains, retain clock ratios and
the defined target-time conversion. Configured frequencies are model inputs,
not timing-closed FPGA or ASIC frequencies. Do not derive physical throughput
from a nominal frequency without corresponding implementation evidence.

## Correctness and measurement windows

1. Validate output against a declared oracle before accepting a performance
   sample. Numerical tolerances, quantization, rounding, and overflow behavior
   must be explicit; a faster incorrect answer is not a successful result.
2. Define start/stop points, initialization, allocation, transfers, synchronization,
   completion visibility, and cleanup. Record which are included or excluded.
3. Separate cold-start from steady-state runs. Document reset, cache/TLB state,
   allocator state, warm-up iterations, and background activity. Never combine
   differently warmed results into a single unexplained score.
4. Validate counters with small known workloads. Record widths, overflow,
   privilege filters, interrupt effects, retired-instruction definitions, and
   per-hart attribution. A counter name alone is not an audited measurement.
5. Preserve all attempted samples, seeds, failures, and timeouts. A timeout is a
   censored/failing run, not a missing fast sample. Investigate before changing
   limits; retain both the original and revised experiment definitions.

## Subsystem comparisons

| Study | Controlled comparison | Required accounting / tests |
| --- | --- | --- |
| CPU architecture | Same binary/inputs; one declared design change | Per-hart correctness, cycles, retired instructions, IPC where meaningful, branch/cache/stall events (`T-CPU-PERF-001`, `T-ISA-001`) |
| Multicore scaling | Same problem, explicit thread count and affinity; fixed or disclosed memory resources | Total completion, per-hart work, synchronization/serial fractions, fairness and contention (`T-HART-001`, `T-COH-001`, `T-ORDER-001`) |
| NPU versus CPU | Same operation, inputs, precision, and correctness tolerance; record each implementation/binary | Command/setup, layout conversion, data movement, kernel, synchronization, fallback and end-to-end time (`T-NPU-NUM-001`, `T-NPU-MEM-001`) |
| GPU versus CPU | Same algorithmic workload and numerical contract; record each implementation/binary | Driver/runtime overhead, transfers, launch, completion, kernel and end-to-end results; API scope explicit (`T-GPU-EXEC-001`, `T-DMA-001`) |
| Memory | Declared access pattern, working-set size, concurrency, cache state and model | Latency distribution, delivered bandwidth, contention, faults, ownership transitions; not silicon bandwidth from simulation (`T-COH-001`, `T-DMA-001`) |

Accelerated and scalar versions necessarily use different execution paths; retain
both sources/binaries and compare equivalent work, not nominal operation counts
with different precision. Kernel-only speedup must not be labeled application
speedup. Include integration overhead and publish cases where offloading loses.

## Reporting and statistics

Report the complete workload set and sample count, raw samples, seeds, median,
spread, and other justified summaries. State whether a run is deterministic;
repeatability is not the same as coverage of different inputs. Use percentiles or
confidence intervals only with an adequate sample design and stated method.
Explain aggregation and weighting; do not select only favorable workloads.

Speedup must identify its denominator and matching metric. Compare target cycles
only under compatible clock definitions; report absolute baseline and candidate
values alongside ratios. Preserve correctness results, regressions, omitted
features, saturation points, and uncertainty. A benchmark badge is not a gate.

## Area, power, and efficiency

Follow [POWER_PHYSICAL](POWER_PHYSICAL.md) for measurement classes. Compare ASIC
area estimates using the same technology, libraries, constraints, and flow.
Record timing feasibility and storage/macro assumptions. FPGA utilization is a
different metric from ASIC area.

For energy, define the rail/system boundary, instrument or estimation model,
voltage, temperature, activity coverage, idle baseline, sampling, duration, and
uncertainty. Report energy per correctly completed workload and throughput with
matching boundaries. Do not mix FPGA watts with simulated ASIC throughput or
omit host/transfer costs silently. `T-POWER-001` is required for any power claim.

BOOM/Rocket P/E roles remain hypotheses until measured trade-offs support them.
No score here establishes Apple performance parity. The resulting evidence for
`REQ-CPU-004` must include artifacts, limitations, and review—not just a favorable
ratio. Update project status only for the exact demonstrated evidence level.
