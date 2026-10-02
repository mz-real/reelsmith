"""Render slide pages to stills and short intro clips with Playwright.

Clips are not screen recordings. Every CSS animation on the page is paused,
then moved to the time of each frame through the Web Animations API, and the
frame is captured. The frames go straight into ffmpeg, so the result is the
same on every run and on any machine speed.
"""

from __future__ import annotations

import base64
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from playwright.sync_api import Locator, Page, sync_playwright

from reelsmith.errors import ReelsmithError
from reelsmith.media.ffmpeg import require_ffmpeg

CLIP_FPS = 30
CLIP_SECONDS = 0.7
CLIP_FRAMES = round(CLIP_SECONDS * CLIP_FPS)
CLIP_CRF = 18
BROWSER_FIX = "reelsmith setup browser"

_SEEK = """
(ms) => {
  for (const a of document.getAnimations()) {
    a.pause();
    a.currentTime = ms;
  }
}
"""
_FINISH = """
() => {
  for (const a of document.getAnimations()) {
    a.pause();
    const timing = a.effect ? a.effect.getComputedTiming() : null;
    const end = timing && Number.isFinite(timing.endTime) ? timing.endTime : 0;
    a.currentTime = end;
  }
}
"""
_READY_TIMEOUT_MS = 15_000
_ENSURE_READY = """
() => {
  if (window.__reelsmithReady !== undefined) return;
  window.__reelsmithReady = false;
  document.fonts.ready.then(() => { window.__reelsmithReady = true; });
}
"""


def _wait_for_render_ready(page: Page) -> None:
    """Wait for web fonts and any layout script before capture."""
    page.evaluate("async () => { await document.fonts.ready; }")
    page.evaluate(_ENSURE_READY)
    try:
        page.wait_for_function(
            "() => window.__reelsmithReady === true",
            timeout=_READY_TIMEOUT_MS,
        )
    except Exception as exc:
        raise ReelsmithError(
            "Slide layout did not finish before capture (timed out waiting for "
            "window.__reelsmithReady).",
            fix=BROWSER_FIX,
        ) from exc


class SlidePage:
    """One browser page at the frame size, reused for every slide state."""

    def __init__(self, page: Page, width: int, height: int) -> None:
        self._page = page
        self._cdp: Any = page.context.new_cdp_session(page)
        self.width = width
        self.height = height

    def load(self, html_text: str) -> None:
        self._page.set_content(html_text, wait_until="load")
        _wait_for_render_ready(self._page)
        self._page.evaluate(_SEEK, 0)

    def capture(self) -> bytes:
        """The current frame as PNG bytes."""
        self._page.evaluate(
            "() => { if (typeof window.__reelsmithRelayout === 'function') "
            "window.__reelsmithRelayout(); }"
        )
        shot = self._cdp.send(
            "Page.captureScreenshot",
            {"format": "png", "optimizeForSpeed": True, "captureBeyondViewport": False},
        )
        return base64.b64decode(shot["data"])

    def locator(self, selector: str) -> Locator:
        return self._page.locator(selector)

    def seek(self, ms: float) -> None:
        self._page.evaluate(_SEEK, ms)

    def finish(self) -> None:
        """Move every animation to its end, so the page shows the final state."""
        self._page.evaluate(_FINISH)

    def still(self, path: Path) -> None:
        self.finish()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.capture())

    def clip(self, path: Path) -> None:
        """Write the intro of the loaded page as an mp4 clip."""
        _wait_for_render_ready(self._page)
        self.seek(0)
        frames = []
        for number in range(CLIP_FRAMES):
            self.seek(number * 1000 / CLIP_FPS)
            frames.append(self.capture())
        encode_frames(frames, path)


@contextmanager
def slide_page(width: int, height: int) -> Iterator[SlidePage]:
    """Open a headless browser page at the given size."""
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(
                    viewport={"width": width, "height": height}, device_scale_factor=1
                )
                yield SlidePage(page, width, height)
            finally:
                browser.close()
    except ReelsmithError:
        raise
    except Exception as exc:
        raise ReelsmithError("Could not render slides with Playwright.", fix=BROWSER_FIX) from exc


def encode_args(path: Path) -> list[str]:
    """ffmpeg arguments that read PNG frames from stdin and write an mp4."""
    return [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "image2pipe",
        "-framerate",
        str(CLIP_FPS),
        "-c:v",
        "png",
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        str(CLIP_CRF),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(CLIP_FPS),
        "-movflags",
        "+faststart",
        str(path),
    ]


def encode_frames(frames: list[bytes], path: Path) -> None:
    """Encode PNG frames into an mp4, through a temp name so a crash leaves nothing."""
    require_ffmpeg()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.stem}.partial{path.suffix}")
    completed = subprocess.run(encode_args(tmp), input=b"".join(frames), capture_output=True)
    if completed.returncode != 0:
        tmp.unlink(missing_ok=True)
        error = " ".join(completed.stderr.decode("utf-8", "replace").split())[-400:]
        raise ReelsmithError(f"ffmpeg could not encode {path.name}: {error or 'no output'}")
    tmp.replace(path)
