# Hi, I'm SFleet89 👋

I build practical Python tools for managing and organising large music libraries — focused on making tedious cleanup tasks safe, reviewable, and repeatable. Currently turning that toolkit into a full desktop application.

---

## 🎵 Projects

### [music-tools](https://github.com/SFleet89/music-tools)
A growing suite of utilities for organising, cleaning, and tagging a music library — with a PySide6 desktop GUI in active development.

**Organisation**
Sort multi-disc albums into CD subfolders · Sort loose albums into artist folders · Sort flat files by artist tag · Move non-music files out of album folders

**Renaming**
Rename album folders by tag · Rename files using a FileBot-style template · Rename to catalogue number format · Fix CD subfolder naming · Undo any rename from a saved report

**Scanning & Fixing**
Flag messy filenames and track cleanup progress · Fix double spaces in filenames · Move featuring credits from Artist tag to Title tag · Scan for missing tags, unreadable files, and encoding issues

**Duplicate Detection**
Compare unsorted downloads against the library using fuzzy matching, metadata, and audio fingerprinting · Find the same track duplicated across multiple artist folders · Full undo support for every move

**MusicBrainz Lookup & Tagging**
Batch look up releases by catalogue number (Anjunabeats, Tiësto / Black Hole, or any label) · Auto-tag files from confirmed lookup results · Undo tags from a backup report · Move folders based on a processed report

**Utilities**
Split a single-file FLAC + CUE sheet into individual tracks · Run multiple tools in sequence as a pipeline · Repair broken paths in .m3u/.m3u8 playlists

### [music-duplicate-finder](https://github.com/SFleet89/music-duplicate-finder)
The original standalone duplicate finder — compare an unsorted collection against an organised library with fuzzy matching, audio fingerprinting, dry-run preview, and full undo support.

---

## 🛠 Stack

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-41CD52?style=flat&logo=qt&logoColor=white)
![HTML](https://img.shields.io/badge/HTML-E34F26?style=flat&logo=html5&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat&logo=sqlite&logoColor=white)

**Libraries:** `mutagen` · `rapidfuzz` · `tqdm` · `Chromaprint (fpcalc)` · `MusicBrainz API`

---

## 📚 Currently learning

Desktop application development with PySide6 (Qt) · Cybersecurity

---

*All tools are dry-run by default — nothing moves, renames, or tags without your confirmation.*
