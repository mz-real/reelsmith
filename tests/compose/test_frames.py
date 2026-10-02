"""Tests for the browser and phone frames drawn with Pillow."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from reelsmith.compose.frames import draw_frame, draw_status_bar, top_colour
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


def test_status_bar_takes_the_app_colour_and_draws_glyphs(tmp_path: Path) -> None:
    out = draw_status_bar(Size(400, 52), "#f4efe6", 1.0, tmp_path / "bar.png")
    with Image.open(out) as image:
        rgb = image.convert("RGB")
        assert rgb.size == (400, 52)
        assert rgb.getpixel((200, 2)) == (244, 239, 230)  # app colour behind the island
        colours = {rgb.getpixel((x, 26)) for x in range(0, 120)}
        assert any(sum(c) < 200 for c in colours)  # dark time text on a light app
        right = {rgb.getpixel((x, 26)) for x in range(300, 400)}
        assert any(sum(c) < 200 for c in right)  # signal, wifi and battery glyphs


def test_status_bar_text_turns_light_on_a_dark_app(tmp_path: Path) -> None:
    out = draw_status_bar(Size(400, 52), "#101010", 1.0, tmp_path / "bar.png")
    with Image.open(out) as image:
        rgb = image.convert("RGB")
        assert any(sum(rgb.getpixel((x, 26))) > 600 for x in range(0, 120))


def test_top_colour_falls_back_to_white(tmp_path: Path) -> None:
    (tmp_path / "broken.mp4").write_bytes(b"not a video")
    assert top_colour(tmp_path / "broken.mp4", tmp_path / "top.png") == "#ffffff"
