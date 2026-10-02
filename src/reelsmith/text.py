"""Shared text normalisation for the transcript checks.

The voice step and QA both compare what Whisper heard with what the
script says. Both use this module, so they agree on what counts as the
same word.

British and American spelling variants come first.

Kokoro reads British spelling correctly, for example "favourites",
"colour" or "organise". Whisper often writes the American form instead.
Comparing a transcript to the script text word for word would then
report a word that was spoken correctly as missing or changed.

normalise_word maps both spellings of a word to the same canonical
form, so a word for word comparison is spelling-blind. It is meant to
run on a single lowercase token with punctuation already stripped.

The rest of the module adds a few narrow tolerances, each driven by a
small table: numbers and digits, a few abbreviations, two words heard as
one (or one as two), and homophones of the script's own vocabulary
words. See compare_text.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

# Short words where "our" is the whole sound, not the British "colour"
# style ending. These are left unchanged.
_OUR_WHOLE_SOUND = {
    "your",
    "four",
    "hour",
    "pour",
    "tour",
    "flour",
    "sour",
    "our",
    "dour",
    "yours",
    "fours",
    "hours",
    "tours",
}


def _ise_roots(words: list[str]) -> set[str]:
    """The part of each word before its final "ise"."""
    return {word[:-3] for word in words}


# Words that are spelled with "ise" in both British and American English.
# Converting them to "ize" would produce a word that does not exist.
_ISE_FIXED_ROOTS = _ise_roots(
    [
        "rise",
        "wise",
        "otherwise",
        "likewise",
        "raise",
        "praise",
        "noise",
        "poise",
        "promise",
        "surprise",
        "exercise",
        "advertise",
        "compromise",
        "expertise",
        "enterprise",
        "premise",
        "precise",
        "concise",
        "paradise",
        "franchise",
        "merchandise",
        "televise",
        "supervise",
        "revise",
        "advise",
        "devise",
        "comprise",
        "despise",
        "disguise",
        "improvise",
    ]
)

# Words that clearly take both spellings (organise/organize and the
# like). These are not special cased in the conversion below: they are
# not in _ISE_FIXED_ROOTS, so they fall through to the default
# conversion. Kept here as documentation and for the test table.
ISE_BOTH_SPELLINGS = [
    "organise",
    "realise",
    "recognise",
    "customise",
    "optimise",
    "prioritise",
    "summarise",
    "finalise",
    "personalise",
    "visualise",
    "minimise",
    "maximise",
    "categorise",
    "synchronise",
]


def _convert_our(word: str) -> str:
    if word in _OUR_WHOLE_SOUND or "our" not in word:
        return word
    return word.replace("our", "or")


def _convert_ise(word: str) -> str:
    for suffix, replacement in (
        ("isation", "ization"),
        ("ising", "izing"),
        ("ised", "ized"),
        ("ise", "ize"),
    ):
        if word.endswith(suffix) and len(word) > len(suffix):
            root = word[: -len(suffix)]
            if root in _ISE_FIXED_ROOTS:
                return word
            return root + replacement
    return word


def _convert_yse(word: str) -> str:
    for suffix, replacement in (("ysing", "yzing"), ("ysed", "yzed"), ("yse", "yze")):
        if word.endswith(suffix) and len(word) > len(suffix):
            return word[: -len(suffix)] + replacement
    return word


def _convert_tre(word: str) -> str:
    if word.endswith("tre") and len(word) > 3:
        return word[:-3] + "ter"
    return word


def _convert_ogue(word: str) -> str:
    if word.endswith("ogue") and len(word) > 4:
        return word[:-4] + "og"
    return word


def _convert_doubled_ll(word: str) -> str:
    if word.endswith("lling") and len(word) > 5:
        return word[:-5] + "ling"
    if word.endswith("lled") and len(word) > 4:
        return word[:-4] + "led"
    return word


def normalise_word(word: str) -> str:
    """Map a word to a canonical form that ignores British/American spelling.

    Two words are equal under this comparison if they match after both
    are passed through here. See the module docstring for the rules.
    """
    result = word.lower()
    result = _convert_our(result)
    result = _convert_ise(result)
    result = _convert_yse(result)
    result = _convert_tre(result)
    result = _convert_ogue(result)
    result = _convert_doubled_ll(result)
    return result


# --- tokens ---------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9']+")
# The dot in a file name, as in spec.yaml or Whisper's "spec .yaml", is
# read aloud as "dot": it comes after a word of two or more letters (or a
# space) and before two or more letters. A full stop is followed by a
# space, a decimal point by a digit, and the dots in Q.A. or e.g. sit
# between single letters, so none of those match.
_SPOKEN_DOT_RE = re.compile(r"(?:(?<=[a-z][a-z])|(?<=\s))\.(?=[a-z][a-z])")
_MAX_JOIN_PARTS = 4

_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_MAX_SPOKEN_NUMBER = 100

ORDINALS = {
    "1st": "first",
    "2nd": "second",
    "3rd": "third",
    "4th": "fourth",
    "5th": "fifth",
    "6th": "sixth",
    "7th": "seventh",
    "8th": "eighth",
    "9th": "ninth",
    "10th": "tenth",
}

ABBREVIATIONS: dict[str, tuple[str, ...]] = {
    "dr": ("doctor",),
    "st": ("street",),
    "vs": ("versus",),
    "etc": ("et", "cetera"),
}


def number_words(value: int) -> list[str]:
    """Spell out a number from 0 to 100 as words."""
    if value < 20:
        return [_ONES[value]]
    if value < 100:
        tens, rest = divmod(value, 10)
        return [_TENS[tens]] if rest == 0 else [_TENS[tens], _ONES[rest]]
    return ["one", "hundred"]


def _expand(token: str) -> list[str]:
    if token.isdigit() and int(token) <= _MAX_SPOKEN_NUMBER:
        return number_words(int(token))
    if token in ORDINALS:
        return [ORDINALS[token]]
    if token in ABBREVIATIONS:
        return list(ABBREVIATIONS[token])
    return [normalise_word(token)]


def tokens(text: str) -> list[str]:
    """Lowercase bare words, with numbers, ordinals, abbreviations and the
    dot in a file name spelled out, and British/American spelling folded
    to one form."""
    result: list[str] = []
    spoken = _SPOKEN_DOT_RE.sub(" dot ", text.lower())
    for raw in _WORD_RE.findall(spoken):
        word = raw.strip("'")
        if word:
            result.extend(_expand(word))
    return result


# --- phonetic key ---------------------------------------------------------

_VOWELS = frozenset("aeiou")
_INITIAL_SILENT = ("kn", "gn", "pn", "wr", "ae")
_MIN_KEY_LENGTH = 2


def _next(word: str, index: int) -> str:
    return word[index + 1] if index + 1 < len(word) else ""


def _consonant_code(word: str, i: int) -> str:
    """The sound of the consonant at word[i], a simplified Metaphone rule."""
    letter, after, before = word[i], _next(word, i), word[i - 1] if i else ""
    rest = word[i + 1 :]
    if letter == "b":
        return "" if before == "m" and not after else "P"
    if letter == "c":
        if rest.startswith(("ia", "h")):
            return "X"
        return "S" if after in ("i", "e", "y") else "K"
    if letter == "d":
        return "J" if rest.startswith(("ge", "gi", "gy")) else "T"
    if letter == "g":
        if after == "h" and _next(word, i + 1) not in _VOWELS:
            return ""
        return "J" if after in ("i", "e", "y") else "K"
    if letter == "h":
        return "H" if after in _VOWELS and before not in ("c", "s", "p", "t", "g") else ""
    if letter == "k":
        return "" if before == "c" else "K"
    if letter == "p":
        return "F" if after == "h" else "P"
    if letter == "s":
        return "X" if rest.startswith(("h", "io", "ia")) else "S"
    if letter == "t":
        if rest.startswith(("io", "ia")):
            return "X"
        return "0" if after == "h" else "T"
    if letter in ("w", "y"):
        return letter.upper() if after in _VOWELS else ""
    simple = {"q": "K", "v": "F", "x": "KS", "z": "S"}
    return simple.get(letter, letter.upper())


def phonetic_key(word: str) -> str:
    """A small Metaphone style sound key: vowels after the first letter are
    dropped and letters that sound alike share a code."""
    letters = "".join(ch for ch in word.lower() if ch.isalpha())
    if letters.startswith(_INITIAL_SILENT):
        letters = letters[1:]
    if letters.startswith("x"):
        letters = "s" + letters[1:]
    key: list[str] = []
    for i, letter in enumerate(letters):
        if i and letter == letters[i - 1] and letter != "c":
            continue
        if letter in _VOWELS:
            if i == 0:
                key.append("A")
            continue
        key.append(_consonant_code(letters, i))
    return "".join(key)


def sounds_alike(word: str, heard: str) -> bool:
    """Whether two different words share a sound key long enough to trust."""
    if word == heard:
        return False
    key = phonetic_key(word)
    return len(key) >= _MIN_KEY_LENGTH and key == phonetic_key(heard)


# --- joins ----------------------------------------------------------------


def _joins_to(combined: str, expected: set[str], vocabulary: set[str]) -> bool:
    if combined in expected:
        return True
    return any(word in expected and sounds_alike(word, combined) for word in vocabulary)


def reconcile_joins(
    expected: Sequence[str], heard: Sequence[str], vocabulary: Iterable[str] = ()
) -> list[str]:
    """Rewrite heard tokens where Whisper joined or split words.

    "scriptcheck" is split back into "script check" when the script says
    "script check", and "SRT" into "S R T" when the script spells it out
    (up to four parts). "plug in" is joined into "plugin" when the script
    says "plugin". Two heard words are also joined when, together, they
    sound like a vocabulary word in the script ("real smith" for
    "reelsmith"); the homophone rule then decides how to report it. The
    letters must match exactly otherwise, so a dropped word stays dropped.
    """
    expected_set = set(expected)
    vocab = set(vocabulary)
    pairs = set(zip(expected, expected[1:], strict=False))
    split = _split_table(expected)
    result: list[str] = []
    index = 0
    while index < len(heard):
        word = heard[index]
        if word not in expected_set and word in split:
            result.extend(split[word])
            index += 1
            continue
        after = heard[index + 1] if index + 1 < len(heard) else None
        if (
            after is not None
            and (word, after) not in pairs
            and not (word in expected_set and after in expected_set)
            and _joins_to(word + after, expected_set, vocab)
        ):
            result.append(word + after)
            index += 2
            continue
        result.append(word)
        index += 1
    return result


def _split_table(expected: Sequence[str]) -> dict[str, tuple[str, ...]]:
    """Each run of two to four adjacent script words, keyed by its letters."""
    table: dict[str, tuple[str, ...]] = {}
    for size in range(2, _MAX_JOIN_PARTS + 1):
        for start in range(len(expected) - size + 1):
            parts = tuple(expected[start : start + size])
            table.setdefault("".join(parts), parts)
    return table


# --- comparison -----------------------------------------------------------


@dataclass(frozen=True)
class Comparison:
    """How a transcript differs from the script text.

    missing and changed are real errors. homophones are vocabulary words
    heard as a word with the same sound: worth a look, not a failure.
    """

    missing: list[str] = field(default_factory=list)
    changed: list[tuple[str, str]] = field(default_factory=list)
    homophones: list[tuple[str, str]] = field(default_factory=list)


def vocabulary_tokens(vocabulary: Iterable[str]) -> set[str]:
    return {token for entry in vocabulary for token in tokens(entry)}


def compare_text(expected: str, heard: str, vocabulary: Iterable[str] = ()) -> Comparison:
    """Diff the script text against a transcript, word by word.

    Extra heard words are ignored. A changed word is moved to homophones
    only when the script word is in the vocabulary and both words share
    a sound key.
    """
    vocab = vocabulary_tokens(vocabulary)
    expected_words = tokens(expected)
    heard_words = reconcile_joins(expected_words, tokens(heard), vocab)
    matcher = difflib.SequenceMatcher(a=expected_words, b=heard_words, autojunk=False)
    result = Comparison()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("equal", "insert"):
            continue
        expected_slice = expected_words[i1:i2]
        heard_slice = heard_words[j1:j2]
        for index, word in enumerate(expected_slice):
            if index >= len(heard_slice):
                result.missing.append(word)
            elif word in vocab and sounds_alike(word, heard_slice[index]):
                result.homophones.append((word, heard_slice[index]))
            else:
                result.changed.append((word, heard_slice[index]))
    return result


# --- vocabulary hints -----------------------------------------------------

_EDGE_PUNCTUATION = ".,;:!?\"'()[]{}"
_SENTENCE_END = (".", "!", "?", ":")
_PRONOUN_I = {"I", "I'm", "I'll", "I've", "I'd"}


def _is_uncommon(word: str, sentence_start: bool) -> bool:
    if (len(word) < 2 and not word.isdigit()) or word in _PRONOUN_I:
        return False
    if any(ch.isdigit() for ch in word) or "." in word or "_" in word:
        return True
    if any(ch.isupper() for ch in word[1:]):
        return True
    return not sentence_start and word[0].isupper()


def vocabulary_words(texts: Iterable[str]) -> list[str]:
    """Uncommon words in the script, as hints for the speech model.

    A word counts when it is capitalised in mid sentence, has a capital
    after its first letter, or has a digit, a dot or an underscore.
    Single letters and the pronoun I never count. Each
    word is listed once, in the order first seen.
    """
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        sentence_start = True
        for raw in text.split():
            word = raw.strip(_EDGE_PUNCTUATION)
            if word and _is_uncommon(word, sentence_start) and word.lower() not in seen:
                seen.add(word.lower())
                found.append(word)
            sentence_start = raw.endswith(_SENTENCE_END)
    return found


# --- say versus text ------------------------------------------------------

_SAY_MIN_SIMILARITY = 0.6


def _squash(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def say_differs_much(text: str, say: str) -> bool:
    """Whether say reads like a different sentence from text.

    Case, spacing and punctuation are ignored, so "qa" and "Q A" or
    "spec.yaml" and "spec dot yaml" are close. A low letter similarity
    means the voice may say something the captions do not.
    """
    ratio = difflib.SequenceMatcher(a=_squash(text), b=_squash(say), autojunk=False).ratio()
    return ratio < _SAY_MIN_SIMILARITY


__all__ = [
    "ABBREVIATIONS",
    "ORDINALS",
    "Comparison",
    "compare_text",
    "normalise_word",
    "number_words",
    "phonetic_key",
    "reconcile_joins",
    "say_differs_much",
    "sounds_alike",
    "tokens",
    "vocabulary_tokens",
    "vocabulary_words",
]
