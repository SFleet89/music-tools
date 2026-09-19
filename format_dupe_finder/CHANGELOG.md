# Changelog — Format Duplicate Finder

## v1.0 — 2026-06-13

### Added
- Initial release
- Detects format duplicate pairs: same-folder mixed content (Option A) and sibling folders with similar names (Option B)
- Sibling folder name normalisation: strips `[MP3]`, `[FLAC]`, `(320)`, `[LOSSLESS]` etc. before comparing
- ffmpeg full-decode integrity check on all FLAC files; results cached in `integrity_cache` table in `music_cache.db`
- fpcalc Chromaprint fingerprint comparison for MP3 ↔ FLAC pairs; results cached in `fp_cache` table in `music_cache.db`
- `--sample` flag: `3` (default — first 3 tracks), `half` (first 50%), `all` (every track)
- `--no-fp` flag: skip fingerprinting — integrity + track count only
- `--threshold N` flag: override FP similarity threshold (default from `music_config.json`, fallback 85%)
- Verdict logic: `SAFE TO DELETE MP3` / `NEEDS REVIEW` / `FLAC CORRUPT`
- CSV report saved to `format_dupe_finder/reports/` with timestamp
- Shared SQLite cache (`music_cache.db`) reused across tools — FP and integrity results built up over time
- `run_format_dupe_finder()` GUI-callable core function with `progress_callback` and `log_callback`
- One `.cmd` launcher: `Run - Format Dupe Finder.cmd` (read-only scan, folder picker)
