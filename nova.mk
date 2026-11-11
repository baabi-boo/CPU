# NOVA repository checks only. Hardware builds remain explicit and separate.
.DEFAULT_GOAL := help
PYTHON ?= python3
DOCTOR_FLAGS ?=

.PHONY: help check validate test whitespace doctor doctor-strict

help:
	@printf '%s\n' \
	  'NOVA-M1 project tooling (run from the repository root)' \
	  '  make -f nova.mk check          Metadata, links, provenance, unit tests, whitespace' \
	  '  make -f nova.mk validate       Project validator only' \
	  '  make -f nova.mk test           Python tooling tests; empty discovery fails' \
	  '  make -f nova.mk doctor         Non-mutating environment diagnosis' \
	  '  make -f nova.mk doctor-strict  Diagnose and fail on missing prerequisites' \
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
