"""Tests for slide line icons."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from reelsmith.errors import ReelsmithError
from reelsmith.slides.icons import ICON_NAMES, icon_svg

_REVIEW_PNG = Path("/Users/dev/.claude/jobs/reelsmith/review/icons.png")


def _parse_svg(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def test_every_icon_is_valid_xml_with_viewbox() -> None:
    for name in ICON_NAMES:
        root = _parse_svg(icon_svg(name))
        assert root.tag.endswith("svg")
        assert root.attrib.get("viewBox") == "0 0 24 24"


def test_size_and_color_applied() -> None:
    svg = icon_svg("check", size=48, color="#2dd4bf", stroke=2.0)
    root = _parse_svg(svg)
    assert root.attrib["width"] == "48"
    assert root.attrib["height"] == "48"
    assert root.attrib["stroke"] == "#2dd4bf"
    assert root.attrib["stroke-width"] == "2.0"


def test_unknown_name_raises_with_available_list() -> None:
    with pytest.raises(ReelsmithError, match="Unknown icon 'missing'") as info:
        icon_svg("missing")
    message = str(info.value)
    for name in ICON_NAMES:
        assert name in message


def test_icon_contact_sheet_png() -> None:
    cells: list[str] = []
    for name in ICON_NAMES:
        svg = icon_svg(name, size=48, color="#e8e8e8", stroke=1.75)
        cells.append(
            f'<div class="cell"><div class="icon">{svg}</div><div class="label">{name}</div></div>'
        )
    grid = "\n".join(cells)
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  body {{ margin: 0; background: #111; color: #aaa; font: 12px system-ui, sans-serif; }}
  #sheet {{ display: inline-block; padding: 24px; background: #111; }}
  .grid {{ display: grid; grid-template-columns: repeat(8, 1fr); gap: 20px; width: 960px; }}
  .cell {{ text-align: center; }}
  .icon {{ display: flex; justify-content: center; align-items: center; height: 56px; }}
  .label {{ margin-top: 6px; word-break: break-all; }}
</style>
</head>
<body>
<div id="sheet">
<div class="grid">
{grid}
</div>
</div>
</body>
</html>"""
    _REVIEW_PNG.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_content(html)
        page.locator("#sheet").screenshot(path=str(_REVIEW_PNG))
        browser.close()
    assert _REVIEW_PNG.is_file()
    assert _REVIEW_PNG.stat().st_size > 1000
