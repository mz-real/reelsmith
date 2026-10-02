# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Design spec and implementation plan (`docs/design/2026-10-02-reelsmith-design.md`, `docs/design/2026-10-02-reelsmith-plan.md`)
- Project skeleton: Python package, uv tooling, ruff, mypy (strict on `src/`), pytest, dash checker script
- CI on Windows, macOS and Linux (Python 3.11 and 3.13)
- Core models and JSON Schemas: spec, clip, script and brand
- Timing engine (pinning, holds, pace windows, caption durations)
- CLI: `doctor`, `init`, `setup browser`
- Capture: import and web recording paths
- Slides pipeline (initial)
- Recipe Box example app and demo assets under `examples/recipe-box`
- Voice: Kokoro narration with `voice generate` and `voice preview`, pace and dropped word checks, end of line clean up and phrase timings
- Compose and export: `compose` renders each scene into a master per format (`--preview` for a fast draft), and `export` writes voiced and silent videos, the narration track and an .srt
- QA: `qa` checks the finished video and writes `qa/report.md` with contact sheets
- Detect: `detect` finds screen changes in a clip and writes contact sheets for Narrate mode
- Mobile capture: `capture mobile` drives a Maestro flow and records the iOS simulator or Android screen locally
- Instruction layer: shared guides generated for Claude Code, Codex, Cursor, Gemini CLI and Copilot, the Claude Code plugin, `agent install` and `prompts/HANDOVER_PROMPT.md`
- Own voice cloning with Chatterbox through the `clone` extra, gated on consent in spec.yaml, watermark always on
- `voice pick-reference` finds the cleanest stretch of a voice recording to clone from
- `voice compare` reads a few lines with each reference and recommends one
- `run` runs every step from script check to export, stopping at the first error
- `schema export` writes the JSON Schemas, now including slides
- README and user docs: `docs/install.md`, `docs/voices.md`, `docs/formats.md`

### Changed

- Every command takes the demo folder the same way, as an optional argument that defaults to the current folder
- `capture web` records at the requested `--size`
