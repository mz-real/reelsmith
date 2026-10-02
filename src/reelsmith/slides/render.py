"""Turn slide models into HTML and PNG images."""

from __future__ import annotations

import html
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

from reelsmith.errors import ReelsmithError
from reelsmith.fsutil import backup_existing
from reelsmith.models.slides import (
    BulletsSlide,
    ChartSlide,
    FlowSlide,
    SlideItem,
    SlidesModel,
    TitleSlide,
)
from reelsmith.slides.themes import SlideTheme, theme_styles

_TEMPLATES = Path(__file__).resolve().parent / "templates"
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def step_cue_count(slide: SlideItem) -> int:
    """How many build step images to write (steps minus one)."""
    if isinstance(slide, FlowSlide):
        return max(0, len(slide.steps) - 1)
    if isinstance(slide, BulletsSlide):
        return max(0, len(slide.items) - 1)
    return 0


def format_chart_value(value: float) -> str:
    """Format a chart number without a trailing .0."""
    rounded = round(value, 4)
    if abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))
    text = f"{rounded:.4f}".rstrip("0").rstrip(".")
    return text


def apply_template(text: str, values: dict[str, str]) -> str:
    """Replace {{ name }} placeholders in a template string."""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(key)
        return values[key]

    return _PLACEHOLDER.sub(repl, text)


def _load_template(name: str) -> str:
    path = _TEMPLATES / f"{name}.html"
    if not path.is_file():
        raise ReelsmithError(f"Slide template missing: {name}")
    return path.read_text(encoding="utf-8")


def _logo_block(theme: SlideTheme) -> str:
    if theme.logo_uri is None:
        return ""
    return f'<img class="logo" src="{html.escape(theme.logo_uri, quote=True)}" alt="">'


def _title_block(title: str | None) -> str:
    if not title:
        return ""
    return f"<h1>{html.escape(title)}</h1>"


def _chart_svg(slide: ChartSlide, theme: SlideTheme, frame_height: int) -> str:
    count = len(slide.labels)
    width = 800
    height = 420
    pad = 48
    inner_w = width - pad * 2
    inner_h = height - pad * 2
    axis_font = frame_height * 0.024
    value_font = frame_height * 0.028
    max_val = max(slide.values) if slide.values else 1.0
    if max_val <= 0:
        max_val = 1.0
    parts = [
        f'<svg viewBox="0 0 {width} {height}" '
        f'width="100%" height="auto" xmlns="http://www.w3.org/2000/svg">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="none"/>',
    ]
    if slide.chart_type == "bars":
        bar_w = inner_w / max(count, 1) * 0.6
        gap = inner_w / max(count, 1)
        for index, (label, value) in enumerate(zip(slide.labels, slide.values, strict=True)):
            # Leave room above the tallest bar for its value label.
            bar_h = (value / max_val) * (inner_h - value_font * 1.4)
            x = pad + index * gap + (gap - bar_w) / 2
            y = pad + inner_h - bar_h
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
                f'fill="{theme.primary}" rx="4"/>'
            )
            value_y = max(pad + value_font, y - axis_font * 0.35)
            parts.append(
                f'<text x="{x + bar_w / 2:.1f}" y="{value_y:.1f}" text-anchor="middle" '
                f'fill="{theme.text}" font-size="{value_font:.1f}">'
                f"{html.escape(format_chart_value(value))}</text>"
            )
            parts.append(
                f'<text x="{x + bar_w / 2:.1f}" y="{height - pad * 0.35:.1f}" '
                f'text-anchor="middle" fill="{theme.secondary}" '
                f'font-size="{axis_font:.1f}">{html.escape(label)}</text>'
            )
    else:
        points: list[tuple[float, float]] = []
        step_x = inner_w / max(count - 1, 1)
        for index, value in enumerate(slide.values):
            x = pad + index * step_x
            y = pad + inner_h - (value / max_val) * inner_h
            points.append((x, y))
        if len(points) >= 2:
            path_d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)
            parts.append(
                f'<path d="{path_d}" fill="none" stroke="{theme.primary}" '
                f'stroke-width="3" stroke-linecap="round"/>'
            )
        for (x, y), label in zip(points, slide.labels, strict=True):
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{theme.accent}"/>')
            parts.append(
                f'<text x="{x:.1f}" y="{height - pad * 0.35:.1f}" text-anchor="middle" '
                f'fill="{theme.secondary}" font-size="{axis_font:.1f}">'
                f"{html.escape(label)}</text>"
            )
    parts.append("</svg>")
    return "\n".join(parts)


