"""Tests for reelsmith.voice.models_dl."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from reelsmith.errors import ReelsmithError
from reelsmith.voice import models_dl


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._buf.read(size)


def _fake_spec(payload: bytes, filename: str = "fake.bin") -> models_dl.ModelSpec:
    return models_dl.ModelSpec(
        filename=filename,
        url=f"https://example.invalid/{filename}",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def test_ensure_model_unknown_name_raises() -> None:
    with pytest.raises(ReelsmithError):
        models_dl.ensure_model("not-a-real-model")


def test_ensure_model_returns_cached_file_without_downloading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"already cached bytes"
    spec = _fake_spec(payload)
    monkeypatch.setattr(models_dl, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(models_dl, "_MODELS", {spec.filename: spec})

    dest_dir = tmp_path / "models"
    dest_dir.mkdir(parents=True)
    (dest_dir / spec.filename).write_bytes(payload)

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("should not download a file already cached")

    monkeypatch.setattr(models_dl.urllib.request, "urlopen", _boom)

    result = models_dl.ensure_model(spec.filename)

    assert result == dest_dir / spec.filename


def test_ensure_model_downloads_and_verifies_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"freshly downloaded bytes"
    spec = _fake_spec(payload)
    monkeypatch.setattr(models_dl, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(models_dl, "_MODELS", {spec.filename: spec})
    monkeypatch.setattr(
        models_dl.urllib.request,
        "urlopen",
        lambda url, timeout=30: _FakeResponse(payload),
    )

    result = models_dl.ensure_model(spec.filename)

    assert result.read_bytes() == payload
    assert not result.with_name(result.name + ".part").exists()


def test_ensure_model_raises_with_retry_command_on_network_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _fake_spec(b"whatever")
    monkeypatch.setattr(models_dl, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(models_dl, "_MODELS", {spec.filename: spec})

    def _raise(*args: object, **kwargs: object) -> None:
        raise models_dl.urllib.error.URLError("offline")

    monkeypatch.setattr(models_dl.urllib.request, "urlopen", _raise)

    with pytest.raises(ReelsmithError) as excinfo:
        models_dl.ensure_model(spec.filename)

    assert excinfo.value.fix is not None
    assert spec.url in excinfo.value.fix
    assert "curl" in excinfo.value.fix


def test_ensure_model_raises_on_checksum_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = models_dl.ModelSpec(
        filename="fake.bin",
        url="https://example.invalid/fake.bin",
        sha256="0" * 64,
        size_bytes=4,
    )
    monkeypatch.setattr(models_dl, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(models_dl, "_MODELS", {spec.filename: spec})
    monkeypatch.setattr(
        models_dl.urllib.request,
        "urlopen",
        lambda url, timeout=30: _FakeResponse(b"not a match"),
    )

    with pytest.raises(ReelsmithError) as excinfo:
        models_dl.ensure_model(spec.filename)

    assert "checksum" in str(excinfo.value)
    assert not (tmp_path / "models" / "fake.bin").exists()
