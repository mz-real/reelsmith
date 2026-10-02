"""Capture footage for a demo: import a file or record the web."""

from reelsmith.capture.importer import import_recording
from reelsmith.capture.mobile import run_mobile_flow
from reelsmith.capture.web import run_web_flow

__all__ = ["import_recording", "run_mobile_flow", "run_web_flow"]
