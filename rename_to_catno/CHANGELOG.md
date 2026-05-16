# Changelog — rename_to_catno.py

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
