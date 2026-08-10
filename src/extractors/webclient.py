"""Extractor for WebClients API request builders.

Parses hand-written TypeScript files in WebClients/packages/shared/lib/api/
that export functions returning {method, url, data?, params?} objects.

This is the broadest-coverage source, covering ALL Proton services:
Drive, Mail, Calendar, Meet, Lumo, Docs, VPN, Core.
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
API_DIR = PROJECT_ROOT / "api"
SOURCES_DIR = PROJECT_ROOT / "sources"

SOURCE_NAME = "webclient"

# Skip files that don't contain API endpoint definitions
SKIP_FILES = {
    "createApi.ts",
    "interface.ts",
    "apiEnvironmentConfig.ts",
    "apiRateLimiter.ts",
}

# Regex patterns
# Match: export const funcName = (...) => ({
# Match: export const funcName = {
EXPORT_FUNC_RE = re.compile(
    r"^export\s+const\s+(\w+)\s*=\s*" r"(?:\([^)]*\)\s*(?::\s*\w+)?\s*=>)?\s*\(?\{?"
)
# Match: method: 'get' or method: 'post' etc.
METHOD_RE = re.compile(r"""method:\s*['"](\w+)['"]""")
# Match: url: 'some/path' or url: `template/${var}/path`
URL_LITERAL_RE = re.compile(r"""url:\s*['"]([^'"]+)['"]""")
URL_TEMPLATE_RE = re.compile(r"url:\s*`([^`]+)`")
# Match data: { ... } or data: varName or data,
DATA_FIELD_RE = re.compile(r"data[,:]")


def normalize_url(url: str) -> str:
    """Normalize a URL by converting template literals to path params.

    `mail/v4/messages/${messageID}` → `mail/v4/messages/{messageID}`
    Also strip query strings and resolve known constants.
    """
    # Resolve known URL prefix constants
    known_constants = {
        "CALENDAR_V1": "calendar/v1",
        "CALENDAR_V2": "calendar/v2",
    }
    for const_name, const_value in known_constants.items():
        url = url.replace(f"${{{const_name}}}", const_value)

    # Convert ${var} to {var}
    url = re.sub(r"\$\{([^}]+)\}", r"{\1}", url)
    # Remove encodeURIComponent wrapper
    url = re.sub(r"\{encodeURIComponent\((\w+)\)\}", r"{\1}", url)
    # Strip query strings
    url = url.split("?")[0]
    # Ensure leading slash
    if not url.startswith("/"):
        url = "/" + url
    return url


def extract_path_params(url: str) -> dict[str, dict]:
    """Extract path parameters from normalized URL."""
    params = {}
    for m in re.finditer(r"\{(\w+)\}", url):
        params[m.group(1)] = {"type": "string"}
    return params


def extract_data_fields(block: str) -> dict[str, dict] | None:
    """Try to extract request body field names from the data object in a block.

    Handles two patterns:
    1. Explicit key-value: data: { CurrentRevisionID: currentRevisionId, ... }
       → Extract only keys (left side of colon)
    2. Shorthand: data: { Email, MaxSpace, ... }
       → Word followed by comma/closing brace (no colon after it)

    Only extracts the actual JSON property names sent over the wire.
    """
    # Look for data: { ... } pattern
    data_match = re.search(r"data:\s*\{([^}]+)\}", block, re.DOTALL)
    if data_match:
        content = data_match.group(1)
        fields = {}

        # Pattern 1: explicit key: value pairs
        for m in re.finditer(r"(\w+)\s*:", content):
            name = m.group(1)
            if name in _DATA_SKIP_WORDS:
                continue
            fields[name] = {"type": "string"}

        # Pattern 2: shorthand properties (word followed by , or end)
        # Only pick these up if we found NO explicit keys (avoids double-capture)
        if not fields:
            for m in re.finditer(r"(\w+)\s*[,}]", content):
                name = m.group(1)
                if name in _DATA_SKIP_WORDS:
                    continue
                # Skip if this word also appears as a value (after a colon)
                fields[name] = {"type": "string"}

        if fields:
            return fields

    # Look for data: varName pattern (referencing a parameter)
    data_var = re.search(r"data:\s*(\w+)", block)
    if data_var:
        var_name = data_var.group(1)
        if var_name not in ("undefined", "data"):
            return {var_name: {"type": "object", "description": f"See {var_name} type"}}

    return None


_DATA_SKIP_WORDS = frozenset(
    {
        "method",
        "url",
        "data",
        "params",
        "undefined",
        "Number",
        "true",
        "false",
        "timeout",
        "silence",
        "input",
        "output",
        "credentials",
        "ignoreHandler",
        "null",
    }
)


