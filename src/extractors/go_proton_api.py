"""Extractor for go-proton-api Go client.

Parses Go source files to extract API endpoint definitions from
func (c *Client) methods that call c.do(ctx, ...) with resty requests.

This source is known to be incomplete relative to the official SDKs.
The absence of endpoints/fields here (compared to other sources) signals
gaps in the Go client.
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
API_DIR = PROJECT_ROOT / "api"
SOURCES_DIR = PROJECT_ROOT / "sources"

SOURCE_NAME = "go-proton-api"

# Regex patterns for Go source parsing
# Match: func (c *Client) MethodName(
CLIENT_METHOD_RE = re.compile(r"^func\s+\([a-z]\s+\*Client\)\s+(\w+)\(")
# Match: .Get("/path..." or .Post("/path..." etc. — captures the full line
HTTP_METHOD_RE = re.compile(r"\.(Get|Post|Put|Delete|Patch)\((.+?)\)")
# Match: .SetBody(varOrExpr)
SET_BODY_RE = re.compile(r"\.SetBody\((\w+)")
# Match: .SetResult(&res)
SET_RESULT_RE = re.compile(r"\.SetResult\(&(\w+)\)")
# Match: struct field definitions like:  FieldName string
STRUCT_FIELD_RE = re.compile(
    r"^\s+(\w+)\s+(string|int|int64|bool|float64|Bool|\[\]\w+|\*?\w+)" r"(?:\s+`[^`]*`)?"
)
# Match: type TypeName struct {
TYPE_DEF_RE = re.compile(r"^type\s+(\w+)\s+struct\s*\{")


def parse_struct_types(source_dir: Path) -> dict[str, dict[str, dict]]:
    """Parse all _types.go files to build a map of struct name → fields."""
    types: dict[str, dict[str, dict]] = {}

    for go_file in sorted(source_dir.glob("*_types.go")):
        content = go_file.read_text()
        lines = content.splitlines()

        current_type = None
        brace_depth = 0

        for line in lines:
            # New type definition
            m = TYPE_DEF_RE.match(line)
            if m:
                current_type = m.group(1)
                types[current_type] = {}
                brace_depth = 1
                continue

            if current_type is None:
                continue

            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                current_type = None
                continue

            # Field in current struct
            fm = STRUCT_FIELD_RE.match(line)
            if fm:
                field_name = fm.group(1)
                field_type = fm.group(2)
                # Skip unexported fields
                if field_name[0].islower():
                    continue
                types[current_type][field_name] = {"type": _go_type_to_schema_type(field_type)}

    return types


def _go_type_to_schema_type(go_type: str) -> str:
    """Map Go type to our schema type string."""
    go_type = go_type.lstrip("*")
    if go_type in ("string",):
        return "string"
    if go_type in ("int", "int64", "int32"):
        return "integer"
    if go_type in ("float64", "float32"):
        return "number"
    if go_type in ("bool", "Bool"):
        return "boolean"
    if go_type.startswith("[]"):
        return "array"
    return "object"


def normalize_go_url(url_expr: str) -> str:
    """Normalize a Go URL expression into a path template.

    Go URLs use string concatenation: "/path/" + variable + "/more"
    This function converts concatenated parts into {param} templates.
    """
    # Split on + for concatenation
    parts = [p.strip() for p in url_expr.split("+")]
    result = ""
    for part in parts:
        # String literal
        if part.startswith('"') and part.endswith('"'):
            result += part.strip('"')
        elif part.startswith('"'):
            # Partial string (shouldn't happen with proper split)
            result += part.strip('"')
        else:
            # Variable reference → path parameter
            result += "{" + part + "}"

    if not result.startswith("/"):
        result = "/" + result
    # Remove trailing slash
    result = result.rstrip("/")
    return result


def extract_endpoints_from_file(
    filepath: Path, struct_types: dict[str, dict[str, dict]]
) -> list[dict]:
    """Extract endpoint definitions from a single Go source file."""
    content = filepath.read_text()
    endpoints: list[dict] = []

    # Find all client method bodies
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        method_match = CLIENT_METHOD_RE.match(line)
        if not method_match:
            i += 1
            continue

        func_name = method_match.group(1)

        # Collect the full function body
        brace_depth = 0
        func_body_lines = []
        j = i
        while j < len(lines):
            func_body_lines.append(lines[j])
            brace_depth += lines[j].count("{") - lines[j].count("}")
            if brace_depth <= 0 and j > i:
                break
            j += 1

        func_body = "\n".join(func_body_lines)

        # Find HTTP method calls within the function body
        http_matches = HTTP_METHOD_RE.findall(func_body)
        for http_method, url_expr in http_matches:
            method = http_method.upper()
            url = normalize_go_url(url_expr)

            # Build operation
            op: dict = {"operationId": func_name}

            # Check for request body
            body_match = SET_BODY_RE.search(func_body)
            if body_match and method in ("POST", "PUT", "PATCH", "DELETE"):
                body_var = body_match.group(1)
                # Try to resolve struct type
                if body_var in struct_types:
                    fields = {}
                    for fname, fdef in struct_types[body_var].items():
                        fields[fname] = fdef
                    if fields:
                        op["requestBody"] = {
                            "contentType": "application/json",
                            "fields": fields,
                        }
                else:
                    op["requestBody"] = {
                        "contentType": "application/json",
                        "fields": {body_var: {"type": "object"}},
                    }

            # Check for response type (inline struct in the function)
            # Look for: var res struct { FieldName Type }
            res_struct_re = re.compile(r"var\s+\w+\s+struct\s*\{([^}]+)\}", re.DOTALL)
            res_match = res_struct_re.search(func_body)
            if res_match:
                res_body = res_match.group(1)
                fields = {}
                for fm in STRUCT_FIELD_RE.finditer(res_body):
                    fname = fm.group(1)
                    ftype = fm.group(2)
                    if fname[0].isupper():
                        fields[fname] = {"type": _go_type_to_schema_type(ftype)}
                if fields:
                    op["responses"] = {"200": {"fields": fields}}

            endpoint = {
                "url": url,
                "method": method,
                "operation": op,
            }
            endpoints.append(endpoint)
            break  # Only take the first HTTP call per function

        i = j + 1

    return endpoints


def extract_path_params(url: str) -> dict[str, dict]:
    """Extract path parameters from a normalized URL."""
    params = {}
    for m in re.finditer(r"\{(\w+)\}", url):
        params[m.group(1)] = {"type": "string"}
    return params


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


def write_endpoint(endpoint: dict, output_dir: Path) -> None:
    """Write endpoint definition to source file via pathutil."""
    from src.pathutil import write_endpoint as _write

    _write(endpoint.get("path", ""), endpoint.get("operations", {}), SOURCE_NAME)


def main() -> None:
    """Entry point for the go-proton-api extractor."""
    source_dir = SOURCES_DIR / "go-proton-api"

    if not source_dir.exists():
        print(f"Error: source not found at {source_dir}", file=sys.stderr)
        sys.exit(1)

    # Parse struct types first
    struct_types = parse_struct_types(source_dir)

    # Extract endpoints from all non-test Go files in the root package
    go_files = sorted(
        f
        for f in source_dir.glob("*.go")
        if not f.name.endswith("_test.go")
        and f.name
        not in (
            "boolean.go",
            "contexts.go",
            "future.go",
            "job.go",
            "logging.go",
            "netctl.go",
            "option.go",
            "paging.go",
            "pool.go",
            "response.go",
            "ticker.go",
            "internal.go",
            "package.go",
            "keyring.go",
        )
    )

    all_endpoints: list[dict] = []
    for filepath in go_files:
        endpoints = extract_endpoints_from_file(filepath, struct_types)
        all_endpoints.extend(endpoints)

    # Group by path and write
    grouped = group_by_path(all_endpoints)
    total = 0
    for path, endpoint in grouped.items():
        if not endpoint["operations"]:
            continue
        output_dir = path_to_dir(path)
        write_endpoint(endpoint, output_dir)
        total += 1

    print(f"Extracted {total} endpoints from go-proton-api")


if __name__ == "__main__":
    main()
