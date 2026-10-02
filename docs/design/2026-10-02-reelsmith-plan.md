# reelsmith implementation plan

> For agentic workers: each task is built in its own git worktree from a brief that quotes the task below. Steps use checkbox syntax. Tests come first. Leave changes uncommitted; the owner approves commits once per wave.

**Goal:** build reelsmith 0.1.0 as described in the spec: a Python CLI that records, scripts, voices, composes and checks narrated demo videos locally, plus a Claude Code plugin and instruction files for other AI tools.

**Architecture:** one Python package, `reelsmith`, with one module group per engine component. Each component reads and writes files in a demo folder, and the CLI is a thin typer layer over them. ffmpeg does all media work through argument lists, never a shell string. The timing logic is pure and fully unit tested.

**Tech stack:** Python 3.11 to 3.13, uv, typer, pydantic v2, PyYAML, numpy, soundfile, kokoro-onnx, faster-whisper, playwright, ffmpeg (user installed), Maestro (user installed, mobile only), chatterbox-tts (the `[clone]` extra, Python 3.11 or 3.12). Tooling: ruff, mypy (strict on `src/`), pytest.

**Spec:** `docs/design/2026-10-02-reelsmith-design.md`

## Global constraints

- Python `>=3.11,<3.14`. The `clone` extra uses the environment marker `python_version < "3.13"`.
- Licence MIT. Package name `reelsmith`. Version `0.1.0`. Plugin and CLI share it.
- No em dashes or en dashes in any tracked file. `scripts/check_dashes.py` enforces this in CI.
- Docs, prompts and CLI messages: human tone, short sentences, plain words, no marketing filler.
- No AI attribution anywhere. No code or files copied from other projects.
- Nothing is uploaded. All models run locally. Models download on first use into the user cache dir, with the size shown first.
- Every command ends with the shared result block from `reelsmith.result` (see T1).
- Nothing is overwritten silently: use `reelsmith.fsutil.backup_existing` before writing an output that already exists.
- ffmpeg and other tools are called with `subprocess.run([...])`, never `shell=True`.
- Defaults: Kokoro model `kokoro-v1.0.int8.onnx`, voice `af_heart`, Whisper model `base.en`, loudness target -16 LUFS, max hold 3.0 s, pace window 130 to 210 wpm, output 1080p.
- Windows, macOS and Linux are all supported. Use `pathlib` everywhere and test on all three in CI.

## Review focus

These five inputs are implied by the spec but easy to miss. Each one has a test in the task named.

1. **Paths with spaces, non-ASCII names or Windows separators** passed to ffmpeg must work. Test in T1 (`ffmpeg.probe` on a file named `my demo é.mp4`).
2. **Imported recordings with variable frame rate, odd sizes such as 1171x2532, no audio track, or rotation metadata** must be normalised to constant frame rate and even sizes. Test in T8.
3. **A narration line longer than its gap, with holds turned off,** must give a clear conflict naming the line and how many seconds it is over. It must never drift silently. Test in T2.
4. **A rerun after a crash or with partial outputs** must resume or back up, never overwrite silently. Tests in T1 (`backup_existing`) and T3 (voice skips lines whose audio and hash already match).
5. **A missing optional dependency or no network for a model download** must give a short error with the exact fix command, never a traceback. Tests in T1 (CLI turns `ReelsmithError` into an ERROR block) and T3 (missing model, offline).

## Shared interfaces (all tasks rely on these names)

```python
# reelsmith/result.py (T1)
class Status(StrEnum): OK = "OK"; WARN = "WARN"; ERROR = "ERROR"
@dataclass
class Result:
    status: Status
    message: str
    details: list[str] = field(default_factory=list)
    next_step: str | None = None
def emit(result: Result) -> int  # prints the block below, returns 0 for OK/WARN, 1 for ERROR
```

Result block, always printed last:

```
[OK] Voice generated for 12 lines
  - 2 lines regenerated for pace
Next: reelsmith compose --preview
```

