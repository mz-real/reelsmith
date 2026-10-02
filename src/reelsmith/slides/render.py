"""Turn slide models into HTML, still images and short intro clips."""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from pathlib import Path

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
from reelsmith.slides.animate import SlidePage, slide_page
from reelsmith.slides.markup import ACCENT_CLASS, markup_html, plain_text
from reelsmith.slides.studio import step_count, studio_values
from reelsmith.slides.themes import SlideTheme, theme_styles

_TEMPLATES = Path(__file__).resolve().parent / "templates"
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def step_cue_count(slide: SlideItem) -> int:
    """How many build steps come after the first one (steps minus one)."""
    return step_count(slide) - 1


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


def _eyebrow_block(eyebrow: str | None) -> str:
    if not eyebrow:
        return ""
    return f'<p class="eyebrow">{markup_html(eyebrow)}</p>'


def _subtitle_block(subtitle: str | None) -> str:
    if not subtitle:
        return ""
    return f'<p class="subtitle">{markup_html(subtitle)}</p>'


def _title_block(slide: FlowSlide | ChartSlide | BulletsSlide) -> str:
    title = f"<h1>{markup_html(slide.title)}</h1>" if slide.title else ""
    return _eyebrow_block(slide.eyebrow) + title + _subtitle_block(slide.subtitle)


