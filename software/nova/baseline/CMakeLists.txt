cmake_minimum_required(VERSION 3.13)

# Select the cross-compiler before project() performs compiler detection.
# An explicit compiler path is allowed so a reviewed pinned environment can be
# selected without falling back to whichever host compiler happens to be first.
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR riscv64)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
if(NOT DEFINED CMAKE_C_COMPILER)
    set(CMAKE_C_COMPILER riscv64-unknown-elf-gcc CACHE FILEPATH
        "Reviewed pinned RV64 bare-metal C compiler")
endif()

project(nova-baseline-workloads LANGUAGES C)

execute_process(
    COMMAND "${CMAKE_C_COMPILER}" -dumpmachine
    RESULT_VARIABLE NOVA_COMPILER_STATUS
    OUTPUT_VARIABLE NOVA_COMPILER_TARGET
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET
    TIMEOUT 10)
if(NOT NOVA_COMPILER_STATUS EQUAL 0
        OR NOT NOVA_COMPILER_TARGET MATCHES "^riscv64-.*-elf$")
    message(FATAL_ERROR "An RV64 bare-metal compiler is required; host fallback is forbidden")
endif()

get_filename_component(NOVA_REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
set(NOVA_LINKER_SCRIPT "${NOVA_REPO_ROOT}/tests/htif.ld")
set(NOVA_ATEXIT_WORKAROUND "${NOVA_REPO_ROOT}/tests/atexit-workaround.c")
foreach(required_input IN ITEMS "${NOVA_LINKER_SCRIPT}" "${NOVA_ATEXIT_WORKAROUND}")
    if(NOT EXISTS "${required_input}")
        message(FATAL_ERROR "Required pinned target runtime input is missing: ${required_input}")
    endif()
endforeach()

execute_process(
    COMMAND "${CMAKE_C_COMPILER}" -print-file-name=htif_nano.specs
    RESULT_VARIABLE NOVA_SPECS_STATUS
    OUTPUT_VARIABLE NOVA_HTIF_SPECS
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET
    TIMEOUT 10)
if(NOT NOVA_SPECS_STATUS EQUAL 0 OR NOT IS_ABSOLUTE "${NOVA_HTIF_SPECS}"
        OR NOT EXISTS "${NOVA_HTIF_SPECS}")
    message(FATAL_ERROR "The selected compiler must resolve the reviewed HTIF nano specs")
endif()

# The ABI/runtime may use F/D instructions; these smoke checks do not qualify
# F/D, atomics, compressed instructions, privilege transitions, or the MMU.
set(NOVA_ARCH_FLAGS -march=rv64imafd_zicsr_zifencei -mabi=lp64d -mcmodel=medany)

function(nova_add_baseline target expected_failure)
    add_executable(${target} baseline.c "${NOVA_ATEXIT_WORKAROUND}")
    set_target_properties(${target} PROPERTIES
        C_STANDARD 11
        C_STANDARD_REQUIRED YES
        C_EXTENSIONS YES
        SUFFIX ".riscv"
        LINK_DEPENDS "${NOVA_LINKER_SCRIPT}")
    target_compile_definitions(${target} PRIVATE NOVA_EXPECTED_FAILURE=${expected_failure})
    target_compile_options(${target} PRIVATE
        -O2 -Wall -Wextra -Werror -fno-common -fno-builtin-printf
        ${NOVA_ARCH_FLAGS} "-specs=${NOVA_HTIF_SPECS}")
    target_link_options(${target} PRIVATE
        ${NOVA_ARCH_FLAGS} -static "-specs=${NOVA_HTIF_SPECS}"
        "-T${NOVA_LINKER_SCRIPT}" -Wl,--wrap=atexit)
endfunction()

nova_add_baseline(nova-baseline 0)
nova_add_baseline(nova-baseline-fail 1)
