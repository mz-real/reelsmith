"""Build a small demo folder for integration smoke tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml
from PIL import Image, ImageDraw


def ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
        check=True,
    )


def write_slide(path: Path, label: str) -> None:
    image = Image.new("RGB", (1920, 1080), "#1e3a8a")
    draw = ImageDraw.Draw(image)
    draw.rectangle((160, 160, 1760, 920), outline="#facc15", width=12)
    draw.text((200, 200), label, fill="#facc15")
    image.save(path)


def write_tone(path: Path, seconds: float, frequency: int) -> None:
    ffmpeg("-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={seconds}", str(path))


def write_clip_video(path: Path, seconds: float, width: int, height: int) -> None:
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=duration={seconds}:size={width}x{height}:rate=30",
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        str(path),
    )


def build_smoke_demo(root: Path) -> Path:
    """A ~10 s produce demo with blur, prebuilt voice and Pillow slides."""
    clip_dir = root / "capture" / "clips" / "search"
    clip_dir.mkdir(parents=True)
    (root / "voice").mkdir()
    (root / "slides").mkdir()

    spec = {
        "version": 1,
        "formats": ["16:9"],
        "theme": "dark",
        "scenes": [
            {"id": "intro", "layout": "slide", "slide": "intro"},
            {"id": "search", "layout": "browser", "clip": "search"},
        ],
        "blur": [{"clip": "search", "box": [0.05, 0.05, 0.30, 0.10], "start": 0.0, "end": None}],
    }
    script = {
        "version": 1,
        "scenes": [
            {
                "id": "intro",
                "caption": "Demo",
                "lines": [
                    {
                        "id": "l1",
                        "phrases": [
                            {"text": "Welcome to the integration smoke demo."},
                            {"text": "This clip checks compose, blur and export."},
                        ],
                    }
                ],
            },
            {
                "id": "search",
                "caption": "Browser",
                "lines": [
                    {
                        "id": "l1",
                        "phrases": [
                            {"text": "The search box is blurred for privacy.", "pin": "e1"},
                            {"text": "Everything else stays sharp on screen."},
                        ],
                    }
                ],
            },
        ],
    }
    clip = {
        "id": "search",
        "video": "video.mp4",
        "width": 640,
        "height": 400,
        "fps": 30,
        "duration": 5.0,
        "events": [
            {"id": "e1", "t": 1.0, "type": "tap", "x": 0.15, "y": 0.08, "label": "Search"},
        ],
    }
    timings = {
        "engine": "kokoro",
        "voice": "af_heart",
        "lines": [
            {
                "scene": "intro",
                "line": "l1",
                "file": "intro__l1.wav",
                "duration": 5.0,
                "hash": "a",
                "phrases": [
                    {"index": 0, "start": 0.0, "end": 2.4},
                    {"index": 1, "start": 2.6, "end": 5.0},
                ],
                "wpm": 150.0,
                "transcript_ok": True,
                "attempts": 1,
            },
            {
                "scene": "search",
                "line": "l1",
                "file": "search__l1.wav",
                "duration": 5.0,
                "hash": "b",
                "phrases": [
                    {"index": 0, "start": 0.0, "end": 2.2},
                    {"index": 1, "start": 2.4, "end": 5.0},
                ],
                "wpm": 150.0,
                "transcript_ok": True,
                "attempts": 1,
            },
        ],
    }

    (root / "spec.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")
    (root / "script.yaml").write_text(yaml.safe_dump(script), encoding="utf-8")
    (clip_dir / "clip.json").write_text(json.dumps(clip), encoding="utf-8")
    (root / "voice" / "timings.json").write_text(json.dumps(timings), encoding="utf-8")

    write_slide(root / "slides" / "intro.png", "Smoke")
    write_tone(root / "voice" / "intro__l1.wav", 5.0, 440)
    write_tone(root / "voice" / "search__l1.wav", 5.0, 660)
    write_clip_video(clip_dir / "video.mp4", 5.0, 640, 400)
    return root