```python
# reelsmith/errors.py (T1)
class ReelsmithError(Exception):
    def __init__(self, message: str, fix: str | None = None) -> None
# The CLI catches it and emits Result(ERROR, message, next_step=fix).

# reelsmith/paths.py (T1)
@dataclass(frozen=True)
class DemoPaths:
    root: Path
    spec: Path; brand: Path; script: Path      # spec.yaml, brand.yaml, script.yaml
    flows: Path; clips: Path                   # capture/flows, capture/clips
    voice: Path; slides: Path; build: Path; qa: Path; out: Path
    @classmethod
    def at(cls, root: Path) -> "DemoPaths"

# reelsmith/fsutil.py (T1)
def backup_existing(path: Path) -> Path | None  # renames to <name>.bak-YYYYmmdd-HHMMSS, returns new path
def cache_dir() -> Path                         # platformdirs user cache dir / "reelsmith"

# reelsmith/media/ffmpeg.py (T1)
@dataclass(frozen=True)
class MediaInfo: duration: float; width: int; height: int; fps: float; has_audio: bool; rotation: int
def require_ffmpeg() -> None                    # raises ReelsmithError with the OS install command
def run_ffmpeg(args: list[str]) -> None         # prepends ffmpeg -y -hide_banner -loglevel error
def probe(path: Path) -> MediaInfo

# reelsmith/models (T2). All pydantic v2, extra="forbid".
SpecModel, BrandModel, ClipModel, Event, ScriptModel, ScriptScene, Line, Phrase
def load_model(path: Path, model: type[M]) -> M     # YAML or JSON by suffix, errors name the field
def save_model(path: Path, obj: BaseModel) -> None  # backs up first

# reelsmith/timing.py (T2), pure functions
def plan_scene(scene: SceneInput, rules: TimingRules) -> SceneTimeline
def caption_duration(text: str) -> float

# reelsmith/voice (T3)
@dataclass
class Audio: samples: np.ndarray; sample_rate: int  # float32 mono
class VoiceEngine(Protocol):
    name: str
    def synthesize(self, text: str, seed: int) -> Audio
def get_engine(spec: SpecModel) -> VoiceEngine
# Output: voice/<scene>__<line>.wav and voice/timings.json (see T3)
```

### File formats (T2 owns the models; everyone else reads them)

`spec.yaml`:

```yaml
version: 1
mode: produce            # narrate | produce
goal: Show how to save a favourite recipe
audience: customers
target_seconds: 90
formats: ["16:9"]        # 16:9 | 9:16 | 1:1
quality: 1080p           # 1080p | 4k
theme: dark              # dark | light | minimal
footage: web             # import | web | mobile
voice:
  engine: kokoro         # kokoro | chatterbox | none
  kokoro_voice: af_heart
  speed: 1.0
  sample: null           # chatterbox only
  consent: null          # chatterbox only: own | permission
options:
  allow_holds: true
  speed_up_waits: false
  captions: burned       # none | burned | srt | both
  highlight_clicks: true
scenes:
  - id: intro
    layout: slide        # slide | phone | browser | full
    slide: intro
  - id: search
    layout: browser
    clip: search
blur:
  - clip: search
    box: [0.05, 0.10, 0.30, 0.06]   # x, y, w, h as fractions of the frame
    start: 0.0
    end: null                        # null means to the end of the clip
```

Validation rules: `voice.engine == chatterbox` needs `sample` and a `consent` value, or loading fails with the message "Cloning needs a voice sample and consent." Scene ids are unique. A `layout: slide` scene needs `slide`. The other layouts need `clip`.

`capture/clips/<id>/clip.json`:

```json
{"id": "search", "video": "video.mp4", "width": 1920, "height": 1080, "fps": 30, "duration": 12.4,
 "events": [{"id": "e1", "t": 2.10, "type": "click", "x": 0.42, "y": 0.18, "label": "Search box"}]}
```

`type` is one of `click | tap | key | scroll | screen | back`. `x` and `y` are fractions of the frame, or null for `screen` and `key`.

