"""Browser and phone frames, drawn with Pillow at the exact size needed.

Nothing is downloaded and no product artwork is copied: every shape is
drawn here from plain rectangles, circles and lines. Shapes are drawn at
a larger size and scaled down, so curves have smooth edges.

A frame is three images:
- the frame itself, laid over the footage, with a clear hole for the screen;
- an underlay (soft shadow, phone side buttons) laid under the footage;
- a mask that rounds the corners of the footage to match the screen.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter

from reelsmith.compose.captions import find_font
from reelsmith.compose.layouts import FRAME_INSETS, FrameKind, Size
from reelsmith.compose.typeface import find_faces

SUPERSAMPLE = 3
TRAFFIC_LIGHTS = ("#ff5f57", "#febc2e", "#28c840")
BROWSER_RADIUS = 14  # at 1080p
FULL_RADIUS = 18  # rounded corners of bare footage, at 1080p
PHONE_SCREEN_SHARE = 0.115  # screen corner radius as a share of its width
UNDERLAY_PAD = 90  # room around the frame for the shadow, at 1080p

Rect = tuple[float, float, float, float]


def _insets(kind: FrameKind, unit: float) -> tuple[int, int, int, int]:
    left, top, right, bottom = (round(v * unit) for v in FRAME_INSETS[kind])
    return left, top, right, bottom


def screen_radius(kind: FrameKind | None, screen: Size, unit: float) -> int:
    """Corner radius of the footage inside a frame, or of bare footage."""
    if kind == "phone":
        return max(2, round(screen.width * PHONE_SCREEN_SHARE))
    if kind == "browser":
        return max(1, round((BROWSER_RADIUS - FRAME_INSETS["browser"][0]) * unit))
    return max(2, round(FULL_RADIUS * unit))


def _outer_radius(kind: FrameKind, outer: Size, unit: float) -> int:
    left, top, right, _ = _insets(kind, unit)
    if kind == "phone":
        screen = Size(outer.width - left - right, outer.height)
        return screen_radius("phone", screen, unit) + left
    return max(2, round(BROWSER_RADIUS * unit))


def draw_frame(kind: FrameKind, outer: Size, unit: float, *, dark: bool, dest: Path) -> Path:
    """Draw a frame of size outer whose hole matches FRAME_INSETS."""
    image = _browser(outer, unit, dark) if kind == "browser" else _phone(outer, unit)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest)
    return dest


def _scaled(rect: Rect, s: int) -> Rect:
    return (rect[0] * s, rect[1] * s, rect[2] * s - 1, rect[3] * s - 1)


def _down(image: Image.Image, size: Size) -> Image.Image:
    return image.resize((size.width, size.height), Image.Resampling.LANCZOS)


def _vertical(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
    """A top to bottom gradient between two colours."""
    start = Image.new("RGBA", size, top)
    end = Image.new("RGBA", size, bottom)
    ramp = Image.linear_gradient("L").resize(size)
    return Image.composite(end, start, ramp)


def _phone(outer: Size, unit: float) -> Image.Image:
    s = SUPERSAMPLE
    w, h = outer.width * s, outer.height * s
    left, top, right, bottom = _insets("phone", unit)
    radius = _outer_radius("phone", outer, unit) * s
    screen_w = outer.width - left - right
    hole_radius = screen_radius("phone", Size(screen_w, outer.height), unit) * s
    rim = max(s, round(3.2 * unit * s))
    body = Image.new("L", (w, h), 0)
    ImageDraw.Draw(body).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    metal = _vertical((w, h), "#5b616c", "#2b2f37")
    image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    image.paste(metal, (0, 0), body)
    ImageDraw.Draw(image).rounded_rectangle(
        (rim, rim, w - 1 - rim, h - 1 - rim), radius - rim, fill=(6, 7, 9, 255)
    )
    # A faint highlight just inside the metal edge.
    shine = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(shine).rounded_rectangle(
        (rim // 2, rim // 2, w - 1 - rim // 2, h - 1 - rim // 2),
        radius - rim // 2,
        outline=(255, 255, 255, 46),
        width=max(1, s // 2 + 1),
    )
    image.alpha_composite(shine)
    hole = Image.new("L", (w, h), 0)
    hole_box = _scaled((left, top, outer.width - right, outer.height - bottom), s)
    ImageDraw.Draw(hole).rounded_rectangle(hole_box, hole_radius, fill=255)
    image.putalpha(ImageChops.subtract(image.getchannel("A"), hole))
    _island(ImageDraw.Draw(image), hole_box, s)
    return _down(image, outer)


def _island(draw: ImageDraw.ImageDraw, screen: Rect, s: int) -> None:
    """A black pill at the top of the screen, with a small camera lens."""
    x0, y0, x1, _ = screen
    width = x1 - x0
    pill_w, pill_h = width * 0.30, width * 0.085
    cx = (x0 + x1) / 2
    top = y0 + width * 0.032
    draw.rounded_rectangle(
        (cx - pill_w / 2, top, cx + pill_w / 2, top + pill_h), pill_h / 2, fill=(0, 0, 0, 255)
    )
    lens = pill_h * 0.22
    lx, ly = cx + pill_w / 2 - pill_h * 0.5, top + pill_h / 2
    draw.ellipse((lx - lens, ly - lens, lx + lens, ly + lens), fill=(16, 22, 38, 255))
    glint = lens * 0.35
    draw.ellipse(
        (lx - glint, ly - lens * 0.5 - glint / 2, lx + glint * 0.3, ly - lens * 0.5 + glint / 2),
        fill=(70, 90, 140, 180),
    )


def _browser(outer: Size, unit: float, dark: bool) -> Image.Image:
    s = SUPERSAMPLE
    w, h = outer.width * s, outer.height * s
    left, top, right, bottom = _insets("browser", unit)
    radius = _outer_radius("browser", outer, unit) * s
    bar_top, bar_bottom = ("#262b35", "#1d212a") if dark else ("#f4f5f7", "#e6e8ec")
    border = (255, 255, 255, 30) if dark else (0, 0, 0, 40)
    shape = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shape).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    image.paste(_vertical((w, h), bar_top, bar_bottom), (0, 0), shape)
    hole = Image.new("L", (w, h), 0)
    hole_box = _scaled((left, top, outer.width - right, outer.height - bottom), s)
    inner_radius = screen_radius("browser", outer, unit) * s
    ImageDraw.Draw(hole).rounded_rectangle(
        hole_box, inner_radius, fill=255, corners=(False, False, True, True)
    )
    image.putalpha(ImageChops.subtract(image.getchannel("A"), hole))
    deco = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(deco)
    line = max(1, round(unit * s))
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius, outline=border, width=line)
    if dark:
        draw.line((radius, line, w - radius, line), fill=(255, 255, 255, 22), width=line)
    sep = top * s - line
    draw.line(
        (line, sep, w - line, sep), fill=(0, 0, 0, 110) if dark else (0, 0, 0, 30), width=line
    )
    _title_bar(draw, w, top * s, unit * s, dark)
    image.alpha_composite(deco)
    return _down(image, outer)


def _title_bar(draw: ImageDraw.ImageDraw, width: int, bar: int, u: float, dark: bool) -> None:
    mid = bar / 2
    dot = 6.2 * u
    for number, color in enumerate(TRAFFIC_LIGHTS):
        cx = (22 + 20 * number) * u
        draw.ellipse((cx - dot, mid - dot, cx + dot, mid + dot), fill=color)
        draw.ellipse(
            (cx - dot, mid - dot, cx + dot, mid + dot),
            outline=(0, 0, 0, 50),
            width=max(1, round(u)),
        )
    muted = (255, 255, 255, 80) if dark else (0, 0, 0, 90)
    stroke = max(1, round(1.8 * u))
    for number, sign in enumerate((-1, 1)):
        cx = (96 + 24 * number) * u
        arm = 5 * u
        tip = cx + sign * arm / 2
        draw.line(
            [(tip - sign * arm, mid - arm), (tip, mid), (tip - sign * arm, mid + arm)],
            fill=muted if number == 0 else (muted[0], muted[1], muted[2], muted[3] * 2 // 3),
            width=stroke,
            joint="curve",
        )
    pill_w = min(width * 0.44, 560 * u)
    pill_h = 28 * u
    x0 = (width - pill_w) / 2
    fill = (255, 255, 255, 16) if dark else (0, 0, 0, 14)
    draw.rounded_rectangle((x0, mid - pill_h / 2, x0 + pill_w, mid + pill_h / 2), 8 * u, fill=fill)
    _lock(draw, x0 + 14 * u, mid, u, muted)
    for number, length in enumerate((0.34, 0.12)):
        start = x0 + 30 * u + number * (pill_w * 0.36 + 6 * u)
        draw.rounded_rectangle(
            (start, mid - 2.5 * u, start + pill_w * length, mid + 2.5 * u),
            2.5 * u,
            fill=(muted[0], muted[1], muted[2], muted[3] // (2 + number)),
        )


def _lock(
    draw: ImageDraw.ImageDraw, x: float, mid: float, u: float, color: tuple[int, int, int, int]
) -> None:
    body_w, body_h = 9 * u, 7 * u
    draw.rounded_rectangle(
        (x - body_w / 2, mid - body_h / 2 + 2 * u, x + body_w / 2, mid + body_h / 2 + 2 * u),
        1.5 * u,
        fill=color,
    )
    arc = 3.2 * u
    draw.arc(
        (x - arc, mid - arc - 3.2 * u, x + arc, mid + arc - 3.2 * u),
        180,
        360,
        fill=color,
        width=max(1, round(1.5 * u)),
    )


def draw_underlay(kind: FrameKind | None, outer: Size, unit: float, dest: Path) -> tuple[Path, int]:
    """A soft shadow (and phone side buttons) for under a frame of size outer.

    Returns the image and how far it reaches past the frame on each side.
    """
    pad = max(4, round(UNDERLAY_PAD * unit))
    s = 2
    size = ((outer.width + 2 * pad) // s, (outer.height + 2 * pad) // s)
    if kind is None:
        radius = screen_radius(None, outer, unit)
    else:
        radius = _outer_radius(kind, outer, unit)
    shadow = Image.new("L", size, 0)
    draw = ImageDraw.Draw(shadow)
    drop = 22 * unit / s
    box = (pad / s, pad / s + drop, (pad + outer.width) / s, (pad + outer.height) / s + drop)
    draw.rounded_rectangle(box, radius / s, fill=150)
    wide = shadow.filter(ImageFilter.GaussianBlur(34 * unit / s))
    tight = Image.new("L", size, 0)
    near = (box[0], box[1] - drop * 0.7, box[2], box[3] - drop * 0.7)
    ImageDraw.Draw(tight).rounded_rectangle(near, radius / s, fill=110)
    tight = tight.filter(ImageFilter.GaussianBlur(7 * unit / s))
    alpha = ImageChops.add(wide, tight)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    image.putalpha(alpha)
    image = image.resize((outer.width + 2 * pad, outer.height + 2 * pad), Image.Resampling.BICUBIC)
    if kind == "phone":
        _buttons(image, outer, pad, unit)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest)
    return dest, pad


def _buttons(image: Image.Image, outer: Size, pad: int, unit: float) -> None:
    """Volume and power keys that peek out from the sides of the phone."""
    s = SUPERSAMPLE
    layer = Image.new("RGBA", (image.width * s, image.height * s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    depth = 3.2 * unit * s
    keys = [("left", 0.17, 0.035), ("left", 0.24, 0.065), ("left", 0.32, 0.065)]
    keys.append(("right", 0.27, 0.10))
    for side, at, length in keys:
        y0 = (pad + outer.height * at) * s
        y1 = y0 + outer.height * length * s
        if side == "left":
            x0, x1 = pad * s - depth, pad * s + depth
        else:
            x0, x1 = (pad + outer.width) * s - depth, (pad + outer.width) * s + depth
        draw.rounded_rectangle((x0, y0, x1, y1), depth, fill=(64, 69, 79, 255))
    small = layer.resize(image.size, Image.Resampling.LANCZOS)
    image.alpha_composite(small)


def draw_mask(kind: FrameKind | None, screen: Size, unit: float, dest: Path) -> Path:
    """A grey mask the size of the footage: white shows, black is cut away."""
    s = SUPERSAMPLE
    radius = screen_radius(kind, screen, unit) * s
    mask = Image.new("L", (screen.width * s, screen.height * s), 0)
    corners = (False, False, True, True) if kind == "browser" else None
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, screen.width * s - 1, screen.height * s - 1), radius, fill=255, corners=corners
    )
    small = mask.resize((screen.width, screen.height), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    small.save(dest)
    return dest


def top_colour(video: Path, dest: Path) -> str:
    """The app's own colour along the top of the footage, or white if unknown."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-frames:v", "1", str(dest)],
            check=True,
            capture_output=True,
        )
        with Image.open(dest) as image:
            rgb = image.convert("RGB")
            strip = rgb.crop((0, 0, rgb.width, max(1, rgb.height // 200)))
            pixels = list(strip.tobytes())
    except (OSError, subprocess.CalledProcessError):
        return "#ffffff"
    triples = [tuple(pixels[i : i + 3]) for i in range(0, len(pixels) - 2, 3)]
    if not triples:
        return "#ffffff"
    red, green, blue = max(set(triples), key=triples.count)
    return f"#{red:02x}{green:02x}{blue:02x}"


def draw_status_bar(size: Size, colour: str, unit: float, dest: Path) -> Path:
    """A phone status bar on the app colour: the time on the left, and signal,
    wifi and battery glyphs on the right, either side of the island."""
    s = SUPERSAMPLE
    w, h = size.width * s, size.height * s
    image = Image.new("RGB", (w, h), colour)
    red, green, blue = ImageColor.getrgb(colour)[:3]
    light = (0.299 * red + 0.587 * green + 0.114 * blue) > 140
    ink = (0, 0, 0) if light else (255, 255, 255)
    draw = ImageDraw.Draw(image)
    width = size.width * s
    cy = min(h * 0.62, width * 0.0745)
    font_size = max(6, round(width * 0.042))
    face = find_faces([], find_font([])).bold
    font = face.load(font_size)
    draw.text((width * 0.175, cy), "9:41", font=font, fill=ink, anchor="mm")
    glyph = width * 0.04  # glyph height
    x = width * 0.705
    _signal(draw, x, cy, glyph, ink)
    _wifi(draw, x + glyph * 1.6, cy, glyph, ink)
    _battery(draw, x + glyph * 3.3, cy, glyph, ink)
    small = image.resize((size.width, size.height), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    small.save(dest)
    return dest


Ink = tuple[int, int, int]


def _signal(draw: ImageDraw.ImageDraw, x: float, cy: float, h: float, ink: Ink) -> None:
    bar = h * 0.22
    for number in range(4):
        top = cy + h / 2 - h * (0.35 + 0.65 * number / 3)
        left = x + number * bar * 1.4
        draw.rounded_rectangle((left, top, left + bar, cy + h / 2), bar * 0.3, fill=ink)


def _wifi(draw: ImageDraw.ImageDraw, x: float, cy: float, h: float, ink: Ink) -> None:
    cx = x + h * 0.7
    bottom = cy + h / 2
    stroke = max(1, round(h * 0.16))
    for radius in (h * 0.95, h * 0.62):
        draw.arc(
            (cx - radius, bottom - radius, cx + radius, bottom + radius), 225, 315,
            fill=ink, width=stroke,
        )  # fmt: skip
    dot = h * 0.3
    draw.pieslice((cx - dot, bottom - dot, cx + dot, bottom + dot), 225, 315, fill=ink)


def _battery(draw: ImageDraw.ImageDraw, x: float, cy: float, h: float, ink: Ink) -> None:
    body_w, body_h = h * 1.9, h * 0.9
    top = cy - body_h / 2
    line = max(1, round(h * 0.09))
    draw.rounded_rectangle(
        (x, top, x + body_w, top + body_h), body_h * 0.28, outline=ink, width=line
    )
    pad = line * 2
    draw.rounded_rectangle(
        (x + pad, top + pad, x + body_w * 0.8, top + body_h - pad), body_h * 0.16, fill=ink
    )
    nub = h * 0.12
    draw.rounded_rectangle(
        (x + body_w + line, cy - body_h * 0.18, x + body_w + line + nub, cy + body_h * 0.18),
        nub / 2,
        fill=ink,
    )
