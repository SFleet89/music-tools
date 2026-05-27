# Duplicate Finder

Compares an unsorted music folder against your organized library and identifies duplicates. Moves confirmed duplicates to a holding folder safely — with a review step before anything moves, and full undo support.

Nothing moves automatically except exact matches. Everything else goes through a browser-based review where you make the final call.

---

## How it works

Every file in your unsorted folder is compared against your organized library and placed into one of four categories:

| Category | Description | What happens |
|---|---|---|
| **Exact Match** | Same filename, metadata, bitrate, and size (within tolerance) | Auto-moved — no review needed |
| **Standard Duplicate** | Matches on chosen criteria, organized copy is equal or better | Shown for review |
| **Higher Quality** | Matches but unsorted copy has a higher bitrate | Shown for review |
| **No Match** | Nothing found in organized library | Left completely untouched |

---

## Requirements

```
pip install mutagen tqdm rapidfuzz
```

**Optional — for audio fingerprint matching:**

Download `fpcalc` from [acoustid.org/chromaprint](https://acoustid.org/chromaprint) and set the path in `music_config.json`. No API key required.

---

## Setup

1. Install dependencies:
   ```
   pip install mutagen tqdm rapidfuzz
   ```

2. Copy the example config and set your folder paths:
   ```
   cp music_config.example.json music_config.json
   ```
   Edit `music_config.json`:
   ```json
   "folders": {
     "organized":      "C:\\Music\\Organized",
     "unsorted":       "C:\\Music\\Unsorted",
     "duplicates":     "C:\\Music\\Duplicates",
     "better_quality": "C:\\Music\\BetterQuality"
   }
   ```

3. If using fingerprint matching, set your fpcalc path:
   ```json
   "acoustid": {
     "enabled": true,
     "fpcalc_path": "C:\\tools\\fpcalc.exe"
   }
   ```

4. Run:
   ```
   python find_music_duplicates.py --dry-run
   ```

---

## Recommended workflow

```
# Step 1 — dry run, skip Notepad, generate CSV for browser review
python find_music_duplicates.py --dry-run --no-review

# Step 2 — open music_report_viewer.html, drop the CSV in,
#           click Keep library / Keep unsorted / Skip on each match,
#           download the _reviewed.csv

# Step 3 — commit your selections
python find_music_duplicates.py --confirm "music_report_..._dry_..._reviewed.csv"
```

---

## Usage

```
python find_music_duplicates.py                          # normal run (uses config unsorted folder)
python find_music_duplicates.py --pick-source            # choose comparison folder via dialog
python find_music_duplicates.py --source "C:\My\Folder" # specify comparison folder directly
python find_music_duplicates.py --dry-run                # preview only
python find_music_duplicates.py --dry-run --no-review    # preview, skip Notepad
python find_music_duplicates.py --confirm "report.csv"   # live run from selections
python find_music_duplicates.py --clear-cache            # force re-scan of library
python find_music_duplicates.py --clear-fp-cache         # clear fingerprint cache
python find_music_duplicates.py --clear-resume           # discard interrupted run
```

### Choosing a comparison folder

By default the script compares whatever folder is set as `unsorted` in `music_config.json`. Use `--pick-source` to open a folder dialog instead — useful when you want to check a specific batch folder like `C:\Downloads\To Move\` without editing the config. The dialog opens before scanning starts, so you can check different folders in separate runs without touching any settings.

**Launchers:**

| File | What it does |
|------|---|
| `Run - Find Duplicates.cmd` | Uses the config `unsorted` folder |
| `Run - Find Duplicates (Pick Source).cmd` | Opens a folder picker first |

---

## Pre-warming the cache

Run `build_fp_cache.py` before your first scan to fingerprint your entire library in advance. Subsequent scans will use the cached fingerprints and run near-instantly.

```
python build_fp_cache.py                  # build both caches
python build_fp_cache.py --fp-only        # fingerprint cache only
python build_fp_cache.py --rebuild        # wipe and rebuild from scratch
```

Any files that fail fingerprinting are flagged and saved to a warnings CSV. They are classified into two categories:

| Category | Meaning |
|---|---|
| `too_small` | File is under 30 seconds or 500 KB — too short to fingerprint. Usually interludes or short clips. |
| `corrupted` | Normal-sized file where fingerprinting failed or returned a suspiciously short result. Worth inspecting. |

To copy flagged files into separate review folders:

```
python build_fp_cache.py --fp-only --copy-errors              # dry run — shows what would be copied
python build_fp_cache.py --fp-only --copy-errors --apply      # actually copies
python build_fp_cache.py --fp-only --copy-errors --apply --error-dest "C:\Review\FP Errors"
```

Or double-click `Run - Copy FP Errors (Apply).bat`.

---

## Undoing a run

`undo_duplicates.py` reads any live run CSV report and moves files back to their original locations.

```
python undo_duplicates.py "music_report_TIMESTAMP_live.csv"
python undo_duplicates.py "music_report_TIMESTAMP_live.csv" --dry-run
python undo_duplicates.py "music_report_TIMESTAMP_live.csv" --list
python undo_duplicates.py "music_report_TIMESTAMP_live.csv" --filter-method "audio fingerprint"
```

---

## Match modes

| Mode | How it works |
|---|---|
| `1` — Filename only | Filenames must match |
| `2` — Metadata only | Title, artist, and album must match |
| `3` — Either | Filename OR metadata matches |
| `4` — Both *(recommended)* | Filename AND metadata must both match on the same file |

---

## Audio fingerprint matching

When enabled, a second pass runs on No Match files using Chromaprint to compare actual audio content. Catches renamed or retagged duplicates that filename and metadata matching cannot find.

Fingerprint matches are grouped by confidence tier in the review viewer:

| Tier | Score | Guidance |
|---|---|---|
| High | 95–100% | Almost certainly the same audio |
| Medium | 90–94% | Very likely duplicates |
| Low | 85–89% | Most scrutiny needed |

---

## Running without the command line

Double-click any `.bat` file to open a terminal and run the script automatically:

| File | Action |
|---|---|
| `Run - Find Duplicates.bat` | Run the duplicate finder |
| `Run - Build Cache.bat` | Build metadata and fingerprint caches |
| `Run - Undo Duplicates.bat` | Restore files from a previous run |

---

## Checking for bad AcoustID tags

`check_audio_tags.py` scans a folder tree and flags any audio file whose embedded
AcoustID tags are malformed:

- **`acoustid_id`** must be a valid UUID (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`).
  Literal text like `"acoustid"` or `"acousticid"` is flagged.
