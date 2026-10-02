"""Record a browser flow with Playwright."""

from __future__ import annotations

import asyncio
import importlib.util
import shutil
import subprocess
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeGuard

import numpy as np
from playwright.async_api import Page, async_playwright

from reelsmith.capture.events import CaptureLog
from reelsmith.errors import ReelsmithError
from reelsmith.fsutil import backup_existing
from reelsmith.media.ffmpeg import probe, run_ffmpeg
from reelsmith.models import ClipModel, Event, save_model

FlowFn = Callable[[Page, CaptureLog], Awaitable[None]]
TARGET_FPS = 30.0
_BLANK_PAGE = "data:text/html,<body style='margin:0;background:#ffffff'></body>"
_MARKER_SHOW_MS = 1500
_MARKER_WARMUP_MS = 500
_SCAN_WIDTH = 160
_SCAN_SECONDS = 10.0
_MAGENTA_RGB = (255, 0, 255)
_MAGENTA_MAX_DIST = 80
_MAGENTA_MIN_FRACTION = 0.60
_MARKER_FIND_ATTEMPTS = 2


def _is_flow(value: object) -> TypeGuard[FlowFn]:
    return asyncio.iscoroutinefunction(value)


def is_magenta_rgb(r: int, g: int, b: int) -> bool:
    return r > 200 and g < 80 and b > 200


def is_red_rgb(r: int, g: int, b: int) -> bool:
    return r > 200 and g < 80 and b < 80


def parse_size(raw: str) -> tuple[int, int]:
    """Parse WIDTHxHEIGHT. Both must be positive and even."""
    parts = raw.lower().split("x")
    if len(parts) != 2:
        raise ReelsmithError(
            f"Size '{raw}' is not valid.",
            fix="Use even numbers like 1280x720",
        )
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError:
        raise ReelsmithError(
            f"Size '{raw}' is not valid.",
            fix="Use even numbers like 1280x720",
        ) from None
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ReelsmithError(
            f"Size '{raw}' is not valid.",
            fix="Use even numbers like 1280x720",
        )
    return width, height


def _load_flow(path: Path) -> FlowFn:
    path = path.resolve()
    if not path.is_file():
        raise ReelsmithError(f"{path} not found")
    spec = importlib.util.spec_from_file_location(f"reelsmith_flow_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ReelsmithError(f"Could not load {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    flow_obj: object = getattr(module, "flow", None)
    if not _is_flow(flow_obj):
        raise ReelsmithError(
            f"{path.name} must define async def flow(page, log).",
            fix=f"Add async def flow(page, log) to {path}",
        )
    return flow_obj


def _convert_webm(webm_path: Path, mp4_path: Path) -> None:
    backup_existing(mp4_path)
    info = probe(webm_path)
    vf = f"scale=trunc(iw/2)*2:trunc(ih/2)*2,fps={TARGET_FPS:g}"
    args: list[str] = ["-i", str(webm_path)]
    if not info.has_audio:
        args.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]
        )
    args.extend(["-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p"])
    if info.has_audio:
        args.extend(["-c:a", "aac", "-b:a", "128k"])
    else:
        args.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:a",
                "aac",
                "-shortest",
            ]
        )
    args.append(str(mp4_path))
    run_ffmpeg(args)


async def _run_sync_marker(page: Page, wall_elapsed: Callable[[], float]) -> float:
    """Flash magenta so we can line up event times with video frames."""
    await page.goto(_BLANK_PAGE, wait_until="commit")
    await page.evaluate(
        f"""() => {{
          return new Promise((resolve) => {{
            requestAnimationFrame(() => {{
              setTimeout(() => {{
                const el = document.createElement('div');
                el.id = 'reelsmith-sync-marker';
                el.style.cssText =
                  'position:fixed;inset:0;background:#ff00ff;z-index:2147483647';
                document.body.appendChild(el);
                resolve();
              }}, {_MARKER_WARMUP_MS});
            }});
          }});
        }}"""
    )
    marker_t = wall_elapsed()
    await page.wait_for_timeout(_MARKER_SHOW_MS)
    await page.evaluate("() => document.getElementById('reelsmith-sync-marker')?.remove()")
    return marker_t


