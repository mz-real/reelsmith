"""Phone-sized product demo: search, favourite, Favourites tab."""

from __future__ import annotations

from pathlib import Path

from playwright.async_api import Page

APP_HTML = Path(__file__).resolve().parents[2] / "recipe-box" / "app" / "index.html"


async def flow(page: Page, log) -> None:
    await page.goto(APP_HTML.as_uri())
    await page.get_by_test_id("search-input").wait_for(state="visible")
    await page.wait_for_timeout(800)
    await log.screen("browse recipes")
    await page.wait_for_timeout(2000)
    await log.type(
        page.get_by_test_id("search-input"),
        "tomato",
        "search tomato",
    )
    await page.wait_for_timeout(1200)
    await log.click(
        page.get_by_test_id("recipe-card-tomato-pasta"),
        "open Tomato Basil Pasta",
    )
    await page.wait_for_timeout(1500)
    await log.click(page.get_by_test_id("favourite-toggle"), "add to favourites")
    await page.wait_for_timeout(1200)
    await log.click(page.get_by_test_id("back-button"), "back to list")
    await page.wait_for_timeout(1000)
    await log.click(page.get_by_test_id("tab-favourites"), "Favourites tab")
    await page.wait_for_timeout(1000)
    await log.screen("Tomato Basil Pasta in favourites")
    await page.wait_for_timeout(2500)
