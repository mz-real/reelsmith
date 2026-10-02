"""Search the recipe list for tomato."""

from __future__ import annotations

from pathlib import Path

from playwright.async_api import Page

APP_HTML = Path(__file__).resolve().parent.parent / "app" / "index.html"


async def flow(page: Page, log) -> None:
    # Pauses follow the narration: about 0.4 s per word of the line
    # that describes each step, so the voice never runs ahead.
    await page.goto(APP_HTML.as_uri())
    await page.get_by_test_id("search-input").wait_for(state="visible")
    await page.wait_for_timeout(600)
    await log.screen("all recipes")
    await page.wait_for_timeout(3400)
    await log.type(
        page.get_by_test_id("search-input"),
        "tomato",
        "type tomato in search",
    )
    await page.wait_for_timeout(2200)
    await log.screen("filtered tomato recipes")
    await page.wait_for_timeout(5200)
