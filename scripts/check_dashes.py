#!/usr/bin/env python3
"""Fail if any tracked text file contains an em dash or en dash.

Usage: check_dashes.py [root]

Exits 1 and prints one ``path:line`` per hit if any are found. Exits 0 on a
clean tree. Skips ``.git`` folders and files that look binary.
"""

from __future__ import annotations

import sys
from pathlib import Path

EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)
BAD_CHARS = (EM_DASH, EN_DASH)

SKIP_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}


def _is_binary(data: bytes) -> bool:
    return b"\x00" in data


def _iter_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def check(root: Path) -> list[str]:
    hits: list[str] = []
    for path in sorted(_iter_files(root)):
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if _is_binary(raw):
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(char in line for char in BAD_CHARS):
                hits.append(f"{path}:{line_number}")
    return hits


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    hits = check(root)
    if hits:
        for hit in hits:
            print(hit)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
