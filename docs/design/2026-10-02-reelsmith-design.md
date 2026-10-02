# reelsmith: design spec

Status: approved
Date: 2026-10-02
Owner: mz-real
License: MIT

## 1. What we are building

reelsmith makes professional narrated demo videos of software, fully on your own machine. You describe what you want to an AI coding tool, it asks you a few questions, and reelsmith records, scripts, voices, assembles and checks the video.

It ships as:

- a Python command line tool, `reelsmith`, that does all the real work
- a Claude Code plugin (the top priority), plus instruction files for Codex, Cursor, Gemini CLI, GitHub Copilot and any other AI tool

Nothing is uploaded. Voices come from Kokoro (stock voices) or Chatterbox (your own voice, with consent). No ElevenLabs or other online voice service.

### Who it is for

Coders first, on Windows, macOS and Linux. People who are less technical are welcome, and the AI tool guides them, but the defaults and docs assume someone comfortable with a terminal.

### What success looks like

- A developer installs the plugin, says "make a demo of my app", answers a short interview, approves a plan and a script, and gets a finished video they are happy to share.
- The same request gives the same quality in Claude Code, Codex, Cursor and Gemini CLI.
- The engine works on all three operating systems, proven by CI.
- The repo looks and reads like a well run open source project.

### Out of scope for v1

- An MCP server (planned for a later release as a thin wrapper around the CLI)
- A GUI or web dashboard
- Background music
- Scripted native test frameworks inside the app (such as Detox). Mobile automation uses Maestro instead.

## 2. Two modes

The first interview question picks the mode: "Do you already have a recording you just want narrated, or should we produce a full demo?"

### Narrate

For someone who already has a recording and wants a voice explaining each click.

1. The user gives a video.
2. reelsmith detects screen changes and builds timestamped contact sheets. The AI reads them and proposes a timeline of actions ("0:04 clicks Login"). The user can correct it.
3. The AI writes step by step narration, each phrase pinned to its action. The user approves the script.
4. Voice is generated with Kokoro or Chatterbox.
5. Output is the original video at the same resolution, with narration added. The length stays the same unless held frames or speed ups are turned on. Optional and off by default: burned in captions or an .srt file, a highlight where each click happens, speeding up long waits.

If a line is longer than the gap before the next action, reelsmith either holds the frame briefly (only if allowed) or asks the AI to shorten the line. The voice never drifts ahead of the clicks.

### Produce

The full package: slides that explain the business logic, device or browser frames, side captions, tap ripples, transitions, several formats.

## 3. User experience

```
You: "make a demo of my app"
AI:  short interview, one question at a time, with suggested answers
     1. Narrate an existing recording, or produce a full demo?
     2. What should it show? (one feature, full tour, mobile app, release notes)
     3. Who is watching, and how long? (team, customers, social; 30 s to 5 min)
     4. Footage: your recordings, automated web, or automated mobile?
     5. Voice: Kokoro stock voice, your own voice (Chatterbox), or silent with captions?
     6. Format, branding, anything to blur
AI:  writes spec.yaml               -> approval point 1
AI:  captures or imports footage, writes script.yaml -> approval point 2
AI:  voices, builds slides, composes, runs QA
AI:  shows the preview and QA report, fixes what you ask, exports
```

There are always two approval points: the plan and the script. Nothing is voiced or rendered before the user agrees to the words.

Presets keep the interview short: Quick feature clip (30 to 60 s), Full app tour (3 to 5 min), Mobile demo, Release notes video.

## 4. Architecture

The AI tools never generate pipeline code. They follow shared instructions and call one CLI. This keeps results consistent, saves tokens, and stops fixed bugs from coming back.

### Engine components

Each component has one job, reads and writes files in the demo folder, and can be tested alone.