`script.yaml`:

```yaml
version: 1
scenes:
  - id: search
    caption: Find a recipe fast
    lines:
      - id: l1
        phrases:
          - text: Type a dish into the search box.
            pin: e1
          - text: Results update as you type.
```

A pin must name an event in that scene's clip. `reelsmith script check` validates this.

`voice/timings.json`:

```json
{"engine": "kokoro", "voice": "af_heart", "lines": [
  {"scene": "search", "line": "l1", "file": "search__l1.wav", "duration": 3.42, "hash": "sha256 of text+voice+speed",
   "phrases": [{"index": 0, "start": 0.0, "end": 1.71}, {"index": 1, "start": 1.93, "end": 3.30}],
   "wpm": 168.0, "transcript_ok": true, "attempts": 1}]}
```

---

## Wave 1

### Task T1: project skeleton (Claude A)

**Files:** `pyproject.toml`, `src/reelsmith/{__init__,__main__,cli,result,errors,paths,fsutil}.py`, `src/reelsmith/media/{__init__,ffmpeg}.py`, `scripts/check_dashes.py`, `tests/test_{result,errors_cli,paths,fsutil,check_dashes}.py`, `tests/media/test_ffmpeg.py`, `tests/conftest.py` (fixture `tiny_video` built with ffmpeg testsrc, 2 s, 320x240, with a sine audio track), `.github/workflows/ci.yml`, `LICENSE`, `.gitignore` additions.

**Produces:** everything in "Shared interfaces" marked T1, plus `reelsmith --version` and a `cli.app` typer instance. Later tasks add commands by creating `src/reelsmith/commands/<name>.py` with `def register(app: typer.Typer) -> None`. `cli.py` imports and registers each module listed in `COMMANDS`.

- [ ] Write the tests first:
  - `emit` prints `[OK] msg`, the indented details and `Next:` in that order, and returns 0, 0 and 1 for OK, WARN and ERROR.
  - A command raising `ReelsmithError("x", fix="brew install ffmpeg")` exits 1 and prints `[ERROR] x` and `Next: brew install ffmpeg`, with no traceback.
  - `backup_existing` returns None for a missing path. For a file and for a folder it renames, and the original name is free afterwards.
  - `probe` works on `tiny_video` copied to `my demo é.mp4`: duration 2.0 ± 0.1, 320x240, has_audio is True.
  - `check_dashes.py` exits 1 and prints `file:line` for a temp file containing U+2014. It exits 0 on a clean tree and skips `.git` and binary files.
- [ ] Run them and see them fail.
- [ ] Implement. `pyproject` uses hatchling and has `[project.scripts] reelsmith = "reelsmith.cli:main"`. Playwright is a core dependency. The only extra is `clone = ["chatterbox-tts; python_version < '3.13'", "setuptools<81"]`. Dev group: pytest, ruff, mypy, types-PyYAML.
- [ ] CI: a matrix of ubuntu-latest, macos-latest and windows-latest on Python 3.11 and 3.13. Install ffmpeg per OS (apt, brew, choco). Steps: `uv sync`, ruff check, ruff format --check, mypy src, pytest, check_dashes.
- [ ] Run the full check command and get PASS.

### Task T5: Recipe Box example app (Cursor 2, no dependency on T1)

**Files:** only `examples/recipe-box/app/` (`index.html`, `app.js`, `styles.css`, `recipes.json`).

- [ ] Plain HTML, CSS and JS, no build step and no external CDN. It must work from `python -m http.server` and from `file://`. For `file://`, embed the recipes in `app.js` as a fallback.
- [ ] Features: a grid of 8 recipes with emoji or CSS art (no external images), a search box filtering by title and ingredient as you type, a recipe detail view with ingredients and steps, a favourite toggle and a Favourites tab (stored in localStorage), and a "New recipe" form that adds a recipe to the list.
- [ ] Every interactive element has a stable `data-testid`: `search-input`, `recipe-card-<slug>`, `favourite-toggle`, `tab-all`, `tab-favourites`, `new-recipe-button`, `new-recipe-title`, `new-recipe-ingredients`, `new-recipe-steps`, `new-recipe-save`, `back-button`.
- [ ] It looks clean at 1280x720 and at 390x844 (phone).
- [ ] Original recipe text, written fresh. No dashes.
- [ ] Verify with a Playwright screenshot at both sizes, saved to the scratchpad, not the repo.

