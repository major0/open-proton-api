"""Extractor for Kotlin Retrofit API interfaces.

Parses Kotlin source files that define Retrofit API interfaces using
annotations like @GET, @POST, @PUT, @DELETE, @PATCH with URL paths,
@Path for path parameters, @Query for query parameters, @Body for
request bodies.

This extractor handles multiple sources that share the same pattern:
- protoncore-android (Core: auth, keys, contacts, events, etc.)
- android-drive (Drive: files, folders, shares, links, etc.)
- android-pass (Pass)

The source name is passed as a CLI argument.
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
API_DIR = PROJECT_ROOT / "api"
SOURCES_DIR = PROJECT_ROOT / "sources"

# Retrofit annotation patterns
HTTP_ANNOTATION_RE = re.compile(r'@(GET|POST|PUT|DELETE|PATCH)\("([^"]+)"\)')
PATH_PARAM_RE = re.compile(r'@Path\("([^"]+)"\)\s+\w+:\s+(\w+)')
QUERY_PARAM_RE = re.compile(r'@Query\("([^"]+)"\)\s+\w+:\s+(\w+)')
BODY_PARAM_RE = re.compile(r"@Body\s+\w+:\s+(\w+)")
RETURN_TYPE_RE = re.compile(r"\):\s+(\w+)")
FUN_NAME_RE = re.compile(r"suspend\s+fun\s+(\w+)\(")


def normalize_path(path: str) -> str:
    """Normalize Retrofit path to our standard format.

    Converts {enc_shareID} → {shareID} (strip enc_ prefix).
    Ensures leading slash.
    """
    # Strip enc_ prefix from path params
    path = re.sub(r"\{enc_(\w+)\}", r"{\1}", path)
    if not path.startswith("/"):
        path = "/" + path
    return path


def extract_path_params(path: str) -> dict[str, dict]:
    """Extract path parameters from normalized path."""
    params = {}
    for m in re.finditer(r"\{(\w+)\}", path):
        params[m.group(1)] = {"type": "string"}
    return params


def parse_retrofit_interface(content: str) -> list[dict]:
    """Parse a Kotlin file for Retrofit-annotated interface methods."""
    endpoints: list[dict] = []
    lines = content.splitlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Look for HTTP method annotation
        ann_match = HTTP_ANNOTATION_RE.search(line)
        if not ann_match:
            i += 1
            continue

        http_method = ann_match.group(1)
        path = ann_match.group(2)

        # Collect the full function signature (may span multiple lines)
        func_lines = []
        j = i + 1
        while j < len(lines):
            func_lines.append(lines[j])
            if ")" in lines[j] and (":" in lines[j] or j > i + 20):
                break
            j += 1

        func_block = " ".join(func_lines)

        # Extract function name
        func_name_match = FUN_NAME_RE.search(func_block)
        func_name = func_name_match.group(1) if func_name_match else f"unknown_{i}"

        # Normalize path
        path = normalize_path(path)

        # Build operation
        op: dict = {"operationId": func_name}

        # Extract query parameters
        query_params = {}
        for qm in QUERY_PARAM_RE.finditer(func_block):
            query_params[qm.group(1)] = {"type": _kotlin_type_to_schema(qm.group(2))}
        if query_params:
            op["queryParams"] = query_params

        # Extract request body type
        body_match = BODY_PARAM_RE.search(func_block)
        if body_match and http_method in ("POST", "PUT", "PATCH"):
            body_type = body_match.group(1)
            op["requestBody"] = {
                "contentType": "application/json",
                "fields": {body_type: {"type": "object", "description": f"See {body_type}"}},
            }

        # Extract response type
        return_match = RETURN_TYPE_RE.search(func_block)
        if return_match:
            return_type = return_match.group(1)
            if return_type not in ("Response", "ResponseBody"):
                op["responses"] = {"200": {"fields": {return_type: {"type": "object"}}}}

        endpoints.append(
            {
                "url": path,
                "method": http_method,
                "operation": op,
            }
        )

        i = j + 1

    return endpoints


def _kotlin_type_to_schema(kt_type: str) -> str:
    """Map Kotlin type to schema type."""
    mapping = {
        "String": "string",
        "Int": "integer",
        "Long": "integer",
        "Boolean": "boolean",
        "Float": "number",
        "Double": "number",
    }
    return mapping.get(kt_type, "string")


def group_by_path(endpoints: list[dict]) -> dict[str, dict]:
    """Group endpoints by URL path."""
    grouped: dict[str, dict] = {}
    for ep in endpoints:
        url = ep["url"]
        method = ep["method"]
        op = ep["operation"]
        if url not in grouped:
            grouped[url] = {"path": url, "operations": {}}
            path_params = extract_path_params(url)
            if path_params:
                grouped[url]["pathParams"] = path_params
        if method not in grouped[url]["operations"]:
            grouped[url]["operations"][method] = op
    return grouped


def path_to_dir(path: str) -> Path:
    """Convert API path to directory under api/."""
    from src.pathutil import API_DIR, normalize_path
    from src.pathutil import path_to_dir as _ptd

    return _ptd(normalize_path(path), API_DIR)


def write_endpoint(endpoint: dict, output_dir: Path, source_name: str) -> None:
    """Write endpoint definition to source file via pathutil."""
    from src.pathutil import write_endpoint as _write

    _write(endpoint.get("path", ""), endpoint.get("operations", {}), source_name)


def extract_source(source_dir: Path, source_name: str) -> int:
    """Extract all Retrofit API endpoints from a source directory."""
    api_files = sorted(
        f
        for f in source_dir.rglob("*Api.kt")
        if "test" not in str(f).lower() and "mock" not in str(f).lower()
    )

    all_endpoints: list[dict] = []
    for filepath in api_files:
        content = filepath.read_text()
        # Only process files with Retrofit annotations
        if "@GET" not in content and "@POST" not in content:
            continue
        endpoints = parse_retrofit_interface(content)
        all_endpoints.extend(endpoints)

    grouped = group_by_path(all_endpoints)
    total = 0
    for path, endpoint in grouped.items():
        if not endpoint["operations"]:
            continue
        output_dir = path_to_dir(path)
        write_endpoint(endpoint, output_dir, source_name)
        total += 1

    return total


def main() -> None:
    """Entry point. Expects source name as first argument."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.extractors.kotlin_retrofit <source-name>", file=sys.stderr)
        sys.exit(1)

    source_name = sys.argv[1]
    source_dir = SOURCES_DIR / source_name

    if not source_dir.exists():
        print(f"Error: source not found at {source_dir}", file=sys.stderr)
        sys.exit(1)

    count = extract_source(source_dir, source_name)
    print(f"Extracted {count} endpoints from {source_name}")


if __name__ == "__main__":
    main()
