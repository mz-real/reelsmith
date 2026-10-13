"""Gradium cloud text to speech."""

from __future__ import annotations

import io
import json
import os
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from reelsmith.errors import ReelsmithError
from reelsmith.voice.base import Audio
from reelsmith.voice.cloud_http import multipart_body, read_file_bytes, request_bytes

_HOST = "api.gradium.ai"


def default_api_key_env() -> str:
    return "GRADIUM_API_KEY"


def _api_key(api_key_env: str) -> str:
    value = os.environ.get(api_key_env, "").strip()
    if not value:
        raise ReelsmithError(
            f"Set {api_key_env} in your environment before using Gradium.",
            fix=f"export {api_key_env}=your_key",
        )
    return value


def _wav_to_audio(data: bytes) -> Audio:
    with wave.open(io.BytesIO(data), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())
    if sample_width != 2:
        raise ReelsmithError("Gradium returned audio reelsmith cannot read.")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return Audio(samples=samples, sample_rate=sample_rate)


@dataclass
class GradiumEngine:
    voice_id: str
    api_key_env: str = default_api_key_env()
    name: str = "gradium"
    controls_rate: bool = False

    def synthesize(self, text: str, seed: int, speed: float | None = None) -> Audio:
        key = _api_key(self.api_key_env)
        payload = {
            "text": text,
            "voice_id": self.voice_id,
            "output_format": "wav",
            "only_audio": True,
        }
        raw = request_bytes(
            "POST",
            f"https://{_HOST}/api/post/speech/tts",
            headers={"x-api-key": key, "Content-Type": "application/json"},
            body=json.dumps(payload).encode("utf-8"),
            api_key_env=self.api_key_env,
            voice_id=self.voice_id,
        )
        return _wav_to_audio(raw)


def clone_voice(
    sample: Path,
    name: str,
    *,
    api_key_env: str = default_api_key_env(),
) -> str:
    key = _api_key(api_key_env)
    content = read_file_bytes(sample)
    body, content_type = multipart_body(
        {"name": name, "language": "en"},
        [("audio_file", sample.name, content)],
    )
    raw = request_bytes(
        "POST",
        f"https://{_HOST}/api/voices/",
        headers={"x-api-key": key, "Content-Type": content_type},
        body=body,
        api_key_env=api_key_env,
    )
    data = json.loads(raw.decode("utf-8"))
    voice_id = data.get("uid")
    if not isinstance(voice_id, str) or not voice_id:
        raise ReelsmithError(
            "Gradium did not return a voice id.",
            fix="Check the sample and try again.",
        )
    return voice_id


def delete_voice(voice_id: str, *, api_key_env: str = default_api_key_env()) -> None:
    key = _api_key(api_key_env)
    request_bytes(
        "DELETE",
        f"https://{_HOST}/api/voices/{voice_id}",
        headers={"x-api-key": key},
        body=None,
        api_key_env=api_key_env,
        voice_id=voice_id,
    )


def host() -> str:
    return _HOST
