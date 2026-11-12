# NOVA single-hart target smoke workloads

These are **unexecuted RV64 target programs**, not observed processor-test
results. Their source-contract and host C syntax checks validate only source
structure; they do not compile RISC-V instructions, execute RTL, or close G1.

The isolated build does not modify the inherited `tests/CMakeLists.txt`.
It selects an RV64 bare-metal compiler before CMake's `project()` call and
uses the pinned HTIF nano specs, the repository's `tests/htif.ld` link to
libgloss, and its existing `atexit` workaround. Toolchain preparation and
provenance validation remain mandatory prerequisites.

## Exact target protocol

`nova-baseline.riscv` performs eight deterministic checks:

1. Read `mhartid` at runtime and require hart 0.
2. Exercise unsigned 64-bit addition wrapping to one.
3. Exercise unsigned 64-bit subtraction wrapping to all ones.
4. Logically right-shift a high bit to bit zero.
5. Multiply two fixed operands using the M-extension instruction.
6. Exercise equal and unequal inputs through an explicit conditional branch.
7. Round-trip a fixed 64-bit value through aligned `sd` and `ld` instructions.
8. Write and sum eight volatile words with a fixed expected checksum.

The instruction checks use explicit inline assembly so constant folding cannot
replace them with precomputed C results. C arithmetic is unsigned, shifts are
bounded, and the memory loop accesses only its eight-element array. This is
narrow smoke coverage, not a full RV64I/M or architectural-compliance claim.
It does not test other harts, interrupts, privilege transitions, traps, atomics,
memory ordering/coherence, MMU behavior, F/D arithmetic, or compressed opcodes.
Reading hart 0 does not prove that the generated machine has exactly one hart.

On success, the positive workload emits exactly this terminal line, flushes
stdout, and returns zero through the target runtime:

```text
NOVA_BASELINE_V1 PASS hart=0 checks=8
```

`nova-baseline-fail.riscv` first performs the same checks. Only if they all
succeed does it emit the following line, flush stdout, and intentionally
return **7** through HTIF:

```text
NOVA_BASELINE_V1 EXPECTED_FAIL hart=0 code=7
```

A real check mismatch prints a `NOVA_BASELINE_V1 FAIL` record and returns a
nonzero check ID. An output error also returns nonzero. Neither error path
prints the positive completion marker. The negative workload is an expected
failure control, never a passing CPU test in isolation.

The execution harness must retain and verify the distinct simulator/HTIF
completion result, exact target output, process status, binary hashes, and
complete bounded logs. A printed marker alone is not evidence of completion.
See the [baseline runbook](../../../docs/nova/BASELINE_RUNBOOK.md).

## Prepared-environment build entry point

After the approved pinned toolchain and required submodules are prepared, from
the repository root:

```bash
cmake -S software/nova/baseline -B software/nova/baseline/build
cmake --build software/nova/baseline/build \
  --target nova-baseline nova-baseline-fail --parallel 2
```

The output files are `software/nova/baseline/build/nova-baseline.riscv` and
`software/nova/baseline/build/nova-baseline-fail.riscv`. Apply the separately
approved wall-time, memory, and disk limits when running these commands.
They are inspected entry points, **not commands observed to succeed here**.
The selected build ISA is `rv64imafd_zicsr_zifencei` with `lp64d` ABI; that
build/runtime contract does not imply the workload tests every enabled extension.
