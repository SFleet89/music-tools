# Changelog — sort_cd_tracks.py

All notable changes to Sort CD Tracks are documented here.

---

## v1.4 — 2026-05-24

### Changed (pre-work for GUI application)
- Extracted all core logic into `run_sort_cd_tracks(folder, apply, recursive, progress_callback, log_callback)` — callable directly by the GUI without going through the CLI layer.
- `main()` is now a thin CLI wrapper: handles flag parsing, folder picking, banner, confirmation prompt, then calls `run_sort_cd_tracks()`. `.cmd` launchers unchanged.
- Replaced `sys.exit()` inside the core logic with `raise ValueError(...)`. `main()` catches these and exits as before; the GUI catches them and shows a dialog.
- Added `progress_callback(current, total, message)` parameter for GUI progress bar integration.
- Added `log_callback(message)` parameter — defaults to `print()` so CLI output is unchanged.
- Core function now returns a structured `dict` (moved, skipped, errors, no_tag, skipped_albums, results, report_path) instead of printing a summary only.

---

## v1.3 — 2026-05-23

### Fixed
- Removed the `if len(by_disc) < 2` guard that skipped folders where all files shared only one disc number. Folders tagged with only disc 1 (single-album, no disc 2) now correctly have their files moved into a CD1/ subfolder.
- Fixed version banner — was incorrectly showing "v1.0" since the initial release; now shows the correct version.

### Added
- Auto-detect recursive mode: if the pointed folder contains no music files directly but its subfolders do, the script automatically switches to recursive mode without needing `--recursive`. A message is printed so the user knows what happened.
- `interactive_options()` menu: script now presents a numbered options menu at startup so --apply and --recursive can be chosen interactively. .cmd launchers updated — Dry Run passes no flags, Apply passes only --apply.

---

## v1.2 — 2026-05-18

### Fixed
- `REPORTS_FOLDER` was a hardcoded absolute path. Added `SCRIPT_DIR = Path(__file__).parent` and changed `REPORTS_FOLDER` to `SCRIPT_DIR / "reports"`.

---

## [1.1] - 2026-03-21

### Added
- **`--recursive` flag** — instead of pointing the script at a single album folder, you can now point it at a root folder (artist or library level) and it will walk through every subfolder automatically. Folders that are already sorted into CD subfolders, single-disc albums, and folders with no disc tags are all skipped cleanly with a summary at the end. The dry run preview groups output by album so you can review all changes at once before committing.

---

## [1.0] - 2026-03-21

### Added
- Initial release.
- Reads DISCNUMBER tag from music files and moves them into CD1/CD2/CD3 subfolders.
- Handles both plain number format (`1`, `2`) and fraction format (`1/2`, `2/2`).
- Folder picker dialog opens automatically when no `--path` is given.
- `--apply` flag required to move files — dry run by default.
- Files with no disc tag are left in place and noted in the report.
- Collision check — skips files where the destination already exists.
- CSV report saved after every run (dry and live).
- Final y/n confirmation before any files are moved.
