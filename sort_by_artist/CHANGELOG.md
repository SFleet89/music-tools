# Changelog — Sort By Artist

## v1.3 — 2026-05-24

### Changed (pre-work PW-01: GUI-callable function extraction)
- Extracted `run_sort_by_artist(folder, apply, progress_callback, log_callback) -> dict` as the callable core function. GUI can call this directly; CLI calls `main()` as before.
- Moved module-level `interactive_options([])` call inside `main()`.
- Moved module-level `DRY_RUN`, `PICK_DIR`, `_path_flag` flag parsing inside `main()`.
- Added `apply: bool = False` parameter to `scan_folder()` — replaces the global `DRY_RUN` reference inside that function (sets status to "pending" vs "would_move" accordingly).
- `run_sort_by_artist()` raises `ValueError` for bad folder instead of `sys.exit(1)`.
- Fixed `VERSION` constant (was "1.1" despite being v1.2; bumped to "1.3").
- Fixed docstring version (was "v1.2"; bumped to "v1.3").
- `main()` calls `run_sort_by_artist(apply=False)` for the dry plan, then executes apply directly via `apply_moves()` after confirmation (avoids re-scanning for the apply step).

---

## v1.2 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## v1.1 — 2026-05-18

### Fixed
- **Feat-stripping false positive** — artist names that begin with `Ft.`/`Feat.` (e.g. "Ft. Nox") were being stripped to an empty string, causing the file to be skipped with "no artist detected". Guard added: if stripping consumes the entire string, the original name is kept.
- **Various Artists tag now falls back to filename** — files tagged as "Various Artists" (or `VA`, `V.A.`, etc.) previously stopped at the tag and were skipped. Detection now falls through to filename parsing before giving up.

### Changed
- Dry-run status changed from `pending` to `would_move`, consistent with the rest of the project's dry-run conventions.
- `destination` column in CSV report now records the destination **folder** only (e.g. `...\Unsorted\Tiësto`), not the full file path. Makes the report easier to review at a glance.

---

## v1.0 — 2026-05-18

### Added
- Initial release.
- Non-recursive scan of a flat audio folder.
- Artist detection: mutagen tag first, then "Artist - Title" filename pattern.
- Featured-artist stripping via regex (`ft.`, `feat.`, `featuring`, `with`).
- Various Artists variants (`VA`, `V.A.`, `Various Artists`, etc.) are skipped — files left in place.
- Collision handling: appends counter suffix `(1)`, `(2)`, etc. if destination filename already exists.
- Dry run by default; `--apply` required to move files.
- Confirmation prompt before any moves in `--apply` mode.
- `--pick` opens a native Windows folder dialog; `--path` for scripted use.
- Timestamped CSV report saved to `sort_by_artist/reports/` after every run.
- Two `.cmd` launchers (Dry Run and Apply).
