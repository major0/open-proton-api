"""Renderer: produce OpenAPI 3.1 specification from the compacted api/ tree.

Walks the api/ tree, reads all endpoint files (common.json + source deltas),
merges them into unified path entries, and outputs per-service OpenAPI specs.

Generates canonical operationIds from method + path following RESTful
conventions (e.g., GET /drive/shares/{shareId} → getShare).

Output files are versioned with a date-based serial (YYYYMMDDNN) similar
to DNS SOA serial numbers.
"""

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
API_DIR = PROJECT_ROOT / "api"
OUTPUT_DIR = PROJECT_ROOT / "output"

SKIP_FILES = {"common.json", "meta.json"}

# Service detection from first path segment
KNOWN_SERVICES = {
    "drive",
    "core",
    "mail",
    "calendar",
    "meet",
    "lumo",
    "vpn",
    "pass",
    "contacts",
    "auth",
    "account",
    "docs",
    "data",
    "keys",
    "domains",
    "members",
    "oauth",
    "organizations",
    "permissions",
    "settings",
    "metrics",
    "logs",
    "tests",
    "payments",
    "shares",
}


def dir_to_path(endpoint_dir: Path) -> str:
    """Convert directory path back to API path template."""
    rel = endpoint_dir.relative_to(API_DIR)
    return "/" + str(rel)


def detect_service(api_path: str) -> str:
    """Detect which service an API path belongs to."""
    segments = api_path.lstrip("/").split("/")
    if not segments:
        return "unknown"
    first = segments[0]
    if first in KNOWN_SERVICES:
        return first
    return "other"


def generate_operation_id(method: str, path: str) -> str:
    """Generate a canonical operationId from method + path.

    Uses all meaningful path segments (skipping version numbers and service
    prefixes when they don't add disambiguation) to produce a unique
    camelCase identifier.

    GET /drive/shares/{shareId} → getShare
    POST /drive/shares/{shareId}/files/{linkId}/revisions → createRevision
    DELETE /drive/shares/{shareId}/files/{linkId}/revisions/{revisionId} → deleteRevision
    """
    method_verbs = {
        "GET": "get",
        "POST": "create",
        "PUT": "update",
        "DELETE": "delete",
        "PATCH": "patch",
    }
    verb = method_verbs.get(method.upper(), method.lower())

    # Extract non-param path segments
    all_segments = [s for s in path.split("/") if s and not s.startswith("{")]

    # Skip the first segment if it's a known service (drive, core, mail, etc.)
    # but keep version segments for uniqueness
    meaningful = all_segments[:]
    if meaningful and meaningful[0] in KNOWN_SERVICES:
        meaningful = meaningful[1:]

    if not meaningful:
        # Fallback: use full path segments including service
        meaningful = all_segments

    if not meaningful:
        return verb

    # GET on a collection (path doesn't end with param) → "list" prefix
    path_ends_with_param = path.rstrip("/").split("/")[-1].startswith("{")
    if method.upper() == "GET" and not path_ends_with_param:
        verb = "list"

    # Build resource name from all meaningful segments
    parts = []
    for seg in meaningful:
        # Convert kebab-case or snake_case to words
        words = re.split(r"[-_]", seg)
        parts.append("".join(w.capitalize() for w in words))

    resource = "".join(parts)

    # Singularize if path ends with a param (accessing a specific resource)
    if path_ends_with_param and resource.endswith("s") and not resource.endswith("ss"):
        resource = resource[:-1]

    return verb + resource


