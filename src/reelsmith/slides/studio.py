"""The Studio look: a deep gradient, soft glows, left aligned type and cards.

Every size is in 1080p pixels times ``unit`` (the short side over 1080), so
the same slide reads the same in 16:9, 9:16, 1:1 and 4K.

Each slide state is one HTML page. Its CSS animations are the intro of that
state: step 0 is the slide's entrance, step n draws the arrow to card n and
lights it up. The renderer steps these animations frame by frame, and the
finished page is the still image.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

from reelsmith.models.slides import (
    BulletsSlide,
    ChartSlide,
    FlowSlide,
    SlideItem,
    TitleSlide,
)
from reelsmith.slides.markup import ACCENT_CLASS, markup_html
from reelsmith.slides.themes import SlideTheme

EASE_OUT = "cubic-bezier(0.16, 1, 0.3, 1)"
EASE_IN_OUT = "cubic-bezier(0.65, 0, 0.35, 1)"
DIM_OPACITY = 0.35
INTRO_END_MS = 640  # every intro finishes before the last frame of a 0.7 s clip
_GRAIN = (
    "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' "
    "height='240'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' "
    "numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1 0 0 0 0 1 "
    "0 0 0 0 1 0 0 0 0.55 0'/></filter><rect width='100%' height='100%' "
    "filter='url(%23n)'/></svg>\")"
)


@dataclass(frozen=True)
class Frame:
    """The canvas a slide is drawn on."""

    width: int
    height: int

    @property
    def unit(self) -> float:
        """Pixels per 1080p pixel. Portrait type is a bit larger, for phones."""
        boost = 1.15 if self.height / self.width > 1.5 else 1.0
        return min(self.width, self.height) / 1080 * boost

    @property
    def squat(self) -> bool:
        """Not wide and not tall: the square format, where height is short."""
        return not self.wide and self.height / self.width < 1.3

    @property
    def wide(self) -> bool:
        return self.width / self.height >= 1.5

    def px(self, value: float) -> str:
        return f"{value * self.unit:.1f}px"


@dataclass(frozen=True)
class Parts:
    """What a slide kind adds to the shared page."""

    head: str
    body: str
    css: str
    kind: str


def _rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgba(color: str, alpha: float) -> str:
    r, g, b = _rgb(color)
    return f"rgba({r}, {g}, {b}, {alpha:g})"


def mix(a: str, b: str, amount: float) -> str:
    """Blend colour a towards colour b by amount (0 keeps a)."""
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    parts = (round(x + (y - x) * amount) for x, y in ((ra, rb), (ga, gb), (ba, bb)))
    return "#" + "".join(f"{p:02x}" for p in parts)


def step_count(slide: SlideItem) -> int:
    """How many build states a slide has. Each one gets a clip and a still."""
    if isinstance(slide, FlowSlide):
        return len(slide.steps)
    if isinstance(slide, BulletsSlide):
        return len(slide.items)
    return 1


# Shared page ---------------------------------------------------------------


def _base_css(theme: SlideTheme, frame: Frame) -> str:
    p = frame.px
    accent = theme.accent
    deep = mix(theme.background, accent, 0.16)
    second = mix(accent, "#6366f1", 0.55)
    margin_x = max(frame.width * 0.06, 64 * frame.unit)
    top = max(frame.height * 0.085, 84 * frame.unit)
    bottom = max(frame.height * 0.13, 120 * frame.unit)
    footer_y = max(frame.height * 0.05, 48 * frame.unit)
    text = theme.text
    return f"""
{theme.font_face_css}
:root {{
  --accent: {accent};
  --text: {text};
  --muted: {rgba(text, 0.6)};
  --faint: {rgba(text, 0.42)};
  --card: {rgba(text, 0.035)};
  --line: {rgba(text, 0.08)};
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{
  width: 100%; height: 100%; overflow: hidden;
  background: {theme.background}; color: var(--text);
  font-family: {theme.font_family};
  -webkit-font-smoothing: antialiased;
  text-rendering: geometricPrecision;
  font-feature-settings: "ss01", "cv11";
}}
.{ACCENT_CLASS} {{ color: var(--accent); }}
.bg {{
  position: absolute; inset: 0; overflow: hidden;
  background: linear-gradient(155deg, {theme.background} 0%, {theme.background} 38%, {deep} 100%);
}}
.glow {{ position: absolute; border-radius: 50%; }}
.g1 {{
  width: {p(1500)}; height: {p(1500)}; left: {p(-460)}; top: {p(-800)};
  background: radial-gradient(closest-side, {rgba(accent, 0.26)}, {rgba(accent, 0.09)} 55%,
    {rgba(accent, 0)});
}}
.g2 {{
  width: {p(1300)}; height: {p(1300)}; right: {p(-420)}; bottom: {p(-760)};
  background: radial-gradient(closest-side, {rgba(second, 0.2)}, {rgba(second, 0.06)} 55%,
    {rgba(second, 0)});
}}
.vignette {{
  position: absolute; inset: 0;
  background: radial-gradient(130% 110% at 30% 20%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.42) 100%);
}}
.grain {{
  position: absolute; inset: 0; opacity: 0.06; mix-blend-mode: overlay;
  background-image: {_GRAIN}; background-size: {p(240)} {p(240)};
}}
.chapter {{
  position: absolute; top: {p(-40)}; right: {frame.width * 0.045:.1f}px;
  font-size: {p(470 if frame.wide else 380)}; font-weight: 800; line-height: 1;
  letter-spacing: -0.05em; color: {rgba(text, 0.06)};
  font-variant-numeric: tabular-nums;
}}
.stage {{
  position: absolute; left: {margin_x:.1f}px; right: {margin_x:.1f}px;
  top: {top:.1f}px; bottom: {bottom:.1f}px;
  display: flex; flex-direction: column;
}}
.eyebrow {{
  display: flex; align-items: center; gap: {p(14)};
  font-size: {p(20)}; font-weight: 650; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--accent);
  margin-bottom: {p(22)};
  font-variant-numeric: tabular-nums;
}}
.eyebrow::before {{
  content: ""; width: {p(30)}; height: {p(2)}; border-radius: {p(2)};
  background: var(--accent);
}}
.swap {{ display: inline-grid; }}
.swap > span {{ grid-area: 1 / 1; }}
.title {{
  font-size: {p(72 if frame.wide else 66)}; font-weight: 750; line-height: 1.06;
  letter-spacing: -0.025em; max-width: {"78%" if frame.wide else "100%"};
  text-wrap: balance;
}}
.subtitle {{
  position: relative; margin-top: {p(26)}; padding-left: {p(22)};
  font-size: {p(27)}; line-height: 1.45; color: var(--muted);
  max-width: {"62%" if frame.wide else "100%"};
  text-wrap: pretty;
}}
.subtitle::before {{
  content: ""; position: absolute; left: 0; top: 0.18em; bottom: 0.18em;
  width: {max(3 * frame.unit, 2):.1f}px; border-radius: {p(3)};
  background: var(--accent); transform-origin: top;
}}
.body {{
  flex: 1; min-height: 0; display: flex; flex-direction: column;
  justify-content: safe center; margin-top: {p(40 if frame.squat else 48)};
}}
.footer {{
  position: absolute; left: {margin_x:.1f}px; right: {margin_x:.1f}px;
  bottom: {footer_y:.1f}px; display: flex; align-items: center; gap: {p(12)};
  font-size: {p(17)}; color: var(--faint); letter-spacing: 0.02em;
  white-space: nowrap; overflow: hidden;
}}
.footer .brand {{ color: {rgba(text, 0.78)}; font-weight: 650; }}
.footer .tag {{ overflow: hidden; text-overflow: ellipsis; }}
.footer img {{ height: {p(24)}; width: auto; object-fit: contain; }}
.card {{
  position: relative; border-radius: {p(14)};
  background: var(--card); border: 1px solid var(--line);
  box-shadow: 0 {p(24)} {p(48)} {p(-24)} rgba(0,0,0,0.65),
    inset 0 1px 0 {rgba(text, 0.04)};
}}
.card::before {{
  content: ""; position: absolute; inset: -1px; border-radius: inherit;
  border: 1px solid {rgba(accent, 0.6)};
  background: linear-gradient(180deg, {rgba(accent, 0.2)}, {rgba(accent, 0.06)});
  box-shadow: 0 0 0 1px {rgba(accent, 0.12)}, 0 {p(30)} {p(70)} {p(-30)} {rgba(accent, 0.6)};
  opacity: 0; pointer-events: none;
}}
.card > * {{ position: relative; }}
.card.is-active::before {{ opacity: 1; }}
.card.is-future.dim {{ opacity: {DIM_OPACITY}; }}
.card.is-future.reveal, .is-future.reveal {{ visibility: hidden; }}
.num {{
  display: inline-grid; place-items: center; flex: 0 0 auto;
  width: {p(46)}; height: {p(46)}; border-radius: {p(12)};
  font-size: {p(18)}; font-weight: 700; letter-spacing: 0.04em;
  font-variant-numeric: tabular-nums;
  color: var(--accent); background-color: {rgba(accent, 0.12)};
  border: 1px solid {rgba(accent, 0.3)};
}}
.card.is-active .num {{
  color: {theme.background}; background-color: var(--accent); border-color: var(--accent);
}}
"""


def _motion_css(theme: SlideTheme, frame: Frame) -> str:
    """Keyframes and the step 0 entrance for the shared page parts."""
    p = frame.px
    accent = theme.accent
    return f"""
