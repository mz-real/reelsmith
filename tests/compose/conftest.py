"""A small demo folder for compose and export tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from PIL import Image, ImageDraw

SPEC = {
    "version": 1,
    "formats": ["16:9"],
    "theme": "dark",
    "scenes": [
        {"id": "intro", "layout": "slide", "slide": "intro"},
        {"id": "search", "layout": "browser", "clip": "search"},
    ],
    "blur": [{"clip": "search", "box": [0.05, 0.05, 0.30, 0.10], "start": 0.0, "end": None}],
}

SCRIPT = {
    "version": 1,
    "scenes": [
        {
            "id": "intro",
            "caption": "Recipe Box",
            "lines": [
                {
                    "id": "l1",
                    "phrases": [
                        {"text": "Recipe Box keeps the dishes you love in one place."},
                        {"text": "Here is how to find one again in seconds."},
                    ],
                }
            ],
        },
        {
            "id": "search",
            "caption": "Find a recipe fast",
            "lines": [
                {
                    "id": "l1",
                    "phrases": [
                        {"text": "Type a dish into the search box.", "pin": "e1"},
                        {"text": "Results update as you type, then tap Back to go home."},
                    ],
                }
            ],
        },
    ],
}

CLIP = {
    "id": "search",
    "video": "video.mp4",
    "width": 640,
    "height": 400,
    "fps": 30,
    "duration": 5.0,
    "events": [
        {"id": "e1", "t": 1.0, "type": "tap", "x": 0.42, "y": 0.18, "label": "Search box"},
        {"id": "e2", "t": 4.0, "type": "back"},
    ],
}

TIMINGS = {
    "engine": "kokoro",
    "voice": "af_heart",
    "lines": [
        {
            "scene": "intro",
            "line": "l1",
            "file": "intro__l1.wav",
            "duration": 4.0,
            "hash": "x",
            "phrases": [
                {"index": 0, "start": 0.0, "end": 1.9},
                {"index": 1, "start": 2.1, "end": 4.0},
            ],
            "wpm": 160.0,
            "transcript_ok": True,
            "attempts": 1,
        },
        {
            "scene": "search",
            "line": "l1",
            "file": "search__l1.wav",
            "duration": 4.0,
            "hash": "y",
            "phrases": [
                {"index": 0, "start": 0.0, "end": 1.6},
                {"index": 1, "start": 1.8, "end": 4.0},
            ],
            "wpm": 165.0,
            "transcript_ok": True,
            "attempts": 1,
        },
    ],
}


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def _slide(path: Path) -> None:
    image = Image.new("RGB", (1920, 1080), "#1e3a8a")
    draw = ImageDraw.Draw(image)
    draw.rectangle((160, 160, 1760, 920), outline="#facc15", width=12)
    draw.ellipse((860, 440, 1060, 640), fill="#facc15")
    image.save(path)


def make_demo(root: Path, *, media: bool) -> Path:
    """Write spec, script, clip and timings. With media, also slides, wavs and video."""
    (root / "capture" / "clips" / "search").mkdir(parents=True)
    (root / "voice").mkdir()
    (root / "slides").mkdir()
    (root / "spec.yaml").write_text(yaml.safe_dump(SPEC), encoding="utf-8")
    (root / "script.yaml").write_text(yaml.safe_dump(SCRIPT), encoding="utf-8")
    clip_dir = root / "capture" / "clips" / "search"
    (clip_dir / "clip.json").write_text(json.dumps(CLIP), encoding="utf-8")
    (root / "voice" / "timings.json").write_text(json.dumps(TIMINGS), encoding="utf-8")
    if not media:
        return root
    _slide(root / "slides" / "intro.png")
    for name, freq in (("intro__l1.wav", 440), ("search__l1.wav", 660)):
        _ffmpeg(
            "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=4", str(root / "voice" / name)
        )
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=5:size=640x400:rate=30",
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        str(clip_dir / "video.mp4"),
    )
    return root


@pytest.fixture
def demo(tmp_path: Path) -> Path:
    return make_demo(tmp_path / "my demo", media=False)


@pytest.fixture
def media_demo(tmp_path: Path) -> Path:
    """The demo folder with real slide, tone and video files."""
    return make_demo(tmp_path / "smoke demo é", media=True)


@pytest.fixture
def ready(demo: Path) -> Path:
    (demo / "voice" / "intro__l1.wav").write_bytes(b"wav1")
    (demo / "voice" / "search__l1.wav").write_bytes(b"wav2")
    (demo / "capture" / "clips" / "search" / "video.mp4").write_bytes(b"mp4")
    Image.new("RGB", (192, 108), "navy").save(demo / "slides" / "intro.png")
    return demo
