"""Line icons for slide templates."""

from __future__ import annotations

from reelsmith.errors import ReelsmithError

_ICON_PATHS: dict[str, str] = {
    "bell": (
        '<path d="M5 9.5a7 7 0 0 1 14 0c0 4.5 2 6.5 2 6.5H3c0 0 2-2 2-6.5"/>'
        '<path d="M9.5 18.5a2.5 2.5 0 0 0 5 0"/>'
    ),
    "shield": '<path d="M12 3l7 2.5v6.5c0 5.5-7 8.5-7 8.5S5 17.5 5 12V5.5L12 3z"/>',
    "play": '<polygon points="9,7 17,12 9,17"/>',
    "pause": '<line x1="9" y1="7" x2="9" y2="17"/><line x1="15" y1="7" x2="15" y2="17"/>',
    "terminal": (
        '<rect x="3" y="4" width="18" height="16" rx="2"/>'
        '<path d="M7 9l3 3-3 3"/><line x1="12" y1="15" x2="17" y2="15"/>'
    ),
    "mic": (
        '<rect x="9" y="4" width="6" height="10" rx="3"/>'
        '<path d="M6 11a6 6 0 0 0 12 0"/>'
        '<line x1="12" y1="17" x2="12" y2="20"/>'
        '<line x1="8" y1="20" x2="16" y2="20"/>'
    ),
    "waveform": (
        '<line x1="4" y1="12" x2="4" y2="12"/>'
        '<line x1="7" y1="9" x2="7" y2="15"/>'
        '<line x1="10" y1="6" x2="10" y2="18"/>'
        '<line x1="13" y1="8" x2="13" y2="16"/>'
        '<line x1="16" y1="5" x2="16" y2="19"/>'
        '<line x1="19" y1="10" x2="19" y2="14"/>'
    ),
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "cross": '<path d="M7 7l10 10M17 7L7 17"/>',
    "film": (
        '<rect x="3" y="5" width="18" height="14" rx="1"/>'
        '<line x1="7" y1="5" x2="7" y2="19"/>'
        '<line x1="17" y1="5" x2="17" y2="19"/>'
        '<line x1="3" y1="9" x2="7" y2="9"/>'
        '<line x1="3" y1="15" x2="7" y2="15"/>'
        '<line x1="17" y1="9" x2="20" y2="9"/>'
        '<line x1="17" y1="15" x2="20" y2="15"/>'
    ),
    "folder": (
        '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>'
    ),
    "file": (
        '<path d="M8 3h6l5 5v13a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>'
        '<path d="M14 3v5h5"/>'
    ),
    "cursor": '<path d="M5 4l14 8-6 1.5L10 20 8.5 14 5 4z"/>',
    "phone": (
        '<path d="M8 4h8a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/>'
        '<line x1="10" y1="18" x2="14" y2="18"/>'
    ),
    "browser": (
        '<rect x="3" y="5" width="18" height="14" rx="2"/>'
        '<line x1="3" y1="9" x2="21" y2="9"/>'
        '<circle cx="6" cy="7" r="0.75" fill="currentColor" stroke="none"/>'
        '<circle cx="8.5" cy="7" r="0.75" fill="currentColor" stroke="none"/>'
        '<circle cx="11" cy="7" r="0.75" fill="currentColor" stroke="none"/>'
    ),
    "chip": (
        '<rect x="7" y="7" width="10" height="10" rx="1"/>'
        '<line x1="9" y1="7" x2="9" y2="5"/><line x1="12" y1="7" x2="12" y2="5"/>'
        '<line x1="15" y1="7" x2="15" y2="5"/>'
        '<line x1="9" y1="17" x2="9" y2="19"/><line x1="12" y1="17" x2="12" y2="19"/>'
        '<line x1="15" y1="17" x2="15" y2="19"/>'
        '<line x1="7" y1="9" x2="5" y2="9"/><line x1="7" y1="12" x2="5" y2="12"/>'
        '<line x1="7" y1="15" x2="5" y2="15"/>'
        '<line x1="17" y1="9" x2="19" y2="9"/><line x1="17" y1="12" x2="19" y2="12"/>'
        '<line x1="17" y1="15" x2="19" y2="15"/>'
    ),
    "gear": (
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M12 3v2M12 19v2M3 12h2M19 12h2"/>'
        '<path d="M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4l1.4-1.4M17 7l1.4-1.4"/>'
    ),
    "eye": (
        '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z"/>'
        '<circle cx="12" cy="12" r="2.5"/>'
    ),
    "lock": (
        '<rect x="6" y="10" width="12" height="10" rx="2"/><path d="M8 10V8a4 4 0 0 1 8 0v2"/>'
    ),
    "sparkle": (
        '<path d="M8 4C9 7 10.5 10 12 12C10.5 14 9 17 8 20'
        'C7 17 5.5 14 4 12C5.5 10 7 7 8 4z"/>'
        '<path d="M18 5.5C18.5 6.5 19.2 7 19.8 7.2C19.2 7.4 18.5 7.9 18 8.8'
        'C17.5 7.9 16.8 7.4 16.2 7.2C16.8 7 17.5 6.5 18 5.5z"/>'
    ),
    "clock": ('<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>'),
    "layers": ('<path d="M12 4l9 5-9 5-9-5 9-5z"/><path d="M3 14l9 5 9-5"/>'),
    "git-branch": (
        '<circle cx="7" cy="6" r="2"/>'
        '<circle cx="7" cy="18" r="2"/>'
        '<circle cx="17" cy="12" r="2"/>'
        '<path d="M7 8v8M7 12h7"/>'
    ),
    "plug": (
        '<line x1="9" y1="3" x2="9" y2="8"/>'
        '<line x1="15" y1="3" x2="15" y2="8"/>'
        '<rect x="6.5" y="8" width="11" height="8" rx="3"/>'
        '<path d="M12 16v2.5"/>'
        '<path d="M9.5 18.5c0 0 1.2 2 2.5 2s2.5-2 2.5-2"/>'
    ),
    "chat": (
        '<path d="M4 5h16a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H9l-4 4V6a1 1 0 0 1 1-1z"/>'
        '<line x1="8" y1="10" x2="16" y2="10"/>'
        '<line x1="8" y1="13" x2="13" y2="13"/>'
    ),
    "flow": (
        '<rect x="3" y="4" width="6" height="6" rx="1"/>'
        '<rect x="15" y="14" width="6" height="6" rx="1"/>'
        '<path d="M9 7h6v7"/>'
    ),
    "ruler": (
        '<path d="M4 16l12-12 4 4L8 20 4 16z"/>'
        '<line x1="9" y1="11" x2="11" y2="9"/>'
        '<line x1="12" y1="14" x2="14" y2="12"/>'
        '<line x1="15" y1="17" x2="17" y2="15"/>'
    ),
    "scissors": (
        '<circle cx="7" cy="7" r="2"/>'
        '<circle cx="7" cy="17" r="2"/>'
        '<path d="M9 8.5l11 7M9 15.5l11-7"/>'
    ),
    "image": (
        '<rect x="4" y="4" width="16" height="16" rx="2"/>'
        '<circle cx="9" cy="9" r="1.5"/>'
        '<path d="M4 16l5-5 4 4 3-3 4 4"/>'
    ),
    "globe": (
        '<circle cx="12" cy="12" r="8"/>'
        '<path d="M4 12h16"/>'
        '<path d="M12 4a12 12 0 0 1 0 16"/>'
        '<path d="M12 4a12 12 0 0 0 0 16"/>'
    ),
    "user": ('<circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-3.5 3-6 7-6s7 2.5 7 6"/>'),
    "bolt": '<path d="M13 3L5 14h6l-1 7 9-12h-6l1-6z"/>',
}

ICON_NAMES: tuple[str, ...] = tuple(sorted(_ICON_PATHS.keys()))


def icon_svg(
    name: str,
    size: int = 32,
    color: str = "currentColor",
    stroke: float = 1.75,
) -> str:
    """Return a self-contained SVG string for a named line icon."""
    paths = _ICON_PATHS.get(name)
    if paths is None:
        available = ", ".join(ICON_NAMES)
        raise ReelsmithError(f"Unknown icon '{name}'. Available icons: {available}")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke}" '
        f'stroke-linecap="round" stroke-linejoin="round">{paths}</svg>'
    )
