"""A real render at 1280x720: a phone scene with points and a zoom, and a
browser scene with cursor clicks."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import yaml
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from reelsmith.compose.footage import cursor_clicks, panel_pieces, scene_colors
from reelsmith.compose.graph import Encode
from reelsmith.compose.inputs import load_project
from reelsmith.compose.layouts import canvas_size, theme_colors
from reelsmith.compose.motion import CURSOR_LEAD, ZOOM_LEAD
from reelsmith.compose.project import RenderSettings, _look, compose_project
from reelsmith.compose.scene import scene_layout
from reelsmith.media.ffmpeg import probe
from reelsmith.models import BrandModel
from reelsmith.paths import DemoPaths

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")

SETTINGS = RenderSettings(2 / 3, Encode("ultrafast", 20), use_cache=False, preview=False)
ACCENT = (45, 212, 191)  # the default Studio accent, #2dd4bf

SPEC = {
    "version": 1,
    "formats": ["16:9"],
    "theme": "dark",
    "footage": "web",
    "scenes": [
        {
            "id": "tour",
            "layout": "phone",
            "clip": "tour",
            "eyebrow": "Step 1",
            "title": "Plan the *week*",
            "points": [
                {"text": "Pick meals in *seconds*", "line": "t1"},
                {"text": "Share the list", "line": "t2"},
            ],
            "zoom": [{"box": [0.0, 0.0, 0.5, 0.5], "at": "e1", "hold": 1.0}],
        },
        {"id": "web", "layout": "browser", "clip": "web"},
    ],
}

SCRIPT = {
    "version": 1,
    "scenes": [
        {
            "id": "tour",
            "lines": [
                {"id": "t1", "phrases": [{"text": "Pick a few meals.", "pin": "e1"}]},
                {"id": "t2", "phrases": [{"text": "Then share the list with home."}]},
            ],
        },
        {
            "id": "web",
            "lines": [
                {"id": "w1", "phrases": [{"text": "Click the first card.", "pin": "e1"}]},
                {"id": "w2", "phrases": [{"text": "Then the second one.", "pin": "e2"}]},
            ],
        },
    ],
}

CLIPS = {
    "tour": {"size": (360, 780), "duration": 6.0, "events": [(1.5, "tap", 0.25, 0.25)]},
    "web": {
        "size": (640, 360),
        "duration": 6.0,
        "events": [(1.5, "click", 0.25, 0.3), (4.0, "click", 0.75, 0.7)],
    },
}

LINES = {"tour": [("t1", 1.5), ("t2", 2.0)], "web": [("w1", 1.4), ("w2", 1.4)]}


def _quadrants(path: Path, size: tuple[int, int]) -> None:
    """A still picture of four coloured quarters, so zoom is easy to see."""
    w, h = size
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, w // 2, h // 2), fill=(220, 40, 40))
    draw.rectangle((w // 2, 0, w, h // 2), fill=(40, 180, 60))
    draw.rectangle((0, h // 2, w // 2, h), fill=(40, 60, 220))
    image.save(path)


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def make_motion_demo(root: Path) -> Path:
    (root / "voice").mkdir(parents=True)
    (root / "spec.yaml").write_text(yaml.safe_dump(SPEC), encoding="utf-8")
    (root / "script.yaml").write_text(yaml.safe_dump(SCRIPT), encoding="utf-8")
    timings = []
    for scene, lines in LINES.items():
        for line, seconds in lines:
            name = f"{scene}__{line}.wav"
            _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=500:duration={seconds}",
                    str(root / "voice" / name))  # fmt: skip
            timings.append(
                {"scene": scene, "line": line, "file": name, "duration": seconds, "hash": "h",
                 "phrases": [{"index": 0, "start": 0.0, "end": seconds}]}
            )  # fmt: skip
    data = {"engine": "kokoro", "voice": "am_michael", "lines": timings}
    (root / "voice" / "timings.json").write_text(json.dumps(data), encoding="utf-8")
    for clip_id, clip in CLIPS.items():
        folder = root / "capture" / "clips" / clip_id
        folder.mkdir(parents=True)
        size = clip["size"]
        assert isinstance(size, tuple)
        still = folder / "still.png"
        if clip_id == "tour":
            _quadrants(still, size)
        else:
            Image.new("RGB", size, (128, 128, 128)).save(still)
        _ffmpeg("-loop", "1", "-framerate", "30", "-i", str(still), "-t", str(clip["duration"]),
                "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
                str(folder / "video.mp4"))  # fmt: skip
        events = clip["events"]
        assert isinstance(events, list)
        model = {
            "id": clip_id, "video": "video.mp4", "width": size[0], "height": size[1],
            "fps": 30, "duration": clip["duration"],
            "events": [{"id": f"e{n + 1}", "t": t, "type": kind, "x": x, "y": y}
                       for n, (t, kind, x, y) in enumerate(events)],
        }  # fmt: skip
        (folder / "clip.json").write_text(json.dumps(model), encoding="utf-8")
    return root


def frame_at(master: Path, at: float, dest: Path) -> NDArray[np.int64]:
    _ffmpeg("-ss", f"{at:.3f}", "-i", str(master), "-frames:v", "1", str(dest))
    with Image.open(dest) as image:
        return np.asarray(image.convert("RGB")).astype(np.int64)


def near(pixels: NDArray[np.int64], color: tuple[int, int, int], tolerance: int = 40) -> int:
    distance = np.abs(pixels - np.array(color)).sum(axis=-1)
    return int((distance < tolerance).sum())


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> tuple[DemoPaths, Path]:
    paths = DemoPaths.at(make_motion_demo(tmp_path_factory.mktemp("motion") / "motion demo"))
    report = compose_project(paths, SETTINGS)
    return paths, report.formats[0].master


def test_motion_render_at_1280x720(rendered: tuple[DemoPaths, Path], tmp_path: Path) -> None:
    paths, master = rendered
    info = probe(master)
    assert (info.width, info.height) == (1280, 720)
    project = load_project(paths)
    look = _look(project, "16:9", SETTINGS)
    assert look.canvas == canvas_size("16:9", 2 / 3)
    tour, web = project.scenes
    assert info.duration == pytest.approx(tour.timeline.duration + web.timeline.duration, abs=0.2)

    # The phone scene: the Studio panel shows the title at once and point two on its line.
    layout = scene_layout(tour, look)
    pieces = {piece.name: piece for piece in panel_pieces(tour, layout, look)}
    second = pieces["point_1"]
    before = frame_at(master, second.start - 0.3, tmp_path / "before.png")
    after = frame_at(master, second.start + 0.8, tmp_path / "after.png")
    box = second.box
    region = (slice(box.y, box.y + box.h), slice(box.x, box.x + box.w))
    assert np.abs(after[region] - before[region]).sum(axis=-1).max() > 200
    title = pieces["title"].box
    assert near(after[title.y : title.y + title.h, title.x : title.x + title.w], ACCENT) > 20

    # The zoom: at the tap the footage shows only its top left (red) quarter.
    content = layout.content
    tap = tour.timeline.placements[0].out_start + 0.25
    hold = frame_at(master, tap + 0.3, tmp_path / "zoom.png")
    centre = hold[content.y + content.h // 2, content.x + content.w // 2]
    assert centre[0] > 150 and centre[1] < 120 and centre[2] < 120, centre
    start = frame_at(master, max(0.0, tap - ZOOM_LEAD - 1.2), tmp_path / "wide.png")
    corner = start[content.y + content.h - 40, content.x + content.w - 40]
    assert corner.min() > 200, corner  # the white quarter is still in view before the zoom

    # The background is the Studio gradient, not the flat theme colour.
    flat = theme_colors("dark", BrandModel()).background
    assert start[5, 5].tolist() != list(bytes.fromhex(flat.lstrip("#")))


def test_cursor_reaches_each_click_and_pulses(
    rendered: tuple[DemoPaths, Path], tmp_path: Path
) -> None:
    paths, master = rendered
    project = load_project(paths)
    look = _look(project, "16:9", SETTINGS)
    tour, web = project.scenes
    layout = scene_layout(web, look)
    clicks = cursor_clicks(web, look)
    accent = tuple(bytes.fromhex(scene_colors(web, look).accent.lstrip("#")))
    assert len(clicks) == 2
    offset = tour.timeline.duration
    content = layout.content
    for number, click in enumerate(clicks):
        x = content.x + round(click.x * content.w)
        y = content.y + round(click.y * content.h)
        at = offset + click.t - CURSOR_LEAD / 2
        pixels = frame_at(master, at, tmp_path / f"cursor{number}.png")
        tip = pixels[y : y + 24, x : x + 18]
        assert near(tip, (255, 255, 255), 60) > 10, "white arrow body at the click"
        assert near(tip, (17, 20, 26), 60) > 5, "dark arrow outline at the click"
        pulse = frame_at(master, offset + click.t + 0.12, tmp_path / f"pulse{number}.png")
        ring = pulse[y - 40 : y + 40, x - 40 : x + 40]
        tinted = np.abs(ring - np.array(accent)).sum(-1) < np.abs(ring - 128).sum(-1)
        assert tinted.sum() > 30, "accent pulse around the click"
