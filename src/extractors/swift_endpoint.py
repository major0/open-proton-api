"""Extractor for Swift Endpoint pattern (iOS clients).

Parses Swift source files that define structs conforming to the Endpoint
protocol with explicit `path`, `method`, `Body`, and `Response` types.

Handles two patterns:
- ios-pass: `path = "/pass/v1/..."`, `method = .post`
- ios-drive: URL built via appendPathComponent(), httpMethod set directly

The source name is determined by which repository is being processed.
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
API_DIR = PROJECT_ROOT / "api"
SOURCES_DIR = PROJECT_ROOT / "sources"

# Pattern: path = "/some/path/\(variable)/more"
PATH_ASSIGN_RE = re.compile(r'path\s*=\s*"(/[^"]+)"')
# Pattern: path = "/some/\(var)/path"  (string interpolation)
PATH_INTERPOLATION_RE = re.compile(r'path\s*=\s*"((?:[^"\\]|\\.)*)"')
# Pattern: method = .post / .get / .put / .delete
METHOD_ASSIGN_RE = re.compile(r"method\s*=\s*\.(\w+)")
# Pattern: httpMethod = "POST"
HTTP_METHOD_ASSIGN_RE = re.compile(r'httpMethod\s*=\s*"(\w+)"')
# Pattern: typealias Body = SomeType
BODY_TYPE_RE = re.compile(r"typealias\s+Body\s*=\s*(\w+)")
# Pattern: typealias Response = SomeType
RESPONSE_TYPE_RE = re.compile(r"typealias\s+Response\s*=\s*(\w+)")
# Pattern for ios-drive URL building: url.appendPathComponent("/files")
APPEND_PATH_RE = re.compile(r'appendPathComponent\("([^"]+)"\)')
# Pattern: service.url(of: "/shares")
SERVICE_URL_RE = re.compile(r'service\.url\(of:\s*"([^"]+)"\)')


def normalize_swift_path(path: str) -> str:
    """Normalize Swift string interpolation to path params.

    "/pass/v1/share/\\(shareId)/items" → "/pass/v1/share/{shareId}/items"
    """
    # Convert \(varName) to {varName}
    path = re.sub(r"\\\((\w+)\)", r"{\1}", path)
    # Ensure leading slash
    if not path.startswith("/"):
        path = "/" + path
    # Remove trailing slash
    path = path.rstrip("/")
    return path


def extract_ios_pass_endpoint(content: str) -> dict | None:
    """Extract endpoint from ios-pass style (explicit path and method)."""
    path_match = PATH_INTERPOLATION_RE.search(content)
    if not path_match:
        return None

    path = normalize_swift_path(path_match.group(1))

    method_match = METHOD_ASSIGN_RE.search(content)
    if not method_match:
        return None
    method = method_match.group(1).upper()

    op: dict = {}

    # Extract Body type
    body_match = BODY_TYPE_RE.search(content)
    if body_match and method in ("POST", "PUT", "PATCH"):
        body_type = body_match.group(1)
        if body_type not in ("EmptyRequest", "Never"):
            op["requestBody"] = {
                "contentType": "application/json",
                "fields": {body_type: {"type": "object"}},
            }

    # Extract Response type
    resp_match = RESPONSE_TYPE_RE.search(content)
    if resp_match:
        resp_type = resp_match.group(1)
        if resp_type not in ("EmptyResponse", "CodeOnlyResponse"):
            op["responses"] = {"200": {"fields": {resp_type: {"type": "object"}}}}

    return {"url": path, "method": method, "operation": op}


def extract_ios_drive_endpoint(content: str) -> dict | None:
    """Extract endpoint from ios-drive style (URL built via appendPathComponent)."""
    # Find base URL
    base_match = SERVICE_URL_RE.search(content)
    if not base_match:
        return None

    path_parts = [base_match.group(1)]

    # Find all appended path components
    for m in APPEND_PATH_RE.finditer(content):
        component = m.group(1)
        path_parts.append(component)

    # Also check for variable appends — these are path params
    # Pattern: url.appendPathComponent(varName)
    var_appends = re.findall(r"appendPathComponent\((\w+)\)", content)
    for var_name in var_appends:
        if var_name not in [m.group(1) for m in APPEND_PATH_RE.finditer(content)]:
            # It's a variable, not a string literal
            path_parts.append("{" + var_name + "}")

    path = "/".join(p.strip("/") for p in path_parts if p)
    if not path.startswith("/"):
        path = "/" + path

    # Get HTTP method
    method_match = HTTP_METHOD_ASSIGN_RE.search(content)
    if not method_match:
        method_match = METHOD_ASSIGN_RE.search(content)
    if not method_match:
        return None

    method = method_match.group(1).upper()

    op: dict = {}

    # Look for Response struct
    resp_match = re.search(r"struct\s+Response:\s*Codable", content)
    if resp_match:
        op["responses"] = {"200": {"fields": {}}}

    return {"url": path, "method": method, "operation": op}


def parse_swift_file(filepath: Path) -> dict | None:
    """Parse a single Swift endpoint file."""
    content = filepath.read_text()

    # Skip if it doesn't look like an endpoint definition
    if "Endpoint" not in content and "endpoint" not in content:
        return None

    # Try ios-pass pattern first (more explicit)
    result = extract_ios_pass_endpoint(content)
    if result:
        # Use struct name as operationId
        struct_match = re.search(r"struct\s+(\w+Endpoint)", content)
        if struct_match:
            result["operation"]["operationId"] = struct_match.group(1)
        return result

    # Try ios-drive pattern
    result = extract_ios_drive_endpoint(content)
    if result:
        struct_match = re.search(r"struct\s+(\w+Endpoint)", content)
        if struct_match:
            result["operation"]["operationId"] = struct_match.group(1)
        return result

    return None


def extract_path_params(url: str) -> dict[str, dict]:
    """Extract path parameters from normalized URL."""
    params = {}
    for m in re.finditer(r"\{(\w+)\}", url):
        params[m.group(1)] = {"type": "string"}
    return params


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
    """Extract all Swift endpoints from a source directory."""
    endpoint_files = sorted(
        f
        for f in source_dir.rglob("*Endpoint.swift")
        if "test" not in str(f).lower() and "mock" not in str(f).lower()
    )

    grouped: dict[str, dict] = {}

    for filepath in endpoint_files:
        result = parse_swift_file(filepath)
        if not result:
            continue

        url = result["url"]
        method = result["method"]
        op = result["operation"]

        if url not in grouped:
            grouped[url] = {"path": url, "operations": {}}
            path_params = extract_path_params(url)
            if path_params:
                grouped[url]["pathParams"] = path_params

        if method not in grouped[url]["operations"]:
            grouped[url]["operations"][method] = op

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
        print("Usage: python -m src.extractors.swift_endpoint <source-name>", file=sys.stderr)
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