@keyframes rs-fade {{ from {{ opacity: 0; }} }}
@keyframes rs-unfade {{ from {{ opacity: 1; }} to {{ opacity: 0; }} }}
@keyframes rs-rise {{ from {{ opacity: 0; transform: translateY({p(30)}); }} }}
@keyframes rs-slide {{ from {{ opacity: 0; transform: translateX({p(-60)}); }} }}
@keyframes rs-nudge {{ from {{ opacity: 0; transform: translateX({p(-24)}); }} }}
@keyframes rs-grow-y {{ from {{ transform: scaleY(0); }} }}
@keyframes rs-grow-x {{ from {{ transform: scaleX(0); }} }}
@keyframes rs-draw {{ from {{ stroke-dashoffset: 1; }} to {{ stroke-dashoffset: 0; }} }}
@keyframes rs-wipe {{ from {{ clip-path: inset(0 100% 0 0); }} }}
@keyframes rs-pop {{ from {{ opacity: 0; transform: translate(-50%, 50%) scale(0.3); }} }}
@keyframes rs-chapter {{ from {{ opacity: 0; transform: translateX({p(50)}); }} }}
@keyframes rs-drift-a {{ from {{ opacity: 0.2; transform: translate({p(-90)}, {p(-50)})
  scale(0.86); }} }}
