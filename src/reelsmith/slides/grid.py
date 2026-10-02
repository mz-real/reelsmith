"""Studio kinds built from cards in a grid: cards, compare, stats and gallery."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from PIL import Image

from reelsmith.errors import ReelsmithError
from reelsmith.models.slides import (
    CardsSlide,
    CompareSlide,
    GalleryImage,
    GallerySlide,
    StatsMetric,
    StatsSlide,
)
from reelsmith.slides.icons import icon_svg
from reelsmith.slides.markup import markup_html
from reelsmith.slides.studio import (
    DIM_OPACITY,
    EASE_IN_OUT,
    EASE_OUT,
    Frame,
    Parts,
    _eyebrow,
    _head,
    _intro_delay,
    cards_css,
    format_value,
    item_classes,
    rgba,
)
from reelsmith.slides.themes import SlideTheme

BAD = "#f87171"  # the cross on the before side, and conflicts


def _icon(name: str | None, frame: Frame, size: float = 32) -> str:
    if name is None:
        return ""
    return icon_svg(name, size=round(size * frame.unit), stroke=1.9)


def _chips(items: list[str], cls: str = "chip") -> str:
    return "".join(f'<span class="{cls}">{markup_html(text)}</span>' for text in items)


def _chip_css(theme: SlideTheme, frame: Frame, font: float = 18) -> str:
    p = frame.px
    return f"""
.chip {{ display: inline-flex; align-items: center; padding: {p(7)} {p(15)};
  border-radius: 999px; font-size: {p(font)}; font-weight: 550; line-height: 1.2;
  color: {rgba(theme.text, 0.78)}; background: {rgba(theme.text, 0.05)};
  border: 1px solid {rgba(theme.text, 0.12)}; white-space: nowrap; }}
"""


def _light_css(theme: SlideTheme, selector: str) -> str:
    """The icon tile fills with the accent while its card is lit."""
    accent = theme.accent
    bg = theme.background
    on = f"{selector}.is-active .ico, {selector}.is-accent:not(.is-future) .ico"
    return f"""
{on} {{ color: {bg}; background: {accent}; border-color: {accent}; }}
@keyframes rs-ico-on {{ from {{ color: {accent}; background: {rgba(accent, 0.1)};
  border-color: {rgba(accent, 0.28)}; }} }}
@keyframes rs-ico-off {{ from {{ color: {bg}; background: {accent}; border-color: {accent}; }} }}
{selector}.to-active .ico {{ animation: rs-ico-on 380ms {EASE_OUT} 170ms both; }}
{selector}.from-active .ico {{ animation: rs-ico-off 360ms {EASE_IN_OUT} both; }}
"""


# Cards ---------------------------------------------------------------------


def _card_columns(frame: Frame, count: int) -> int:
    if frame.wide:
        return count if count <= 5 else 3
    if frame.squat:
        return {2: 2, 3: 3, 4: 2}.get(count, 3)
    return 1 if count <= 3 else 2


def cards_parts(slide: CardsSlide, theme: SlideTheme, frame: Frame, active: int) -> Parts:
    count = len(slide.cards)
    cells = []
    for index, card in enumerate(slide.cards):
        cell, classes = item_classes(
            index, active, slide.step_style, accent=card.accent, base="card tile"
        )
        number = card.number if card.number is not None else f"{index + 1:02d}"
        top = ""
        if card.icon:
            top += f'<div class="ico">{_icon(card.icon, frame)}</div>'
        top += f'<div class="tnum">{markup_html(number)}</div>' if number else ""
        detail = f'<div class="cdetail">{markup_html(card.detail)}</div>' if card.detail else ""
        chips = f'<div class="tchips">{_chips(card.chips)}</div>' if card.chips else ""
        cells.append(
            f'<div class="{cell}" data-i="{index}"><div class="{classes}">'
            f'<div class="tile-top">{top}</div><div class="ctitle">{markup_html(card.title)}</div>'
            f"{detail}{chips}</div></div>"
        )
    columns = _card_columns(frame, count)
    head = _head(_eyebrow(slide), slide.title, slide.subtitle, "title")
    body = f'<div class="cards" style="--cols: {columns}">{"".join(cells)}</div>'
    css = _cards_kind_css(theme, frame, count, columns)
    return Parts(head, body, css + cards_css(frame, count, active == 0), "cards")


def _cards_kind_css(theme: SlideTheme, frame: Frame, count: int, columns: int) -> str:
    p = frame.px
    rows = -(-count // columns)
    scale = {1: 1.2, 2: 1.2, 3: 1.2, 4: 1.12, 5: 0.98}.get(columns, 1.0)
    if rows >= 2 and frame.wide:
        scale = min(scale, 1.0)
    if frame.squat:
        scale *= 0.8 if rows >= 2 or columns >= 3 else 0.9
    if not frame.wide and not frame.squat and rows >= 3:
        scale *= 0.92
    pad_y = 32 * scale + 4
    pad_x = 30 * scale + 2
    accent = theme.accent
    return (
        f"""
