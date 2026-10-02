"""Open Tomato Basil Pasta and scroll the ingredients."""

from __future__ import annotations

from pathlib import Path

from playwright.async_api import Page

APP_HTML = Path(__file__).resolve().parent.parent / "app" / "index.html"


async def flow(page: Page, log) -> None:
    await page.goto(APP_HTML.as_uri())
    await page.get_by_test_id("recipe-card-tomato-pasta").wait_for(state="visible")
    await page.wait_for_timeout(600)
    await log.click(
        page.get_by_test_id("recipe-card-tomato-pasta"),
        "open Tomato Basil Pasta",
    )
    await page.wait_for_timeout(600)
    await log.screen("recipe detail")
    ingredients = page.locator(".ingredient-list")
    await ingredients.scroll_into_view_if_needed()
    await page.wait_for_timeout(600)
    await log.screen("ingredients on screen")
