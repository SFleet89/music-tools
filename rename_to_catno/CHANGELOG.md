# Changelog — rename_to_catno.py

---

## v1.5 — 2026-05-24

### Changed (pre-work PW-01: GUI-callable function extraction)
- Extracted `run_rename_to_catno(folder, apply, progress_callback, log_callback) -> dict` replacing the old `run_rename()` internal function. GUI can call this directly; CLI calls `main()` as before.
- Moved module-level `interactive_options([])` call inside `main()`.
- `run_rename_to_catno()` raises `ValueError` for bad folder instead of calling `sys.exit(1)`.
- Report writing moved into `run_rename_to_catno()` (previously done in `main()`); report_path returned in result dict.
- Added `progress_callback` and `log_callback` support throughout the scan loop.
- Fixed banner version (was showing "v1.1" despite being v1.4).
- Added explicit `--pick` flag support (previously defaulted to folder picker implicitly).

---

## v1.4 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## v1.3 — 2026-05-18

### Fixed
- `reports_dir` was pointing to `SCRIPT_DIR.parent / "reports"` (parent of `rename_to_catno/`) instead of `SCRIPT_DIR / "reports"`. This is a standalone script — reports should save next to the script. Fixed.
- Stripped 7 null bytes of binary padding from end of file.

---

## v1.1 — 2026-04-25

### Added
- Catno fallback: if no `CATALOGNUMBER` tag is present (or tag contains a placeholder like `none`), catno is parsed from the folder name using ANJ/ANJCD/ANJDEEP regex.
- Catno normalisation: `ANJ-001` → `ANJ001`, `ANJ 216D` → `ANJ216D`.
- Album ` / ` separators replaced with ` & ` (double A-side releases).
- Double spaces collapsed after sanitising.
- Placeholder catno values (`none`, `n/a`, empty) treated as missing and trigger folder name fallback.

---

## v1.0 — 2026-04-21

### Added
- Initial release.
- Recursively scans a folder for album subfolders containing audio files.
- Reads `CATALOGNUMBER` and `ALBUM` tags from the first audio file in each folder.
- Renames folder to `CATNO - Album Name` format.
- Dry run by default — `--apply` to rename.
- Collision detection, confirmation prompt, CSV report.
