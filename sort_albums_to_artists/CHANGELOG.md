# Changelog — Sort Albums Into Artist Folders

---

## v1.5 — 2026-05-24

### Changed (pre-work PW-01: GUI-callable function extraction)
- Extracted `run_sort_albums_to_artists(folder, apply, conflict_resolver, empty_resolver, progress_callback, log_callback) -> dict` as the callable core function. GUI can call this directly; CLI calls `main()` as before.
- `conflict_resolver` and `empty_resolver` are optional callbacks; both default to the existing interactive CLI prompts (`prompt_conflict` / `prompt_empty`). GUI supplies its own dialog callables.
- Moved module-level `interactive_options([])` call inside `main()`.
- Moved module-level `DRY_RUN`, `PICK_DIR`, `_path` flag parsing inside `main()`.
- `run_sort_albums_to_artists()` raises `ValueError` for bad folder instead of `sys.exit(1)`.
- `write_report()` now returns the report `Path` (or `None` on error).
- Fixed banner version (was showing "v1.0" despite being v1.4).
- `main()` runs dry-run via `run_sort_albums_to_artists(apply=False)` then does its own apply loop (avoids re-scanning; interactive conflict resolution already completed in the dry-run phase).

---

## v1.4 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## v1.3 — 2026-05-22

### Fixed
- Removed dead `DEFAULT_FOLDER` constant (`C:\Users\neo_s\Downloads\...`).
- Simplified folder resolution: the confusing `if PICK_DIR or (not _path and not PICK_DIR)` conditional replaced with a clean `if _path → else pick_folder → exit if None` pattern.

---

## v1.2 — 2026-05-18

### Fixed
- `REPORTS_FOLDER` was a hardcoded absolute path. Added `SCRIPT_DIR = Path(__file__).parent` and changed `REPORTS_FOLDER` to `SCRIPT_DIR / "reports"`.
- Truncation bug: file ended with `main(` missing its closing `)`. Restored.

---

## v1.0 — 2026-03-20

### Initial release
- Scans a folder of album subfolders and reads Album Artist tag (falling back to Artist) from music files
- Handles CD subfolders correctly — reads tags recursively within each album folder
- Prompts interactively to resolve tag conflicts and missing tags
- Collision detection — skips albums whose destination alrea