"""Extractor for ios-pass (Swift Endpoint pattern)."""

import sys

from src.extractors.swift_endpoint import SOURCES_DIR, extract_source


def main() -> None:
    """Entry point for ios-pass extractor."""
    source_dir = SOURCES_DIR / "ios-pass"
    if not source_dir.exists():
        print(f"Error: source not found at {source_dir}", file=sys.stderr)
        sys.exit(1)
    count = extract_source(source_dir, "ios-pass")
    print(f"Extracted {count} endpoints from ios-pass")


if __name__ == "__main__":
    main()
