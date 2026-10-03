# Demo folder and file formats

Everything reelsmith knows about a demo lives in one folder of plain YAML and JSON files. You can read and edit any of them by hand. Unknown fields are an error, so a typo shows up at the next command with the field named.

## Ids

A scene, line, clip, event or slide id (and a `--id` or `--clip` option on the command line) must match `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`: letters, numbers, `-` and `_`, starting with a letter or number, at most 64 characters. Ids end up directly in file and folder names (`voice/<scene>__<line>.wav`, `slides/<id>_step<n>.png`, `capture/clips/<id>/`), so this rule is also what keeps an id from turning into a path such as `../elsewhere`. An id with a space, a dot, a slash or any other character outside that set is rejected before anything is read or written, with the message "Ids may use letters, numbers, - and _ and start with a letter or number."

## The demo folder

`reelsmith init demo` creates the files and empty folders. The files inside the folders appear as each step runs.

```
demo/
  spec.yaml          the plan (approval point 1)
  brand.yaml         name, logo, colours, font (optional)
  script.yaml        narration per scene (approval point 2)
  slides.yaml        slide definitions (Produce mode, optional)
  capture/
    flows/           Playwright flows (.py) or Maestro flows (.yaml)
    clips/
      <id>/
        video.mp4    the normalised recording
        clip.json    size, length and events
        detected.json, sheets/   written by reelsmith detect
  voice/             one wav per line, plus timings.json
    preview/         voice preview files
    compare/         voice compare output
  slides/            rendered slides: slides/<format>/<id>_step<n>.png and .mp4, and <id>.png
  build/             working files and master_<format>.mp4, safe to delete
  qa/                report.md and contact sheets
  out/               final videos, narration and .srt
```

`reelsmith export` writes these to `out/`, using the folder name unless you pass `--name`:

```
out/
  demo_16x9.mp4           with narration
  demo_16x9_silent.mp4    without narration
  demo_narration.wav      narration only
  demo.srt                captions
```

There is one pair of videos per format in spec.yaml (`16x9`, `9x16`, `1x1`).

With `voice.engine: none` the video already has no narration, so `demo_16x9_silent.mp4` and `demo_narration.wav` would only duplicate it or record silence. Export leaves both out and notes why; you get `demo_16x9.mp4` and `demo.srt` only.

reelsmith never overwrites output silently. The previous file is kept next to the new one as `<name>.bak-<date>-<time>`.

## spec.yaml

The plan. The AI writes it from the interview and you approve it.

```yaml
version: 1
mode: produce            # produce or narrate
goal: Show how to save a favourite recipe
audience: customers
target_seconds: 90
formats: ["16:9"]        # any of 16:9, 9:16, 1:1
quality: 1080p           # 1080p or 4k
theme: studio            # studio (the default), dark, light or minimal
footage: web             # import, web or mobile
voice:
  engine: kokoro         # kokoro, chatterbox or none
  kokoro_voice: af_heart
  speed: 1.0
  sample: null           # chatterbox only: path to the reference, relative to this folder
  consent: null          # chatterbox only: own or permission
  vocabulary: []         # rare words the voice says, such as product names
  pronounce: {}          # kokoro only: word to phonemes, for a word plain text still says wrong
options:
  allow_holds: true      # may hold the last frame when a line needs more time
  speed_up_waits: false  # may speed up long waits
  captions: burned       # none, burned, srt or both
  highlight_clicks: true
scenes:                  # in playing order
  - id: intro
    layout: slide        # slide, phone, browser or full
    slide: intro         # a slide id in slides.yaml
  - id: search
    layout: browser
    clip: search         # a clip id under capture/clips/
    eyebrow: Step 1      # optional: small label above the title
    title: Find a dish *fast*   # optional: *stars* draw words in the accent colour
    points:              # optional: shown beside the footage instead of the spoken words
      - text: Search by *name* or ingredient
        line: search-2   # appears when this script line starts, then stays
    zoom:                # optional: ease in to a region around a moment
      - box: [0.55, 0.0, 0.45, 0.25]   # x, y, width, height as fractions of the clip
        at: e2           # an event id, or seconds in clip time
        hold: 1.5        # seconds to stay zoomed after the moment
    cursor: true         # optional: a drawn pointer that moves to each click
blur:
  - clip: search
    box: [0.05, 0.10, 0.30, 0.06]   # x, y, width, height as fractions of the frame
    start: 0.0
    end: null                        # null means to the end of the clip
```

