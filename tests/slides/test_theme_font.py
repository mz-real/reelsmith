"""Brand fonts on slides."""

from __future__ import annotations

from pathlib import Path

from reelsmith.models import BrandModel
from reelsmith.models.spec import SpecModel
from reelsmith.slides.themes import resolve_theme


def test_brand_font_family_is_used_in_css(tmp_path: Path) -> None:
    font = tmp_path / "fonts" / "Manrope.ttf"
    font.parent.mkdir(parents=True)
    font.write_bytes(b"")
    brand = BrandModel.model_validate(
        {"font": {"family": "Manrope", "files": ["fonts/Manrope.ttf"]}}
    )
    spec = SpecModel.model_validate({"scenes": [{"id": "a", "layout": "slide", "slide": "a"}]})
    theme = resolve_theme(spec, brand, tmp_path)
    assert "font-family: 'Manrope'" in theme.font_face_css
    assert "'Manrope'" in theme.font_family
