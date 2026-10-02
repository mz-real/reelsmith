"""Tests for scripts/check_dashes.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_dashes.py"
EM_DASH = chr(0x2014)


def run_check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root)],
        capture_output=True,
        text=True,
    )


def test_exits_1_and_prints_file_and_line_for_em_dash(tmp_path: Path) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text(f"this has an em dash {EM_DASH} right here\n", encoding="utf-8")

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert f"{bad}:1" in result.stdout


def test_exits_0_on_a_clean_tree(tmp_path: Path) -> None:
    clean = tmp_path / "notes.txt"
    clean.write_text("this has a comma, not a dash\n", encoding="utf-8")

    result = run_check(tmp_path)

    assert result.returncode == 0


def test_skips_git_directory(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "hidden").write_text(f"em dash {EM_DASH} inside git\n", encoding="utf-8")

    result = run_check(tmp_path)

    assert result.returncode == 0


def test_skips_binary_files(tmp_path: Path) -> None:
    binary = tmp_path / "image.bin"
    binary.write_bytes(bytes([0, 1, 2, 0xE2, 0x80, 0x94, 0, 255]))

    result = run_check(tmp_path)

    assert result.returncode == 0
