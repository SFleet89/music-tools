# Changelog — sort_cd_tracks.py

All notable changes to Sort CD Tracks are documented here.

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
