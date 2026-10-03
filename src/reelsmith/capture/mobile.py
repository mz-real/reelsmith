"""Record a Maestro mobile flow with our own screen capture."""

from __future__ import annotations

import json
import platform
import shutil
import signal
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from reelsmith.capture.importer import import_recording
from reelsmith.doctor.checks import check_adb, check_java, check_maestro, check_simctl
from reelsmith.errors import ReelsmithError
from reelsmith.media.ffmpeg import require_ffmpeg
from reelsmith.models import ClipModel, Event, save_model
from reelsmith.models.clip import EventType
from reelsmith.result import Status

Platform = Literal["ios", "android"]
ANDROID_REMOTE_VIDEO = "/sdcard/reelsmith.mp4"
ANDROID_RECORD_BITRATE = "8000000"
ANDROID_RECORD_LIMIT_SEC = 180.0
RECORDER_STOP_TIMEOUT_SEC = 120.0

MaestroTiming = tuple[float, float, float]


@dataclass
class MobileCaptureResult:
    clip: ClipModel
    warnings: list[str] = field(default_factory=list)


def subprocess_runner(
    args: list[str],
    *,
    background: bool = False,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str] | subprocess.Popen[Any]:
    """Run a subprocess. Set background=True to return a Popen handle."""
    if background:
        return subprocess.Popen(args, **kwargs)
    capture = kwargs.pop("capture_output", True)
    text = kwargs.pop("text", True)
    check = kwargs.pop("check", False)
    completed = subprocess.run(
        args,
        capture_output=capture,
        text=text,
        check=False,
        **kwargs,
    )
    if check and completed.returncode != 0:
        stderr = completed.stderr if isinstance(completed.stderr, str) else ""
        stdout = completed.stdout if isinstance(completed.stdout, str) else ""
        detail = stderr.strip() or stdout.strip() or f"exit code {completed.returncode}"
        raise ReelsmithError(f"Command failed: {' '.join(args)}\n{detail}")
    return completed


def require_mobile_tools(target: Platform) -> None:
    """Raise ReelsmithError when a required tool is missing."""
    require_ffmpeg()
    java = check_java()
    if java.status != Status.OK:
        raise ReelsmithError(f"Java: {java.found}", fix=java.fix)
    maestro = check_maestro()
    if maestro.status != Status.OK:
        raise ReelsmithError(f"Maestro: {maestro.found}", fix=maestro.fix)

    if target == "ios":
        if platform.system() != "Darwin":
            raise ReelsmithError(
                "iOS mobile capture only works on macOS.",
                fix="Use --platform android on this system.",
            )
        simctl = check_simctl()
        if simctl.status != Status.OK:
            raise ReelsmithError(f"iOS simulator tools: {simctl.found}", fix=simctl.fix)
    else:
        adb = check_adb()
        if adb.status != Status.OK:
            raise ReelsmithError(f"adb: {adb.found}", fix=adb.fix)


def _booted_simulators() -> list[tuple[str, str]]:
    """(udid, name) of every booted iOS simulator."""
    completed = subprocess_runner(
        ["xcrun", "simctl", "list", "devices", "booted", "-j"], check=True
    )
    stdout = completed.stdout if isinstance(completed.stdout, str) else ""
    try:
        runtimes = json.loads(stdout).get("devices", {})
    except json.JSONDecodeError:
        return []
    return [
        (str(device["udid"]), str(device.get("name", "")))
        for devices in runtimes.values()
        for device in devices
        if device.get("state") == "Booted"
    ]


def _android_devices() -> list[str]:
    """Serials of every Android device or emulator adb can use."""
    completed = subprocess_runner(["adb", "devices"], check=True)
    stdout = completed.stdout if isinstance(completed.stdout, str) else ""
    serials: list[str] = []
    for line in stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials


