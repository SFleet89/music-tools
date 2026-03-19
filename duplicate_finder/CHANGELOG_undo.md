# Changelog — undo_duplicates.py

All notable changes to the Music Duplicate Undo script are documented here.

---

## [2.2] - 2026-03-14

### Added
- **`--list` flag** — prints a full summary of the CSV before undoing anything: total moved files, breakdown by category and match method, and a file-by-file listing showing the filename, current location, original location, and whether each file is still at its destination. Useful for reviewing a live run report from weeks ago before committing to an undo.
- **`--filter-method` flag** — filter the undo by match method, e.g. `--filter-method "audio fingerprint"` to only undo fingerprint-matched duplicates, or `--filter-method "filename/metadata"` for metadata matches only. Combines with `--filter-category` and `--dry-run`.
- **`undo_report_viewer.html`** — standalone browser-based viewer for live run reports. Drop any `music_report_*_live_*.csv` to see everything that was moved: category, match method, original location, and current location. Filter by category or fingerprint matches, search by path. Includes a **Copy undo command** button that copies the exact terminal command for the loaded file.

### Fixed
- **`--list-categories` was listed in help text but not implemented** — the flag now works correctly, printing all unique category values and match methods with row counts.

### Changed
- Match method is now shown alongside category in the console output for each restored file, making it easier to see at a glance how each duplicate was originally found.

---

## [2.1] - 2026-03-04

### Added
- **`--list-categories` flag** — prints all unique category values found in the CSV report along with row counts and how many were moved. Useful for checking valid values before using `--filter-category`.
- **Compatibility note in docstring** — clarifies that `Match Method` and `Why Not Exact` columns present in v3.1+ reports are intentionally ignored.

### Fixed
- **`--filter-category` docstring** — previously listed `"Standard Duplicate"` and `"Higher Quality Match"` as the valid category values. Corrected to reflect the actual CSV values: `"Exact Match"`, `"DUPLICATE"`, and `"BETTER QUALITY"`. Old v3.0 labels still accepted for backward compatibility.

---

## [2.0] - 2026-02-27

### Added
- Full rewrite to support the v3.0 CSV report format from find_music_duplicates.py.
- `--dry-run` flag — preview restores without moving anything.
- `--filter-category` flag — undo only a specific category of files.
- Handles missing files and conflicts gracefully (skips with explanation rather than crashing).
- Summary at end of run showing restored, skipped, and error counts.
- Skips dry-run rows from the CSV automatically (rows with "Would move" actions).

---

## [1.0] - 2026-02-27

### Added
- Initial script — reads log file from find_music_duplicates.py and moves files back to original locations.
- Basic error handling.
