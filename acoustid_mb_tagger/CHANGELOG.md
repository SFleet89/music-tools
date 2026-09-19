# CHANGELOG — acoustid_mb_tagger.py

## v1.1 — 2026-06-05

### Fixed
- `musicbrainzngs.get_recording_by_id()` called with invalid includes
  `"release-group"` and `"labels"` — neither is valid for the recording
  endpoint in musicbrainzngs. Changed to `["artists", "releases",
  "artist-credits"]`. Release-group data (type, artist-credit) is embedded
  in each release object automatically when `releases` is included.
- `_get_mb_cache()` now returns `None` when `mb_recording_id` is NULL in the
  cache row. Previously, stale rows with NULL metadata (e.g. from failed prior
  runs) were treated as valid cache hits, causing all files to show `no_match`
  without hitting the API. Now those rows are treated as cache misses and
  re-queried, which also allows previously unmatched files to be retried as
  MusicBrainz data improves over time.

## v1.0 — 2026-06-05

### Added
- Initial release.
- Scans folder for files with `ACOUSTID_ID` tags (written by `acoustid_fingerprint.py`).
- AcoustID API lookup by track ID — gets associated MusicBrainz recording IDs.
- MusicBrainz recording lookup via `musicbrainzngs` — fetches full metadata
  (title, artist, album, albumartist, date, tracknumber, discnumber, label,
  catalogue number, country, release type, all MB IDs).
- Cache layer: `mb_acoustid_cache` table in `music_cache.db` — keyed by
  `acoustid_id`. Apply pass after dry run makes zero API calls.
- Three-state tag logic:
  - No existing tags → write all selected tags.
  - Tags match MB (title + artist) → write MB IDs only.
  - Tags differ from MB → flag for review (or override with `--conflict`).
- Format-aware tag writer: FLAC, MP3 (ID3), M4A/AAC/ALAC, OGG Vorbis, Opus.
- `--conflict flag / mb_wins / keep_existing` flag.
- `run_acoustid_mb_tagger()` GUI-callable core function with `progress_callback`
  and `log_callback` hooks.
- Timestamped CSV report to `acoustid_mb_tagger/reports/`.
- Two `.cmd` launchers (dry run + apply).
