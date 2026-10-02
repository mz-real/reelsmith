"""The Studio code card: a terminal or file with simple highlighting per line."""

from __future__ import annotations

import html
import re

from reelsmith.models.slides import CodeSlide
from reelsmith.slides.grid import BAD, _icon
from reelsmith.slides.studio import (
    EASE_IN_OUT,
    EASE_OUT,
    Frame,
    Parts,
    _eyebrow,
    _head,
    _intro_delay,
    mix,
    rgba,
)
from reelsmith.slides.themes import SlideTheme

WARN = "#fbbf24"
MONO = "'SF Mono', 'JetBrains Mono', 'Cascadia Code', Menlo, Consolas, monospace"
CODE_FONT = 28.0  # 1080p pixels, about 2.6% of the frame height
DIM_LINE = 0.4

_YAML_KEY = re.compile(r"^(\s*)(- )?([^\s#'\"][^:#]*?)(:)(?=\s|$)")
_JSON_TOKEN = re.compile(
    r'(?P<str>"(?:[^"\\]|\\.)*")(?P<colon>\s*:)?|(?P<num>-?\d+(?:\.\d+)?)|'
    r"(?P<kw>\btrue\b|\bfalse\b|\bnull\b)"
)
_RESULT = re.compile(r"^(\s*)\[(OK|WARN|ERROR)\](.*)$")
_PROMPT = re.compile(r"^(\s*)([$>] )(.*)$")
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def _span(cls: str, text: str) -> str:
    return f'<span class="{cls}">{html.escape(text)}</span>' if text else ""


def _split_comment(line: str) -> tuple[str, str]:
    """Code and a trailing # comment, ignoring a # inside quotes."""
    quote = ""
    for index, char in enumerate(line):
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index], line[index:]
    return line, ""


def _yaml_value(text: str) -> str:
    stripped = text.strip()
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()) :]
    if not stripped:
        return html.escape(text)
    if stripped[0] in "'\"" and stripped[-1] == stripped[0] and len(stripped) > 1:
        cls = "t-str"
    elif _NUMBER.match(stripped):
        cls = "t-num"
    elif stripped in ("true", "false", "null", "~"):
        cls = "t-kw"
    else:
        cls = "t-val"
    return html.escape(lead) + _span(cls, stripped) + html.escape(trail)


def highlight_yaml(line: str) -> str:
    code, comment = _split_comment(line)
    match = _YAML_KEY.match(code)
    out = ""
    if match:
        indent, dash, key, colon = match.groups()
        out = html.escape(indent) + _span("t-pun", dash or "") + _span("t-key", key)
        out += _span("t-pun", colon) + _yaml_value(code[match.end() :])
    else:
        stripped = code.lstrip()
        indent = code[: len(code) - len(stripped)]
        if stripped.startswith("- "):
            out = html.escape(indent) + _span("t-pun", "- ") + _yaml_value(stripped[2:])
        else:
            out = html.escape(indent) + _yaml_value(stripped) if stripped else html.escape(code)
    return out + _span("t-com", comment)


def highlight_json(line: str) -> str:
    out: list[str] = []
    last = 0
    for match in _JSON_TOKEN.finditer(line):
        out.append(_span("t-pun", line[last : match.start()]))
        if match.group("str") is not None:
            if match.group("colon"):
                out.append(_span("t-key", match.group("str")))
                out.append(_span("t-pun", match.group("colon")))
            else:
                out.append(_span("t-str", match.group("str")))
        elif match.group("num") is not None:
            out.append(_span("t-num", match.group("num")))
        else:
            out.append(_span("t-kw", match.group("kw")))
        last = match.end()
    out.append(_span("t-pun", line[last:]))
    return "".join(out)


