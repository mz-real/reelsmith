"""Tests for mobile capture (mocked subprocesses only)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from reelsmith.capture import mobile as mobile_mod
from reelsmith.errors import ReelsmithError
from reelsmith.models import ClipModel, load_model

SAMPLE_COMMANDS_JSON = """
[
  {
    "command": {
      "tapOnPointV2Command": {
        "point": "540,960",
        "label": "Search box",
        "optional": false
      }
    },
    "metadata": {
      "status": "COMPLETED",
      "timestamp": 1000500,
      "duration": 400
    }
  },
  {
    "command": {
      "pressKeyCommand": {
        "key": "Back",
        "optional": false
      }
    },
    "metadata": {
      "status": "COMPLETED",
      "timestamp": 1001200,
      "duration": 120
    }
  },
  {
    "command": {
      "swipeCommand": {
        "label": "Scroll list",
        "optional": false
      }
    },
    "metadata": {
      "status": "COMPLETED",
      "timestamp": 1002000,
      "duration": 800
    }
  }
]
"""

SAMPLE_JUNIT = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="flow" tests="1" failures="0">
    <testcase classname="demo" name="login" time="12.5"/>
  </testsuite>
</testsuites>
"""


class FakePopen:
    def __init__(self, args: list[str], **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        self.returncode: int | None = None
        self._signals: list[int] = []

    def poll(self) -> int | None:
        return self.returncode

    def send_signal(self, sig: int) -> None:
        self._signals.append(sig)
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = 0
        return 0

    def kill(self) -> None:
        self.returncode = -9


def test_ios_stop_sends_sigint() -> None:
    proc = FakePopen(["xcrun", "simctl", "io", "booted", "recordVideo"])
    mobile_mod._stop_ios_recorder(proc)  # type: ignore[arg-type]
    import signal

    assert proc._signals == [signal.SIGINT]


def test_ios_record_command_line() -> None:
    cmd = mobile_mod.ios_record_command(Path("/tmp/out.mov"))
    assert cmd[:6] == ["xcrun", "simctl", "io", "booted", "recordVideo", "--codec=h264"]
    assert cmd[-1] == str(Path("/tmp/out.mov"))


def test_android_record_and_stop_commands() -> None:
    record = mobile_mod.android_record_command("emulator-5554")
    assert record == [
        "adb",
        "-s",
        "emulator-5554",
        "shell",
        "screenrecord",
        "--bit-rate",
        mobile_mod.ANDROID_RECORD_BITRATE,
        mobile_mod.ANDROID_REMOTE_VIDEO,
    ]
    stop = mobile_mod.android_stop_record_command(None)
    assert stop[-2:] == ["-INT", "screenrecord"]


def test_maestro_command_includes_junit_and_debug() -> None:
    flow = Path("flows/demo.yaml")
    cmd = mobile_mod.maestro_test_command(
        flow,
        junit_path=Path("/tmp/report.xml"),
        debug_dir=Path("/tmp/debug"),
    )
    assert cmd[0] == "maestro"
    assert "--format" in cmd and "junit" in cmd
    assert "--flatten-debug-output" in cmd


def test_parse_maestro_commands_json() -> None:
    payload = json.loads(SAMPLE_COMMANDS_JSON)
    recorder_mono = 20.0
    maestro_timing = (1000.0, 20.0, 25.0)
    events = mobile_mod.parse_maestro_commands(
        payload,
        width=1080,
        height=1920,
        recorder_mono=recorder_mono,
        maestro_timing=maestro_timing,
    )
    assert len(events) == 3
    assert events[0].type == "tap"
    assert events[0].label == "Search box"
    assert events[0].x == pytest.approx(0.5)
    assert events[0].y == pytest.approx(0.5)
    # A tap is timed when its command ends (500 ms start + 400 ms finding the
    # element), which is when the screen changes. Keys keep their start time.
    assert events[0].t == pytest.approx(0.9)
    assert events[1].type == "back"
    assert events[1].t == pytest.approx(1.2)
    assert events[2].type == "scroll"


def test_parse_junit_duration_from_file(tmp_path: Path) -> None:
    report = tmp_path / "report.xml"
    report.write_text(SAMPLE_JUNIT, encoding="utf-8")
    assert mobile_mod.parse_junit_flow_duration(report) == pytest.approx(12.5)


def test_events_fallback_when_no_commands(tmp_path: Path) -> None:
    debug = tmp_path / "debug"
    debug.mkdir()
    flow = tmp_path / "demo.yaml"
    flow.write_text("appId: demo\n", encoding="utf-8")
    events, warnings = mobile_mod.events_from_maestro_output(
        debug_dir=debug,
        flow_path=flow,
        width=1080,
        height=1920,
        recorder_mono=0.0,
        maestro_timing=(0.0, 0.0, 1.0),
    )
    assert len(events) == 1
    assert events[0].type == "screen"
    assert warnings


def test_require_mobile_tools_missing_maestro(monkeypatch: pytest.MonkeyPatch) -> None:
    from reelsmith.doctor.checks import Check
    from reelsmith.result import Status

    monkeypatch.setattr(
        mobile_mod,
        "check_java",
        lambda: Check(name="java", status=Status.OK, found="ok", fix=None),
    )
    monkeypatch.setattr(
        mobile_mod,
        "check_maestro",
        lambda: Check(
            name="maestro",
            status=Status.WARN,
            found="missing",
            fix="install maestro",
        ),
    )
    monkeypatch.setattr(
        mobile_mod,
        "check_adb",
        lambda: Check(name="adb", status=Status.OK, found="ok", fix=None),
    )
    with pytest.raises(ReelsmithError) as err:
        mobile_mod.require_mobile_tools("android")
    assert "Maestro" in str(err.value)
    assert err.value.fix == "install maestro"


def test_ios_unsupported_off_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    from reelsmith.doctor.checks import Check
    from reelsmith.result import Status

    monkeypatch.setattr(mobile_mod.platform, "system", lambda: "Linux")
    monkeypatch.setattr(mobile_mod, "require_ffmpeg", lambda: None)

    def fake_which(name: str) -> str | None:
        if name == "java":
            return "/usr/bin/java"
        if name == "maestro":
            return "/usr/bin/maestro"
        return None

    monkeypatch.setattr("reelsmith.capture.mobile.shutil.which", fake_which)
    monkeypatch.setattr(
        mobile_mod,
        "check_java",
        lambda: Check(name="java", status=Status.OK, found="ok", fix=None),
    )
    monkeypatch.setattr(
        mobile_mod,
        "check_maestro",
        lambda: Check(name="maestro", status=Status.OK, found="ok", fix=None),
    )
    with pytest.raises(ReelsmithError) as err:
        mobile_mod.require_mobile_tools("ios")
    assert "macOS" in str(err.value)


def test_android_record_limit_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mobile_mod, "ANDROID_RECORD_LIMIT_SEC", 5.0)
    with pytest.raises(ReelsmithError) as err:
        mobile_mod._ensure_record_length(
            6.0,
            junit_path=None,
            platform_name="android",
        )
    assert "screenrecord" in str(err.value)


