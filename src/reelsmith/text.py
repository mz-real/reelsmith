"""Shared text normalisation: British and American spelling variants.

Kokoro reads British spelling correctly, for example "favourites",
"colour" or "organise". Whisper often writes the American form instead.
Comparing a transcript to the script text word for word would then
report a word that was spoken correctly as missing or changed.

normalise_word maps both spellings of a word to the same canonical
form, so a word for word comparison is spelling-blind. It is meant to
run on a single lowercase token with punctuation already stripped.
"""

from __future__ import annotations

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


__all__ = ["normalise_word"]
