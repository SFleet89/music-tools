# Changelog — fix_featuring.py

---

## v1.2 — 2026-04-25

### Added
- `--from-csv` flag: applies changes from a dry-run CSV without re-scanning. A file picker opens to select the CSV. Only `pending` rows are processed. Each file's current tags are verified against the dry-run snapshot before writing — a warning is shown if a tag changed between the dry run and now.

---

## v1.1 — 2026-04-25

### Fixed
- Unicode lookalike characters (One Dot Leader U+2024, non-breaking hyphens, etc.) in artist tags were invisible to the regex, causing all files to report `no_featuring`. Tags are now normalised to ASCII before matching and when writing back.
- Reports folder was being saved to the parent of the script folder instead of inside it.

---

## v1.0 — 2026-04-21

### Added
- Initial release.
- Moves featuring credits from Artist tag to Title tag.
- Handles `feat.`, `ft.`, `featuring` with or without brackets.
- Album Artist tag is not modified.
- Dry run by default — `--apply` required to write tags.
- CSV report with original and new values for both Artist and Title.