def field_to_schema(field_def: dict) -> dict:
    """Convert our internal field definition to OpenAPI 3.1 schema."""
    schema: dict = {}
    field_type = field_def.get("type", "string")

    # Map to OpenAPI types
    type_map = {
        "string": {"type": "string"},
        "integer": {"type": "integer"},
        "number": {"type": "number"},
        "boolean": {"type": "boolean"},
        "array": {"type": "array"},
        "object": {"type": "object"},
    }
    schema.update(type_map.get(field_type, {"type": "string"}))

    # Nullable (OpenAPI 3.1 uses type array with null)
    if field_def.get("nullable") and isinstance(schema.get("type"), str):
        schema["type"] = [schema["type"], "null"]

    # Enum
    if "enum" in field_def:
        schema["enum"] = field_def["enum"]

    # Description
    if "description" in field_def:
        desc = field_def["description"]
        # Skip internal $ref: descriptions
        if not desc.startswith("$ref:"):
            schema["description"] = desc

    # Nested fields (object properties)
    if "fields" in field_def:
        schema["type"] = "object"
        schema["properties"] = {
            name: field_to_schema(fdef) for name, fdef in field_def["fields"].items()
        }

    # Array items
    if "items" in field_def:
        schema["items"] = field_to_schema(field_def["items"])

    return schema


def generate_tag(path: str) -> str:
    """Generate a tag from the path's primary resource grouping.

    Uses the first 1-2 non-param, non-version segments after the service
    prefix. This groups operations by top-level resource.

    /drive/shares/{shareId}/files/{linkId}/revisions → shares
    /drive/photos/volumes/{volumeId}/albums → photos
    /mail/v4/messages/{messageId}/attachments → messages
    /core/v4/addresses/{addressId}/keys → addresses
    """
    segments = [
        s for s in path.split("/") if s and not s.startswith("{") and not re.match(r"^v\d+$", s)
    ]
    # Skip service prefix
    if segments and segments[0] in KNOWN_SERVICES:
        segments = segments[1:]

    if not segments:
        return "other"

    # Use first segment as tag (top-level resource grouping)
    return segments[0]


def build_operation(method: str, path: str, op_data: dict) -> dict:
    """Build an OpenAPI operation object from our internal format."""
    operation: dict = {
        "operationId": generate_operation_id(method, path),
        "tags": [generate_tag(path)],
    }

    # Query parameters
    if "queryParams" in op_data:
        # Deduplicate case collisions in query params
        deduped = _dedup_case_collisions(op_data["queryParams"])
        params = []
        for name, pdef in deduped.items():
            params.append(
                {
                    "name": name,
                    "in": "query",
                    "schema": field_to_schema(pdef),
                }
            )
        operation["parameters"] = params

    # Request body
    if "requestBody" in op_data:
        rb = op_data["requestBody"]
        properties = {}
        for name, fdef in rb.get("fields", {}).items():
            properties[name] = field_to_schema(fdef)
        # Deduplicate case collisions (prefer PascalCase — matches wire format)
        properties = _dedup_case_collisions(properties)
        if properties:
            operation["requestBody"] = {
                "content": {
                    rb.get("contentType", "application/json"): {
                        "schema": {
                            "type": "object",
                            "properties": properties,
                        }
                    }
                }
            }

    # Responses
    if "responses" in op_data:
        responses = {}
        for code, resp in op_data["responses"].items():
            resp_schema: dict = {"description": f"HTTP {code}"}
            if resp.get("fields"):
                properties = {name: field_to_schema(fdef) for name, fdef in resp["fields"].items()}
                properties = _dedup_case_collisions(properties)
                resp_schema["content"] = {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": properties,
                        }
                    }
                }
            responses[code] = resp_schema
        operation["responses"] = responses
    else:
        # Every operation needs at least one response for OpenAPI validity
        operation["responses"] = {"200": {"description": "Success"}}

    return operation