.cards {{ display: grid; grid-template-columns: repeat(var(--cols), minmax(0, 1fr));
  gap: {p(24 if frame.wide else 20)}; width: 100%; align-items: stretch; }}
.cards .cell {{ display: flex; min-width: 0; }}
.cards .cell > .card {{ flex: 1; }}
.tile {{ display: flex; flex-direction: column; padding: {p(pad_y)} {p(pad_x)} {p(pad_y + 2)}; }}
.tile-top {{ display: flex; align-items: center; justify-content: space-between;
  margin-bottom: {p(26 * scale)}; min-height: {p(8)}; }}
.ico {{ display: grid; place-items: center; width: {p(64 * scale)}; height: {p(64 * scale)};
  border-radius: {p(16 * scale)}; color: var(--accent); background: {rgba(accent, 0.1)};
  border: 1px solid {rgba(accent, 0.28)}; }}
.ico svg {{ width: {p(32 * scale)}; height: {p(32 * scale)}; }}
.tnum {{ font-size: {p(19 * scale)}; font-weight: 700; letter-spacing: 0.08em;
  color: var(--faint); font-variant-numeric: tabular-nums; margin-left: auto; }}
.tile.is-active .tnum, .tile.is-accent:not(.is-future) .tnum {{ color: var(--accent); }}
.tile .ctitle {{ font-size: {p(32 * scale)}; font-weight: 680; line-height: 1.15;
  letter-spacing: -0.015em; }}
.tile .cdetail {{ margin-top: {p(12 * scale)}; font-size: {p(22 * scale)}; line-height: 1.42;
  color: var(--muted); text-wrap: pretty; }}
.tchips {{ display: flex; flex-wrap: wrap; gap: {p(8)}; margin-top: auto;
  padding-top: {p(22 * scale)}; }}
