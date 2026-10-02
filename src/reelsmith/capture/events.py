"""Record capture events with timestamps from the video start."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from reelsmith.errors import ReelsmithError
from reelsmith.models import Event

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page


class CaptureLog:
    """Helper passed into a web capture flow to log clicks and screens."""

    def __init__(self, page: Page, started_at: float, width: int, height: int) -> None:
        self._page = page
        self._started_at = started_at
        self._width = width
        self._height = height
        self.events: list[Event] = []
        self._counter = 0

    def elapsed(self) -> float:
        """Seconds since recording started (same clock as event times)."""
        return max(0.0, time.monotonic() - self._started_at)

    def _next_id(self) -> str:
        self._counter += 1
        return f"e{self._counter}"

    async def _centre(self, locator: Locator) -> tuple[float, float]:
        await locator.wait_for(state="visible")
        box = await locator.bounding_box()
        if box is None:
            raise ReelsmithError("Could not find the element on screen.")
        x = (box["x"] + box["width"] / 2) / self._width
        y = (box["y"] + box["height"] / 2) / self._height
        return min(1.0, max(0.0, x)), min(1.0, max(0.0, y))

    async def click(self, locator: Locator, label: str) -> None:
        x, y = await self._centre(locator)
        t = self.elapsed()
        await locator.click()
        self.events.append(
            Event(
                id=self._next_id(),
                t=t,
                type="click",
                x=x,
                y=y,
                label=label,
            )
        )

    async def type(self, locator: Locator, text: str, label: str, delay_ms: int = 55) -> None:
        """Type text one key at a time, so the viewer sees it being typed."""
        x, y = await self._centre(locator)
        t = self.elapsed()
        await locator.click()
        await locator.press_sequentially(text, delay=delay_ms)
        self.events.append(
            Event(
                id=self._next_id(),
                t=t,
                type="click",
                x=x,
                y=y,
                label=label,
            )
        )

    async def key(self, name: str) -> None:
        t = self.elapsed()
        await self._page.keyboard.press(name)
        self.events.append(
            Event(
                id=self._next_id(),
                t=t,
                type="key",
                label=name,
            )
        )

    async def screen(self, label: str) -> None:
        self.events.append(
            Event(
                id=self._next_id(),
                t=self.elapsed(),
                type="screen",
                label=label,
            )
        )