- **`acoustid_fingerprint`** (if present) must be a base64-encoded string at least
  50 characters long.

Files with no AcoustID tag at all are skipped — only files that *have* a tag but
the value is wrong are reported.

In dry-run mode it reports only. In `--apply` mode it deletes the bad tag(s) from
the file (audio data is untouched). Run MusicBrainz Picard afterward to repopulate
correct tags.

```
python check_audio_tags.py --pick              # pick folder, dry run
python check_audio_tags.py --pick --apply      # pick folder, delete bad tags
python check_audio_tags.py --path "E:\Music"   # specify folder directly
```

Or double-click `Run - Check Audio Tags (Dry Run).cmd` / `Run - Check Audio Tags (Apply).cmd`.

---

## Investigating near-misses and false positives

After a scan, use `compare_audio.py` to examine specific pairs the duplicate
finder flagged or missed. It shows both files' metadata side by side, runs
fpcalc on each, and gives a plain-English verdict using the same similarity
score as the main scan.

```
python compare_audio.py --pick                                   # pick both files via dialog
python compare_audio.py --file1 "path\a.mp3" --file2 "path\b.mp3"
```

Or double-click `Run - Compare Audio.cmd`.

The score printed by compare_audio is directly comparable to scores in
near-miss CSVs and scan reports — they all use the same algorithm.

---

## Files

| File | Description |
|---|---|
| `find_music_duplicates.py` | Main duplicate finder script |
| `check_audio_tags.py` | Scan for files with invalid AcoustID tags (corrupt UUIDs, non-base64 fingerprints) |
| `compare_audio.py` | Compare two files by fingerprint — diagnose near-misses and false positives |
| `undo_duplicates.py` | Restore files from a previous run |
| `build_fp_cache.py` | Pre-build metadata and fingerprint caches |
| `music_config.json` | Your configuration *(not committed — see example)* |
| `music_config.example.json` | Example configuration with placeholder paths |
| `music_report_viewer.html` | Browser-based report viewer with decision tracking |
| `undo_report_viewer.html` | Browser-based viewer for live run reports |
| `Find_Music_Duplicate_Run_Commands.txt` | Quick reference |
| `Undo_Duplicates_Run_Commands.txt` | Quick reference for undo |
| `Build_Cache_Run_Commands.txt` | Quick reference for cache builder |
