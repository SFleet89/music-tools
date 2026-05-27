# Changelog — Duplicate Finder Tools

## find_music_duplicates.py — v3.12 — 2026-05-25

### Changed (PW-06 — Config centralisation)
- Removed local `load_config()` function. Now imports `load_config` from `music_tools_common` — single shared reader for `music_config.json`.
- Local folder validation logic extracted to `_validate_config(cfg)` helper, called immediately after `load_config()` at both call sites.

---

## find_music_duplicates.py — v3.11 — 2026-05-25

### Changed (PW-01 — GUI-callable function extraction)
- Extracted `run_find_music_duplicates()` as GUI-callable core. Parameters:
  `unsorted_folder`, `organized_folder`, `duplicates_folder`, `better_quality_folder`,
  `dry_run`, `no_review`, `near_miss`, `clear_cache`, `clear_fp_cache`,
  `use_fingerprints`, `match_mode`, `config_file`, `log_folder`,
  `progress_callback`, `log_callback`. Raises `ValueError` for bad paths or
  invalid config. Returns dict: `cats`, `counts`, `report_path`, `log_path`,
  `reports_dir`.
- Moved all module-level flags (`DRY_RUN`, `CLEAR_CACHE`, `CLEAR_RESUME`,
  `CLEAR_FP_CACHE`, `NO_REVIEW`, `NEAR_MISS`, `_cfg_flag`, `CONFIG_FILE`,
  `_confirm_flag`, `CONFIRM_CSV`, `PICK_SOURCE`, `_source_flag`), the
  `interactive_options([])` call, `CFG = load_config()`, and all 20+ config-derived
  constants (`ORGANIZED_FOLDER`, `UNSORTED_FOLDER`, `DUPLICATES_FOLDER`,
  `BETTER_QUALITY_FOLDER`, `DEFAULT_MODE`, `FUZZY_ENABLED`, `FUZZY_THRESHOLD`,
  `USE_DURATION`, `DURATION_TOLERANCE`, `EXACT_SIZE_TOLERANCE`, `MAX_THREADS`,
  `CACHE_ENABLED`, `RESUME_ENABLED`, `RESUME_FILE`, `LOG_FOLDER`, `ACOUSTID_OFFER`,
  `FPCALC_PATH`, `FP_SIMILARITY_THRESHOLD`, `NEAR_MISS_LOW_THRESHOLD`) inside
  `main()`. No module-level side effects on import.
- `load_config()` now raises `ValueError` instead of calling `sys.exit()`.
- `run_find_music_duplicates()` sets `no_review=True` by default: auto-selects
  all matches without interactive prompts (no Notepad, no `input()` calls).
  CLI `main()` keeps the full interactive review flow unchanged.

---

## build_fp_cache.py — v3.3 — 2026-05-25

### Changed (PW-06 — Config centralisation)
- Removed local `load_config()` function. Now imports `load_config` from `music_tools_common`. `get_config_path()` retained locally (handles `--config` CLI flag).

---

## build_fp_cache.py — v3.2 — 2026-05-25

### Changed (PW-01 — GUI-callable function extraction)
- Extracted `run_build_fp_cache()` as GUI-callable core. Parameters:
  `root`, `build_meta`, `build_fp`, `rebuild`, `recheck`, `copy_errors`,
  `error_dest`, `apply_errors`, `fpcalc_path`, `max_threads`, `reports_dir`,
  `progress_callback`, `log_callback`. Raises `ValueError` for bad root or
  missing fpcalc in fp-only mode. Returns dict: `new_meta`, `cached_meta`,
  `new_fp`, `cached_fp`, `warnings_count`, `report_path`, `reports_dir`.
- Moved all module-level flags (`REBUILD`, `META_ONLY`, `FP_ONLY`, `BUILD_META`,
  `BUILD_FP`, `COPY_ERRORS`, `APPLY`, `RECHECK`, `_error_dest_arg`, `_path_arg`,
  `_threads_arg`), the `interactive_options([])` call, `CFG = load_config()`, and
  all config-derived constants (`ORGANIZED`, `REPORTS_DIR`, `FPCALC_PATH`,
  `MAX_THREADS`) inside `main()`. No module-level side effects on import.
