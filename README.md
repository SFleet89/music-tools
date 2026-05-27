# Music Tools

A collection of Python utilities for organising, cleaning, and deduplicating a music library. Every script defaults to a **dry run** — nothing moves or changes until you explicitly run the Apply version. All tools write a timestamped CSV report so you can review what happened.

---

## Quick Start

**1. Install Python packages**

```
pip install mutagen tqdm rapidfuzz
```

**2. Run the setup wizard**

```
python setup_music_tools.py
```

This creates `music_config.json` in the project root and walks you through setting your folder paths (library, unsorted downloads, duplicates holding folder). Run it once after cloning. You can re-run it any time to update settings — press Enter at any prompt to keep the existing value.

**3. Run any tool**

Each tool has two `.cmd` shortcuts in its folder:

- **`Run - Tool Name (Dry Run).cmd`** — scans and reports, nothing changes
- **`Run - Tool Name (Apply).cmd`** — opens a folder picker, then shows a confirmation prompt before making any changes

Always run the dry run first and review the report before applying.

---

## Configuration

All tools that need folder paths read from **`music_config.json`** in the project root. This is created by the setup wizard.

The `music_config.example.json` in `duplicate_finder/` shows the full structure with comments explaining each setting.

**Key settings:**

| Setting | Purpose |
|---|---|
| `folders.organized` | Your main sorted music library (e.g. `E:\Music`) |
| `folders.unsorted` | New downloads to check against the library |
| `folders.duplicates` | Holding folder for confirmed duplicates |
| `folders.better_quality` | Unsorted files that are higher bitrate than your library copy |
| `matching.mode` | `4` = match by both filename and metadata (recommended) |
| `matching.fuzzy_threshold` | `88` = how similar two tracks must be to count as a match |

A local `music_cache.db` file is created automatically in the project root. It caches audio fingerprints and file metadata to speed up repeated scans. It is not tracked by git (it can be several hundred MB).

---

## Tools

### Duplicate Finder

**`duplicate_finder/`**

Compares a folder of unsorted downloads against your organised library and identifies duplicates using filename matching, metadata tags, and optional audio fingerprinting. Reports include confidence scores, bitrate comparisons, and per-match decisions. Includes a browser-based report viewer and a full undo script.

| Script | Purpose |
|---|---|
| `find_music_duplicates.py` | Main scan — finds duplicates and writes a report |
| `build_fp_cache.py` | Pre-computes audio fingerprints for your library (speeds up later scans) |
| `check_audio_tags.py` | Checks whether audio files have the expected metadata tags |
| `compare_audio.py` | Side-by-side comparison of two specific audio files |
| `undo_duplicates.py` | Moves duplicates back from the holding folder to their original location |

