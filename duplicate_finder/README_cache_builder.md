# Music Cache Builder

A utility script that pre-builds the two cache files used by `find_music_duplicates.py` — so your next duplicate scan starts instantly and the fingerprint pass runs in seconds rather than minutes.

Can also be run as a standalone **library audit tool** to identify corrupted, silent, or unreadable files without needing to run a full duplicate scan.

---

## Why use this

`find_music_duplicates.py` builds both caches automatically during a scan, but only as it needs them. If you run the cache builder separately beforehand:

- The duplicate scan skips the metadata read pass entirely (files are already cached)
- The fingerprint pass completes near-instantly (fingerprints are already stored)
- Corrupt or unreadable files are identified and reported before you start a scan

It's also useful after adding new music to your library — run it to update the caches without having to do a full duplicate scan.

---

## Two caches

**Metadata cache** (`music_cache.json`)

Stores the filename, tags, bitrate, and duration for every file in your organized library. The duplicate finder reads this instead of re-scanning your entire library on every run. Keyed by file path + modification time + size, so changed files are automatically detected and refreshed.

**Fingerprint cache** (`music_fp_cache.json`)

Stores the Chromaprint audio fingerprint for every file. Used by the duplicate finder's optional fingerprint pass to identify renamed or retagged duplicates that filename and metadata matching can't catch. Requires `fpcalc` (see [Requirements](#requirements)).

---

## Requirements

```
pip install mutagen tqdm
```

| Package | Purpose |
|---|---|
| `mutagen` | Reading audio metadata and bitrate |
| `tqdm` | Progress bars *(optional but recommended)* |

**For fingerprint cache only:**

Download `fpcalc` from [acoustid.org/chromaprint](https://acoustid.org/chromaprint) and either add it to your PATH or set the full path in `music_config.json` under `acoustid.fpcalc_path`. No API key required — all processing is local.

---

## Setup

The script reads your folder paths and settings from `music_config.json` — the same config file used by `find_music_duplicates.py`. No separate configuration needed.

Make sure these keys are set in your config:

```json
{
  "folders": {
    "organized": "C:\\Music\\Organized"
  },
  "performance": {
    "cache_file": "music_cache.json",
    "max_threads": 0
  },
  "acoustid": {
    "fpcalc_path": "fpcalc",
    "fp_cache_file": "music_fp_cache.json"
  },
  "output": {
    "log_folder": "C:\\Music\\tools\\duplicate_finder\\reports"
  }
}
```

---

## Usage

```
python build_fp_cache.py                     # build both caches (incremental)
python build_fp_cache.py --metadata-only     # metadata cache only
python build_fp_cache.py --fp-only           # fingerprint cache only
python build_fp_cache.py --rebuild           # wipe and rebuild selected cache(s) from scratch
python build_fp_cache.py --path "C:\Music"   # override the organized folder path
python build_fp_cache.py --config my.json    # use a different config file
python build_fp_cache.py --threads 4         # override thread count
```

Flags can be combined:

```
python build_fp_cache.py --fp-only --rebuild
python build_fp_cache.py --metadata-only --path "C:\Music\New Additions"
python build_fp_cache.py --rebuild --threads 8
```

---

## How it works

**Incremental by default** — on each run the script checks every file against what's already stored in the cache. Files that haven't changed (same path, size, and modification time) are skipped. Only new or modified files are processed. This makes repeat runs fast even on large libraries.

**Fingerprint failures are cached** — if a file fails fingerprinting, that failure is recorded in the cache so the script doesn't waste time retrying the same broken file on every run. Use `--rebuild` to force a retry after fixing a file.

**fpcalc availability check** — if fingerprinting is selected but fpcalc isn't found, the script reports the error clearly and skips the fingerprint cache rather than crashing. If both caches were requested, the metadata cache still completes normally.

---

## Output

On each run the script prints a summary to the console:

```
============================================================
Music Cache Builder
============================================================
  Mode      : metadata + fingerprint  [incremental]
  Folder    : C:\Music\Organized
  Threads   : 8
  Meta cache: music_cache.json
  FP cache  : music_fp_cache.json
  fpcalc    : fpcalc
============================================================

── Metadata Cache ──────────────────────────────────────────

  Files scanned   : 12,847
  New / updated   : 143
  From cache      : 12,704
  Cache saved to  : music_cache.json
  Cache file size : 8.2 MB

── Fingerprint Cache ───────────────────────────────────────

  Files processed : 12,847
  New / updated   : 143
  From cache      : 12,704
  Valid           : 12,705
  Warnings        : 2
  Cache saved to  : music_fp_cache.json
  Cache file size : 156.4 MB

  WARNING: 2 file(s) flagged:

    ! Andrew Spinks - SMB3 World 2.mp3
      short fingerprint — file may be corrupted or silent
      C:\Music\Organized\Game OST\Andrew Spinks - SMB3 World 2.mp3

    ! Britney Spears - Don't Go Knockin' On My Door.mp3
      fingerprint generation failed
      C:\Music\Organized\Britney Spears\...

  Warnings saved to: ...\reports\fp_warnings_20260309_143022.csv
```

### Fingerprint warnings report

If any files fail fingerprinting or produce suspiciously short fingerprints, they are saved to a CSV report in your reports folder: `fp_warnings_TIMESTAMP.csv`

| Column | Description |
|---|---|
| Folder | Folder path relative to your organized root |
| Filename | Filename only |
| Full Path | Complete path to the file |
| Reason | `short fingerprint` or `fingerprint generation failed` |
| Fingerprint Length | Number of integers in the fingerprint (blank for failed) |

Rows are sorted by reason, then folder, then filename — so all generation failures group together and all short fingerprint files group together.

---

## Fingerprint length guide

A healthy fingerprint for a typical 3–5 minute track contains 120–500+ integers. The script flags anything under 50.

| Length | Likely cause |
|---|---|
| 0 / failed | File is unreadable, DRM-protected, or severely corrupted |
| 1–20 | File is near-silent, extremely short, or has corrupt audio data |
| 20–49 | File may be truncated or partially corrupted |
| 50+ | Valid — file will be included in fingerprint matching |

---

## Supported formats

MP3, FLAC, AAC, M4A

---

## Files

| File | Description |
|---|---|
| `build_fp_cache.py` | This script |
| `music_config.json` | Shared config (also used by `find_music_duplicates.py`) |
| `music_cache.json` | Auto-generated metadata cache |
| `music_fp_cache.json` | Auto-generated fingerprint cache |
| `reports\fp_warnings_*.csv` | Per-run fingerprint warnings (if any) |
