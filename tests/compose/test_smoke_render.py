"""One real render: a slide and a browser clip with a test tone, end to end."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import cast

import pytest
import yaml
from PIL import Image, ImageColor, ImageStat

from reelsmith.compose.graph import Encode
from reelsmith.compose.inputs import load_project
from reelsmith.compose.layouts import Size, canvas_size, plan_layout, theme_colors
from reelsmith.compose.project import RenderSettings, compose_project
from reelsmith.export import export_project
from reelsmith.media.ffmpeg import probe
from reelsmith.models import BrandModel
from reelsmith.paths import DemoPaths

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")

TINY = RenderSettings(0.25, Encode("ultrafast", 30), use_cache=True, preview=False)


def test_compose_and_export_a_short_demo(media_demo: Path) -> None:
    paths = DemoPaths.at(media_demo)
    report = compose_project(paths, TINY)
    expected = report.formats[0].duration
    assert 9.0 < expected < 11.0

    master = probe(report.formats[0].master)
    assert (master.width, master.height) == (480, 270)
    assert master.duration == pytest.approx(expected, abs=0.15)
    assert master.has_audio

    export = export_project(paths, "smoke")
    names = {p.name for p in export.written}
    assert names == {"smoke_16x9.mp4", "smoke_16x9_silent.mp4", "smoke_narration.wav", "smoke.srt"}
    voiced = probe(paths.out / "smoke_16x9.mp4")
    silent = probe(paths.out / "smoke_16x9_silent.mp4")
    for info in (voiced, silent):
        assert (info.width, info.height) == (480, 270)
        assert info.duration == pytest.approx(expected, abs=0.15)
    assert voiced.has_audio
    assert not silent.has_audio
    assert (paths.out / "smoke_narration.wav").stat().st_size > 0


def _luminance(rgb: tuple[float, float, float]) -> float:
    def channel(value: float) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("footage", ["testsrc2=", "color=c=white:"])
def test_side_panel_text_is_readable_over_bright_footage(media_demo: Path, footage: str) -> None:
    clip_dir = media_demo / "capture" / "clips" / "search"
    spec = yaml.safe_load((media_demo / "spec.yaml").read_text(encoding="utf-8"))
    spec["scenes"][1]["layout"] = "phone"
    (media_demo / "spec.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")
    clip = json.loads((clip_dir / "clip.json").read_text(encoding="utf-8"))
    clip.update(width=360, height=780)
    (clip_dir / "clip.json").write_text(json.dumps(clip), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"{footage}duration=5:size=360x780:rate=30",
         "-pix_fmt", "yuv420p", str(clip_dir / "video.mp4")],
        check=True,
    )  # fmt: skip
    paths = DemoPaths.at(media_demo)
    settings = RenderSettings(0.5, Encode("ultrafast", 20), use_cache=False, preview=False)
    report = compose_project(paths, settings)
    project = load_project(paths)
    at = project.scenes[0].timeline.duration + 1.5  # phrase one is on screen
    frame = media_demo / "frame.png"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", str(at), "-i", str(report.formats[0].master),
         "-frames:v", "1", str(frame)],
        check=True,
    )  # fmt: skip
    canvas = canvas_size("16:9", 0.5)
    layout = plan_layout("phone", "16:9", canvas, Size(360, 780), captions=True)
    panel = layout.panel
    assert panel is not None and layout.panel_kind == "side"
    with Image.open(frame) as image:
        region = image.convert("RGB").crop((panel.x, panel.y, panel.x + panel.w, panel.y + panel.h))
        mean = cast(tuple[float, float, float], tuple(ImageStat.Stat(region).mean))
    colors = theme_colors("dark", BrandModel())
    for text in (colors.text, colors.accent):
        rgb = cast(tuple[float, float, float], ImageColor.getrgb(text)[:3])
        assert contrast(rgb, mean) >= 4.5, (text, mean)


def _sound_onsets(media: Path) -> list[float]:
    """Times where sound starts after silence, from ffmpeg silencedetect."""
    done = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(media),
         "-af", "silencedetect=noise=-45dB:d=0.1", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return [float(line.split("silence_end: ")[1].split()[0]) for line in done.stderr.splitlines()
            if "silence_end: " in line]  # fmt: skip


def test_timeline_placements_match_the_narration_in_the_master(media_demo: Path) -> None:
    paths = DemoPaths.at(media_demo)
    report = compose_project(paths, TINY)
    doc = json.loads((paths.build / "timeline.json").read_text(encoding="utf-8"))
    starts = [p["out_start"] for scene in doc["scenes"] for p in scene["placements"]]
    assert starts[0] == 0.0  # the master opens with speech, so there is no onset to find
    end = doc["duration"]
    onsets = [t for t in _sound_onsets(report.formats[0].master) if t < end - 0.1]
    assert len(onsets) == len(starts) - 1, (onsets, starts)
    for expected, found in zip(starts[1:], onsets, strict=True):
        # AAC frames and the detector window make onsets up to a few frames late.
        assert found == pytest.approx(expected, abs=0.08)
