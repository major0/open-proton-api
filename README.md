# open-proton-api

A compilation pipeline that reverse-engineers the complete Proton API surface
from all available official SDKs and clients, normalizes it to RESTful
conventions, and publishes it as OpenAPI 3.1 specifications.

## Problem

Proton maintains an internal OpenAPI specification that drives their official
SDKs (TypeScript, C#, Kotlin, Swift). The Go API client (`go-proton-api`) is
hand-maintained and perpetually out of date. No public, authoritative, complete
specification of the Proton API exists. Different clients expose different
subsets with different levels of completeness.

## Approach

This project treats each SDK/client as a "witness" of the API. A compilation
pipeline:

1. **Extracts** endpoint definitions from each source using per-source parsers
2. **Normalizes** all paths and parameters to RESTful naming conventions
3. **Compacts** by computing consensus (what all sources agree on) and
   identifying unique contributions from each source
4. **Renders** the result as valid OpenAPI 3.1 specifications
5. **Lints** for structural validity and convention compliance

The output is a set of versioned OpenAPI specs covering all Proton services.

## RESTful Normalization

All paths are normalized per [restfulapi.net](https://restfulapi.net/resource-naming/):

- Path segments: lowercase nouns with hyphens (`/drive/shares`, not `/Drive/Shares`)
- Path parameters: camelCase with `Id` suffix (`{shareId}`, not `{shareID}` or `{enc_shareID}`)
- No encoding prefixes, no trailing slashes
- Canonical operationIds generated from method + path (e.g., `GET /drive/shares/{shareId}` → `getShare`)

Different sources use different conventions (TypeScript SDK uses `{shareID}`,
WebClients use `{shareId}`, Android SDK uses `{enc_shareID}`). The
normalization layer maps all variants to a single canonical form.

## Sources

Active sources (contribute unique field-level data):

| Source | Language | Coverage | Unique Value |
|--------|----------|----------|--------------|
| protondrive-sdk (TypeScript) | TS (generated from internal OpenAPI) | Drive + Core | Deepest field detail, highest fidelity |
| WebClients | TS (hand-written) | All services | Broadest coverage: Mail, Calendar, Meet, VPN, Lumo |
| go-proton-api | Go | Drive + Mail | Sole source for some Mail operations |
| protoncore-android | Kotlin (Retrofit) | Core | Unique query params for auth/keys/payments |

Disabled sources (contribute no unique field-level info after compaction):

| Source | Reason |
|--------|--------|
| android-drive | 84% subsumed — only type-name references |
| ios-drive | 100% subsumed |
| ios-pass | 100% subsumed by android-pass |
| android-pass | Only extraction artifacts ($PREFIX) |
| android-mail | Uses compiled Rust SDK — no parseable endpoints |

Sources are managed via `sources.yaml`. Toggle `enabled: true/false` to
include or exclude any source.

## Pipeline

```
make fetch     → clone/update source repos (reads sources.yaml)
make extract   → run enabled extractors (per-source JSON into api/)
make compact   → compute common.json, reduce sources to deltas
make render    → produce OpenAPI 3.1 specs in output/
make lint      → structural validation + RESTful convention checks
make all       → full pipeline
make clean     → remove generated output
make distclean → clean + remove sources and venv
```

## Output

Rendered specs are published as versioned artifacts:

```
proton-drive-api-2025073101.json
proton-core-api-2025073101.json
proton-mail-api-2025073101.json
proton-full-api-2025073101.json
```

Version format: `YYYYMMDDNN` (date-based serial, NN is a sequence number for
multiple releases on the same day — same convention as DNS SOA serials).

Per-service specs:

| Spec | Paths | Description |
|------|-------|-------------|
| `proton-drive-api` | 160 | File storage, shares, links, revisions, blocks, photos |
| `proton-core-api` | 178 | Auth, users, addresses, keys, sessions, settings, organizations |
| `proton-mail-api` | 44 | Messages, conversations, attachments, labels, filters |
| `proton-calendar-api` | 13 | Events, calendars, attendees, alarms |
| `proton-meet-api` | 5 | Meetings, participants, access tokens |
| `proton-full-api` | 435 | All services combined (527 operations) |

## Directory Structure

```
src/                   Python source code
  extractors/          Per-source extraction modules
  pathutil.py          Path normalization (RESTful conventions)
  compactor.py         Consensus computation and delta reduction
  renderer.py          OpenAPI 3.1 assembly
  lint.py              Custom RESTful linter
  config.py            sources.yaml reader
  validator.py         Schema validation for intermediate files
schema/                JSON Schema for internal endpoint format
sources.yaml           Source registry (URLs, enabled flags, extractor mapping)
scripts/               Shell scripts for source fetching
api/                   Intermediate output — canonical API tree (gitignored)
output/                Rendered OpenAPI specs (gitignored)
provenance/            Compaction reports (gitignored)
sources/               Cloned source repos (gitignored)
```

## Adding a New Source

1. Add the repository to `sources.yaml` with `enabled: true`
2. Create `src/extractors/your_source.py` with a `main()` function
3. Use `src.pathutil.write_endpoint(path, operations, source_name)` for output
4. Add the extractor module name to the source's `extractors:` list in `sources.yaml`
5. Run `make all` — verify the source contributes unique field-level data after compaction
6. If it contributes nothing unique, set `enabled: false`

## Setup

```sh
git clone <this-repo> open-proton-api.git
cd open-proton-api.git
make all   # creates venv, fetches sources, runs full pipeline
```

The Makefile auto-creates the Python virtualenv and installs all dependencies
on first run.

## Linting

The custom linter (`src/lint.py`) checks:

- **Structural validity** — OpenAPI 3.1 schema compliance (hard fail)
- **Path segments lowercase** — warns on camelCase segments like `checkAvailableHashes`
- **Path parameters camelCase** — warns on `{share_id}` or `{ShareID}`
- **No verbs in paths** — warns on `add`, `update`, `check` segments (with exception list for known Proton RPC-style endpoints)
- **No trailing slashes**

Known Proton API quirks (RPC-style verb endpoints like `trash_multiple`,
`delete_multiple`, `forward`) are tracked in the exception list and suppressed.

## License

MIT
