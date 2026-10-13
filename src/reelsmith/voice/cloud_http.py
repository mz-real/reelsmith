"""HTTP helpers for cloud voice providers (urllib only)."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from reelsmith.errors import ReelsmithError

_RETRY_STATUS = frozenset({502, 503, 504})
_MAX_ATTEMPTS = 4  # first try plus 3 retries
_BACKOFF_SECONDS = (0.5, 1.0, 2.0)


def resolve_host(host: str) -> str:
    """Return a short message after checking the host resolves."""
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        return f"cannot resolve {host}: {exc}"
    return f"{host} resolves"


def _sleep_before_retry(attempt: int) -> None:
    if attempt < len(_BACKOFF_SECONDS):
        time.sleep(_BACKOFF_SECONDS[attempt])


def _cloud_error(
    status: int,
    body: bytes,
    *,
    api_key_env: str,
    voice_id: str | None = None,
) -> ReelsmithError:
    text = body.decode("utf-8", errors="replace").strip()
    if status == 401:
        return ReelsmithError(
            f"The API key in {api_key_env} is missing or not accepted.",
            fix=f"Set {api_key_env} in your environment and run the command again.",
        )
    if status == 404 and voice_id:
        return ReelsmithError(
            f"Voice id {voice_id!r} was not found at the provider.",
            fix="Check voice.provider_voice_id in spec.yaml or clone again.",
        )
    if status == 429:
        return ReelsmithError(
            "The provider refused the request because of rate limits or quota.",
            fix="Wait a moment and try again, or check your provider account.",
        )
    detail = text[:200] if text else f"HTTP {status}"
    return ReelsmithError(
        f"Cloud voice request failed ({status}): {detail}",
        fix="Check your network and provider status, then try again.",
    )


def request_bytes(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    body: bytes | None = None,
    api_key_env: str,
    voice_id: str | None = None,
) -> bytes:
    """Send an HTTP request with retries on 502, 503, 504 and network errors."""
    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        req = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                status = resp.getcode() or 200
                data = resp.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            data = exc.read()
            if status in _RETRY_STATUS and attempt < _MAX_ATTEMPTS - 1:
                _sleep_before_retry(attempt)
                continue
            raise _cloud_error(status, data, api_key_env=api_key_env, voice_id=voice_id) from None
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < _MAX_ATTEMPTS - 1:
                _sleep_before_retry(attempt)
                continue
            raise ReelsmithError(
                f"Could not reach the voice provider: {exc.reason}",
                fix="Check your network connection and try again.",
            ) from None
        else:
            if status in _RETRY_STATUS and attempt < _MAX_ATTEMPTS - 1:
                _sleep_before_retry(attempt)
                continue
            if status >= 400:
                raise _cloud_error(status, data, api_key_env=api_key_env, voice_id=voice_id)
            return cast(bytes, data)
    raise ReelsmithError(
        "Could not reach the voice provider after several tries.",
        fix="Check your network connection and try again.",
    ) from last_error


def request_json(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    json_body: object | None,
    api_key_env: str,
    voice_id: str | None = None,
) -> object:
    body = None
    merged = dict(headers)
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        merged.setdefault("Content-Type", "application/json")
    raw = request_bytes(
        method, url, headers=merged, body=body, api_key_env=api_key_env, voice_id=voice_id
    )
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def multipart_body(
    fields: Mapping[str, str],
    files: Sequence[tuple[str, str, bytes]],
) -> tuple[bytes, str]:
    """Build multipart/form-data. files entries are (field_name, filename, content)."""
    boundary = f"reelsmith-{uuid.uuid4().hex}"
    lines: list[bytes] = []
    for key, value in fields.items():
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        lines.append(value.encode("utf-8"))
        lines.append(b"\r\n")
    for field_name, filename, content in files:
        lines.append(f"--{boundary}\r\n".encode())
        disposition = (
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        )
        lines.append(disposition.encode())
        lines.append(b"Content-Type: application/octet-stream\r\n\r\n")
        lines.append(content)
        lines.append(b"\r\n")
    lines.append(f"--{boundary}--\r\n".encode())
    body = b"".join(lines)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def read_file_bytes(path: Path, limit_mb: int = 25) -> bytes:
    data = path.read_bytes()
    if len(data) > limit_mb * 1024 * 1024:
        raise ReelsmithError(
            f"Sample file is larger than {limit_mb} MB.",
            fix="Use a shorter clip for cloning.",
        )
    return data