| Component | Job |
|---|---|
| doctor | Checks Python, ffmpeg, browser, Java and Maestro, simulators, voice models and GPU. Prints exact fixes for the current OS. |
| project | `reelsmith init` creates a demo folder with a starter spec.yaml. |
| capture | Gets footage three ways: import, web (Playwright), mobile (Maestro plus our own screen recorder). All three produce the same clip format. |
| script | Narration per scene: text, the clip it belongs to, and the event each phrase is pinned to. |
| voice | Kokoro or Chatterbox behind one interface. Pace check, dropped word check, end of line clean up, phrase alignment. |
| slides | Turns simple slide descriptions (title, logic flow, chart) into images, using the brand file. Slides are HTML templates rendered to PNG with Playwright. |
| compose | Builds the master video: layouts, captions, ripples, blur, transitions. |
| export | Writes the deliverables from the master: each format, voiceover and silent versions, the narration audio track and the .srt file. |
| qa | Runs the checks and writes a pass or fail report with suggested fixes. |

Data flows one way: spec, capture, script, voice, slides, compose, qa, export. Any step can be rerun on its own. Changing the voice reruns only voice, compose, qa and export.

### Command list

`doctor`, `init`, `capture import|web|mobile`, `detect` (Narrate mode timeline), `script check`, `voice generate|preview|compare|pick-reference`, `slides`, `compose [--preview]`, `qa`, `export`, `run` (all steps for a ready made example), `agent install <tool>`, `setup browser`.

Every command ends with a short structured summary (OK, WARN or ERROR, plus the next step) so any AI tool can read the result reliably.

## 5. Demo folder and file formats

```
my-demo/
  spec.yaml        the plan (approval point 1)
  brand.yaml       logo, colours, fonts (optional)
  capture/
    flows/         Playwright scripts or Maestro YAML written by the AI
    clips/         videos, each with a clip.json
  script.yaml      narration per scene (approval point 2)
  voice/           one audio file per line, plus timings
  slides/          rendered slide images
  build/           working files, safe to delete
  qa/              report.md and contact sheets
  out/             final videos and .srt captions
```

- spec.yaml: mode, goal, audience, length, format, quality, voice choice (Kokoro voice name, or Chatterbox sample path plus consent), footage source, scenes in order, blur list.
- clip.json: video path, screen size, and a list of events with time, type (tap, screen, key) and position. Automated capture writes events itself. For imported recordings the AI marks them from contact sheets, or the user adds rough times.
- script.yaml: per scene, the caption and the narration split into phrases. A phrase can be pinned to an event so it lands on that tap.

All formats are plain YAML or JSON with a published schema, so coders can edit anything by hand.

## 6. Capture

- Import: any screen recording or phone recording. Frame rate and size are normalised on import.
- Web: Playwright drives a headless or visible Chromium and records it. The AI writes the flow script. Every action is logged with its time and position.
- Mobile: Maestro drives taps from a YAML flow on an iOS simulator or Android emulator or device. reelsmith records the screen itself (`simctl` on iOS, `adb screenrecord` on Android) and logs tap times. Maestro's own recording is not used, so nothing goes to a cloud.

Platform limits, reported by doctor: iOS needs macOS with Xcode. Android works on all three operating systems with an emulator or a USB device with debugging enabled. Maestro needs Java 17 or newer.

## 7. Voice

One interface, two engines.

### Kokoro (default)

- The ONNX build: small, no PyTorch, same install on every OS, fast on a laptop CPU.
- The interview offers a short list of good voices. `voice preview` reads the same line in three or four voices.
- English first. Other Kokoro languages are marked best effort.

### Chatterbox (own voice, opt-in)

- Optional install, `reelsmith[clone]`, because it needs PyTorch. Uses an NVIDIA GPU, Apple Silicon or the CPU. doctor warns how slow the CPU path is.
- Consent gate: the AI asks whether the sample is the user's own voice or used with permission, and spec.yaml stores the answer. No consent, no cloning.
- The built in watermark stays on. Nothing is uploaded.
- `voice pick-reference`: finds the cleanest 10 to 15 seconds in a longer recording, since only about 10 seconds is used.
- `voice compare`: generates the same lines from several references or settings, scores voice similarity and pace, and recommends one.

### Quality steps for both engines

1. Pace check: lines outside about 130 to 210 words per minute are regenerated with a new seed.
2. Dropped word check: each line is transcribed locally with Whisper and compared with the script. Mismatches are regenerated.
3. End of line clean up: cut only after the voice has stayed quiet for a short time, so clicks go and last words stay.
4. Phrase alignment: pinned phrases are split at natural pauses and placed on their events.

## 8. Look and assembly

### Layouts per scene

