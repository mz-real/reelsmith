"""Shared fixtures for integration tests."""

from __future__ import annotations

import shutil

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: full pipeline test with ffmpeg and optional Playwright",
    )


@pytest.fixture(scope="session")
def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg and ffprobe are required for integration tests")