@keyframes rs-drift-b {{ from {{ opacity: 0.2; transform: translate({p(90)}, {p(70)})
  scale(0.9); }} }}
@keyframes rs-lift {{ from {{ opacity: {DIM_OPACITY}; transform: translateY({p(10)}); }} }}
@keyframes rs-out-up {{ to {{ opacity: 0; transform: translateY(-0.5em); }} }}
@keyframes rs-in-up {{ from {{ opacity: 0; transform: translateY(0.5em); }} }}
@keyframes rs-num-on {{ from {{ color: var(--accent); background-color: {rgba(accent, 0.12)};
  border-color: {rgba(accent, 0.3)}; }} 45% {{ color: {theme.text}; }} }}
@keyframes rs-num-off {{ from {{ color: {theme.background}; background-color: {accent};
  border-color: {accent}; }} 55% {{ color: {theme.text}; }} }}
.intro .g1 {{ animation: rs-drift-a 660ms {EASE_OUT} both; }}
.intro .g2 {{ animation: rs-drift-b 660ms {EASE_OUT} both; }}
.intro .chapter {{ animation: rs-chapter 600ms {EASE_OUT} 40ms both; }}
.intro .eyebrow {{ animation: rs-rise 380ms {EASE_OUT} 60ms both; }}
.intro .eyebrow::before {{ transform-origin: left;
  animation: rs-grow-x 380ms {EASE_OUT} 100ms both; }}
