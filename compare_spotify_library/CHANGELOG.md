# Changelog — compare_spotify_library

## v1.0 — 2026-05-31

### Added
- Initial release
- Scans Spotify staging folder and main library using mutagen
- Two-tier matching: exact (albumartist + album + title) and loose (artist + title)
- Quality scoring: format tier + bitrate for lossy formats
- Recommendations: UPGRADE / SAME / SKIP / NEW
- Report-only mode — no files moved or deleted
- Timestamped CSV saved to `reports\` after every run
- Two `.cmd` launchers
