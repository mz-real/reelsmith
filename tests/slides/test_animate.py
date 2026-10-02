"""Step clips: real Playwright and ffmpeg renders at a small size."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from reelsmith.models import BrandModel, SpecModel
from reelsmith.models.slides import SlidesModel
from reelsmith.slides.animate import CLIP_FPS, CLIP_FRAMES, encode_args
from reelsmith.slides.render import render_slides_to_dir
from reelsmith.slides.themes import resolve_theme

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")

WIDTH, HEIGHT = 480, 270


def _frames(path: Path) -> tuple[int, int, int]:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames,width,height",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(out.stdout)["streams"][0]
    return int(stream["nb_read_frames"]), int(stream["width"]), int(stream["height"])


def _frame_bytes(path: Path, number: int) -> bytes:
    out = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"select=eq(n\\,{number})",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    return out.stdout


def _mean_diff(a: bytes, b: bytes) -> float:
    assert len(a) == len(b) == WIDTH * HEIGHT
    return sum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a)


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("slides")
    spec = SpecModel.model_validate({"version": 1})
    slides = SlidesModel.model_validate(
        {
            "slides": [
                {
                    "id": "flow",
                    "kind": "flow",
                    "title": "How it *works*",
                    "chapter": 2,
                    "steps": [
                        {"title": "Plan", "detail": "Write the spec"},
                        {"title": "Render", "detail": "Make the video"},
                    ],
                }
            ]
        }
    )
    theme = resolve_theme(spec, BrandModel(), out)
    written = render_slides_to_dir(slides, theme, out, width=WIDTH, height=HEIGHT)
    assert written == [
        "flow_step0.mp4",
        "flow_step0.png",
        "flow_step1.mp4",
        "flow_step1.png",
        "flow.png",
    ]
    return out


def test_every_step_has_a_clip_with_the_right_frames_and_size(rendered: Path) -> None:
    assert CLIP_FRAMES == 21 and CLIP_FPS == 30
    for step in (0, 1):
        assert _frames(rendered / f"flow_step{step}.mp4") == (CLIP_FRAMES, WIDTH, HEIGHT)


def test_clips_move_and_end_on_their_still(rendered: Path) -> None:
    for step in (0, 1):
        clip = rendered / f"flow_step{step}.mp4"
        first = _frame_bytes(clip, 0)
        last = _frame_bytes(clip, CLIP_FRAMES - 1)
        assert _mean_diff(first, last) > 0.5, f"step {step} has no motion"


def test_step_one_starts_where_step_zero_ends(rendered: Path) -> None:
    end_of_zero = _frame_bytes(rendered / "flow_step0.mp4", CLIP_FRAMES - 1)
    start_of_one = _frame_bytes(rendered / "flow_step1.mp4", 0)
    assert _mean_diff(end_of_zero, start_of_one) < 1.5


def test_final_image_is_the_last_step(rendered: Path) -> None:
    assert (rendered / "flow.png").read_bytes() == (rendered / "flow_step1.png").read_bytes()


def test_encoder_settings() -> None:
    args = encode_args(Path("out.mp4"))
    assert args[args.index("-crf") + 1] == "18"
    assert args[args.index("-pix_fmt") + 1] == "yuv420p"
    assert args[args.index("-framerate") + 1] == "30"