.intro .title {{ animation: rs-slide 480ms {EASE_OUT} 90ms both; }}
.intro .subtitle {{ animation: rs-nudge 420ms {EASE_OUT} 190ms both; }}
.intro .subtitle::before {{ animation: rs-grow-y 380ms {EASE_OUT} 220ms both; }}
.intro .footer {{ animation: rs-fade 400ms ease-out 220ms both; }}
.swap .old {{ animation: rs-out-up 260ms {EASE_IN_OUT} both; }}
.swap .new.changed {{ animation: rs-in-up 300ms {EASE_OUT} 120ms both; }}
"""


def _chapter(slide: SlideItem) -> str:
    if slide.chapter is None:
        return ""
    return f'<div class="chapter" aria-hidden="true">{slide.chapter:02d}</div>'


def _footer(theme: SlideTheme) -> str:
    bits: list[str] = []
    if theme.logo_uri:
        bits.append(f'<img src="{html.escape(theme.logo_uri, quote=True)}" alt="">')
    if theme.brand_name:
        bits.append(f'<span class="brand">{html.escape(theme.brand_name)}</span>')
    if theme.brand_name and theme.footer_title:
        bits.append("<span>·</span>")
    if theme.footer_title:
        bits.append(f'<span class="tag">{markup_html(theme.footer_title)}</span>')
    if not bits:
        return ""
    return f'<footer class="footer">{"".join(bits)}</footer>'


def _head(eyebrow: str, title: str | None, subtitle: str | None, title_class: str) -> str:
    parts = []
    if eyebrow:
        parts.append(f'<div class="eyebrow"><span>{eyebrow}</span></div>')
    if title:
        parts.append(f'<h1 class="{title_class}">{markup_html(title)}</h1>')
    if subtitle:
        parts.append(f'<p class="subtitle">{markup_html(subtitle)}</p>')
    return "".join(parts)


def _eyebrow(slide: SlideItem) -> str:
    return markup_html(slide.eyebrow) if slide.eyebrow else ""


def _step_eyebrow(active: int, total: int) -> str:
    """'Step 2 of 4', with the number rolling over from the step before."""
    if active == 0:
        return f'Step <span class="swap"><span class="new">1</span></span> of {total}'
    return (
        f'Step <span class="swap"><span class="old">{active}</span>'
        f'<span class="new changed">{active + 1}</span></span> of {total}'
    )


def _intro_delay(index: int, count: int, start: int, duration: int) -> int:
    """Stagger items so the last one still ends by INTRO_END_MS."""
    if count <= 1:
        return start
    room = max(0, INTRO_END_MS - start - duration)
    gap = min(70, room // (count - 1))
    return start + index * gap


# Card states ---------------------------------------------------------------


def _state(index: int, active: int) -> str:
    if index < active:
        return "is-done"
    if index == active:
        return "is-active"
    return "is-future"


def _card_motion(index: int, active: int, intro: bool, style: str) -> tuple[str, str]:
    """Inline animation styles for a card cell and the card itself."""
    if intro:
        return "", ""
    if index == active - 1:
        return "", "from-active"
    if index != active:
        return "", ""
    if style == "reveal":
        return "arrive", "to-active"
    return "", "to-active lift"


def _cards_css(frame: Frame, count: int, intro: bool) -> str:
    p = frame.px
    css = [
        f".card.to-active::before {{ animation: rs-fade 380ms {EASE_OUT} 170ms both; }}",
        f".card.to-active .num {{ animation: rs-num-on 380ms {EASE_OUT} 170ms both; }}",
        f".card.from-active::before {{ animation: rs-unfade 360ms {EASE_IN_OUT} both; }}",
        f".card.from-active .num {{ animation: rs-num-off 360ms {EASE_IN_OUT} both; }}",
        f".card.lift {{ animation: rs-lift 420ms {EASE_OUT} 150ms both; }}",
        f".cell.arrive {{ animation: rs-rise 420ms {EASE_OUT} 130ms both; }}",
        f".link.draw-in .draw {{ animation: rs-draw 340ms {EASE_IN_OUT} both; }}",
        f".exits.arrive {{ animation: rs-rise 320ms {EASE_OUT} 300ms both; }}",
    ]
    if intro:
        for index in range(count):
            delay = _intro_delay(index, count, 190, 360)
            css.append(
                f'.intro [data-i="{index}"] {{ animation: rs-rise 360ms {EASE_OUT} '
                f"{delay}ms both; }}"
            )
        css.append(".intro .exits { animation: rs-fade 300ms ease-out 320ms both; }")
    css.append(f".exits .chip::before {{ width: {p(7)}; height: {p(7)}; }}")
    return "\n".join(css)


def _exits(slide: FlowSlide, active: int, total: int, step_class: str, intro: bool) -> str:
    if not slide.exits:
        return ""
    last = active == total - 1
    classes = ["exits"]
    if not last:
        classes += ["is-future", step_class]
    elif not intro:
        classes.append("arrive")
    chips = "".join(f'<span class="chip">{markup_html(label)}</span>' for label in slide.exits)
    return f'<div class="{" ".join(classes)}">{chips}</div>'


# Flow ----------------------------------------------------------------------


def _link(index: int, active: int, wide: bool, style: str) -> str:
    """The arrow from card index to card index + 1."""
    drawn = index + 1 <= active
    classes = ["link"]
    if index + 1 == active:
        classes.append("draw-in")
    if not drawn:
        classes += ["is-future", style]
    offset = "0" if drawn else "1"
    path = "M4 12 H58 M50 4 L58 12 L50 20"
    svg = (
        f'<svg viewBox="0 0 64 24" preserveAspectRatio="xMidYMid meet" aria-hidden="true">'
        f'<path class="track" d="{path}" />'
        f'<path class="draw" d="{path}" pathLength="1" stroke-dasharray="1 1" '
        f'stroke-dashoffset="{offset}" style="stroke-dashoffset: {offset}" />'
        "</svg>"
    )
    direction = "" if wide else " down"
    return f'<div class="{" ".join(classes)}{direction}" data-i="{index + 1}">{svg}</div>'


def _flow_parts(slide: FlowSlide, theme: SlideTheme, frame: Frame, active: int) -> Parts:
    items = slide.step_items()
    total = len(items)
    intro = active == 0
    wide = frame.wide
    style = slide.step_style
    cells: list[str] = []
    for index, item in enumerate(items):
        cell_motion, card_motion = _card_motion(index, active, intro, style)
        state = _state(index, active)
        card_classes = " ".join(c for c in ("card", state, style, card_motion) if c)
        cell_classes = " ".join(c for c in ("cell", cell_motion) if c)
        if state == "is-future" and style == "reveal":
            cell_classes += " is-future reveal"
        detail = f'<div class="cdetail">{markup_html(item.detail)}</div>' if item.detail else ""
        cells.append(
            f'<div class="{cell_classes}" data-i="{index}">'
            f'<div class="{card_classes}"><div class="num">{index + 1:02d}</div>'
            f'<div class="ctext"><div class="ctitle">{markup_html(item.title)}</div>'
            f"{detail}</div></div></div>"
        )
        if index < total - 1:
            cells.append(_link(index, active, wide, style))
    eyebrow = _eyebrow(slide) or _step_eyebrow(active, total)
    head = _head(eyebrow, slide.title, slide.subtitle, "title")
    exits = _exits(slide, active, total, style, intro)
    layout = "wide" if wide else "tall"
    body = f'<div class="flow {layout}">{"".join(cells)}</div>{exits}'
    css = _flow_css(theme, frame, total, any(i.detail for i in items))
    return Parts(head, body, css + _cards_css(frame, total, intro), "flow")


def _flow_css(theme: SlideTheme, frame: Frame, total: int, details: bool) -> str:
    p = frame.px
    scale = 1.0 if total <= 4 else max(0.72, 4 / total)
    if not frame.wide:
        scale = 1.0 if total <= 4 else max(0.7, 4.5 / total)
        if frame.squat:
            scale *= 0.8
    title_px = (32 if frame.wide else 30) * scale
    detail_px = (22 if frame.wide else 21) * scale
    link_w = 64 * scale
    common = f"""