def magenta_match_fraction(frame: np.ndarray) -> float:
    """Share of pixels close to sync marker magenta (255, 0, 255)."""
    target = np.array(_MAGENTA_RGB, dtype=np.float64)
    diff = frame.astype(np.float64) - target
    dist = np.linalg.norm(diff, axis=-1)
    return float(np.mean(dist <= _MAGENTA_MAX_DIST))


def frame_has_sync_marker(frame: np.ndarray) -> bool:
    return magenta_match_fraction(frame) >= _MAGENTA_MIN_FRACTION


def _decode_scan_frames(video: Path) -> np.ndarray:
    info = probe(video)
    scan_h = max(2, int(_SCAN_WIDTH * info.height / info.width))
    if scan_h % 2:
        scan_h += 1
    frame_bytes = _SCAN_WIDTH * scan_h * 3
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-t",
        f"{_SCAN_SECONDS:.3f}",
        "-i",
        str(video),
        "-vf",
        f"scale={_SCAN_WIDTH}:{scan_h}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    raw = subprocess.run(ffmpeg_cmd, capture_output=True, check=False)
    if raw.returncode != 0 or not raw.stdout:
        raise ReelsmithError("Could not read frames from the web capture video.")
    data = np.frombuffer(raw.stdout, dtype=np.uint8)
    frame_count = data.size // frame_bytes
    if frame_count == 0:
        raise ReelsmithError(
            "Could not find the sync marker in the web capture video.",
            fix="Retry capture web or update Playwright Chromium",
        )
    return data[: frame_count * frame_bytes].reshape(frame_count, scan_h, _SCAN_WIDTH, 3)


def _find_magenta_range(video: Path) -> tuple[float, float]:
    info = probe(video)
    fps = info.fps if info.fps > 0 else TARGET_FPS
    frames = _decode_scan_frames(video)
    indices: list[int] = []
    best_fraction = 0.0
    for index, frame in enumerate(frames):
        fraction = magenta_match_fraction(frame)
        if fraction > best_fraction:
            best_fraction = fraction
        if frame_has_sync_marker(frame):
            indices.append(index)
    if not indices:
        pct = best_fraction * 100.0
        raise ReelsmithError(
            "Could not find the sync marker in the web capture video. "
            f"Scanned {len(frames)} frames, best match {pct:.1f}%.",
            fix="Retry capture web or update Playwright Chromium",
        )
    start = indices[0] / fps
    end = (indices[-1] + 1) / fps
    return start, end


def _align_events(
    events: list[Event],
    *,
    marker_t: float,
    marker_video_start: float,
    trim_at: float,
    duration: float,
) -> list[Event]:
    offset = marker_video_start - marker_t
    aligned: list[Event] = []
    for event in events:
        t = event.t + offset - trim_at
        t = min(max(0.0, t), duration)
        aligned.append(event.model_copy(update={"t": t}))
    return aligned


def _trim_video_start(source: Path, dest: Path, start: float) -> None:
    if start <= 1e-6:
        shutil.copy2(source, dest)
        return
    backup_existing(dest)
    args = [
        "-ss",
        f"{start:.6f}",
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
    ]
    info = probe(source)
    if info.has_audio:
        args.extend(["-c:a", "aac", "-b:a", "128k"])
    else:
        args.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:a",
                "aac",
                "-shortest",
            ]
        )
    args.append(str(dest))
    run_ffmpeg(args)


def centre_rgb_at_time(video: Path, t: float) -> tuple[int, int, int]:
    """Sample the centre pixel of one frame (used by sync tests)."""
    info = probe(video)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, t):.6f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-vf",
        f"scale={info.width}:{info.height}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    raw = subprocess.run(command, capture_output=True, check=False)
    if raw.returncode != 0 or len(raw.stdout) < 3:
        raise ReelsmithError(f"Could not read a frame at {t:.3f} s from {video.name}")
    cx = info.width // 2
    cy = info.height // 2
    offset = (cy * info.width + cx) * 3
    pixel = raw.stdout[offset : offset + 3]
    return int(pixel[0]), int(pixel[1]), int(pixel[2])