Rules worth knowing:

- A `slide` scene needs `slide:`. Every other layout needs `clip:`.
- Use `browser` for web footage, `phone` for mobile footage, `full` for raw recordings and desktop apps.
- `eyebrow`, `title`, `points`, `zoom` and `cursor` only work on footage scenes (phone, browser, full).
- With points, the panel shows the eyebrow, title and points in the Studio look, and the spoken words go to the srt only. Set `options.captions: burned` to also burn them as subtitles under the footage.
- Each point names a line id from the same scene in script.yaml.
- A zoom is fully in a quarter second before its moment, holds, then eases out. It zooms the footage only, never the frame or the panel. Keep boxes to about half the frame or larger, since a closer zoom makes the recording soft. The zoom is at most 2.5 times.
- The cursor is on by default for web footage in `browser` and `full` scenes. It arrives just before each click and the click pulses in the accent colour. Set `cursor: false` to turn it off. Phone scenes show a tap pulse instead.
- Web pages recorded at phone size get a drawn status bar above them in the `phone` frame, so nothing sits under the camera cutout.
- `engine: chatterbox` needs both `sample` and `consent`. See [voices.md](voices.md).
- `vocabulary` lists rare words such as your product name. They are passed to the speech model that checks the narration, as hints. Unusual words in the script (capitalised in mid sentence, or with digits, dots or underscores) are added for you.
- `pronounce` maps a whole word, matched without regard to case, to the Kokoro or espeak phonemes it should be read as. Use it when a word still sounds wrong with plain text, for example a product name. It only works with the `kokoro` engine: Chatterbox cannot read phonemes, so it warns and ignores the map, use a phrase's `say` for it instead. Find a word's phonemes with `uv run python -c "from kokoro_onnx.tokenizer import Tokenizer; print(Tokenizer().phonemize('reelsmith', 'en-us'))"`, then adjust spacing or symbols in the result to fix the sound, for example `ɹˈiːl smɪθ` instead of `ɹˈiːlsmɪθ` to say "REEL-smith" instead of "realsmith".

## script.yaml

The narration. Each scene in spec.yaml has a matching scene here. Each scene has lines, and each line is split into phrases.

```yaml
version: 1
scenes:
  - id: search                 # same id as the scene in spec.yaml
    caption: Search            # shown in the caption panel
    lines:
      - id: search-1           # voice/search__search-1.wav
        phrases:
          - text: Start on the full list of sample recipes.
      - id: search-2
        phrases:
          - text: Type tomato in the search box.
            pin: e2            # lands on event e2 in this scene's clip.json
  - id: favourite
    caption: Favourites
    lines:
      - id: fav-2
        phrases:               # one line, two pinned phrases
          - text: Go back to the list,
            pin: e3
          - text: and open the Favourites tab.
            pin: e4
      - id: fav-3
        phrases:
          - text: Then run reelsmith qa.
            say: Then run reelsmith Q A.   # what the voice reads
```

A line is voiced as one piece of audio. Pinned phrases are placed so they start on their event. `reelsmith script check` confirms that the scenes match spec.yaml and that every pin names a real event.

`say` is optional. The captions and the srt show `text`; the voice reads `say`, and the transcript checks compare against it. Use it for acronyms, file names (`spec.yaml` as "spec dot yaml") and command words. `reelsmith script check` warns when `say` reads very differently from `text`.

## slides.yaml

Slides for Produce mode. There are eleven kinds. The first four:

