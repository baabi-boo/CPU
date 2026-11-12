"""Offline target-source contracts; not RISC-V compilation or CPU execution."""

from pathlib import Path
import re
import shutil
import struct
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "software/nova/baseline"
PASS_LINE = "NOVA_BASELINE_V1 PASS hart=0 checks=8"
FAIL_LINE = "NOVA_BASELINE_V1 EXPECTED_FAIL hart=0 code=7"


class TargetContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (TARGET / "baseline.c").read_text(encoding="utf-8")
        cls.cmake = (TARGET / "CMakeLists.txt").read_text(encoding="utf-8")
        cls.readme = (TARGET / "README.md").read_text(encoding="utf-8")

    def test_target_only_guard_and_unsigned_abi_are_explicit(self):
        self.assertIn("__riscv_xlen != 64", self.source)
        self.assertIn('#error "NOVA baseline requires an RV64 target compiler"', self.source)
        self.assertIn('sizeof(uint64_t) == 8', self.source)
        self.assertIn('sizeof(unsigned long) == 8', self.source)

    def test_hart_identity_is_read_before_expected_hart_is_printed(self):
        self.assertIn('"csrr %0, mhartid"', self.source)
        self.assertIn("REQUIRE(1, hart, UINT64_C(0))", self.source)
        self.assertLess(self.source.index("REQUIRE(1, hart"), self.source.index(PASS_LINE))

    def test_exactly_eight_numbered_checks_match_terminal_protocol(self):
        ids = re.findall(r"(?m)^    REQUIRE\((\d+),", self.source)
        self.assertEqual(ids, [str(number) for number in range(1, 9)])
        self.assertIn("#define NOVA_BASELINE_CHECKS 8U", self.source)
        self.assertIn("if (checks != NOVA_BASELINE_CHECKS)", self.source)
        self.assertEqual(self.source.count(PASS_LINE), 1)
        self.assertIn(PASS_LINE, self.readme)

    def test_positive_and_negative_terminal_paths_are_separate(self):
        terminal = self.source.split("#if NOVA_EXPECTED_FAILURE", 2)[-1]
        negative, positive = terminal.split("#else", 1)
        self.assertIn(FAIL_LINE, negative)
        self.assertIn("return 7;", negative)
        self.assertNotIn(PASS_LINE, negative)
        self.assertIn(PASS_LINE, positive)
        self.assertIn("return 0;", positive)
        self.assertNotIn(FAIL_LINE, positive)
        self.assertLess(self.source.index("REQUIRE(8,"), self.source.index(FAIL_LINE))

    def test_inline_instruction_checks_cannot_be_only_constant_c_expressions(self):
        for instruction in ("add", "sub", "srl", "mul"):
            self.assertIn(f'RV_BINARY_FUNCTION(rv_{instruction}, "{instruction}")', self.source)
        self.assertIn('"bne %1, %2, 1f', self.source)
        self.assertIn('"sd %2, 0(%1)', self.source)
        self.assertIn('"ld %0, 0(%1)', self.source)
        self.assertIn('"=&r" (value)', self.source)
        self.assertIn('"memory"', self.source)

    def test_memory_checksum_constant_matches_bounded_unsigned_reference(self):
        words = [0x0102030405060708 ^ index for index in range(8)]
        self.assertEqual(sum(words) & ((1 << 64) - 1), 0x081018202830385C)
        self.assertIn("#define NOVA_MEMORY_WORDS 8U", self.source)
        self.assertIn("static volatile uint64_t memory_words[NOVA_MEMORY_WORDS]", self.source)
        self.assertEqual(self.source.count("index < NOVA_MEMORY_WORDS"), 2)
        self.assertIn("UINT64_C(0x081018202830385c)", self.source)

    def test_cmake_selects_cross_compiler_before_project(self):
        project_at = self.cmake.index("project(nova-baseline-workloads")
        for setting in ("set(CMAKE_SYSTEM_NAME Generic)",
                        "set(CMAKE_SYSTEM_PROCESSOR riscv64)",
                        "set(CMAKE_C_COMPILER riscv64-unknown-elf-gcc",
                        "set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)"):
            self.assertLess(self.cmake.index(setting), project_at)
        self.assertIn("host fallback is forbidden", self.cmake)
        self.assertIn("-dumpmachine", self.cmake)

    def test_cmake_keeps_runtime_inputs_absolute_and_uses_pinned_workaround(self):
        self.assertIn('"${NOVA_REPO_ROOT}/tests/htif.ld"', self.cmake)
        self.assertIn('"${NOVA_REPO_ROOT}/tests/atexit-workaround.c"', self.cmake)
        self.assertIn("-print-file-name=htif_nano.specs", self.cmake)
        self.assertIn('"-T${NOVA_LINKER_SCRIPT}"', self.cmake)
        self.assertIn("-Wl,--wrap=atexit", self.cmake)
        self.assertIn('LINK_DEPENDS "${NOVA_LINKER_SCRIPT}"', self.cmake)

    def test_cmake_exposes_two_explicit_cross_target_variants(self):
        self.assertIn("nova_add_baseline(nova-baseline 0)", self.cmake)
        self.assertIn("nova_add_baseline(nova-baseline-fail 1)", self.cmake)
        self.assertIn('SUFFIX ".riscv"', self.cmake)
        self.assertIn("NOVA_EXPECTED_FAILURE=${expected_failure}", self.cmake)
        self.assertIn("-march=rv64imafd_zicsr_zifencei -mabi=lp64d", self.cmake)

    def test_documentation_does_not_claim_target_execution(self):
        self.assertIn("unexecuted RV64 target programs", self.readme)
        self.assertIn("not observed processor-test", self.readme)
        self.assertIn("not a full RV64I/M", self.readme)
        self.assertIn("Reading hart 0 does not prove", self.readme)
        self.assertIn("not commands observed to succeed here", self.readme)

    @unittest.skipUnless(shutil.which("gcc") and struct.calcsize("L") == 8,
                         "optional host-only GCC syntax check requires 64-bit unsigned long")
    def test_host_frontend_syntax_only_for_both_target_variants(self):
        # -fsyntax-only does not assemble the RISC-V inline instructions. The
        # architecture defines merely let the host frontend parse the C body;
        # this is explicitly not a cross-compilation or a target execution.
        for variant in (0, 1):
            with self.subTest(variant=variant):
                result = subprocess.run(
                    [shutil.which("gcc"), "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                     "-fsyntax-only", "-D__riscv=1", "-D__riscv_xlen=64",
                     f"-DNOVA_EXPECTED_FAILURE={variant}", str(TARGET / "baseline.c")],
                    cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True,
                    text=True, check=False, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("gcc"), "optional compiler-guard test needs GCC")
    def test_host_compiler_without_target_defines_is_rejected(self):
        result = subprocess.run(
            [shutil.which("gcc"), "-std=gnu11", "-fsyntax-only", "-U__riscv",
             "-U__riscv_xlen", str(TARGET / "baseline.c")],
            cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, check=False, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NOVA baseline requires an RV64 target compiler", result.stderr)


if __name__ == "__main__":
    unittest.main()
