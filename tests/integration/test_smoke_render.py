"""Smoke render: placeholder media, compose at small scale, export, blur check."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from reelsmith.compose.blur import blur_boxes
from reelsmith.compose.graph import Encode
from reelsmith.compose.project import RenderSettings, compose_project
from reelsmith.export import export_project
from reelsmith.media.ffmpeg import probe
from reelsmith.models import SpecModel, load_model
from reelsmith.paths import DemoPaths
from reelsmith.qa.image import grayscale_crop, laplacian_variance
from tests.integration._demo import build_smoke_demo

pytestmark = pytest.mark.integration

SMALL = RenderSettings(0.25, Encode("ultrafast", 30), use_cache=False, preview=False)


def _parse_srt(text: str) -> list[tuple[float, float, str]]:
    cues: list[tuple[float, float, str]] = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        match = re.match(
            r"(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})",
            lines[1],
        )
        if match is None:
            raise AssertionError(f"bad srt timing line: {lines[1]}")

        def to_seconds(groups: tuple[str, ...]) -> float:
            h, m, s, ms = (int(groups[i]) for i in range(4))
            return h * 3600 + m * 60 + s + ms / 1000

        start = to_seconds(match.groups()[:4])
        end = to_seconds(match.groups()[4:])
        body = "\n".join(lines[2:])
        cues.append((start, end, body))
    if not cues:
        raise AssertionError("srt had no cues")
    return cues


def _blur_pixel_box(spec: SpecModel, width: int, height: int) -> tuple[int, int, int, int]:
    region = spec.blur[0]
    boxes = blur_boxes([region], region.clip, width, height)
    box = boxes[0]
    return box.x, box.y, box.w, box.h


def test_smoke_compose_export_and_blur(tmp_path: Path, require_ffmpeg: None) -> None:
    root = build_smoke_demo(tmp_path / "smoke")
    paths = DemoPaths.at(root)
    report = compose_project(paths, SMALL)
    duration = report.formats[0].duration
    assert 9.0 < duration < 12.0

    export = export_project(paths, "smoke")
    assert export.written

    voiced = probe(paths.out / "smoke_16x9.mp4")
    silent = probe(paths.out / "smoke_16x9_silent.mp4")
    width, height = voiced.width, voiced.height
    assert (width, height) == (480, 270)
    for info in (voiced, silent):
        assert info.duration == pytest.approx(duration, abs=0.35)
    assert voiced.has_audio
    assert not silent.has_audio

    srt_text = (paths.out / "smoke.srt").read_text(encoding="utf-8")
    cues = _parse_srt(srt_text)
    assert cues[0][0] == 0.0
    assert cues[-1][1] <= duration + 0.05

    spec = load_model(paths.spec, SpecModel)
    frame_path = tmp_path / "blur_frame.png"
    sample_at = duration * 0.55
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            f"{sample_at:.3f}",
            "-i",
            str(paths.out / "smoke_16x9_silent.mp4"),
            "-frames:v",
            "1",
            str(frame_path),
        ],
        check=True,
    )
    bx, by, bw, bh = _blur_pixel_box(spec, width, height)
    inside = grayscale_crop(frame_path, (float(bx), float(by), float(bw), float(bh)))
    outside = grayscale_crop(
        frame_path,
        (float(bx + bw + 4), float(by + bh + 4), float(width - bx - bw - 8), float(40)),
    )
    inside_energy = laplacian_variance(inside)
    outside_energy = laplacian_variance(outside)
    assert outside_energy > 0.0
    assert inside_energy < outside_energy * 0.5
