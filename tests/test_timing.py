"""Tests for reelsmith.timing.

Default rules used throughout: pin_lead 0.25, pin_late 0.40, breath 0.35,
phrase_gap 0.15, max_hold 3.0, min_wait_to_speed 2.5, max_speed 4.0.
"""

from __future__ import annotations

import pytest

from reelsmith.timing import (
    Conflict,
    PhraseInput,
    SceneInput,
    SceneTimeline,
    Segment,
    TimingRules,
    caption_duration,
    plan_scene,
)

NO_HOLD_REASON = "line too long for the gap before its event"


def approx(value: float) -> object:
    return pytest.approx(value, abs=1e-6)


def phrase(index: int, duration: float, pin: float | None = None) -> PhraseInput:
    return PhraseInput(index=index, duration=duration, pin_time=pin)


def clip_scene(clip: float | None, *phrases: PhraseInput) -> SceneInput:
    return SceneInput(scene_id="demo", clip_duration=clip, phrases=list(phrases))


def starts(timeline: SceneTimeline) -> list[float]:
    return [p.out_start for p in timeline.placements]


def assert_segment(
    seg: Segment,
    kind: str,
    src: tuple[float, float],
    out: tuple[float, float],
    speed: float = 1.0,
) -> None:
    assert seg.kind == kind
    assert (seg.src_start, seg.src_end) == (approx(src[0]), approx(src[1]))
    assert (seg.out_start, seg.out_end) == (approx(out[0]), approx(out[1]))
    assert seg.speed == approx(speed)


def assert_contiguous(timeline: SceneTimeline) -> None:
    segments = timeline.segments
    assert segments, "a timeline always has at least one segment"
    assert segments[0].out_start == approx(0.0)
    for before, after in zip(segments, segments[1:], strict=False):
        assert after.out_start == approx(before.out_end)
    assert segments[-1].out_end == approx(timeline.duration)
    total = sum(s.out_end - s.out_start for s in segments)
    assert total == approx(timeline.duration)
    for seg in segments:
        assert seg.out_end > seg.out_start
        if seg.kind == "play":
            assert (seg.src_end - seg.src_start) / seg.speed == approx(seg.out_end - seg.out_start)
        else:
            assert seg.src_start == seg.src_end


# Rule 1: an unpinned phrase starts at the previous phrase end plus phrase_gap.


def test_unpinned_phrases_follow_each_other_with_the_phrase_gap() -> None:
    timeline = plan_scene(clip_scene(10.0, phrase(0, 2.0), phrase(1, 1.5)), TimingRules())

    assert starts(timeline) == [approx(0.0), approx(2.15)]
    assert timeline.placements[1].out_end == approx(3.65)
    assert timeline.duration == approx(10.0)
    assert len(timeline.segments) == 1
    assert_segment(timeline.segments[0], "play", (0.0, 10.0), (0.0, 10.0))
    assert timeline.conflicts == []


# Rule 2: a pinned phrase starts at max(event - pin_lead, previous_end + gap).


def test_pinned_phrase_starts_pin_lead_before_its_event() -> None:
    timeline = plan_scene(clip_scene(10.0, phrase(0, 1.0), phrase(1, 2.0, pin=4.0)), TimingRules())

    assert starts(timeline) == [approx(0.0), approx(3.75)]
    assert timeline.placements[1].out_end == approx(5.75)
    assert timeline.conflicts == []


def test_pinned_phrase_waits_for_previous_phrase_inside_the_late_window() -> None:
    # Previous phrase ends at 3.9, so the earliest start is 4.05. That is
    # after the event (4.0) but inside the 0.40 s late window: no hold.
    timeline = plan_scene(clip_scene(10.0, phrase(0, 3.9), phrase(1, 1.0, pin=4.0)), TimingRules())

    assert starts(timeline) == [approx(0.0), approx(4.05)]
    assert [s.kind for s in timeline.segments] == ["play"]
    assert timeline.conflicts == []


def test_first_pinned_phrase_never_starts_before_zero() -> None:
    timeline = plan_scene(clip_scene(5.0, phrase(0, 1.0, pin=0.1)), TimingRules())

    assert starts(timeline) == [approx(0.0)]


# Rule 3: a hold is inserted before the event when the phrase would be late.