---

## Wave 2 (after T1 merges)

### Task T2: models and timing engine (Claude A)

**Files:** `src/reelsmith/models/{__init__,common,spec,brand,clip,script,io}.py`, `src/reelsmith/timing.py`, `src/reelsmith/commands/{schema,script_check}.py`, `schemas/*.schema.json` (generated), `tests/models/*`, `tests/test_timing.py`.

**Consumes:** T1 `ReelsmithError`, `backup_existing`, `DemoPaths`.

**Produces:** the models and formats above, plus:

```python
@dataclass(frozen=True)
class TimingRules:
    max_hold: float = 3.0; allow_holds: bool = True; speed_up_waits: bool = False
    pin_lead: float = 0.25      # a pinned phrase may start this early before its event
    pin_late: float = 0.40      # and must start no later than this after it
    breath: float = 0.35        # gap after the last phrase of a scene
    phrase_gap: float = 0.15
    max_speed: float = 4.0; min_wait_to_speed: float = 2.5
@dataclass(frozen=True)
class PhraseInput: index: int; duration: float; pin_time: float | None   # pin_time is in clip time
@dataclass(frozen=True)
class SceneInput: scene_id: str; clip_duration: float | None; phrases: list[PhraseInput]   # None means a slide
@dataclass(frozen=True)
class Segment: kind: Literal["play", "hold"]; src_start: float; src_end: float; speed: float; out_start: float; out_end: float
@dataclass(frozen=True)
class Placement: index: int; out_start: float; out_end: float
@dataclass(frozen=True)
class Conflict: phrase_index: int; seconds_over: float; reason: str
@dataclass(frozen=True)
class SceneTimeline: scene_id: str; segments: list[Segment]; placements: list[Placement]; duration: float; conflicts: list[Conflict]
def plan_scene(scene: SceneInput, rules: TimingRules) -> SceneTimeline
def caption_duration(text: str) -> float   # max(1.5, words / 2.8 + 0.5)
```

The rules `plan_scene` must follow, one test each:
- An unpinned phrase starts at the previous phrase end plus `phrase_gap`.
- A pinned phrase starts at `max(event_out_time - pin_lead, previous_end + phrase_gap)`.
- If that is later than `event_out_time + pin_late` and holds are allowed, insert a hold just before the event, long enough that the phrase starts at `event_out_time - pin_lead`. If that hold would be over `max_hold`, cap it and add a Conflict with the seconds left over.
- If holds are not allowed, add `Conflict(index, seconds_over, "line too long for the gap before its event")`. This is review focus item 3.
- With `speed_up_waits`, a stretch of video longer than `min_wait_to_speed` with no narration and no event plays faster, up to `max_speed`, but never past an event.
- Scene duration is `max(end of video in output time, last phrase end + breath)`. Any extra time is a hold of the last frame. If that hold is over `max_hold`, add a Conflict.
- For a slide scene (`clip_duration=None`), the duration is the last phrase end plus breath, with one play segment of that length.
- Output segments are contiguous and their `out_*` times add up to `duration`.

Steps: write tests for each rule above, plus model tests (the chatterbox-without-consent error, unique ids, pins referencing missing events caught by `script check`, round trip save and load). Watch them fail. Implement. Add `reelsmith schema export` to write `schemas/` and a test that the files match the models. Add `reelsmith script check [DIR]`. Run the full checks.

### Task T3: voice core with Kokoro (Claude B)

**Files:** `src/reelsmith/voice/{__init__,base,kokoro_engine,models_dl,quality,transcribe,align,pipeline}.py`, `src/reelsmith/commands/voice.py`, `tests/voice/*`.

