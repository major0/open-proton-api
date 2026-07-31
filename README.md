# open-proton-api

Proton API specification compiler. Extracts, compiles, and renders the complete
Proton API surface from all available SDKs and clients into a canonical OpenAPI
3.1 specification.

## Overview

Proton publishes multiple SDK implementations (TypeScript, C#, Kotlin, Swift,
Go) that each expose different subsets of the API with varying levels of
completeness. This project:

1. Crawls all available sources using per-source Python extractors
2. Emits normalized endpoint definitions into a directory tree (`api/`)
3. Computes consensus (what all sources agree on) via a compaction pass
4. Renders the result as a publishable OpenAPI 3.1 specification

## Directory Structure

```
api/                   Canonical API tree (directory-as-namespace)
schema/                JSON Schema for the endpoint definition format
src/                   Python source (extractors, compactor, renderer)
scripts/               Shell scripts for source fetching
sources/               Cloned source repos (gitignored)
output/                Rendered OpenAPI specs
provenance/            Generated provenance and gap reports
tests/                 Test suite
```

## Pipeline

```
make fetch     → clone/update source repos
make extract   → run all extractors (per-source JSON into api/)
make compact   → compute common.json, reduce sources to deltas
make render    → produce OpenAPI 3.1 specs
make validate  → validate all intermediate and final output
make report    → generate provenance/gap analysis
make all       → full pipeline
```

## Endpoint Definition Format

Each endpoint is a directory under `api/` mirroring the REST path. Within each
directory, one JSON file per source contains that source's view of the endpoint:

```
api/drive/shares/{shareID}/files/{linkID}/revisions/
├── common.json              (computed by compactor)
├── protondrive-sdk-ts.json  (from TypeScript SDK extractor)
├── webclient.json           (from WebClients extractor)
└── meta.json                (provenance metadata)
```

All JSON files conform to `schema/endpoint.json`. See that file for the full
format specification.

## Adding a New Extractor

1. Create `src/extractors/your_source.py` with a `main()` function
2. Parse your source and emit one JSON file per endpoint into `api/`
3. Validate output against `schema/endpoint.json`
4. Add the entry point to `pyproject.toml` under `[project.scripts]`
5. Add the make target to `Makefile`

## Setup

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
make all
```

## Services Covered

- Drive (file storage, shares, links, revisions, blocks, photos, albums)
- Core (auth, users, addresses, keys, sessions, settings)
- Mail (messages, conversations, attachments, labels, filters)
- Calendar (events, calendars, attendees, alarms)
- Meet (meetings, participants, access tokens)
- Docs (documents, collaboration)
- Lumo (waitlist, invitations)
- VPN (connections, servers, settings)