def test_late_pinned_phrase_gets_a_hold_before_its_event() -> None:
    # Previous phrase ends at 5.0, earliest start 5.15. Event at 4.0 means
    # the window closes at 4.4. A 1.4 s hold moves the event to 5.4, so the
    # phrase starts at exactly 5.4 - 0.25 = 5.15.
    timeline = plan_scene(clip_scene(10.0, phrase(0, 5.0), phrase(1, 1.0, pin=4.0)), TimingRules())

    assert len(timeline.segments) == 3
    assert_segment(timeline.segments[0], "play", (0.0, 4.0), (0.0, 4.0))
    assert_segment(timeline.segments[1], "hold", (4.0, 4.0), (4.0, 5.4))
    assert_segment(timeline.segments[2], "play", (4.0, 10.0), (5.4, 11.4))
    assert starts(timeline) == [approx(0.0), approx(5.15)]
    assert timeline.duration == approx(11.4)
    assert timeline.conflicts == []


def test_hold_is_capped_at_max_hold_and_the_rest_is_a_conflict() -> None:
    # Previous phrase ends at 8.0, earliest start 8.15. Event at 2.0 would
    # need a 6.4 s hold. The hold is capped at 3.0 s, so the event lands at
    # 5.0 and the window closes at 5.4. The phrase still starts at 8.15,
    # which is 2.75 s too late.
    timeline = plan_scene(clip_scene(10.0, phrase(0, 8.0), phrase(1, 1.0, pin=2.0)), TimingRules())

    assert_segment(timeline.segments[0], "play", (0.0, 2.0), (0.0, 2.0))
    assert_segment(timeline.segments[1], "hold", (2.0, 2.0), (2.0, 5.0))
    assert_segment(timeline.segments[2], "play", (2.0, 10.0), (5.0, 13.0))
    assert starts(timeline) == [approx(0.0), approx(8.15)]
    assert len(timeline.conflicts) == 1
    conflict = timeline.conflicts[0]
    assert conflict.phrase_index == 1
    assert conflict.seconds_over == approx(2.75)
    assert NO_HOLD_REASON in conflict.reason
    assert "3 s hold" in conflict.reason


def test_hold_capped_but_still_inside_the_window_is_not_a_conflict() -> None:
    # Needs a 3.5 s hold, gets 3.0. The phrase then starts 0.25 s after the
    # event, which is inside the 0.40 s late window.
    timeline = plan_scene(clip_scene(10.0, phrase(0, 5.1), phrase(1, 1.0, pin=2.0)), TimingRules())

    assert_segment(timeline.segments[1], "hold", (2.0, 2.0), (2.0, 5.0))
    assert starts(timeline)[1] == approx(5.25)
    assert timeline.conflicts == []


# Rule 4 (review focus item 3): holds off gives a conflict, never a drift.


def test_holds_off_reports_the_line_and_seconds_over() -> None:
    rules = TimingRules(allow_holds=False)
    # Earliest start 5.15, the window for an event at 4.0 closes at 4.4.
    timeline = plan_scene(clip_scene(10.0, phrase(0, 5.0), phrase(1, 1.0, pin=4.0)), rules)

    assert timeline.conflicts == [
        Conflict(phrase_index=1, seconds_over=0.75, reason=NO_HOLD_REASON)
    ]
    # No hold was added and the late phrase never overlaps the one before.
    assert [s.kind for s in timeline.segments] == ["play"]
    assert starts(timeline) == [approx(0.0), approx(5.15)]
    assert timeline.duration == approx(10.0)


def test_holds_off_at_the_exact_window_edge_is_not_a_conflict() -> None:
    rules = TimingRules(allow_holds=False)
    # Earliest start 4.25 + 0.15 = 4.4, exactly event + pin_late.
    timeline = plan_scene(clip_scene(10.0, phrase(0, 4.25), phrase(1, 1.0, pin=4.0)), rules)

    assert timeline.conflicts == []
    assert starts(timeline)[1] == approx(4.4)


def test_holds_off_names_every_late_line_and_keeps_the_order() -> None:
    rules = TimingRules(allow_holds=False)
    scene = clip_scene(
        12.0,
        phrase(0, 3.0),
        phrase(1, 2.0, pin=2.0),  # earliest 3.15, window closes 2.4: 0.75 over
        phrase(2, 1.0, pin=6.0),  # earliest 5.30, fits at 5.75
        phrase(3, 2.0, pin=7.0),  # earliest 6.90, fits at 6.90
        phrase(4, 1.0, pin=8.0),  # earliest 9.05, window closes 8.4: 0.65 over
    )
    timeline = plan_scene(scene, rules)

    assert [(c.phrase_index, c.seconds_over) for c in timeline.conflicts] == [
        (1, approx(0.75)),
        (4, approx(0.65)),
    ]
    assert all(c.reason == NO_HOLD_REASON for c in timeline.conflicts)
    assert starts(timeline) == [
        approx(0.0),
        approx(3.15),
        approx(5.75),
        approx(6.90),
        approx(9.05),
    ]
    for before, after in zip(timeline.placements, timeline.placements[1:], strict=False):
        assert after.out_start >= before.out_end + rules.phrase_gap - 1e-9
    assert [s.kind for s in timeline.segments] == ["play"]


