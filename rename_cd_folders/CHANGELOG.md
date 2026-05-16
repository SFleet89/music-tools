# Changelog — rename_cd_folders.py

---

## v1.1 — 2026-05-16

### Fixed
- `REPORTS_FOLDER` was incorrectly pointing to `filename_scanner\reports`. Now saves reports to `rename_cd_folders\reports\` (next to the script).
- Replaced `Path.rename()` with `shutil.move()` for safer cross-device moves, consistent with project standards.
- Removed hardcoded `DEFAULT_FOLDER` — script now requires `--pick` or `--path` to avoid silently scanning the wrong location.

### Added
- `--pick` flag: opens a native folder-picker dialog (same pattern as other tools).
- `.cmd` files updated to use `--pick` by default (no hardcoded paths).

---

## v1.0 — 2026-03-14

### Added
- Initial release.
- Finds folders named `CD #` (with a space) and renames to `CD#` (no space).
- Handles any number after CD (CD 1 through CD 99+).
- Dry run by default — `--apply` required to rename.
- `--path` flag to specify root folder.
- Skips if destination already exists.
- CSV report saved after every run.
