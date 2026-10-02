# Check the video

## Goal

Make sure the video is right before anyone sees it: every word is said as written, every phrase lands on its click, nothing private shows, and the sound is clean. You run the checks, read the report, look at the frames yourself, and fix every FAIL. Only then is the video done.

## Rules

{{rules}}

## What to ask or check

- Has the user seen the preview from `reelsmith compose --preview`? Fix what they asked for before the full render.
- Is the full render done? `reelsmith qa` checks the master videos from `reelsmith compose`, not the preview.
- What must never be visible? Check the blur list in spec.yaml against what the user told you.

## Commands

From inside the demo folder:

```
reelsmith compose --preview     # fast 540p draft, build/master_16x9_preview.mp4 for 16:9
reelsmith compose               # full quality, build/master_16x9.mp4 for 16:9
reelsmith qa                    # writes qa/report.md and contact sheets in qa/sheets/
reelsmith export                # after qa passes: writes out/
```

`reelsmith qa` runs these checks, each PASS or FAIL with a suggested fix:

| Check | Catches |
|---|---|
| Transcript vs script | missing, slurred or changed words |
| Sync | phrases early or late against their event |
| Cut off lines | narration running into the next scene or past the end |
| End of line noise | clicks or breaths after the last word |
| Loudness | far from -16 LUFS, or clipping |
| Hold limits | frozen frames longer than allowed |
| Captions | text overflowing its panel, or on screen too briefly to read |
| Blur | listed regions covered on every frame they apply to |
| Contact sheets | frames at each scene start, event and transition, for you to look at |

With `voice.engine: none` there is no narration, so Transcript vs script, End of line noise and Loudness are skipped (a note in the report says why) instead of failing. The rest still run.

**Do these yourself too, every time:**

1. **View the frames.** Open every image in `qa/sheets/`. Check that each frame shows what the narration says at that moment, the captions fit, and the layout is right.
2. **Check every line's words.** Go through the transcript result for each line in `qa/report.md`, one by one, against script.yaml. Do not stop at the summary. If you cannot read a line's result, say so to the user instead of guessing.
3. **Check the blur, including held frames.** Every listed region must be covered on every frame, including frames that are held while the voice finishes and the last frame of each scene. Look for private data the blur list missed: emails, names, tokens, prices, notifications.
4. **Ask the user to watch it.** You cannot hear the audio. Ask them to listen to the full render before export.

`reelsmith export` writes, per format: `out/<name>_<format>.mp4` (with voice), `out/<name>_<format>_silent.mp4`, plus `out/<name>_narration.wav` and `out/<name>.srt`. With `voice.engine: none` the silent copy and the narration wav are left out, since the main video already carries no narration. The name is the demo folder's name, or set it with `--name`. Existing files are backed up, never overwritten.

## Reading the output

compose:

```
[OK] Video composed: 4 scenes in 1 format
  - 16:9: build/master_16x9.mp4 (84.2 s, 1 scenes rendered, 3 reused)
Next: reelsmith qa
```

A `[WARN]` from compose lists timing conflicts, for example a line that is some seconds over the gap before its event. QA fails those too. Shorten the line, then rerun `reelsmith voice generate --only scene/line` and compose.

qa ends with `[OK]` when every check passes and `[ERROR]` when any check fails. The details and `qa/report.md` name each FAIL and its fix. Always open the report, even on `[OK]`.

## Common failures and fixes

| FAIL | Fix |
|---|---|
| Transcript vs script | Rewrite the line more simply, then `reelsmith voice generate --only scene/line`. |
| Sync | Check the pin in script.yaml points at the right event. Shorten the phrase before it so this one can start on time. |
| Cut off lines | The line is longer than its scene. Shorten it, or allow a hold if the user agrees. |
| End of line noise | Regenerate that line. If it repeats, rewrite the last word. |
| Loudness | Rerun `reelsmith compose`. If it still fails, check the voice files for clipping and regenerate them. |
| Hold limits | A held frame is over about 3 seconds. Shorten the narration for that scene, or record a longer clip. |
| Captions | Shorten the scene caption or the line. |
| Blur | Fix the box (x, y, width, height as fractions) or the start and end times in spec.yaml, then compose again. |
| Something on screen does not match the words | That is a truth rule problem. Change the words, or recapture the clip. Never leave it. |

After every fix, run `reelsmith compose` and `reelsmith qa` again, and read the new report.

## Done when

- [ ] `reelsmith qa` ends with `[OK]` and `qa/report.md` has no FAIL.
- [ ] You looked at every contact sheet and every frame matches its narration.
- [ ] You checked every line's transcript against the script.
- [ ] Blur covers every private region on every frame, held frames included.
- [ ] The user watched and listened to the full render and is happy.
- [ ] `reelsmith export` wrote the files to `out/`, and you told the user where they are.