def _flow_body(
    slide: FlowSlide,
    theme: SlideTheme,
    visible_steps: int,
    width: int,
    height: int,
) -> tuple[str, str, str, str]:
    portrait = height > width
    arrow = "↓" if portrait else "→"
    row_class = "flow-row portrait" if portrait else "flow-row"
    step_label_px = height * 0.032
    step_num_px = height * 0.024
    arrow_px = height * 0.045
    exit_px = height * 0.024
    gap_px = height * 0.015
    pad_px = height * 0.018
    min_step_w = height * 0.14
    max_step_w = height * 0.22
    total = len(slide.steps)
    step_cells: list[str] = []
    for index, label in enumerate(slide.steps):
        hidden = index >= visible_steps
        step_class = "flow-step is-hidden" if hidden else "flow-step"
        step_cells.append(
            f'<div class="{step_class}" data-step="{index}">'
            f'<span class="step-num">{index + 1}</span>'
            f'<span class="step-label">{html.escape(label)}</span>'
            "</div>"
        )
        if index < len(slide.steps) - 1:
            arrow_hidden = (index + 1) >= visible_steps
            arrow_class = "flow-arrow is-hidden" if arrow_hidden else "flow-arrow"
            step_cells.append(f'<div class="{arrow_class}" aria-hidden="true">{arrow}</div>')
    steps_html = "".join(step_cells)
    hide_exits = visible_steps < total
    exit_cells = []
    for label in slide.exits:
        chip_class = "exit-chip is-hidden" if hide_exits else "exit-chip"
        exit_cells.append(f'<span class="{chip_class}">{html.escape(label)}</span>')
    exits_html = "".join(exit_cells)
    flex_dir = "column" if portrait else "row"
    flow_css = f"""
.flow-row {{
  display: flex;
  flex-direction: {flex_dir};
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: {gap_px:.1f}px;
  width: 100%;
  max-width: 100%;
}}
.flow-step {{
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: {gap_px * 0.4:.1f}px;
  padding: {pad_px:.1f}px {pad_px * 1.2:.1f}px;
  border-radius: {pad_px:.1f}px;
  background: {theme.muted};
  min-width: {min_step_w:.1f}px;
  max-width: {max_step_w:.1f}px;
  flex: 0 1 auto;
}}
.step-num {{
  font-size: {step_num_px:.1f}px;
  color: {theme.secondary};
}}
.step-label {{
  text-align: center;
  font-size: {step_label_px:.1f}px;
  line-height: 1.25;
}}
.flow-arrow {{
  font-size: {arrow_px:.1f}px;
  color: {theme.accent};
  line-height: 1;
  flex: 0 0 auto;
}}
.exits {{
  display: flex;
  flex-wrap: wrap;
  gap: {gap_px:.1f}px;
  justify-content: center;
  margin-top: {gap_px:.1f}px;
  width: 100%;
}}
.exit-chip {{
  padding: {gap_px * 0.5:.1f}px {gap_px * 1.1:.1f}px;
  border-radius: 999px;
  border: 1px solid {theme.secondary};
  color: {theme.secondary};
  font-size: {exit_px:.1f}px;
}}
"""
    return steps_html, exits_html, flow_css, row_class


def _bullets_body(
    slide: BulletsSlide,
    theme: SlideTheme,
    visible_items: int,
    height: int,
) -> tuple[str, str]:
    bullet_px = height * 0.032
    gap_px = height * 0.015
    pad_px = height * 0.018
    lis: list[str] = []
    for index, text in enumerate(slide.items):
        hidden = index >= visible_items
        item_class = "is-hidden" if hidden else ""
        class_attr = f' class="{item_class}"' if item_class else ""
        lis.append(f"<li{class_attr}>{html.escape(text)}</li>")
    bullet_css = f"""
ul.bullets {{
  list-style: none;
  width: min(90%, 52rem);
  display: flex;
  flex-direction: column;
  gap: {gap_px:.1f}px;
}}
ul.bullets li {{
  padding: {pad_px:.1f}px {pad_px * 1.2:.1f}px {pad_px:.1f}px {pad_px * 2.2:.1f}px;
  background: {theme.muted};
  border-radius: {pad_px:.1f}px;
  position: relative;
  font-size: {bullet_px:.1f}px;
  line-height: 1.35;
}}
ul.bullets li::before {{
  content: "•";
  position: absolute;
  left: {pad_px:.1f}px;
  color: {theme.primary};
  font-weight: 700;
}}
"""
    return f'<ul class="bullets">{"".join(lis)}</ul>', bullet_css


