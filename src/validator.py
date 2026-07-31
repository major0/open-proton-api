"""Validate all endpoint JSON files in api/ against schema/endpoint.json."""

import json
import sys
from pathlib import Path

import jsonschema


def load_schema() -> dict:
    """Load the endpoint JSON Schema."""
    schema_path = Path(__file__).parent.parent / "schema" / "endpoint.json"
    with open(schema_path) as f:
        return json.load(f)


def find_endpoint_files(api_dir: Path) -> list[Path]:
    """Find all JSON files in the api/ tree, excluding common.json and meta.json."""
    return sorted(
        p
        for p in api_dir.rglob("*.json")
        if p.name not in ("common.json", "meta.json")
    )


def validate_file(path: Path, schema: dict) -> list[str]:
    """Validate a single endpoint JSON file. Returns list of error messages."""
    errors = []
    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"{path}: invalid JSON: {e}"]

    validator = jsonschema.Draft202012Validator(schema)
    for error in validator.iter_errors(data):
        location = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"{path}: {location}: {error.message}")

    return errors


def main() -> None:
    """Entry point for opa-validate."""
    api_dir = Path(__file__).parent.parent / "api"
    schema = load_schema()

    if not api_dir.exists():
        print("No api/ directory found.", file=sys.stderr)
        sys.exit(1)

    files = find_endpoint_files(api_dir)
    if not files:
        print("No endpoint JSON files found in api/.", file=sys.stderr)
        sys.exit(1)

    all_errors: list[str] = []
    for path in files:
        errors = validate_file(path, schema)
        all_errors.extend(errors)

    if all_errors:
        print(f"Validation failed with {len(all_errors)} error(s):", file=sys.stderr)
        for err in all_errors:
            print(f"  {err}", file=sys.stderr)
        sys.exit(1)

    print(f"Validated {len(files)} file(s) successfully.")


if __name__ == "__main__":
    main()
