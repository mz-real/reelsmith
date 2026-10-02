"""Slide scenes play each step's intro clip at its cue, then hold its still."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from reelsmith.compose.graph import Encode, SlideSource, SlideStep, scene_args
from reelsmith.compose.inputs import resolve_slide_images, slide_clip
from reelsmith.compose.layouts import Box
from reelsmith.compose.project import PREVIEW, RenderSettings, compose_project
from reelsmith.media.ffmpeg import probe
from reelsmith.paths import DemoPaths
from reelsmith.timing import Segment

from .test_graph import clip_plan, graph_of
from .test_project import FakeFfmpeg

CLIP_WARNING = "no intro clip"


def _steps(folder: Path, count: int, clips: bool) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for step in range(count):
        Image.new("RGB", (192, 108), "navy").save(folder / f"intro_step{step}.png")
        if clips:
            (folder / f"intro_step{step}.mp4").write_bytes(b"mp4")
    Image.new("RGB", (192, 108), "navy").save(folder / "intro.png")


def test_clips_are_found_next_to_step_stills(tmp_path: Path) -> None:
    _steps(tmp_path / "16x9", 2, clips=True)
    images, warnings = resolve_slide_images(tmp_path, "intro", "16:9")
    assert [p.name for p in images] == ["intro_step0.png", "intro_step1.png"]
    assert [slide_clip(p) for p in images] == [p.with_suffix(".mp4") for p in images]
    assert warnings == []


def test_missing_clips_fall_back_to_stills_with_a_warn(tmp_path: Path) -> None:
    _steps(tmp_path / "16x9", 2, clips=False)
    images, warnings = resolve_slide_images(tmp_path, "intro", "16:9")
    assert [slide_clip(p) for p in images] == [None, None]
    assert len(warnings) == 1 and CLIP_WARNING in warnings[0]
    assert "2 of 2 step(s)" in warnings[0]


def test_graph_plays_each_clip_then_holds_its_still() -> None:
    plan = clip_plan(
        source=SlideSource(
            [
                SlideStep(Path("s_step0.png"), 0.0, Path("s_step0.mp4")),
                SlideStep(Path("s_step1.png"), 2.0, Path("s_step1.mp4")),
            ]
        ),
        segments=[Segment("play", 0.0, 5.5, 1.0, 0.0, 5.5)],
        blur=[],
        zoom=0.05,
        content=Box(0, 0, 1920, 1080),
    )
    args = scene_args(plan, Encode("ultrafast", 28), Path("o.mp4"))
    graph = graph_of(args)
    assert args.count("s_step0.mp4") == 1 and args.count("s_step1.mp4") == 1
    assert "[sclip0][shold0]concat=n=2:v=1:a=0,trim=duration=2," in graph
    assert "[sclip1][shold1]concat=n=2:v=1:a=0,trim=duration=3.9," in graph
    assert "[sp0][sp1]concat=n=2:v=1:a=0[slides]" in graph
    assert "eval=frame" in graph  # the slow push in stays on top
    assert "fade=t=in" not in graph


def test_compose_picks_the_clips(ready: Path) -> None:
    _steps(ready / "slides" / "16x9", 2, clips=True)
    fake = FakeFfmpeg()
    report = compose_project(DemoPaths.at(ready), PREVIEW, fake)
    assert not [w for w in report.warnings if CLIP_WARNING in w]
    intro_call = fake.calls[0]
    clip_inputs = [a for a in intro_call if a.endswith(".mp4") and "_step" in a]
    assert [Path(a).name for a in clip_inputs] == ["intro_step0.mp4", "intro_step1.mp4"]


def test_compose_warns_when_a_slide_has_no_clip(ready: Path) -> None:
    report = compose_project(DemoPaths.at(ready), PREVIEW, FakeFfmpeg())
    assert [w for w in report.warnings if CLIP_WARNING in w]


def _clip(path: Path, color: str) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=1920x1080:r=30:d=0.7",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_a_real_slide_scene_renders_with_clips(media_demo: Path) -> None:
    folder = media_demo / "slides" / "16x9"
    folder.mkdir(parents=True)
    for step, color in enumerate(("red", "blue")):
        Image.new("RGB", (1920, 1080), color).save(folder / f"intro_step{step}.png")
        _clip(folder / f"intro_step{step}.mp4", color)
    tiny = RenderSettings(0.25, Encode("ultrafast", 30), use_cache=False, preview=True)
    report = compose_project(DemoPaths.at(media_demo), tiny)
    assert not [w for w in report.warnings if CLIP_WARNING in w]
    master = probe(report.formats[0].master)
    assert master.duration == pytest.approx(report.formats[0].duration, abs=0.15)