def resolve_device(target: Platform, device: str | None) -> str:
    """The one simulator or device to record, so Maestro never picks another.

    Maestro drives whichever device it finds first. With an iOS simulator and
    an Android emulator both running, a flow meant for one would run on the
    other, so the device is always named explicitly.
    """
    if device:
        return device
    if target == "ios":
        booted = _booted_simulators()
        if not booted:
            raise ReelsmithError(
                "No iOS simulator is booted.",
                fix="Open the Simulator app and boot a device, then run the command again.",
            )
        if len(booted) > 1:
            names = ", ".join(f"{name} ({udid})" for udid, name in booted)
            raise ReelsmithError(
                f"More than one iOS simulator is booted: {names}.",
                fix="Pick one with --device <udid>, or shut down the others.",
            )
        return booted[0][0]
    serials = _android_devices()
    if not serials:
        raise ReelsmithError(
            "adb sees no Android device or emulator.",
            fix="Start an emulator, or plug in the phone with USB debugging on.",
        )
    if len(serials) > 1:
        raise ReelsmithError(
            f"More than one Android device is connected: {', '.join(serials)}.",
            fix="Pick one with --device <serial>.",
        )
    return serials[0]


def ios_record_command(output: Path, udid: str = "booted") -> list[str]:
    return [
        "xcrun",
        "simctl",
        "io",
        udid,
        "recordVideo",
        "--codec=h264",
        "--force",
        str(output),
    ]


def android_record_command(device: str | None) -> list[str]:
    prefix = ["adb"]
    if device:
        prefix.extend(["-s", device])
    return [
        *prefix,
        "shell",
        "screenrecord",
        "--bit-rate",
        ANDROID_RECORD_BITRATE,
        ANDROID_REMOTE_VIDEO,
    ]


def android_stop_record_command(device: str | None) -> list[str]:
    prefix = ["adb"]
    if device:
        prefix.extend(["-s", device])
    return [*prefix, "shell", "pkill", "-INT", "screenrecord"]


def android_pull_command(device: str | None, dest: Path) -> list[str]:
    prefix = ["adb"]
    if device:
        prefix.extend(["-s", device])
    return [*prefix, "pull", ANDROID_REMOTE_VIDEO, str(dest)]


def android_rm_remote_command(device: str | None) -> list[str]:
    prefix = ["adb"]
    if device:
        prefix.extend(["-s", device])
    return [*prefix, "shell", "rm", "-f", ANDROID_REMOTE_VIDEO]


def maestro_test_command(
    flow_path: Path,
    *,
    junit_path: Path,
    debug_dir: Path,
    device: str | None = None,
) -> list[str]:
    target = ["--device", device] if device else []
    return [
        "maestro",
        *target,
        "test",
        str(flow_path),
        "--format",
        "junit",
        "--output",
        str(junit_path),
        "--debug-output",
        str(debug_dir),
        "--flatten-debug-output",
    ]


def _selector_label(selector: dict[str, Any]) -> str:
    for key in ("text", "id", "textRegex", "description"):
        value = selector.get(key)
        if value:
            return str(value)
    return "tap"


def _parse_percent_pair(raw: str) -> tuple[float, float] | None:
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 2:
        return None
    xs: list[float] = []
    for part in parts:
        if part.endswith("%"):
            try:
                xs.append(float(part[:-1]) / 100.0)
            except ValueError:
                return None
        else:
            return None
    return min(1.0, max(0.0, xs[0])), min(1.0, max(0.0, xs[1]))


def _parse_pixel_pair(raw: str, width: int, height: int) -> tuple[float, float] | None:
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 2:
        return None
    try:
        x_px = float(parts[0])
        y_px = float(parts[1])
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return (
        min(1.0, max(0.0, x_px / width)),
        min(1.0, max(0.0, y_px / height)),
    )


def _event_time(
    metadata: dict[str, Any],
    *,
    recorder_mono: float,
    maestro_timing: MaestroTiming,
    at_end: bool = False,
) -> float | None:
    """Seconds into the recording for a Maestro command.

    `timestamp` is when the command started. A tap first looks for its
    element, which can take seconds, and only then taps, so with at_end the
    time is when the command finished, which is when the screen changed.
    """
    timestamp = metadata.get("timestamp")
    if not isinstance(timestamp, (int, float)):
        return None
    duration = metadata.get("duration")
    if at_end and isinstance(duration, (int, float)):
        timestamp = float(timestamp) + float(duration)
    maestro_wall0, maestro_mono0, _ = maestro_timing
    wall_t = float(timestamp) / 1000.0
    mono_t = (wall_t - maestro_wall0) + maestro_mono0
    return max(0.0, mono_t - recorder_mono)


