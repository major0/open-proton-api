.PHONY: all fetch extract compact render validate lint report release clean distclean help

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
fetch: $(VENV)/bin/python
	scripts/fetch-sources.sh

# --- Extract (independent per source, parallelizable with -j) ---
extract: fetch $(VENV)/bin/python
	@for mod in $$($(PYTHON) -m src.config extractors); do \
		echo "Running extractor: $${mod}"; \
		$(PYTHON) -m "src.extractors.$${mod}" || exit 1; \
	done

# Individual extractor targets for manual/incremental use
extract-%: fetch $(VENV)/bin/python
	$(PYTHON) -m src.extractors.$*

# --- Compact ---
compact: extract
	$(PYTHON) -m src.compactor

# --- Render ---
render: compact
	$(PYTHON) -m src.renderer

# --- Validate ---
validate: render $(VENV)/bin/python
	$(PYTHON) -m src.validator
	$(PYTHON) -m src.lint

# --- Report ---
report: compact
	@echo "Report not yet implemented — skipping."

# --- Release ---
release: validate
	gh release create "v$$(date -u +%Y%m%d)01" output/proton-*-api-*.json \
		--title "v$$(date -u +%Y%m%d)01" \
		--notes "Proton API specs compiled from official SDKs. Run: $$(date -u +%Y-%m-%d)"

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
