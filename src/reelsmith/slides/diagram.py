"""Studio diagrams: architecture boxes with drawn arrows, and a timing track."""

from __future__ import annotations

import html

from reelsmith.models.slides import ArchitectureSlide, TimelinePhrase, TimelineSlide
from reelsmith.slides.grid import BAD, _chip_css, _chips, _icon, _light_css
from reelsmith.slides.markup import markup_html, plain_text
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

# Architecture --------------------------------------------------------------

# Edges are laid out in the page, from where the boxes really are. Offsets
# (not bounding boxes) are used, so a box that is still moving in does not
# bend its arrow. It runs again once fonts are ready, before any capture.
_WIRES_JS = """
(() => {
  window.__reelsmithReady = false;
  const root = document.querySelector('.arch');
  if (!root) {
    document.fonts.ready.then(() => { window.__reelsmithReady = true; });
    return;
  }
  const pos = (el) => {
    let x = 0, y = 0, node = el;
    while (node && node !== root) { x += node.offsetLeft; y += node.offsetTop;
      node = node.offsetParent; }
    return { x, y, w: el.offsetWidth, h: el.offsetHeight };
  };
  const layout = () => {
    const svg = root.querySelector('svg.wires');
    svg.setAttribute('width', root.offsetWidth);
    svg.setAttribute('height', root.offsetHeight);
    const gap = parseFloat(root.dataset.gap), head = parseFloat(root.dataset.head);
    const across = root.dataset.dir === 'h';
    for (const edge of root.querySelectorAll('.edge')) {
      const a = root.querySelector(`.cell[data-node="${edge.dataset.from}"] > .node`);
      const b = root.querySelector(`.cell[data-node="${edge.dataset.to}"] > .node`);
      if (!a || !b) continue;
      const ca = a.closest('.cell').dataset.c, cb = b.closest('.cell').dataset.c;
      const p = pos(a), q = pos(b);
      const flat = across ? ca !== cb : ca === cb;
      let sx, sy, ex, ey, c1x, c1y, c2x, c2y, dx = 0, dy = 0;
      if (flat) {
        const fwd = q.x >= p.x;
        sx = fwd ? p.x + p.w + gap : p.x - gap; sy = p.y + p.h / 2;
        ex = fwd ? q.x - gap : q.x + q.w + gap; ey = q.y + q.h / 2;
        const m = (ex - sx) / 2; c1x = sx + m; c1y = sy; c2x = ex - m; c2y = ey;
        dx = fwd ? 1 : -1;
      } else {
        const down = q.y >= p.y;
        sx = p.x + p.w / 2; sy = down ? p.y + p.h + gap : p.y - gap;
        ex = q.x + q.w / 2; ey = down ? q.y - gap : q.y + q.h + gap;
        const m = (ey - sy) / 2; c1x = sx; c1y = sy + m; c2x = ex; c2y = ey - m;
        dy = down ? 1 : -1;
      }
      const d = `M${sx} ${sy} C${c1x} ${c1y} ${c2x} ${c2y} ${ex} ${ey}`;
      for (const path of edge.querySelectorAll('.track, .draw')) path.setAttribute('d', d);
      const h = head, w = head * 0.7;
      const tip = dx
        ? `M${ex - dx * h} ${ey - w} L${ex} ${ey} L${ex - dx * h} ${ey + w}`
        : `M${ex - w} ${ey - dy * h} L${ex} ${ey} L${ex + w} ${ey - dy * h}`;
      edge.querySelector('.tip').setAttribute('d', tip);
      const label = root.querySelector(`.elabel[data-e="${edge.dataset.e}"]`);
      if (label) {
        const mx = (sx + 3 * c1x + 3 * c2x + ex) / 8, my = (sy + 3 * c1y + 3 * c2y + ey) / 8;
        label.style.left = `${mx}px`; label.style.top = `${my}px`;
        label.classList.add(flat === across ? 'over' : 'beside');
      }
    }
  };
  document.fonts.ready.then(() => {
    layout();
    window.__reelsmithReady = true;
  });
})();
"""


def _edge_step(slide: ArchitectureSlide, source: str, target: str) -> int:
    order = slide.ordered_ids()
    return max(order.index(source), order.index(target))


def _edge_state(step: int, active: int, style: str) -> str:
    if step < active:
        return "edge is-done"
    if step == active and active > 0:
        return "edge draw-in"
    return f"edge is-future {style}"