def load_endpoint(endpoint_dir: Path) -> dict | None:
    """Load and merge all files at an endpoint into a unified view."""
    merged_ops: dict = {}
    path = None

    # Load common.json first (consensus)
    common_file = endpoint_dir / "common.json"
    if common_file.exists():
        with open(common_file) as f:
            data = json.load(f)
        path = data.get("path")
        for method, op_data in data.get("operations", {}).items():
            merged_ops[method] = op_data

    # Load source deltas and merge (adds unique operations/fields)
    for f in sorted(endpoint_dir.glob("*.json")):
        if f.name in SKIP_FILES:
            continue
        with open(f) as fh:
            data = json.load(fh)
        if path is None:
            path = data.get("path")
        for method, op_data in data.get("operations", {}).items():
            if method not in merged_ops:
                merged_ops[method] = op_data
            else:
                # Merge fields from delta into existing
                existing = merged_ops[method]
                # Merge request body fields
                if "requestBody" in op_data:
                    if "requestBody" not in existing:
                        existing["requestBody"] = op_data["requestBody"]
                    else:
                        existing_fields = existing["requestBody"].get("fields", {})
                        new_fields = op_data["requestBody"].get("fields", {})
                        existing_fields.update(new_fields)
                        existing["requestBody"]["fields"] = existing_fields
                # Merge response fields
                if "responses" in op_data:
                    if "responses" not in existing:
                        existing["responses"] = op_data["responses"]
                    else:
                        for code, resp in op_data["responses"].items():
                            if code not in existing["responses"]:
                                existing["responses"][code] = resp
                            else:
                                existing_fields = existing["responses"][code].get("fields", {})
                                new_fields = resp.get("fields", {})
                                existing_fields.update(new_fields)
                                existing["responses"][code]["fields"] = existing_fields
                # Merge query params
                if "queryParams" in op_data:
                    if "queryParams" not in existing:
                        existing["queryParams"] = op_data["queryParams"]
                    else:
                        existing["queryParams"].update(op_data["queryParams"])

    if not path or not merged_ops:
        return None

    return {"path": path, "operations": merged_ops}


def find_endpoint_dirs(api_dir: Path) -> list[Path]:
    """Find all directories that contain endpoint JSON files."""
    dirs = set()
    for f in api_dir.rglob("*.json"):
        dirs.add(f.parent)
    return sorted(dirs)


def build_path_item(endpoint: dict) -> dict:
    """Build an OpenAPI path item from a merged endpoint."""
    path = endpoint["path"]
    path_item: dict = {}

    # Path parameters
    params = re.findall(r"\{([^}]+)\}", path)
    if params:
        path_item["parameters"] = [
            {"name": p, "in": "path", "required": True, "schema": {"type": "string"}}
            for p in params
        ]

    # Operations
    for method, op_data in endpoint["operations"].items():
        path_item[method.lower()] = build_operation(method, path, op_data)

    return path_item


def render_service_spec(service: str, paths: dict[str, dict]) -> dict:
    """Build a complete OpenAPI 3.1 spec for a service."""
    # Collect all unique tags used across operations
    tags_seen: set[str] = set()
    for path_item in paths.values():
        for method in ("get", "post", "put", "delete", "patch"):
            if method in path_item:
                for tag in path_item[method].get("tags", []):
                    tags_seen.add(tag)

    return {
        "openapi": "3.1.0",
        "info": {
            "title": f"Proton {service.capitalize()} API",
            "description": (
                f"OpenAPI specification for the Proton {service.capitalize()} API, "
                f"compiled from multiple official SDK sources."
            ),
            "version": "0.1.0",
            "contact": {"name": "open-proton-api", "url": "https://github.com/open-proton-api"},
        },
        "servers": [{"url": "https://mail.proton.me/api", "description": "Proton API"}],
        "tags": [{"name": tag} for tag in sorted(tags_seen)],
        "paths": dict(sorted(paths.items())),
    }


def _dedup_case_collisions(properties: dict) -> dict:
    """Remove case-only collisions from a properties dict.

    When two keys differ only by case (e.g., IDs vs Ids), keep the one
    with more uppercase letters (closer to Proton's wire format which
    uses PascalCase with uppercase acronyms like ID, UID).
    """
    lower_map: dict[str, str] = {}
    result: dict = {}
    for key, val in properties.items():
        lk = key.lower()
        if lk in lower_map:
            existing = lower_map[lk]
            # Keep whichever has more uppercase (closer to wire format)
            if sum(1 for c in key if c.isupper()) > sum(1 for c in existing if c.isupper()):
                del result[existing]
                result[key] = val
                lower_map[lk] = key
            # else keep existing, skip this one
        else:
            lower_map[lk] = key
            result[key] = val
    return result