- `load_config()` now raises `ValueError` instead of calling `sys.exit()`.
- Note: mutagen/tqdm import-error blocks retain `print()` + `sys.exit(1)` —
  pre-existing pattern, outside PW-01 scope.

---

## compare_audio.py — v1.3 — 2026-05-25

### Changed (PW-01 — GUI-callable function extraction)
- Added `run_compare_audio(mode, file1=None, file2=None, folder_a=None,
  folder_b=None, progress_callback=None, log_callback=None) -> dict` as unified
  GUI-callable dispatcher. `mode`: "file" | "folder". Raises `ValueError` for
  missing params or invalid mode.
- `run_folder_scan(folder_a, folder_b, progress_callback=None, log_callback=None)`
  — params replace globals; raises `ValueError` instead of `sys.exit()`; returns dict.
- `run_file_compare(file1, file2, progress_callback=None, log_callback=None)`
  — params replace globals; raises `ValueError`; returns dict.
- Moved module-level flags (`PICK_FILES`, `PICK_FOLDERS`, `_file1_flag`,
  `_file2_flag`, `_folder1_flag`, `_folder2_flag`) inside `main()`. No
  module-level side effects on import.

---

## undo_duplicates.py — v2.5 — 2026-05-25

### Changed (PW-01 — GUI-callable function extraction)
- Extracted `run_undo_duplicates()` as GUI-callable core. Parameters:
  `csv_path`, `mode` ("undo" | "list" | "list-categories"), `dry_run`,
  `filter_category`, `filter_method`, `progress_callback`, `log_callback`.
  Raises `ValueError` for missing CSV or invalid mode. Returns dict:
  `restored`/`skipped`/`errors` (undo), `rows`/`moved` (list), `report_path` (None).
- Moved `interactive_options([])`, `DRY_RUN`, `LIST_SUMMARY`, `LIST_CATEGORIES`,
  `_filter_cat`, `_filter_method`, `FILTER_CATEGORY`, `FILTER_METHOD` inside
  `main()`. No module-level side effects on import.
- `apply_filters(rows, filter_category=None, filter_method=None)` — params replace
  `FILTER_CATEGORY`/`FILTER_METHOD` globals.
- `cmd_list`, `cmd_list_categories`, `cmd_undo` — each accepts `log_callback` and
  relevant params; `cmd_undo` also accepts `progress_callback(current, total, filename)`.
- Wrapped entry point in `def main()` called from `if __name__ == "__main__"`.

---

## check_audio_tags.py — v1.7 — 2026-05-25

### Changed (PW-01 — GUI-callable function extraction)
- Extracted `run_check_audio_tags()` as GUI-callable core. Parameters:
  `root`, `apply`, `skip_missing`, `skip_short`, `min_length_secs`, `reports_dir`,
  `progress_callback`, `log_callback`. Raises `ValueError` for bad/missing root.
  Returns dict: `issues`, `counts`, `report_path`, `reports_dir`.
- Moved `interactive_options([])`, `DRY_RUN`, `SKIP_MISSING`, `SKIP_SHORT`,
  `_path_flag`, `_min_length_flag`, `MIN_LENGTH_SECS` inside `main()`.
  No module-level side effects on import.
- `scan_folder(root, skip_short=True, min_length_secs=30, skip_missing=False,
  progress_callback=None)` — all former globals become params.
- `write_report(issues, dry_run, reports_folder=None)` — `reports_folder` param
  replaces `REPORTS_FOLDER` global reference (still falls back to module constant).
- GUI-callable core clears bad tags directly without `input()` confirmation.
  CLI `main()` retains the confirmation prompt.

---

## check_audio_tags.py v1.6 — 2026-05-24

