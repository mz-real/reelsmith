"""Compare rendered slide PNGs for tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

# Architecture arrows are thin SVG strokes. Chromium's macOS rasteriser can
# antialias them slightly differently between two captures even when layout
# is stable, so PNG bytes may not match while pixels stay within this band.
ARCH_MAX_DIFF_FRACTION = 0.005
ARCH_MAX_CHANNEL_DIFF = 32
ARCH_FORBIDDEN_CHANNEL_DIFF = 64


@dataclass(frozen=True)
class PngDiff:
    differing_pixels: int
    total_pixels: int
    max_channel_diff: int
    has_large_channel_diff: bool
    bbox: tuple[int, int, int, int] | None

    def message(self) -> str:
        fraction = self.differing_pixels / self.total_pixels if self.total_pixels else 0.0
        bbox = (
            "none"
            if self.bbox is None
            else (f"x={self.bbox[0]}..{self.bbox[2]}, y={self.bbox[1]}..{self.bbox[3]}")
        )
        return (
            f"differing_pixels={self.differing_pixels} "
            f"({fraction * 100:.4f}% of {self.total_pixels}), "
            f"max_channel_diff={self.max_channel_diff}, "
            f"any_channel_diff_ge_{ARCH_FORBIDDEN_CHANNEL_DIFF}="
            f"{self.has_large_channel_diff}, bbox={bbox}"
        )


def png_pixel_diff(left: Path, right: Path) -> PngDiff:
    with Image.open(left) as image_a, Image.open(right) as image_b:
        if image_a.size != image_b.size:
            raise AssertionError(f"sizes differ: {image_a.size} vs {image_b.size}")
        array_a = np.asarray(image_a.convert("RGBA"), dtype=np.int16)
        array_b = np.asarray(image_b.convert("RGBA"), dtype=np.int16)
    return _diff_arrays(array_a, array_b)


def _diff_arrays(array_a: np.ndarray, array_b: np.ndarray) -> PngDiff:
    channel_diff = np.abs(array_a - array_b)
    per_pixel = channel_diff.max(axis=2)
    differing = per_pixel > 0
    count = int(differing.sum())
    total = int(per_pixel.size)
    if count == 0:
        return PngDiff(0, total, 0, False, None)
    rows, cols = np.where(differing)
    bbox = (int(cols.min()), int(rows.min()), int(cols.max()), int(rows.max()))
    return PngDiff(
        count,
        total,
        int(channel_diff.max()),
        bool((channel_diff >= ARCH_FORBIDDEN_CHANNEL_DIFF).any()),
        bbox,
    )


def architecture_pixels_match(diff: PngDiff) -> bool:
    if diff.differing_pixels == 0:
        return True
    if diff.has_large_channel_diff:
        return False
    if diff.max_channel_diff > ARCH_MAX_CHANNEL_DIFF:
        return False
    return diff.differing_pixels / diff.total_pixels < ARCH_MAX_DIFF_FRACTION


def assert_render_pair_equal(left: Path, right: Path, *, name: str, arch_tolerance: bool) -> None:
    if left.read_bytes() == right.read_bytes():
        return
    diff = png_pixel_diff(left, right)
    detail = diff.message()
    if arch_tolerance and architecture_pixels_match(diff):
        return
    kind = "outside architecture pixel tolerance" if arch_tolerance else "bytes differ"
    raise AssertionError(f"{name}: {kind}. {detail}")
