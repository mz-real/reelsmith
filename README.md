# reelsmith

[![CI](https://github.com/mz-real/reelsmith/actions/workflows/ci.yml/badge.svg)](https://github.com/mz-real/reelsmith/actions/workflows/ci.yml)

Narrated demo videos of your app, made on your own machine.

You tell your AI coding tool "make a demo of my app". It asks you a few short questions, writes a plan, and drives the `reelsmith` CLI. reelsmith records the app, voices the script, renders slides, puts it all together and checks the result. You approve the plan and the script before anything is voiced or rendered. Nothing is uploaded.

<!-- preview video: added at release -->

> **Status:** reelsmith 0.1.0 is not released yet. It is not on PyPI and the plugin is not in a published release. You can try it from source today (see [Install](#install)).

## Why it exists

Demo videos take a long time to make by hand: record, write a script, read it out, cut it to the clicks, add captions, export three sizes. Online voice tools want your audio and your money. reelsmith does the whole job locally with open models, and the AI tool you already use runs it for you.

The AI never writes video code. It follows shared instructions and calls one CLI, so the results are the same in Claude Code, Codex, Cursor, Gemini CLI and Copilot.

## Quick start

### Claude Code

```
/plugin marketplace add mz-real/reelsmith
/plugin install reelsmith@reelsmith
```

Then ask: "make a demo of my app". The skill checks for the CLI and offers to install it if it is missing.

### Codex, Cursor, Gemini CLI, Copilot

Install the CLI (see [Install](#install)), then write the instruction files into your project:

```
reelsmith agent install codex      # AGENTS.md
reelsmith agent install cursor     # .cursor/rules/reelsmith.mdc
reelsmith agent install gemini     # GEMINI.md
reelsmith agent install copilot    # .github/copilot-instructions.md
```

The step guides go into `reelsmith-guides/` next to them. Use `--project <path>` to write into a folder other than the current one.

### Any other tool

Paste [`prompts/HANDOVER_PROMPT.md`](prompts/HANDOVER_PROMPT.md) into the chat. It has the full instructions and guides in one file.

## Two modes

The first interview question picks the mode.

**Narrate.** You already have a recording and want a voice that explains each click. reelsmith finds the screen changes and builds contact sheets, the AI proposes a timeline and a script, and you get the same video back with narration. The length stays the same unless you allow held frames or sped up waits.

```
reelsmith init demo
# spec.yaml: mode narrate, one scene with layout full and clip main
reelsmith capture import ~/Movies/invoice.mov demo --id main
reelsmith detect demo --clip main
# the AI marks events in clip.json and writes script.yaml, you approve it
reelsmith run demo
```

**Produce.** The full package: slides for the business logic, browser or phone frames, captions, tap ripples, transitions and several formats. The Recipe Box example is a ready made Produce demo:

```
reelsmith capture web examples/recipe-box/flows/search.py examples/recipe-box --id search
# ...one capture per flow, see examples/recipe-box/README.md
reelsmith run examples/recipe-box
```

`reelsmith run` goes from script check to export and stops at the first error. Add `--preview` for a fast draft with no export.

## What the interview asks

One question at a time, each with suggested answers. Presets (quick feature clip, full app tour, mobile demo, release notes video) skip most of them.

1. Narrate an existing recording, or produce a full demo?
2. What should it show? One feature, a full tour, the mobile app, release notes.
3. Who is watching, and how long? Team, customers or social, 30 s to 5 min.
4. Where does the footage come from? Your recordings, automated web, or automated mobile.
5. Which voice? A Kokoro stock voice, your own voice (Chatterbox), or silent with captions.
6. Format, branding, and anything on screen to blur.

The answers become `spec.yaml` (approval point 1). The narration becomes `script.yaml` (approval point 2).

## Install

You need [uv](https://docs.astral.sh/uv/) and ffmpeg 6 or newer. Python 3.11 to 3.13 is fine, and uv can install it for you.

Until 0.1.0 is on PyPI, install from source:

```
uv tool install git+https://github.com/mz-real/reelsmith
```

Once it is on PyPI this becomes `uv tool install reelsmith`.

Then set up the rest:

| Step | Windows | macOS | Linux |
|---|---|---|---|
| ffmpeg | `winget install ffmpeg` | `brew install ffmpeg` | `sudo apt install ffmpeg` or `sudo dnf install ffmpeg` |
| Browser for web capture and slides | `reelsmith setup browser` | same | same |
| Java 17 or newer (mobile only) | `winget install EclipseAdoptium.Temurin.17.JDK` | `brew install --cask temurin@17` | your distro's OpenJDK 17 package |
| Maestro (mobile only) | see the [Maestro docs](https://docs.maestro.dev/) | `curl -fsSL "https://get.maestro.mobile.dev" \| bash` | same as macOS |

Then check everything:

```
reelsmith doctor
```

doctor checks Python, ffmpeg, the browser, Java, Maestro, adb, the iOS simulator tools, the voice models and the GPU, and prints the fix for your OS. `reelsmith doctor --fix` offers to run those fixes and asks before each one.

More detail per OS, including GPU notes for cloning: [docs/install.md](docs/install.md).

## Voices

**Kokoro stock voices (default).** Small, fast on a laptop CPU, no PyTorch. Good English voices:

| Voice | Accent |
|---|---|
| `af_heart` (default) | US female |
| `af_bella` | US female |
| `bf_emma` | UK female |
| `am_michael` | US male |
| `am_fenrir` | US male |
| `bm_george` | UK male |

Hear a few read the same line:

```
reelsmith voice preview --text "Type a dish into the search box." --voices af_heart,bf_emma,am_michael
```

**Your own voice (Chatterbox).** Optional, through the `clone` extra. It needs PyTorch and Python 3.11 or 3.12:

```
uv tool install --python 3.12 "reelsmith[clone] @ git+https://github.com/mz-real/reelsmith"
```

Once on PyPI: `uv tool install --python 3.12 "reelsmith[clone]"`.

The consent policy, stated plainly:

- Only clone your own voice, or a voice you have the speaker's permission to use.
- `spec.yaml` records that consent as `consent: own` or `consent: permission`. Without it, reelsmith refuses to clone.
- The Chatterbox watermark is always on. reelsmith will not run a build without it.
- Nothing is uploaded. Your sample and the generated audio stay on your machine.

Cloning is supported and covered by tests with stand ins. A real Chatterbox run is on the manual release checklist. More in [docs/voices.md](docs/voices.md).

## Commands

Most commands take the demo folder as an argument and default to the current folder. Every command ends with an `[OK]`, `[WARN]` or `[ERROR]` line and a `Next:` step.

| Command | What it does |
|---|---|
| `reelsmith doctor` | Check Python, ffmpeg, browser, mobile tools, models and GPU. |
| `reelsmith init <dir>` | Create a demo folder with starter spec, brand and script files. |
| `reelsmith capture import <video> --id <id>` | Normalise a recording into `capture/clips/<id>/`. |
| `reelsmith capture web <flow.py> --id <id>` | Record a Playwright flow. `--size`, `--headed`. |
| `reelsmith capture mobile <flow.yaml> --id <id> --platform ios\|android` | Record a Maestro flow. `--device` picks an Android device. |
| `reelsmith detect --clip <id>` | Find screen changes in a clip and write contact sheets. |
| `reelsmith script check` | Check that scenes match spec.yaml and pins name real clip events. |
| `reelsmith voice preview --text "..."` | Read one line in a few Kokoro voices. |
| `reelsmith voice generate` | Voice every line in script.yaml. `--only scene/line` to redo some. |
| `reelsmith voice pick-reference <recording>` | Find the cleanest stretch of a voice recording for cloning. |
| `reelsmith voice compare --refs a.wav,b.wav` | Read a few lines with each reference and recommend one. |
| `reelsmith slides` | Render slides from slides.yaml. |
| `reelsmith compose` | Render each scene and join them into `build/master_<format>.mp4`. `--preview` for a fast 540p draft. |
| `reelsmith qa` | Check the composed video and write `qa/report.md`. |
| `reelsmith export` | Write voiced and silent videos, the narration and an .srt to `out/`. |
| `reelsmith run` | Run every step from script check to export. `--preview` makes a fast draft and skips export. |
| `reelsmith agent install <tool>` | Write instruction files for claude, codex, cursor, gemini or copilot. |
| `reelsmith setup browser` | Install the Chromium build used for web capture and slides. |
| `reelsmith schema export` | Write the JSON Schemas of the file formats. |

Run any command with `--help` for all its options. File formats are described in [docs/formats.md](docs/formats.md).

## FAQ and troubleshooting

**`ffmpeg` not found, or doctor says it is too old.** Install ffmpeg 6 or newer with the command in the install table, then open a new terminal so the PATH updates. `reelsmith doctor` confirms it.

**The first voice run is slow.** The first `voice generate` downloads about 290 MB of models into your user cache: the Kokoro model (114 MB), its voices (28 MB) and the Whisper model that checks for dropped words (about 145 MB). Later runs use the cache.

**Paths on Windows.** Quote paths that contain spaces. In YAML files, use forward slashes (`C:/Users/me/ref.wav`) or single quotes. Inside double quotes a backslash starts an escape, so `"C:\new"` breaks. In PowerShell, set environment variables with `$env:NAME="value"`.

**Cloning is very slow.** Without an NVIDIA GPU or Apple Silicon, Chatterbox runs on the CPU and often takes a minute or more per line. reelsmith warns when it falls back to the CPU. Kokoro stays fast on any machine.

**Android capture stopped at 3 minutes.** `adb screenrecord` stops after 180 seconds, and reelsmith reports an error if a flow runs longer. Split the Maestro flow into several clips.

**iOS capture does not work.** iOS simulators need macOS with Xcode. Android capture works on all three systems with an emulator or a USB device with debugging on. Mobile capture is supported but needs Java, Maestro and a simulator or device. Real device runs are on the manual release checklist.

A command printed a Python traceback? That is a bug. Please [open an issue](https://github.com/mz-real/reelsmith/issues) with the command and its output.

## Licences and credits

reelsmith is MIT licensed. It stands on these projects:

| Dependency | Licence | How it is used |
|---|---|---|
| Kokoro (model and ONNX runtime) | Apache 2.0 | downloaded on first use, not bundled |
| Chatterbox | MIT | optional extra, downloaded on first use |
| espeak-ng (shipped by espeakng-loader, a kokoro-onnx dependency) | GPL 3.0 | separate library in its own package, loaded at run time, not part of our code |
| Whisper (faster-whisper) | MIT | local transcription |
| Playwright | Apache 2.0 | web capture and slide rendering |
| Maestro | Apache 2.0 | user installed, mobile automation |
| ffmpeg | LGPL or GPL depending on build | user installed |

Thanks to everyone who builds and maintains them.

## Contributing, security, licence

- [CONTRIBUTING.md](CONTRIBUTING.md): dev setup, checks and how to add a command.
- [SECURITY.md](SECURITY.md): how to report a vulnerability privately.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- [CHANGELOG.md](CHANGELOG.md)
- [LICENSE](LICENSE): MIT.
