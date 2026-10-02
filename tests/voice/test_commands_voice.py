"""Tests for the result formatting in reelsmith.commands.voice."""

from __future__ import annotations

from reelsmith.commands.voice import _plural, _result_for
from reelsmith.result import Status
from reelsmith.voice.pipeline import LineReport, VoiceReport


def _line(**overrides: object) -> LineReport:
    base: dict[str, object] = {
        "scene": "s",
        "line": "l1",
        "file": "s__l1.wav",
        "duration": 2.0,
        "hash": "abc",
        "phrases": [],
        "wpm": 170.0,
        "transcript_ok": True,
        "attempts": 1,
    }
    base.update(overrides)
    return LineReport(**base)  # type: ignore[arg-type]


def test_plural_singular_and_plural() -> None:
    assert _plural(1, "line") == "1 line"
    assert _plural(2, "line") == "2 lines"
    assert _plural(0, "line") == "0 lines"


def test_result_for_all_ok_always_reports_counts() -> None:
    report = VoiceReport(engine="kokoro", voice="af_heart", lines=[_line()])

    result = _result_for(report)

    assert result.status == Status.OK
    assert result.message == "Voice generated for 1 line"
    assert result.details == [
        "1 line generated",
        "0 lines skipped, already up to date",
        "0 lines regenerated for pace",
        "0 lines regenerated for dropped words",
    ]
    assert result.next_step == "reelsmith compose --preview"


def test_result_for_does_not_count_a_line_left_out_by_only() -> None:
    report = VoiceReport(
        engine="kokoro",
        voice="af_heart",
        lines=[_line(), _line(line="l2", left_out=True)],
    )

    result = _result_for(report)

    assert "1 line generated" in result.details
    assert result.message == "Voice generated for 2 lines"


def test_result_for_reports_pace_transcript_and_skip_counts() -> None:
    report = VoiceReport(
        engine="kokoro",
        voice="af_heart",
        lines=[
            _line(pace_retried=True),
            _line(line="l2", transcript_retried=True),
            _line(line="l3", skipped=True),
        ],
    )

    result = _result_for(report)

    assert result.status == Status.OK
    assert "1 line regenerated for pace" in result.details
    assert "1 line regenerated for dropped words" in result.details
    assert "1 line skipped, already up to date" in result.details


def test_result_for_warns_on_remaining_transcript_failures() -> None:
    report = VoiceReport(
        engine="kokoro",
        voice="af_heart",
        lines=[_line(transcript_ok=False, missing_words=["fast"])],
    )

    result = _result_for(report)

    assert result.status == Status.WARN
    assert "need review" in result.message
    assert result.next_step == "reelsmith voice generate --only s/l1"
    assert any("dropped words" in detail for detail in result.details)


def test_result_for_warns_on_a_line_that_still_fails_pace() -> None:
    report = VoiceReport(
        engine="kokoro",
        voice="af_heart",
        lines=[_line(wpm=60.0, pace_retried=True)],
    )

    result = _result_for(report)

    assert result.status == Status.WARN
    assert "need review" in result.message
    assert any("pace" in detail for detail in result.details)


def test_result_for_ignores_pace_on_a_line_where_pace_was_not_checked() -> None:
    report = VoiceReport(
        engine="kokoro",
        voice="af_heart",
        lines=[_line(wpm=400.0, pace_checked=False)],
    )

    result = _result_for(report)

    assert result.status == Status.OK


def test_result_for_never_ok_when_a_line_still_fails() -> None:
    report = VoiceReport(
        engine="kokoro",
        voice="af_heart",
        lines=[_line(wpm=400.0, transcript_ok=False)],
    )

    result = _result_for(report)

    assert result.status != Status.OK
    assert "s/l1 still fails: pace and dropped words" in result.details


def test_result_for_warns_on_a_pronunciation_fallback() -> None:
    report = VoiceReport(
        engine="kokoro",
        voice="af_heart",
        lines=[_line(warnings=["WARN: could not place the pronunciation for 'reelsmith'"])],
    )

    result = _result_for(report)

    assert result.status == Status.WARN
    assert any("reelsmith" in detail for detail in result.details)
    assert result.next_step == "reelsmith compose --preview"


def test_result_for_ignores_pronunciation_warnings_on_a_skipped_line() -> None:
    report = VoiceReport(
        engine="kokoro",
        voice="af_heart",
        lines=[_line(skipped=True, warnings=["WARN: stale, should not be reported"])],
    )

    result = _result_for(report)

    assert result.status == Status.OK
    assert not any("stale" in detail for detail in result.details)


def test_result_for_repeats_only_for_each_failing_line() -> None:
    report = VoiceReport(
        engine="kokoro",
        voice="af_heart",
        lines=[
            _line(scene="a", line="l1", transcript_ok=False),
            _line(scene="b", line="l2", wpm=60.0),
            _line(scene="c", line="l3"),
        ],
    )

    result = _result_for(report)

    assert result.next_step == "reelsmith voice generate --only a/l1 --only b/l2"