.flow {{ display: flex; width: 100%; }}
.cell {{ display: flex; min-width: 0; }}
.cell > .card {{ flex: 1; display: flex; }}
.ctitle {{ font-size: {p(title_px)}; font-weight: 650; line-height: 1.2;
  letter-spacing: -0.01em; }}
.cdetail {{ margin-top: {p(10)}; font-size: {p(detail_px)}; line-height: 1.45;
  color: var(--muted); }}
.link {{ display: flex; align-items: center; justify-content: center; flex: 0 0 auto; }}
.link svg {{ overflow: visible; }}
.link path {{ fill: none; stroke-width: 2.8; stroke-linecap: round; stroke-linejoin: round; }}
.link .track {{ stroke: {rgba(theme.text, 0.22)}; }}
.link.is-future.reveal .track {{ stroke: none; }}
.link .draw {{ stroke: var(--accent); }}
.exits {{ display: flex; flex-wrap: wrap; gap: {p(14)}; margin-top: {p(34)}; }}
.exits.is-future.dim {{ opacity: {DIM_OPACITY}; }}
.chip {{ display: inline-flex; align-items: center; gap: {p(10)};
  padding: {p(10)} {p(20)}; border-radius: 999px; font-size: {p(19)};
  color: var(--muted); background: {rgba(theme.text, 0.03)};
  border: 1px solid {rgba(theme.text, 0.14)}; }}
