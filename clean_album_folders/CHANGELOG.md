# Changelog — clean_album_folders.py

All notable changes to Clean Album Folders are documented here.

---

## clean_album_folders_viewer.html

### v1.1 — 2026-04-05

#### Fixed
- Font size buttons (A−/A+) now correctly resize all table text. Previously the change targeted the container div but was overridden by hardcoded CSS on table and cell elements.

#### Changed
- Table fills the full window height instead of being capped at `max-height: calc(100vh - 420px)`.

#### Added
- Column resize handles — drag the right edge of any column header to adjust its width.

---

## [1.0] - 2026-03-22

### Added
- Initial release.
- Scans all folders recursively and moves non-music files to a holding folder.
- Holding folder mirrors the original directory structure for easy restore.
- CUE file detection — keeps CUE files only when paired with a single audio file larger than 100MB (single-file rip needing splitting). Removes CUE files in normal multi-track albums.
- Folder picker dialog opens automatically when no `--path` is given.
- `--apply` flag required to move files — dry run by default.
- Extension breakdown in console output showing how many of each file type would be moved.
- Collision handling — if a file already exists in the holding folder a numeric suffix is added.
- Final y/n confirmation before any files are moved.
- CSV report saved after every run (dry and live).
