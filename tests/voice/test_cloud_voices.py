"""Cloud voice engines and commands (mocked HTTP)."""

from __future__ import annotations

import io
import json
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from reelsmith.errors import ReelsmithError
from reelsmith.models import SpecModel
from reelsmith.voice import cloud_http, elevenlabs_engine, gradium_engine
from reelsmith.voice.elevenlabs_engine import ElevenLabsEngine, clone_voice, delete_voice
from reelsmith.voice.gradium_engine import GradiumEngine


def _pcm_bytes(samples: int = 200) -> bytes:
    return (np.zeros(samples, dtype="<i2")).tobytes()


def _wav_bytes(sample_rate: int = 24000, frames: int = 100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes((np.zeros(frames, dtype="<i2")).tobytes())
    return buf.getvalue()


def test_elevenlabs_tts_sends_expected_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-value")

    def fake_request_bytes(method: str, url: str, **kwargs: Any) -> bytes:
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["body"] = kwargs.get("body")
        return _pcm_bytes()

    monkeypatch.setattr(elevenlabs_engine, "request_bytes", fake_request_bytes)
    engine = ElevenLabsEngine(voice_id="voice-abc")
    audio = engine.synthesize("Hello there.", seed=0)
    assert audio.sample_rate == 44100
    assert captured["method"] == "POST"
    assert "voice-abc" in captured["url"]
    assert captured["headers"]["xi-api-key"] == "test-key-value"
    payload = json.loads(captured["body"].decode())
    assert payload["text"] == "Hello there."
    assert payload["model_id"] == "eleven_multilingual_v2"
    assert engine.controls_rate is False


def test_gradium_decodes_wav(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRADIUM_API_KEY", "g-key")

    def fake_request_bytes(method: str, url: str, **kwargs: Any) -> bytes:
        assert kwargs["headers"]["x-api-key"] == "g-key"
        body = json.loads(kwargs["body"].decode())
        assert body["voice_id"] == "uid-1"
        return _wav_bytes()

    monkeypatch.setattr(gradium_engine, "request_bytes", fake_request_bytes)
    engine = GradiumEngine(voice_id="uid-1")
    audio = engine.synthesize("Hi", seed=0)
    assert audio.sample_rate == 24000
    assert audio.samples.size == 100


def test_retry_on_503(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    attempts = 0

    class Resp:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def getcode(self) -> int:
            return 200

        def read(self) -> bytes:
            return self._data

        def __enter__(self) -> Resp:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def fake_urlopen(_req: Any, timeout: int = 0) -> Resp:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise urllib.error.HTTPError("https://example.com", 503, "busy", None, io.BytesIO(b""))
        return Resp(_pcm_bytes())

    monkeypatch.setattr(cloud_http.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(cloud_http.time, "sleep", lambda _s: None)
    cloud_http.request_bytes(
        "GET",
        "https://example.com",
        headers={},
        api_key_env="ELEVENLABS_API_KEY",
    )
    assert attempts == 3


def test_401_names_env_var_not_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    def boom(*_a: Any, **_k: Any) -> bytes:
        raise AssertionError("should not be called")

    monkeypatch.setattr(elevenlabs_engine, "request_bytes", boom)
    engine = ElevenLabsEngine(voice_id="v", api_key_env="ELEVENLABS_API_KEY")
    with pytest.raises(ReelsmithError) as exc:
        engine.synthesize("hi", 0)
    message = str(exc.value)
    assert "ELEVENLABS_API_KEY" in message
    assert "test-key" not in message


def test_clone_refuses_without_consent(tmp_path: Path) -> None:
    from reelsmith.cli import app, run

    root = tmp_path / "demo"
    root.mkdir()
    (root / "spec.yaml").write_text(
        "version: 1\nmode: produce\nvoice:\n  engine: elevenlabs\n",
        encoding="utf-8",
    )
    sample = tmp_path / "s.wav"
    sample.write_bytes(_wav_bytes())
    code = run(
        app,
        [
            "voice",
            "clone",
            str(root),
            "--provider",
            "elevenlabs",
            "--sample",
            str(sample),
            "--name",
            "n",
            "--consent",
            "neither",
        ],
    )
    assert code != 0


def test_clone_writes_provider_voice_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from reelsmith.cli import app, run

    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    root = tmp_path / "demo"
    root.mkdir()
    (root / "spec.yaml").write_text(
        "version: 1\nmode: produce\nvoice:\n  engine: elevenlabs\n",
        encoding="utf-8",
    )
    sample = tmp_path / "s.wav"
    sample.write_bytes(_wav_bytes())

    def fake_clone(sample_path: Path, name: str, *, api_key_env: str) -> str:
        assert api_key_env == "ELEVENLABS_API_KEY"
        return "new-voice-id"

    monkeypatch.setattr("reelsmith.commands.voice.elevenlabs_clone", fake_clone)
    code = run(
        app,
        [
            "voice",
            "clone",
            str(root),
            "--provider",
            "elevenlabs",
            "--sample",
            str(sample),
            "--name",
            "Demo",
            "--consent",
            "own",
        ],
    )
    assert code == 0
    data = yaml.safe_load((root / "spec.yaml").read_text(encoding="utf-8"))
    assert data["voice"]["provider_voice_id"] == "new-voice-id"


def test_elevenlabs_clone_multipart(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    captured: dict[str, Any] = {}

    def fake_request_bytes(method: str, url: str, **kwargs: Any) -> bytes:
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["body"] = kwargs["body"]
        return json.dumps({"voice_id": "cloned-1"}).encode()

    monkeypatch.setattr(elevenlabs_engine, "request_bytes", fake_request_bytes)
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"abc")
    voice_id = clone_voice(sample, "My voice")
    assert voice_id == "cloned-1"
    assert "voices/add" in captured["url"]
    assert "multipart" in captured["headers"]["Content-Type"]
    assert b"sample.wav" in captured["body"]


def test_delete_voice_calls_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    seen: list[str] = []

    def fake_request_bytes(method: str, url: str, **kwargs: Any) -> bytes:
        seen.append(method + " " + url)
        return b""

    monkeypatch.setattr(elevenlabs_engine, "request_bytes", fake_request_bytes)
    delete_voice("vid-9")
    assert seen == ["DELETE https://api.elevenlabs.io/v1/voices/vid-9"]


def test_get_engine_requires_provider_voice_id(tmp_path: Path) -> None:
    from reelsmith.voice.base import get_engine

    spec = SpecModel.model_validate(
        {"version": 1, "mode": "produce", "voice": {"engine": "gradium"}}
    )
    with pytest.raises(ReelsmithError) as exc:
        get_engine(spec)
    assert "provider_voice_id" in str(exc.value)
