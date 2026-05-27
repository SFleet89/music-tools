# Changelog

All notable changes to Library Duplicate Finder are documented here.

---

## remove_library_dupes.py — v1.2 — 2026-05-25

### Changed (PW-01 — GUI-callable function extraction)
- Extracted `run_remove_library_dupes()` as GUI-callable core. Parameters:
  `decisions_csv`, `mode` ("remove" | "list" | "undo"), `dry_run`, `config_file`,
  `reports_dir`, `progress_callback`, `log_callback`. Raises `ValueError` for
  missing CSV, invalid mode, or (undo mode) missing undo log. Returns dict:
  `report_path` plus mode-specific keys (`moved`/`skipped`/`errors`/`undo_log_path`
  for remove, `restored`/`skipped`/`errors` for undo, `rows`/`remove_rows`/
  `dec_counts`/`method_counts` for list).
- Moved all module-level flags (`DRY_RUN`, `DO_UNDO`, `DO_LIST`, `_cfg_flag`,
  `CFG`, `_folders`, `REPORTS_DIR`, `_holding_default`, `HOLDING_FOLDER`) and
  `interactive_options([])` inside `main()`. No module-level side effects on import.
- `find_undo_log(decisions_csv, reports_dir)` — `reports_dir` param replaces
  `REPORTS_DIR` global.
- `save_undo_log(..., reports_dir, holding_folder)` — both params replace globals.
- `cmd_list(decisions_csv, holding_folder, log_callback=None)` — now returns dict;
  all output routed through `log_callback` (falls back to `print`).
- `cmd_remove(decisions_csv, dry_run, holding_folder, reports_dir, progress_callback,
  log_callback)` — `dry_run`/`holding_folder`/`reports_dir` params replace globals;
  `progress_callback(current, total, filename)` added; returns dict.
- `cmd_undo(decisions_csv, dry_run, reports_dir, progress_callback, log_callback)` —
  same pattern; raises `ValueError` instead of `sys.exit(1)` when no undo log found.
- Wrapped entry point in `def main()` called from `if __name__ == "__main__"`.

---

## v1.3 — 2026-05-25

### Changed (PW-01 — GUI-callable function extraction)
- Extracted `run_find_library_dupes()` as GUI-callable core. Parameters:
  `organized_path`, `config_file`, `use_fp`, `use_filename`, `rebuild_cache`,
  `reports_dir`, `progress_callback`, `log_callback`. Raises `ValueError` for
  bad paths/config. Returns dict: `matches`, `fp_warnings`, `errors`,
  `report_path`, `log_path`, `reports_dir`.
- Moved all module-level flags (`REBUILD_CACHE`, `USE_FP`, `USE_FILENAME`,
  `_cfg_flag`, `_path_flag`, `CONFIG_FILE`) and all config-derived constants
  (`CFG`, `ORGANIZED`, `REPORTS_DIR`, `FP_ENABLED`, `FN_ENABLED`,
  `FP_THRESHOLD`, `DUR_TOL`, `FUZZY_ENABLED`, `FUZZY_THRESHOLD`, `FPCALC_PATH`,
  `FP_MIN_LEN`, `LSH_BANDS`, `LSH_BAND_SZ`, `MAX_THREADS`) inside the run
  function. `interactive_options([])` moved inside `main()`. No module-level
  side effects on import.
- `load_config()` now raises `ValueError` instead of calling `sys.exit()`.
- `is_valid_fp(fp, min_fp_length=50)` — param replaces `FP_MIN_LEN` global.
- `scan_library(root, errors, max_threads=4)` — param replaces `MAX_THREADS`.
- `build_fp_index(..., min_fp_length=50)` — passes through to `is_valid_fp`.
- `find_fp_duplicates(..., lsh_bands=20, lsh_band_size=6)` — params replace
  `LSH_BANDS`/`LSH_BAND_SZ` globals.
- `find_filename_duplicates(..., dur_tol=2.0, fuzzy_enabled=True,
  fuzzy_threshold=88.0)` — params replace `DUR_TOL`/`FUZZY_*` globals.

---

## v1.2 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## v1.1 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## find_library_dupes.py — v1.1 — 2026-05-22

### Changed
- Fingerprint cache migrated from standalone `library_fp_cache.json` to the shared `music_cache.db` SQLite database (`fp_cache` table), consistent with `find_music_duplicates.py` and `build_fp_cache.py`.
- `build_fp_index()` now accepts a `sqlite3.Connection` instead of a dict. Cache hits check mtime to invalidate stale entries.
- `--rebuild-cache` now clears the `fp_cache` table in SQLite rather than deleting a JSON file.
- `fp_cache_file` key removed from `library_dupes_config.json` and the example config (no longer needed).
- `library_fp_cache.json` removed from `.gitignore` (no longer generated).
- Imports `open_db`, `init_db`, `DB_PATH` from `music_tools_common`.

