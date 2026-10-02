"""Built in slide themes merged with brand.yaml overrides."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reelsmith.compose.layouts import canvas_size
from reelsmith.models import BrandModel
from reelsmith.models.spec import SpecModel, VideoFormat


@dataclass(frozen=True)
class SlideTheme:
    background: str
    text: str
    primary: str
    secondary: str
    accent: str
    muted: str
    font_family: str
    font_face_css: str
    logo_uri: str | None


_BASE_THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "background": "#0f172a",
        "text": "#f8fafc",
        "primary": "#2563eb",
        "secondary": "#64748b",
        "accent": "#38bdf8",
        "muted": "#334155",
    },
    "light": {
        "background": "#ffffff",
        "text": "#0f172a",
        "primary": "#2563eb",
        "secondary": "#64748b",
        "accent": "#0ea5e9",
        "muted": "#e2e8f0",
    },
    "minimal": {
        "background": "#fafafa",
        "text": "#171717",
        "primary": "#404040",
        "secondary": "#737373",
        "accent": "#525252",
        "muted": "#e5e5e5",
    },
}


def frame_size(spec: SpecModel, fmt: VideoFormat | None = None) -> tuple[int, int]:
    """Pixel width and height for a format and quality (default: first format)."""
    chosen: VideoFormat = fmt if fmt is not None else spec.formats[0]
    scale = 2.0 if spec.quality == "4k" else 1.0
    size = canvas_size(chosen, scale)
    return size.width, size.height


def _pick_color(brand_value: str | None, theme_value: str) -> str:
    return brand_value if brand_value is not None else theme_value


def _font_face_css(demo_root: Path, brand: BrandModel, family: str) -> str:
    if not brand.font.files:
        return ""
    lines = ["@font-face {"]
    for index, rel in enumerate(brand.font.files):
        path = (demo_root / rel).resolve()
        lines.append(f"  font-family: '{family}';")
        lines.append(f"  src: url('{path.as_uri()}');")
        if index == 0:
            lines.append("  font-weight: normal;")
            lines.append("  font-style: normal;")
        lines.append("}")
    return "\n".join(lines)


def resolve_theme(spec: SpecModel, brand: BrandModel, demo_root: Path) -> SlideTheme:
    """Merge spec theme defaults with optional brand colours, logo and fonts."""
    base = _BASE_THEMES[spec.theme]
    colors = brand.colors
    background = _pick_color(colors.background, base["background"])
    text = _pick_color(colors.text, base["text"])
    primary = _pick_color(colors.primary, base["primary"])
    secondary = _pick_color(colors.secondary, base["secondary"])
    accent = _pick_color(colors.accent, base["accent"])
    muted = base["muted"]
    if brand.colors.background is not None:
        muted = _pick_color(colors.secondary, base["muted"])
    family = brand.font.family or "system-ui, -apple-system, Segoe UI, sans-serif"
    if brand.font.files:
        family = "ReelsmithBrand, " + family
    logo_uri: str | None = None
    if brand.logo:
        logo_path = (demo_root / brand.logo).resolve()
        if logo_path.is_file():
            logo_uri = logo_path.as_uri()
    return SlideTheme(
        background=background,
        text=text,
        primary=primary,
        secondary=secondary,
        accent=accent,
        muted=muted,
        font_family=family,
        font_face_css=_font_face_css(demo_root, brand, "ReelsmithBrand"),
        logo_uri=logo_uri,
    )


def theme_styles(theme: SlideTheme, frame_height: int) -> str:
    """Shared CSS for every slide template, scaled to the render height."""
    title_px = frame_height * 0.07
    subtitle_px = frame_height * 0.04
    return f"""
{theme.font_face_css}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{
  width: 100%;
  height: 100%;
  background: {theme.background};
  color: {theme.text};
  font-family: {theme.font_family};
}}
.slide {{
  width: 100%;
  height: 100%;
  padding: 6%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: {frame_height * 0.02:.1f}px;
  overflow: hidden;
}}
.logo {{
  max-height: 12%;
  max-width: 40%;
  object-fit: contain;
}}
h1 {{
  font-size: {title_px:.1f}px;
  font-weight: 700;
  text-align: center;
  line-height: 1.15;
}}
.subtitle {{
  font-size: {subtitle_px:.1f}px;
  color: {theme.secondary};
  text-align: center;
  max-width: 80%;
}}
.muted {{
  color: {theme.secondary};
}}
.is-hidden {{
  visibility: hidden;
}}
"""
