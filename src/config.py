"""Configuration reader for sources.yaml."""

import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "sources.yaml"


def load_config() -> dict:
    """Load and return the sources.yaml configuration."""
    if not CONFIG_PATH.exists():
        print(f"Error: {CONFIG_PATH} not found", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def enabled_sources() -> dict[str, dict]:
    """Return only enabled sources from config."""
    config = load_config()
    return {
        name: source
        for name, source in config.get("sources", {}).items()
        if source.get("enabled", True)
    }


def enabled_extractors() -> list[str]:
    """Return list of enabled extractor module names."""
    extractors = []
    for source in enabled_sources().values():
        for ext in source.get("extractors", []):
            if ext not in extractors:
                extractors.append(ext)
    return extractors


def main() -> None:
    """CLI interface for querying config.

    Usage:
        python -m src.config sources    # print enabled source names
        python -m src.config urls       # print name=url pairs for fetch
        python -m src.config extractors # print enabled extractor modules
    """
    if len(sys.argv) < 2:
        print("Usage: python -m src.config [sources|urls|extractors]", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "sources":
        for name in enabled_sources():
            print(name)
    elif cmd == "urls":
        for name, source in enabled_sources().items():
            print(f"{name} {source['url']}")
    elif cmd == "extractors":
        for ext in enabled_extractors():
            print(ext)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
