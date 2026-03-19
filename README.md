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

The filename scanner and utilities have their paths set directly at the top of each script.

---

## Supported formats

MP3, FLAC, AAC, M4A
