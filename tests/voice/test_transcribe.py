"""Tests for the vocabulary hints passed to faster-whisper."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from reelsmith.models import Line, Phrase, ScriptModel, ScriptScene, SpecModel, VoiceSettings
from reelsmith.voice import transcribe as voice_transcribe
from reelsmith.voice.base import Audio


class _FakeModel:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def transcribe(self, samples: np.ndarray, **kwargs: Any) -> tuple[list[Any], None]:
        self.kwargs = kwargs
        word = SimpleNamespace(word=" hello", start=0.0, end=0.2)
        return [SimpleNamespace(words=[word])], None


@pytest.fixture
def fake_model(monkeypatch: pytest.MonkeyPatch) -> _FakeModel:
    model = _FakeModel()
    monkeypatch.setattr(voice_transcribe, "_load_model", lambda: model)
    return model


def _audio() -> Audio:
    return Audio(samples=np.zeros(1600, dtype=np.float32), sample_rate=16000)


SENTENCE = "In Claude Code, add the reelsmith marketplace, then open spec.yaml."


def _script() -> ScriptModel:
    return ScriptModel(
        scenes=[
            ScriptScene(
                id="s",
                lines=[
                    Line(id="l1", phrases=[Phrase(text=SENTENCE)]),
                    Line(
                        id="l2",
                        phrases=[Phrase(text="Run reelsmith qa.", say="Run reelsmith QA now.")],
                    ),
                ],
            )
        ]
    )


def _spec() -> SpecModel:
    return SpecModel(voice=VoiceSettings(vocabulary=["reelsmith", "Kokoro"]))


def test_hints_hold_the_user_vocabulary_then_the_uncommon_script_words() -> None:
    hints = voice_transcribe.vocabulary_hints(_spec(), _script())

    assert hints == ["reelsmith", "Kokoro", "Claude", "Code", "spec.yaml", "QA"]


def test_hints_come_from_say_where_a_phrase_has_one() -> None:
    hints = voice_transcribe.vocabulary_hints(SpecModel(), _script())

    assert hints[-1] == "QA"


def test_hints_are_capped() -> None:
    spec = SpecModel(voice=VoiceSettings(vocabulary=[f"Word{n}" for n in range(200)]))

    hints = voice_transcribe.vocabulary_hints(spec, ScriptModel())

    assert len(hints) == voice_transcribe.MAX_HINTS


def test_the_prompt_holds_only_vocabulary_words_never_the_sentence(
    fake_model: _FakeModel,
) -> None:
    hints = voice_transcribe.vocabulary_hints(_spec(), _script())

    words = voice_transcribe.transcribe(_audio(), vocabulary=hints)

    assert words[0].text == "hello"
    prompt = fake_model.kwargs["hotwords"]
    assert prompt.split(", ") == hints
    assert SENTENCE not in prompt
    for common in ("add", "the", "marketplace", "then", "open", "In", "Run"):
        assert common not in prompt.split(", ")
    assert "initial_prompt" not in fake_model.kwargs


def test_no_vocabulary_means_no_hotwords(fake_model: _FakeModel) -> None:
    voice_transcribe.transcribe(_audio())

    assert "hotwords" not in fake_model.kwargs
    assert "initial_prompt" not in fake_model.kwargs