def _make_tiny_video(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=320x240:rate=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )


def test_run_mobile_flow_orchestration_android(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = tmp_path / "demo.yaml"
    flow.write_text("appId: demo\n", encoding="utf-8")
    clips = tmp_path / "clips"
    sample_commands = json.loads(SAMPLE_COMMANDS_JSON)

    popen_calls: list[list[str]] = []
    run_calls: list[list[str]] = []

    def fake_start_recorder(args: list[str], *, label: str = "device") -> FakePopen:
        popen_calls.append(args)
        return FakePopen(args)

    def fake_runner(
        args: list[str],
        *,
        background: bool = False,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str] | FakePopen:
        run_calls.append(args)
        if background:
            raise AssertionError("use _start_background_recorder in tests")
        if args[0] == "maestro" and "test" in args:
            junit = Path(args[args.index("--output") + 1])
            junit.write_text(SAMPLE_JUNIT, encoding="utf-8")
            debug_dir = Path(args[args.index("--debug-output") + 1])
            debug_dir.mkdir(parents=True, exist_ok=True)
            commands_path = debug_dir / "commands-(demo).json"
            commands_path.write_text(json.dumps(sample_commands), encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if "pull" in args:
            dest = Path(args[-1])
            _make_tiny_video(dest)
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(mobile_mod, "subprocess_runner", fake_runner)
    monkeypatch.setattr(mobile_mod, "_start_background_recorder", fake_start_recorder)
    monkeypatch.setattr(mobile_mod, "require_mobile_tools", lambda _: None)
    monkeypatch.setattr(mobile_mod.time, "time", lambda: 1000.0)
    mono = {"value": 100.0}

    def fake_monotonic() -> float:
        mono["value"] += 0.05
        return mono["value"]

    monkeypatch.setattr(mobile_mod.time, "monotonic", fake_monotonic)

    result = mobile_mod.run_mobile_flow(
        flow,
        "demo",
        clips,
        platform_name="android",
        device="emulator-5554",
    )

    assert popen_calls
    assert popen_calls[0][0:3] == ["adb", "-s", "emulator-5554"]
    maestro = next(call for call in run_calls if call[0] == "maestro")
    assert maestro[1:4] == ["--device", "emulator-5554", "test"]
    assert "screenrecord" in popen_calls[0]
    assert any("pkill" in " ".join(c) for c in run_calls)
    assert result.clip.id == "demo"
    assert len(result.clip.events) >= 2
    loaded = load_model(clips / "demo" / "clip.json", ClipModel)
    assert loaded.events == result.clip.events


def _completed(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")


def _simulators(*devices: tuple[str, str]) -> str:
    booted = [{"udid": udid, "name": name, "state": "Booted"} for udid, name in devices]
    return json.dumps({"devices": {"com.apple.CoreSimulator.SimRuntime.iOS-26-0": booted}})


def test_ios_uses_the_one_booted_simulator(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _simulators(("UDID-1", "iPhone 16"))
    monkeypatch.setattr(mobile_mod, "subprocess_runner", lambda args, **kw: _completed(out))
    assert mobile_mod.resolve_device("ios", None) == "UDID-1"


def test_ios_with_two_booted_simulators_asks_for_one(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _simulators(("UDID-1", "iPhone 16"), ("UDID-2", "iPad"))
    monkeypatch.setattr(mobile_mod, "subprocess_runner", lambda args, **kw: _completed(out))
    with pytest.raises(ReelsmithError, match="More than one iOS simulator") as caught:
        mobile_mod.resolve_device("ios", None)
    assert caught.value.fix is not None and "--device" in caught.value.fix


def test_ios_without_a_booted_simulator_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _simulators()
    monkeypatch.setattr(mobile_mod, "subprocess_runner", lambda args, **kw: _completed(out))
    with pytest.raises(ReelsmithError, match="No iOS simulator is booted"):
        mobile_mod.resolve_device("ios", None)


def test_android_uses_the_one_connected_device(monkeypatch: pytest.MonkeyPatch) -> None:
    out = "List of devices attached\nemulator-5554\tdevice\nZX1\toffline\n\n"
    monkeypatch.setattr(mobile_mod, "subprocess_runner", lambda args, **kw: _completed(out))
    assert mobile_mod.resolve_device("android", None) == "emulator-5554"


def test_android_with_two_devices_asks_for_one(monkeypatch: pytest.MonkeyPatch) -> None:
    out = "List of devices attached\nemulator-5554\tdevice\nR58M\tdevice\n"
    monkeypatch.setattr(mobile_mod, "subprocess_runner", lambda args, **kw: _completed(out))
    with pytest.raises(ReelsmithError, match="More than one Android device"):
        mobile_mod.resolve_device("android", None)


def test_an_explicit_device_is_used_as_given(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(args: list[str], **kw: Any) -> None:
        raise AssertionError("no lookup when --device is given")

    monkeypatch.setattr(mobile_mod, "subprocess_runner", fail)
    assert mobile_mod.resolve_device("ios", "UDID-9") == "UDID-9"


def test_maestro_and_the_ios_recorder_target_the_same_simulator() -> None:
    cmd = mobile_mod.maestro_test_command(
        Path("flow.yaml"), junit_path=Path("r.xml"), debug_dir=Path("d"), device="UDID-1"
    )
    assert cmd[:4] == ["maestro", "--device", "UDID-1", "test"]
    assert mobile_mod.ios_record_command(Path("o.mov"), "UDID-1")[3] == "UDID-1"


def test_commands_json_is_found_in_the_maestro_2_layout(tmp_path: Path) -> None:
    flow = Path("capture/flows/checkout.yaml")
    nested = tmp_path / "checkout" / "commands.json"
    nested.parent.mkdir()
    nested.write_text("[]", encoding="utf-8")
    assert mobile_mod.find_commands_json(tmp_path, flow) == nested


def test_commands_json_is_found_in_the_maestro_1_layout(tmp_path: Path) -> None:
    flat = tmp_path / "commands-(checkout).json"
    flat.write_text("[]", encoding="utf-8")
    assert mobile_mod.find_commands_json(tmp_path, Path("checkout.yaml")) == flat


def test_a_percent_point_tap_keeps_its_position() -> None:
    entry = mobile_mod._command_entry(
        {"tapOnPointV2Command": {"point": "50%,17%"}}, width=1080, height=2400
    )
    assert entry == ("tap", "tap", pytest.approx(0.5), pytest.approx(0.17))


def test_an_optional_step_that_did_not_run_is_not_an_event() -> None:
    payload = [
        {
            "command": {"tapOnElement": {"selector": {"textRegex": "No thanks"}}},
            "metadata": {"status": "WARNED", "timestamp": 1000500, "duration": 5000},
        }
    ]
    events = mobile_mod.parse_maestro_commands(
        payload,
        width=1080,
        height=2400,
        recorder_mono=20.0,
        maestro_timing=(1000.0, 20.0, 25.0),
    )
    assert events == []