.chip::before {{ content: ""; border-radius: 50%; border: 1.5px solid var(--faint); }}
"""
    if frame.wide:
        return (
            common
            + f"""
.flow.wide {{ align-items: stretch; }}
.flow.wide .cell {{ flex: 1 1 0; }}
.flow.wide .card {{ flex-direction: column; gap: {p(22)};
  padding: {p(30 * scale + 4)} {p(28 * scale + 2)} {p(32 * scale + 4)}; }}
.flow.wide .link {{ width: {p(link_w)}; }}
.flow.wide .link svg {{ width: {p(link_w * 0.78)}; height: {p(24)}; }}
"""
        )
    return (
        common
        + f"""
.flow.tall {{ flex-direction: column; }}
.flow.tall .card {{ flex-direction: row; align-items: center; gap: {p(24)};
  padding: {p(24 * scale + 2)} {p(28)}; }}
.flow.tall .link {{ height: {p(36 * scale)}; }}
.flow.tall .link svg {{ width: {p(34 * scale)}; height: {p(16)}; transform: rotate(90deg); }}
"""
    )


# Bullets -------------------------------------------------------------------


def _bullets_parts(slide: BulletsSlide, theme: SlideTheme, frame: Frame, active: int) -> Parts:
    total = len(slide.items)
    intro = active == 0
    style = slide.step_style
    rows: list[str] = []
    for index, text in enumerate(slide.items):
        cell_motion, card_motion = _card_motion(index, active, intro, style)
        state = _state(index, active)
        card_classes = " ".join(c for c in ("card", "row", state, style, card_motion) if c)
        cell_classes = " ".join(c for c in ("cell", cell_motion) if c)
        if state == "is-future" and style == "reveal":
            cell_classes += " is-future reveal"
        rows.append(
            f'<div class="{cell_classes}" data-i="{index}"><div class="{card_classes}">'
            f'<span class="mark"></span><span class="txt">{markup_html(text)}</span>'
            "</div></div>"
        )
    head = _head(_eyebrow(slide), slide.title, slide.subtitle, "title")
    body = f'<div class="list">{"".join(rows)}</div>'
    p = frame.px
    scale = 1.0 if total <= 5 else max(0.7, 5 / total)
    if frame.squat:
        scale *= 0.9
    accent = theme.accent
    css = f"""
.list {{ display: flex; flex-direction: column; gap: {p(16 * scale)};
  width: {"min(100%, " + p(1240) + ")" if frame.wide else "100%"}; }}
.row {{ display: flex; align-items: center; gap: {p(24)};
  padding: {p(24 * scale + 2)} {p(30)}; font-size: {p(30 * scale)}; line-height: 1.35;
  font-weight: 500; letter-spacing: -0.005em; }}
.mark {{ flex: 0 0 auto; width: {p(12)}; height: {p(12)}; border-radius: 50%;
  border: {p(2)} solid {rgba(accent, 0.7)}; }}
.row.is-active .mark {{ background: var(--accent); border-color: var(--accent);
  box-shadow: 0 0 0 {p(6)} {rgba(accent, 0.18)}; }}