- Slide: full frame, build steps appear in time with the narration.
- Phone: vertical device frame on a blurred background, captions in a side panel.
- Browser: a clean browser window frame, captions beside or below.
- Full screen: raw footage, for desktop apps or imported recordings.

### Formats

- 16:9: device in the centre, captions to the side.
- 9:16: device fills the frame, captions in a top or bottom band placed away from important content.
- 1:1: in between.

Three built in themes (dark, light, minimal). brand.yaml overrides colours, logo and font.

### Motion

Slides scale into the device frame (about 0.4 s), build steps fade in, a gentle slow zoom on slides, tap ripples, a Back key badge for Android.

### Timing rules

- A scene lasts at least its narration plus a short breath.
- Extra time is a held last frame, capped at about 3 s. Longer holds fail QA.
- Repetitive parts can be sped up so narration does not run ahead.
- Pinned phrases land on their events.

### Exports

`reelsmith export` writes voiceover and silent versions, a narration only audio track and an .srt file, in each requested format. 1080p by default, 4K optional. Blur regions are applied in compose, so every export already has them.

### Iteration speed

`compose --preview` renders a fast low resolution draft. Final renders cache each scene and only rebuild what changed.

## 9. QA and errors

`reelsmith qa` writes qa/report.md with PASS or FAIL per check and a suggested fix for each failure.

| Check | Catches |
|---|---|
| Transcript vs script | missing, slurred or changed words |
| Sync | phrases early or late against their event |
| Cut off lines | narration running into the next scene or past the end |
| End of line noise | clicks or breaths after the last word |
| Loudness | far from -16 LUFS, or clipping |
| Hold limits | frozen frames longer than allowed |
| Captions | text overflowing its panel or too short to read |
| Blur | listed regions present on every frame they apply to |
| Contact sheets | frames at each scene, event and transition for review by eye |

The instructions require the AI to read the report and clear every FAIL before calling a video done.

Error handling:

- Errors say what went wrong and how to fix it on the current OS.
- Long steps show progress and resume after a crash instead of starting over.
- Nothing is overwritten silently. Reruns keep the previous output as a backup.
- `doctor --fix` installs only with the user's agreement and never asks for admin rights without saying so.

## 10. Instruction layer

The instructions are treated as carefully as the code.

### Structure

- A short entry file (SKILL.md for Claude, AGENTS.md for Codex, a Cursor rule file in `.cursor/rules/`, GEMINI.md, Copilot instructions): goal, workflow, approval points, rules. About one page. Cursor also reads AGENTS.md, so either file works there.
- Detailed guides in references/, read only when the AI reaches that step: interview, narrate, capture web, capture mobile, script writing, voice, QA, troubleshooting.

Every guide follows the same pattern: goal of the step, what to ask or check, which command to run with examples, how to read the output, common failures and fixes, a "done when" checklist.

### Rules built into every guide

- Truth rule: narration and captions only claim what is on screen.
- Run `reelsmith qa` and read the report before saying a video is finished.
- One interview question at a time, with suggested answers.
- Never invent features. Read the app or ask.
- Business logic first, then the screen, in the user's own speaking style if they share one.

### One source, many tools

A single source set of instruction files generates the Claude skill, AGENTS.md, Cursor rules, GEMINI.md and Copilot instructions. CI fails if a generated file drifts from its source.

### Writing rules (docs and prompts)

Human tone, short sentences, plain words, no marketing filler, no em dashes. CI fails on an em dash.

## 11. Installation and distribution

### Engine

- Published on PyPI. `uv tool install reelsmith`, or `uv tool install "reelsmith[clone]"` for own voice cloning.
- Python 3.11 to 3.13, managed by uv. The `[clone]` extra needs Python 3.11 or 3.12, because Chatterbox does not run on newer versions yet.
- External tools, checked by doctor with per OS commands: ffmpeg (winget, brew, apt or dnf), Chromium via `reelsmith setup browser`, Java 17 and Maestro only for mobile capture.
- Models download on first use into a cache folder: the Kokoro voice model, the faster-whisper model used by the dropped word check, and Chatterbox if the extra is installed. Sizes are shown before download.

### AI tools

