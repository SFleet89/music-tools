# Changelog — Utilities

---

## rename_album_folders.py

See [CHANGELOG_rename_album_folders.md](CHANGELOG_rename_album_folders.md) for the full version history.

Current version: **v2.2**

---

## rename_cd_folders.py

### v1.0 — 2026-03-14

#### Added
- Initial release
- Finds folders named `CD #` (with a space) and renames them to `CD#` (no space)
- Handles any number after CD (CD 1 through CD 99+)
- Dry run by default — `--apply` required to rename for real
- `--path` flag to specify root folder on the command line
- Skips target if destination already exists
- CSV report saved after every run (dry and live)
