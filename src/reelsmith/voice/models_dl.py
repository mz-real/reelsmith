"""Downloads the Kokoro model files into the user cache, with a checksum.

Files come from the thewh1teagle/kokoro-onnx GitHub release tag
model-files-v1.1. The URLs and sha256 sums below were verified by
downloading each file once and hashing it.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from reelsmith import progress
from reelsmith.errors import ReelsmithError
from reelsmith.fsutil import cache_dir

_RELEASE_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"


@dataclass(frozen=True)
class ModelSpec:
    filename: str
    url: str
    sha256: str
    size_bytes: int


KOKORO_INT8 = ModelSpec(
    filename="kokoro-v1.0.int8.onnx",
    url=f"{_RELEASE_URL}/kokoro-v1.0.int8.onnx",
    sha256="ae315a79b623f244700e4afb9246c46a26066782e049ba174bf3ba433970ee9c",
    size_bytes=114_119_327,
)

KOKORO_FULL = ModelSpec(
    filename="kokoro-v1.0.onnx",
    url=f"{_RELEASE_URL}/kokoro-v1.0.onnx",
    sha256="beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a",
    size_bytes=325_505_369,
)

KOKORO_VOICES = ModelSpec(
    filename="voices-v1.0.bin",
    url=f"{_RELEASE_URL}/voices-v1.0.bin",
    sha256="bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
    size_bytes=28_214_398,
)

_MODELS: dict[str, ModelSpec] = {
    spec.filename: spec for spec in (KOKORO_INT8, KOKORO_FULL, KOKORO_VOICES)
}


def models_dir() -> Path:
    """The folder model files are downloaded into."""
    return cache_dir() / "models"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manual_fix(spec: ModelSpec, dest: Path) -> str:
    return f"curl -L -o {dest} {spec.url}"


_CHUNK = 1 << 20


def _copy_with_progress(response: BinaryIO, out: BinaryIO, spec: ModelSpec) -> None:
    label = f"Downloading {spec.filename}"
    done = 0
    while chunk := response.read(_CHUNK):
        out.write(chunk)
        done += len(chunk)
        progress.transfer(label, done, max(spec.size_bytes, done))


def ensure_model(name: str) -> Path:
    """Return the local path to a model file, downloading it if needed.

    name is a model filename, such as "kokoro-v1.0.int8.onnx". The size is
    printed before downloading. The download is verified against a known
    sha256. A network failure or a checksum mismatch raises a
    ReelsmithError whose fix is the exact command to download the file by
    hand, which also names the manual download URL.
    """
    spec = _MODELS.get(name)
    if spec is None:
        raise ReelsmithError(f"Unknown model: {name}")

    dest_dir = models_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / spec.filename

    if dest.exists() and _sha256(dest) == spec.sha256:
        return dest

    size_mb = spec.size_bytes / (1024 * 1024)
    # stderr, so the result block on stdout stays clean.
    print(f"Downloading {spec.filename} ({size_mb:.0f} MB) to {dest_dir}", file=sys.stderr)

    tmp_path = dest.with_name(dest.name + ".part")
    try:
        with (
            urllib.request.urlopen(spec.url, timeout=30) as response,
            tmp_path.open("wb") as out,
        ):
            _copy_with_progress(response, out, spec)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        tmp_path.unlink(missing_ok=True)
        raise ReelsmithError(
            f"Could not download {spec.filename}: {exc}",
            fix=_manual_fix(spec, dest),
        ) from exc

    actual = _sha256(tmp_path)
    if actual != spec.sha256:
        tmp_path.unlink(missing_ok=True)
        raise ReelsmithError(
            f"Downloaded {spec.filename} does not match the expected checksum.",
            fix=_manual_fix(spec, dest),
        )

    shutil.move(str(tmp_path), str(dest))
    return dest
