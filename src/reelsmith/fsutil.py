"""File system helpers: safe backups and the shared cache folder."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from platformdirs import user_cache_dir


def backup_existing(path: Path) -> Path | None:
    """Rename an existing file or folder out of the way.

    Returns the new path, or None if nothing was there to back up. The
    backup name is ``<name>.bak-YYYYmmdd-HHMMSS``, so the original name is
    free for the caller to write to right after.
    """
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.move(str(path), str(backup))
    return backup


def cache_dir() -> Path:
    """The folder reelsmith caches downloaded models in."""
    return Path(user_cache_dir("reelsmith"))
