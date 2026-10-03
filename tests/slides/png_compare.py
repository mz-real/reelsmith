"""Compare rendered slide PNGs for tests."""

from __future__ import annotations

from pathlib import Path


def assert_render_pair_equal(left: Path, right: Path, *, name: str) -> None:
    if left.read_bytes() == right.read_bytes():
        return
    raise AssertionError(f"{name}: bytes differ")
