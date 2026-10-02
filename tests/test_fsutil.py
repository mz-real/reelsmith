"""Tests for reelsmith.fsutil."""

from __future__ import annotations

import re
from pathlib import Path

from reelsmith.fsutil import backup_existing, cache_dir


def test_backup_existing_returns_none_for_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "nothing.txt"
    assert backup_existing(missing) is None


def test_backup_existing_renames_a_file(tmp_path: Path) -> None:
    original = tmp_path / "spec.yaml"
    original.write_text("version: 1\n", encoding="utf-8")

    backup = backup_existing(original)

    assert backup is not None
    assert backup.exists()
    assert not original.exists()
    assert backup.read_text(encoding="utf-8") == "version: 1\n"
    assert re.fullmatch(r"spec\.yaml\.bak-\d{8}-\d{6}", backup.name)


def test_backup_existing_renames_a_folder(tmp_path: Path) -> None:
    original = tmp_path / "voice"
    original.mkdir()
    (original / "l1.wav").write_bytes(b"data")

    backup = backup_existing(original)

    assert backup is not None
    assert backup.is_dir()
    assert not original.exists()
    assert (backup / "l1.wav").read_bytes() == b"data"
    assert re.fullmatch(r"voice\.bak-\d{8}-\d{6}", backup.name)


def test_backup_existing_frees_the_original_name(tmp_path: Path) -> None:
    original = tmp_path / "script.yaml"
    original.write_text("version: 1\n", encoding="utf-8")

    backup_existing(original)

    assert not original.exists()
    original.write_text("version: 2\n", encoding="utf-8")
    assert original.read_text(encoding="utf-8") == "version: 2\n"


def test_cache_dir_ends_with_reelsmith(tmp_path: Path) -> None:
    path = cache_dir()
    assert path.name == "reelsmith"
    assert isinstance(path, Path)
