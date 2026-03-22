# Music Tools

A collection of Python utilities for organising, deduplicating, and cleaning up a music library. Built around a workflow of scanning, reviewing, and acting — nothing moves or renames automatically without your confirmation.

---

## Tools

### [Duplicate Finder](duplicate_finder/)
Compares an unsorted music folder against your organized library and identifies duplicates using filename matching, metadata tags, and optional audio fingerprinting. Includes a browser-based report viewer with decision tracking, and a full undo script.

### [Filename Scanner](filename_scanner/)
Scans your organized library and flags filenames that look messy — underscores, all caps, inconsistent dash spacing, and more. Tracks cleanup progress over time across multiple scans.

### [Library Dupes](library_dupes/)
Finds songs that exist under more than one top-level artist folder in your organized library — for example, the same track in both an artist folder and a compilation folder. Includes a viewer for reviewing matches and a script for safely moving flagged copies to a holding folder.

### [Sort Albums Into Artist Folders](sort_albums_to_artists/)
Scans a flat folder of album subfolders, reads the Album Artist tag from the music files inside each one, and moves each album into a new or existing artist subfolder. Handles tag conflicts interactively.

### [Sort CD Tracks](sort_cd_tracks/)
Reads the disc number tag from music files and sorts them into CD1, CD2 etc. subfolders within each album folder. Useful for multi-disc albums where all tracks are in a single flat folder.

### [Clean Album Folders](clean_album_folders/)
Scans album folders and moves non-music files (cover art, NFOs, logs, playlists etc.) to a separate holding folder for review. Keeps CUE files in place.

### [Anjuna MusicBrainz Lookup](anjuna_mb_lookup/)
Batch-looks up Anjunabeats releases on MusicBrainz by extracting the catalogue number from folder names. Compares local file metadata against MB tracklists for confidence scoring. Includes an HTML viewer for reviewing and manually selecting matches.

### [Utilities](utilities/)
Standalone rename scripts:
- **rename_album_folders.py** — renames folders to match the album tag read from the music files inside
- **rename_cd_folders.py** — removes the space between CD and number in folder names (`CD 1` → `CD1`)

---

## Requirements

```
pip install mutagen tqdm rapidfuzz
```

| Package | Purpose |
|---|---|
| `mutagen` | Reading audio metadata and bitrate |
| `tqdm` | Progress bars |
| `rapidfuzz` | Fast fuzzy string matching |

**Optional — for audio fingerprint matching:**

Download `fpcalc` from [acoustid.org/chromaprint](https://acoustid.org/chromaprint). No API key required — all processing is local.

---

## Setup

Each tool has its own config file. Copy the example and fill in your folder paths:

```
duplicate_finder/
  cp music_config.example.json music_config.json

library_dupes/
  cp library_dupes_config.example.json library_dupes_config.json
```

The filename scanner, utilities, and sorting scripts have their paths set directly at the top of each script or via a `--path` flag / folder picker dialog.

---

## Supported formats

MP3, FLAC, AAC, M4A