**Consumes:** T1 interfaces. It reads `script.yaml` and `spec.yaml` through T2 models. Until T2 lands, use a local minimal loader behind the same names and swap it at merge (the brief says this).

**Produces:**
- `models_dl.ensure_model(name) -> Path`. Downloads to `cache_dir()/models` with the size shown first and a sha256 check. Offline or a failed download raises `ReelsmithError` with the exact retry command and a manual download URL.
- `quality.words_per_minute(text, seconds)`, `quality.pace_ok(wpm, low=130, high=210)`.
- `quality.trim_tail(audio, silence_db=-45, min_silence=0.25) -> Audio`. It cuts only after sustained silence and keeps a 60 ms tail.
- `transcribe.transcribe(audio) -> list[Word(text, start, end)]` with faster-whisper `base.en`, word timestamps, on CPU, using int8.
- `quality.transcript_matches(expected, words) -> tuple[bool, list[str]]`. It normalises case, punctuation and numbers to words, and returns the missing words.
- `align.phrase_bounds(phrases, words, audio) -> list[tuple[float, float]]`. It maps each phrase to its word span, then moves each cut to the quietest point between words.
- `pipeline.generate(paths, spec, script, only: set[str] | None) -> VoiceReport`. Per line: synthesize, then trim, then the pace check (on failure, retry with a new seed up to 3 times), then the transcript check (same retries), then align. It writes the wav and `timings.json`. It skips a line whose hash matches and whose wav exists (review focus item 4).
- Commands: `voice generate [--only scene/line]` and `voice preview --text "..." --voices af_heart,bf_emma,am_michael`, which writes `voice/preview/<voice>.wav`.

Steps: write the tests first, using synthetic audio (numpy tones and silence) for `trim_tail`, pace and alignment, and a fake `VoiceEngine` and fake transcriber for the pipeline retry and skip logic. Mark a single real Kokoro and Whisper test with `@pytest.mark.models`, skipped unless `REELSMITH_TEST_MODELS=1`. Implement. Run that marked test locally once and report the result.

### Task T4: doctor, init, setup browser (Cursor 1)

**Files:** `src/reelsmith/doctor/{__init__,checks,fixes}.py`, `src/reelsmith/commands/{doctor,init,setup}.py`, `src/reelsmith/templates/starter/{spec.yaml,brand.yaml,script.yaml}`, `tests/doctor/*`, `tests/test_init.py`.

**Checks** (each returns `Check(name, status, found, fix)`):
- Python version.
- ffmpeg present, with a version of 6 or newer.
- Playwright Chromium installed.
- Java 17 or newer and Maestro (mobile only, a WARN if missing).
- On macOS, xcrun simctl.
- adb.
- Kokoro and Whisper models cached.
- Chatterbox importable (only if the spec asks for it).
- GPU: CUDA via `nvidia-smi`, or Apple Silicon via `platform.machine()`.
- Plugin version vs CLI version, read from the env var `REELSMITH_EXPECTED_VERSION` if set.

Fix commands per OS: winget, brew, and apt or dnf for ffmpeg; `reelsmith setup browser` for Chromium; Temurin 17 for Java; Maestro's official install command. `doctor --fix` lists what it will run, asks y/n per item, and says when admin rights are needed. `--yes` skips the prompts. `init DIR` copies the starter files and creates the folder tree from `DemoPaths`. It refuses a non-empty folder unless `--force`. `setup browser` runs `playwright install chromium`.

Tests mock `shutil.which`, `subprocess.run` and `platform.system()` for all three operating systems.

---

## Wave 3 (after wave 2 merges)

### Task T6: compose and export (Claude A)

**Files:** `src/reelsmith/compose/{__init__,layouts,graph,captions,ripples,blur,transitions,cache,master}.py`, `src/reelsmith/export.py`, `src/reelsmith/commands/{compose,export}.py`, `src/reelsmith/assets/frames/*.png` (browser and phone frames drawn by our own code with Pillow at build time, not downloaded), `tests/compose/*`.