### Changed
- Short track filtering is now **on by default** — tracks under 30 seconds are silently skipped for missing AcoustID warnings without needing to select any option.
- Removed `--skip-short` flag (no longer needed).
- Added `--include-short` flag as an opt-out if you want short tracks included in the report.
- `--min-length N` still works to adjust the threshold (default: 30s).

---


## check_audio_tags.py v1.5 — 2026-05-24

### Added
- `--skip-short` flag: suppresses missing AcoustID warnings for tracks shorter than the threshold. Useful for intros, skits, hidden tracks, and other short clips that are unlikely to be in the acoustid.org database. Only affects missing-ID reporting — malformed/bad tags are still flagged regardless of length.
- `--min-length N` flag: sets the threshold in seconds for `--skip-short` (default: 30). Example: `--min-length 20` skips tracks under 20 seconds.
- `--skip-short` added to the interactive options menu at startup.
- Duration (s) column added to CSV report — shows track length for every flagged file.
- Duration shown inline in terminal output next to each flagged file path.
- Progress bar now shows skipped-short count alongside issues when `--skip-short` is active.

---


## check_audio_tags.py v1.4 — 2026-05-23

### Added
- Files with **no acoustid_id tag at all** are now flagged as "missing" (previously only malformed/corrupt values were reported). Missing files are listed with a `[MISSING]` label and appear in the CSV with action "needs Picard tagging".
- New `--skip-missing` flag to suppress missing-tag reporting and only flag malformed values (original behaviour).
- Interactive options menu now includes `--skip-missing` as a selectable option at startup.

### Fixed
- Restored truncated `main()` ending — apply loop, summary print, and `if __name__` entry point were missing due to a patching error from a previous session.

---

## v3.1 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## v2.4 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## v3.10 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## v1.3 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## check_audio_tags.py

### v1.2 — 2026-05-23

#### Added
- In-place progress bar during scan: `[████████░░░░░░░░░░░░░░░░░░░░░░] 1234/56789 ( 2.2%)  issues: 0`. Updates every file on a single line using `\r` — no scrolling. Issues found so far shown live.

---

### v1.1 — 2026-05-23

#### Fixed
- `BASE64_RE` now accepts URL-safe base64 characters (`-` and `_`) in addition to
  standard base64 (`+` and `/`). MusicBrainz Picard stores Chromaprint fingerprints
  in URL-safe base64, so the previous regex incorrectly flagged every correctly-tagged
  file as having a bad fingerprint. 36,789 false positives in the first real-world run.

---

### v1.0 — 2026-05-22

