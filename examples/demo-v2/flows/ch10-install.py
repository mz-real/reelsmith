"""Chapter 10: Claude Code plugin marketplace, install and list."""

from __future__ import annotations

import time
from pathlib import Path

from playwright.async_api import Page

PAGE = Path(__file__).resolve().parent.parent / "terminal" / "index.html"
SESSION = "install"

# Start times follow the narration at about 0.4 s per word of the line that
# describes each step.
STEPS = [
    (1.0, "add marketplace to Claude Code", "marketplace added"),
    (6.4, "install the plugin", "plugin installed"),
    (9.6, "confirm plugin enabled", "plugin enabled"),
]
END = 14.8


async def flow(page: Page, log) -> None:
    await page.goto(PAGE.as_uri() + "?manual#" + SESSION)
    await page.wait_for_function("window.replay && window.replay.steps > 0")
    t0 = time.monotonic()

    async def until(seconds: float) -> None:
        wait = t0 + seconds - time.monotonic()
        if wait > 0:
            await page.wait_for_timeout(wait * 1000)

    for n, (start, start_label, _out_label) in enumerate(STEPS, start=1):
        await until(start)
        await page.evaluate(f"window.replay.start({n})")
        await log.screen(start_label)
        await page.get_by_test_id(f"key-{n}").wait_for(state="visible", timeout=60000)
    await page.wait_for_function("window.replayDone === true")
    await until(END)