**Consumes:** `SceneTimeline` from T2, `timings.json` from T3, `slides/<id>.png` from T9, and clips.

**Behaviour:**
- Each scene renders to `build/scenes/<id>-<hash>.mp4` from its timeline: play segments (`setpts` for speed), holds (`tpad` or a looped still), the layout, burned captions (drawtext with the theme font, wrapped to the panel width), tap ripples at event x and y, an Android Back badge on `back` events, blur boxes (crop, boxblur, overlay) applied before layout, and a slow zoom on slides.
- Narration is placed at each placement's `out_start` with `adelay` and `amix`.
- Scenes are joined with a 0.4 s xfade, and the result is loudness-normalised with `loudnorm` I=-16 TP=-1.5.
- `--preview` renders 540p with ultrafast, ignoring the cache.
- The cache key is a hash of the scene inputs, so unchanged scenes are reused.
- Output: `build/master_<format>.mp4`.
- `export` writes `out/<name>_<format>.mp4`, `out/<name>_<format>_silent.mp4`, `out/<name>_narration.wav` and `out/<name>.srt` from the placements. It backs up existing files.

**Tests:** graph builder unit tests on the argument lists, caption wrapping, srt timing from placements, and the cache hit and miss. One smoke render test (10 s from placeholder PNGs and a test tone) checks duration, resolution and the audio stream in both versions.

### Task T7: qa and detect (Claude B)

**Files:** `src/reelsmith/qa/{__init__,checks,report,contact}.py`, `src/reelsmith/detect.py`, `src/reelsmith/commands/{qa,detect}.py`, `tests/qa/*`, `tests/test_detect.py`.

**qa** runs the 9 checks from spec section 9 and writes `qa/report.md` with PASS or FAIL per check plus a suggested fix for each FAIL. It exits with ERROR if any check fails.
- Transcript vs script: Whisper over each master's narration track.
- Sync: phrase start vs pinned event, within the pin window.
- Cut off lines: any placement past the scene end.
- End of line noise: energy after the last word.
- Loudness: ebur128 within ±1.5 of -16, true peak at or below -1.
- Hold limits.
- Captions: overflow and minimum duration.
- Blur: sample frames inside each box should have low high-frequency energy.
- Contact sheets: `qa/sheets/*.jpg` at each scene start, event and transition, built with ffmpeg tile.

**detect** runs ffmpeg `select='gt(scene,0.08)'` with showinfo, plus a minimum spacing. It writes `capture/clips/<id>/detected.json` and timestamped contact sheets that the AI reads to propose events.

### Task T8: capture import and capture web (Cursor 1)

**Files:** `src/reelsmith/capture/{__init__,importer,web,events}.py`, `src/reelsmith/commands/capture.py`, `tests/capture/*`.

- **import:** normalises to constant frame rate (30 fps), even width and height, applied rotation, H.264 yuv420p and AAC (or silent). It writes `clips/<id>/video.mp4` and a `clip.json` with no events. Review focus item 2 has its tests here, using generated VFR, odd-size, rotated and no-audio inputs.
- **web:** `capture web FLOW.py --id ID [--headed] [--size 1280x720]`. The flow is a Python file defining `async def flow(page, log)`. reelsmith starts Chromium with `record_video_dir`. Helper functions `log.click(locator, label)`, `log.type(locator, text, label)`, `log.key(name)` and `log.screen(label)` perform the action and record the time (from the video start) and the element centre as fractions. The video is converted to mp4 at the end. The test runs a tiny local HTML page headless and checks that the event times are inside the video duration.

### Task T9: slides (Cursor 2)

**Files:** `src/reelsmith/slides/{__init__,render,themes}.py`, `src/reelsmith/slides/templates/{title,flow,chart,bullets}.html`, `src/reelsmith/commands/slides.py`, `tests/slides/*`.

