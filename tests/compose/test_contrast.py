"""Tests for panel contrast helpers."""

from __future__ import annotations

from reelsmith.compose.contrast import contrast_ratio, panel_text_color


def test_dark_brand_text_meets_aa_on_dark_background() -> None:
    background = "#0B1413"
    text = "#EEF4F2"
    assert contrast_ratio(text, background) >= 4.5
    assert panel_text_color(text, background) == text


def test_dim_accent_is_lifted_for_eyebrows() -> None:
    background = "#0B1413"
    weak = "#7CC7BB"
    fixed = panel_text_color(weak, background, minimum=3.0)
    assert contrast_ratio(fixed, background) >= 3.0
