"""Chapter 10: first project run, install offer and first interview question."""

from __future__ import annotations

import time
from pathlib import Path

from playwright.async_api import Page

PAGE = Path(__file__).resolve().parent.parent / "terminal" / "index.html"
SESSION = "firstrun"

STEPS = [
    (1.0, "ask for a demo video", "request typed"),
    (5.2, "reelsmith skill loads", "app summary"),
    (10.2, "offer CLI install", "install choices"),
    (17.8, "confirm standard install", "choice typed"),
    (19.0, "doctor passed", "setup ok"),
    (23.0, "first interview question", "mode question"),
]
END = 29.0


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
        await page.get_by_test_id(f"key-{n}").wait_for(state="visible", timeout=90000)
    await page.wait_for_function("window.replayDone === true")
    await until(END)
