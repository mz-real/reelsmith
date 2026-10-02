"""Import a screen recording and normalise it for reelsmith."""

from __future__ import annotations

from pathlib import Path

from reelsmith.errors import ReelsmithError
from reelsmith.fsutil import backup_existing
from reelsmith.media.ffmpeg import MediaInfo, probe, run_ffmpeg
from reelsmith.models import ClipModel, save_model

TARGET_FPS = 30.0


def _rotation_filter(degrees: int) -> str | None:
    if degrees == 90:
        return "transpose=1"
    if degrees == 180:
        return "hflip,vflip"
    if degrees == 270:
        return "transpose=2"
    return None


def _video_filters(info: MediaInfo) -> str:
    parts: list[str] = []
    rotate = _rotation_filter(info.rotation)
    if rotate is not None:
        parts.append(rotate)
    parts.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
    parts.append(f"fps={TARGET_FPS:g}")
    return ",".join(parts)


def import_recording(source: Path, clip_id: str, clips_root: Path) -> ClipModel:
    """Normalise a file into clips/<id>/video.mp4 and clip.json with no events."""
    source = source.resolve()
    if not source.is_file():
        raise ReelsmithError(f"{source} not found")

    info = probe(source)
    clip_dir = clips_root / clip_id
    clip_dir.mkdir(parents=True, exist_ok=True)
    video_path = clip_dir / "video.mp4"
    backup_existing(video_path)

    vf = _video_filters(info)
    args: list[str] = ["-noautorotate", "-i", str(source)]
    if not info.has_audio:
        args.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]
        )
    args.extend(["-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p"])
    if info.has_audio:
        args.extend(["-c:a", "aac", "-b:a", "128k"])
    else:
        args.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:a",
                "aac",
                "-shortest",
            ]
        )
    args.append(str(video_path))
    run_ffmpeg(args)

    out = probe(video_path)
    clip = ClipModel(
        id=clip_id,
        video="video.mp4",
        width=out.width,
        height=out.height,
        fps=out.fps,
        duration=out.duration,
        events=[],
    )
    save_model(clip_dir / "clip.json", clip)
    return clip
