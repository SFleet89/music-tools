# Changelog — Sort Albums Into Artist Folders

---

## v1.0 — 2026-03-20

### Initial release
- Scans a folder of album subfolders and reads Album Artist tag (falling back to Artist) from music files
- Handles CD subfolders correctly — reads tags recursively within each album folder
- Prompts interactively to resolve tag conflicts and missing tags
- Collision detection — skips albums whose destination already exists
- Illegal Windows characters stripped from artist folder names automatically
- Folder picker dialog opens by default when no path is specified
- Dry run by default — nothing moves until `--apply` is passed
- CSV report saved after every run (dry and live)
- Supports MP3, FLAC, AAC, M4A