For audio fingerprinting: download `fpcalc` from [acoustid.org/chromaprint](https://acoustid.org/chromaprint). No API key required — all processing is local.

---

### Library Dupes

**`library_dupes/`**

Finds tracks that exist under more than one top-level artist folder in your organised library — for example, the same track filed under both an artist folder and a compilation folder. Includes an HTML viewer for reviewing matches.

| Script | Purpose |
|---|---|
| `find_library_dupes.py` | Scans the library and flags duplicate tracks across folders |
| `remove_library_dupes.py` | Moves flagged copies to a holding folder for review |

---

### Sort & Organise

**Sorting scripts** move files and folders into the right structure.

| Script | Folder | Purpose |
|---|---|---|
| `sort_cd_tracks.py` | `sort_cd_tracks/` | Reads disc number tags and sorts tracks into CD1, CD2 subfolders within each album folder |
| `sort_albums_to_artists.py` | `sort_albums_to_artists/` | Reads Album Artist tags and moves each album folder into the correct artist subfolder |
| `sort_by_artist.py` | `sort_by_artist/` | Sorts loose audio files from a flat folder into artist subfolders |

---

### Renaming

**Renaming scripts** change folder or filenames to match metadata.

| Script | Folder | Purpose |
|---|---|---|
| `rename_album_folders.py` | `rename_album_folders/` | Renames album folders to match the Album tag read from the files inside |
| `rename_cd_folders.py` | `rename_cd_folders/` | Removes the space between CD and number in folder names (`CD 1` → `CD1`) |
| `rename_music_files.py` | `rename_music_files/` | Renames audio files using a FileBot-style template (e.g. `{pi.pad(2)} - {t}`) |
| `rename_to_catno.py` | `rename_to_catno/` | Renames album folders to `CATNO - Album Name` using the embedded catalogue number tag |
| `rename_undo.py` | `rename_undo/` | Undoes renames from a previous dry-run report CSV |

---

### Tag Fixing

**`fix_featuring/fix_featuring.py`**

Moves featuring credits out of the Artist tag and into the Title tag, where they belong.

```
Before:  Artist = "Above & Beyond feat. Zoë Johnston"  |  Title = "Sun & Moon"
After:   Artist = "Above & Beyond"                      |  Title = "Sun & Moon (feat. Zoë Johnston)"
```

Handles `feat.`, `ft.`, `featuring`, with or without brackets. Album Artist is never modified.

---

### Filename Scanner

**`filename_scanner/`**

Scans your library and flags filenames that look messy — underscores, ALL CAPS, inconsistent dash spacing, double spaces, and more. Tracks progress over time across multiple scans.

| Script | Purpose |
|---|---|
| `scan_music_filenames.py` | Main scan — produces an HTML+CSV report of flagged filenames |
| `fix_double_spaces.py` | Finds and renames files with double spaces in the name |
| `scan_progress.py` | Compares scan results over time to show cleanup progress |

---

### Music Integrity

**`music_integrity/check_music_integrity.py`**

Scans your library for structural problems: missing required tags (title, artist, album, track number), files with no duration, unreadable files, and format-specific issues. Reports flagged files with the specific problem for each one.

---

### Repair Playlists

**`repair_playlists/repair_playlists.py`**

Scans `.m3u` and `.m3u8` playlist files and fixes broken file paths — for example, after you've moved or reorganised your library. Finds the correct file by matching on filename, then updates the playlist entry.

---

### Clean Album Folders

**`clean_album_folders/clean_album_folders.py`**

Moves non-music files (cover art, NFOs, logs, extra playlists) out of album folders into a holding folder for review. CUE files are left in place.

---

### FLAC to CUE

**`flac_to_cue/flac_to_cue.py`**

Splits a single-file FLAC + CUE sheet into individual tracks per song. Useful for rips where the whole album is one file.

---

### Anjuna / MusicBrainz Suite

**`anjuna_mb_lookup/`**

Batch-looks up Anjunabeats, Tiësto, and similar releases on MusicBrainz using catalogue numbers extracted from folder names. Compares local file metadata against MB tracklists for confidence scoring. Tags files with MusicBrainz IDs and correct metadata. Includes an HTML viewer for reviewing and manually selecting matches.

| Script | Purpose |
|---|---|
| `anjuna_mb_lookup.py` | Looks up Anjunabeats releases on MusicBrainz by catalogue number |
| `mb_lookup.py` | General MusicBrainz lookup for any release |
| `tiesto_lookup.py` | Looks up Tiësto/Black Hole releases |
| `anjuna_tagger.py` | Tags files using a confirmed Anjunabeats lookup report |
| `mb_tagger.py` | Tags files using a general MusicBrainz lookup report |
| `tagger_undo.py` | Reverts tags to their pre-tagger values from a backup report |
| `move_from_report.py` | Moves folders based on a processed lookup report |

Requires: `pip install musicbrainzngs requests`

---

### Pipeline

**`pipeline/pipeline.py`**

Runs multiple tools in a defined sequence. Select which steps to include, point it at a folder, and it executes each tool in order — useful for processing a batch of new downloads from start to finish.

---

### Report Viewer

**`report_viewer/viewer.html`**

Open this file in any browser to browse CSV reports visually. Drag and drop a report CSV onto the page. Works offline — no internet connection needed.

---

## Shared Modules

These files are used by multiple tools and must stay in the project root:

| File | Purpose |
|---|---|
| `music_tools_common.py` (v2.5) | Shared utilities: `load_config()`, `pick_folder()`, cache DB access, tag reading, progress callbacks |
| `anjuna_mb_lookup/music_mb_common.py` (v1.0) | MusicBrainz API helpers shared across the anjuna suite |

---

## Requirements

**Core (needed by most tools):**

```
pip install mutagen tqdm rapidfuzz
```

**MusicBrainz suite only:**

```
pip install musicbrainzngs requests beautifulsoup4
```

**Audio fingerprinting (optional, duplicate finder only):**

Download `fpcalc` from [acoustid.org/chromaprint](https://acoustid.org/chromaprint) and place it somewhere on your PATH. No API key required.

| Package | Used by |
|---|---|
| `mutagen` | Everything — reads and writes audio tags |
| `tqdm` | Progress bars |
| `rapidfuzz` | Fuzzy string matching in duplicate finder |
| `musicbrainzngs` | Anjuna MB lookup suite |
| `requests` | MB lookup suite, mbz2cue |
| `beautifulsoup4` | mbz2cue |

---

## Dev Utilities

| Script | Purpose |
|---|---|
| `setup_music_tools.py` | First-run wizard — creates `music_config.json` |
| `create_test_environment.py` | Creates a small synthetic music library for testing scripts safely |

---

## Supported Audio Formats

MP3, FLAC, AAC, M4A
