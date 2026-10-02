"""Terminal replay: init, capture web, the logged events and script check."""

from __future__ import annotations

import time
from pathlib import Path

from playwright.async_api import Page

PAGE = Path(__file__).resolve().parent.parent / "terminal" / "index.html"
SESSION = "capture"

# (start time in seconds, label when the step starts, label when its output appears)
# Start times follow the narration at about 0.4 s per word of the line that
# describes each step, so the voice never runs ahead of the screen.
STEPS = [
    (1.0, "type reelsmith init", "demo folder ready"),
    (11.1, "type reelsmith capture web", "clip recorded with 3 events"),
    (18.6, "type jq events", "three logged events"),
    (34.1, "type reelsmith script check", "script check OK"),
]
END = 41.5


async def flow(page: Page, log) -> None:
    await page.goto(PAGE.as_uri() + "?manual#" + SESSION)
    await page.wait_for_function("window.replay && window.replay.steps > 0")
    t0 = time.monotonic()

    async def until(seconds: float) -> None:
        wait = t0 + seconds - time.monotonic()
        if wait > 0:
            await page.wait_for_timeout(wait * 1000)

    for n, (start, start_label, out_label) in enumerate(STEPS, start=1):
        await until(start)
        await page.evaluate(f"window.replay.start({n})")
        await log.screen(start_label)
        await page.get_by_test_id(f"key-{n}").wait_for(state="visible", timeout=30000)
        await log.screen(out_label)
    await page.wait_for_function("window.replayDone === true")
    await until(END)
