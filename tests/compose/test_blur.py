"""Tests for blur boxes and their filter chain."""

from __future__ import annotations

from reelsmith.compose.blur import BlurBox, blur_boxes, blur_filters
from reelsmith.models import BlurRegion


def region(clip: str, box: list[float], start: float = 0.0, end: float | None = None) -> BlurRegion:
    return BlurRegion.model_validate({"clip": clip, "box": box, "start": start, "end": end})


def test_blur_boxes_pick_this_clip_and_convert_to_even_pixels() -> None:
    regions = [region("search", [0.05, 0.10, 0.30, 0.06]), region("other", [0, 0, 1, 1])]
    boxes = blur_boxes(regions, "search", 1920, 1080)
    assert boxes == [BlurBox(96, 108, 576, 64, 0.0, None)]


def test_blur_boxes_stay_inside_the_frame() -> None:
    boxes = blur_boxes([region("a", [0.9, 0.9, 0.5, 0.5])], "a", 101, 99)
    box = boxes[0]
    assert box.x + box.w <= 101 and box.y + box.h <= 99
    assert box.w % 2 == 0 and box.h % 2 == 0


def test_blur_filters_crop_blur_and_overlay_in_a_time_window() -> None:
    boxes = [BlurBox(96, 108, 576, 64, 1.5, 4.0)]
    chains = blur_filters(boxes, "src", "blurred")
    text = ";".join(chains)
    assert "crop=576:64:96:108" in text
    assert "boxblur=" in text
    assert "overlay=96:108:enable='between(t,1.5,4)'" in text
    assert text.startswith("[src]split")
    assert text.endswith("[blurred]")


def test_blur_with_no_end_runs_to_the_end_of_the_clip() -> None:
    text = ";".join(blur_filters([BlurBox(0, 0, 100, 40, 2.0, None)], "a", "b"))
    assert "enable='gte(t,2)'" in text


def test_blur_radius_is_small_enough_for_a_thin_box() -> None:
    text = ";".join(blur_filters([BlurBox(0, 0, 200, 12, 0.0, None)], "a", "b"))
    radius = int(text.split("boxblur=")[1].split(":")[0])
    assert 1 <= radius < 12 // 4


def test_blur_radius_stays_below_the_chroma_limit() -> None:
    text = ";".join(blur_filters([BlurBox(0, 0, 192, 40, 0.0, None)], "a", "b"))
    assert "boxblur=9:2" in text


def test_no_boxes_passes_the_stream_through() -> None:
    assert blur_filters([], "a", "b") == ["[a]null[b]"]