def architecture_parts(
    slide: ArchitectureSlide, theme: SlideTheme, frame: Frame, active: int
) -> Parts:
    nodes = {node.id: node for node in slide.nodes}
    order = slide.ordered_ids()
    style = slide.step_style
    columns = []
    for column_index, column in enumerate(slide.layout):
        cells = []
        for node_id in column:
            node = nodes[node_id]
            index = order.index(node_id)
            cell, classes = item_classes(index, active, style, base="card node")
            icon = f'<div class="ico">{_icon(node.icon, frame, 28)}</div>' if node.icon else ""
            detail = f'<div class="ndetail">{markup_html(node.detail)}</div>' if node.detail else ""
            chips = f'<div class="nchips">{_chips(node.chips)}</div>' if node.chips else ""
            cells.append(
                f'<div class="{cell}" data-i="{index}" data-c="{column_index}" '
                f'data-node="{html.escape(node_id, quote=True)}"><div class="{classes}">'
                f'<div class="nhead">{icon}<div class="nlabel">{markup_html(node.label)}</div>'
                f"</div>{detail}{chips}</div></div>"
            )
        columns.append(f'<div class="acol">{"".join(cells)}</div>')
    edges = []
    labels = []
    for number, edge in enumerate(slide.edges):
        state = _edge_state(_edge_step(slide, edge.source, edge.to), active, style)
        offset = "0" if "is-done" in state else "1"
        edges.append(
            f'<g class="{state}" data-e="{number}" '
            f'data-from="{html.escape(edge.source, quote=True)}" '
            f'data-to="{html.escape(edge.to, quote=True)}">'
            f'<path class="track" d="M0 0"/><path class="draw" d="M0 0" pathLength="1" '
            f'stroke-dasharray="1 1" style="stroke-dashoffset: {offset}"/>'
            f'<path class="tip" d="M0 0"/></g>'
        )
        if edge.label:
            labels.append(
                f'<div class="elabel {state.replace("edge ", "")}" data-e="{number}">'
                f"<span>{markup_html(edge.label)}</span></div>"
            )
    across = frame.wide
    p_gap = 10 * frame.unit
    head_px = 9 * frame.unit
    body = (
        f'<div class="arch {"across" if across else "down"}" data-dir="{"h" if across else "v"}" '
        f'data-gap="{p_gap:.1f}" data-head="{head_px:.1f}">'
        f'<svg class="wires" aria-hidden="true">{"".join(edges)}</svg>'
        f"{''.join(columns)}{''.join(labels)}</div><script>{_WIRES_JS}</script>"
    )
    head = _head(_eyebrow(slide), slide.title, slide.subtitle, "title")
    css = _arch_css(theme, frame, slide, across)
    return Parts(head, body, css + cards_css(frame, len(order), active == 0), "architecture")