def _command_entry(
    command: dict[str, Any],
    *,
    width: int,
    height: int,
) -> tuple[EventType, str | None, float | None, float | None] | None:
    """Return event type, label, x, y for one Maestro command object."""
    if "tapOnElement" in command:
        body = command["tapOnElement"]
        if not isinstance(body, dict):
            return None
        label = body.get("label") or _selector_label(body.get("selector", {}))
        rel = body.get("relativePoint")
        if isinstance(rel, str):
            pair = _parse_percent_pair(rel)
            if pair is not None:
                return "tap", str(label), pair[0], pair[1]
        return "screen", str(label), None, None

    if "tapOnPointV2Command" in command:
        body = command["tapOnPointV2Command"]
        if not isinstance(body, dict):
            return None
        label = body.get("label") or "tap"
        point = body.get("point")
        if isinstance(point, str):
            pair = _parse_percent_pair(point) or _parse_pixel_pair(point, width, height)
            if pair is not None:
                return "tap", str(label), pair[0], pair[1]
        return "screen", str(label), None, None

    if "tapOnPoint" in command:
        body = command["tapOnPoint"]
        if not isinstance(body, dict):
            return None
        label = body.get("label") or "tap"
        try:
            x_px = int(body["x"])
            y_px = int(body["y"])
        except (KeyError, TypeError, ValueError):
            return "screen", str(label), None, None
        if width > 0 and height > 0:
            return (
                "tap",
                str(label),
                min(1.0, max(0.0, x_px / width)),
                min(1.0, max(0.0, y_px / height)),
            )
        return "screen", str(label), None, None

    if "backPressCommand" in command:
        body = command["backPressCommand"]
        label = "Back"
        if isinstance(body, dict) and body.get("label"):
            label = str(body["label"])
        return "back", label, None, None

    if "pressKeyCommand" in command:
        body = command["pressKeyCommand"]
        if not isinstance(body, dict):
            return None
        key = str(body.get("key", "key"))
        label = body.get("label") or key
        if key.lower() == "back":
            return "back", str(label), None, None
        return "key", str(label), None, None

    if "inputTextCommand" in command:
        body = command["inputTextCommand"]
        if not isinstance(body, dict):
            return None
        text = str(body.get("text", "input"))
        return "key", text, None, None

    if "swipeCommand" in command or "scrollCommand" in command:
        key = "swipeCommand" if "swipeCommand" in command else "scrollCommand"
        body = command[key]
        label = "scroll"
        if isinstance(body, dict) and body.get("label"):
            label = str(body["label"])
        return "scroll", label, None, None

    return None


def parse_maestro_commands(
    payload: list[Any],
    *,
    width: int,
    height: int,
    recorder_mono: float,
    maestro_timing: MaestroTiming,
) -> list[Event]:
    """Turn Maestro commands JSON into clip events."""
    events: list[Event] = []
    counter = 0
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        command = entry.get("command")
        metadata = entry.get("metadata")
        if not isinstance(command, dict) or not isinstance(metadata, dict):
            continue
        status = metadata.get("status")
        # WARNED is an optional step that did not run (its element never
        # appeared), so nothing happened on screen.
        if status in ("FAILED", "WARNED", "SKIPPED"):
            continue
        parsed = _command_entry(command, width=width, height=height)
        if parsed is None:
            continue
        event_type, label, x, y = parsed
        is_tap = any(name.startswith("tapOn") for name in command)
        t = _event_time(
            metadata,
            recorder_mono=recorder_mono,
            maestro_timing=maestro_timing,
            at_end=is_tap,
        )
        if t is None:
            continue
        counter += 1
        events.append(
            Event(
                id=f"e{counter}",
                t=t,
                type=event_type,
                x=x,
                y=y,
                label=label,
            )
        )
    return events


