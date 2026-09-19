# Changelog — AcousticID Fingerprint

## v1.6 — 2026-06-03

### Added
- acoustid_cache table in music_cache.db: AcousticID lookup results are now
  cached per file (keyed by path + mtime). Re-runs check the cache first and
  skip the API entirely for already-looked-up files — apply runs after a dry
  run need zero API calls. Rate-limit delay only applies to actual API calls.
  New functions: load_acoustid_cache(), upsert_acoustid_cache().

## v1.5 — 2026-06-03

### Fixed
- Phase 3 skipped ALL files when they were cache-hits from Phase 1 (skipped=True
  in fp_results). The check now only skips hard fingerprint errors, not cache-skips.
- Phase 3 was reading info["fingerprint"] (raw integers, not in info for cached files)
  for the ACOUSTID_FINGERPRINT tag. The b64 fingerprint from Phase 2 is now stored
  in match_data["b64_fingerprint"] and used instead — correct format, always available.
  Net effect: apply runs on fully-cached folders now actually write tags.

## v1.4 — 2026-06-03

### Changed
- MUSICBRAINZ_TRACKID removed from tag writing. Only ACOUSTID_ID and
  ACOUSTID_FINGERPRINT are written. Reason: Qobuz metadata is authoritative;
  the MB recording ID from AcousticID may reference a different release and
  could confuse Picard or other MB-aware tools.

## v1.3 — 2026-06-02

### Fixed
- Cached files were silently skipped in Phase 2 (API lookup). Being in fp_cache
  means "fingerprinted", not "looked up" — so on any re-run where files were
  already cached, zero lookups happened. Phase 2 now includes all files that
  aren't errored, regardless of cache status.
- b64_dur is now used as duration fallback for cached files whose info dict
  has no "duration" key, preventing a KeyError on skipped files.
- Phase 2 log now shows how many of the lookup files are from cache.

## v1.2 — 2026-06-02

### Fixed
- 400 Bad Request errors on every file: the AcousticID API requires a base64
  Chromaprint fingerprint, but the script was sending raw comma-separated integers
  (the fpcalc -raw format). fp_cache continues to store raw integers (consistent
  with build_fp_cache.py and the duplicate finder's fingerprint_similarity()
  function). In Phase 2, fpcalc is now run a second time without -raw to obtain
  the base64 fingerprint for API submission.
- run_fpcalc() now accepts a raw=True/False parameter to select format.

## v1.1 — 2026-06-02

### Added
- Tag-writing (Phase 3): writes MUSICBRAINZ_TRACKID, ACOUSTID_ID, and
  ACOUSTID_FINGERPRINT to matched files using mutagen.
  Supports FLAC, MP3, M4A/AAC/ALAC, OGG, Opus.
- `--apply` flag required to write tags; dry-run is now the default.
  Without --apply the script shows what WOULD be tagged in the report.
- `--min-confidence` flag (default 0.80): files below threshold are skipped
  and reported as low_conf in the CSV.
- `tagged` column added to CSV report.
  Values: would_tag / yes / low_conf / no_match / tag_error / unsupported_format
- Report filename now includes _dry or _applied suffix.
- New launcher: Run - AcousticID Fingerprint (Write Tags).cmd (--apply mode).
- GUI panel v0.2: Write Tags checkbox, min-confidence spinbox, Tagged column,
  apply-mode warning label, and updated Run button label.

## v1.0 — 2026-06-02

### Added
- Initial release.
- Runs fpcalc on all audio files in a selected folder (4 parallel workers).
- Stores fingerprints in fp_cache table in music_cache.db.
- Submits fingerprints to AcousticID API (https://api.acoustid.org/v2/lookup)
  and retrieves MusicBrainz recording ID, title, and artist for each match.
- CSV report saved to reports/ after every run.
- Skip-cached mode (default): files with matching mtime already in fp_cache
  are skipped, making re-runs fast.
- --no-lookup flag to fingerprint without making API calls.
- --include-cached flag to force re-processing of all files.
- run_acoustid_fingerprint() function for GUI integration.
- GUI panel (AcousticID Fingerprint) wired into main_window.py under
  the -- IDENTIFICATION -- section.
- API key stored in music_config.json → acoustid.api_key.
