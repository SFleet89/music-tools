# Changelog — clean_album_folders.py

All notable changes to Clean Album Folders are documented here.

---

## v1.3 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## clean_album_folders_viewer.html

### v1.1 — 2026-04-05

#### Fixed
- Font size buttons (A−/A+) now correctly resize all table text. Previously the change targeted the container div but was overridden by hardcoded CSS on table and cell elements.

#### Changed
- Table fills the full window height instead of being capped at `max-height: calc(100vh - 420px)`.

#### Added
- Column resize handles — drag the right edge of any column header to adjust its width.

---

## [1.2] — 2026-05-22

### Fixed
- Removed dead `DEFAULT_FOLDER` constant (was pointing to old ThinQ backup path, never used since `pick_folder()` was already the fallback).
- Removed hardcoded `HOLDING_FOLDER` absolute path.

### Changed
- `DEFAULT_HOLDING` is now `SCRIPT_DIR / "holding"` — relative to the script, no hardcoded absolute paths.

### Added
- `--holding "C:\path"` flag — overrides the holding folder destination at runtime without editing the script.

---

## [1.1] — 2026-05-17

### Changed
- `pick_folder` now imported from `music_tools_common` (removed local copy).

---

## [1.0] - 2026-03-22

### Added
- Initial release.
- Scans all folders recursively and moves non-music files to a holding folder.
- Holding folder mirrors the original directory structure for easy restore.
- CUE file det