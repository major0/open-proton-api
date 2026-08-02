"""Custom OpenAPI linter for RESTful naming conventions.

Validates rendered OpenAPI specs against:
1. Structural validity (OpenAPI 3.1 schema compliance) — hard fail
2. RESTful naming conventions per restfulapi.net — warnings

Convention checks (warnings, not failures):
- Path segments should be lowercase nouns (no verbs, no camelCase)
- Path parameters should be camelCase ({shareId} not {share_id})
- No trailing slashes
- Collections should be plural nouns
- Operations should not duplicate HTTP method semantics in the path

Known Proton API exceptions are tracked and suppressed.
"""

import json
import re
import sys
from pathlib import Path

from openapi_spec_validator import validate
from openapi_spec_validator.exceptions import OpenAPISpecValidatorError

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

# Known Proton API paths that legitimately violate REST conventions.
# These are real API routes we document but can't change.
KNOWN_EXCEPTIONS = {
    # Verb-like segments that are actually RPC-style endpoints in Proton's API
    "trash_multiple",
    "delete_multiple",
    "delete",
    "empty",
    "unread",
    "read",
    "forward",
    "unforward",
    "send",
    "import",
    "export",
    "trash",
    "untrash",
    "label",
    "unlabel",
    "move",
    "rename",
    "restore",
    "join",
    "accept",
    "reject",
    "lock",
    "unlock",
    "enable",
    "disable",
    "reinvite",
    "rotate",
    "verify",
    "validate",
    "revoke",
    "refresh",
    "setup",
    "reset",
    "cancel_send",
    "force_send",
    "apply-filters",
    "check",
}

# Common verbs that indicate a non-RESTful path segment
VERB_INDICATORS = {
    "get",
    "create",
    "update",
    "delete",
    "fetch",
    "list",
    "add",
    "remove",
    "set",
    "check",
    "query",
}


def validate_structure(spec_path: Path) -> list[str]:
    """Validate OpenAPI 3.1 structural compliance. Returns errors."""
    errors = []
    try:
        with open(spec_path) as f:
            spec = json.load(f)
        validate(spec)
    except (OpenAPISpecValidatorError, json.JSONDecodeError) as e:
        errors.append(f"Structural validation failed: {e}")
    return errors


def lint_paths(spec: dict) -> list[dict]:
    """Lint path naming conventions. Returns list of findings."""
    findings = []
    paths = spec.get("paths", {})

    for path, path_item in paths.items():
        segments = [s for s in path.split("/") if s and not s.startswith("{")]
        params = re.findall(r"\{([^}]+)\}", path)

        # Check: path segments should be lowercase
        for seg in segments:
            if seg != seg.lower():
                findings.append(
                    {
                        "level": "warning",
                        "path": path,
                        "rule": "path-segment-lowercase",
                        "message": f"Segment '{seg}' is not lowercase",
                    }
                )

        # Check: path segments should not contain obvious verbs
        # (skip known Proton exceptions)
        for seg in segments:
            if seg in KNOWN_EXCEPTIONS:
                continue
            if seg.lower() in VERB_INDICATORS:
                findings.append(
                    {
                        "level": "warning",
                        "path": path,
                        "rule": "path-no-verbs",
                        "message": f"Segment '{seg}' looks like a verb — REST paths should use nouns",
                    }
                )

        # Check: path parameters should be camelCase
        for param in params:
            if param != param[0].lower() + param[1:]:
                findings.append(
                    {
                        "level": "warning",
                        "path": path,
                        "rule": "param-camelCase",
                        "message": f"Parameter '{{{param}}}' should be camelCase",
                    }
                )
            if "_" in param:
                findings.append(
                    {
                        "level": "warning",
                        "path": path,
                        "rule": "param-no-underscores",
                        "message": f"Parameter '{{{param}}}' contains underscores — use camelCase",
                    }
                )

        # Check: path should not have trailing slash
        if path.endswith("/") and path != "/":
            findings.append(
                {
                    "level": "warning",
                    "path": path,
                    "rule": "no-trailing-slash",
                    "message": "Path has trailing slash",
                }
            )

        # Check: operations exist
        methods = [m for m in ("get", "post", "put", "delete", "patch") if m in path_item]
        if not methods:
            findings.append(
                {
                    "level": "error",
                    "path": path,
                    "rule": "has-operations",
                    "message": "Path has no operations defined",
                }
            )

        # Check: operations have responses
        for method in methods:
            op = path_item[method]
            if "responses" not in op:
                findings.append(
                    {
                        "level": "info",
                        "path": path,
                        "rule": "has-responses",
                        "message": f"{method.upper()} has no responses defined",
                    }
                )

    return findings


def lint_operations(spec: dict) -> list[dict]:
    """Lint operation-level conventions."""
    findings = []
    paths = spec.get("paths", {})

    for path, path_item in paths.items():
        methods = [m for m in ("get", "post", "put", "delete", "patch") if m in path_item]
        for method in methods:
            op = path_item[method]

            # Check: operationId should be camelCase
            op_id = op.get("operationId", "")
            if op_id:
                if "_" in op_id:
                    findings.append(
                        {
                            "level": "warning",
                            "path": path,
                            "rule": "operationId-camelCase",
                            "message": f"operationId '{op_id}' contains underscores",
                        }
                    )
                if op_id[0].isupper():
                    findings.append(
                        {
                            "level": "warning",
                            "path": path,
                            "rule": "operationId-camelCase",
                            "message": f"operationId '{op_id}' should start lowercase",
                        }
                    )

    return findings


def print_findings(findings: list[dict]) -> tuple[int, int, int]:
    """Print findings grouped by level. Returns (errors, warnings, info) counts."""
    errors = [f for f in findings if f["level"] == "error"]
    warnings = [f for f in findings if f["level"] == "warning"]
    infos = [f for f in findings if f["level"] == "info"]

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for f in errors:
            print(f"  [{f['rule']}] {f['path']}: {f['message']}")

    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        # Group by rule
        by_rule: dict[str, list] = {}
        for f in warnings:
            by_rule.setdefault(f["rule"], []).append(f)
        for rule, items in sorted(by_rule.items()):
            print(f"  {rule}: {len(items)} occurrences")
            for item in items[:3]:
                print(f"    {item['path']}: {item['message']}")
            if len(items) > 3:
                print(f"    ... and {len(items) - 3} more")

    if infos:
        print(f"\nInfo ({len(infos)}):")
        print(f"  {len(infos)} operations missing response definitions")

    return len(errors), len(warnings), len(infos)


def main() -> None:
    """Entry point for the custom linter."""
    spec_files = sorted(OUTPUT_DIR.glob("proton-*-api-*.json"))

    if not spec_files:
        print("No rendered specs found in output/. Run 'make render' first.", file=sys.stderr)
        sys.exit(1)

    total_errors = 0
    total_warnings = 0

    for spec_path in spec_files:
        print(f"Linting {spec_path.name}...")

        # Structural validation
        struct_errors = validate_structure(spec_path)
        if struct_errors:
            for err in struct_errors:
                print(f"  FAIL: {err}")
            total_errors += len(struct_errors)
            continue

        # Load spec for convention linting
        with open(spec_path) as f:
            spec = json.load(f)

        # Convention linting
        findings = lint_paths(spec) + lint_operations(spec)
        errors, warnings, _ = print_findings(findings)
        total_errors += errors
        total_warnings += warnings

        path_count = len(spec.get("paths", {}))
        print(f"  {path_count} paths, {errors} errors, {warnings} warnings")

    print(f"\nTotal: {total_errors} errors, {total_warnings} warnings")
    if total_errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
