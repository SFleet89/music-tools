# Changelog — build_fp_cache.py

All notable changes to the Music Cache Builder are documented here.

---

## [1.0] - 2026-03-09

### Added
- Initial release.
- **Metadata cache building** — scans the organized folder and writes `music_cache.json`, the same cache used by `find_music_duplicates.py`. Files are keyed by path + modification time + size so changed files are detected and refreshed automatically.
- **Fingerprint cache building** — generates Chromaprint fingerprints via `fpcalc` and writes `music_fp_cache.json`. Cache is compatible with `find_music_duplicates.py` and `find_library_dupes.py` — all three tools share one cache file if pointed at the same path.
- **Incremental by default** — only processes new or changed files on each run. Use `--rebuild` to wipe and start fresh.
- **Fingerprint failure caching** — files that fail fingerprinting have their failure cached so they aren\'t retried on every run. Use `--rebuild` to force a retry after fixing a file.
- **Fingerprint warnings CSV** — files with invalid or failed fingerprints saved to `fp_warnings_TIMESTAMP.csv` in the reports folder. Same format as the warnings CSV produced by `find_music_duplicates.py`.
- **`--metadata-only`** — build metadata cache only, skipping fingerprinting.
- **`--fp-only`** — build fingerprint cache only, skipping metadata.
- **`--rebuild`** — wipe selected cache(s) and regenerate from scratch.
- **`--path`** — override the organized folder path without editing the config.
- **`--threads`** — override the thread count without editing the config.
- **`--config`** — specify an alternative config file.
- Reads all settings from `music_config.json` — same config as `find_music_duplicates.py`, no separate configuration needed.