```yaml
version: 1
slides:
  - id: intro
    kind: title
    title: Recipe Box
    subtitle: Find, save and cook your favourite dishes
  - id: why
    kind: flow                 # steps shown in order, they build in with the narration
    eyebrow: The basics        # optional small label above the title
    title: How it *works*      # *words* are drawn in the accent colour, \* is a plain star
    subtitle: Four steps, about a minute
    chapter: 1                 # optional big faded number, top right
    step_style: dim            # dim (future steps faded) or reveal (hidden until their step)
    steps:
      - title: Find a dish
        detail: Search by name or ingredient   # optional one line under the title
      - Open it                # a plain string works too
      - Save it
      - Cook it
    exits: []                  # optional labels, shown once every step is in
  - id: growth
    kind: chart
    title: Recipes saved per week
    chart_type: bars           # bars or lines
    labels: [W1, W2, W3]
    values: [12, 30, 45]       # same length as labels
  - id: outro
    kind: bullets
    title: You are ready
    items:
      - Search by title or ingredient
      - Save recipes to Favourites
```

Every kind takes the optional `eyebrow`, `subtitle`, `chapter` and `step_style` fields shown on the flow. In a flow without an `eyebrow`, the label counts the steps ("Step 2 of 4"). A flow step can take `accent: true` to stay lit in the accent once it is reached, for example the steps where you approve.

A title can list what comes next as chips, and with a `chapter` it shows the number large beside the title:

```yaml
  - id: ch1
    kind: title
    chapter: 1
    eyebrow: Chapter 1
    title: How it *works*
    coming_up: [The pieces, The result block]   # up to 6 chips
```

The other seven kinds are drawn in the Studio look, even with an older theme. Each one builds in step by step. Steps count from 1, the way the narration does.

**cards**: 2 to 6 cards in a grid, one card per step. `icon` is a name from the built in set (for example `lock`, `chat`, `terminal`, `shield`, `mic`, `phone`, `browser`; the schema lists them all). `number` is filled in as 01, 02 and so on when left out.

```yaml
  - id: overview
    kind: cards
    title: Demo videos, made *on your machine*
    cards:
      - icon: lock
        title: Runs locally
        detail: Nothing is uploaded.        # optional
        chips: [Kokoro, Whisper]            # optional
        accent: true                        # optional, stays lit
      - icon: chat
        title: Your AI tool drives it
```

**architecture**: boxes in columns joined by arrows. `layout` lists the columns, left to right (top to bottom in 9:16 and 1:1). Each node is one step, in layout order, and an arrow draws in when both of its ends are in. `chips` puts a group of parts inside a node.

```yaml
  - id: how
    kind: architecture
    nodes:
      - {id: you, icon: user, label: You, detail: Ask for a demo}
      - {id: cli, icon: terminal, label: reelsmith CLI}
      - {id: engine, icon: gear, label: The engine, chips: [Capture, Voice, QA]}
    layout: [[you], [cli], [engine]]
    edges:
      - {from: you, to: cli, label: asks}   # label is optional
      - {from: cli, to: engine}
```

**code**: a terminal or file card. `file` is the title bar label; a `.yaml` or `.json` name picks that highlighting, `terminal` picks the shell one, which colours `[OK]`, `[WARN]`, `[ERROR]` and `Next:` lines. Set `language` (`yaml`, `json`, `shell` or `text`) to choose it yourself. `highlight` lists `[step, [line numbers]]`: those lines brighten and the others dim. The slide has as many steps as the highest step named.

```yaml
  - id: result
    kind: code
    file: terminal
    code: |
      $ reelsmith slides
      [OK] Rendered 4 slide(s) in 1 format
      Next: reelsmith compose --preview
    highlight:
      - [1, [2]]
      - [2, [3]]
```

**timeline**: a track in seconds. `markers` are the clicks, `phrases` are bars on a lane above, `holds` are hatched blocks on the track and `conflicts` are red markers. A phrase with `pin` (a marker `id` or `label`) snaps onto that marker. Steps: the track, then the phrases slide in, then the holds, then the conflicts. `duration` is the track length; left out, it fits the content.

