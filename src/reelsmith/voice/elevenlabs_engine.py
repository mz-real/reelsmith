"""ElevenLabs cloud text to speech."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from reelsmith.errors import ReelsmithError
from reelsmith.voice.base import Audio
from reelsmith.voice.cloud_http import multipart_body, read_file_bytes, request_bytes

_DEFAULT_MODEL = "eleven_multilingual_v2"
_HOST = "api.elevenlabs.io"


def default_api_key_env() -> str:
    return "ELEVENLABS_API_KEY"


def _api_key(api_key_env: str) -> str:
    value = os.environ.get(api_key_env, "").strip()
    if not value:
        raise ReelsmithError(
            f"Set {api_key_env} in your environment before using ElevenLabs.",
            fix=f"export {api_key_env}=your_key",
        )
    return value


def _pcm_to_audio(data: bytes, sample_rate: int = 44100) -> Audio:
    if len(data) % 2 != 0:
        raise ReelsmithError("ElevenLabs returned invalid PCM audio.")
    samples = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
    return Audio(samples=samples, sample_rate=sample_rate)


@dataclass
class ElevenLabsEngine:
    voice_id: str
    api_key_env: str = default_api_key_env()
    model: str = _DEFAULT_MODEL
    name: str = "elevenlabs"
    controls_rate: bool = False

    def synthesize(self, text: str, seed: int, speed: float | None = None) -> Audio:
        key = _api_key(self.api_key_env)
        url = f"https://{_HOST}/v1/text-to-speech/{self.voice_id}?output_format=pcm_44100"
        payload = {"text": text, "model_id": self.model}
        raw = request_bytes(
            "POST",
            url,
            headers={
                "xi-api-key": key,
                "Content-Type": "application/json",
                "Accept": "audio/pcm",
            },
            body=json.dumps(payload).encode("utf-8"),
            api_key_env=self.api_key_env,
            voice_id=self.voice_id,
        )
        return _pcm_to_audio(raw)


def clone_voice(
    sample: Path,
    name: str,
    *,
    api_key_env: str = default_api_key_env(),
) -> str:
    key = _api_key(api_key_env)
    content = read_file_bytes(sample)
    body, content_type = multipart_body(
        {"name": name},
        [("files", sample.name, content)],
    )
    raw = request_bytes(
        "POST",
        f"https://{_HOST}/v1/voices/add",
        headers={"xi-api-key": key, "Content-Type": content_type},
        body=body,
        api_key_env=api_key_env,
    )
    data = json.loads(raw.decode("utf-8"))
    voice_id = data.get("voice_id")
    if not isinstance(voice_id, str) or not voice_id:
        raise ReelsmithError(
            "ElevenLabs did not return a voice id.",
            fix="Check the sample and try again.",
        )
    return voice_id


def delete_voice(voice_id: str, *, api_key_env: str = default_api_key_env()) -> None:
    key = _api_key(api_key_env)
    request_bytes(
        "DELETE",
        f"https://{_HOST}/v1/voices/{voice_id}",
        headers={"xi-api-key": key},
        body=None,
        api_key_env=api_key_env,
        voice_id=voice_id,
    )


def host() -> str:
    return _HOST
