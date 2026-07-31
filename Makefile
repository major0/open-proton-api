.PHONY: all fetch extract compact render validate report clean distclean help

VENV := .venv
PYTHON := $(VENV)/bin/python

all: validate

help:
	@echo "Targets:"
	@echo "  setup    - Create virtualenv and install dependencies"
	@echo "  fetch    - Clone/update source repositories into sources/"
	@echo "  extract  - Run all implemented extractors (emits per-source JSON into api/)"
	@echo "  compact  - Compute common.json and reduce source files to deltas"
	@echo "  render   - Produce OpenAPI 3.1 specs in output/"
	@echo "  validate - Validate all api/ JSON and rendered specs"
	@echo "  report   - Generate provenance and gap analysis reports"
	@echo "  all      - Full pipeline (fetch → extract → compact → render → validate)"
	@echo "  clean    - Remove generated output and provenance files"
	@echo "  distclean - clean + remove sources and venv"

# --- Setup (create venv if missing) ---
$(VENV)/bin/python:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -e ".[dev]"
	$(VENV)/bin/pre-commit install
	$(VENV)/bin/pre-commit install --hook-type commit-msg

# --- Fetch ---
fetch:
	scripts/fetch-sources.sh

# --- Extract (independent per source, parallelizable with -j) ---
# Extractors that have been implemented (add modules here as they are built)
EXTRACTORS :=

extract: fetch $(VENV)/bin/python
	@for mod in $(EXTRACTORS); do \
		echo "Running extractor: $${mod}"; \
		$(PYTHON) -m "src.extractors.$${mod}" || exit 1; \
	done
	@if test -z "$(EXTRACTORS)"; then \
		echo "No extractors implemented yet — skipping extract."; \
	fi

# Individual extractor targets for incremental use
extract-protondrive-sdk-ts: fetch
	$(PYTHON) -m src.extractors.protondrive_sdk_ts

extract-webclient: fetch
	$(PYTHON) -m src.extractors.webclient

extract-protondrive-sdk-cs: fetch
	$(PYTHON) -m src.extractors.protondrive_sdk_cs

extract-protondrive-sdk-kt: fetch
	$(PYTHON) -m src.extractors.protondrive_sdk_kt

extract-protondrive-sdk-swift: fetch
	$(PYTHON) -m src.extractors.protondrive_sdk_swift

extract-go-proton-api: fetch
	$(PYTHON) -m src.extractors.go_proton_api

extract-proton-bridge: fetch
	$(PYTHON) -m src.extractors.proton_bridge

# --- Compact ---
compact: extract
	@echo "Compactor not yet implemented — skipping."

# --- Render ---
render: compact
	@echo "Renderer not yet implemented — skipping."

# --- Validate ---
validate: render $(VENV)/bin/python
	$(PYTHON) -m src.validator

# --- Report ---
report: compact
	@echo "Report not yet implemented — skipping."

# --- Clean ---
clean:
	rm -rf output/*
	rm -rf provenance/*
	find api -name "common.json" -delete
	find api -name "meta.json" -delete

# --- Distclean (clean + remove fetched sources and venv) ---
distclean: clean
	rm -rf sources
	rm -rf .venv
