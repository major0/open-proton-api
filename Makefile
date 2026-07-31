.PHONY: all fetch extract compact render validate report clean help

PYTHON ?= python3

all: validate report

help:
	@echo "Targets:"
	@echo "  fetch    - Clone/update source repositories into sources/"
	@echo "  extract  - Run all extractors (emits per-source JSON into api/)"
	@echo "  compact  - Compute common.json and reduce source files to deltas"
	@echo "  render   - Produce OpenAPI 3.1 specs in output/"
	@echo "  validate - Validate all api/ JSON and rendered specs"
	@echo "  report   - Generate provenance and gap analysis reports"
	@echo "  all      - Full pipeline (fetch → extract → compact → render → validate → report)"
	@echo "  clean    - Remove generated output and provenance files"

# --- Fetch ---
fetch:
	scripts/fetch-sources.sh

# --- Extract (independent per source, parallelizable with -j) ---
extract: fetch
	$(PYTHON) -m src.extractors.protondrive_sdk_ts
	$(PYTHON) -m src.extractors.webclient
	$(PYTHON) -m src.extractors.protondrive_sdk_cs
	$(PYTHON) -m src.extractors.protondrive_sdk_kt
	$(PYTHON) -m src.extractors.protondrive_sdk_swift
	$(PYTHON) -m src.extractors.go_proton_api
	$(PYTHON) -m src.extractors.proton_bridge

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
	$(PYTHON) -m src.compactor

# --- Render ---
render: compact
	$(PYTHON) -m src.renderer

# --- Validate ---
validate: render
	$(PYTHON) -m src.validator

# --- Report ---
report: compact
	$(PYTHON) -m src.report

# --- Clean ---
clean:
	rm -rf output/*
	rm -rf provenance/*
	find api -name "common.json" -delete
	find api -name "meta.json" -delete