.row.is-done .mark {{ background: {rgba(accent, 0.7)}; border-color: transparent; }}
"""
    return Parts(head, body, css + _cards_css(frame, total, intro), "bullets")


# Title ---------------------------------------------------------------------


def _title_parts(slide: TitleSlide, frame: Frame) -> Parts:
    head = _head(_eyebrow(slide), slide.title, slide.subtitle, "title hero")
    p = frame.px
    css = f"""
.kind-title .stage {{ justify-content: center; padding-bottom: {p(30)}; }}
.kind-title .body {{ display: none; }}
.title.hero {{ font-size: {p(124 if frame.wide else 104)}; letter-spacing: -0.035em;
  line-height: 1.0; max-width: {"84%" if frame.wide else "100%"}; }}
.kind-title .subtitle {{ margin-top: {p(36)}; font-size: {p(34)};
  max-width: {"62%" if frame.wide else "100%"}; }}
.kind-title .eyebrow {{ margin-bottom: {p(30)}; font-size: {p(22)}; }}
"""
    return Parts(head, "", css, "title")


# Chart ---------------------------------------------------------------------


def format_value(value: float) -> str:
    rounded = round(value, 4)
    if abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))
    return f"{rounded:.4f}".rstrip("0").rstrip(".")


def _chart_parts(slide: ChartSlide, theme: SlideTheme, frame: Frame) -> Parts:
    count = len(slide.values)
    top = max(max(slide.values), 0.0) or 1.0
    heights = [max(0.0, v) / top * 86 for v in slide.values]
    peak = slide.values.index(max(slide.values))
    slot = 100 / count
    grid = "".join(f'<div class="gridline" style="bottom: {h}%"></div>' for h in (25, 50, 75))
    labels = "".join(
        f'<div class="clabel" style="left: {slot * i:.3f}%; width: {slot:.3f}%">'
        f"{markup_html(label)}</div>"
        for i, label in enumerate(slide.labels)
    )
    if slide.chart_type == "bars":
        marks = _bar_marks(slide, heights, peak, slot)
    else:
        marks = _line_marks(slide, heights, slot)
    head = _head(_eyebrow(slide), slide.title, slide.subtitle, "title")
    body = (
        f'<div class="chart {slide.chart_type}"><div class="plot">{grid}'
        f'<div class="baseline"></div>{marks}</div><div class="labels">{labels}</div></div>'
    )
    return Parts(head, body, _chart_css(theme, frame, count), "chart")


def _bar_marks(slide: ChartSlide, heights: list[float], peak: int, slot: float) -> str:
    cols = []
    for index, (value, height) in enumerate(zip(slide.values, heights, strict=True)):
        peak_class = " is-peak" if index == peak else ""
        cols.append(
            f'<div class="bcol" data-i="{index}" style="left: {slot * index:.3f}%; '
            f'width: {slot:.3f}%"><div class="val">{format_value(value)}</div>'
            f'<div class="bar{peak_class}" style="height: {height:.3f}%"></div></div>'
        )
    return "".join(cols)


def _line_marks(slide: ChartSlide, heights: list[float], slot: float) -> str:
    points = [(slot * (i + 0.5) * 10, 1000 - h * 10) for i, h in enumerate(heights)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    area = f"{points[0][0]:.1f},1000 {line} {points[-1][0]:.1f},1000"
    svg = (
        '<svg class="lines-svg" viewBox="0 0 1000 1000" preserveAspectRatio="none">'
        '<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="var(--accent)" stop-opacity="0.28"/>'
        '<stop offset="1" stop-color="var(--accent)" stop-opacity="0"/></linearGradient></defs>'
        f'<polygon points="{area}" fill="url(#area)"/>'
        f'<polyline points="{line}" fill="none" stroke="var(--accent)" '
        'stroke-width="4" vector-effect="non-scaling-stroke" stroke-linejoin="round" '
        'stroke-linecap="round"/></svg>'
    )
    dots = []
    for index, (value, height) in enumerate(zip(slide.values, heights, strict=True)):
        x = slot * (index + 0.5)
        dots.append(
            f'<div class="dot" data-i="{index}" style="left: {x:.3f}%; bottom: {height:.3f}%">'
            f'<div class="val">{format_value(value)}</div></div>'
        )
    return svg + "".join(dots)


def _chart_css(theme: SlideTheme, frame: Frame, count: int) -> str:
    p = frame.px
    accent = theme.accent
    text = theme.text
    css = [
        f"""
