# Changelog — mbz2cue.py

---

## v1.0

### Added
- Initial release.
- Scrapes tracklist from a MusicBrainz release URL.
- Generates one `.cue` file per disc for multi-disc releases.
- Track times converted to CUE index format (MM:SS:FF at 75 frames/sec).
- Per-track PERFORMER written from MB artist data.
- `--debug_level` flag for verbose output.