def parse_maestro_commands_file(
    path: Path,
    *,
    width: int,
    height: int,
    recorder_mono: float,
    maestro_timing: MaestroTiming,
) -> list[Event]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ReelsmithError(f"Unexpected Maestro commands file: {path.name}")
    return parse_maestro_commands(
        raw,
        width=width,
        height=height,
        recorder_mono=recorder_mono,
        maestro_timing=maestro_timing,
    )


def find_commands_json(debug_dir: Path, flow_path: Path) -> Path | None:
    """Maestro's per-command log for this flow.

    Maestro 1.x writes a flat `commands-(<flow>).json`. Maestro 2.x ignores
    --flatten-debug-output and writes `<flow>/commands.json` instead.
    """
    stem = flow_path.stem.replace("/", "_")
    candidates = [
        *debug_dir.glob(f"commands-*({stem}).json"),
        debug_dir / stem / "commands.json",
        *debug_dir.glob("commands-*.json"),
        *debug_dir.glob("*/commands.json"),
    ]
    return next((path for path in candidates if path.is_file()), None)


def parse_junit_flow_duration(path: Path) -> float | None:
    """Read total flow time from a JUnit report when present."""
    if not path.is_file():
        return None
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except ET.ParseError:
        return None
    for testcase in root.iter("testcase"):
        raw = testcase.get("time")
        if raw is None:
            continue
        try:
            return float(raw)
        except ValueError:
            continue
    return None


def events_from_maestro_output(
    *,
    debug_dir: Path,
    flow_path: Path,
    width: int,
    height: int,
    recorder_mono: float,
    maestro_timing: MaestroTiming,
) -> tuple[list[Event], list[str]]:
    warnings: list[str] = []
    commands_path = find_commands_json(debug_dir, flow_path)
    if commands_path is None:
        warnings.append("No Maestro commands JSON found. Using a single screen event at t=0.")
        return [
            Event(id="e1", t=0.0, type="screen", label=flow_path.stem),
        ], warnings

    events = parse_maestro_commands_file(
        commands_path,
        width=width,
        height=height,
        recorder_mono=recorder_mono,
        maestro_timing=maestro_timing,
    )
    if events:
        return events, warnings

    warnings.append(
        "Could not read step times from Maestro output. Using a single screen event at t=0."
    )
    return [Event(id="e1", t=0.0, type="screen", label=flow_path.stem)], warnings


def _as_background_recorder(
    started: subprocess.CompletedProcess[str] | subprocess.Popen[Any],
    *,
    label: str,
) -> subprocess.Popen[Any]:
    if isinstance(started, subprocess.Popen):
        return started
    if hasattr(started, "poll") and hasattr(started, "send_signal") and hasattr(started, "wait"):
        return started  # type: ignore[return-value]
    raise ReelsmithError(f"Could not start the {label} screen recorder.")


def _stop_ios_recorder(proc: subprocess.Popen[Any]) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=RECORDER_STOP_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def _stop_android_recorder(device: str | None) -> None:
    subprocess_runner(android_stop_record_command(device), check=True)
    time.sleep(0.5)


def _run_maestro(
    flow_path: Path,
    work_dir: Path,
    device: str | None = None,
) -> tuple[Path, Path, MaestroTiming]:
    flow_path = flow_path.resolve()
    if not flow_path.is_file():
        raise ReelsmithError(f"{flow_path} not found")

    junit_path = work_dir / "report.xml"
    debug_dir = work_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    maestro_wall0 = time.time()
    maestro_mono0 = time.monotonic()
    completed = subprocess_runner(
        maestro_test_command(flow_path, junit_path=junit_path, debug_dir=debug_dir, device=device),
        check=False,
    )
    maestro_timing = (maestro_wall0, maestro_mono0, time.monotonic())

    if completed.returncode != 0:
        stderr = completed.stderr if isinstance(completed.stderr, str) else ""
        stdout = completed.stdout if isinstance(completed.stdout, str) else ""
        detail = stderr.strip() or stdout.strip() or f"exit code {completed.returncode}"
        raise ReelsmithError(f"Maestro test failed.\n{detail}")

    return junit_path, debug_dir, maestro_timing