"""
        + _chip_css(theme, frame, 19 * min(max(scale, 0.86), 1.05))
        + _light_css(theme, ".tile")
    )


# Compare -------------------------------------------------------------------


def compare_parts(slide: CompareSlide, theme: SlideTheme, frame: Frame, active: int) -> Parts:
    rows = []
    cross = _icon("cross", frame, 22)
    tick = _icon("check", frame, 22)
    arrow = (
        '<svg viewBox="0 0 64 24" aria-hidden="true"><path d="M4 12 H58 M50 4 L58 12 L50 20"/>'
        "</svg>"
    )
    for index, row in enumerate(slide.rows):
        cell, classes = item_classes(index, active, slide.step_style, base="crow")
        rows.append(
            f'<div class="{cell}" data-i="{index}"><div class="{classes}">'
            f'<div class="card side before"><span class="mk bad">{cross}</span>'
            f'<span class="stext">{markup_html(row.before)}</span></div>'
            f'<div class="carrow">{arrow}</div>'
            f'<div class="card side now"><span class="mk good">{tick}</span>'
            f'<span class="stext">{markup_html(row.now)}</span></div></div></div>'
        )
    labels = (
        f'<div class="cmp-head"><div class="ch before">{markup_html(slide.before_label)}</div>'
        f'<div class="ch-gap"></div><div class="ch now">{markup_html(slide.now_label)}</div></div>'
    )
    head = _head(_eyebrow(slide), slide.title, slide.subtitle, "title")
    layout = "wide" if not frame.squat and frame.wide else "stack"
    body = f'<div class="cmp {layout}">{labels}{"".join(rows)}</div>'
    css = _compare_css(theme, frame, len(slide.rows), layout)
    return Parts(head, body, css + cards_css(frame, len(slide.rows), active == 0), "compare")


def _compare_css(theme: SlideTheme, frame: Frame, count: int, layout: str) -> str:
    p = frame.px
    accent = theme.accent
    text = theme.text
    scale = 1.12 if count <= 3 else max(0.84, 3.6 / count)
    if frame.squat:
        scale *= 0.86
    css = f"""
.cmp {{ display: flex; flex-direction: column; gap: {p(18 * scale)}; width: 100%; }}
.cmp-head {{ display: flex; align-items: center; font-size: {p(18)}; font-weight: 700;
  letter-spacing: 0.14em; text-transform: uppercase; }}
.ch.before {{ color: {rgba(BAD, 0.8)}; }}
.ch.now {{ color: var(--accent); }}
.crow {{ display: flex; align-items: stretch; width: 100%; }}
.cmp .cell {{ display: flex; }}
.cmp .cell > .crow {{ flex: 1; }}
.side {{ flex: 1 1 0; display: flex; align-items: center; gap: {p(22)};
  padding: {p(26 * scale + 2)} {p(30)}; font-size: {p(30 * scale)}; line-height: 1.3;
  font-weight: 550; letter-spacing: -0.01em; }}
.side.before {{ color: {rgba(text, 0.62)}; background: {rgba(text, 0.02)}; }}
.side.now {{ color: var(--text); }}
.mk {{ flex: 0 0 auto; display: grid; place-items: center; width: {p(46)}; height: {p(46)};
  border-radius: 50%; }}
.mk svg {{ width: {p(24)}; height: {p(24)}; }}
.mk.bad {{ color: {BAD}; background: {rgba(BAD, 0.12)}; border: 1px solid {rgba(BAD, 0.3)}; }}
.mk.good {{ color: {theme.background}; background: var(--accent); }}
.crow:not(.is-future) .side.now::before {{ opacity: 1; }}
.carrow {{ flex: 0 0 auto; display: grid; place-items: center; }}
.carrow svg {{ overflow: visible; }}
.carrow path {{ fill: none; stroke: {rgba(accent, 0.75)}; stroke-width: 2.6;
  stroke-linecap: round; stroke-linejoin: round; }}
.crow.is-future.dim {{ opacity: {DIM_OPACITY}; }}
.crow.lift {{ animation: rs-lift 420ms {EASE_OUT} 120ms both; }}
.crow.to-active .side.now {{ animation: rs-nudge 420ms {EASE_OUT} 260ms both; }}
.crow.to-active .side.now::before {{ animation: rs-fade 380ms {EASE_OUT} 300ms both; }}
.crow.to-active .mk.good {{ animation: rs-pop-in 360ms {EASE_OUT} 360ms both; }}
.crow.to-active .carrow path {{ animation: rs-fade 300ms ease-out 200ms both; }}
@keyframes rs-pop-in {{ from {{ opacity: 0; transform: scale(0.4); }} }}
"""
    if layout == "wide":
        return (
            css
            + f"""
.ch-gap {{ width: {p(96)}; }}
.ch {{ flex: 1 1 0; padding-left: {p(4)}; }}
.carrow {{ width: {p(96)}; }}
.carrow svg {{ width: {p(52)}; height: {p(22)}; }}
"""
        )
    return (
        css
        + f"""
