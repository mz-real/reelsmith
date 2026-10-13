"""The Stutter check and the digital silence part of the Background noise check."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from reelsmith.models import ScriptModel, SpecModel
from reelsmith.qa import checks
from reelsmith.qa.checks import CheckStatus, QAContext, check_background_noise, check_stutter
from reelsmith.qa.image import judder_frames
from reelsmith.qa.timeline import PlacementOut, SceneOut, SegmentOut, Timeline
from reelsmith.qa.transcribe import Word


def _frames(count: int, stuck_every: int | None) -> np.ndarray:
    """A picture that moves on every frame, except one that repeats every stuck_every."""
    rng = np.random.default_rng(3)
    base = rng.uniform(0, 255, size=(90, 160))
    out = []
    shift = 0
    for index in range(count):
        if not (stuck_every and index % stuck_every == 0 and index > 0):
            shift += 1
        out.append(np.roll(base, shift * 3, axis=1))
    return np.stack(out)


def test_a_repeated_frame_inside_motion_is_a_judder_frame() -> None:
    assert len(judder_frames(_frames(60, 10))) == 5


def test_a_steady_move_and_a_still_picture_have_no_judder() -> None:
    assert judder_frames(_frames(60, None)) == []
    assert judder_frames(np.zeros((60, 90, 160))) == []


def test_a_short_clip_has_no_judder_frames() -> None:
    assert judder_frames(_frames(3, None)) == []


def _scene(scene_id: str, start: float, end: float) -> SceneOut:
    segment = SegmentOut("play", 0.0, end - start, 1.0, 0.0, end - start)
    return SceneOut(scene_id, start, end, [segment], None, None, None)


def _context(tmp_path: Path, scenes: list[SceneOut]) -> QAContext:
    timeline = Timeline(format="16x9", duration=scenes[-1].out_end, scenes=scenes, transitions=[])
    return QAContext(
        spec=SpecModel.model_validate({}),
        script=ScriptModel.model_validate({}),
        timeline=timeline,
        master=tmp_path / "master.mp4",
        master_duration=timeline.duration or 0.0,
        sheets_dir=tmp_path / "sheets",
        work_dir=tmp_path,
        transcriber=lambda path: [],
    )


def _serve(monkeypatch: pytest.MonkeyPatch, by_scene: dict[float, np.ndarray]) -> None:
    def fake(_master: Path, start: float, _end: float, _fps: float) -> np.ndarray:
        return by_scene[start]

    monkeypatch.setattr(checks, "extract_gray_frames", fake)


def test_stutter_passes_on_smooth_footage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, {0.0: _frames(300, None)})

    row = check_stutter(_context(tmp_path, [_scene("a", 0.0, 10.0)]))

    assert row.status == CheckStatus.PASS
    assert "0 judder frames" in row.details[0]


def test_stutter_warns_above_six_per_minute_and_names_the_scene(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 9 stuck frames in one minute of footage.
    frames = _frames(1800, None)
    frames = _with_stuck(frames, [100 + 150 * k for k in range(9)])
    _serve(monkeypatch, {0.0: frames})

    row = check_stutter(_context(tmp_path, [_scene("slide-a", 0.0, 60.0)]))

    assert row.status == CheckStatus.WARN
    assert "scene 'slide-a'" in row.details[0]


def test_stutter_fails_above_fifteen_per_minute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frames = _with_stuck(_frames(1800, None), [100 + 80 * k for k in range(20)])
    _serve(monkeypatch, {0.0: frames})

    row = check_stutter(_context(tmp_path, [_scene("hold", 0.0, 60.0)]))

    assert row.status == CheckStatus.FAIL
    assert "scene 'hold'" in row.details[0]


def test_stutter_counts_per_minute_across_scenes_not_per_scene(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clean = _frames(1800, None)
    bumpy = _with_stuck(_frames(1800, None), [100 + 150 * k for k in range(9)])
    _serve(monkeypatch, {0.0: bumpy, 60.0: clean})

    row = check_stutter(_context(tmp_path, [_scene("a", 0.0, 60.0), _scene("b", 60.0, 120.0)]))

    assert row.status == CheckStatus.PASS
    assert "4.5 per minute" in row.details[0]


def _with_stuck(frames: np.ndarray, indexes: list[int]) -> np.ndarray:
    """Repeat the previous frame at each index, so the picture stands still for one frame."""
    out = frames.copy()
    for index in indexes:
        out[index] = out[index - 1]
        out[index + 1 :] = np.roll(out[index + 1 :], -3, axis=2)
    return out


def _noise_context(tmp_path: Path) -> QAContext:
    scene = SceneOut(
        id="s",
        out_start=0.0,
        out_end=10.0,
        segments=None,
        placements=[PlacementOut("l1", 0, 0.0, 10.0, None)],
        captions=None,
        blur=None,
    )
    ctx = _context(tmp_path, [scene])
    words = [Word(text=f"w{i}", start=i * 0.5, end=i * 0.5 + 0.3) for i in range(20)]
    ctx.transcriber = lambda path: words
    return ctx


def _serve_gaps(monkeypatch: pytest.MonkeyPatch, levels: list[float]) -> None:
    queue = iter(levels)
    monkeypatch.setattr(checks, "extract_audio_window", lambda *args, **kwargs: None)
    monkeypatch.setattr(checks, "_rms_db", lambda *args, **kwargs: next(queue))


def test_noise_fails_when_the_floor_flips_between_digital_silence_and_hiss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve_gaps(monkeypatch, [-120.0, -52.0] * 10)

    row = check_background_noise(_noise_context(tmp_path))

    assert row.status == CheckStatus.FAIL
    assert "digital silence" in row.details[0]


def test_noise_passes_when_the_floor_is_steady_and_low(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve_gaps(monkeypatch, [-82.0, -80.0, -85.0, -79.0] * 5)

    row = check_background_noise(_noise_context(tmp_path))

    assert row.status == CheckStatus.PASS


def test_noise_passes_when_a_flat_digital_silence_has_no_audible_floor_to_flip_with(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve_gaps(monkeypatch, [-120.0] * 19)

    row = check_background_noise(_noise_context(tmp_path))

    assert row.status == CheckStatus.PASS