def _ensure_record_length(
    elapsed: float,
    *,
    junit_path: Path | None,
    platform_name: Platform,
) -> None:
    if platform_name != "android":
        return
    if elapsed <= ANDROID_RECORD_LIMIT_SEC:
        return
    flow_hint = ""
    if junit_path is not None:
        duration = parse_junit_flow_duration(junit_path)
        if duration is not None and duration > ANDROID_RECORD_LIMIT_SEC:
            flow_hint = f" Maestro reported {duration:.0f} s."
    raise ReelsmithError(
        f"Android screenrecord stops after {ANDROID_RECORD_LIMIT_SEC:.0f} seconds."
        f"{flow_hint} Your capture ran about {elapsed:.0f} s.",
        fix="Shorten the Maestro flow or split it into multiple clips.",
    )


def _start_background_recorder(args: list[str], *, label: str) -> subprocess.Popen[Any]:
    proc = subprocess_runner(
        args,
        background=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    return _as_background_recorder(proc, label=label)


def run_mobile_flow(
    flow_path: Path,
    clip_id: str,
    clips_root: Path,
    *,
    platform_name: Platform,
    device: str | None = None,
) -> MobileCaptureResult:
    """Record a Maestro flow and write clips/<id>/video.mp4 and clip.json."""
    require_mobile_tools(platform_name)
    device = resolve_device(platform_name, device)
    flow_path = flow_path.resolve()
    clip_dir = clips_root / clip_id
    clip_dir.mkdir(parents=True, exist_ok=True)
    work_dir = clip_dir / ".mobile_work"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    raw_video = work_dir / ("capture.mov" if platform_name == "ios" else "capture.mp4")

    recorder_mono = time.monotonic()
    recorder: subprocess.Popen[Any] | None = None
    junit_path: Path | None = None
    debug_dir: Path | None = None
    maestro_timing: MaestroTiming = (0.0, 0.0, 0.0)
    maestro_error: ReelsmithError | None = None

    if platform_name == "ios":
        recorder = _start_background_recorder(ios_record_command(raw_video, device), label="iOS")
    else:
        subprocess_runner(android_rm_remote_command(device), check=False)
        recorder = _start_background_recorder(
            android_record_command(device),
            label="Android",
        )

    try:
        junit_path, debug_dir, maestro_timing = _run_maestro(flow_path, work_dir, device)
    except ReelsmithError as exc:
        maestro_error = exc
    finally:
        elapsed = time.monotonic() - recorder_mono
        if platform_name == "ios":
            if recorder is not None:
                _stop_ios_recorder(recorder)
        else:
            _stop_android_recorder(device)
            if raw_video.exists():
                raw_video.unlink()
            pulled = subprocess_runner(
                android_pull_command(device, raw_video),
                check=False,
            )
            if pulled.returncode != 0 or not raw_video.is_file():
                stderr = pulled.stderr if isinstance(pulled.stderr, str) else ""
                raise ReelsmithError(
                    "Could not pull the Android recording.",
                    fix=stderr.strip() or "Check adb devices and retry.",
                )
            subprocess_runner(android_rm_remote_command(device), check=False)

    if maestro_error is not None:
        raise maestro_error

    assert junit_path is not None and debug_dir is not None

    _ensure_record_length(elapsed, junit_path=junit_path, platform_name=platform_name)

    if not raw_video.is_file():
        raise ReelsmithError("Screen recording file is missing after capture.")

    clip = import_recording(raw_video, clip_id, clips_root)
    events, warnings = events_from_maestro_output(
        debug_dir=debug_dir,
        flow_path=flow_path,
        width=clip.width,
        height=clip.height,
        recorder_mono=recorder_mono,
        maestro_timing=maestro_timing,
    )

    duration = clip.duration
    trimmed: list[Event] = []
    for event in events:
        t = min(max(0.0, event.t), duration)
        trimmed.append(event.model_copy(update={"t": t}))

    clip = clip.model_copy(update={"events": trimmed})
    save_model(clip_dir / "clip.json", clip)

    shutil.rmtree(work_dir, ignore_errors=True)
    return MobileCaptureResult(clip=clip, warnings=warnings)
