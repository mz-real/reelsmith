"""The nine QA checks run against a composed master video."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from reelsmith.errors import ReelsmithError
from reelsmith.models import ScriptModel, SpecModel
from reelsmith.qa.av import ebur128_loudness, extract_audio_window, extract_frame, rms_of_window
from reelsmith.qa.image import build_contact_sheet, grayscale_crop, laplacian_variance
from reelsmith.qa.text import compare_words
from reelsmith.qa.timeline import CaptionOut, PlacementOut, SceneOut, Timeline
from reelsmith.qa.transcribe import Transcriber
from reelsmith.timing import TimingRules, caption_duration

LOUDNESS_TARGET = -16.0
LOUDNESS_TOLERANCE = 1.5
TRUE_PEAK_CEILING = -1.0
END_NOISE_WINDOW = 0.30
END_NOISE_RATIO = 0.35
END_NOISE_FLOOR = 0.01
END_NOISE_NEXT_GAP = 0.05
END_NOISE_MIN_GAP = 0.15
BLUR_RATIO = 0.30
BLUR_SAMPLES = 3
# A caption on screen for its whole spoken line is readable: the viewer hears it.
CAPTION_READ_GRACE = 0.0
CAPTION_MIN_ON_SCREEN = 1.0
TRANSCRIPT_LEAD = 0.1
TRANSCRIPT_TRAIL = 0.35
TRANSCRIPT_NEXT_GAP = 0.05
EPS = 1e-6


class CheckStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


_RANK = {CheckStatus.PASS: 0, CheckStatus.WARN: 1, CheckStatus.FAIL: 2}


def worse(a: CheckStatus, b: CheckStatus) -> CheckStatus:
    return a if _RANK[a] >= _RANK[b] else b


@dataclass
class CheckRow:
    name: str
    status: CheckStatus
    details: list[str] = field(default_factory=list)


@dataclass
class QAContext:
    spec: SpecModel
    script: ScriptModel
    timeline: Timeline
    master: Path
    master_duration: float
    sheets_dir: Path
    work_dir: Path
    transcriber: Transcriber
    rules: TimingRules = field(default_factory=TimingRules)


def _scene_where(scene_id: str) -> str:
    return f"scene '{scene_id}'"


def _line_where(scene_id: str, placement: PlacementOut) -> str:
    return f"scene '{scene_id}' line '{placement.line}' phrase {placement.phrase}"


def check_transcript(ctx: QAContext) -> CheckRow:
    """1. Transcript vs script: does the narration say what the script says.

    Each line is transcribed as a whole, from a little before its first
    phrase starts to a little after its last phrase ends, so a word
    boundary never falls right at the cut and clips the last word (heard
    as a shorter, different word). A singular/plural difference against
    the script is not treated as a real mistake: it is noted as a WARN
    instead of a FAIL.
    """
    status = CheckStatus.PASS
    details: list[str] = []
    scenes_by_id = {s.id: s for s in ctx.script.scenes}

    for scene_tl in ctx.timeline.scenes:
        if scene_tl.placements is None:
            details.append(
                f"{_scene_where(scene_tl.id)}: timeline.json has no 'placements' field, "
                "so narration cannot be checked. Fix: have compose write placements for "
                "this scene."
            )
            status = worse(status, CheckStatus.WARN)
            continue
        script_scene = scenes_by_id.get(scene_tl.id)
        if script_scene is None:
            details.append(
                f"{_scene_where(scene_tl.id)} is in the master but not in script.yaml. "
                "Fix: add this scene to script.yaml or rebuild without it."
            )
            status = worse(status, CheckStatus.WARN)
            continue
        lines_by_id = {line.id: line for line in script_scene.lines}
        all_starts = sorted(p.out_start for p in scene_tl.placements)
        for line_id, placements in _group_by_line(scene_tl.placements).items():
            ordered = sorted(placements, key=lambda p: p.phrase)
            first = ordered[0]
            line = lines_by_id.get(line_id)
            if line is None or any(p.phrase >= len(line.phrases) for p in ordered):
                details.append(
                    f"{_line_where(scene_tl.id, first)}: no matching phrase in "
                    "script.yaml. Fix: check script.yaml matches the current build."
                )
                status = worse(status, CheckStatus.WARN)
                continue
            expected = line.text
            last = max(ordered, key=lambda p: p.phrase)
            start = max(0.0, first.out_start - TRANSCRIPT_LEAD)
            end = last.out_end + TRANSCRIPT_TRAIL
            next_start = next((s for s in all_starts if s > last.out_end + EPS), None)
            if next_start is not None:
                end = min(end, next_start - TRANSCRIPT_NEXT_GAP)
            end = max(end, last.out_end)
            if ctx.master_duration:
                end = min(end, ctx.master_duration)
            heard = _transcribe_window(ctx, start, end)
            missing, changed = compare_words(expected, heard)
            real_changed = [pair for pair in changed if not _is_plural_only(*pair)]
            plural_notes = [pair for pair in changed if _is_plural_only(*pair)]
            if missing or real_changed:
                status = worse(status, CheckStatus.FAIL)
                parts = []
                if missing:
                    parts.append(f"missing word(s) {missing}")
                if real_changed:
                    said = [f"'{exp}' heard as '{act}'" for exp, act in real_changed]
                    parts.append(f"changed word(s): {said}")
                details.append(
                    f"{_line_where(scene_tl.id, first)} at {first.out_start:.2f}s: "
                    f"{'; '.join(parts)}. Fix: re-record this line "
                    f"(reelsmith voice generate --only {scene_tl.id}/{line_id}) "
                    "and recompose."
                )
                continue
            if plural_notes:
                status = worse(status, CheckStatus.WARN)
                said = [f"'{exp}' heard as '{act}'" for exp, act in plural_notes]
                details.append(
                    f"{_line_where(scene_tl.id, first)} at {first.out_start:.2f}s: "
                    f"singular/plural only, not a failure: {said}."
                )
    if not details:
        details.append("Every narrated phrase matches its script text.")
    return CheckRow("Transcript vs script", status, details)


def _is_plural_only(expected: str, heard: str) -> bool:
    """True when the only difference between the two words is a trailing s."""
    if expected.endswith("s") and expected[:-1] == heard:
        return True
    return heard.endswith("s") and heard[:-1] == expected


def _transcribe_window(ctx: QAContext, start: float, end: float) -> str:
    wav_path = ctx.work_dir / f"transcript-{start:.3f}-{end:.3f}.wav"
    extract_audio_window(ctx.master, start, end, wav_path)
    words = ctx.transcriber(wav_path)
    return " ".join(word.text for word in words)


def check_sync(ctx: QAContext) -> CheckRow:
    """2. Sync: a pinned phrase starts near its event."""
    status = CheckStatus.PASS
    details: list[str] = []
    lead, late = ctx.rules.pin_lead, ctx.rules.pin_late

    for scene_tl in ctx.timeline.scenes:
        if scene_tl.placements is None:
            details.append(
                f"{_scene_where(scene_tl.id)}: timeline.json has no 'placements' field, "
                "so sync cannot be checked. Fix: have compose write placements for this "
                "scene."
            )
            status = worse(status, CheckStatus.WARN)
            continue
        for placement in scene_tl.placements:
            if placement.pin_event_out is None:
                continue
            diff = placement.out_start - placement.pin_event_out
            if -lead - EPS <= diff <= late + EPS:
                continue
            status = worse(status, CheckStatus.FAIL)
            when = "early" if diff < 0 else "late"
            details.append(
                f"{_line_where(scene_tl.id, placement)}: starts at "
                f"{placement.out_start:.2f}s, {abs(diff):.2f}s {when} against its event at "
                f"{placement.pin_event_out:.2f}s (allowed -{lead:g}s to +{late:g}s). "
                "Fix: adjust the pin in script.yaml or rerun reelsmith compose."
            )
    if not details:
        details.append("Every pinned phrase starts inside its sync window.")
    return CheckRow("Sync", status, details)


def check_cutoff(ctx: QAContext) -> CheckRow:
    """3. Cut off lines: narration must not run past its scene or the master."""
    status = CheckStatus.PASS
    details: list[str] = []
    master_end = ctx.timeline.duration if ctx.timeline.duration is not None else ctx.master_duration

    for scene_tl in ctx.timeline.scenes:
        if scene_tl.placements is None:
            details.append(
                f"{_scene_where(scene_tl.id)}: timeline.json has no 'placements' field, "
                "so cut off lines cannot be checked. Fix: have compose write placements "
                "for this scene."
            )
            status = worse(status, CheckStatus.WARN)
            continue
        for placement in scene_tl.placements:
            over_scene = placement.out_end - scene_tl.out_end
            if over_scene > EPS:
                status = worse(status, CheckStatus.FAIL)
                details.append(
                    f"{_line_where(scene_tl.id, placement)}: ends at "
                    f"{placement.out_end:.2f}s, {over_scene:.2f}s past the end of its scene "
                    f"({scene_tl.out_end:.2f}s). Fix: shorten this line, enable holds or "
                    "speed_up_waits in spec.yaml, then recompose."
                )
                continue
            over_master = placement.out_end - master_end
            if over_master > EPS:
                status = worse(status, CheckStatus.FAIL)
                details.append(
                    f"{_line_where(scene_tl.id, placement)}: ends at "
                    f"{placement.out_end:.2f}s, {over_master:.2f}s past the end of the "
                    f"master ({master_end:.2f}s). Fix: shorten this line and recompose."
                )
    if not details:
        details.append("No line runs past its scene or the end of the master.")
    return CheckRow("Cut off lines", status, details)


def check_end_noise(ctx: QAContext) -> CheckRow:
    """4. End of line noise: a click or breath left in after the last word.

    Only the gap after the last phrase of a line is measured, never the
    whole 300 ms window regardless of what comes next: the next phrase or
    line often starts well inside that window, so a window reaching past
    it would measure speech, not silence. When the next line starts too
    soon to leave a real gap, the line is skipped rather than measured.
    """
    status = CheckStatus.PASS
    details: list[str] = []
    all_starts = sorted(
        p.out_start for s in ctx.timeline.scenes if s.placements for p in s.placements
    )

    for scene_tl in ctx.timeline.scenes:
        if scene_tl.placements is None:
            details.append(
                f"{_scene_where(scene_tl.id)}: timeline.json has no 'placements' field, "
                "so end of line noise cannot be checked. Fix: have compose write "
                "placements for this scene."
            )
            status = worse(status, CheckStatus.WARN)
            continue
        for line_id, placements in _group_by_line(scene_tl.placements).items():
            first = min(placements, key=lambda p: p.out_start)
            last = max(placements, key=lambda p: p.phrase)
            after_start = last.out_end
            next_start = next((s for s in all_starts if s > after_start + EPS), None)
            if next_start is not None:
                boundary = next_start - END_NOISE_NEXT_GAP
            elif ctx.master_duration:
                boundary = ctx.master_duration
            else:
                boundary = after_start + END_NOISE_WINDOW
            gap = boundary - after_start
            if gap < END_NOISE_MIN_GAP - EPS:
                details.append(
                    f"{_scene_where(scene_tl.id)} line '{line_id}': the next line starts "
                    f"only {max(gap, 0.0):.2f}s later, too soon to check for leftover "
                    "noise. Skipped."
                )
                continue
            after_end = after_start + min(gap, END_NOISE_WINDOW)
            if after_end - after_start < 0.02:
                continue
            speech_level = rms_of_window(ctx.master, first.out_start, last.out_end, ctx.work_dir)
            after_level = rms_of_window(ctx.master, after_start, after_end, ctx.work_dir)
            threshold = max(END_NOISE_FLOOR, speech_level * END_NOISE_RATIO)
            if after_level <= threshold:
                continue
            status = worse(status, CheckStatus.FAIL)
            details.append(
                f"{_scene_where(scene_tl.id)} line '{line_id}': noise after the last word "
                f"at {after_start:.2f}s is still loud ({after_level:.4f} vs a speech level "
                f"of {speech_level:.4f}). Fix: trim the trailing audio for this line "
                f"(reelsmith voice generate --only {scene_tl.id}/{line_id}) and recompose."
            )
    if not details:
        details.append("No leftover noise found after the last word of any line.")
    return CheckRow("End of line noise", status, details)


def _group_by_line(placements: list[PlacementOut]) -> dict[str, list[PlacementOut]]:
    grouped: dict[str, list[PlacementOut]] = {}
    for placement in placements:
        grouped.setdefault(placement.line, []).append(placement)
    return grouped


def check_loudness(ctx: QAContext) -> CheckRow:
    """5. Loudness: integrated loudness and true peak within spec."""
    integrated, true_peak = ebur128_loudness(ctx.master)
    details: list[str] = []
    status = CheckStatus.PASS
    low, high = LOUDNESS_TARGET - LOUDNESS_TOLERANCE, LOUDNESS_TARGET + LOUDNESS_TOLERANCE
    if not (low - EPS <= integrated <= high + EPS):
        status = worse(status, CheckStatus.FAIL)
        details.append(
            f"Integrated loudness is {integrated:.1f} LUFS, outside "
            f"{LOUDNESS_TARGET:g} +/-{LOUDNESS_TOLERANCE:g} LUFS. "
            "Fix: re-run compose or export so loudnorm targets "
            f"{LOUDNESS_TARGET:g} LUFS."
        )
    if true_peak > TRUE_PEAK_CEILING + EPS:
        status = worse(status, CheckStatus.FAIL)
        details.append(
            f"True peak is {true_peak:.1f} dBTP, above the {TRUE_PEAK_CEILING:g} dBTP "
            "ceiling. Fix: lower the narration or music gain and recompose."
        )
    if not details:
        details.append(
            f"Integrated loudness {integrated:.1f} LUFS, true peak {true_peak:.1f} dBTP."
        )
    return CheckRow("Loudness", status, details)


def check_holds(ctx: QAContext) -> CheckRow:
    """6. Hold limits: a held last frame must not run too long."""
    status = CheckStatus.PASS
    details: list[str] = []
    max_hold = ctx.rules.max_hold

    for scene_tl in ctx.timeline.scenes:
        if scene_tl.segments is None:
            details.append(
                f"{_scene_where(scene_tl.id)}: timeline.json has no 'segments' field, "
                "so holds cannot be checked. Fix: have compose write segments for this "
                "scene."
            )
            status = worse(status, CheckStatus.WARN)
            continue
        for segment in scene_tl.segments:
            if segment.kind != "hold":
                continue
            length = segment.out_end - segment.out_start
            if length > max_hold + EPS:
                status = worse(status, CheckStatus.FAIL)
                details.append(
                    f"{_scene_where(scene_tl.id)}: holds the last frame for {length:.2f}s "
                    f"at {segment.out_start:.2f}s, over the {max_hold:g}s limit. "
                    "Fix: shorten the narration, turn on speed_up_waits, or trim the "
                    "clip, then recompose."
                )
    if not details:
        details.append("No held frame runs longer than the hold limit.")
    return CheckRow("Hold limits", status, details)


def check_captions(ctx: QAContext) -> CheckRow:
    """7. Captions: text fits its panel and stays on screen long enough.

    A caption that stays on screen for as long as its narration plays (plus
    a small grace period) is readable by definition, even if that is less
    than the generic reading-speed estimate. The required time is whichever
    of the two is shorter. A caption on screen for under a second always
    fails, no matter how short its text is.
    """
    status = CheckStatus.PASS
    details: list[str] = []

    captions_off = ctx.spec.options.captions == "none"
    for scene_tl in ctx.timeline.scenes:
        if scene_tl.captions is None:
            if captions_off:
                continue
            details.append(
                f"{_scene_where(scene_tl.id)}: timeline.json has no 'captions' field, "
                "so captions cannot be checked. Fix: have compose write captions for "
                "this scene, or skip this check when captions are off."
            )
            status = worse(status, CheckStatus.WARN)
            continue
        for caption in scene_tl.captions:
            box_x, box_y, box_w, box_h = caption.box
            panel_x, panel_y, panel_w, panel_h = caption.panel
            inside = (
                box_x >= panel_x - EPS
                and box_y >= panel_y - EPS
                and box_x + box_w <= panel_x + panel_w + EPS
                and box_y + box_h <= panel_y + panel_h + EPS
            )
            if not inside:
                status = worse(status, CheckStatus.FAIL)
                details.append(
                    f"{_scene_where(scene_tl.id)} caption '{caption.text}' at "
                    f"{caption.out_start:.2f}s: text box {list(caption.box)} overflows "
                    f"its panel {list(caption.panel)}. Fix: widen the panel or shorten "
                    "the caption text, then recompose."
                )
            read_time = caption_duration(caption.text)
            spoken = _caption_spoken_duration(scene_tl.placements, caption)
            if spoken is not None:
                required = min(read_time, spoken + CAPTION_READ_GRACE)
            else:
                required = read_time
            required = max(required, CAPTION_MIN_ON_SCREEN)
            actual = caption.out_end - caption.out_start
            if actual < required - EPS:
                status = worse(status, CheckStatus.FAIL)
                details.append(
                    f"{_scene_where(scene_tl.id)} caption '{caption.text}' at "
                    f"{caption.out_start:.2f}s: on screen for {actual:.2f}s, needs at "
                    f"least {required:.2f}s to read. Fix: lengthen this caption or "
                    "split the line, then recompose."
                )
    if not details:
        if captions_off:
            details.append("Captions are turned off in spec.yaml, so there is nothing to check.")
        else:
            details.append("Every caption fits its panel and stays on screen long enough.")
    return CheckRow("Captions", status, details)


def _caption_spoken_duration(
    placements: list[PlacementOut] | None, caption: CaptionOut
) -> float | None:
    """Sum the narrated time of the phrases a caption covers.

    A caption's own window often runs a little past the phrase it names
    (the gap before the next line starts, or the whole scene for a title
    caption), so only placements whose phrase starts inside the caption's
    window are counted, using the timeline's own placement times. Returns
    None when there is nothing to count, so the caller falls back to the
    plain reading-speed estimate.
    """
    if placements is None:
        return None
    covered = [
        placement
        for placement in placements
        if caption.out_start - EPS <= placement.out_start < caption.out_end - EPS
    ]
    if not covered:
        return None
    return sum(placement.out_end - placement.out_start for placement in covered)


def check_blur(ctx: QAContext) -> CheckRow:
    """8. Blur: listed regions stay blurred for their whole window."""
    status = CheckStatus.PASS
    details: list[str] = []

    for scene_tl in ctx.timeline.scenes:
        if scene_tl.blur is None:
            details.append(
                f"{_scene_where(scene_tl.id)}: timeline.json has no 'blur' field, so blur "
                "cannot be checked. Fix: have compose write blur regions for this scene, "
                "or skip this check when none are configured."
            )
            status = worse(status, CheckStatus.WARN)
            continue
        for index, region in enumerate(scene_tl.blur):
            raw_times = _sample_times(region.out_start, region.out_end, BLUR_SAMPLES)
            times = [_clamp_to_master(t, ctx.master_duration) for t in raw_times]
            for time in times:
                frame_path = ctx.work_dir / f"blur-{scene_tl.id}-{index}-{time:.3f}.png"
                extract_frame(ctx.master, time, frame_path)
                box_gray = grayscale_crop(frame_path, region.box)
                box_variance = laplacian_variance(box_gray)
                frame_gray = grayscale_crop(frame_path, None)
                frame_variance = laplacian_variance(frame_gray)
                if frame_variance <= EPS:
                    continue
                ratio = box_variance / frame_variance
                if ratio > BLUR_RATIO:
                    status = worse(status, CheckStatus.FAIL)
                    details.append(
                        f"{_scene_where(scene_tl.id)} blur region {index} "
                        f"{list(region.box)}: still sharp at {time:.2f}s "
                        f"(detail {box_variance:.1f} vs frame {frame_variance:.1f}). "
                        "Fix: check the blur filter covers this region for its full "
                        "window and recompose."
                    )
    if not details:
        details.append("Every blur region stays blurred for its whole window.")
    return CheckRow("Blur", status, details)


def _sample_times(start: float, end: float, count: int) -> list[float]:
    if count <= 1 or end <= start:
        return [start]
    step = (end - start) / (count - 1)
    return [start + step * i for i in range(count)]


FRAME_EPS = 0.05


def _clamp_to_master(time: float, master_duration: float) -> float:
    """Pull a sample time just inside the master so a frame always exists."""
    if master_duration <= 0.0:
        return time
    return min(time, max(0.0, master_duration - FRAME_EPS))


def check_contact_sheets(ctx: QAContext) -> CheckRow:
    """9. Contact sheets: frames for a human (or an AI) to look over by eye."""
    details: list[str] = []

    scene_frames = [
        (scene.out_start, f"{scene.id} @ {scene.out_start:.2f}s") for scene in ctx.timeline.scenes
    ]
    event_frames = _event_frames(ctx.timeline.scenes)
    transition_frames = [(t, f"transition @ {t:.2f}s") for t in (ctx.timeline.transitions or [])]

    for name, frames in (
        ("scenes", scene_frames),
        ("events", event_frames),
        ("transitions", transition_frames),
    ):
        sheet_path = ctx.sheets_dir / f"{name}.jpg"
        tiles: list[tuple[Path, str]] = []
        for time, label in frames:
            frame_path = ctx.work_dir / f"sheet-{name}-{time:.3f}.png"
            try:
                extract_frame(ctx.master, time, frame_path)
            except Exception:  # noqa: BLE001 - one bad frame should not break the sheet
                continue
            tiles.append((frame_path, label))
        if not tiles:
            details.append(f"No {name} to put on a contact sheet.")
            continue
        build_contact_sheet(tiles, sheet_path)
        details.append(f"{sheet_path.name} ({len(tiles)} frame(s))")

    return CheckRow("Contact sheets", CheckStatus.PASS, details)


def _event_frames(scenes: Iterable[SceneOut]) -> list[tuple[float, str]]:
    seen: set[float] = set()
    frames: list[tuple[float, str]] = []
    for scene in scenes:
        if scene.placements is None:
            continue
        for placement in scene.placements:
            if placement.pin_event_out is None:
                continue
            key = round(placement.pin_event_out, 3)
            if key in seen:
                continue
            seen.add(key)
            frames.append((placement.pin_event_out, f"{scene.id}/{placement.line} @ {key:.2f}s"))
    return frames


CHECKS: tuple[tuple[str, Callable[[QAContext], CheckRow]], ...] = (
    ("Transcript vs script", check_transcript),
    ("Sync", check_sync),
    ("Cut off lines", check_cutoff),
    ("End of line noise", check_end_noise),
    ("Loudness", check_loudness),
    ("Hold limits", check_holds),
    ("Captions", check_captions),
    ("Blur", check_blur),
    ("Contact sheets", check_contact_sheets),
)


def run_checks(ctx: QAContext) -> list[CheckRow]:
    """Run every check, so one check's own problem never loses the rest.

    A check that cannot run at all (for example a missing optional
    dependency) becomes a WARN row naming the problem and its fix,
    instead of stopping the whole report.
    """
    rows: list[CheckRow] = []
    for name, check in CHECKS:
        try:
            rows.append(check(ctx))
        except ReelsmithError as exc:
            message = str(exc)
            if exc.fix:
                message = f"{message} Fix: {exc.fix}"
            rows.append(CheckRow(name, CheckStatus.WARN, [f"Could not run this check: {message}"]))
    return rows
