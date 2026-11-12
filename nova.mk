# NOVA repository checks only. Hardware builds remain explicit and separate.
.DEFAULT_GOAL := help
PYTHON ?= python3
DOCTOR_FLAGS ?=

.PHONY: help check validate test whitespace doctor doctor-strict preflight preflight-strict rocket-plan g1-plan g1-campaign-plan g1-profile g1-profile-strict conda-plan

help:
	@printf '%s\n' \
	  'NOVA-M1 project tooling (run from the repository root)' \
	  '  make -f nova.mk check          Metadata, links, provenance, unit tests, whitespace' \
	  '  make -f nova.mk validate       Project validator only' \
	  '  make -f nova.mk test           Python tooling tests; empty discovery fails' \
	  '  make -f nova.mk doctor         Non-mutating environment diagnosis' \
	  '  make -f nova.mk doctor-strict  Diagnose and fail on missing prerequisites' \
	  '  make -f nova.mk preflight      Non-mutating NOVA-001 setup/lock safety report' \
	  '  make -f nova.mk preflight-strict  Report and fail on unsafe setup prerequisites' \
	  '  make -f nova.mk rocket-plan    Read-only plan for bounded Rocket simulation' \
	  '  make -f nova.mk g1-plan        Read-only two-profile workload campaign plan' \
	  '  make -f nova.mk g1-campaign-plan  Read-only bounded runner plan and limitations' \
	  '  make -f nova.mk g1-profile     Diagnose the fixed Chisel-6 baseline profile' \
	  '  make -f nova.mk g1-profile-strict  Fail on missing known profile prerequisites' \
	  '  make -f nova.mk conda-plan     Inspect the unchanged pinned package inventory' \
	  'These targets do not install dependencies, build RTL, or qualify hardware.'

check: validate test whitespace

validate:
	$(PYTHON) -B scripts/nova/check.py

test:
	$(PYTHON) -B scripts/nova/run_tests.py

whitespace:
	$(PYTHON) -B scripts/nova/check_whitespace.py
	git diff --check

doctor:
	$(PYTHON) -B scripts/nova/doctor.py $(DOCTOR_FLAGS)

doctor-strict:
	$(PYTHON) -B scripts/nova/doctor.py --strict

preflight:
	$(PYTHON) -B scripts/nova/bootstrap_preflight.py

preflight-strict:
	$(PYTHON) -B scripts/nova/bootstrap_preflight.py --strict

rocket-plan:
	$(PYTHON) -B scripts/nova/rocket_baseline.py --plan

g1-plan:
	$(PYTHON) -B scripts/nova/campaign_plan.py

g1-campaign-plan:
	$(PYTHON) -B scripts/nova/g1_campaign.py --plan

g1-profile:
	$(PYTHON) -B scripts/nova/g1_profile.py

g1-profile-strict:
	$(PYTHON) -B scripts/nova/g1_profile.py --strict

conda-plan:
	$(PYTHON) -B scripts/nova/conda_inventory.py
