/*
 * NOVA single-hart RV64 smoke workload. This is deliberately a small set of
 * deterministic checks, not an ISA-compliance, privilege, or memory-model suite.
 * The harness must independently verify simulator/HTIF completion after the
 * terminal record; printing the record alone is not execution evidence.
 */
#include <stdint.h>
#include <stdio.h>

#if !defined(__riscv) || !defined(__riscv_xlen) || __riscv_xlen != 64
#error "NOVA baseline requires an RV64 target compiler"
#endif

#ifndef NOVA_EXPECTED_FAILURE
#define NOVA_EXPECTED_FAILURE 0
#endif
#if NOVA_EXPECTED_FAILURE != 0 && NOVA_EXPECTED_FAILURE != 1
#error "NOVA_EXPECTED_FAILURE must be 0 or 1"
#endif

#define NOVA_BASELINE_CHECKS 8U
#define NOVA_MEMORY_WORDS 8U

_Static_assert(sizeof(uint64_t) == 8, "64-bit words are required");
_Static_assert(sizeof(unsigned long) == 8, "RV64 printf ABI is required");

static volatile uint64_t memory_words[NOVA_MEMORY_WORDS];

static uint64_t read_hart_id(void)
{
    uint64_t value;
    __asm__ volatile ("csrr %0, mhartid" : "=r" (value));
    return value;
}

#define RV_BINARY_FUNCTION(name, instruction) \
    static uint64_t name(uint64_t left, uint64_t right) \
    { \
        uint64_t value; \
        __asm__ volatile (instruction " %0, %1, %2" \
                          : "=r" (value) : "r" (left), "r" (right)); \
        return value; \
    }

RV_BINARY_FUNCTION(rv_add, "add")
RV_BINARY_FUNCTION(rv_sub, "sub")
RV_BINARY_FUNCTION(rv_srl, "srl")
RV_BINARY_FUNCTION(rv_mul, "mul")

static uint64_t branch_equal(uint64_t left, uint64_t right)
{
    uint64_t value;
    /* Early-clobber keeps the initialized result out of both input registers. */
    __asm__ volatile (
        "li %0, 0\n\t"
        "bne %1, %2, 1f\n\t"
        "li %0, 1\n"
        "1:"
        : "=&r" (value) : "r" (left), "r" (right));
    return value;
}

static uint64_t store_and_load(volatile uint64_t *address, uint64_t value)
{
    uint64_t observed;
    __asm__ volatile (
        "sd %2, 0(%1)\n\t"
        "ld %0, 0(%1)"
        : "=&r" (observed) : "r" (address), "r" (value) : "memory");
    return observed;
}

static uint64_t memory_checksum(void)
{
    uint64_t sum = 0;
    unsigned int index;
    for (index = 0; index < NOVA_MEMORY_WORDS; ++index) {
        memory_words[index] = UINT64_C(0x0102030405060708) ^ (uint64_t)index;
    }
    for (index = 0; index < NOVA_MEMORY_WORDS; ++index) {
        sum += memory_words[index];
    }
    return sum;
}

static int failed_check(uint64_t hart, unsigned int id,
                        uint64_t observed, uint64_t expected)
{
    (void)printf("NOVA_BASELINE_V1 FAIL hart=%lu check=%u observed=%016lx expected=%016lx\n",
                 (unsigned long)hart, id, (unsigned long)observed,
                 (unsigned long)expected);
    (void)fflush(stdout);
    return (int)id;
}

#define REQUIRE(id, expression, expected_value) \
    do { \
        const uint64_t observed = (expression); \
        const uint64_t expected = (expected_value); \
        if (observed != expected) { \
            return failed_check(hart, (id), observed, expected); \
        } \
        ++checks; \
    } while (0)

int main(void)
{
    const uint64_t hart = read_hart_id();
    unsigned int checks = 0;

    REQUIRE(1, hart, UINT64_C(0));
    REQUIRE(2, rv_add(UINT64_MAX, UINT64_C(2)), UINT64_C(1));
    REQUIRE(3, rv_sub(UINT64_C(0), UINT64_C(1)), UINT64_MAX);
    REQUIRE(4, rv_srl(UINT64_C(0x8000000000000000), UINT64_C(63)), UINT64_C(1));
    REQUIRE(5, rv_mul(UINT64_C(0xffffffff), UINT64_C(2)), UINT64_C(0x1fffffffe));
    REQUIRE(6, (branch_equal(UINT64_C(17), UINT64_C(17)) << 1)
               | branch_equal(UINT64_C(17), UINT64_C(18)), UINT64_C(2));
    REQUIRE(7, store_and_load(&memory_words[0], UINT64_C(0x0123456789abcdef)),
               UINT64_C(0x0123456789abcdef));
    REQUIRE(8, memory_checksum(), UINT64_C(0x081018202830385c));

    if (checks != NOVA_BASELINE_CHECKS) {
        return failed_check(hart, 9U, checks, NOVA_BASELINE_CHECKS);
    }

#if NOVA_EXPECTED_FAILURE
    /* Intentional HTIF failure control, only after the real checks above. */
    if (printf("NOVA_BASELINE_V1 EXPECTED_FAIL hart=0 code=7\n") < 0
            || fflush(stdout) != 0) {
        return 125;
    }
    return 7;
#else
    if (printf("NOVA_BASELINE_V1 PASS hart=0 checks=8\n") < 0
            || fflush(stdout) != 0) {
        return 125;
    }
    return 0;
#endif
}