def _future_class(style: str) -> str:
    return "is-hidden" if style == "reveal" else "is-dim"


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
                f'font-size="{axis_font:.1f}">{html.escape(plain_text(label))}</text>'
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
                f"{html.escape(plain_text(label))}</text>"
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
    items = slide.step_items()
    total = len(items)
    future = _future_class(slide.step_style)
    entering = visible_steps - 1
    step_cells: list[str] = []
    for index, item in enumerate(items):
        step_class = "flow-step"
        if index >= visible_steps:
            step_class += f" {future}"
        elif index == entering and index > 0:
            step_class += " enter"
        detail = ""
        if item.detail:
            detail = f'<span class="step-detail">{markup_html(item.detail)}</span>'
        step_cells.append(
            f'<div class="{step_class}" data-step="{index}">'
            f'<span class="step-num">{index + 1}</span>'
            f'<span class="step-label">{markup_html(item.title)}</span>'
            f"{detail}</div>"
        )
        if index < total - 1:
            arrow_class = "flow-arrow"
            if (index + 1) >= visible_steps:
                arrow_class += f" {future}"
            elif index + 1 == entering:
                arrow_class += " enter"
            step_cells.append(f'<div class="{arrow_class}" aria-hidden="true">{arrow}</div>')
    steps_html = "".join(step_cells)
    exit_cells = []
    for label in slide.exits:
        chip_class = "exit-chip"
        if visible_steps < total:
            chip_class += f" {future}"
        elif total > 1:
            chip_class += " enter"
        exit_cells.append(f'<span class="{chip_class}">{markup_html(label)}</span>')
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
.step-detail {{
  text-align: center;
  font-size: {exit_px:.1f}px;
  color: {theme.secondary};
  line-height: 1.3;
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
    future = _future_class(slide.step_style)
    for index, text in enumerate(slide.items):
        item_class = ""
        if index >= visible_items:
            item_class = future
        elif index == visible_items - 1 and index > 0:
            item_class = "enter"
        class_attr = f' class="{item_class}"' if item_class else ""
        lis.append(f"<li{class_attr}>{markup_html(text)}</li>")
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
    """Build self contained HTML for one slide state.

    build_index is the build step shown (0 is the first). None shows the
    finished slide. The page carries the CSS intro of that step.
    """
    last = step_count(slide) - 1
    active = last if build_index is None else max(0, min(build_index, last))
    if theme.style == "studio":
        values = studio_values(slide, theme, active=active, width=width, height=height)
        return apply_template(_load_template("studio"), values)
    return _classic_html(slide, theme, active, width, height)


def _classic_html(slide: SlideItem, theme: SlideTheme, active: int, width: int, height: int) -> str:
    styles = theme_styles(theme, height) + _classic_motion(height)
    logo = _logo_block(theme)
    body_class = "intro" if active == 0 else ""
    if isinstance(slide, TitleSlide):
        return apply_template(
            _load_template("title"),
            {
                "styles": styles,
                "body_class": body_class,
                "logo": logo,
                "eyebrow": _eyebrow_block(slide.eyebrow),
                "title": markup_html(slide.title),
                "subtitle": _subtitle_block(slide.subtitle),
            },
        )
    if isinstance(slide, FlowSlide):
        steps_html, exits_html, flow_css, row_class = _flow_body(
            slide, theme, active + 1, width, height
        )
        return apply_template(
            _load_template("flow"),
            {
                "styles": styles + flow_css,
                "body_class": body_class,
                "logo": logo,
                "heading": _title_block(slide),
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
                "body_class": body_class,
                "logo": logo,
                "heading": _title_block(slide),
                "chart": _chart_svg(slide, theme, height),
            },
        )
    if isinstance(slide, BulletsSlide):
        content, bullet_css = _bullets_body(slide, theme, active + 1, height)
        return apply_template(
            _load_template("bullets"),
            {
                "styles": styles + bullet_css,
                "body_class": body_class,
                "logo": logo,
                "heading": _title_block(slide),
                "content": content,
            },
        )
    raise ReelsmithError(f"Unknown slide kind for '{slide.id}'")


def _classic_motion(height: int) -> str:
    """A gentle rise for the classic themes: the whole slide, then each new item."""
    rise = height * 0.025
    return f"""
.{ACCENT_CLASS} {{ font-weight: 700; }}
.eyebrow {{
  font-size: {height * 0.022:.1f}px; letter-spacing: 0.12em; text-transform: uppercase;
  font-weight: 600;
}}
.is-dim {{ opacity: 0.35; }}
@keyframes rs-rise {{ from {{ opacity: 0; transform: translateY({rise:.1f}px); }} }}
.intro .slide > * {{ animation: rs-rise 460ms cubic-bezier(0.16, 1, 0.3, 1) both; }}
.intro .slide > *:nth-child(2) {{ animation-delay: 60ms; }}
.intro .slide > *:nth-child(3) {{ animation-delay: 120ms; }}
.intro .slide > *:nth-child(n + 4) {{ animation-delay: 180ms; }}
.enter {{ animation: rs-rise 420ms cubic-bezier(0.16, 1, 0.3, 1) 80ms both; }}
"""


def element_boxes(html_text: str, width: int, height: int, selector: str) -> list[dict[str, float]]:
    """Measure element bounding boxes of the finished slide (for tests)."""
    boxes: list[dict[str, float]] = []
    with slide_page(width, height) as page:
        page.load(html_text)
        page.finish()
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
    return boxes


def screenshot_html(html_text: str, width: int, height: int, path: Path) -> None:
    """Render the finished state of a slide page to a PNG."""
    backup_existing(path)
    with slide_page(width, height) as page:
        page.load(html_text)
        page.still(path)


@dataclass(frozen=True)
class RenderStats:
    slides: int
    steps: int
    clips: int
    seconds: float


def step_still_name(slide_id: str, step: int) -> str:
    return f"{slide_id}_step{step}.png"


def step_clip_name(slide_id: str, step: int) -> str:
    return f"{slide_id}_step{step}.mp4"


def _clear_stale_steps(out_dir: Path, slide_id: str, count: int) -> None:
    """Move away step files from an older render that has more steps."""
    pattern = re.compile(rf"^{re.escape(slide_id)}_step(\d+)\.(png|mp4)$")
    for path in out_dir.glob(f"{slide_id}_step*"):
        match = pattern.match(path.name)
        if match and int(match.group(1)) >= count:
            backup_existing(path)


def _render_slide(
    page: SlidePage,
    slide: SlideItem,
    theme: SlideTheme,
    out_dir: Path,
    clips: bool,
) -> list[str]:
    written: list[str] = []
    count = step_count(slide)
    _clear_stale_steps(out_dir, slide.id, count)
    for step in range(count):
        page.load(
            render_slide_html(slide, theme, build_index=step, width=page.width, height=page.height)
        )
        if clips:
            clip_name = step_clip_name(slide.id, step)
            page.clip(out_dir / clip_name)
            written.append(clip_name)
        still_name = step_still_name(slide.id, step)
        backup_existing(out_dir / still_name)
        page.still(out_dir / still_name)
        written.append(still_name)
    final_name = f"{slide.id}.png"
    backup_existing(out_dir / final_name)
    last_still = out_dir / step_still_name(slide.id, count - 1)
    (out_dir / final_name).write_bytes(last_still.read_bytes())
    written.append(final_name)
    return written


def render_slides_to_dir(
    slides: SlidesModel,
    theme: SlideTheme,
    out_dir: Path,
    *,
    width: int,
    height: int,
    clips: bool = True,
    stats: list[RenderStats] | None = None,
) -> list[str]:
    """Write every slide's step stills and intro clips, plus <id>.png, the finished slide.

    Step n shows the first n + 1 items. Returns paths relative to out_dir.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    started = time.monotonic()
    with slide_page(width, height) as page:
        for slide in slides.slides:
            written += _render_slide(page, slide, theme, out_dir, clips)
    if stats is not None:
        steps = sum(step_count(slide) for slide in slides.slides)
        stats.append(
            RenderStats(
                len(slides.slides), steps, steps if clips else 0, time.monotonic() - started
            )
        )
    return written
