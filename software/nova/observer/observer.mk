# Optional NOVA observer; load AFTER sims/verilator/Makefile with a second -f.
# Upstream sources and libraries are never changed. The complete htif.cc user
# object is linked by Verilator before its LDLIBS, so original htif.o need not be
# extracted from the explicit ordinary static FESVR archive.

ifeq ($(strip $(base_dir)),)
$(error NOVA observer requires the upstream Verilator Makefile first)
endif
ifeq ($(strip $(model_mk) $(model_mk_debug) $(sim) $(sim_debug)),)
$(error NOVA observer requires upstream Verilator build targets)
endif

NOVA_HTIF_OBSERVER_DIR ?= $(base_dir)/nova-out/htif-observer
nova_htif_source_dir := $(base_dir)/toolchains/riscv-tools/riscv-isa-sim
nova_htif_native_dir := $(base_dir)/software/nova/observer
nova_htif_make_fragment := $(lastword $(MAKEFILE_LIST))
nova_htif_shell_quote = '$(subst ','"'"',$(1))'

# Refuse hidden FESVR fallbacks in the preserved extension points.
ifneq ($(findstring fesvr,$(LDFLAGS) $(EXTRA_SIM_LDFLAGS) $(LRISCV)),)
$(error NOVA observer disallows an additional FESVR link specification)
endif
ifneq ($(filter command% environment% override,$(origin EXTRA_SIM_SOURCES) $(origin EXTRA_SIM_CXXFLAGS)),)
$(error NOVA observer requires makefile-owned extra simulator sources and flags)
endif

EXTRA_SIM_SOURCES += \
	$(NOVA_HTIF_OBSERVER_DIR)/htif.cc \
	$(nova_htif_native_dir)/nova_htif_exit.cc

# The final escaped quotes survive both Verilator's -CFLAGS shell argument and
# the generated native makefile. PREFIX is used by pinned htif.cc's payload path.
EXTRA_SIM_CXXFLAGS += \
	-iquote $(nova_htif_source_dir)/fesvr \
	-iquote $(nova_htif_source_dir)/riscv \
	-iquote $(nova_htif_source_dir)/softfloat \
	-iquote $(RISCV)/include/fesvr \
	-iquote $(nova_htif_native_dir) \
	-DPREFIX=\\\"$(RISCV)\\\"

# Keep the original sims/common-sim-flags.mk expression and ordering, replacing
# only -lfesvr with the exact static archive; never permit .so search fallback.
override SIM_LDFLAGS = \
	$(LDFLAGS) \
	-L$(RISCV)/lib \
	-Wl,-rpath,$(RISCV)/lib \
	-L$(sim_dir) \
	-L$(dramsim_dir) \
	$(LRISCV) \
	$(RISCV)/lib/libfesvr.a \
	-ldramsim \
	$(EXTRA_SIM_LDFLAGS)

.PHONY: nova-htif-observer-check
nova-htif-observer-check:
	python3 -B $(call nova_htif_shell_quote,$(base_dir)/scripts/nova/htif_observer.py) --verify --root $(call nova_htif_shell_quote,$(base_dir)) --output $(call nova_htif_shell_quote,$(NOVA_HTIF_OBSERVER_DIR)) > /dev/null

# Earlier prerequisite expansions in the upstream Makefile have already run.
# Add these explicitly, and verify even when generated simulator targets exist.
$(model_mk) $(model_mk_debug): $(NOVA_HTIF_OBSERVER_DIR)/htif.cc $(NOVA_HTIF_OBSERVER_DIR)/manifest.json $(nova_htif_native_dir)/nova_htif_exit.cc $(nova_htif_native_dir)/nova_htif_exit.h $(nova_htif_make_fragment)
$(model_mk) $(model_mk_debug) $(sim) $(sim_debug): | nova-htif-observer-check
