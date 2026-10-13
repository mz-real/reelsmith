"""Small updates to voice fields in spec.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from reelsmith.fsutil import backup_existing


def patch_voice_fields(spec_path: Path, **fields: Any) -> None:
    """Merge fields into the voice block of spec.yaml."""
    data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        data = {}
    voice = data.get("voice")
    if not isinstance(voice, dict):
        voice = {}
    voice.update(fields)
    data["voice"] = voice
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    backup_existing(spec_path)
    spec_path.write_text(text, encoding="utf-8")
