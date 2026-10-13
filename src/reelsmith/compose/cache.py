"""The scene cache: a scene is rebuilt only when its inputs change."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path

KEY_LENGTH = 16


@lru_cache(maxsize=512)
def _digest(path: str, size: int, mtime_ns: int) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(block)
    return hasher.hexdigest()


def file_digest(path: Path) -> str:
    """sha256 of a file, or "missing" when it does not exist."""
    if not path.is_file():
        return "missing"
    stat = path.stat()
    return _digest(str(path), stat.st_size, stat.st_mtime_ns)


def scene_key(payload: Mapping[str, object], files: Sequence[Path]) -> str:
    """A hash of the scene settings and the content of every input file."""
    data = {
        "payload": payload,
        "files": [[path.name, file_digest(path)] for path in files],
    }
    text = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def scene_path(scenes_dir: Path, scene_id: str, key: str) -> Path:
    return scenes_dir / f"{scene_id}-{key[:KEY_LENGTH]}.mp4"


def is_cached(path: Path) -> bool:
    """A finished scene file. Renders go to a temp name first, so a crash
    never leaves a half written file under this name."""
    return path.is_file() and path.stat().st_size > 0


@lru_cache(maxsize=1)
def render_code_fingerprint() -> str:
    """A hash of the compose and slide code, so an upgrade or a local edit rebuilds scenes.

    The package version alone misses changes between releases and in editable installs.
    """
    return code_fingerprint(Path(__file__).resolve().parent.parent)


def code_fingerprint(root: Path) -> str:
    """The hash behind render_code_fingerprint, for any package root."""
    digest = hashlib.sha256()
    for folder in ("compose", "slides"):
        for path in sorted((root / folder).glob("*.py")):
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]
