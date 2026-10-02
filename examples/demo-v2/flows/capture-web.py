"""Chapter 4 capture: search click, type, open recipe, favourite."""

from __future__ import annotations

from pathlib import Path

from playwright.async_api import Page

APP_HTML = Path(__file__).resolve().parents[2] / "recipe-box" / "app" / "index.html"


async def flow(page: Page, log) -> None:
    # Pauses follow the narration: about 0.4 s per word of the line
    # that describes each step, so the voice can pin to each action.
    await page.goto(APP_HTML.as_uri())
    await page.get_by_test_id("search-input").wait_for(state="visible")
    await page.wait_for_timeout(800)
    await log.screen("Recipe Box home")
    # "For a web app, the AI writes a short Playwright flow for each scene."
    await page.wait_for_timeout(5600)
    await log.click(page.get_by_test_id("search-input"), "click search box")
    # "reelsmith runs it in a real browser, records the screen,"
    await page.wait_for_timeout(3600)
    await log.type(
        page.get_by_test_id("search-input"),
        "tomato",
        "type tomato",
    )
    # "and logs every click with its time and position."
    await page.wait_for_timeout(3600)
    await log.click(
        page.get_by_test_id("recipe-card-tomato-pasta"),
        "open Tomato Basil Pasta",
    )
    # "Those events are what the narration pins to."
    await page.wait_for_timeout(3200)
    await log.click(page.get_by_test_id("favourite-toggle"), "Add to favourites")
    await page.wait_for_timeout(4000)
