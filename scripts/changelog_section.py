#!/usr/bin/env python3
"""Print the CHANGELOG section for one release version.

Usage: changelog_section.py VERSION [changelog_path]

VERSION is X.Y.Z (a leading v is stripped). Prints from the matching
``## [X.Y.Z]`` heading through the line before the next version heading.
Exits 1 if that section is not found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SECTION_START = re.compile(r"^## \[(?P<ver>[^\]]+)\]", re.MULTILINE)


def normalize_version(raw: str) -> str:
    text = raw.strip()
    if text.startswith("v") or text.startswith("V"):
        return text[1:]
    return text


def section_for(text: str, version: str) -> str | None:
    """Return the changelog block for version, including its ## header."""
    version = normalize_version(version)
    matches = list(SECTION_START.finditer(text))
    for index, match in enumerate(matches):
        heading_version = match.group("ver").split("-", 1)[0].strip()
        if heading_version != version:
            continue
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end].rstrip()
        return block + "\n" if block else None
    return None


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: changelog_section.py VERSION [changelog_path]", file=sys.stderr)
        return 1
    version = normalize_version(args[0])
    changelog = Path(args[1]) if len(args) > 1 else Path("CHANGELOG.md")
    if not changelog.is_file():
        print(f"changelog not found: {changelog}", file=sys.stderr)
        return 1
    block = section_for(changelog.read_text(encoding="utf-8"), version)
    if block is None:
        print(f"no changelog section for version {version}", file=sys.stderr)
        return 1
    sys.stdout.write(block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