def extract_query_params(block: str) -> dict[str, dict] | None:
    """Try to extract query parameter names from the params object."""
    params_match = re.search(r"params:\s*\{([^}]+)\}", block, re.DOTALL)
    if params_match:
        content = params_match.group(1)
        params = {}
        for m in re.finditer(r"(\w+)\s*[,:}]", content):
            name = m.group(1)
            if name in ("method", "url", "data", "params", "undefined", "Number"):
                continue
            params[name] = {"type": "string"}
        if params:
            return params
    return None


def parse_api_file(filepath: Path) -> list[dict]:
    """Parse a single API builder file and extract endpoint definitions.

    Returns a list of (url, method, operation_data) tuples as endpoint dicts.
    """
    content = filepath.read_text()
    endpoints: list[dict] = []

    # Split into blocks at export boundaries
    # Each export const/function defines one or more endpoints
    blocks = re.split(r"(?=^export\s+const\s+)", content, flags=re.MULTILINE)

    for block in blocks:
        if not block.strip():
            continue

        # Extract function name
        name_match = re.match(r"export\s+const\s+(\w+)", block)
        if not name_match:
            continue
        func_name = name_match.group(1)

        # Extract method
        method_match = METHOD_RE.search(block)
        if not method_match:
            continue
        method = method_match.group(1).upper()

        # Extract URL
        url = None
        url_match = URL_TEMPLATE_RE.search(block)
        if url_match:
            url = url_match.group(1)
        else:
            url_match = URL_LITERAL_RE.search(block)
            if url_match:
                url = url_match.group(1)

        if not url:
            continue

        url = normalize_url(url)

        # Build operation
        op: dict = {"operationId": func_name}

        # Query params
        qparams = extract_query_params(block)
        if qparams:
            op["queryParams"] = qparams

        # Request body (only for POST/PUT/PATCH)
        if method in ("POST", "PUT", "PATCH"):
            fields = extract_data_fields(block)
            if fields:
                op["requestBody"] = {
                    "contentType": "application/json",
                    "fields": fields,
                }

        endpoints.append(
            {
                "url": url,
                "method": method,
                "operation": op,
            }
        )

    return endpoints


def group_by_path(endpoints: list[dict]) -> dict[str, dict]:
    """Group extracted endpoints by URL path.

    Returns path → {operations: {METHOD: op_def}, pathParams: {...}}
    """
    grouped: dict[str, dict] = {}

    for ep in endpoints:
        url = ep["url"]
        method = ep["method"]
        op = ep["operation"]

        if url not in grouped:
            grouped[url] = {
                "path": url,
                "operations": {},
            }
            path_params = extract_path_params(url)
            if path_params:
                grouped[url]["pathParams"] = path_params

        # Don't overwrite if we already have this method (first wins)
        if method not in grouped[url]["operations"]:
            grouped[url]["operations"][method] = op

    return grouped


def path_to_dir(path: str) -> Path:
    """Convert an API path to a directory under api/."""
    from src.pathutil import API_DIR, normalize_path
    from src.pathutil import path_to_dir as _path_to_dir

    return _path_to_dir(normalize_path(path), API_DIR)


def write_endpoint(endpoint: dict, output_dir: Path) -> None:
    """Write an endpoint definition to its source file via pathutil."""
    from src.pathutil import write_endpoint as _write

    _write(endpoint.get("path", ""), endpoint.get("operations", {}), SOURCE_NAME)


def main() -> None:
    """Entry point for the WebClients extractor."""
    api_base = SOURCES_DIR / "webclient" / "packages" / "shared" / "lib" / "api"

    if not api_base.exists():
        print(f"Error: source not found at {api_base}", file=sys.stderr)
        sys.exit(1)

    # Collect all API files (top-level + subdirectories like drive/)
    api_files = []
    for ts_file in sorted(api_base.rglob("*.ts")):
        if ts_file.name in SKIP_FILES:
            continue
        # Skip helper subdirectories
        if "helpers" in ts_file.parts or "core" in ts_file.parts:
            continue
        api_files.append(ts_file)

    total = 0
    service_counts: dict[str, int] = {}

    for filepath in api_files:
        endpoints = parse_api_file(filepath)
        grouped = group_by_path(endpoints)

        for path, endpoint in grouped.items():
            if not endpoint["operations"]:
                continue

            output_dir = path_to_dir(path)
            write_endpoint(endpoint, output_dir)
            total += 1

            # Track service
            service = path.lstrip("/").split("/")[0] if "/" in path.lstrip("/") else "unknown"
            service_counts[service] = service_counts.get(service, 0) + 1

    print(f"Extracted {total} endpoints from WebClients:")
    for service, count in sorted(service_counts.items()):
        print(f"  {service}: {count}")


if __name__ == "__main__":
    main()
