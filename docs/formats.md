# Demo folder and file formats

Everything reelsmith knows about a demo lives in one folder of plain YAML and JSON files. You can read and edit any of them by hand. Unknown fields are an error, so a typo shows up at the next command with the field named.

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
  slides/            rendered slide images, <id>.png
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
theme: dark              # dark, light or minimal
footage: web             # import, web or mobile
voice:
  engine: kokoro         # kokoro, chatterbox or none
  kokoro_voice: af_heart
  speed: 1.0
  sample: null           # chatterbox only: path to the reference, relative to this folder
  consent: null          # chatterbox only: own or permission
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
blur:
  - clip: search
    box: [0.05, 0.10, 0.30, 0.06]   # x, y, width, height as fractions of the frame
    start: 0.0
    end: null                        # null means to the end of the clip
```

Rules worth knowing:

- A `slide` scene needs `slide:`. Every other layout needs `clip:`.
- Use `browser` for web footage, `phone` for mobile footage, `full` for raw recordings and desktop apps.
- `engine: chatterbox` needs both `sample` and `consent`. See [voices.md](voices.md).

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
```

A line is voiced as one piece of audio. Pinned phrases are placed so they start on their event. `reelsmith script check` confirms that the scenes match spec.yaml and that every pin names a real event.

## slides.yaml

Slides for Produce mode. There are four kinds:

```yaml
version: 1
slides:
  - id: intro
    kind: title
    title: Recipe Box
    subtitle: Find, save and cook your favourite dishes
  - id: why
    kind: flow                 # steps shown in order, they build in with the narration
    title: How it works
    steps: [Find a dish, Open it, Save it, Cook it]
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

`reelsmith slides` renders them to `slides/<id>.png` using the theme from spec.yaml and the colours, logo and font from brand.yaml.

## brand.yaml

Optional. Every field can be left out.

```yaml
version: 1
name: My product
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
