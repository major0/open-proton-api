"""Extractor for android-drive (Kotlin Retrofit interfaces)."""

import sys

from src.extractors.kotlin_retrofit import SOURCES_DIR, extract_source


def main() -> None:
    """Entry point for android-drive extractor."""
    source_dir = SOURCES_DIR / "android-drive"
    if not source_dir.exists():
        print(f"Error: source not found at {source_dir}", file=sys.stderr)
        sys.exit(1)
    count = extract_source(source_dir, "android-drive")
    print(f"Extracted {count} endpoints from android-drive")


if __name__ == "__main__":
    main()