def highlight_shell(line: str) -> str:
    result = _RESULT.match(line)
    if result:
        indent, status, rest = result.groups()
        badge = f'<span class="t-badge t-{status.lower()}">{status}</span>'
        return html.escape(indent) + badge + _span("t-msg", rest)
    if line.startswith("Next:"):
        return _span("t-next", "Next:") + _span("t-cmd", line[5:])
    prompt = _PROMPT.match(line)
    if prompt:
        indent, mark, command = prompt.groups()
        return html.escape(indent) + _span("t-prompt", mark) + _span("t-cmd", command)
    if line.lstrip().startswith("#"):
        return _span("t-com", line)
    if line.lstrip().startswith("- "):
        return _span("t-detail", line)
    return _span("t-out", line)


def highlight_line(line: str, language: str) -> str:
    """One line of code as HTML with token spans."""
    if language == "yaml":
        return highlight_yaml(line)
    if language == "json":
        return highlight_json(line)
    if language == "shell":
        return highlight_shell(line)
    return html.escape(line)


def _line_state(number: int, lines: set[int] | None) -> str:
    if lines is None:
        return "plain"
    return "hl" if number in lines else "dim"


def code_parts(slide: CodeSlide, theme: SlideTheme, frame: Frame, active: int) -> Parts:
    language = slide.resolved_language()
    marks = {step: set(numbers) for step, numbers in slide.highlight}
    now = marks.get(active + 1)
    before = marks.get(active) if active > 0 else None
    numbered = language != "shell"
    rows = []
    for number, line in enumerate(slide.lines(), start=1):
        state = _line_state(number, now)
        classes = ["ln", state]
        if active > 0:
            previous = _line_state(number, before)
            if previous != state:
                classes.append(f"from-{previous}")
        gutter = f'<span class="no">{number}</span>' if numbered else ""
        text = highlight_line(line, language) or "&#8203;"
        rows.append(
            f'<div class="{" ".join(classes)}" data-l="{number}">{gutter}'
            f'<span class="tx">{text}</span></div>'
        )
    icon = "terminal" if language == "shell" else "file"
    bar = (
        f'<div class="cbar"><i></i><i></i><i></i><span class="cname">{_icon(icon, frame, 18)}'
        f"<span>{html.escape(slide.file)}</span></span></div>"
    )
    head = _head(_eyebrow(slide), slide.title, slide.subtitle, "title")
    body = f'<div class="code card {language}">{bar}<div class="cbody">{"".join(rows)}</div></div>'
    return Parts(head, body, _code_css(theme, frame, slide, numbered), "code")