def _dedup_operation_ids(spec: dict) -> None:
    """Ensure all operationIds in a spec are unique by appending suffixes."""
    seen: dict[str, int] = {}
    for path_item in spec.get("paths", {}).values():
        for method in ("get", "post", "put", "delete", "patch"):
            if method not in path_item:
                continue
            op = path_item[method]
            op_id = op.get("operationId", "")
            if not op_id:
                continue
            if op_id in seen:
                seen[op_id] += 1
                op["operationId"] = f"{op_id}{seen[op_id]}"
            else:
                seen[op_id] = 1


def compute_serial() -> str:
    """Compute a date-based serial version (YYYYMMDDNN).

    Format matches DNS SOA serial convention. NN is a sequence number
    starting at 01, incremented if multiple renders happen on the same day
    (detected by checking existing output files).
    """
    today = datetime.now(UTC).strftime("%Y%m%d")

    # Check for existing files from today to determine sequence number
    existing = sorted(OUTPUT_DIR.glob(f"proton-*-api-{today}*.json"))
    if existing:
        # Extract the highest sequence number from today's files
        max_seq = 0
        for f in existing:
            m = re.search(rf"{today}(\d{{2}})", f.name)
            if m:
                max_seq = max(max_seq, int(m.group(1)))
        seq = max_seq + 1
    else:
        seq = 1

    return f"{today}{seq:02d}"


def main() -> None:
    """Entry point for the renderer."""
    if not API_DIR.exists():
        print("No api/ directory found. Run extractors + compactor first.", file=sys.stderr)
        sys.exit(1)

    endpoint_dirs = find_endpoint_dirs(API_DIR)
    if not endpoint_dirs:
        print("No endpoint files found.", file=sys.stderr)
        sys.exit(1)

    # Group endpoints by service
    service_paths: dict[str, dict[str, dict]] = {}
    all_paths: dict[str, dict] = {}

    for endpoint_dir in endpoint_dirs:
        endpoint = load_endpoint(endpoint_dir)
        if not endpoint:
            continue

        path = endpoint["path"]
        service = detect_service(path)
        path_item = build_path_item(endpoint)

        service_paths.setdefault(service, {})[path] = path_item
        all_paths[path] = path_item

    # Compute version serial
    serial = compute_serial()

    # Write per-service specs
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for service, paths in sorted(service_paths.items()):
        spec = render_service_spec(service, paths)
        spec["info"]["version"] = serial
        _dedup_operation_ids(spec)

        output_file = OUTPUT_DIR / f"proton-{service}-api-{serial}.json"
        with open(output_file, "w") as f:
            json.dump(spec, f, indent=2)
            f.write("\n")
        print(f"  {service}: {len(paths)} paths → {output_file.name}")

    # Write unified spec
    unified = render_service_spec("all", all_paths)
    unified["info"]["title"] = "Proton API (Full)"
    unified["info"]["description"] = (
        "Complete OpenAPI specification for all Proton services, "
        "compiled from multiple official SDK sources."
    )
    unified["info"]["version"] = serial
    # For unified spec, prefix operationIds with service name to avoid cross-service collisions
    for path_str, path_item in unified.get("paths", {}).items():
        service = detect_service(path_str)
        for method in ("get", "post", "put", "delete", "patch"):
            if method in path_item:
                op = path_item[method]
                if "operationId" in op:
                    op["operationId"] = (
                        service + op["operationId"][0].upper() + op["operationId"][1:]
                    )
    _dedup_operation_ids(unified)

    unified_file = OUTPUT_DIR / f"proton-full-api-{serial}.json"
    with open(unified_file, "w") as f:
        json.dump(unified, f, indent=2)
        f.write("\n")

    total_paths = len(all_paths)
    total_ops = sum(
        len([m for m in ("get", "post", "put", "delete", "patch") if m in pi])
        for pi in all_paths.values()
    )
    print(
        f"\nTotal: {total_paths} paths, {total_ops} operations across {len(service_paths)} services"
    )
    print(f"Unified spec: {unified_file}")


if __name__ == "__main__":
    main()