.kind-chart .body {{ justify-content: stretch; }}
.chart {{ flex: 1; display: flex; flex-direction: column; min-height: 0; }}
.plot {{ position: relative; flex: 1; min-height: 0; margin-top: {p(40)}; }}
.gridline {{ position: absolute; left: 0; right: 0; height: 0;
  border-top: 1px dashed {rgba(text, 0.08)}; }}
.baseline {{ position: absolute; left: 0; right: 0; bottom: 0; height: 0;
  border-top: 1px solid {rgba(text, 0.22)}; }}
.labels {{ position: relative; height: {p(54)}; }}
.clabel {{ position: absolute; top: {p(16)}; text-align: center;
  font-size: {p(22)}; color: var(--muted); white-space: nowrap; }}
.bcol {{ position: absolute; top: 0; bottom: 0; display: flex; flex-direction: column;
  justify-content: flex-end; align-items: center; }}
.val {{ font-size: {p(30)}; font-weight: 700; letter-spacing: -0.01em;
  font-variant-numeric: tabular-nums; margin-bottom: {p(14)}; }}
.bar {{ width: min(56%, {p(170)}); border-radius: {p(10)} {p(10)} {p(3)} {p(3)};
  background: linear-gradient(180deg, {rgba(accent, 0.8)}, {rgba(accent, 0.22)});
  border: 1px solid {rgba(accent, 0.35)}; border-bottom: 0;
  transform-origin: bottom; }}
.bar.is-peak {{ background: linear-gradient(180deg, {accent}, {rgba(accent, 0.4)});
  box-shadow: 0 0 {p(60)} {p(-6)} {rgba(accent, 0.45)}; }}
.lines-svg {{ position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }}
.dot {{ position: absolute; width: {p(18)}; height: {p(18)}; border-radius: 50%;
  transform: translate(-50%, 50%); background: {theme.background};
  border: {p(4)} solid var(--accent); box-shadow: 0 0 {p(24)} {rgba(accent, 0.5)}; }}
.dot .val {{ position: absolute; bottom: {p(22)}; left: 50%;
  transform: translateX(-50%); margin: 0; }}
.intro .lines-svg {{ animation: rs-wipe 520ms {EASE_IN_OUT} 140ms both; }}
"""
    ]
    for index in range(count):
        delay = _intro_delay(index, count, 150, 380)
        css.append(
            f'.intro .bcol[data-i="{index}"] .bar {{ animation: rs-grow-y 380ms {EASE_OUT} '
            f"{delay}ms both; }}\n"
            f'.intro .bcol[data-i="{index}"] .val {{ animation: rs-rise 300ms {EASE_OUT} '
            f"{min(delay + 160, INTRO_END_MS - 300)}ms both; }}\n"
            f'.intro .dot[data-i="{index}"] {{ animation: rs-pop 300ms {EASE_OUT} '
            f"{min(140 + index * 520 // max(count, 1), INTRO_END_MS - 300)}ms both; }}"
        )
    return "\n".join(css)


# Page ----------------------------------------------------------------------


def _parts(slide: SlideItem, theme: SlideTheme, frame: Frame, active: int) -> Parts:
    if isinstance(slide, TitleSlide):
        return _title_parts(slide, frame)
    if isinstance(slide, FlowSlide):
        return _flow_parts(slide, theme, frame, active)
    if isinstance(slide, BulletsSlide):
        return _bullets_parts(slide, theme, frame, active)
    return _chart_parts(slide, theme, frame)


def studio_values(
    slide: SlideItem, theme: SlideTheme, *, active: int, width: int, height: int
) -> dict[str, str]:
    """Template values for one build state of a slide, with that state's intro."""
    frame = Frame(width, height)
    parts = _parts(slide, theme, frame, active)
    body_class = f"kind-{parts.kind}" + (" intro" if active == 0 else "")
    return {
        "styles": _base_css(theme, frame) + parts.css + _motion_css(theme, frame),
        "body_class": body_class,
        "chapter": _chapter(slide),
        "head": parts.head,
        "body": parts.body,
        "footer": _footer(theme),
    }