---

## library_dupes_viewer.html

### v1.1 — 2026-04-05

#### Fixed
- Font size buttons (A−/A+) now correctly resize all table text.

#### Changed
- App fills the full window height.

---

## [1.2] - 2026-03-14

### Added
- **`remove_library_dupes.py`** — companion script that reads a decisions CSV exported from `library_dupes_viewer.html` and moves files marked for removal to a configurable holding folder. Files are never permanently deleted — they sit in the holding folder until you choose to empty it.
  - `--dry-run` — preview all moves without touching anything
  - `--list` — summary of what the decisions CSV contains and what would be removed
  - `--undo` — restore files moved by the last removal run for a given decisions CSV, using an automatically saved undo log
  - `--config` — use a different config file
- **Undo log** — after every live removal run, a JSON undo log is saved to the reports folder (`library_dupes_undo_TIMESTAMP.json`) recording the original and destination path of every moved file. `--undo` reads this log to reverse the operation.
- **Holding folder config** — `folders.holding` added to `library_dupes_config.json`. Defaults to a `library_dupes_removed` folder next to the reports folder.
- **`Library_Dupes_Remove_Commands.txt`** — quick reference for all remove/undo commands.

---

## [1.1] - 2026-03-13

### Changed
- **Filename fallback replaced with metadata tag matching** — the previous method parsed artist and title from the filename stem, which was unreliable for files without an `Artist - Title` separator and caused false positives from common one-word titles (e.g. `one.mp3` from Metallica matching `one.mp3` from U2). The new method reads the embedded artist and title tags directly from the file using mutagen. Both tags must be non-empty for a match to count. Files with missing or incomplete tags fall back to fingerprint matching only.
- **Generic name blocklist applied to metadata matching** — structural track names (Intro, Outro, Main Title, End Credits, Game Over, etc.) are excluded from metadata tag matching as well as exact filename matching. These titles appear on almost every album and OST and would otherwise generate false positives even when tags are populated.
- **Match method label updated** — rows matched by metadata tags now show `metadata tags` as the match method in the CSV report, distinguishing them clearly from `exact filename` and `audio fingerprint` matches.

### Fixed
- **False positives from title-only filename matches** — the previous Artist + Title parsing produced many incorrect matches when no artist separator was present in the filename, causing different songs with the same title to be flagged as duplicates.
- **`Armin Van Buuren ↔ Eminem` false positives** — caused by `01 - Intro.mp3` matching across every artist folder. Fixed by the generic name blocklist (introduced in v1.0.1) and confirmed eliminated by the metadata tag requirement.

### Added
- **Metadata pill in report viewer** — the viewer now shows a separate green **Metadata tags** filter pill alongside Fingerprint and Filename, reflecting the three distinct matching methods.

---

## [1.0.1] - 2026-03-13

### Fixed
- **Generic filename false positives** — `01 - Intro.mp3`, `01 - Main Title.mp3`, `16 - Outro.mp3` and similar structural track names were matching across every album in the library, producing over 1,300 false positive pairs. Added a blocklist of 25 generic stems that are excluded from exact filename matching. These can still be matched by audio fingerprint.

---

## [1.0] - 2026-03-12

### Added
- Initial release.
- **Audio fingerprint matching** — uses Chromaprint (`fpcalc`) to generate fingerprints for every file and finds cross-folder duplicates by audio content. Catches renamed and retagged duplicates that filename matching cannot find.
- **LSH candidate detection** — uses Locality-Sensitive Hashing band bucketing to find fingerprint candidates in O(n) rather than O(n²), making the fingerprint pass practical on large libraries.
- **Filename fallback matching** — exact filename match after stripping track number. Fingerprint-matched pairs excluded to avoid double-reporting.
- **Cross-folder only** — pairs where both files share the same top-level artist folder are ignored.
- **Duration tolerance** — configurable, default ±2 seconds.
- **Multi-threaded metadata scanning** — configurable thread count.
- **Fingerprint cache** — compatible with `find_music_duplicates.py` and `build_fp_cache.py` if pointed at the same cache file.
- **`--rebuild-cache`**, **`--no-fp`**, **`--no-filename`**, **`--path`**, **`--config`** CLI flags.
- **Main CSV report**, **fingerprint warnings CSV**, **error log**, **run log**.
- **`library_dupes_viewer.html`** — browser-based report viewer with filter pills, search, and sort.
- **`library_dupes_config.json`** — JSON config for all settings.
