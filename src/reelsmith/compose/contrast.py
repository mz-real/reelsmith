"""WCAG contrast helpers for panel text on brand backgrounds."""

from __future__ import annotations

import math

from PIL import ImageColor


def _srgb(channel: float) -> float:
    if channel <= 0.04045:
        return float(channel / 12.92)
    return math.pow((channel + 0.055) / 1.055, 2.4)


def relative_luminance(hex_color: str) -> float:
    """Relative luminance for a CSS hex colour."""
    red, green, blue = (c / 255 for c in ImageColor.getrgb(hex_color)[:3])
    return 0.2126 * _srgb(red) + 0.7152 * _srgb(green) + 0.0722 * _srgb(blue)


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG contrast ratio between two colours."""
    light = relative_luminance(foreground)
    dark = relative_luminance(background)
    if light < dark:
        light, dark = dark, light
    return (light + 0.05) / (dark + 0.05)


def panel_text_color(text: str, background: str, minimum: float = 4.5) -> str:
    """Return text or a lightened/darkened variant that meets minimum contrast."""
    if contrast_ratio(text, background) >= minimum:
        return text
    toward = "#ffffff" if relative_luminance(background) < 0.5 else "#000000"
    best = text
    best_ratio = contrast_ratio(text, background)
    for step in range(1, 17):
        share = step / 16
        red, green, blue = ImageColor.getrgb(text)[:3]
        target = ImageColor.getrgb(toward)
        mixed = (
            round(red + (target[0] - red) * share),
            round(green + (target[1] - green) * share),
            round(blue + (target[2] - blue) * share),
        )
        candidate = f"#{mixed[0]:02x}{mixed[1]:02x}{mixed[2]:02x}"
        ratio = contrast_ratio(candidate, background)
        if ratio >= minimum:
            return candidate
        if ratio > best_ratio:
            best, best_ratio = candidate, ratio
    return best


def panel_accent_color(accent: str, background: str, minimum: float = 3.0) -> str:
    """Eyebrow and rule colour: large text AA is 3:1."""
    return panel_text_color(accent, background, minimum)
