"""Extractor for protoncore-android (Kotlin Retrofit interfaces)."""

import sys

from src.extractors.kotlin_retrofit import SOURCES_DIR, extract_source


def main() -> None:
    """Entry point for protoncore-android extractor."""
    source_dir = SOURCES_DIR / "protoncore-android"
    if not source_dir.exists():
        print(f"Error: source not found at {source_dir}", file=sys.stderr)
        sys.exit(1)
    count = extract_source(source_dir, "protoncore-android")
    print(f"Extracted {count} endpoints from protoncore-android")


if __name__ == "__main__":
    main()