#### Added
- New tool: scan any audio folder tree for files with invalid or corrupt AcoustID tags.
- Validates `acoustid_id` — must be a proper UUID (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`,
  lowercase hex). Literal strings like `"acoustid"` or `"acousticid"` are flagged.
- Validates `acoustid_fingerprint` — if present, must be base64-encoded and at least
  50 characters long. Real Chromaprint fingerprints are typically 100–200 characters.
- Files with no AcoustID tag at all are silently skipped — only malformed values are reported.
- `--apply` mode deletes the bad tag(s) from the file using mutagen. Audio data is not
  modified. Run MusicBrainz Picard afterward to repopulate correct tags.
- CSV report saved to `duplicate_finder/reports/` on every run (dry and apply).
- Two launchers: `Run - Check Audio Tags (Dry Run).cmd` and `Run - Check Audio Tags (Apply).cmd`.

---

## music_report_viewer.html

### v1.1 — 2026-04-05

#### Fixed
- Font size buttons (A−/A+) now correctly resize all table text.

#### Changed
- Table fills the full window height.

#### Added
- Column resize handles — drag the right edge of any column header.

---

## undo_report_viewer.html

### v1.1 — 2026-04-05

#### Fixed
- Font size buttons (A−/A+) now correctly resize all table text.

#### Changed
- Table fills the full window height.

#### Added
- Column resize handles — drag the right edge of any column header.

---

## compare_audio.py

### v1.2 — 2026-05-21

#### Fixed
- Files under 30 seconds now produce a clear warning instead of a silent
  misleading score. Short files generate too few fingerprint data points for
  a reliable result — the same threshold used by find_music_duplicates.py v3.9
  to suppress game-soundtrack jingles.
- Two-file mode: short-file note printed before the metadata table; fingerprint
  tier label shows "UNRELIABLE — short file"; verdict section leads with a
  WARNING block and reports the score as untrustworthy rather than making a
  confident SAME RECORDING / DIFFERENT call.
- Folder scan mode: short files pre-announced before fingerprinting; results
  table shows `[!]` marker on affected rows with a legend below; CSV Notes
  column populated with duration and reason; summary counts short-file rows
  separately and excludes them from same/near-miss/different totals.

---

### v1.1 — 2026-05-21

#### Added
- Folder scan mode (`--pick-folders`, `--folder1`/`--folder2`): for each file
  in Folder A, finds the best-matching file in Folder B by fingerprint score.
  Results printed as a scored table (score, verdict, filename pair) sorted
  high to low. CSV saved to `duplicate_finder/reports/compare_audio_<timestamp>.csv`.
- `Run - Compare Audio (Folder Scan).cmd` launcher.
- Summary block: counts of same/near-miss/different/no-fingerprint results.

---

### v1.0 — 2026-05-21

#### Added
- New tool: compare two audio files side by side.
- Reads metadata (title, artist, album, duration, bitrate, size, format,
  AcoustID tag) for both files and prints a formatted comparison table.
- Runs fpcalc on each file and computes a similarity score using the
  identical algorithm as `find_music_duplicates.py` — results are directly
  comparable to near-miss CSV scores and scan reports.
- Plain-English verdict: SAME RECORDING / NEAR MISS / DIFFERENT RECORDINGS,
  with quality comparison (which file has higher bitrate) and AcoustID tag
  confirmation if both files carry the tag.
- `--pick` opens two file-picker dialogs in sequence; `--file1` / `--file2`
  flags support scripted use.
- Read-only diagnostic tool — no files are moved or modified, no CSV output.
- `Run - Compare Audio.cmd` launcher.

---

## build_fp_cache.py

### v3.0 — 2026-05-21

#### Fixed
- `get_file_metadata()` now reads and stores the `acoustid_id` tag from each
  file. This populates the new `acoustid_id` column added in `music_tools_common`
  schema v3, enabling the AcoustID tag short-circuit in the duplicate finder to
  work correctly against library files loaded from cache.

---

### v2.9 — 2026-05-18

#### Changed
- Combined runs (metadata + fingerprint) now use `metadata_cache` as the file
  source for the fingerprint phase, eliminating the second rglob scan. Previously
  both phases independently walked the full library directory tree; now only the
  metadata pass does a directory scan (necessary to find new files), and the
  fingerprint pass reads the already-current DB index. Saves ~1 minute on a
  38k-file library.

---

### v2.8 — 2026-05-18

#### Added
- `--fp-only` builds now use `metadata_cache` as the file source instead of rglob.
  A DB query over an indexed table takes milliseconds regardless of library size,
  eliminating the silent wait at startup for large libraries. Falls back to rglob
  automatically if `metadata_cache` is empty.
- Live progress counter during full rglob scans: prints a dot every 1,000 files
  and shows the final count, so the terminal no longer appears stuck.
- Header now shows `File list: metadata_cache (DB index)` vs `directory scan`
  so it's clear which path is being used.

---

### v2.7 — 2026-05-18

#### Added
- `--recheck` flag — re-fingerprints files that previously failed (have an empty fingerprint in the DB) without touching the rest of the cache. Use `--fp-only --recheck` to target only failed entries. Useful after fixing a path or encoding issue without doing a full rebuild.
- fpcalc stderr is now captured and included in the warnings CSV `Reason` column when fingerprinting fails. Previously the error was silently discarded, making it impossible to tell why fpcalc failed.

#### Fixed
- Subprocess output now decoded as UTF-8 with `errors='replace'` instead of relying on `text=True`. This prevents a `UnicodeDecodeError` in fpcalc's stderr (e.g. from non-ASCII characters in a path) from silently swallowing a successful fingerprint result.
- `REPORTS_DIR` now defaults to `duplicate_finder/reports/` when `log_folder` is empty in `music_config.json`. Previously an empty string resolved to the current working directory.
- Warnings CSV is now always written when there are corrupted entries — the `if REPORTS_DIR:` guard is gone since the path is always set.

#### Changed
- `music_config.json` `log_folder` cleared to `""` so reports save to `duplicate_finder/reports/` by default (was pointing to ThinQ backup folder).
- Two `.cmd` launchers added: `Run - Build FP Cache (Incremental).cmd` and `Run - Build FP Cache (Recheck Failed).cmd`.

---

### v2.6 — 2026-05-17

#### Changed
- `get_fingerprint()` now passes `-length 60` to fpcalc, limiting audio analysis to 60 seconds per file (previously the full track, up to 120 s). 60 s is sufficient for reliable Chromaprint matching and roughly halves per-file processing time. Subprocess timeout raised from 60 → 90 s to accommodate slow storage.
- `build_fingerprint_cache()` is now parallel. Files are pre-split into cached (mtime unchanged, skipped) and to-fingerprint. New/changed files are processed by a `ThreadPoolExecutor` with `FP_WORKERS = 4` parallel fpcalc processes — tuned for i5-12450H (4 P-cores). Since fpcalc is an external subprocess, the GIL does not apply; each worker runs on its own core.
- Added constants `FP_SAMPLE_SECONDS = 60` and `FP_WORKERS = 4` near the top of the file for easy adjustment.
- Run summary now prints `FP sample` (seconds) and `FP workers` alongside fpcalc path.

### v2.5 — 2026-05-17

#### Changed
- **SQLite backend** — both caches (metadata and fingerprints) are now stored in `music_cache.db` in the project root, replacing `music_cache.json` and `music_fp_cache.json`.
- Imports `DB_PATH`, `open_db`, `init_db`, `upsert_metadata_rows`, `migrate_json_to_db` from the new shared module `music_tools_common.py`.
- `get_file_metadata(path)` now returns a flat dict matching the `metadata_cache` schema (18 fields including `year`, `album_artist`, `sample_rate`, `bit_depth`, `mb_track_id`, `mb_album_id`). The nested `metadata` sub-dict is gone.
- `build_metadata_cache(folder, conn)` — pre-loads a `{path_str: (mtime, size)}` snapshot from SQLite before spawning threads. Threads check this snapshot in memory (no DB calls inside threads). Bulk-upserts at the end. Returns `(new_count, cached_count)`.
- `get_fingerprint(path, fpcalc_path)` now returns `(fingerprint, duration)` tuple — captures the `DURATION=` line from fpcalc output (previously discarded). Callers unpack both values.
- `build_fingerprint_cache(folder, conn, fpcalc_path)` — pre-loads `{path_str: (mtime, fp)}` snapshot, loops sequentially, bulk-upserts. Returns `(new_count, cached_count, warnings)`.
- `prune_fp_cache(conn)` — deletes stale fingerprint entries via `DELETE FROM fp_cache WHERE path_str NOT IN (...)` using the live file list. Returns pruned count.
- `main()` — runs JSON→SQLite migration on first launch (if old `.json` files present), uses `DELETE FROM` for `--rebuild` instead of file deletion. Prints DB size instead of separate file sizes.

#### Removed
- `META_CACHE` and `FP_CACHE` path variables (replaced by `DB_PATH` from common module).
- Local JSON read/write logic for both caches.

### v2.3 — 2026-05-17

#### Added
- FP cache pruning: stale entries for files that no longer exist on disk are
  removed automatically before saving. Prevents the fingerprint cache from
  growing indefinitely as files are deleted or moved. Pruned count is shown
  in the run summary.

#### Changed
- Both caches now saved as compact JSON (no indentation or extra whitespace).
  Reduces file size by ~25–40% with no loss of data. Size before/after is
  shown in the run summary when the FP cache shrinks.

---

### v2.0 — 2026-04-02

#### Added
- **Fingerprint error classification** — flagged files are now split into two categories:
  - `too_small` — file duration under 30 seconds, or file size under 500 KB if duration is unreadable. These legitimately can't produce a meaningful fingerprint (interludes, short clips, etc.).
  - `corrupted` — normal-sized file where fingerprinting failed or returned a suspiciously short result. These warrant closer inspection.
- **`Category` column** added to the warnings CSV — makes it easy to sort and filter in the browser.
- **`--copy-errors` flag** — copies flagged files into `reports\fp_errors\too_small\` and `reports\fp_errors\corrupted\`, preserving relative folder structure. Without `--apply` it dry-runs and prints what would be copied. Add `--apply` to actually copy.
- **`--error-dest PATH` flag** — override the default copy destination.
- **`--apply` flag** — required to execute the file copy. Cache building is unaffected (always runs).
- New bat file: `Run - Copy FP Errors (Apply).bat` — runs `--fp-only --copy-errors --apply`.

#### Changed
- Warning output now shows `[too_small]` or `[corrupted]` label per file.
- Summary line added: count of too_small vs corrupted before the per-file list.
- Warnings CSV sorted by Category first, then Reason, Folder, Filename.

---

## find_music_duplicates.py

### v3.9 — 2026-05-21

#### Changed
- **Short library files silently skipped during fingerprint indexing** — files under
  30 seconds that produce a short/degenerate fingerprint are no longer included in the
  fingerprint warnings CSV or terminal output. They are legitimately too brief for
  Chromaprint (sound effects, jingles, game audio stings) and the warnings were noise.
  Only normal-length files (≥30 s) with a bad fingerprint result, or files where fpcalc
  fails entirely, are now flagged as genuine errors. Threshold controlled by the
  `FP_SHORT_FILE_SECONDS` constant (default 30).

---

### v3.8 — 2026-05-21

#### Fixed
- **AcoustID tag short-circuit now actually works for library files** — the
  `acoustid_id` field was never stored in the SQLite metadata cache, so
  `acoustid_id_pass()` always built an empty index for the organized library
  and silently skipped every candidate. Root cause: `music_tools_common.py`
  schema version 2 had no `acoustid_id` column. Fixed by adding the column
  (schema v3 migration), populating it in `build_fp_cache.py`, and reading it
  in `load_cache()` / `save_cache()`. After running `build_fp_cache.py` once
  to repopulate the cache, same-recording matches with different filenames
  (e.g. `Robbie Williams - Millennium.mp3` vs `03 - Millennium.mp3`) will be
  caught instantly without fingerprinting.

---

### v3.7 — 2026-05-21

#### Added
- **`--near-miss` flag** — when fingerprint matching is active, writes a separate
  `music_near_miss_<timestamp>.csv` listing every unsorted file whose best fingerprint
  score fell between 50% and the match threshold (default 85%). Each row shows the
  unsorted file, the closest library match found, the actual score, the threshold, and
  the gap. Sorted by score descending so the closest misses appear first. Use this to
  diagnose why a specific file was not matched without re-running the full scan.
- **`NEAR_MISS_LOW_THRESHOLD`** constant (default 50.0) — controls the floor for
  near-miss reporting. Files that scored below this are not included (likely genuinely
  different recordings).

---

### v3.6 — 2026-05-21

#### Fixed
- **Duration tolerance widened from 2 s to 5 s** — the old 2 s window was too narrow for
  the common case of the same recording released on different albums (e.g. an original
  single vs a boxset rip). The same audio file can measure 2–3 s different depending on
  the CD pressing and MP3 encoder silence padding. 5 s catches these cases without
  introducing false positives, since genuinely different tracks are almost never within
  5 s of each other. The value is still configurable via `duration_tolerance_seconds` in
  the JSON config.

#### Added
- **AcoustID tag short-circuit pass** — before running fpcalc fingerprinting, the script
  now checks whether the unsorted file and any library file share the same embedded
  `acoustid_id` tag (written by MusicBrainz Picard and compatible taggers). If they do,
  the files are the same recording by definition — no fingerprint comparison needed. This
  catches cases where the fingerprint score falls below the 85% threshold due to
  different rip sources or masterings, and requires zero additional computation.

---

### v3.5 — 2026-05-20

#### Changed
- `SUPPORTED_EXTENSIONS` is no longer defined locally — now imported from `music_tools_common` alongside the other shared utilities. Single source of truth for recognised audio extensions across the suite.

---

### v3.4 — 2026-05-18

#### Added
- `--pick-source` flag — opens a native folder dialog at runtime to select which folder to compare against the library. Useful when you want to check a specific batch folder rather than the default unsorted folder in config.
- `--source "C:\..."` flag — specify the comparison folder directly on the command line (scripted equivalent of `--pick-source`).
- `pick_folder()` utility function (used internally by `--pick-source`).
- `Run - Find Duplicates (Pick Source).cmd` launcher — double-click to run with folder picker.

#### Changed
- Config `unsorted` folder is now the *fallback* when neither `--pick-source` nor `--source` is given. Existing workflow unchanged.
- Folder validation label changed from "Unsorted" to "Comparison" in error messages (more accurate when using a custom source folder).
- `pick_folder` no longer defined locally — now imported from `music_tools_common` (shared version has better tkinter error handling).

#### Fixed
- Truncation bug: summary block at the end of `main()` was cut off (`log.info(f"SUMMARY  [` incomplete). Restored full summary output: exact / duplicate / better / no-match counts.
- Stripped 5 null bytes of binary padding.

---

### v3.3 — 2026-05-18

#### Fixed
- `LOG_FOLDER` fallback now resolves to `<script folder>/reports/` instead of `DUPLICATES_FOLDER`. Reports were being saved to the duplicates target folder (or failing silently) when `log_folder` was blank in config.

---

### v3.2 — 2026-05-17

#### Changed
- **SQLite backend** — metadata and fingerprint caches are now read from and written to `music_cache.db` (the shared SQLite database in the project root).
- Imports `DB_PATH`, `open_db`, `init_db`, `upsert_metadata_rows` from `music_tools_common`.
- `_cache_key(path)` simplified: returns `str(path)` directly (was an MD5 hash of the path string — unnecessary since SQLite uses `path_str` as primary key).
- `load_cache(conn)` — `SELECT * FROM metadata_cache`, builds the same in-memory dict used by the rest of the script. Bridges the flat SQLite schema to the legacy nested `metadata` sub-dict format so existing matching logic is unchanged.
- `save_cache(conn, cache)` — flattens the nested dict back to individual columns, calls `upsert_metadata_rows` for a bulk write.
- `load_fp_cache(conn)` — `SELECT path_str, fingerprint FROM fp_cache`, returns `{path_str: fingerprint}`.
- `save_fp_cache(conn, fp_cache)` — `INSERT OR REPLACE` into `fp_cache` table.
- Cache invalidation now uses `abs(mtime - stat.st_mtime) < 0.01 and size == stat.st_size` (was MD5 hash comparison).
- `get_fingerprint()` returns `(fingerprint, duration)` tuple; callers updated to unpack both values.
- `CLEAR_CACHE` CLI path: runs `DELETE FROM metadata_cache` instead of `unlink()` on a JSON file.
- `CLEAR_FP_CACHE` CLI path: runs `DELETE FROM fp_cache` + clears in-memory dict.
- Removed `import hashlib` (no longer needed).

#### Removed
- `CACHE_FILE` and `FP_CACHE_FILE` config variables.
- Local JSON read/write functions.

### v3.1 — (previous session)

See repository history.

---

## undo_duplicates.py

### v2.2 — (previous session)

See repository history.
