"""Slide rendering: HTML templates to PNG via Playwright.

The renderer is loaded on first use, so the slides.yaml model can import
the icon names from this package without a circular import.
"""

from __future__ import annotations

from typing import Any

__all__ = ["render_slides_to_dir", "step_cue_count"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from reelsmith.slides import render

        return getattr(render, name)
    raise AttributeError(name)