def _arch_css(theme: SlideTheme, frame: Frame, slide: ArchitectureSlide, across: bool) -> str:
    p = frame.px
    accent = theme.accent
    text = theme.text
    columns = len(slide.layout)
    tallest = max(len(column) for column in slide.layout)
    scale = 1.08 if columns <= 4 else 0.94
    if across and columns >= 6:
        scale = 0.86
    if not across:
        scale = 0.84 if frame.squat else 0.96
        if frame.squat and columns >= 4:
            scale = 0.74
    gap_main = (104 if across else (54 if frame.squat else 84)) * (scale if not across else 1)
    gap_cross = 22 * scale
    css = f"""
.kind-architecture .body {{ justify-content: center; }}
.arch {{ position: relative; display: flex; width: 100%; }}
.arch.across {{ flex-direction: row; align-items: stretch; gap: {p(gap_main)}; }}
.arch.down {{ flex-direction: column; gap: {p(gap_main)}; }}
.acol {{ flex: 1 1 0; min-width: 0; display: flex; justify-content: center; gap: {p(gap_cross)}; }}
.arch.across .acol {{ flex-direction: column; }}
.arch.down .acol {{ flex-direction: row; align-items: center; }}
.arch .cell {{ display: flex; min-width: 0; position: relative; z-index: 1; }}
.arch.down .cell {{ flex: 1 1 0; max-width: {p(620 * scale)}; }}
.arch .cell > .node {{ flex: 1; }}
.node {{ padding: {p(22 * scale + 2)} {p(24 * scale + 2)}; }}
.nhead {{ display: flex; align-items: center; gap: {p(16 * scale)}; }}
.node .ico {{ flex: 0 0 auto; display: grid; place-items: center;
  width: {p(54 * scale)}; height: {p(54 * scale)}; border-radius: {p(14 * scale)};
  color: var(--accent); background: {rgba(accent, 0.1)}; border: 1px solid {rgba(accent, 0.28)}; }}
.node .ico svg {{ width: {p(28 * scale)}; height: {p(28 * scale)}; }}
.nlabel {{ font-size: {p(29 * scale)}; font-weight: 680; line-height: 1.15;
  letter-spacing: -0.015em; }}
.ndetail {{ margin-top: {p(12 * scale)}; font-size: {p(20 * scale)}; line-height: 1.4;
  color: var(--muted); text-wrap: pretty; }}
.nchips {{ display: flex; flex-wrap: wrap; gap: {p(8 * scale)}; margin-top: {p(16 * scale)}; }}
svg.wires {{ position: absolute; left: 0; top: 0; overflow: visible; z-index: 0; }}
.edge path {{ fill: none; stroke-linecap: round; stroke-linejoin: round; }}
.edge .track {{ stroke: {rgba(text, 0.16)}; stroke-width: {max(2.2 * frame.unit, 1.2):.2f}; }}
.edge .draw {{ stroke: {rgba(accent, 0.9)}; stroke-width: {max(2.6 * frame.unit, 1.4):.2f};
  filter: drop-shadow(0 0 {p(6)} {rgba(accent, 0.55)}); }}
.edge .tip {{ stroke: {accent}; stroke-width: {max(2.6 * frame.unit, 1.4):.2f}; }}
.edge.is-future .tip {{ stroke: {rgba(text, 0.22)}; }}
.edge.is-future.reveal {{ visibility: hidden; }}
.edge.draw-in .draw {{ animation: rs-draw 420ms {EASE_IN_OUT} 40ms both; }}
.edge.draw-in .tip {{ animation: rs-fade 160ms ease-out 400ms both; }}
.elabel {{ position: absolute; z-index: 2; left: 0; top: 0; white-space: nowrap;
  font-size: {p(16 * max(scale, 0.9))}; font-weight: 650; letter-spacing: 0.1em;
  text-transform: uppercase; color: {rgba(accent, 0.95)}; }}
.elabel span {{ display: inline-block; padding: {p(5)} {p(12)}; border-radius: 999px;
  background: {theme.background}; border: 1px solid {rgba(accent, 0.3)}; }}
.elabel.over {{ transform: translate(-50%, calc(-100% - {p(10)})); }}
.elabel.beside {{ transform: translate({p(14)}, -50%); }}
.elabel.is-future.dim {{ opacity: {DIM_OPACITY}; }}
.elabel.is-future.reveal {{ visibility: hidden; }}
.elabel.draw-in span {{ animation: rs-fade 300ms ease-out 300ms both; }}
.intro .edge, .intro .elabel {{ animation: rs-fade 360ms ease-out 200ms both; }}
"""
    if tallest >= 3 and across:
        css += f".arch.across .node {{ padding: {p(18 * scale)} {p(22 * scale)}; }}\n"
    return css + _chip_css(theme, frame, 16 * max(scale, 0.88)) + _light_css(theme, ".node")


# Timeline ------------------------------------------------------------------

_TICK_STEPS = (0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0, 120.0)


def tick_step(seconds: float, most: int) -> float:
    """The smallest round step that gives at most ``most`` gaps along the track."""
    return next((step for step in _TICK_STEPS if seconds / step <= most), _TICK_STEPS[-1])


def _pct(value: float, total: float) -> str:
    return f"{value / total * 100:.4f}%"


def _stage_class(stage: str, stages: list[str], active: int, style: str) -> str:
    index = stages.index(stage)
    if index < active:
        return "is-done"
    if index == active:
        return "is-active enter" if active > 0 else "is-active"
    return f"is-future {style}"


LABEL_PX = (22, 20)  # phrase label size in 1080p pixels: wide, then other shapes
NAME_W = 150  # the lane names column, wide frames only


