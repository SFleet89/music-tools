# Changelog — Pipeline

## v1.2 — 2026-05-25

### Changed
- **PW-01**: Added `run_pipeline(batch_path, steps, apply, progress_callback, log_callback) -> dict` — GUI-callable entry point. Raises `ValueError` for missing path. Returns `steps_run`, `steps_skipped`, `steps_failed`, `report_path`.
- Module-level `interactive_options([])`, `DRY_RUN`, `PICK_DIR`, `_path_flag`, `_steps_preselect` removed; moved inside `main()`.
- `build_command()`, `run_step()`, `write_report()` now accept explicit `dry_run` parameter instead of reading a global. `select_steps()` now accepts `steps_preselect` parameter. No behaviour change when run from CLI.

## v1.1 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## v1.0 — 2026-05-18

### Added
- Initial release.
- Interactive step menu: shows all 5 pipeline steps with descriptions; user picks which to run (or "all").
- `--steps 1 2 3` flag to pre-select steps without the interactive menu.
- Dry-run mode (default): shows planned commands and saves a report but does not launch any scripts.
- Apply mode (`--apply`): launches each selected script in sequence, waiting for completion before moving to the next. Passes `--apply` and `--path` to each script automatically.
- After each step, prompts "Continue to next step?" — remaining steps are marked `skipped` in the report if the user stops early.
- CSV report saved to `pipeline/reports/` with step number, name, status, exit code, and full command used.
- `--pick` (folder dialog) and `--path` flags following project conventions.
- Script existence check at startup — exits with a clear error if any selected script is missing.
