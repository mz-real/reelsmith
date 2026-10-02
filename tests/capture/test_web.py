"""Tests for web capture recording."""

from __future__ import annotations

from pathlib import Path

import pytest

from reelsmith.capture.web import centre_rgb_at_time, is_red_rgb, run_web_flow
from reelsmith.media.ffmpeg import probe
from reelsmith.models import ClipModel, load_model

_RED_PAGE = """<!DOCTYPE html>
<html><body>
<button id="btn">Go</button>
<script>
document.getElementById('btn').addEventListener('click', () => {
  document.body.style.background = '#ff0000';
});
</script>
</body></html>"""


@pytest.fixture
def flow_file(tmp_path: Path) -> Path:
    flow = tmp_path / "flow.py"
    flow.write_text(
        f'''import asyncio

_PAGE = """{_RED_PAGE}"""

async def flow(page, log):
    await page.set_content(_PAGE)
    await asyncio.sleep(1.0)
    await log.click(page.locator("#btn"), "turn red")
    await asyncio.sleep(1.0)
''',
        encoding="utf-8",
    )
    return flow


def test_web_capture_records_events_in_video_duration(flow_file: Path, tmp_path: Path) -> None:
    clips = tmp_path / "clips"
    run_web_flow(flow_file, "demo", clips, size="640x480")

    clip = load_model(clips / "demo" / "clip.json", ClipModel)
    info = probe(clips / "demo" / "video.mp4")

    assert len(clip.events) >= 1
    assert clip.duration == pytest.approx(info.duration, abs=0.25)
    assert clip.fps == pytest.approx(info.fps, abs=0.5)
    for event in clip.events:
        assert 0.0 <= event.t <= info.duration + 0.01

    click = next(e for e in clip.events if e.type == "click")
    assert click.label == "turn red"


def test_web_capture_event_times_match_video_frames(flow_file: Path, tmp_path: Path) -> None:
    clips = tmp_path / "clips"
    run_web_flow(flow_file, "sync", clips, size="640x480")

    clip = load_model(clips / "sync" / "clip.json", ClipModel)
    video = clips / "sync" / "video.mp4"
    click = next(event for event in clip.events if event.type == "click")

    assert click.t >= 0.35, "click should be after the pre-click wait"

    before = centre_rgb_at_time(video, click.t - 0.25)
    after = centre_rgb_at_time(video, click.t + 0.25)

    assert not is_red_rgb(*before), f"frame before click should not be red: {before}"
    assert is_red_rgb(*after), f"frame after click should be red: {after}"


def test_web_capture_records_at_the_requested_size(flow_file: Path, tmp_path: Path) -> None:
    # Playwright scales recordings down to fit 800x800 unless told the size.
    clips = tmp_path / "clips"
    run_web_flow(flow_file, "big", clips, size="1280x720")

    clip = load_model(clips / "big" / "clip.json", ClipModel)
    info = probe(clips / "big" / "video.mp4")

    assert (info.width, info.height) == (1280, 720)
    assert (clip.width, clip.height) == (1280, 720)


def test_log_type_types_visibly_one_key_at_a_time(tmp_path: Path) -> None:
    flow = tmp_path / "typing.py"
    flow.write_text(
        "async def flow(page, log):\n"
        "    await page.set_content('<input id=box>')\n"
        "    await log.type(page.locator('#box'), 'hello world', 'type greeting')\n"
        "    await log.screen('typed')\n"
        "    assert await page.locator('#box').input_value() == 'hello world'\n",
        encoding="utf-8",
    )
    clips = tmp_path / "clips"
    run_web_flow(flow, "typing", clips, size="640x480")

    clip = load_model(clips / "typing" / "clip.json", ClipModel)
    typed, done = clip.events[0], clip.events[1]
    # 11 keys at 55 ms each: the typing itself is on screen for over half a second.
    assert done.t - typed.t >= 0.5
