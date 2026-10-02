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
