"""Pillow and numpy backed image helpers for the blur check and contact sheets.

ffmpeg's own text drawing (drawtext) needs a font filter that is not built
into every ffmpeg install, so contact sheet labels are drawn with Pillow
instead.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

Box = tuple[float, float, float, float]

THUMB_WIDTH = 240
LABEL_HEIGHT = 20


def grayscale_crop(png_path: Path, box: Box | None) -> np.ndarray:
    """Read a PNG frame as a grayscale array, optionally cropped to a pixel box."""
    with Image.open(png_path) as image:
        gray = image.convert("L")
        if box is not None:
            x, y, w, h = box
            left, top = max(0, int(round(x))), max(0, int(round(y)))
            right = min(gray.width, left + max(1, int(round(w))))
            bottom = min(gray.height, top + max(1, int(round(h))))
            if right <= left or bottom <= top:
                return np.zeros((1, 1), dtype=np.float64)
            gray = gray.crop((left, top, right, bottom))
        return np.asarray(gray, dtype=np.float64)


def laplacian_variance(gray: np.ndarray) -> float:
    """How much high frequency detail is in a grayscale array.

    A blurred region has little detail left, so its Laplacian variance
    is low compared with a sharp one.
    """
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    center = gray[1:-1, 1:-1]
    laplacian = -4.0 * center + gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:]
    return float(np.var(laplacian))


def build_contact_sheet(frames: list[tuple[Path, str]], out_path: Path, columns: int = 4) -> None:
    """Tile frame images into one labelled sheet, written as a JPEG.

    Each frame is shrunk to a common thumbnail width and labelled with the
    text given alongside it (normally a time or event label).
    """
    if not frames:
        return
    thumbnails: list[Image.Image] = []
    try:
        font = ImageFont.load_default()
        for path, label in frames:
            with Image.open(path) as source:
                ratio = THUMB_WIDTH / source.width
                size = (THUMB_WIDTH, max(1, round(source.height * ratio)))
                thumb = source.convert("RGB").resize(size)
            canvas = Image.new("RGB", (thumb.width, thumb.height + LABEL_HEIGHT), "black")
            canvas.paste(thumb, (0, 0))
            draw = ImageDraw.Draw(canvas)
            draw.text((2, thumb.height + 2), label, fill="white", font=font)
            thumbnails.append(canvas)

        rows = (len(thumbnails) + columns - 1) // columns
        cell_w = max(t.width for t in thumbnails)
        cell_h = max(t.height for t in thumbnails)
        sheet = Image.new("RGB", (cell_w * columns, cell_h * rows), "black")
        for index, thumb in enumerate(thumbnails):
            col, row = index % columns, index // columns
            sheet.paste(thumb, (col * cell_w, row * cell_h))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sheet.convert("RGB").save(out_path, "JPEG", quality=85)
    finally:
        for thumb in thumbnails:
            thumb.close()