def test_holds_off_never_lets_narration_run_ahead_of_its_event() -> None:
    rules = TimingRules(allow_holds=False)
    scene = clip_scene(9.0, phrase(0, 0.5), phrase(1, 1.0, pin=6.0))
    timeline = plan_scene(scene, rules)

    # The phrase waits for its event instead of following straight on.
    assert starts(timeline)[1] == approx(5.75)
    assert timeline.conflicts == []


# Rule 5: speed up long quiet waits, never past an event.


def test_long_quiet_wait_before_an_event_is_sped_up() -> None:
    # Quiet from 1.0 to 4.75 (the phrase starts 0.25 before the event at
    # 5.0). That is 3.75 s, over the 2.5 s threshold, so it plays at 1.5x
    # and lasts 2.5 s.
    rules = TimingRules(speed_up_waits=True)
    # The quiet tail after the narration (5.6 to 7.0) is too short to speed.
    timeline = plan_scene(clip_scene(7.0, phrase(0, 1.0), phrase(1, 0.5, pin=5.0)), rules)

    assert len(timeline.segments) == 3
    assert_segment(timeline.segments[0], "play", (0.0, 1.0), (0.0, 1.0))
    assert_segment(timeline.segments[1], "play", (1.0, 4.75), (1.0, 3.5), speed=1.5)
    assert_segment(timeline.segments[2], "play", (4.75, 7.0), (3.5, 5.75))
    assert starts(timeline) == [approx(0.0), approx(3.5)]
    assert timeline.duration == approx(5.75)


def test_speed_up_is_capped_at_max_speed_and_stops_before_the_event() -> None:
    # Quiet from 1.0 to 14.75 is 13.75 s. 13.75 / 2.5 = 5.5x, capped at 4x.
    rules = TimingRules(speed_up_waits=True)
    timeline = plan_scene(clip_scene(16.0, phrase(0, 1.0), phrase(1, 0.5, pin=15.0)), rules)

    fast = timeline.segments[1]
    assert_segment(fast, "play", (1.0, 14.75), (1.0, 4.4375), speed=4.0)
    assert fast.src_end <= 15.0
    assert starts(timeline)[1] == approx(4.4375)
    # The event (clip 15.0) lands 0.25 s after the phrase starts.
    assert_segment(timeline.segments[2], "play", (14.75, 16.0), (4.4375, 5.6875))
    assert timeline.duration == approx(5.6875)


def test_short_quiet_wait_is_not_sped_up() -> None:
    # Quiet from 1.0 to 3.0 is 2.0 s, under the 2.5 s threshold.
    rules = TimingRules(speed_up_waits=True)
    timeline = plan_scene(clip_scene(5.0, phrase(0, 1.0), phrase(1, 1.0, pin=3.25)), rules)

    assert all(s.speed == 1.0 for s in timeline.segments)
    assert starts(timeline)[1] == approx(3.0)


def test_quiet_tail_after_the_narration_is_sped_up() -> None:
    # Narration plus breath ends at 1.35. The rest of the clip, 8.65 s, has
    # no narration, so it plays at 8.65 / 2.5 = 3.46x.
    rules = TimingRules(speed_up_waits=True)
    timeline = plan_scene(clip_scene(10.0, phrase(0, 1.0)), rules)

    assert len(timeline.segments) == 2
    assert_segment(timeline.segments[0], "play", (0.0, 1.35), (0.0, 1.35))
    assert_segment(timeline.segments[1], "play", (1.35, 10.0), (1.35, 3.85), speed=3.46)
    assert timeline.duration == approx(3.85)


def test_waits_are_not_sped_up_unless_asked() -> None:
    timeline = plan_scene(clip_scene(16.0, phrase(0, 1.0), phrase(1, 0.5, pin=15.0)), TimingRules())

    assert all(s.speed == 1.0 for s in timeline.segments)
    assert starts(timeline)[1] == approx(14.75)


# Rule 6: duration is max(video end, last phrase end + breath).


def test_narration_longer_than_the_clip_holds_the_last_frame() -> None:
    timeline = plan_scene(clip_scene(3.0, phrase(0, 4.0)), TimingRules())

    assert timeline.duration == approx(4.35)
    assert_segment(timeline.segments[0], "play", (0.0, 3.0), (0.0, 3.0))
    assert_segment(timeline.segments[1], "hold", (3.0, 3.0), (3.0, 4.35))
    assert timeline.conflicts == []


