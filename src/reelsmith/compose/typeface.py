"""Font faces for panel text: regular, medium and bold weights.

Brand fonts from brand.yaml come first. Otherwise a common system sans
is used. When no bold file exists, the regular face is drawn with a thin
stroke so titles still read as bold.
"""

from __future__ import annotations

import os
import platform
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont

from reelsmith.compose.captions import Font, load_font


@dataclass(frozen=True)
class Face:
    path: Path | None
    index: int = 0
    fake_bold: bool = False

    def load(self, size: int) -> Font:
        if self.path is not None:
            try:
                return ImageFont.truetype(str(self.path), size, index=self.index)
            except OSError:
                pass
        return load_font(None, size)

    def stroke(self, size: int) -> int:
        """Extra stroke width to draw with, for a face that fakes bold."""
        return max(1, round(size * 0.03)) if self.fake_bold else 0


@dataclass(frozen=True)
class Faces:
    regular: Face
    medium: Face
    bold: Face


# (file, regular index, medium index, bold index) for font collections,
# or separate files per weight.
_MAC_COLLECTIONS = [
    ("/System/Library/Fonts/HelveticaNeue.ttc", 0, 10, 1),
    ("/System/Library/Fonts/Avenir Next.ttc", 7, 5, 0),
]


def _linux_sets() -> list[tuple[str, str, str]]:
    roots = ["/usr/share/fonts/truetype", "/usr/share/fonts/TTF", "/usr/share/fonts"]
    sets = []
    for root in roots:
        sets.append(
            (
                f"{root}/dejavu/DejaVuSans.ttf",
                f"{root}/dejavu/DejaVuSans.ttf",
                f"{root}/dejavu/DejaVuSans-Bold.ttf",
            )
        )
        sets.append(
            (
                f"{root}/liberation/LiberationSans-Regular.ttf",
                f"{root}/liberation/LiberationSans-Regular.ttf",
                f"{root}/liberation/LiberationSans-Bold.ttf",
            )
        )
        sets.append(
            (f"{root}/DejaVuSans.ttf", f"{root}/DejaVuSans.ttf", f"{root}/DejaVuSans-Bold.ttf")
        )
    return sets


def _windows_sets() -> list[tuple[str, str, str]]:
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    return [(str(fonts / "segoeui.ttf"), str(fonts / "seguisb.ttf"), str(fonts / "segoeuib.ttf"))]


def _from_brand(files: Sequence[Path]) -> Faces | None:
    existing = [path for path in files if path.is_file()]
    if not existing:
        return None

    def pick(*words: str) -> Path | None:
        for word in words:
            for path in existing:
                if word in path.stem.lower().replace("-", "").replace("_", ""):
                    return path
        return None

    regular = pick("regular", "book", "text") or existing[0]
    bold = pick("bold", "black", "heavy")
    medium = pick("semibold", "medium") or bold
    return Faces(
        Face(regular),
        Face(medium) if medium else Face(regular, fake_bold=True),
        Face(bold) if bold else Face(regular, fake_bold=True),
    )


def find_faces(brand_files: Sequence[Path], fallback: Path | None) -> Faces:
    """Regular, medium and bold faces: brand fonts, then system fonts."""
    branded = _from_brand(brand_files)
    if branded is not None:
        return branded
    system = platform.system()
    if system == "Darwin":
        for name, regular, medium, bold in _MAC_COLLECTIONS:
            path = Path(name)
            if path.is_file():
                return Faces(Face(path, regular), Face(path, medium), Face(path, bold))
    sets = _windows_sets() if system == "Windows" else _linux_sets()
    for regular_name, medium_name, bold_name in sets:
        regular_path, medium_path, bold_path = (
            Path(regular_name),
            Path(medium_name),
            Path(bold_name),
        )
        if regular_path.is_file() and bold_path.is_file():
            medium_face = Face(medium_path) if medium_path.is_file() else Face(regular_path)
            return Faces(Face(regular_path), medium_face, Face(bold_path))
    return Faces(Face(fallback), Face(fallback), Face(fallback, fake_bold=True))