.cmp-head {{ display: none; }}
.crow {{ flex-direction: column; }}
.carrow {{ height: {p(40 * scale)}; }}
.carrow svg {{ width: {p(30)}; height: {p(16)}; transform: rotate(90deg); }}
"""
    )


# Stats ---------------------------------------------------------------------


def _decimals(value: float) -> int:
    text = format_value(value)
    return min(len(text.split(".")[1]), 2) if "." in text else 0


def _hero(slide: StatsSlide, theme: SlideTheme) -> tuple[str, str]:
    """The hero number, which counts up from zero during the slide's entrance."""
    hero = slide.hero
    places = _decimals(hero.value)
    scaled = round(abs(hero.value) * 10**places)
    sign = "-" if hero.value < 0 else ""
    if places:
        unit = 10**places
        style = "decimal-leading-zero" if places == 2 else "decimal"
        number_css = (
            f".count {{ --n: {scaled}; --i: round(down, calc(var(--n) / {unit}), 1);"
            f" --f: mod(var(--n), {unit}); counter-reset: ci var(--i) cf var(--f); }}\n"
            f'.count::after {{ content: "{sign}" counter(ci) "." counter(cf, {style}); }}'
        )
    else:
        number_css = (
            f".count {{ --n: {scaled}; counter-reset: ci var(--n); }}\n"
            f'.count::after {{ content: "{sign}" counter(ci); }}'
        )
    css = f"""
@property --n {{ syntax: "<integer>"; inherits: false; initial-value: 0; }}
@property --i {{ syntax: "<integer>"; inherits: false; initial-value: 0; }}
@property --f {{ syntax: "<integer>"; inherits: false; initial-value: 0; }}
@keyframes rs-count {{ from {{ --n: 0; }} }}
{number_css}
.intro .count {{ animation: rs-count 560ms cubic-bezier(0.22, 1, 0.36, 1) 80ms both; }}
"""
    suffix = f'<span class="suffix">{markup_html(hero.suffix)}</span>' if hero.suffix else ""
    of = f'<span class="of">/ {format_value(hero.of)}</span>' if hero.of is not None else ""
    value = format_value(hero.value)
    html = (
        f'<div class="hero" data-i="0"><div class="hero-num" aria-label="{value}">'
        f'<span class="count"></span>{suffix}{of}</div>'
        f'<div class="hero-label">{markup_html(hero.label)}</div></div>'
    )
    return html, css


def _metric(metric: StatsMetric) -> str:
    bar = ""
    if isinstance(metric.bar, tuple):
        start, end = metric.bar
        bar = (
            f'<div class="track"><div class="fill band" style="left: {start * 100:.2f}%; '
            f'width: {(end - start) * 100:.2f}%"></div></div>'
        )
    elif metric.bar is not None:
        bar = (
            f'<div class="track"><div class="fill" style="width: {metric.bar * 100:.2f}%">'
            "</div></div>"
        )
    return (
        f'<div class="mlabel">{markup_html(metric.label)}</div>'
        f'<div class="mvalue">{markup_html(metric.value)}</div>{bar}'
    )


def stats_parts(slide: StatsSlide, theme: SlideTheme, frame: Frame, active: int) -> Parts:
    stages = slide.stages()
    hero_html, hero_css = _hero(slide, theme)
    side = []
    for index, metric in enumerate(slide.metrics, start=1):
        cell, classes = item_classes(index, active, slide.step_style, base="card metric")
        side.append(
            f'<div class="{cell}" data-i="{index}"><div class="{classes}">{_metric(metric)}'
            "</div></div>"
        )
    if slide.chips:
        index = len(stages) - 1
        classes = "schips"
        if index > active:
            classes += f" is-future {slide.step_style}"
        elif index == active:
            classes += f" enter {slide.step_style}"
        tick = _icon("check", frame, 18)
        chips = "".join(
            f'<span class="schip" data-c="{n}"><span class="sk">{tick}</span>'
            f"<span>{markup_html(text)}</span></span>"
            for n, text in enumerate(slide.chips)
        )
        side.append(f'<div class="cell" data-c="all"><div class="{classes}">{chips}</div></div>')
    layout = "wide" if frame.wide else "stack"
    head = _head(_eyebrow(slide), slide.title, slide.subtitle, "title")
    body = f'<div class="stats {layout}">{hero_html}<div class="side">{"".join(side)}</div></div>'
    css = hero_css + _stats_css(theme, frame, slide, layout)
    return Parts(head, body, css + cards_css(frame, len(stages), active == 0), "stats")