def _label_fits(phrase: TimelinePhrase, total: float, frame: Frame) -> bool:
    """Whether a phrase label fits on two lines inside its bar."""
    margin = max(frame.width * 0.06, 64 * frame.unit)
    plot = frame.width - 2 * margin - (NAME_W * frame.unit if frame.wide else 0)
    inner = (phrase.end - phrase.start) / total * plot - 30 * frame.unit
    font = (LABEL_PX[0] if frame.wide else LABEL_PX[1]) * frame.unit
    words = plain_text(phrase.label).split()
    lines, used = 1, 0.0
    for word in words:
        width = (len(word) + 1) * font * 0.56
        if width > inner:
            return False
        if used + width > inner:
            lines, used = lines + 1, 0.0
        used += width
    return lines <= 2


def timeline_parts(slide: TimelineSlide, theme: SlideTheme, frame: Frame, active: int) -> Parts:
    total = slide.track_seconds()
    stages = slide.stages()
    style = slide.step_style
    pinned = {
        id(marker)
        for phrase in slide.phrases
        if phrase.pin is not None
        for marker in [slide.marker_for(phrase.pin)]
        if marker is not None
    }
    step = tick_step(total, 12 if frame.wide else 6)
    ticks = []
    lines = []
    value = 0.0
    while value <= total + 1e-9:
        left = _pct(value, total)
        ticks.append(f'<span class="tick" style="left: {left}">{format_value(value)} s</span>')
        lines.append(f'<i class="gl" style="left: {left}"></i>')
        value += step
    lit = "phrases" in stages and 0 < stages.index("phrases") <= active
    pin_class = " pinned lit" if lit else " pinned"
    markers = "".join(
        f'<div class="mk{pin_class if id(marker) in pinned else ""}" data-m="{n}" '
        f'style="left: {_pct(marker.t, total)}"><i class="stem"></i><b class="dot"></b>'
        f'<span class="mlab">{markup_html(marker.label)}</span></div>'
        for n, marker in enumerate(slide.markers)
    )
    phrase_state = _stage_class("phrases", stages, active, style) if slide.phrases else ""
    phrases = "".join(
        f'<div class="ph {phrase_state}{" pinned" if phrase.pin else ""}'
        f'{"" if _label_fits(phrase, total, frame) else " below"}" data-p="{n}" '
        f'style="left: {_pct(phrase.start, total)}; '
        f'width: {_pct(phrase.end - phrase.start, total)}">'
        f"<span>{markup_html(phrase.label)}</span></div>"
        for n, phrase in enumerate(slide.phrases)
    )
    hold_state = _stage_class("holds", stages, active, style) if slide.holds else ""
    holds = "".join(
        f'<div class="hold {hold_state}" data-h="{n}" style="left: {_pct(hold.at, total)}; '
        f'width: {_pct(hold.seconds, total)}">'
        f"<span>hold {format_value(hold.seconds)} s</span></div>"
        for n, hold in enumerate(slide.holds)
    )
    conflict_state = _stage_class("conflicts", stages, active, style) if slide.conflicts else ""
    conflicts = "".join(
        f'<div class="cf {conflict_state}" data-x="{n}" style="left: {_pct(c.at, total)}">'
        f'<i class="cline"></i><span class="cpill">{markup_html(c.label)}</span></div>'
        for n, c in enumerate(slide.conflicts)
    )
    names = '<div class="lname vo">Voice</div><div class="lname sc">Clicks</div>'
    body = (
        f'<div class="tl">{names}<div class="plot">'
        f'<div class="grid">{"".join(lines)}</div>'
        f'<div class="rail"></div>{holds}{markers}{phrases}{conflicts}'
        f'<div class="axis">{"".join(ticks)}</div></div></div>'
    )
    head = _head(_eyebrow(slide), slide.title, slide.subtitle, "title")
    css = _timeline_css(theme, frame, slide, active)
    return Parts(head, body, css, "timeline")


