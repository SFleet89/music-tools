# Pipeline — Music Tools Batch Processor

Runs the music tools processing steps in sequence for a new batch of downloads. Presents an interactive menu so you can choose which steps to run; launches each selected script in turn and waits for it to finish before moving to the next.

## What it does

Opens a folder picker for your batch folder (e.g. `C:\Users\neo_s\Downloads\To Move\`), then shows a numbered menu of pipeline steps. You choose which steps to run, and the pipeline launches each one with the folder path pre-filled — no need to pick the folder in each script separately.

## Pipeline steps

| # | Step | Script |
|---|------|--------|
| 1 | Build fingerprint cache | `duplicate_finder/build_fp_cache.py` |
| 2 | MusicBrainz lookup | `anjuna_mb_lookup/mb_lookup.py` |
| 3 | Tag files from lookup CSV | `anjuna_mb_lookup/mb_tagger.py` |
| 4 | Sort loose files by artist | `sort_by_artist/sort_by_artist.py` |
| 5 | Sort albums into artist folders | `sort_albums_to_artists/sort_albums_to_artists.py` |

Step 3 (mb_tagger) does not take a folder path — it opens its own file picker so you can select the CSV report produced by Step 2.

## Usage

**Flags:**

| Flag | Description |
|------|-------------|
| `--pick` | Open a folder dialog to select the batch folder |
| `--path "C:\..."` | Specify the batch folder directly |
| `--apply` | Launch the scripts (default is dry run — shows plan only) |
| `--steps 1 2 3` | Pre-select steps, skipping the interactive menu |

**Examples:**

```
python pipeline.py --pick                  # dry run — shows plan
python pipeline.py --pick --apply          # launches scripts for real
python pipeline.py --pick --steps 2 3     # run only steps 2 and 3
python pipeline.py --path "C:\..." --apply
```

## Dry run vs apply

Without `--apply` the pipeline shows the planned commands but does not launch anything — useful to see what would run before committing.

With `--apply` the pipeline launches each script in sequence. Each script also runs in apply mode, but still shows its own confirmation prompts before touching any files.

After each step the pipeline asks "Continue to next step?" so you can stop if something looks wrong.

## Output

A CSV report is saved to `pipeline/reports/` after each run, showing which steps ran, their exit codes, and the exact commands used.

## Requirements

Python 3.x. All dependencies are handled by the individual scripts in the pipeline.