- Claude Code: `/plugin marketplace add mz-real/reelsmith`, then `/plugin install reelsmith@reelsmith`. The skill detects a missing CLI and offers to install it.
- Codex, Cursor, Gemini CLI, Copilot: `reelsmith agent install <tool>` writes the right file into the user's project.
- Any other tool: paste prompts/HANDOVER_PROMPT.md.

The instructions declare the CLI version they expect. doctor warns on a mismatch. Plugin and CLI share one version number.

## 12. Testing and CI

Unit tests on every push: schema validation, timing logic (pinning, holds, speed ups, caption durations), instruction sync, no em dashes.

Integration tests in CI on Windows, macOS and Linux:

- Smoke render: 10 seconds from placeholder images and a short test audio. Covers composition, captions, blur, silent and voiceover exports.
- Kokoro: one line generated, length checked, read back by Whisper.
- Narrate mode: a 15 second sample through detect, fixed script, voice, mux and QA.
- Web capture: Playwright records the Recipe Box example headless.

Manual before each release, with a checklist: Chatterbox cloning, Maestro on a real iOS simulator and Android emulator, and full Recipe Box runs driven by Claude Code, Codex and Gemini CLI.

Code quality: ruff for lint and format, mypy for types, tests next to each module.

## 13. Example, tutorial, docs, release

### Recipe Box example

A small web app in plain HTML and JS: browse, search, open a recipe, add to favourites, create a recipe. It ships with a ready spec.yaml and script.yaml, so `reelsmith run examples/recipe-box` builds a full demo, plus a short sample recording to try Narrate mode.

### Tutorial video

A 3 to 4 minute walkthrough of reelsmith made with reelsmith, narrated in a Kokoro stock voice. No personal voice anywhere. Hosted as a GitHub Release asset (and optionally YouTube), previewed in the README, not stored in the repo.

### README outline

Pitch with a preview, why it exists, quick start for Claude Code then other tools, the two modes with short examples, what the interview asks, install per OS and doctor, voice options and the cloning consent policy, FAQ and troubleshooting, dependency licences and credits.

### Repo files

docs/, LICENSE (MIT), CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CHANGELOG, issue and PR templates.

### Release

First version 0.1.0. Each release needs green CI on all three operating systems, the manual checklist, an updated CHANGELOG, matching PyPI and plugin versions, and a GitHub Release with notes and the tutorial video.

Nothing is pushed or published without the owner's explicit approval.

## 14. Licences of key dependencies

| Dependency | Licence | How it is used |
|---|---|---|
| Kokoro (model and ONNX runtime) | Apache 2.0 | downloaded on first use, not bundled |
| Chatterbox | MIT | optional extra, downloaded on first use |
| espeak-ng (shipped by espeakng-loader, a kokoro-onnx dependency) | GPL 3.0 | separate library in its own package, loaded at run time, not part of our code |
| Whisper (faster-whisper) | MIT | local transcription |
| Playwright | Apache 2.0 | web capture and slide rendering |
| Maestro | Apache 2.0 | user installed, mobile automation |
| ffmpeg | LGPL or GPL depending on build | user installed |

## 15. Resolved questions

Checked against current docs on 2026-10-02.

- Plugin layout: `.claude-plugin/plugin.json` (only `name` is required) and `.claude-plugin/marketplace.json` (name, owner, plugins) at the repo root, with the skill in `skills/reelsmith/SKILL.md`. The marketplace is named `reelsmith` and lists the plugin with `"source": "./"`. Skills reach bundled files through `${CLAUDE_PLUGIN_ROOT}`.
- Kokoro ONNX: `kokoro-onnx` supports Python 3.10 to 3.13. It does not need a system espeak-ng. Its dependency `espeakng-loader` ships espeak-ng libraries for Windows, macOS and Linux on x86-64 and arm64. Output is 24 kHz.
- Model downloads: `kokoro-v1.0.int8.onnx` (114 MB, the default) or `kokoro-v1.0.onnx` (326 MB, optional), plus `voices-v1.0.bin` (28 MB). faster-whisper `base.en` (about 145 MB) is the default for the dropped word check, with `small.en` (about 484 MB) as an option.
- Recommended Kokoro voices, by published grade: `af_heart` and `af_bella` (US female), `bf_emma` (UK female), `am_michael` and `am_fenrir` (US male), `bm_george` (UK male). The final list and order are picked by listening during implementation.
