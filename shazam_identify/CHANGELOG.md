# Changelog — shazam_identify.py

---

## v1.0 — 2026-05-29

### Added
- Initial release.
- Scans a folder for audio files and identifies each one via the Shazam API (shazamio).
- Dry run by default — shows what would be tagged without writing anything.
- Apply mode (`--apply`) writes Artist, Title, Album, Year tags using mutagen.
  Supports MP3 (EasyID3), FLAC, M4A/AAC (MP4 tags), and generic easy tags.
- `--skip-tagged` flag skips files that already have Artist + Title populated.
- `--delay N` flag controls seconds between Shazam API requests (default: 0.5).
- CSV report saved to `shazam_identify/reports/` on every run (dry and applied).
  Report includes original tag values for reference/rollback.
- `run_shazam_identify()` GUI-callable entry point.
- Three .cmd launchers: Dry Run, Apply, Skip Tagged + Dry Run.
