# Changelog — rename_album_folders.py

---

## v2.6 — 2026-05-24

### Changed (pre-work PW-01: GUI-callable function extraction)
- Extracted `run_rename_album_folders(folder, apply, filter_ok, max_depth, conflict_resolver, progress_callback, log_callback) -> dict` as the callable core function. GUI can call this directly.
- `find_album_folders()` now takes `max_depth` and `filter_ok` as parameters instead of reading module-level variables.
- `conflict_resolver` callback added: GUI passes its own dialog; CLI passes `prompt_conflict()`; if None, conflicts are flagged but skipped.
- Moved module-level flag parsing inside `main()`.
- `Path.rename()` replaced with `shutil.move()` throughout.
- Fixed banner version (was incorrectly showing "v2.0" despite being v2.5).
- `write_report()` now returns `Path|None`.
- `run_rename_album_folders()` raises `ValueError` for bad folder.
- Added `interactive_options([])` at top of `main()`.

---

## v2.5 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## v2.4 — 2026-05-22

### Fixed
- Removed hardcoded `DEFAULT_FOLDER` constant (`C:\Users\neo_s\Downloads\...`). Script now falls back to `config_organized_folder()` from `music_tools_common` when no `--path` or `--pick` is given.

### Changed
- Folder resolution order: `--path` → `--pick` dialog → `config_organized_folder()` from `music_config.json` → clear error message with usage hint.

---

## v2.3 — 2026-05-18

### Fixed
- `REPORTS_FOLDER` was a hardcoded absolute path. Added `SCRIPT_DIR = Path(__file__).parent` and changed `REPORTS_FOLDER` to `SCRIPT_DIR / "reports"`.
- Truncation bug: file ended with `main(` missing its closing `)`. Restored.

---

## v2.2 — 2026-03-19

### Fixed
- Multi-CD detection not working in practice — `rglob` was visiting CD subfolders before their parent, causing each CD subfolder to be added as an individual rename candidate and producing collision errors. Fixed by sorting all directories by depth before processing so parents are always evaluated before children.

---

## v2.1 — 2026-03-15

### Added
- Multi-CD album support — folders containing only CD/Disc/Disk subfolders are detected as multi-CD albums. The parent folder is renamed; CD subfolders are left untouched.
- Multi-CD column in CSV report (`Yes`/`No`).
- Multi-CD label in console preview showing disc count.

### Changed
- `find_album_folders()` now performs a two-pass check: CD subfolders first (multi-CD structure), then direct music file detection. CD subfolders belonging to a detected parent are excluded to prevent double-processing.

---

## v2.0 — 2026-03-14

### Added
- Reports saved after every run (dry and live) — timestamped CSV to reports folder.
- Track titles shown in conflict prompt to help identify the correct album — up to 4 titles sorted by track number per option.
- `--filter` flag — skip folders already correctly named.
- `--depth N` flag — restrict scan to folders exactly N levels deep.
- Cross-folder collision detection before renaming — both folders skipped and warned if two would end up with the same name.

### Changed
- Track titles now read alongside album tags in a single metadata p