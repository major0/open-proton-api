"""Extractor for android-pass (Kotlin Retrofit interfaces)."""

import sys

from src.extractors.kotlin_retrofit import SOURCES_DIR, extract_source


def main() -> None:
    """Entry point for android-pass extractor."""
    source_dir = SOURCES_DIR / "android-pass"
    if not source_dir.exists():
        print(f"Error: source not found at {source_dir}", file=sys.stderr)
        sys.exit(1)
    count = extract_source(source_dir, "android-pass")
    print(f"Extracted {count} endpoints from android-pass")


if __name__ == "__main__":
    main()
