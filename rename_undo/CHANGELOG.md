# Changelog — rename_undo.py

---

## v1.4 — 2026-05-24

### Changed (pre-work PW-01: GUI-callable function extraction)
- Extracted `run_rename_undo(csv_path, apply, progress_callback, log_callback) -> dict` as the callable core function. GUI can call this directly; CLI calls `main()` as before.
- Moved module-level `interactive_options([])` call inside `main()`.
- `run_rename_undo()` raises `ValueError` for missing CSV instead of `sys.exit(1)`.
- Report writing moved into `run_rename_undo()`; report_path returned in result dict.
- Dry-run mode now also writes a report (status = "pending") for review.
- Added explicit `--pick` and `--path` flag support.
- Fixed banner version (was showing "v1.2" despite being v1.3).

---

## v1.3 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## v1.2 — 2026-05-20

### Changed
- CSV reading now uses `load_csv()` from `music_tools_common` instead of inline `csv.DictReader`. Removed `import csv` (no longer needed directly).
- CSV writing now uses `write_csv()` from `music_tools_common` instead of inline `csv.DictWriter`. Column order preserved via explicit `fieldnames` argument.
- `pick_file()` remains local — it's a file picker for CSVs, distinct from the folder picker in `music_tools_common`.

---

## v1.1 — 2026-05-18

### Fixed
- `reports_dir` and file picker `initialdir` were pointing to `SCRIPT_DIR.parent / "reports"` instead of `SCRIPT_DIR / "reports"`. Standalone script — fixed to save next to the script.
- Stripped 14 null bytes of binary padding from end of file.

---

## v1.0 — 2026-04-21

### Added
- Initial release.
- Reverses folder renames made by `rename_to_catno.py` using its CSV report.
- Dry run by default — `--apply` to execute.
- File picker opens if no CSV path is specified on the command line.
- Skips rows where the rename never happened or the folder no longer exists.
