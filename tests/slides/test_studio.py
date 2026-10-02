"""Tests for the Studio theme: defaults, page parts and flow cards."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from reelsmith.models import BrandModel, SpecModel
from reelsmith.models.slides import FlowSlide, FlowStep, SlidesModel, TitleSlide
from reelsmith.slides.render import render_slide_html, step_cue_count
from reelsmith.slides.themes import SlideTheme, resolve_theme

STARTER = Path(__file__).resolve().parents[2] / "src/reelsmith/templates/starter/spec.yaml"


def _studio(tmp_path: Path, brand: dict[str, object] | None = None, goal: str = "") -> SlideTheme:
    spec = SpecModel.model_validate({"version": 1, "goal": goal})
    return resolve_theme(spec, BrandModel.model_validate(brand or {}), tmp_path)


def test_studio_is_the_default_theme() -> None:
    assert SpecModel.model_validate({"version": 1}).theme == "studio"
    assert yaml.safe_load(STARTER.read_text(encoding="utf-8"))["theme"] == "studio"


def test_studio_theme_defaults(tmp_path: Path) -> None:
    theme = _studio(tmp_path, {"name": "Recipe Box"}, goal="Save a recipe")
    assert theme.style == "studio"
    assert theme.accent == "#2dd4bf"
    assert theme.brand_name == "Recipe Box"
    assert theme.footer_title == "Save a recipe"


def test_brand_colours_drive_the_studio_accent(tmp_path: Path) -> None:
    assert _studio(tmp_path, {"colors": {"primary": "#ff5500"}}).accent == "#ff5500"
    both = {"colors": {"primary": "#ff5500", "accent": "#00ff00"}}
    assert _studio(tmp_path, both).accent == "#00ff00"


def test_tagline_fills_the_footer_without_a_goal(tmp_path: Path) -> None:
    theme = _studio(tmp_path, {"name": "Acme", "tagline": "Ship *faster*"})
    html = render_slide_html(
        TitleSlide(id="t", kind="title", title="Hi"),
        theme,
        build_index=None,
        width=1920,
        height=1080,
    )
    assert '<span class="brand">Acme</span>' in html
    assert '<span class="hl">faster</span>' in html


def test_old_themes_keep_the_classic_look(tmp_path: Path) -> None:
    for name in ("dark", "light", "minimal"):
        spec = SpecModel.model_validate({"version": 1, "theme": name})
        theme = resolve_theme(spec, BrandModel(), tmp_path)
        assert theme.style == "classic"
        html = render_slide_html(
            TitleSlide(id="t", kind="title", title="Hi *there*"),
            theme,
            build_index=None,
            width=640,
            height=360,
        )
        assert 'class="slide"' in html and '<span class="hl">there</span>' in html


def test_title_slide_has_eyebrow_chapter_and_subtitle(tmp_path: Path) -> None:
    slide = TitleSlide(
        id="t",
        kind="title",
        title="How *it* works",
        eyebrow="Chapter 2",
        subtitle="One CLI",
        chapter=2,
    )
    html = render_slide_html(
        slide,
        _studio(tmp_path),
        build_index=None,
        width=1920,
        height=1080,
    )
    assert '<div class="chapter" aria-hidden="true">02</div>' in html
    assert "Chapter 2" in html and 'class="subtitle"' in html
    assert 'How <span class="hl">it</span> works' in html
    assert 'class="kind-title intro"' in html


def _flow() -> FlowSlide:
    slides = SlidesModel.model_validate(
        {
            "slides": [
                {
                    "id": "flow",
                    "kind": "flow",
                    "title": "Two approvals",
                    "steps": [
                        {"title": "Plan", "detail": "The AI writes *spec.yaml*"},
                        "Approve",
                        {"title": "Script"},
                    ],
                    "exits": ["Change the plan"],
                }
            ]
        }
    )
    slide = slides.slides[0]
    assert isinstance(slide, FlowSlide)
    return slide


def test_flow_steps_accept_cards_and_plain_strings() -> None:
    slide = _flow()
    assert slide.step_items() == [
        FlowStep(title="Plan", detail="The AI writes *spec.yaml*"),
        FlowStep(title="Approve"),
        FlowStep(title="Script"),
    ]
    assert slide.step_style == "dim"
    assert step_cue_count(slide) == 2


def test_flow_cards_show_title_detail_and_states(tmp_path: Path) -> None:
    theme = _studio(tmp_path)
    html = render_slide_html(
        _flow(),
        theme,
        build_index=1,
        width=1920,
        height=1080,
    )
    cards = re.findall(r'<div class="(card [^"]*)">', html)
    assert [c.split()[1] for c in cards] == ["is-done", "is-active", "is-future"]
    assert "from-active" in cards[0] and "to-active" in cards[1] and "dim" in cards[2]
    assert '<div class="ctitle">Plan</div>' in html
    assert 'The AI writes <span class="hl">spec.yaml</span>' in html
    assert html.count('class="cdetail"') == 1
    assert 'class="link draw-in"' in html
    assert '<span class="old">1</span><span class="new changed">2</span></span> of 3' in html
    assert 'class="exits is-future dim"' in html


def test_reveal_hides_future_cards_and_the_last_step_shows_exits(tmp_path: Path) -> None:
    slide = _flow().model_copy(update={"step_style": "reveal"})
    theme = _studio(tmp_path)
    first = render_slide_html(
        slide,
        theme,
        build_index=0,
        width=1080,
        height=1920,
    )
    assert first.count("is-future reveal") >= 2
    assert 'class="flow tall"' in first
    last = render_slide_html(
        slide,
        theme,
        build_index=None,
        width=1920,
        height=1080,
    )
    assert "is-future" not in last.split("<body", 1)[1]
    assert 'class="exits arrive"' in last