- `slides.yaml` in the demo folder lists slides: `id`, `kind` (title, flow, chart or bullets) and its content. A flow has `steps` and `exits` chips, and its arrows only join real sequence steps. A chart has bars or lines with labels.
- `slides` renders `slides/<id>.png` plus per step images `slides/<id>_step<n>.png` for build steps, so the step cue count is the number of steps minus 1. Rendering uses Playwright at the format size.
- Themes: dark, light and minimal, overridden by `brand.yaml` (colours, logo path, font family, local font files only).
- Tests: template variable rendering in HTML, step cue count, brand override, and one real render checking the PNG size.

---

## Wave 4 (after wave 3 merges)

- **T10, Claude A:**
  - The Chatterbox engine behind `VoiceEngine` in `voice/chatterbox_engine.py`. It imports only if the extra is installed and otherwise raises an error with `uv tool install "reelsmith[clone]"`.
  - The consent check is enforced in the engine too, not only in the model. The watermark stays on.
  - `voice pick-reference IN --out ref.wav`: picks the 12 s window with the best speech ratio, the lowest noise floor and no clipping.
  - `voice compare --refs a.wav,b.wav --lines 3`: scores similarity (the cosine of MFCC means, no extra dependency) and pace, then recommends one.
  - `run DIR`: runs every step in order and stops at the first ERROR.
- **T11, Claude B:**
  - `instructions/` source files: entry plus references for interview, narrate, capture web, capture mobile, script writing, voice, QA and troubleshooting. Every guide has the same sections. The rules are copied from spec section 10.
  - `scripts/gen_instructions.py` builds `skills/reelsmith/SKILL.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `AGENTS.md`, `.cursor/rules/reelsmith.mdc`, `GEMINI.md`, `.github/copilot-instructions.md` and `prompts/HANDOVER_PROMPT.md`.
  - `agent install <tool>` writes the right file into the user's project.
  - A CI drift check runs the generator and then `git diff --exit-code`.
- **T12, Cursor 1:** `capture mobile FLOW.yaml --platform ios|android --id ID`.
  - Start the recorder: `xcrun simctl io booted recordVideo` or `adb shell screenrecord`, pulled at the end.
  - Run `maestro test` with `--format` output and parse the step timestamps into tap events. Fall back to the command start times.
  - Stop the recorder. Never use Maestro cloud or Maestro's own recording.
  - Tests use mocked subprocesses. Real devices are on the manual checklist.
- **T13, Cursor 2:**
  - Write `examples/recipe-box/{spec.yaml,slides.yaml,script.yaml,flows/*.py}` and a 15 s sample recording, captured by our own web capture, for Narrate mode.
  - Add the CI integration jobs: smoke render, a Kokoro line read back by Whisper, the Narrate path, and headless web capture.

## Wave 5

- **T14, Cursor:** CONTRIBUTING, CODE_OF_CONDUCT (Contributor Covenant 2.1), SECURITY, CHANGELOG (0.1.0) and issue and PR templates.
- **T15, Claude:** the README following the spec section 13 outline, plus `docs/` install per OS, the voice and consent policy, and the FAQ.
- **Me:** a full `reelsmith run examples/recipe-box`, QA by viewing frames and transcribing every line, and a scan for employer terms, `co-authored` and voice files. Then the release checklist for the owner.

## Spec coverage check

| Spec section | Tasks |
|---|---|
| 1 What we are building | all |
| 2 Modes | T7 detect, T6, T13 |
| 3 UX and approvals | T11 |
| 4 Components and commands | T1, T4, T8, T12, T2, T3, T9, T6, T7, T10 |
| 5 Formats | T2 |
| 6 Capture | T8, T12 |
| 7 Voice | T3, T10 |
| 8 Look and assembly | T6, T9 |
| 9 QA and errors | T7, T1 |
| 10 Instructions | T11 |
| 11 Install | T1, T4, T11 |
| 12 Testing and CI | T1, T13 |
| 13 Example and docs | T5, T13, T14, T15 |
| 14 Licences | T15 |
