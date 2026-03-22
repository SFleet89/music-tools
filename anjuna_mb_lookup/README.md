# Anjuna MusicBrainz Batch Lookup

A Python script that scans a folder of Anjunabeats releases, extracts the catalogue number from each subfolder name, and automatically looks it up on MusicBrainz. Includes metadata comparison using your existing file tags to improve match confidence.

---

## How it works

Each subfolder in the batch folder is treated as one release. The script:

1. Extracts the ANJ*/ANJCD*/ANJDJ* catalogue number from the folder name
2. Searches MusicBrainz by catalogue number
3. If no result, tries common suffix variants (D, R, EP, CD, DJ etc.)
4. Reads existing file tags (title, artist, track count) using mutagen
5. Fetches the full tracklist from MusicBrainz for each candidate
6. Scores each candidate using catalogue number match (60%) and metadata match (40%)
7. Either auto-picks the best match or flags it for manual review in the viewer

Results are saved to a timestamped CSV in the `reports\` folder next to the script.

---

## Requirements

```
pip install mutagen
```

`mutagen` is required for reading file metadata. Without it the script will still run but metadata comparison will be disabled and all matches will rely on catalogue number alone.

---

## Setup

1. Place `anjuna_mb_lookup.py` and `anjuna_lookup_viewer.html` in the same folder
2. Install mutagen: `pip install mutagen`
3. Run the script

---

## Usage

```
python anjuna_mb_lookup.py                              # opens folder picker
python anjuna_mb_lookup.py "C:\path\to\batch folder"   # use path directly
python anjuna_mb_lookup.py "C:\path\to\batch folder" --auto    # auto-pick mode
python anjuna_mb_lookup.py "C:\path\to\batch folder" --review  # review mode
```

Run one batch folder at a time. Reports are saved to `reports\` next to the script regardless of which batch folder you process.

---

## Modes

When multiple MusicBrainz releases are found for the same catalogue number, you can choose how to handle them:

| Mode | How it works |
|---|---|
| **Auto-pick** | Automatically selects the highest-scoring candidate using catno + metadata scoring. Best for large batches where speed matters. |
| **Review** | Flags all multi-result cases in the report with no MBID assigned. Open the viewer to compare candidates and select the right one manually. |

If neither `--auto` nor `--review` is passed on the command line, the script asks at runtime.

---

## Catalogue number variants

If the exact catalogue number from the folder name returns no results, the script automatically tries common Anjunabeats suffix variants. The variants tried depend on the type of release:

- **Standard releases** (no suffix): tries D, EP, E, X, then R/R2, then CD/DJ/DEEP
- **Remix releases** (R/R2 suffix): tries bare base and other R variants only — does not cross into D variants
- **Digital releases** (D suffix): tries bare base and other digital variants only

This prevents remix releases from being incorrectly matched to the digital version of a different release.

---

## Scoring

Each candidate release gets three scores:

| Column | What it measures |
|---|---|
| `catno_score` | How well the MusicBrainz catalogue number matches your folder catno (hyphens ignored, so ANJ101 == ANJ-101) |
| `meta_score` | How well the MusicBrainz tracklist matches your local file tags (title, track count) |
| `combined_score` | Weighted average: catno 60% + metadata 40% |
| `track_match_pct` | Percentage of local track titles fuzzy-matched against the MB tracklist |
| `count_match` | Whether local file count matches MB track count |

**Note:** If your files have no title tags yet (i.e. before Picard tagging), `meta_score` will show 50 and `track_match_pct` will show 0. This is expected and does not mean the match is wrong — check `catno_score` and `count_match` instead.

---

## Status codes

| Status | Meaning |
|---|---|
| `matched` | Single MusicBrainz result found |
| `auto_matched` | Multiple results found, best candidate auto-selected |
| `review` | Multiple results found, flagged for manual selection in viewer |
| `not_found` | No results found after trying all catalogue number variants |
| `no_catno` | Folder name does not contain a recognisable ANJ* catalogue number |
| `error` | Network error during lookup — safe to re-run |

---

## Viewer

Open `anjuna_lookup_viewer.html` in any browser and drag-drop your CSV report onto it.

- Filter by status using the coloured pills at the top
- Search by folder name, catalogue number, title, or artist
- Sort by any column
- For **Needs review** rows, click **Show X** to expand all candidates
- Click **Use this** on the correct candidate to assign its MBID and mark the row as matched

---

## Files

| File | Description |
|---|---|
| `anjuna_mb_lookup.py` | Main lookup script |
| `anjuna_lookup_viewer.html` | Interactive report viewer |
| `Anjuna_Lookup_Run_Commands.txt` | Quick reference for all run commands |
| `CHANGELOG.md` | Version history |
| `reports\` | Auto-created folder where CSV reports are saved |

---

## Notes

- MusicBrainz enforces a rate limit of 1 request per second. The script respects this with a 1.1 second delay between requests. On a 100-release batch expect 6–8 minutes.
- The script fetches full release details (tracklist) for every candidate, which means 2–3 API calls per folder. This is what enables the metadata comparison but does add to the runtime.
- Network errors mid-run are safe — just re-run the script on the same folder. Already-processed folders will be re-checked but results are identical for matched releases.
