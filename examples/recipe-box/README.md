# Recipe Box demo

A ready made reelsmith demo for the Recipe Box sample app. Inputs live here; captures and builds stay local and are gitignored.

Record the four browser clips. 1280x720 keeps the app large in the frame; compose scales it up.

```bash
uv run reelsmith capture web examples/recipe-box/flows/search.py --demo examples/recipe-box --id search --size 1280x720
uv run reelsmith capture web examples/recipe-box/flows/open.py --demo examples/recipe-box --id open --size 1280x720
uv run reelsmith capture web examples/recipe-box/flows/favourite.py --demo examples/recipe-box --id favourite --size 1280x720
uv run reelsmith capture web examples/recipe-box/flows/create.py --demo examples/recipe-box --id create --size 1280x720
```

Check the script against clips:

```bash
uv run reelsmith script check examples/recipe-box
```

Build the full video when the pipeline is ready:

```bash
uv run reelsmith run examples/recipe-box
```
