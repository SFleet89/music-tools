# Qobuz Upgrade Finder

Scans a music library, identifies albums that could be upgraded to higher quality,
and optionally searches Qobuz for download URLs.

## What it does

**Dry run (default):** Scans every audio file in your library and produces reports:

- `below_320kbps_<timestamp>.csv` — albums where at least one file is below 320 kbps
- `at_320kbps_no_lossless_<timestamp>.csv` — albums that are all 320 kbps but have no lossless version
- `qobuz_upgrade_report_<timestamp>.xlsx` — multi-sheet Excel workbook (see below)
- `summary_<timestamp>.json` — totals by classification

Albums that already contain a lossless file (FLAC, WAV, etc.) are skipped — you don't need them.

**Apply mode:** After the scan, logs in to Qobuz and searches for each candidate album.
Adds Qobuz album URLs to the CSVs and writes two extra files:

- `qobuz_urls_<timestamp>.txt` — one URL per album
- `rip_commands_<timestamp>.txt` — ready-to-run `rip url "..."` commands for streamrip

Reports are saved to the `reports/` folder next to the script.

## Excel workbook

The `.xlsx` report has up to eight sheets, each with a dark header row, alternating grey rows,
and a footer note:

| Sheet | Contents |
|-------|----------|
| Already Downloaded | Upgrade candidates already present in your Spotify downloads folders — no need to re-purchase. Includes a **Found In** column. Only appears when matches are found. |
| AT 320 - No Lossless | Albums already at 320 kbps — prime Qobuz targets |
| 256–319 kbps | Below-threshold albums grouped by min bitrate |
| 192–255 kbps | |
| 128–191 kbps | |
| Under 128 kbps | |
| Mixed Format | Folders with multiple audio format types (MP3 + M4A etc.) |
| Suspicious Bitrate | Folders with corrupt bitrate tags (max > 5,000 kbps) |

Each bitrate-band sheet includes a **Download Quality** column (`LOSSLESS` or `320`) that is
auto-populated based on keyword detection. LOSSLESS rows are highlighted green. You can edit
this column before running `--apply` — see [Quality preferences](#quality-preferences) below.

Requires `openpyxl` — the script prints a warning and skips the Excel file if it's not installed.

## Quality preferences

Not every album needs to be downloaded at lossless quality. Soundtracks, classical, and
EDM where the extra detail matters are worth the extra space; everything else may be fine at
320 kbps MP3.

### How it works

1. **Dry run** — the Excel report is generated with a **Download Quality** column pre-filled:
   - `LOSSLESS` — album/artist name matched a keyword (soundtracks, classical, trance, etc.)
   - `320` — everything else

2. **Edit the Excel** — open the report and change any `Download Quality` values you disagree
   with. You can set individual albums to `LOSSLESS` or `320`.

3. **Apply with preferences** — re-run with `--apply --from-excel <path>` pointing at your
   edited file. The script reads back the column and generates two separate rip-command files:
   - `rip_lossless_<timestamp>.txt` — `rip url "..." --quality 2` (FLAC 16-bit)
   - `rip_320_<timestamp>.txt`      — `rip url "..." --quality 1` (320 kbps MP3)

   > **Note:** lossless/hi-res downloads require a Qobuz Studio subscription.
   > 320 kbps MP3 works on all paid Qobuz plans.

### Streamrip quality levels

| `--quality` flag | Format |
|-----------------|--------|
| `1` | 320 kbps MP3 |
| `2` | CD quality — FLAC 16-bit (lossless) |
| `3` | Hi-res — FLAC 24-bit (where available) |

### Customising keyword detection

By default the script matches these categories as LOSSLESS: soundtracks, OSTs, film/game scores,
classical, orchestral, trance, progressive, anjuna, ambient, jazz.

To add your own keywords, create a `music_config.json` file in the same folder as the script:

```json
{
  "lossless_keywords": ["bossa nova", "audiophile", "remastered"],
  "lossless_artists":  ["Nils Frahm", "Yann Tiersen"],
  "lossless_albums":   ["Deluxe Edition"]
}
```

- `lossless_keywords` — any substring matched against the combined artist + album text
- `lossless_artists`  — matched against artist name only
- `lossless_albums`   — matched against album title only

All matching is case-insensitive. The file is optional — without it, only the built-in
defaults apply.

## Downloads cross-reference

At startup the script scans three Spotify backup folders and fuzzy-matches them against
upgrade candidates. Albums that match are moved to the **Already Downloaded** sheet instead
of appearing in the bitrate-band sheets.

Folders scanned (missing folders are silently skipped):
- `C:\Users\neo_s\Downloads\ThinQ Back Up 2024\Spotify\Organized`
- `C:\Users\neo_s\Downloads\ThinQ Back Up 2024\Spotify\Still needs fixing`
- `C:\Users\neo_s\Downloads\ThinQ Back Up 2024\Spotify\Streamrip`

Matching uses `difflib.SequenceMatcher` on normalised artist and album names
(album similarity ≥ 0.80, artist similarity ≥ 0.70). No extra packages required.

## Requirements

Install these Python packages if you don't have them:

```
pip install mutagen requests openpyxl --break-system-packages
```

**For Qobuz lookup (`--apply`):** streamrip must already be configured with your
Qobuz credentials. The script reads them from the streamrip config file automatically.

If streamrip isn't configured yet, run `rip config open` and fill in the `[qobuz]`
section, or pass `--qobuz-email` and `--qobuz-password` directly.

## Usage

Double-click a launcher:

| File | What it does |
|------|-------------|
| `scan_dry_run.cmd` | Scan only — opens folder picker, writes CSV reports |
| `scan_apply.cmd`   | Scan + Qobuz lookup — writes CSVs, URLs, and rip commands |

Or run from the command line:

```
python qobuz_upgrade_finder.py --pick
python qobuz_upgrade_finder.py --path "E:\Music" --apply
python qobuz_upgrade_finder.py --path "E:\Music" --apply --min-bitrate 256
```

## Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--pick` | — | Open folder picker |
| `--path` | — | Path to library root |
| `--apply` | off | Enable Qobuz search |
| `--min-bitrate` | 320 | Bitrate threshold in kbps |
| `--qobuz-email` | — | Override streamrip config |
| `--qobuz-password` | — | Override streamrip config |
| `--qobuz-app-id` | 950096963 | Qobuz API app ID |
| `--search-delay` | 0.5 | Seconds between API calls |

## How albums are classified

| Classification | Meaning |
|----------------|---------|
| `LOSSLESS_PRESENT` | Folder contains FLAC/WAV/APE/etc — no action needed |
| `AT_THRESHOLD_NO_LOSSLESS` | All files ≥ 320 kbps, no lossless — worth upgrading to lossless |
| `BELOW_THRESHOLD` | At least one file below 320 kbps — quality upgrade needed |
| `UNKNOWN` | Could not read bitrate (damaged files, unusual format) |

## Qobuz matching

The script searches Qobuz using the artist + album name from your file tags (falling
back to folder names if tags are missing). It picks the best match based on name
similarity, preferring hi-res results. It is not perfect — review the results before
running any `rip` commands.

## Notes

- The `--apply` flag only makes API calls — it does not download or modify any files.
- Qobuz login uses the same unofficial API that streamrip uses. If streamrip works for
  you, this will too. If the `--qobuz-app-id` default stops working, check the latest
  streamrip source for the current value.
- Large libraries (50k+ files) will take several minutes to scan.
