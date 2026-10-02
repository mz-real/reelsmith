"""Inline slide markup: ``*words*`` is drawn in the accent colour.

A star with a backslash before it (``\\*``) is a plain star. A star with no
partner is kept as a plain star too, so a stray one never hides text.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

ACCENT_CLASS = "hl"


@dataclass(frozen=True)
class Run:
    """A piece of text and whether it is in the accent colour."""

    text: str
    accent: bool


def _tokens(text: str) -> list[str | None]:
    """Split text into characters and markers. None marks an unescaped star."""
    out: list[str | None] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and text[index + 1 : index + 2] == "*":
            out.append("*")
            index += 2
            continue
        out.append(None if char == "*" else char)
        index += 1
    return out


def parse_markup(text: str) -> list[Run]:
    """Turn marked up text into plain and accent runs."""
    tokens = _tokens(text)
    stars = [i for i, token in enumerate(tokens) if token is None]
    if len(stars) % 2 == 1:
        tokens[stars[-1]] = "*"  # an unpaired star stays a star
    runs: list[Run] = []
    accent = False
    buffer: list[str] = []
    for token in tokens:
        if token is None:
            if buffer:
                runs.append(Run("".join(buffer), accent))
                buffer = []
            accent = not accent
            continue
        buffer.append(token)
    if buffer:
        runs.append(Run("".join(buffer), accent))
    return runs


def markup_html(text: str) -> str:
    """Escaped HTML for marked up text, with accent runs in a span."""
    parts = []
    for run in parse_markup(text):
        escaped = html.escape(run.text)
        if run.accent:
            escaped = f'<span class="{ACCENT_CLASS}">{escaped}</span>'
        parts.append(escaped)
    return "".join(parts)


def plain_text(text: str) -> str:
    """The text without any markup, for places that cannot show colour."""
    return "".join(run.text for run in parse_markup(text))
