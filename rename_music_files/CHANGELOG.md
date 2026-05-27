# rename_music_files.py — Changelog

## v1.2 — 2026-05-24

### Changed (pre-work PW-01: GUI-callable function extraction)
- Extracted `run_rename_music_files(folder, apply, template, progress_callback, log_callback) -> dict` as the callable core function. GUI can call this directly; CLI calls `main()` as before.
- Moved module-level flag parsing (`DRY_RUN`, `PICK_DIR`, `NO_CONFIRM`, `_path_flag`, `_format_flag`, `FORMAT`) inside `main()`.
- Moved `interactive_options([])` inside `main()`.
- `apply_renames()` now accepts optional `progress_callback` and `log_callback` parameters.
- `run_rename_music_files()` raises `ValueError` for bad folder or unknown template variables.
- Fixed banner version (was showing "v1.0" despite being v1.1).

---

## v1.1 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## v1.0 — 2026-05-20

### Added
- Initial release
- FileBot-style template engine: `{t}`, `{n}`, `{artist}`, `{album}`, `{pi}`,
  `{pi.pad(N)}`, `{y}`, `{af}`, `{kbps}`, `{disc}`
- Default format: `{pi.pad(2)} - {t}`
- Recursive folder scan (all subfolders)
- Dry-run by default; `--apply` to rename for real
- Skips files with missing required tags; logs them to CSV
- Collision detection: skips files where the target name already exists
- `already_correct` status for files that already match the template
- Confirmation prompt in apply mode (bypass with `--no-confirm`)
- Template validation: unknown variables reported as an error before scanning
- CSV report saved to `rename_music_files/reports/` on every run
- Two `.cmd` launchers (dry run and apply)
- `--pick` folder dialog; `--path` for scripted use
