"""Progress lines for long steps, written to stderr.

The result block goes to stdout and stays last and clean. Progress is shown
only when stderr is a terminal, or when `reelsmith --progress` forces it.
On a terminal one line is rewritten in place; otherwise each update is its
own line.
"""

from __future__ import annotations

import sys

_forced = False
_last_tenth: dict[str, int] = {}


def configure(*, force: bool) -> None:
    """Force progress on even when stderr is not a terminal."""
    global _forced
    _forced = force


def reset() -> None:
    """Back to the default: progress only on a terminal."""
    global _forced
    _forced = False
    _last_tenth.clear()


def _is_tty() -> bool:
    isatty = getattr(sys.stderr, "isatty", None)
    return bool(isatty and isatty())


def enabled() -> bool:
    return _forced or _is_tty()


def _write(text: str, *, finished: bool) -> None:
    stream = sys.stderr
    if _is_tty():
        stream.write("\r\x1b[K" + text + ("\n" if finished else ""))
    else:
        stream.write(text + "\n")
    stream.flush()


def count(label: str, done: int, total: int, item: str | None = None) -> None:
    """Report item done of total, for example `Voice line 3/34: intro/l1`."""
    if not enabled():
        return
    text = f"{label} {done}/{total}"
    if item:
        text += f": {item}"
    _write(text, finished=done >= total)


def transfer(label: str, done: int, total: int) -> None:
    """Report bytes done of total in megabytes, for downloads."""
    if not enabled():
        return
    finished = total > 0 and done >= total
    if not _is_tty():
        # Off a terminal, one line per tenth is plenty.
        tenth = (done * 10 // total) if total > 0 else 0
        if not finished and _last_tenth.get(label) == tenth:
            return
        _last_tenth[label] = tenth
    mb = 1024 * 1024
    text = f"{label} {done / mb:.1f}/{total / mb:.1f} MB"
    _write(text, finished=finished)
    if finished:
        _last_tenth.pop(label, None)
