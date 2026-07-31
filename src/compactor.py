"""Compactor: compute common.json from per-source files, reduce sources to deltas.

For each endpoint directory with 2+ source files:
1. Load all source JSONs
2. Compute intersection (fields/operations in ALL sources) → common.json
3. Rewrite each source to contain only unique information (delta from common)
4. Delete source files that become empty
5. Write meta.json with provenance data
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
API_DIR = PROJECT_ROOT / "api"
PROVENANCE_DIR = PROJECT_ROOT / "provenance"

SKIP_FILES = {"common.json", "meta.json"}


def load_endpoint_sources(endpoint_dir: Path) -> dict[str, dict]:
    """Load all source JSON files from an endpoint directory."""
    sources = {}
    for f in sorted(endpoint_dir.glob("*.json")):
        if f.name in SKIP_FILES:
            continue
        source_name = f.stem
        with open(f) as fh:
            sources[source_name] = json.load(fh)
    return sources


def intersect_operations(sources: dict[str, dict]) -> dict[str, dict]:
    """Compute the intersection of operations across all sources.

    An operation is "common" if it exists in ALL sources.
    Within a common operation, a field is common if present in all sources
    that have that operation.
    """
    if not sources:
        return {}

    # Find operations present in ALL sources
    all_ops: list[set[str]] = []
    for source_data in sources.values():
        ops = set(source_data.get("operations", {}).keys())
        all_ops.append(ops)

    if not all_ops:
        return {}

    common_ops = set.intersection(*all_ops) if all_ops else set()
    return common_ops


def intersect_fields(field_dicts: list[dict]) -> dict:
    """Compute intersection of field definitions across sources.

    A field is common if it exists in ALL provided dicts.
    For common fields, we take the richest definition (most fields/description).
    """
    if not field_dicts:
        return {}

    # Find field names present in ALL dicts
    all_keys = [set(d.keys()) for d in field_dicts]
    common_keys = set.intersection(*all_keys) if all_keys else set()

    result = {}
    for key in common_keys:
        # Take the richest definition (most keys in the dict)
        candidates = [d[key] for d in field_dicts]
        # Pick the one with the most information
        best = max(candidates, key=lambda c: len(c) if isinstance(c, dict) else 0)
        result[key] = best

    return result


def compute_common(sources: dict[str, dict]) -> dict:
    """Compute the common.json content from all source files."""
    if len(sources) < 2:
        return {}

    # Path and pathParams should be identical across sources
    first = next(iter(sources.values()))
    common: dict = {"path": first.get("path", "")}

    # PathParams — intersect
    all_path_params = [s.get("pathParams", {}) for s in sources.values()]
    common_params = intersect_fields(all_path_params)
    if common_params:
        common["pathParams"] = common_params

    # Operations — find which methods are in ALL sources
    common_op_names = intersect_operations(sources)

    common["operations"] = {}
    for op_name in sorted(common_op_names):
        # Collect this operation from all sources
        op_instances = []
        for source_data in sources.values():
            op = source_data.get("operations", {}).get(op_name)
            if op:
                op_instances.append(op)

        if not op_instances:
            continue

        # The operation exists in common; now intersect its fields
        common_op: dict = {}

        # requestBody fields
        req_bodies = [
            op.get("requestBody", {}).get("fields", {})
            for op in op_instances
            if op.get("requestBody")
        ]
        if req_bodies and len(req_bodies) == len(op_instances):
            common_req_fields = intersect_fields(req_bodies)
            if common_req_fields:
                common_op["requestBody"] = {
                    "contentType": "application/json",
                    "fields": common_req_fields,
                }

        # response fields (200 only for now)
        resp_200s = [
            op.get("responses", {}).get("200", {}).get("fields", {})
            for op in op_instances
            if op.get("responses", {}).get("200")
        ]
        if resp_200s and len(resp_200s) == len(op_instances):
            common_resp_fields = intersect_fields(resp_200s)
            if common_resp_fields:
                common_op["responses"] = {"200": {"fields": common_resp_fields}}

        # queryParams
        query_params_list = [
            op.get("queryParams", {}) for op in op_instances if op.get("queryParams")
        ]
        if query_params_list and len(query_params_list) == len(op_instances):
            common_qp = intersect_fields(query_params_list)
            if common_qp:
                common_op["queryParams"] = common_qp

        common["operations"][op_name] = common_op

    return common


def compute_delta(source_data: dict, common: dict) -> dict:
    """Compute what's unique in a source relative to common.

    Returns the delta — fields/operations NOT in common.
    Returns empty dict if source is fully subsumed.
    """
    delta: dict = {}

    source_ops = source_data.get("operations", {})
    common_ops = common.get("operations", {})

    for op_name, op_data in source_ops.items():
        if op_name not in common_ops:
            # Entire operation is unique to this source
            delta.setdefault("operations", {})[op_name] = op_data
            continue

        # Operation is in common — check for unique fields
        common_op = common_ops[op_name]
        op_delta: dict = {}

        # operationId is always source-specific
        if "operationId" in op_data:
            op_delta["operationId"] = op_data["operationId"]

        # Unique request body fields
        if op_data.get("requestBody"):
            src_fields = op_data["requestBody"].get("fields", {})
            common_fields = common_op.get("requestBody", {}).get("fields", {})
            unique_fields = {k: v for k, v in src_fields.items() if k not in common_fields}
            if unique_fields:
                op_delta["requestBody"] = {
                    "contentType": "application/json",
                    "fields": unique_fields,
                }

        # Unique response fields
        if op_data.get("responses", {}).get("200"):
            src_fields = op_data["responses"]["200"].get("fields", {})
            common_fields = common_op.get("responses", {}).get("200", {}).get("fields", {})
            unique_fields = {k: v for k, v in src_fields.items() if k not in common_fields}
            if unique_fields:
                op_delta.setdefault("responses", {})["200"] = {"fields": unique_fields}

        # Unique query params
        if op_data.get("queryParams"):
            src_qp = op_data["queryParams"]
            common_qp = common_op.get("queryParams", {})
            unique_qp = {k: v for k, v in src_qp.items() if k not in common_qp}
            if unique_qp:
                op_delta["queryParams"] = unique_qp

        # Only include operation in delta if it has unique content beyond operationId
        has_unique = any(k != "operationId" for k in op_delta)
        if has_unique:
            delta.setdefault("operations", {})[op_name] = op_delta

    return delta


def build_provenance(sources: dict[str, dict], common: dict) -> dict:
    """Build provenance metadata for an endpoint."""
    meta: dict = {
        "sources": sorted(sources.keys()),
        "commonOperations": sorted(common.get("operations", {}).keys()),
        "fieldProvenance": {},
        "lastCompacted": datetime.now(UTC).isoformat(),
    }

    # Track which sources contribute each operation
    for source_name, source_data in sources.items():
        for op_name in source_data.get("operations", {}):
            key = f"{op_name}"
            meta["fieldProvenance"].setdefault(key, []).append(source_name)

    return meta


def compact_endpoint(endpoint_dir: Path) -> dict:
    """Compact a single endpoint directory. Returns stats."""
    sources = load_endpoint_sources(endpoint_dir)

    if len(sources) < 2:
        # Nothing to compact with a single source
        return {"sources": len(sources), "common_ops": 0, "deleted": 0}

    common = compute_common(sources)

    # Write common.json
    if common.get("operations"):
        with open(endpoint_dir / "common.json", "w") as f:
            json.dump(common, f, indent=2)
            f.write("\n")

    # Rewrite each source to delta and delete empty ones
    deleted = 0
    for source_name, source_data in sources.items():
        delta = compute_delta(source_data, common)
        source_file = endpoint_dir / f"{source_name}.json"

        if not delta or not delta.get("operations"):
            # Source is fully subsumed by common — delete
            source_file.unlink()
            deleted += 1
        else:
            # Preserve path for context
            delta_out = {"path": source_data.get("path", ""), **delta}
            with open(source_file, "w") as f:
                json.dump(delta_out, f, indent=2)
                f.write("\n")

    # Write meta.json
    meta = build_provenance(sources, common)
    with open(endpoint_dir / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")

    return {
        "sources": len(sources),
        "common_ops": len(common.get("operations", {})),
        "deleted": deleted,
    }


def find_endpoint_dirs(api_dir: Path) -> list[Path]:
    """Find all directories that contain source JSON files."""
    dirs = set()
    for f in api_dir.rglob("*.json"):
        if f.name not in SKIP_FILES:
            dirs.add(f.parent)
    return sorted(dirs)


def main() -> None:
    """Entry point for the compactor."""
    if not API_DIR.exists():
        print("No api/ directory found. Run extractors first.", file=sys.stderr)
        sys.exit(1)

    endpoint_dirs = find_endpoint_dirs(API_DIR)
    if not endpoint_dirs:
        print("No endpoint files found in api/.", file=sys.stderr)
        sys.exit(1)

    total_compacted = 0
    total_deleted = 0
    total_common_ops = 0
    multi_source_count = 0

    for endpoint_dir in endpoint_dirs:
        stats = compact_endpoint(endpoint_dir)
        if stats["sources"] >= 2:
            multi_source_count += 1
            total_compacted += 1
            total_common_ops += stats["common_ops"]
            total_deleted += stats["deleted"]

    # Write summary to provenance/
    PROVENANCE_DIR.mkdir(parents=True, exist_ok=True)

    # Per-source stats
    source_stats: dict[str, dict] = {}
    for endpoint_dir in endpoint_dirs:
        for f in endpoint_dir.glob("*.json"):
            if f.name in SKIP_FILES:
                continue
            source_name = f.stem
            source_stats.setdefault(source_name, {"endpoints": 0, "unique_ops": 0})
            source_stats[source_name]["endpoints"] += 1
            # Count unique operations in delta
            with open(f) as fh:
                data = json.load(fh)
                source_stats[source_name]["unique_ops"] += len(data.get("operations", {}))

    # Count common.json files
    common_count = sum(1 for _ in API_DIR.rglob("common.json"))

    summary = {
        "totalEndpointDirs": len(endpoint_dirs),
        "multiSourceEndpoints": multi_source_count,
        "commonGenerated": common_count,
        "sourcesDeleted": total_deleted,
        "perSource": source_stats,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    with open(PROVENANCE_DIR / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")

    print(f"Compacted {multi_source_count} multi-source endpoints:")
    print(f"  common.json generated: {common_count}")
    print(f"  source files deleted (fully subsumed): {total_deleted}")
    print()
    print("Per-source remaining endpoints (after compaction):")
    for name, stats in sorted(source_stats.items()):
        print(f"  {name}: {stats['endpoints']} files, {stats['unique_ops']} unique operations")


if __name__ == "__main__":
    main()