def _stats_css(theme: SlideTheme, frame: Frame, slide: StatsSlide, layout: str) -> str:
    p = frame.px
    accent = theme.accent
    text = theme.text
    hero_px = 340 if frame.wide else (210 if frame.squat else 260)
    chip_columns = 3 if len(slide.chips) > 6 or layout == "wide" else 2
    if layout == "wide" and len(slide.chips) <= 4:
        chip_columns = 2
    chip_scale = 0.9 if frame.squat else (1.18 if frame.wide else 1.05)
    css = f"""
.stats {{ display: grid; width: 100%; align-items: center; }}
.stats.wide {{ grid-template-columns: minmax(0, 0.82fr) minmax(0, 1.18fr); gap: {p(72)}; }}
.stats.stack {{ grid-template-columns: minmax(0, 1fr); gap: {p(36 if frame.squat else 48)}; }}
.hero-num {{ display: flex; align-items: baseline; gap: {p(14)}; line-height: 0.86;
  font-size: {p(hero_px)}; font-weight: 800; letter-spacing: -0.05em;
  font-variant-numeric: tabular-nums;
  background: linear-gradient(180deg, {text} 20%, {rgba(accent, 0.95)} 120%);
  -webkit-background-clip: text; background-clip: text; color: transparent; }}
.hero-num .count::after {{ background: inherit; -webkit-background-clip: text;
  background-clip: text; }}
.hero-num .suffix, .hero-num .of {{ font-size: 0.32em; font-weight: 700;
  letter-spacing: -0.02em; color: var(--muted); -webkit-text-fill-color: var(--muted); }}
.hero-label {{ margin-top: {p(26)}; font-size: {p(38 if frame.wide else 32)}; font-weight: 600;
  line-height: 1.25; letter-spacing: -0.01em; max-width: {p(620) if frame.wide else "100%"};
  text-wrap: balance; }}
.hero-label::before {{ content: ""; display: block; width: {p(56)}; height: {p(4)};
  border-radius: {p(4)}; background: var(--accent); margin-bottom: {p(22)}; }}
.side {{ display: flex; flex-direction: column; gap: {p(18)}; min-width: 0; }}
.side .cell {{ display: flex; }}
.side .cell > * {{ flex: 1; }}
.metric {{ padding: {p(30)} {p(34)} {p(32)}; }}
.mlabel {{ font-size: {p(17)}; font-weight: 700; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--faint); }}
.metric.is-active .mlabel, .metric.is-accent .mlabel {{ color: var(--accent); }}
.mvalue {{ margin-top: {p(10)}; font-size: {p(38 if frame.wide else 30)}; font-weight: 680;
  letter-spacing: -0.015em; line-height: 1.2; }}
.track {{ position: relative; margin-top: {p(18)}; height: {p(10)}; border-radius: 999px;
  background: {rgba(text, 0.08)}; overflow: hidden; }}
.fill {{ position: absolute; left: 0; top: 0; bottom: 0; border-radius: 999px;
  background: linear-gradient(90deg, {rgba(accent, 0.55)}, {accent});
  box-shadow: 0 0 {p(18)} {rgba(accent, 0.55)}; transform-origin: left; }}
.schips {{ display: grid; grid-template-columns: repeat({chip_columns}, minmax(0, 1fr));
  gap: {p(12 * chip_scale)}; }}
.schips.is-future.dim {{ opacity: {DIM_OPACITY}; }}
.schip {{ display: flex; align-items: center; gap: {p(12)}; min-width: 0;
  padding: {p(14 * chip_scale)} {p(18)}; border-radius: {p(12)};
  font-size: {p(22 * chip_scale)}; font-weight: 560; line-height: 1.2;
  background: {rgba(text, 0.04)}; border: 1px solid {rgba(text, 0.1)}; }}
.sk {{ flex: 0 0 auto; display: grid; place-items: center; width: {p(28)}; height: {p(28)};
  border-radius: 50%; color: var(--accent); background: {rgba(accent, 0.14)}; }}
.sk svg {{ width: {p(16)}; height: {p(16)}; }}
.intro .hero {{ animation: rs-rise 420ms {EASE_OUT} 60ms both; }}
.intro .hero-label::before {{ transform-origin: left;
  animation: rs-grow-x 420ms {EASE_OUT} 220ms both; }}
.metric.to-active .fill {{ animation: rs-grow-x 520ms {EASE_OUT} 160ms both; }}
.intro .metric.is-active .fill {{ animation: rs-grow-x 520ms {EASE_OUT} 200ms both; }}
"""
    for n in range(len(slide.chips)):
        delay = _intro_delay(n, len(slide.chips), 120, 320)
        css += (
            f'.schips.enter [data-c="{n}"] {{ animation: rs-chip-in 320ms {EASE_OUT} '
            f"{delay}ms both; }}\n"
        )
    css += (
        f"@keyframes rs-chip-in {{ from {{ opacity: 0; transform: translateY({p(14)}); }} }}\n"
        f".schips.enter.dim .schip {{ animation-name: rs-chip-lift; }}\n"
        f"@keyframes rs-chip-lift {{ from {{ opacity: {DIM_OPACITY}; }} }}\n"
        ".schips.is-future.reveal { visibility: hidden; }\n"
    )
    return css


