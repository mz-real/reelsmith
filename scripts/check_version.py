#!/usr/bin/env python3
"""Fail if project version strings are not all the same.

Checks pyproject.toml, .claude-plugin/plugin.json, marketplace.json
(metadata and each plugin entry), and the version baked into generated
instruction files.

Usage: check_version.py [root]

Exits 0 when every source agrees. Exits 1 and prints what differs.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

INSTRUCTIONS_PROBE = Path("src/reelsmith/agent_files/AGENTS.md")
EXPECTED_LINE = re.compile(r"^These instructions expect reelsmith (.+)\.\s*$", re.MULTILINE)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def pyproject_version(root: Path) -> str:
    data = tomllib.loads(_read_text(root / "pyproject.toml"))
    return str(data["project"]["version"])


def plugin_version(root: Path) -> str:
    data = json.loads(_read_text(root / ".claude-plugin" / "plugin.json"))
    return str(data["version"])


def marketplace_versions(root: Path) -> list[tuple[str, str]]:
    data = json.loads(_read_text(root / ".claude-plugin" / "marketplace.json"))
    found: list[tuple[str, str]] = []
    meta = data.get("metadata") or {}
    if "version" in meta:
        found.append(("marketplace.json metadata.version", str(meta["version"])))
    for index, plugin in enumerate(data.get("plugins") or []):
        if "version" in plugin:
            found.append((f"marketplace.json plugins[{index}].version", str(plugin["version"])))
    return found


def instructions_version(root: Path) -> str | None:
    path = root / INSTRUCTIONS_PROBE
    if not path.is_file():
        return None
    match = EXPECTED_LINE.search(_read_text(path))
    return match.group(1).strip() if match else None


def collect_versions(root: Path) -> dict[str, str]:
    versions: dict[str, str] = {
        "pyproject.toml": pyproject_version(root),
        ".claude-plugin/plugin.json": plugin_version(root),
    }
    for label, value in marketplace_versions(root):
        versions[label] = value
    instr = instructions_version(root)
    if instr is None:
        versions[str(INSTRUCTIONS_PROBE)] = "<missing or unparsable>"
    else:
        versions[str(INSTRUCTIONS_PROBE)] = instr
    return versions


def check(root: Path) -> list[str]:
    versions = collect_versions(root)
    canonical = versions["pyproject.toml"]
    errors: list[str] = []
    for label, value in versions.items():
        if label == "pyproject.toml":
            continue
        if value != canonical:
            errors.append(f"{label} is {value}, expected {canonical} (from pyproject.toml)")
    if versions.get(str(INSTRUCTIONS_PROBE)) == "<missing or unparsable>":
        errors.append(
            f"{INSTRUCTIONS_PROBE} must contain a line like "
            f"'These instructions expect reelsmith {canonical}.'"
        )
    return errors


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    errors = check(root)
    if errors:
        for line in errors:
            print(line)
        print("Fix the mismatch, then run: uv run python scripts/gen_instructions.py")
        return 1
    print(f"All version strings match {pyproject_version(root)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
