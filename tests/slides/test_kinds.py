"""The newer Studio slide kinds: models, steps, HTML and real renders."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from pydantic import ValidationError

from reelsmith.models import BrandModel, SpecModel
from reelsmith.models.slides import (
    ArchitectureSlide,
    CodeSlide,
    FlowSlide,
    SlideItem,
    SlidesModel,
    TimelineSlide,
    TitleSlide,
)
from reelsmith.slides.code import highlight_line
from reelsmith.slides.diagram import tick_step
from reelsmith.slides.render import element_boxes, render_slide_html, render_slides_to_dir
from reelsmith.slides.themes import SlideTheme, resolve_theme
from tests.slides.png_compare import assert_render_pair_equal

SIZES = [(1920, 1080), (1080, 1920), (1080, 1080)]


def _slide(data: dict[str, Any]) -> SlideItem:
    return SlidesModel.model_validate({"slides": [{"id": "s", **data}]}).slides[0]


def _theme(root: Path, theme: str = "studio") -> SlideTheme:
    spec = SpecModel.model_validate({"version": 1, "theme": theme})
    return resolve_theme(spec, BrandModel(), root)


def _images(root: Path) -> list[str]:
    names = []
    for name, size in (("wide.png", (320, 180)), ("tall.png", (180, 320)), ("sq.png", (200, 200))):
        Image.new("RGB", size, (30, 60, 90)).save(root / name)
        names.append(name)
    return names


CARDS = {
    "kind": "cards",
    "title": "Four *cards*",
    "eyebrow": "Open",
    "subtitle": "One per step",
    "chapter": 1,
    "cards": [
        {"icon": "lock", "title": "Local", "detail": "Nothing is uploaded", "chips": ["a"]},
        {"icon": "chat", "title": "AI driven", "accent": True},
        {"title": "Two approvals", "number": "A"},
    ],
}
ARCH = {
    "kind": "architecture",
    "title": "How it *works*",
    "nodes": [
        {"id": "you", "label": "You", "icon": "user"},
        {"id": "ai", "label": "AI tool", "detail": "Any tool"},
        {"id": "cli", "label": "CLI"},
        {"id": "engine", "label": "Engine", "chips": ["Capture", "Voice", "QA"]},
    ],
    "layout": [["you"], ["ai"], ["cli", "engine"]],
    "edges": [
        {"from": "you", "to": "ai", "label": "asks"},
        {"from": "ai", "to": "cli"},
        {"from": "cli", "to": "engine", "label": "runs"},
    ],
}
CODE = {
    "kind": "code",
    "title": "Result",
    "file": "terminal",
    "code": "$ reelsmith slides\n[OK] Rendered 2 slide(s)\nNext: reelsmith compose\n",
    "highlight": [[1, [2]], [3, [3]]],
}
TIMELINE = {
    "kind": "timeline",
    "title": "Timing",
    "duration": 10,
    "markers": [{"id": "e1", "t": 2, "label": "Search"}, {"t": 6, "label": "Save"}],
    "phrases": [
        {"start": 2, "end": 4.5, "label": "Tap search,", "pin": "e1"},
        {"start": 6, "end": 8, "label": "and save.", "pin": "Save"},
    ],
    "holds": [{"at": 5, "seconds": 1}],
    "conflicts": [{"at": 9, "label": "0.5 s over"}],
}
COMPARE = {
    "kind": "compare",
    "title": "Before and *now*",
    "rows": [{"before": "Late", "now": "On time"}, {"before": "Cut", "now": "Kept"}],
}
STATS = {
    "kind": "stats",
    "title": "Checks",
    "hero": {"value": 9, "label": "checks"},
    "metrics": [
        {"label": "Pace", "value": "130 to 210", "bar": [0.5, 0.8]},
        {"label": "Words", "value": "All", "bar": 1},
    ],
    "chips": ["Sync", "Blur"],
}


def _all_kinds(images: list[str]) -> list[dict[str, Any]]:
    gallery = {
        "kind": "gallery",
        "title": "Formats",
        "images": [{"image": name, "label": name} for name in images],
    }
    title = {"kind": "title", "title": "Chapter", "chapter": 2, "coming_up": ["A", "B"]}
    flow = {"kind": "flow", "steps": ["Plan", {"title": "Approve", "accent": True}, "Render"]}
    return [CARDS, ARCH, CODE, TIMELINE, COMPARE, STATS, gallery, title, flow]


# Models -------------------------------------------------------------------


def test_every_new_kind_validates_and_counts_its_steps(tmp_path: Path) -> None:
    images = _images(tmp_path)
    expected = [3, 4, 3, 4, 2, 4, 3, 1, 3]
    from reelsmith.slides.render import step_cue_count

    for data, steps in zip(_all_kinds(images), expected, strict=True):
        slide = _slide(data)
        assert step_cue_count(slide) == steps - 1, data["kind"]


def test_timeline_steps_follow_what_it_has() -> None:
    slide = _slide({**TIMELINE, "holds": [], "conflicts": []})
    assert isinstance(slide, TimelineSlide)
    assert slide.stages() == ["track", "phrases"]
    assert slide.track_seconds() == 10
    no_duration = _slide({k: v for k, v in TIMELINE.items() if k != "duration"})
    assert isinstance(no_duration, TimelineSlide)
    assert no_duration.track_seconds() == 10.0  # content ends at 9 s, rounded up


def test_code_language_comes_from_the_file_name() -> None:
    assert isinstance(slide := _slide({**CODE, "file": "spec.yaml"}), CodeSlide)
    assert slide.resolved_language() == "yaml"
    assert isinstance(slide := _slide({**CODE, "file": "clip.json"}), CodeSlide)
    assert slide.resolved_language() == "json"
    assert isinstance(slide := _slide(CODE), CodeSlide)
    assert slide.resolved_language() == "shell"


def test_architecture_builds_nodes_in_layout_order() -> None:
    slide = _slide(ARCH)
    assert isinstance(slide, ArchitectureSlide)
    assert slide.ordered_ids() == ["you", "ai", "cli", "engine"]
    assert slide.edges[0].source == "you"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({**CARDS, "cards": CARDS["cards"][:1]}, "at least 2"),
        ({**CARDS, "cards": [{"title": "x", "icon": "nope"}] * 2}, "Unknown icon 'nope'"),
        ({**ARCH, "layout": [["you"], ["ai"], ["cli"]]}, "Node 'engine' is not placed"),
        ({**ARCH, "layout": [["you", "ghost"], ["ai"], ["cli", "engine"]]}, "'ghost'"),
        ({**ARCH, "edges": [{"from": "you", "to": "nobody"}]}, "Edge names node 'nobody'"),
        ({**CODE, "highlight": [[1, [9]]]}, "outside the code"),
        ({**CODE, "highlight": [[0, [1]]]}, "must be from 1"),
        ({**TIMELINE, "phrases": [{"start": 1, "end": 2, "label": "x", "pin": "e9"}]}, "e9"),
        ({**TIMELINE, "phrases": [{"start": 3, "end": 2, "label": "x"}]}, "end after"),
        ({**TIMELINE, "duration": 5}, "past its duration"),
        ({"kind": "timeline"}, "at least one"),
        ({**STATS, "metrics": [{"label": "P", "value": "v", "bar": [0.8, 0.2]}]}, "larger"),
        ({**STATS, "metrics": [{"label": "P", "value": "v", "bar": 1.5}]}, "less than"),
        ({"kind": "gallery", "images": [{"image": "a.png", "label": "a"}]}, "at least 2"),
        ({"kind": "compare", "rows": []}, "at least 1"),
    ],
)
def test_bad_slides_are_rejected_with_a_clear_message(data: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=re.escape(message)):
        _slide(data)


# HTML ---------------------------------------------------------------------


def test_every_kind_renders_the_same_html_twice_in_every_format(tmp_path: Path) -> None:
    images = _images(tmp_path)
    theme = _theme(tmp_path)
    for data in _all_kinds(images):
        slide = _slide({**data, "eyebrow": "Eye *brow*", "subtitle": "Sub", "chapter": 3})
        for width, height in SIZES:
            first = render_slide_html(slide, theme, build_index=0, width=width, height=height)
            again = render_slide_html(slide, theme, build_index=0, width=width, height=height)
            assert first == again
            assert 'Eye <span class="hl">brow</span>' in first
            assert '<div class="chapter" aria-hidden="true">03</div>' in first


def test_reveal_hides_future_items(tmp_path: Path) -> None:
    images = _images(tmp_path)
    theme = _theme(tmp_path)
    stepped = [data for data in _all_kinds(images)[:7] if data["kind"] != "code"]
    for data in stepped:
        slide = _slide({**data, "step_style": "reveal"})
        html = render_slide_html(slide, theme, build_index=0, width=1920, height=1080)
        assert "is-future reveal" in html, data["kind"]


def test_new_kinds_use_the_studio_look_with_a_classic_theme(tmp_path: Path) -> None:
    html = render_slide_html(
        _slide(CARDS), _theme(tmp_path, "dark"), build_index=None, width=640, height=360
    )
    assert 'class="kind-cards"' in html


def test_accent_cards_and_flow_steps_stay_lit(tmp_path: Path) -> None:
    theme = _theme(tmp_path)
    html = render_slide_html(_slide(CARDS), theme, build_index=2, width=1920, height=1080)
    cards = re.findall(r'<div class="(card tile [^"]*)">', html)
    assert "is-accent" in cards[1] and "from-active" not in cards[1]
    flow = _slide({"kind": "flow", "steps": ["Plan", {"title": "OK", "accent": True}, "Go"]})
    assert isinstance(flow, FlowSlide)
    html = render_slide_html(flow, theme, build_index=2, width=1920, height=1080)
    states = re.findall(r'<div class="(card is-[^"]*)">', html)
    assert "is-done" in states[1] and "is-accent" in states[1]
    assert "from-active" not in states[1]


def test_title_shows_coming_up_chips(tmp_path: Path) -> None:
    slide = TitleSlide(id="t", kind="title", title="Hi", chapter=1, coming_up=["One *two*"])
    html = render_slide_html(slide, _theme(tmp_path), build_index=None, width=1920, height=1080)
    assert "Coming up" in html
    assert '<span class="upn">01</span><span>One <span class="hl">two</span></span>' in html


def test_cards_number_themselves_unless_given(tmp_path: Path) -> None:
    html = render_slide_html(
        _slide(CARDS), _theme(tmp_path), build_index=None, width=1920, height=1080
    )
    assert re.findall(r'<div class="tnum">([^<]*)</div>', html) == ["01", "02", "A"]


def test_code_highlight_brightens_its_lines_and_dims_the_rest(tmp_path: Path) -> None:
    theme = _theme(tmp_path)
    slide = _slide(CODE)
    first = render_slide_html(slide, theme, build_index=0, width=1920, height=1080)
    assert re.findall(r'class="ln (\w+)', first) == ["dim", "hl", "dim"]
    second = render_slide_html(slide, theme, build_index=1, width=1920, height=1080)
    assert re.findall(r'class="ln (\w+)', second) == ["plain", "plain", "plain"]
    third = render_slide_html(slide, theme, build_index=2, width=1920, height=1080)
    assert re.findall(r'class="(ln [^"]+)"', third) == [
        "ln dim from-plain",
        "ln dim from-plain",
        "ln hl from-plain",
    ]


def test_highlighting_marks_keys_strings_comments_and_results() -> None:
    yaml_line = highlight_line('  say: "spec dot yaml"  # spoken', "yaml")
    assert '<span class="t-key">say</span>' in yaml_line
    assert '<span class="t-str">&quot;spec dot yaml&quot;</span>' in yaml_line
    assert '<span class="t-com"># spoken</span>' in yaml_line
    json_line = highlight_line('{"t": 1.84, "type": "click"}', "json")
    assert '<span class="t-key">&quot;t&quot;</span>' in json_line
    assert '<span class="t-num">1.84</span>' in json_line
    assert '<span class="t-str">&quot;click&quot;</span>' in json_line
    assert '<span class="t-badge t-warn">WARN</span>' in highlight_line("[WARN] Late", "shell")
    assert '<span class="t-badge t-error">ERROR</span>' in highlight_line("[ERROR] x", "shell")
    assert '<span class="t-next">Next:</span>' in highlight_line("Next: reelsmith qa", "shell")
    assert '<span class="t-prompt">$ </span>' in highlight_line("$ reelsmith qa", "shell")


def test_stats_hero_counts_up_only_in_its_entrance(tmp_path: Path) -> None:
    theme = _theme(tmp_path)
    slide = _slide({**STATS, "hero": {"value": 1.4, "label": "s late", "suffix": "s"}})
    intro = render_slide_html(slide, theme, build_index=0, width=1920, height=1080)
    assert ".intro .count { animation: rs-count" in intro and "--n: 14;" in intro
    later = render_slide_html(slide, theme, build_index=1, width=1920, height=1080)
    assert 'class="kind-stats"' in later and 'class="kind-stats intro"' not in later


def test_tick_steps_stay_readable() -> None:
    assert tick_step(12, 12) == 1.0
    assert tick_step(12, 6) == 2.0
    assert tick_step(300, 12) == 30.0


# Real renders -------------------------------------------------------------


def test_timeline_phrases_sit_at_their_seconds(tmp_path: Path) -> None:
    slide = _slide(TIMELINE)
    assert isinstance(slide, TimelineSlide)
    html = render_slide_html(slide, _theme(tmp_path), build_index=None, width=960, height=540)
    plot = element_boxes(html, 960, 540, ".plot")[0]
    bars = element_boxes(html, 960, 540, ".ph")
    markers = element_boxes(html, 960, 540, ".mk")
    assert len(bars) == 2
    for phrase, box in zip(slide.phrases, bars, strict=True):
        assert box["x"] == pytest.approx(plot["x"] + phrase.start / 10 * plot["width"], abs=1)
        width = (phrase.end - phrase.start) / 10 * plot["width"]
        assert box["width"] == pytest.approx(width, abs=1)
    for marker, box in zip(slide.markers, markers, strict=True):
        assert box["x"] == pytest.approx(plot["x"] + marker.t / 10 * plot["width"], abs=1)


def test_architecture_arrows_are_laid_out_between_their_boxes(tmp_path: Path) -> None:
    html = render_slide_html(
        _slide(ARCH), _theme(tmp_path), build_index=None, width=960, height=540
    )
    paths = element_boxes(html, 960, 540, ".edge .draw")
    nodes = element_boxes(html, 960, 540, ".node")
    assert len(paths) == 3 and all(max(box["width"], box["height"]) > 3 for box in paths)
    you, ai = nodes[0], nodes[1]
    first = paths[0]
    assert first["x"] >= you["x"] + you["width"] - 1
    assert first["x"] + first["width"] <= ai["x"] + 1


def test_every_kind_renders_stills_in_every_format(tmp_path: Path) -> None:
    images = _images(tmp_path)
    slides = SlidesModel.model_validate(
        {"slides": [{"id": f"k{n}", **data} for n, data in enumerate(_all_kinds(images))]}
    )
    theme = _theme(tmp_path)
    for width, height in ((480, 270), (270, 480), (300, 300)):
        out = tmp_path / f"out{width}x{height}"
        written = render_slides_to_dir(slides, theme, out, width=width, height=height, clips=False)
        finals = [name for name in written if re.fullmatch(r"k\d\.png", name)]
        assert len(finals) == len(slides.slides)
        for name in finals:
            with Image.open(out / name) as image:
                assert image.size == (width, height)
                low, high = image.convert("L").getextrema()
                assert high - low > 40, name  # not blank


def test_renders_are_deterministic(tmp_path: Path) -> None:
    slides = SlidesModel.model_validate(
        {"slides": [{"id": "t", **TIMELINE}, {"id": "a", **ARCH}, {"id": "s", **STATS}]}
    )
    theme = _theme(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    render_slides_to_dir(slides, theme, first, width=480, height=270, clips=False)
    render_slides_to_dir(slides, theme, second, width=480, height=270, clips=False)
    pairs = (
        ("t.png", False),
        ("a.png", True),
        ("s.png", False),
        ("a_step1.png", True),
    )
    for name, arch_tolerance in pairs:
        assert_render_pair_equal(
            first / name,
            second / name,
            name=name,
            arch_tolerance=arch_tolerance,
        )


def test_architecture_pixel_tolerance_catches_moved_nodes(tmp_path: Path) -> None:
    theme = _theme(tmp_path)
    baseline = SlidesModel.model_validate({"slides": [{"id": "a", **ARCH}]})
    shifted_layout = [["you", "ai"], ["cli"], ["engine"]]
    shifted = SlidesModel.model_validate(
        {"slides": [{"id": "a", **ARCH, "layout": shifted_layout}]}
    )
    base_dir = tmp_path / "base"
    shift_dir = tmp_path / "shift"
    render_slides_to_dir(baseline, theme, base_dir, width=480, height=270, clips=False)
    render_slides_to_dir(shifted, theme, shift_dir, width=480, height=270, clips=False)
    with pytest.raises(AssertionError, match="outside architecture pixel tolerance"):
        assert_render_pair_equal(
            base_dir / "a.png",
            shift_dir / "a.png",
            name="a.png",
            arch_tolerance=True,
        )


def test_gallery_names_a_missing_image(tmp_path: Path) -> None:
    from reelsmith.errors import ReelsmithError

    slide = _slide({"kind": "gallery", "images": [{"image": "gone.png", "label": "a"}] * 2})
    with pytest.raises(ReelsmithError, match="gone.png"):
        render_slide_html(slide, _theme(tmp_path), build_index=0, width=640, height=360)


# Review fixes -------------------------------------------------------------


def test_chapter_numeral_is_outlined_without_a_glyph_stroke(tmp_path: Path) -> None:
    """A text stroke draws every inner contour of a glyph, a stray line in a 2."""
    slide = TitleSlide(id="t", kind="title", title="Hi", chapter=2)
    for width, height in SIZES:
        html = render_slide_html(
            slide, _theme(tmp_path), build_index=None, width=width, height=height
        )
        assert "text-stroke" not in html
        assert 'filter id="rs-outline"' in html and "url(#rs-outline)" in html


def test_code_cards_are_large_and_wrap_long_lines(tmp_path: Path) -> None:
    long_line = "x" * 160
    slide = _slide({**CODE, "code": f"$ reelsmith qa\n{long_line}\n", "highlight": []})
    html = render_slide_html(slide, _theme(tmp_path), build_index=None, width=1920, height=1080)
    stage = element_boxes(html, 1920, 1080, ".body")[0]
    card = element_boxes(html, 1920, 1080, ".code")[0]
    assert card["width"] >= stage["width"] * 0.69
    assert card["x"] + card["width"] <= stage["x"] + stage["width"] + 1
    lines = element_boxes(html, 1920, 1080, ".ln")
    assert lines[1]["height"] > lines[0]["height"] * 1.8  # wrapped, not shrunk
    body_css = html.split(".cbody", 1)[1].split("}", 1)[0]
    size = re.search(r"font-size: ([\d.]+)px", body_css)
    assert size is not None and float(size.group(1)) >= 28


def _overflow(html: str, width: int, height: int, selector: str) -> list[float]:
    from reelsmith.slides.animate import slide_page

    with slide_page(width, height) as page:
        page.load(html)
        page.finish()
        return list(
            page.locator(selector).evaluate_all(
                "els => els.map(e => e.scrollHeight - e.clientHeight)"
            )
        )


def test_portrait_timeline_labels_are_not_clipped(tmp_path: Path) -> None:
    slide = _slide(
        {
            **TIMELINE,
            "duration": 12,
            "phrases": [
                {"start": 2, "end": 3.6, "label": "Tap the search box,", "pin": "e1"},
                {"start": 6, "end": 7.2, "label": "and save it to favourites.", "pin": "Save"},
            ],
        }
    )
    html = render_slide_html(slide, _theme(tmp_path), build_index=None, width=1080, height=1920)
    assert all(gap <= 1 for gap in _overflow(html, 1080, 1920, ".ph span"))


def test_portrait_gallery_uses_the_height(tmp_path: Path) -> None:
    images = _images(tmp_path)
    slide = _slide(
        {"kind": "gallery", "images": [{"image": name, "label": name} for name in images]}
    )
    html = render_slide_html(slide, _theme(tmp_path), build_index=None, width=1080, height=1920)
    screens = element_boxes(html, 1080, 1920, ".screen")
    assert len({round(box["y"]) for box in screens}) >= 2  # more than one row
    assert screens[0]["height"] >= 1920 * 0.2
