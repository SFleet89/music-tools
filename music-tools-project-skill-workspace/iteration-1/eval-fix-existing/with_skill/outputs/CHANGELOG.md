# Changelog — rename_album_folders.py

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
- Track titles now read alongside album tags in a single metadata pass.
- Report includes New Name and Files count columns.

---

## v1.0 — 2026-03-14

### Added
- Initial release.
- Reads album tag and renames folder to match.
- Conflict handling with prompt to choose or enter custom name.
- `--pick`, `--path`, `--apply` flags.
- Illegal character sanitisation for Windows folder names.
- Same-parent collision check before renaming.
- Final y/n confirmation prompt.
