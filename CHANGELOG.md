# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `uv tool install "reelsmith[clone]"` failed to build `pkuseg`, a dependency of chatterbox-tts 0.1.3 and later whose setup.py imports numpy without declaring it. The clone extra now pins chatterbox-tts 0.1.2, which does not need it.

## [0.1.0] - 2026-10-03

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
- Studio slide theme with animated build steps, and slide kinds for title, flow, chart, bullets, cards, architecture, code, timeline, compare, stats and gallery, with a built in line icon set
- Compose motion: panel points, zoom, cursor, device and browser frames with a status bar, scene transitions (fade, slide, push, zoom) and 4K output
- Voice: `say` overrides for spoken forms, `voice.vocabulary` hints for the transcript check, and `voice.pronounce` for exact phonemes of product names
- `detect` finds small screen changes and pins clicks to the exact frame
- `reelsmith init --preset quick|tour|mobile|release-notes|narrate` writes a ready starting spec, script and slides
- `reelsmith status [--json]` shows which steps are done, stale or missing, and the next command
- Global `--json` prints any command's result as one JSON line; progress for long steps goes to stderr
- `doctor` checks only what the demo needs, by profile (web, mobile, narrate, voice, clone, all), picked from spec.yaml or `--profile`, and takes the demo folder as DIR
- A short `prompts/HANDOVER_PROMPT.md` for any AI tool, with the full guides in `prompts/HANDOVER_PROMPT_FULL.md`
- Release guide, tag only release workflow and version checks
- Integration tests on Linux, macOS and Windows

### Changed

- Every command takes the demo folder the same way, as an optional argument that defaults to the current folder
- `capture web` records at the requested `--size`
- `voice.engine: none` is a clean silent run: `run` skips voice, QA skips the audio checks with a note, and export writes the video and captions only
- Ids must use letters, numbers, `-` and `_`, starting with a letter or number, so an id can never become a path
- The README leads with Narrate, the checks on every finished video, and who reelsmith is for

### Fixed

- Voice: Kokoro int8 synthesis no longer returns silence on some machines, the first and last words of a line are never clipped, stale lines are dropped, and `--only` always re-records
- Voice: a take passes when it matches either the written text or its `say` form; spelling variants and pace by speed are handled
- QA judges captions, transcripts and line ends by the real narration timing
- Slides render the same bytes every time, wait for fonts and layout, and render for every output format
- Web capture finds its sync marker on slow machines
- doctor uses distro Java packages and the real model cache paths
- `status` and `init` quote paths for the user's shell on Windows
- `status` reports slides as stale when their size does not match the spec's quality
- `script check` warns while brand.yaml still has the starter product name
- Web capture times clicks, typing and keys when they land, not before Playwright's actionability wait
- Mobile capture drives and records the one booted simulator or device (or asks for `--device`), reads Maestro 2's command log, times taps when they land, and keeps the position of percent point taps