def test_last_frame_hold_over_max_hold_is_a_conflict() -> None:
    timeline = plan_scene(clip_scene(1.0, phrase(0, 5.0)), TimingRules())

    assert timeline.duration == approx(5.35)
    assert_segment(timeline.segments[1], "hold", (1.0, 1.0), (1.0, 5.35))
    assert len(timeline.conflicts) == 1
    assert timeline.conflicts[0].phrase_index == 0
    assert timeline.conflicts[0].seconds_over == approx(1.35)


def test_clip_longer_than_the_narration_sets_the_duration() -> None:
    timeline = plan_scene(clip_scene(8.0, phrase(0, 2.0)), TimingRules())

    assert timeline.duration == approx(8.0)
    assert [s.kind for s in timeline.segments] == ["play"]


# Rule 7: a slide lasts its narration plus breath, as one play segment.


def test_slide_scene_lasts_its_narration_plus_breath() -> None:
    timeline = plan_scene(clip_scene(None, phrase(0, 2.0), phrase(1, 1.0)), TimingRules())

    assert starts(timeline) == [approx(0.0), approx(2.15)]
    assert timeline.duration == approx(3.5)
    assert len(timeline.segments) == 1
    assert_segment(timeline.segments[0], "play", (0.0, 3.5), (0.0, 3.5))
    assert timeline.scene_id == "demo"


# Rule 8: segments are contiguous and add up to the duration.


@pytest.mark.parametrize(
    ("clip", "phrases", "rules"),
    [
        (10.0, [phrase(0, 2.0), phrase(1, 1.5)], TimingRules()),
        (10.0, [phrase(0, 5.0), phrase(1, 1.0, pin=4.0)], TimingRules()),
        (10.0, [phrase(0, 8.0), phrase(1, 1.0, pin=2.0)], TimingRules()),
        (
            12.0,
            [phrase(0, 4.0), phrase(1, 2.0, pin=2.0), phrase(2, 3.0, pin=5.0)],
            TimingRules(),
        ),
        (16.0, [phrase(0, 1.0), phrase(1, 0.5, pin=15.0)], TimingRules(speed_up_waits=True)),
        (
            30.0,
            [phrase(0, 6.0, pin=10.0), phrase(1, 1.0, pin=12.0), phrase(2, 9.0, pin=25.0)],
            TimingRules(speed_up_waits=True),
        ),
        (1.0, [phrase(0, 5.0)], TimingRules()),
        (None, [phrase(0, 2.0)], TimingRules()),
        (6.0, [], TimingRules()),
    ],
)
def test_segments_are_contiguous_and_sum_to_the_duration(
    clip: float | None, phrases: list[PhraseInput], rules: TimingRules
) -> None:
    timeline = plan_scene(clip_scene(clip, *phrases), rules)

    assert_contiguous(timeline)
    for placement in timeline.placements:
        assert placement.out_end <= timeline.duration + 1e-9


def test_two_holds_in_one_scene_both_land_their_events() -> None:
    scene = clip_scene(
        12.0,
        phrase(0, 4.0),
        phrase(1, 4.0, pin=2.0),
        phrase(2, 3.0, pin=5.0),
    )
    timeline = plan_scene(scene, TimingRules())

    # Phrase 1: earliest 4.15, event at 2.0 needs a 2.4 s hold.
    # Phrase 2: earliest 8.30, event now at 7.4 needs a 1.15 s hold.
    assert [s.kind for s in timeline.segments] == ["play", "hold", "play", "hold", "play"]
    assert_segment(timeline.segments[1], "hold", (2.0, 2.0), (2.0, 4.4))
    assert_segment(timeline.segments[2], "play", (2.0, 5.0), (4.4, 7.4))
    assert_segment(timeline.segments[3], "hold", (5.0, 5.0), (7.4, 8.55))
    assert_segment(timeline.segments[4], "play", (5.0, 12.0), (8.55, 15.55))
    assert starts(timeline) == [approx(0.0), approx(4.15), approx(8.30)]
    assert timeline.conflicts == []
    assert_contiguous(timeline)


def test_default_rules_match_the_spec() -> None:
    rules = TimingRules()
    assert rules.max_hold == 3.0
    assert rules.allow_holds is True
    assert rules.speed_up_waits is False
    assert rules.pin_lead == 0.25
    assert rules.pin_late == 0.40
    assert rules.breath == 0.35
    assert rules.phrase_gap == 0.15
    assert rules.max_speed == 4.0
    assert rules.min_wait_to_speed == 2.5


# Captions


def test_caption_duration_has_a_floor_of_one_and_a_half_seconds() -> None:
    assert caption_duration("Tap save") == approx(1.5)
    assert caption_duration("") == approx(1.5)


def test_caption_duration_grows_with_word_count() -> None:
    text = " ".join(["word"] * 14)
    assert caption_duration(text) == approx(14 / 2.8 + 0.5)
