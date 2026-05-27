# Changelog — repair_playlists.py

---

## v1.8 — 2026-05-24

### Changed (pre-work PW-01: GUI-callable function extraction)
- Extracted `run_repair_playlists_scan(playlists_dir, music_dir, threshold, cache_path, reports_dir, progress_callback, log_callback) -> dict` as GUI-callable scan core. Raises `ValueError` for bad paths or no .m3u files; returns `all_results`, `counts`, `methods`, `missing_entries`, report paths, and `timestamp`.
- Extracted `run_repair_playlists_apply(all_results, output_dir, selections, reports_dir, log_callback) -> dict` as GUI-callable apply core. Takes the `all_results` dict from the scan phase and a pre-loaded `selections` dict; returns `write_repaired_playlists()` summary counts.
- `main()` refactored to call both core functions; path picking and argparse remain in `main()` only.
- Removed orphaned empty `#  SELECTIONS JSON` section header that appeared before `main()`.
- Fixed banner version (was showing "v1.7" without version in header; now shows `v1.8` inline).
- GUI workflow: call `run_repair_playlists_scan()` → show HTML selector or own review UI → get selections → call `run_repair_playlists_apply()`.

---

## v1.7 — 2026-05-17

### Changed
- Cache source switched from JSON (`music_cache.json`) to the shared SQLite database (`music_cache.db`) in the project root.
- `load_from_cache` now opens the database via `open_db()` from `music_tools_common` and queries `metadata_cache` directly — no JSON parsing, no `import json` at runtime.
- `DEFAULT_CACHE` now resolves via `DB_PATH` imported from `music_tools_common` (falls back to `None` gracefully if the module is unavailable, causing the script to fall through to `scan_library`).
- Docstring and `--cache` help text updated to reference `music_cache.db`.
- Added `import sqlite3` (kept for completeness; actual DB access goes via the common helper).

---

## v1.6 — 2026-05-17

### Fixed
- Default cache path corrected: was looking for `music_cache.json` in the script's own folder (`repair_playlists/`); now correctly points to `duplicate_finder/music_cache.json` where the cache actually lives.

---

## v1.5 — (previous)

- Internal improvements and stability fixes.

---

## v1.1 — 2026-05-02

### Added
- Folder and file pickers now open by default — no need to type paths.
- `--playlists` and `--music` flags still accepted to skip pickers (used by .cmd files).
- `--selections` picker opens automatically in apply mode when ambiguous matches exist.
- `.cmd` files regenerated after every run with current paths.
- "Press Enter to close" prompt added so the terminal window does not vanish immediately.
- Next-steps instructions printed at end of dry run summary.

---

## v1.0 — 2026-04-29

### Added
- Initial release.
- Scans `.m3u` playlist files and repairs broken paths against current library.
- Fuzzy name matching (rapidfuzz or difflib fallback) with configurable threshold.
- Track-number-prefix stripping for robust stem matching.
- Three-bucket categorisation: resolved / ambiguous / missing.
- HTML selector for ambiguous matches — side-by-side album/path comparison with radio-button pick.
- Selections JSON and `--selections` flag for applying picks in a separate run.
- Relative path output (forward slashes) — playlists work across drives and machines.
- `--apply` flag required to write files (dry run by default).
- Confirmation prompt before writing repaired playlists.
- Reports: CSV, missing log (`.txt`), HTML selector.
- Graceful encoding fallback: UTF-8 then latin-1 for old playlists.
- Unresolved/missing entries preserved with `# REPAIR_UNRESOLVED` or `# REPAIR_MISSING` comments.