def _code_css(theme: SlideTheme, frame: Frame, slide: CodeSlide, numbered: bool) -> str:
    p = frame.px
    accent = theme.accent
    text = theme.text
    lines = slide.lines()
    font = CODE_FONT + 2 if len(lines) <= 8 else CODE_FONT  # long lines wrap, never shrink
    key = mix(accent, "#ffffff", 0.35)
    css = [
        f"""
.kind-code .body {{ justify-content: center; }}
.code {{ align-self: flex-start; width: fit-content; min-width: {"70%" if frame.wide else "100%"};
  max-width: 100%; overflow: hidden;
  background: {rgba(mix(theme.background, "#000000", 0.4), 0.72)};
  border-color: {rgba(text, 0.11)}; }}
.cbar {{ display: flex; align-items: center; gap: {p(9)}; height: {p(52)}; padding: 0 {p(20)};
  border-bottom: 1px solid {rgba(text, 0.07)}; background: {rgba(text, 0.03)}; }}
.cbar i {{ width: {p(12)}; height: {p(12)}; border-radius: 50%; background: {rgba(text, 0.16)}; }}
.cname {{ display: flex; align-items: center; gap: {p(10)}; margin-left: {p(16)};
  font-family: {MONO}; font-size: {p(17)}; color: var(--muted); }}
.cname svg {{ width: {p(18)}; height: {p(18)}; color: var(--accent); }}
.cbody {{ padding: {p(26)} 0 {p(30)}; font-family: {MONO}; font-size: {p(font)};
  line-height: 1.62; }}
.ln {{ position: relative; display: flex; padding: 0 {p(44)} 0 {p(36 if not numbered else 22)};
  white-space: pre-wrap; }}
.ln .tx {{ min-width: 0; overflow-wrap: anywhere; }}
.ln::before {{ content: ""; position: absolute; inset: 0; opacity: 0;
  background: linear-gradient(90deg, {rgba(accent, 0.2)}, {rgba(accent, 0.04)} 70%, transparent);
  border-left: {p(3)} solid var(--accent); }}
.ln > * {{ position: relative; }}
.ln.hl::before {{ opacity: 1; }}
.ln.dim {{ opacity: {DIM_LINE}; }}
.no {{ flex: 0 0 auto; width: {p(font * 2.3)}; padding-right: {p(font * 0.9)}; text-align: right;
  color: {rgba(text, 0.26)}; user-select: none; }}
.ln.hl .no {{ color: var(--accent); }}
.tx {{ color: {rgba(text, 0.9)}; }}
.t-key {{ color: {key}; }}
.t-str {{ color: #f4c48a; }}
.t-num {{ color: #c4b5fd; }}
.t-kw {{ color: #f9a8d4; }}
.t-val {{ color: {text}; }}
.t-pun {{ color: {rgba(text, 0.5)}; }}
.t-com {{ color: {rgba(text, 0.4)}; font-style: italic; }}
.t-prompt {{ color: var(--accent); font-weight: 700; }}
.t-cmd {{ color: {text}; font-weight: 600; }}
.t-out {{ color: {rgba(text, 0.78)}; }}
.t-detail {{ color: {rgba(text, 0.6)}; }}
.t-msg {{ color: {text}; }}
.t-next {{ color: var(--accent); font-weight: 700; }}
.t-badge {{ display: inline-block; padding: 0 {p(10)}; margin-right: {p(4)}; border-radius: {p(6)};
  font-weight: 800; letter-spacing: 0.04em; }}
.t-ok {{ color: {theme.background}; background: var(--accent); }}
.t-warn {{ color: #1c1300; background: {WARN}; }}
.t-error {{ color: #fff; background: {BAD}; }}
@keyframes rs-line-on {{ from {{ opacity: {DIM_LINE}; }} }}
@keyframes rs-line-off {{ from {{ opacity: 1; }} }}
.ln.from-dim {{ animation: rs-line-on 380ms {EASE_OUT} 60ms both; }}
.ln.dim.from-hl, .ln.dim.from-plain {{ animation: rs-line-off 380ms {EASE_IN_OUT} both; }}
.ln.hl.from-dim::before, .ln.hl.from-plain::before {{
  animation: rs-wipe-in 420ms {EASE_OUT} 120ms both; }}
.ln.from-hl::before {{ animation: rs-unfade 320ms {EASE_IN_OUT} both; }}
@keyframes rs-wipe-in {{ from {{ opacity: 0; clip-path: inset(0 100% 0 0); }}
  to {{ opacity: 1; clip-path: inset(0 0 0 0); }} }}
.intro .code {{ animation: rs-rise 420ms {EASE_OUT} 120ms both; }}
.intro .cbar {{ animation: rs-fade 300ms ease-out 160ms both; }}
.intro .ln.hl::before {{ animation: rs-wipe-in 380ms {EASE_OUT} 380ms both; }}
"""
    ]
    for number in range(1, len(lines) + 1):
        delay = _intro_delay(number - 1, len(lines), 200, 260)
        css.append(
            f'.intro .ln[data-l="{number}"] .tx, .intro .ln[data-l="{number}"] .no '
            f"{{ animation: rs-type 260ms {EASE_OUT} {delay}ms both; }}"
        )
    css.append(f"@keyframes rs-type {{ from {{ opacity: 0; transform: translateX({p(-14)}); }} }}")
    return "\n".join(css)