def render_slide_html(
    slide: SlideItem,
    theme: SlideTheme,
    *,
    build_index: int | None,
    width: int,
    height: int,
) -> str:
    """Build self contained HTML for one slide state."""
    styles = theme_styles(theme, height)
    logo = _logo_block(theme)
    if isinstance(slide, TitleSlide):
        subtitle = ""
        if slide.subtitle:
            subtitle = f'<p class="subtitle">{html.escape(slide.subtitle)}</p>'
        return apply_template(
            _load_template("title"),
            {
                "styles": styles,
                "logo": logo,
                "title": html.escape(slide.title),
                "subtitle": subtitle,
            },
        )
    if isinstance(slide, FlowSlide):
        total = len(slide.steps)
        visible = total if build_index is None else min(build_index + 1, total)
        steps_html, exits_html, flow_css, row_class = _flow_body(
            slide, theme, visible, width, height
        )
        return apply_template(
            _load_template("flow"),
            {
                "styles": styles + flow_css,
                "logo": logo,
                "heading": _title_block(slide.title),
                "steps": steps_html,
                "exits": exits_html,
                "flow_row_class": row_class,
            },
        )
    if isinstance(slide, ChartSlide):
        chart_css = """
.chart-wrap { width: min(92%, 52rem); }
"""
        return apply_template(
            _load_template("chart"),
            {
                "styles": styles + chart_css,
                "logo": logo,
                "heading": _title_block(slide.title),
                "chart": _chart_svg(slide, theme, height),
            },
        )
    if isinstance(slide, BulletsSlide):
        total = len(slide.items)
        visible = total if build_index is None else min(build_index + 1, total)
        content, bullet_css = _bullets_body(slide, theme, visible, height)
        return apply_template(
            _load_template("bullets"),
            {
                "styles": styles + bullet_css,
                "logo": logo,
                "heading": _title_block(slide.title),
                "content": content,
            },
        )
    raise ReelsmithError(f"Unknown slide kind for '{slide.id}'")


def element_boxes(html_text: str, width: int, height: int, selector: str) -> list[dict[str, float]]:
    """Measure element bounding boxes after layout (for tests)."""
    boxes: list[dict[str, float]] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_content(html_text, wait_until="load")
            for handle in page.locator(selector).element_handles():
                box = handle.bounding_box()
                if box is not None:
                    boxes.append(
                        {
                            "x": float(box["x"]),
                            "y": float(box["y"]),
                            "width": float(box["width"]),
                            "height": float(box["height"]),
                        }
                    )
            browser.close()
    except Exception as exc:
        raise ReelsmithError(
            "Could not measure slide layout with Playwright.",
            fix="reelsmith setup browser",
        ) from exc
    return boxes


def screenshot_html(html_text: str, width: int, height: int, path: Path) -> None:
    """Render HTML to a PNG at the given viewport size."""
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_existing(path)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_content(html_text, wait_until="load")
            page.screenshot(path=str(path), type="png")
            browser.close()
    except Exception as exc:
        raise ReelsmithError(
            "Could not render slides with Playwright.",
            fix="reelsmith setup browser",
        ) from exc


def render_slides_to_dir(
    slides: SlidesModel,
    theme: SlideTheme,
    out_dir: Path,
    *,
    width: int,
    height: int,
) -> list[str]:
    """Write PNGs for every slide. Returns paths relative to out_dir."""
    written: list[str] = []
    for slide in slides.slides:
        main_name = f"{slide.id}.png"
        html_final = render_slide_html(slide, theme, build_index=None, width=width, height=height)
        screenshot_html(html_final, width, height, out_dir / main_name)
        written.append(main_name)
        cues = step_cue_count(slide)
        for step in range(cues):
            step_name = f"{slide.id}_step{step + 1}.png"
            html_step = render_slide_html(
                slide, theme, build_index=step, width=width, height=height
            )
            screenshot_html(html_step, width, height, out_dir / step_name)
            written.append(step_name)
    return written
