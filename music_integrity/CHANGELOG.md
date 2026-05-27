# Changelog — check_music_integrity.py

---

## v1.6 — 2026-05-25

### Changed (PW-01 — GUI-callable function extraction)
- Extracted `run_check_music_integrity()` as GUI-callable core. Handles both
  standard scan mode and `--from-csv` mode. Parameters: `root`, `apply`,
  `run_integrity`, `mp3_only`, `rebuild_cache`, `from_csv`, `reports_dir`,
  `progress_callback`, `log_callback`. Raises `ValueError` for bad paths.
  Returns dict: `rows`, `counts`, `report_path`, `reports_dir`.
- Moved `_args`, `APPLY_MODE`, `RUN_INTEGRITY`, `MP3_ONLY`, `FROM_CSV`,
  `REBUILD_CACHE`, `FOLDER_ARG`, `SCAN_EXTENSIONS`, and `interactive_options()`
  inside `main()` — no module-level side effects on import.
- `check_tools(run_integrity=True)` — `run_integrity` param replaces global.
- `find_audio_files(root, run_integrity, mp3_only=False)` — `mp3_only` param
  replaces globals `SCAN_EXTENSIONS` and `MP3_ONLY`; extensions computed internally.
- `run_scan(..., rebuild_cache=False, mp3_only=False, progress_callback=None)` —
  `rebuild_cache` and `mp3_only` params replace globals; `progress_callback` added.
- `_run_sequential()`, `_run_parallel()`, `apply_from_csv()` — each accepts
  optional `progress_callback(current, total, filename)`.

---

## v1.5 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## v1.4 — 2026-05-18

### Added
- Integrity results now cached in SQLite (`integrity_cache` table in `music_cache.db`).
  Files whose mtime and size are unchanged since last check are skipped automatically.
  First run checks everything; subsequent runs are fast.
- `--rebuild-cache` flag to force a full re-decode of every file, ignoring the cache.
- Summary now shows "From integrity cache" and "Freshly decoded" counts.

### Changed
- `music_tools_common.py` bumped to v2.1: added `integrity_cache` table to schema,
  schema versioning system (`schema_version` table, `SCHEMA_VERSION` constant,
  migration framework in `init_db`).

---

## v1.3 — 2026-05-18

### Changed
- Full decode integrity check (ffmpeg) is now **on by default**. Previously required `--integrity` to enable.
- Added `--quick` flag to skip the full decode check and run VBR headers only (fast mode).
- Renamed `check_music_integrity_integrity.cmd` → `check_music_integrity_quick.cmd` (now runs `--quick`).
- Updated `check_music_integrity_dry.cmd` to reflect that it now runs the full decode check by default.
- Updated all in-script messages and usage docs to reflect the new flag behaviour.

---

## v1.0 — 2026-05-02

### Added
- Initial release.
- VBR header check for MP3 files via `mp3val` (fast, always runs).
  - Detects missing or incorrect Xing/LAME/VBRI headers.
  - In `--apply` mode, repairs headers in place via `mp3val -f`.
  - Reports `vbr_needs_fix` / `vbr_fixed` / `vbr_unfixable`.
- Full decode integrity check via `ffmpeg` (slow, opt-in with `--integrity`).
  - Catches corrupt frames, truncated files, audio stream errors.
  - Informational only — cannot auto-repair corruption.
- Parallel processing for read-only checks (up to 8 threads).
- Sequential processing for apply mode (safer for file writes).
- Folder picker (tkinter) — no path typing needed.
- Reports saved to `<script_folder>/reports/`.
- Descriptive filename suffix: `_dry`, `_applied`, `_dry_integrity`, `_applied_integrity`.
- `--mp3-only` flag to skip FLAC/AAC/M4A files.
- Tool discovery: checks next to script first, then PATH.
- Graceful degradation if `mp3val` or `ffmpeg` not found.