def _timeline_css(theme: SlideTheme, frame: Frame, slide: TimelineSlide, active: int) -> str:
    p = frame.px
    accent = theme.accent
    text = theme.text
    wide = frame.wide
    lane = 86 if wide else 92  # phrase bar height
    top = 64  # room for conflict labels
    voice_mid = top + lane / 2
    rail = top + lane + 120
    label_y = rail + 44
    axis = rail + 116
    height = axis + 44
    name_w = NAME_W if wide else 0
    shift = 110  # where a dimmed phrase waits before it snaps in
    css = f"""
.kind-timeline .body {{ justify-content: center; }}
.tl {{ position: relative; width: 100%; padding-left: {p(name_w)}; }}
.lname {{ position: absolute; left: 0; font-size: {p(17)}; font-weight: 700;
  letter-spacing: 0.14em; text-transform: uppercase; color: var(--faint);
  transform: translateY(-50%); }}
.lname.vo {{ top: {p(voice_mid)}; }}
.lname.sc {{ top: {p(rail)}; }}
.plot {{ position: relative; height: {p(height)}; }}
.grid .gl {{ position: absolute; top: {p(top - 8)}; height: {p(axis - top + 8)}; width: 0;
  border-left: 1px dashed {rgba(text, 0.07)}; }}
.axis {{ position: absolute; left: 0; right: 0; top: {p(axis)}; height: 0;
  border-top: 1px solid {rgba(text, 0.2)}; }}
.axis .gl {{ display: none; }}
.tick {{ position: absolute; top: {p(14)}; transform: translateX(-50%); font-size: {p(18)};
  color: var(--faint); font-variant-numeric: tabular-nums; white-space: nowrap; }}
.rail {{ position: absolute; left: 0; right: 0; top: {p(rail - 3)}; height: {p(6)};
  border-radius: 999px; background: {rgba(text, 0.1)}; }}
.mk {{ position: absolute; top: 0; width: 0; height: {p(axis)}; }}
.mk .stem {{ position: absolute; left: {p(-1)}; top: {p(top - 10)}; height: {p(rail - top + 10)};
  border-left: {p(2)} dashed {rgba(text, 0.22)}; }}
.mk .dot {{ position: absolute; left: {p(-11)}; top: {p(rail - 11)}; width: {p(22)};
  height: {p(22)}; border-radius: 50%; background: {theme.background};
  border: {p(4)} solid {rgba(text, 0.75)}; }}
.mk .mlab {{ position: absolute; top: {p(label_y)}; left: 0; transform: translateX(-50%);
  white-space: nowrap; font-size: {p(22 if wide else 20)}; font-weight: 600;
  color: {rgba(text, 0.85)}; }}
.ph {{ position: absolute; top: {p(top)}; height: {p(lane)}; display: flex; align-items: center;
  padding: 0 {p(14)} 0 {p(16)}; border-radius: {p(10)}; overflow: hidden;
  background: linear-gradient(180deg, {rgba(accent, 0.3)}, {rgba(accent, 0.16)});
  border: 1px solid {rgba(accent, 0.55)};
  box-shadow: 0 {p(16)} {p(32)} {p(-16)} {rgba(accent, 0.6)}; }}
.ph span {{ font-size: {p(LABEL_PX[0] if wide else LABEL_PX[1])}; font-weight: 600;
  line-height: 1.2; color: {text}; overflow: hidden; overflow-wrap: anywhere;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }}
.ph.below {{ overflow: visible; }}
.ph.below span {{ position: absolute; left: 0; top: calc(100% + {p(12)}); display: block;
  width: max(100%, {p(120)}); padding-right: {p(10)}; font-size: {p(18)};
  color: {rgba(text, 0.9)};
  text-shadow: 0 0 {p(10)} {theme.background}, 0 0 {p(4)} {theme.background}; }}
.ph.pinned::before {{ content: ""; position: absolute; left: 0; top: 0; bottom: 0;
  width: {p(5)}; background: var(--accent); }}
.hold {{ position: absolute; top: {p(rail - 30)}; height: {p(60)}; border-radius: {p(8)};
  background: repeating-linear-gradient(135deg, {rgba(accent, 0.5)} 0 {p(5)},
    {rgba(accent, 0.1)} {p(5)} {p(13)}); border: 1px solid {rgba(accent, 0.65)};
  transform-origin: left; }}
.hold span {{ position: absolute; left: 50%; bottom: calc(100% + {p(10)});
  transform: translateX(-50%); white-space: nowrap; font-size: {p(18)}; font-weight: 700;
  letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); }}
.cf {{ position: absolute; top: 0; width: 0; height: {p(rail + 30)}; }}
.cf .cline {{ position: absolute; left: {p(-1.5)}; top: {p(top - 18)}; bottom: 0;
  border-left: {p(3)} solid {BAD}; box-shadow: 0 0 {p(14)} {rgba(BAD, 0.7)};
  transform-origin: top; }}
.cf .cpill {{ position: absolute; top: 0; left: 0; transform: translate(-50%, -30%);
  white-space: nowrap; padding: {p(7)} {p(16)}; border-radius: 999px; font-size: {p(19)};
  font-weight: 700; color: #fff; background: {BAD}; box-shadow: 0 0 {p(24)} {rgba(BAD, 0.5)}; }}
.mk.pinned.lit .stem {{ border-left-color: {rgba(accent, 0.8)}; }}
.mk.pinned.lit .dot {{ border-color: var(--accent); box-shadow: 0 0 {p(16)} {rgba(accent, 0.7)}; }}
.is-future.dim {{ opacity: {DIM_OPACITY}; }}
.ph.is-future.dim {{ transform: translateX({p(shift)}); }}
.is-future.reveal {{ visibility: hidden; }}
@keyframes rs-snap {{ 0% {{ opacity: 0; transform: translateX({p(shift * 2.2)}); }}
  72% {{ opacity: 1; transform: translateX({p(-7)}); }} 100% {{ transform: translateX(0); }} }}
@keyframes rs-snap-dim {{ 0% {{ opacity: {DIM_OPACITY}; transform: translateX({p(shift)}); }}
  72% {{ opacity: 1; transform: translateX({p(-7)}); }} 100% {{ transform: translateX(0); }} }}
@keyframes rs-ping {{ 0% {{ transform: scale(1); }} 40% {{ transform: scale(1.6); }}
  100% {{ transform: scale(1); }} }}
@keyframes rs-cut {{ from {{ transform: scaleY(0); }} }}
@keyframes rs-tilt-in {{ from {{ opacity: 0; transform: translate(-50%, -30%) scale(0.5); }} }}
.hold.enter.reveal {{ animation: rs-grow-x 460ms {EASE_OUT} 60ms both; }}
.hold.enter.dim {{ animation: rs-lift 420ms {EASE_OUT} 60ms both; }}
.hold.enter span {{ animation: rs-fade 300ms ease-out 300ms both; }}
.cf.enter.dim {{ animation: rs-fade-up 300ms ease-out both; }}
@keyframes rs-fade-up {{ from {{ opacity: {DIM_OPACITY}; }} }}
.cf.enter .cline {{ animation: rs-cut 380ms {EASE_OUT} 40ms both; }}
.cf.enter .cpill {{ animation: rs-tilt-in 340ms {EASE_OUT} 260ms both; }}
.intro .rail, .intro .axis, .intro .grid {{ animation: rs-fade 420ms ease-out 120ms both; }}
.intro .lname {{ animation: rs-fade 360ms ease-out 160ms both; }}
"""
    rules = [css]
    count = len(slide.markers)
    for n in range(count):
        delay = _intro_delay(n, count, 200, 300)
        rules.append(
            f'.intro .mk[data-m="{n}"] {{ animation: rs-rise 300ms {EASE_OUT} {delay}ms both; }}'
        )
    stages = slide.stages()
    phrases_now = "phrases" in stages and stages.index("phrases") == active and active > 0
    for n, phrase in enumerate(slide.phrases):
        delay = _intro_delay(n, len(slide.phrases), 40, 420)
        name = "rs-snap" if slide.step_style == "reveal" else "rs-snap-dim"
        rules.append(
            f'.ph.enter[data-p="{n}"] {{ animation: {name} 420ms {EASE_OUT} {delay}ms both; }}'
        )
        marker = slide.marker_for(phrase.pin) if phrase.pin else None
        if marker is not None and phrases_now:
            m = slide.markers.index(marker)
            ping = min(delay + 300, 640 - 300)
            rules.append(
                f'.mk[data-m="{m}"] .dot {{ animation: rs-ping 300ms {EASE_OUT} {ping}ms both,'
                f" rs-lit 200ms ease-out {ping}ms both; }}\n"
                f'.mk[data-m="{m}"] .stem {{ animation: rs-lit-stem 200ms ease-out '
                f"{ping}ms both; }}"
            )
    rules.append(
        f"@keyframes rs-lit {{ from {{ border-color: {rgba(text, 0.75)}; box-shadow: none; }} }}\n"
        f"@keyframes rs-lit-stem {{ from {{ border-left-color: {rgba(text, 0.22)}; }} }}"
    )
    return "\n".join(rules)
