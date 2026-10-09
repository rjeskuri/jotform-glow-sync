# The feedback loop. `make check` runs everything offline, needs no
# credentials, and exits non-zero on the first failure. Run it before saying
# a change is done (CLAUDE.md), and paste the tail of its output.
#
# Compatible with the make 3.81 that ships with macOS (tabs, no .ONESHELL).
SHELL := /bin/bash
PYTHON := $(shell test -x .venv/bin/python3 && echo .venv/bin/python3 || echo python3)
RUFF := $(shell test -x .venv/bin/ruff && echo .venv/bin/ruff || command -v ruff)

.PHONY: check test py gs secrets docs-links fixtures fixtures-check lint venv help

check: lint test py gs secrets docs-links fixtures-check   ## everything, offline, no credentials
	@echo "CHECK PASSED"

test:                                                 ## JS tests (test/*_test.js): synthetic fixture always, real data when data/ has it
	@for f in test/*_test.js; do echo "node $$f"; node $$f || exit 1; done

py:                                                   ## every .py parses, every script answers --help, Python unit tests (test/*_test.py)
	$(PYTHON) scripts/check_py.py
	$(PYTHON) -m unittest discover -s test -p '*_test.py'

gs:                                                   ## every Apps Script file parses (guards clasp push)
	node scripts/check_gs.js

secrets:                                              ## no keys, PII or real ids in tracked files
	$(PYTHON) scripts/check_secrets.py

docs-links:                                           ## no dead absolute paths; every relative markdown link resolves
	$(PYTHON) scripts/check_docs_links.py

fixtures:                                             ## regenerate test/fixtures/{enrollment_sample.csv,expected.json}
	$(PYTHON) test/fixtures/make_fixture.py --write

fixtures-check:                                       ## the committed fixture equals a fresh generation
	$(PYTHON) test/fixtures/make_fixture.py --check

lint:                                                 ## ruff (ruff.toml): fails on any finding
	@test -n "$(RUFF)" || { echo "ruff not installed: make venv"; exit 1; }
	$(RUFF) check . && echo "lint: ok"

venv:                                                 ## create .venv with runtime + dev dependencies
	python3 -m venv .venv && .venv/bin/python3 -m pip install --quiet --upgrade pip \
	  && .venv/bin/python3 -m pip install --quiet -r requirements-dev.txt \
	  && echo "ok: .venv ready ($$(.venv/bin/python3 --version))"

help:                                                 ## this list
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed -E 's/:[^#]*##/  -/'
