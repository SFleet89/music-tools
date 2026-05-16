# Changelog — rename_undo.py

---

## v1.0 — 2026-04-21

### Added
- Initial release.
- Reverses folder renames made by `rename_to_catno.py` using its CSV report.
- Dry run by default — `--apply` to execute.
- File picker opens if no CSV path is specified on the command line.
- Skips rows where the rename never happened or the folder no longer exists.
