"""Shared pytest fixtures for the qa tests."""

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "models: needs a real downloaded model, skipped unless REELSMITH_TEST_MODELS=1"
    )


@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "work"
    directory.mkdir()
    return directory
