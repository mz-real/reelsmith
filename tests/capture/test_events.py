"""Event times in a web capture log match when the page actually changed."""

from __future__ import annotations

import asyncio
import time

from reelsmith.capture.events import CaptureLog

SLOW_CLICK = 0.3


class FakeLocator:
    """A locator whose click spends time on actionability checks first."""

    def __init__(self) -> None:
        self.clicked_at: float | None = None

    async def wait_for(self, state: str) -> None:
        return None

    async def bounding_box(self) -> dict[str, float]:
        return {"x": 10.0, "y": 10.0, "width": 20.0, "height": 20.0}

    async def click(self) -> None:
        await asyncio.sleep(SLOW_CLICK)
        self.clicked_at = time.monotonic()

    async def press_sequentially(self, text: str, delay: int) -> None:
        return None


class FakeKeyboard:
    def __init__(self) -> None:
        self.pressed_at: float | None = None

    async def press(self, name: str) -> None:
        await asyncio.sleep(SLOW_CLICK)
        self.pressed_at = time.monotonic()


class FakePage:
    def __init__(self) -> None:
        self.keyboard = FakeKeyboard()


def test_a_slow_click_is_timed_when_it_lands_not_when_it_was_asked_for() -> None:
    started = time.monotonic()
    log = CaptureLog(FakePage(), started, 640, 480)  # type: ignore[arg-type]
    locator = FakeLocator()

    asyncio.run(log.click(locator, "go"))  # type: ignore[arg-type]

    assert locator.clicked_at is not None
    landed = locator.clicked_at - started
    assert abs(log.events[0].t - landed) < 0.05


def test_a_slow_key_is_timed_when_it_lands() -> None:
    started = time.monotonic()
    page = FakePage()
    log = CaptureLog(page, started, 640, 480)  # type: ignore[arg-type]

    asyncio.run(log.key("Enter"))

    assert page.keyboard.pressed_at is not None
    assert abs(log.events[0].t - (page.keyboard.pressed_at - started)) < 0.05


def test_typing_is_timed_when_the_field_is_focused() -> None:
    started = time.monotonic()
    log = CaptureLog(FakePage(), started, 640, 480)  # type: ignore[arg-type]
    locator = FakeLocator()

    asyncio.run(log.type(locator, "pasta", "search"))  # type: ignore[arg-type]

    assert locator.clicked_at is not None
    assert abs(log.events[0].t - (locator.clicked_at - started)) < 0.05
