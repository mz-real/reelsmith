"""Favourite a recipe and confirm it on the Favourites tab."""

from __future__ import annotations

from pathlib import Path

from playwright.async_api import Page

APP_HTML = Path(__file__).resolve().parent.parent / "app" / "index.html"


async def flow(page: Page, log) -> None:
    # Pauses follow the narration: about 0.4 s per word of the line
    # that describes each step, so the voice never runs ahead.
    await page.goto(APP_HTML.as_uri())
    await page.get_by_test_id("recipe-card-tomato-pasta").wait_for(state="visible")
    await page.wait_for_timeout(600)
    await log.click(
        page.get_by_test_id("recipe-card-tomato-pasta"),
        "open Tomato Basil Pasta",
    )
    await page.wait_for_timeout(1200)
    await log.click(page.get_by_test_id("favourite-toggle"), "add to favourites")
    await page.wait_for_timeout(4600)
    await log.click(page.get_by_test_id("back-button"), "back to list")
    await page.wait_for_timeout(2000)
    await log.click(page.get_by_test_id("tab-favourites"), "Favourites tab")
    await page.wait_for_timeout(2200)
    await log.screen("Tomato Basil Pasta in favourites")
    await page.wait_for_timeout(4400)