async def _record_once(
    clip_dir: Path,
    record_dir: Path,
    *,
    flow: FlowFn,
    headed: bool,
    width: int,
    height: int,
    chromium_args: list[str],
) -> tuple[float, CaptureLog, Path]:
    """Record one webm, convert to raw mp4, return marker time and paths."""
    raw_path = clip_dir / "video.raw.mp4"
    webm_path: Path | None = None
    marker_t = 0.0
    log: CaptureLog | None = None

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=not headed,
            args=chromium_args,
        )
        context = await browser.new_context(
            record_video_dir=str(record_dir),
            record_video_size={"width": width, "height": height},
            viewport={"width": width, "height": height},
        )
        page = await context.new_page()
        started = time.monotonic()

        def wall_elapsed() -> float:
            return max(0.0, time.monotonic() - started)

        marker_t = await _run_sync_marker(page, wall_elapsed)
        log = CaptureLog(page, started, width, height)
        await flow(page, log)
        if page.video is not None:
            webm_path = Path(await page.video.path())
        await context.close()
        await browser.close()

    if webm_path is None or not webm_path.is_file():
        raise ReelsmithError("Playwright did not write a recording.")
    if log is None:
        raise ReelsmithError("Capture log was not initialized.")

    _convert_webm(webm_path, raw_path)
    webm_path.unlink(missing_ok=True)
    for leftover in record_dir.glob("*"):
        leftover.unlink(missing_ok=True)
    record_dir.rmdir()

    return marker_t, log, raw_path


async def _record_flow(
    flow_path: Path,
    clip_id: str,
    clips_root: Path,
    *,
    headed: bool,
    size: str,
    chromium_args: list[str] | None = None,
) -> ClipModel:
    width, height = parse_size(size)
    flow = _load_flow(flow_path)
    clip_dir = clips_root / clip_id
    clip_dir.mkdir(parents=True, exist_ok=True)
    record_dir = clip_dir / ".record"
    record_dir.mkdir(parents=True, exist_ok=True)

    video_path = clip_dir / "video.mp4"
    launch_args = list(chromium_args or [])
    marker_t = 0.0
    log: CaptureLog | None = None
    raw_path: Path | None = None
    marker_start = 0.0
    marker_end = 0.0

    for attempt in range(_MARKER_FIND_ATTEMPTS):
        record_dir.mkdir(parents=True, exist_ok=True)
        marker_t, log, raw_path = await _record_once(
            clip_dir,
            record_dir,
            flow=flow,
            headed=headed,
            width=width,
            height=height,
            chromium_args=launch_args,
        )
        try:
            marker_start, marker_end = _find_magenta_range(raw_path)
            break
        except ReelsmithError:
            if raw_path.is_file():
                raw_path.unlink(missing_ok=True)
            if attempt + 1 >= _MARKER_FIND_ATTEMPTS:
                raise

    if log is None or raw_path is None:
        raise ReelsmithError("Web capture failed.")

    _trim_video_start(raw_path, video_path, marker_end)
    raw_path.unlink(missing_ok=True)

    out = probe(video_path)
    events = _align_events(
        log.events,
        marker_t=marker_t,
        marker_video_start=marker_start,
        trim_at=marker_end,
        duration=out.duration,
    )
    clip = ClipModel(
        id=clip_id,
        video="video.mp4",
        width=out.width,
        height=out.height,
        fps=out.fps,
        duration=out.duration,
        events=events,
    )
    save_model(clip_dir / "clip.json", clip)
    return clip


def run_web_flow(
    flow_path: Path,
    clip_id: str,
    clips_root: Path,
    *,
    headed: bool = False,
    size: str = "1280x720",
    chromium_args: list[str] | None = None,
) -> ClipModel:
    """Run a flow file and write clips/<id>/video.mp4 and clip.json."""
    return asyncio.run(
        _record_flow(
            flow_path,
            clip_id,
            clips_root,
            headed=headed,
            size=size,
            chromium_args=chromium_args,
        )
    )