```yaml
  - id: timing
    kind: timeline
    duration: 12
    markers: [{id: e1, t: 1.5, label: Search box}]
    phrases: [{start: 1.5, end: 3.3, label: "Tap the search box,", pin: e1}]
    holds: [{at: 6.8, seconds: 1.2}]
    conflicts: [{at: 10.6, label: "0.8 s over"}]
```

**compare**: rows of `before` and `now`, with a cross and a tick, one row per step. `before_label` and `now_label` change the column names (Before and Now).

```yaml
  - id: fixed
    kind: compare
    rows:
      - {before: The voice runs ahead of the click, now: Every phrase lands on its click}
```

**stats**: a hero number that counts up as the slide comes in, then metric cards one per step, then chips in one step. A metric `bar` is a fill from 0 to 1, or a band `[from, to]`.

```yaml
  - id: qa
    kind: stats
    hero: {value: 9, label: checks on the finished video}   # also of: and suffix:
    metrics:
      - {label: Pace, value: 130 to 210 words a minute, bar: [0.5, 0.81]}
    chips: [Sync, Loudness, Captions]
```

**gallery**: 2 or 3 images side by side in device frames, one image per step. Paths are relative to the demo folder. The frame follows the image shape (a phone for tall, a browser for wide); set `frame` to `phone`, `browser` or `plain` to choose.

```yaml
  - id: formats
    kind: gallery
    images:
      - {image: images/wide.png, label: "16:9 wide"}
      - {image: images/tall.png, label: "9:16 vertical"}
```

`reelsmith slides` renders each slide once per format in spec.yaml, under `slides/16x9/`, `slides/9x16/` and `slides/1x1/` at that format's pixel size. Each build step gets a still, `<id>_step<n>.png`, and its intro animation, `<id>_step<n>.mp4` (0.7 s). Step 0 is the slide's entrance. `<id>.png` is the finished slide. Compose plays each clip when its phrase starts, then holds the still. The first format's images are also copied to `slides/` for older demos. Theme comes from spec.yaml, colours, logo and font from brand.yaml.

The `studio` theme is a deep gradient with soft glows, large left aligned titles and cards. Its accent is brand.yaml `colors.accent` (or `colors.primary`), teal by default. The footer shows brand.yaml `name` and the spec `goal` (or brand.yaml `tagline`).

## brand.yaml

Optional. Every field can be left out.

```yaml
version: 1
name: My product
tagline: null              # short line for the studio slide footer, when spec.yaml has no goal
logo: null                 # path to a local image
colors:                    # #rrggbb, any of primary, secondary, accent, background, text
  primary: "#2563eb"
  background: "#0f172a"
  text: "#f8fafc"
font:
  family: system-ui
  files: []                # local font files only
```

## clip.json

One per clip, in `capture/clips/<id>/`. Capture writes it. Web and mobile capture log events as they happen. `capture import` writes no events: in Narrate mode the AI adds them from the contact sheets that `reelsmith detect` makes, or you add rough times by hand.

```json
{
  "id": "search",
  "video": "video.mp4",
  "width": 1280,
  "height": 720,
  "fps": 30.0,
  "duration": 6.4,
  "events": [
    { "id": "e1", "t": 0.6, "type": "screen", "label": "all recipes" },
    { "id": "e2", "t": 1.2, "type": "click", "x": 0.5, "y": 0.12, "label": "search box" },
    { "id": "e3", "t": 3.1, "type": "screen", "label": "filtered tomato recipes" }
  ]
}
```

- `t` is seconds from the start of the clip and must not be past `duration`.
- `type` is one of `click`, `tap`, `key`, `scroll`, `screen` or `back`.
- `x` and `y` are fractions of the frame, from 0 to 1. `click` and `tap` need them. Other types may leave them out, but give both or neither.
- Event ids must be unique in the clip. Phrases in script.yaml pin to them.

## JSON Schemas

Every format has a JSON Schema in [`schemas/`](../schemas):

- `spec.schema.json`
- `script.schema.json`
- `slides.schema.json`
- `brand.schema.json`
- `clip.schema.json`

Point your editor's YAML or JSON support at them for completion and checks as you type. To write a fresh copy from your installed version:

```
reelsmith schema export --out schemas
```
