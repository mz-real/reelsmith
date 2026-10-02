"""Tests for the *accent* markup in slide text."""

from __future__ import annotations

from reelsmith.slides.markup import Run, markup_html, parse_markup, plain_text


def test_stars_mark_accent_words() -> None:
    assert parse_markup("Make *demo videos* locally") == [
        Run("Make ", False),
        Run("demo videos", True),
        Run(" locally", False),
    ]


def test_escaped_star_stays_plain() -> None:
    assert parse_markup(r"5 \* 3 is *15*") == [Run("5 * 3 is ", False), Run("15", True)]
    assert plain_text(r"a \*b\* c") == "a *b* c"


def test_unpaired_star_is_kept() -> None:
    assert parse_markup("a *b* c *d") == [Run("a ", False), Run("b", True), Run(" c *d", False)]
    assert plain_text("one * two") == "one * two"


def test_html_is_escaped_inside_and_outside_accents() -> None:
    out = markup_html("Save & *<share>*")
    assert out == 'Save &amp; <span class="hl">&lt;share&gt;</span>'


def test_text_without_markup_is_one_plain_run() -> None:
    assert parse_markup("plain") == [Run("plain", False)]
    assert parse_markup("") == []
