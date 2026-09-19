# Format Duplicate Finder

Read-only diagnostic tool. Scans a music library for albums that exist in both MP3 and FLAC format, verifies the FLAC copies are intact and match the recording, and reports which MP3 folders are safe to delete.

## What it does

1. Walks the chosen folder looking for format duplicate pairs:
   - **Same folder** — a folder containing both `.mp3` and `.flac` files
   - **Sibling pair** — two adjacent folders with similar names, one all-MP3 and one all-FLAC (e.g. `Album [MP3]` / `Album [FLAC]`)

2. For each pair found:
   - Runs an **ffmpeg full-decode integrity check** on every FLAC file (results cached in `music_cache.db`)
   - Fingerprints a sample of MP3 and FLAC tracks with **fpcalc** and compares Chromaprint similarity scores (results cached in `music_cache.db`)

3. Assigns a verdict to each pair:

| Verdict | Meaning |
|---|---|
| `SAFE TO DELETE MP3` | All FLACs pass integrity, FP score ≥ threshold, track counts match |
| `NEEDS REVIEW` | Track count mismatch, FP score below threshold, or could not fingerprint |
| `FLAC CORRUPT` | One or more FLACs fail ffmpeg decode — do not delete MP3 |

4. Saves a CSV report to `format_dupe_finder/reports/`

**This script makes no changes to any files.**

## Usage

```
python format_dupe_finder.py --pick
python format_dupe_finder.py --path "E:\Music"
python format_dupe_finder.py --pick --sample half
python format_dupe_finder.py --pick --no-fp
python format_dupe_finder.py --pick --threshold 90
```

## Flags

| Flag | Description |
|---|---|
| `--pick` | Open a folder-picker dialog |
| `--path "..."` | Specify the root folder directly |
| `--sample N` | Tracks to fingerprint per album pair: `3` (default), `half`, `all` |
| `--threshold N` | FP similarity threshold % (default: from `music_config.json`, fallback 85) |
| `--no-fp` | Skip fingerprinting — integrity check + track count only (faster) |

## Report columns

| Column | Description |
|---|---|
| `mp3_folder` | Path to the MP3 folder |
| `flac_folder` | Path to the FLAC folder (same as MP3 folder if mixed) |
| `mp3_track_count` | Number of MP3 files found |
| `flac_track_count` | Number of FLAC files found |
| `tracks_match` | YES / NO |
| `flac_integrity` | PASS / FAIL / PARTIAL (X/N pass) / SKIPPED |
| `fp_similarity` | Average Chromaprint similarity score 0–100, or SKIPPED / FAILED |
| `verdict` | SAFE TO DELETE MP3 / NEEDS REVIEW / FLAC CORRUPT |
| `notes` | Details: mismatches, errors, fpcalc failures |

## Requirements

- Python 3.12
- `mutagen` — `pip install mutagen`
- `ffmpeg` — place `ffmpeg.exe` next to the script or add to PATH
- `fpcalc` — place `fpcalc.exe` next to the script or configure path in `music_config.json`
- `music_cache.db` — shared SQLite cache at project root (auto-created)

## Caching

Results from ffmpeg and fpcalc are stored in `music_cache.db` (the shared project database). Subsequent runs skip files that haven't changed — re-scanning a large library after the first run is much faster.