# Gallery -------------------------------------------------------------------


def _image_uri(image: GalleryImage, theme: SlideTheme) -> tuple[str, float]:
    """The image as a data URI, and its width over height."""
    root = theme.asset_root or Path.cwd()
    path = (root / image.image).resolve()
    if not path.is_file():
        raise ReelsmithError(
            f"Gallery image {image.image} not found in {root}",
            fix="Put the image in the demo folder, or fix its path in slides.yaml",
        )
    try:
        with Image.open(path) as opened:
            width, height = opened.size
    except OSError as exc:
        raise ReelsmithError(f"Could not read gallery image {image.image}: {exc}") from exc
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}", width / height


def _frame_kind(image: GalleryImage, aspect: float) -> str:
    if image.frame != "auto":
        return image.frame
    if aspect < 0.8:
        return "phone"
    if aspect > 1.25:
        return "browser"
    return "plain"


def gallery_parts(slide: GallerySlide, theme: SlideTheme, frame: Frame, active: int) -> Parts:
    p = frame.px
    figures = []
    aspects = []
    bars = 0.0
    for index, image in enumerate(slide.images):
        uri, aspect = _image_uri(image, theme)
        kind = _frame_kind(image, aspect)
        aspects.append(aspect)
        cell, classes = item_classes(index, active, slide.step_style, base=f"card dev {kind}")
        top = '<div class="dbar"><i></i><i></i><i></i><b></b></div>' if kind == "browser" else ""
        notch = '<span class="notch"></span>' if kind == "phone" else ""
        figures.append(
            f'<figure class="{cell}" data-i="{index}" style="--a: {aspect:.5f}">'
            f'<div class="{classes}">{top}<div class="screen">{notch}'
            f'<img src="{uri}" alt=""></div></div>'
            f"<figcaption>{markup_html(image.label)}</figcaption></figure>"
        )
        bars = max(bars, 40.0 if kind == "browser" else 0.0)
    gap = 56 if frame.wide else 36
    bezel = 14
    reserved_h = 66 + bars + 2 * bezel  # caption, browser bar and bezel per row
    rows = gallery_rows(aspects, frame)
    limits = [f"calc((100cqh - {p(len(rows) * reserved_h + (len(rows) - 1) * gap)}) / {len(rows)})"]
    for row in rows:
        width = (len(row) - 1) * gap + len(row) * 2 * bezel
        limits.append(f"calc((100cqw - {p(width)}) / {sum(aspects[i] for i in row):.5f})")
    css = f"""
.kind-gallery .body {{ container-type: size; justify-content: center; }}
.gal {{ --h: min({", ".join(limits)});
  display: flex; flex-direction: column; align-items: center; gap: {p(gap)}; }}
.grow {{ display: flex; align-items: flex-end; justify-content: center; gap: {p(gap)}; }}
.gal .cell {{ display: flex; flex-direction: column; align-items: center; }}
.dev {{ padding: {p(bezel)}; border-radius: {p(22)}; background: {rgba(theme.text, 0.045)}; }}
.dev .screen {{ position: relative; overflow: hidden; height: var(--h);
  width: calc(var(--h) * var(--a)); border-radius: {p(10)}; background: #000; }}
.dev .screen img {{ display: block; width: 100%; height: 100%; object-fit: cover; }}
.dev.phone {{ border-radius: {p(46)}; background: {rgba(theme.text, 0.06)}; }}
.dev.phone .screen {{ border-radius: {p(34)}; }}
.notch {{ position: absolute; z-index: 1; top: {p(12)}; left: 50%; width: 28%; height: {p(22)};
  margin-left: -14%; border-radius: 999px; background: #000; }}
.dbar {{ display: flex; align-items: center; gap: {p(8)}; height: {p(bars)};
  padding: 0 {p(6)} {p(12)}; }}
.dbar i {{ width: {p(11)}; height: {p(11)}; border-radius: 50%;
  background: {rgba(theme.text, 0.22)}; }}
.dbar b {{ flex: 1; height: {p(22)}; margin-left: {p(14)}; border-radius: 999px;
  background: {rgba(theme.text, 0.07)}; }}
.gal figcaption {{ margin-top: {p(22)}; font-size: {p(24)}; font-weight: 620;
  letter-spacing: -0.005em; color: var(--muted); white-space: nowrap; }}
.gal .cell:has(.is-active) figcaption {{ color: var(--accent); }}
"""
    head = _head(_eyebrow(slide), slide.title, slide.subtitle, "title")
    lines = "".join(f'<div class="grow">{"".join(figures[i] for i in row)}</div>' for row in rows)
    body = f'<div class="gal">{lines}</div>'
    return Parts(head, body, css + cards_css(frame, len(figures), active == 0), "gallery")


def gallery_rows(aspects: list[float], frame: Frame) -> list[list[int]]:
    """Split the images, in order, into the rows that show them largest.

    Wide frames keep one row. A portrait frame usually stacks them, with
    narrow images sharing a row.
    """
    margin = max(frame.width * 0.06, 64 * frame.unit)
    room_w = frame.width - 2 * margin
    room_h = frame.height * (0.5 if frame.wide or frame.squat else 0.56)
    count = len(aspects)
    best: list[list[int]] = [list(range(count))]
    best_h = 0.0
    for mask in range(1 << (count - 1)):  # a cut after image i when bit i is set
        rows: list[list[int]] = [[0]]
        for index in range(1, count):
            if mask >> (index - 1) & 1:
                rows.append([])
            rows[-1].append(index)
        tall = (room_h - len(rows) * 120 * frame.unit) / len(rows)
        wide = min(
            (room_w - len(row) * 60 * frame.unit) / sum(aspects[i] for i in row) for row in rows
        )
        height = min(tall, wide)
        if height > best_h + 1:
            best, best_h = rows, height
    return best
