"""Create and save a new recipe."""

from __future__ import annotations

from pathlib import Path

from playwright.async_api import Page

APP_HTML = Path(__file__).resolve().parent.parent / "app" / "index.html"


async def flow(page: Page, log) -> None:
    await page.goto(APP_HTML.as_uri())
    await page.get_by_test_id("new-recipe-button").wait_for(state="visible")
    await page.wait_for_timeout(600)
    await log.click(page.get_by_test_id("new-recipe-button"), "new recipe")
    await page.wait_for_timeout(600)
    await log.type(
        page.get_by_test_id("new-recipe-title"),
        "Demo Pancakes",
        "recipe title",
    )
    await log.type(
        page.get_by_test_id("new-recipe-ingredients"),
        "1 cup flour\n2 eggs\n1 cup milk",
        "ingredients",
    )
    await log.type(
        page.get_by_test_id("new-recipe-steps"),
        "Mix the batter until smooth.\nCook on a hot pan until golden.",
        "cooking steps",
    )
    await page.wait_for_timeout(400)
    await log.click(page.get_by_test_id("new-recipe-save"), "save recipe")
    await page.wait_for_timeout(600)
    await log.screen("saved recipe detail")
