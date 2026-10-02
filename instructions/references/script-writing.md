# Write the script

## Goal

Write the words the viewer hears and reads: script.yaml for every scene, and slides.yaml for the slides in Produce mode. Each phrase lands on the action it talks about. This ends at approval point 2: nothing is voiced or rendered until the user approves the script.

## Rules

{{rules}}

## What to ask or check

- Read each clip's `capture/clips/<id>/clip.json` first. The events (id, time, label) are what you pin to. Do not write about anything that is not in the clip.
- Read the app's code for what each step really does, so you can explain the business logic: what the user gets and why it matters. Then point at the screen.
- If the user shared a sample of how they talk, match its tone and words. Otherwise write plainly, like a colleague showing a feature.
- Check the length against `target_seconds` in spec.yaml. Narration runs at about 150 to 170 words per minute, so 90 seconds is about 230 words in total.

## Commands

**script.yaml.** One entry per spec.yaml scene, same ids. Each line is split into phrases. A phrase with `pin:` starts on that event of the scene's clip.

```yaml
version: 1
scenes:
  - id: intro
    caption: Recipes you keep coming back to
    lines:
      - id: l1
        phrases:
          - text: Recipe Box keeps the recipes you cook most in one place.
  - id: search
    caption: Find a recipe fast
    lines:
      - id: l1
        phrases:
          - text: Type a dish into the search box.
            pin: e2
          - text: The list filters as you type.
            pin: e3
      - id: l2
        phrases:
          - text: Open a recipe to see the ingredients and steps.
            pin: e4
```

- `caption` is the short side caption for the scene. Keep it under about eight words.
- Line ids must be unique inside a scene. Phrases in one line are voiced together, so keep a line to one or two sentences.
- Slide scenes cannot have pins. Their build steps (flow steps, bullet items) appear one per phrase: step 1 at the start, step 2 with phrase 2, and so on. So write one phrase per step.

**slides.yaml** (Produce mode), in the demo folder. Slide ids match `slide:` in spec.yaml:

```yaml
version: 1
slides:
  - id: intro
    kind: title
    title: Recipe Box
    subtitle: Save the recipes you love
  - id: how
    kind: flow
    title: How saving works
    steps: [Find a recipe, Open it, Tap the heart]
    exits: [Favourites tab]
  - id: usage
    kind: chart
    title: Recipes saved per month
    chart_type: bars        # bars or lines
    labels: [Jan, Feb, Mar]
    values: [120, 180, 260]
  - id: whatsnew
    kind: bullets
    title: New in this release
    items: [Search by ingredient, Favourites tab, New recipe form]
```

Only use numbers in a chart that the user gave you or that come from the app. Never make up figures.

`reelsmith slides` writes PNGs under `slides/<format>/` (for example `slides/9x16/intro.png`) at the size compose uses for that format. The first format in spec.yaml is also copied to `slides/<id>.png`.

**Check the script** against spec.yaml and the clips:

```
reelsmith script check
```

Then show the user the whole script as it will be read, scene by scene, with the event each phrase lands on. Ask for approval. Only then run `reelsmith voice generate` and `reelsmith slides`.

**How to write it well:**

- **Pin phrases to events.** A phrase that talks about a click, a tap or a new screen is pinned to that event. A phrase can start up to a quarter second before its event and should start no later than about 0.4 seconds after it.
- **Split lines at natural pauses.** End each phrase where a speaker would breathe: at a full stop or a comma. Do not split in the middle of a phrase like "the search box". reelsmith cuts the audio at the quiet point between phrases.
- **Never let "this screen" play over the previous screen.** Words like "this", "here" and "now you see" must be pinned to the event where that screen appears (a `screen` event or the click that opens it). If they start early, the viewer hears about a screen they cannot see yet.
- **Speed up repetitive taps.** Do not narrate the fifth identical tap. Say it once ("Add each ingredient the same way") and either cut the repeats from the flow or set `speed_up_waits: true` in spec.yaml so quiet stretches play faster.
- **Keep the voice from running ahead of the clicks.** A phrase must fit in the gap before the next pinned event. At about 2.5 words per second, a 2 second gap holds about five words. If it does not fit, shorten the phrase. Holds (a frozen frame while the voice finishes) are a last resort, only if `allow_holds` is on, and at most about 3 seconds.
- **Business logic first, then the screen.** Lead with what the user gets ("Your favourites stay on this device"), then where to click.
- **Truth rule.** Only claim what the viewer can see in that moment. No "instantly", "secure" or "AI powered" unless the screen shows it.
- Use short sentences and plain words. Spell numbers and names the way they should be spoken.

## Reading the output

```
[OK] Script checked: 3 scenes, 6 lines, 4 pins
Next: reelsmith voice generate
```

A `[WARN]` such as `Scene 'outro' has no narration` lists spec scenes without lines. That is fine for a silent scene, but tell the user. An `[ERROR]` lists each problem with the scene, line and phrase, for example:

```
[ERROR] script.yaml has 1 problem
  - Scene 'search', line 'l1', phrase 1 is pinned to 'e9', but clip 'search' has no such event
Next: Fix /path/to/demo/script.yaml, then run: reelsmith script check
```

## Common failures and fixes

| Problem | Fix |
|---|---|
| `pinned to 'e9', but clip 'search' has no such event` | Open the clip.json and use a real event id. |
| `pinned to 'e1', but the scene is a slide` | Remove the pin. Slide steps follow the phrases. |
| `capture/clips/search/clip.json is missing` | Capture or import the clip first. |
| `Scene 'x' is not in spec.yaml` | Use the same scene ids as spec.yaml, or add the scene there (and get the change approved). |
| `Line id 'l1' is used more than once` | Give each line in a scene its own id. |
| Later, compose says a line is some seconds over | The line is too long for its gap. Shorten it, then rerun `reelsmith voice generate`. |

## Done when

- [ ] Every scene in spec.yaml has narration, or the user agreed it is silent.
- [ ] Every phrase about an action is pinned to that action's event.
- [ ] No phrase says "this" or "here" before its screen appears.
- [ ] Every claim is visible on screen, and every chart number came from the user or the app.
- [ ] `reelsmith script check` is OK.
- [ ] The user approved script.yaml (approval point 2).
