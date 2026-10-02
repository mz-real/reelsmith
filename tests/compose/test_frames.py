"""Tests for the browser and phone frames drawn with Pillow."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from reelsmith.compose.frames import draw_frame
from reelsmith.compose.layouts import Size


@pytest.mark.parametrize("kind", ["browser", "phone"])
def test_frame_has_a_clear_screen_and_a_solid_border(kind: str, tmp_path: Path) -> None:
    out = draw_frame(kind, Size(400, 700), 0.5, dark=True, dest=tmp_path / f"{kind}.png")  # type: ignore[arg-type]
    with Image.open(out) as image:
        assert image.size == (400, 700)
        assert image.mode == "RGBA"
        alpha = image.getchannel("A")
        assert alpha.getpixel((200, 400)) == 0  # the screen shows through
        assert alpha.getpixel((200, 3)) == 255  # the frame border is solid


def test_browser_frame_has_a_title_bar(tmp_path: Path) -> None:
    out = draw_frame("browser", Size(800, 500), 1.0, dark=False, dest=tmp_path / "b.png")
    with Image.open(out) as image:
        assert image.getchannel("A").getpixel((400, 30)) == 255
        assert image.getchannel("A").getpixel((400, 60)) == 0
