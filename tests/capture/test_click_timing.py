"""Click times are taken after the click, not before Playwright's waits."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from reelsmith.capture.events import CaptureLog


class FakeLocator:
    def __init__(self, clock: list[float], calls: list[str]) -> None:
        self.clock = clock
        self.calls = calls

    async def wait_for(self, state: str) -> None:
        self.calls.append("wait_for")

    async def bounding_box(self) -> dict[str, float]:
        return {"x": 100.0, "y": 100.0, "width": 20.0, "height": 10.0}

    async def click(self, trial: bool = False) -> None:
        # The trial click is the slow actionability wait; the real one is quick.
        self.calls.append("trial" if trial else "click")
        self.clock[0] += 0.4 if trial else 0.02

    async def press_sequentially(self, text: str, delay: int) -> None:
        self.calls.append("type")
        self.clock[0] += 0.5


def _log(clock: list[float], monkeypatch: Any) -> CaptureLog:
    monkeypatch.setattr("reelsmith.capture.events.time.monotonic", lambda: clock[0])
    return CaptureLog(page=None, started_at=0.0, width=640, height=480)  # type: ignore[arg-type]


def test_click_time_is_after_the_actionability_wait(monkeypatch: Any) -> None:
    clock, calls = [1.0], []
    log = _log(clock, monkeypatch)
    asyncio.run(log.click(FakeLocator(clock, calls), "go"))  # type: ignore[arg-type]
    assert calls == ["wait_for", "trial", "click"]
    assert log.events[0].t == pytest.approx(1.42)


def test_type_event_is_timed_at_its_click_not_after_typing(monkeypatch: Any) -> None:
    clock, calls = [0.0], []
    log = _log(clock, monkeypatch)
    asyncio.run(log.type(FakeLocator(clock, calls), "pasta", "search"))  # type: ignore[arg-type]
    assert calls == ["wait_for", "trial", "click", "type"]
    assert log.events[0].t == pytest.approx(0.42)
