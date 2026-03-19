# Changelog

All notable changes to Music Duplicate Finder are documented here.

---

## [3.5] - 2026-03-14

### Added
- **`--no-review` flag** — runs the full scan and generates the dry-run CSV but skips all Notepad prompts entirely. All actionable matches are marked as selected in the output. Use this when you want to review in the browser viewer instead of Notepad.
  ```
  python find_music_duplicates.py --dry-run --no-review
  ```
- **Cache age warnings** — if the metadata cache (`music_cache.json`) or fingerprint cache (`music_fp_cache.json`) is more than 7 days old, a warning is printed at startup with the exact flag to refresh it. This catches cases where new music has been added to the library but the cache hasn't been updated.
- **Rebuilt report viewer (`music_report_viewer.html`)** — complete redesign with the following additions:
  - **Decision buttons** on every DUPLICATE and BETTER QUALITY row: Keep unsorted, Keep library, Skip. Decided rows are highlighted green.
  - **FP confidence tier pills** — when the report includes fingerprint matches, filter pills appear for High (≥95%), Medium (90–94%), and Low (85–89%) tiers, matching the confidence tiers used during the scan.
  - **Expanded file detail** — each row shows bitrate, size, duration, artist, and title inline alongside the filename, with the full path in small text below. No separate column lookups needed.
  - **Decision panel** — fixed bar at the bottom showing decided vs pending count and a **Download decisions CSV** button.
  - **`--confirm`-compatible download** — the downloaded `_reviewed.csv` has its Action column set to exactly what `--confirm` expects (`Would move to DUPLICATE` / `Would move to BETTER QUALITY`) for rows where you chose Keep library. Rows you skipped or chose Keep unsorted go into a separate `_skipped.csv`. Pass the `_reviewed.csv` directly to `--confirm`.

### Changed
- **Recommended workflow updated** — the new recommended flow uses `--no-review` for the dry run and the browser viewer for review, replacing Notepad for day-to-day use. Notepad review remains fully available for those who prefer it (omit `--no-review`).

---

## [3.4] - 2026-03-09

### Added
- **Fingerprint warnings CSV report** — when fingerprinting is run, any library files that produced invalid or failed fingerprints are now saved to a dedicated CSV alongside the main report: `music_fp_warnings_TIMESTAMP.csv`. Columns: Folder, Filename, Full Path, Reason, Fingerprint Length. Rows are sorted by reason so all generation failures group together and all short fingerprint files group together. The report is only created if there are warnings to report.
- **Fingerprint warnings written to log file** — previously, the "WARNING: N library file(s) skipped due to invalid fingerprints" message was printed to the console only and lost after the session. It is now also written to the log file with full file paths, so every run's warnings are permanently recorded.
- **High-frequency match warnings written to log file** — same fix applied to the high-frequency match warning (a library file matching 5+ unsorted files). Previously console-only, now also captured in the log with full paths.
- **Fingerprint warning count in summary** — the run summary at the bottom of the log now includes a line noting how many files had invalid fingerprints and the name of the warnings CSV, e.g. `FP warnings  : 140 file(s) — see music_fp_warnings_20260309_...csv`.

### Fixed
- **`acoustid` config section missing from `music_config.json`** — the config file was missing the `acoustid` block entirely, causing fingerprint matching to never be offered regardless of whether fpcalc was installed. The section has been added with `enabled: true`, `fpcalc_path`, `similarity_threshold`, and `fp_cache_file`.

---

## [3.3] - 2026-03-06

### Added
- **`--confirm` flag** — takes a dry-run CSV as input and executes those exact selections as a live run, skipping all Notepad review prompts. Recommended workflow: do your dry run, review carefully, then run with `--confirm` to commit without re-reviewing.
  ```
  python find_music_duplicates.py --confirm "music_report_20260304_200225_dry_mode4_fp.csv"
  ```
- **Descriptive report filenames** — log and CSV filenames now include run type, match mode, and whether fingerprinting was used, e.g. `music_report_20260304_200225_dry_mode4_fp.csv`. Makes it easy to identify reports at a glance and avoids accidentally passing a live run report to `--confirm`.
- **Missing file verification in confirm mode** — before executing each selection from the dry-run CSV, the script verifies the unsorted file still exists. Files that have moved or been deleted since the dry run are skipped with a warning rather than causing an error.
- **Safety check on confirm CSV** — if the filename contains `_live_`, the script refuses to use it and exits with an error explaining that `--confirm` only accepts dry-run reports.

---

## [3.2] - 2026-03-04

### Added
- **Fingerprint confidence tiers** — fingerprint matches are now reviewed in three separate Notepad lists grouped by match score: High (95–100%), Medium (90–94%), and Low (85–89%). Allows batch-approving confident matches while focusing scrutiny on lower-confidence ones.
- **`--clear-fp-cache` CLI flag** — clears the fingerprint cache (`music_fp_cache.json`) without needing to delete the file manually. Can be combined with other flags, e.g. `--clear-fp-cache --dry-run`.
- **Degenerate fingerprint detection** — fingerprints with fewer than 50 integers are now rejected before being added to the library index. A warning is printed at startup for any skipped files (e.g. `! 01 - I'm a Slave 4 U.mp3 — short fingerprint (3 integers) — file may be corrupted or silent`).
- **High-frequency match warning** — if any single organized library file matches 5 or more unsorted files during the fingerprint pass, it is flagged in the output as a likely bad fingerprint source.
- **Fingerprint resume tracking** — `fp_processed` is now saved in `music_resume.json` alongside `processed`, so an interrupted fingerprint pass can resume without re-fingerprinting files already completed.

### Fixed
- Syntax error (unterminated f-string) in the high-frequency match warning print statement.

---

## [3.1] - 2026-03-01

### Added
- **AcoustID audio fingerprint matching** (optional) — a second pass on No Match files using Chromaprint (`fpcalc`). Compares actual audio content to catch renamed or retagged duplicates that filename/metadata matching cannot find. No API key required — all comparisons are local.
- **Fingerprint caching** — fingerprints stored in `music_fp_cache.json`. First run is slow; subsequent runs are fast.
- **`acoustid` config section** — `enabled` (default false), `fpcalc_path`, `similarity_threshold` (default 85%), `fp_cache_file`.
- **"Why not exact" explanations** — Standard Duplicates now show a human-readable reason why they didn't qualify for auto-move (e.g. `size diff: 2.5% (tolerance: 3.0%)`). Shown in Notepad review list, log output, and CSV report.
- **`Why Not Exact` and `Match Method` CSV columns** — every row in the report now records how the match was found and why it wasn't auto-moved.

### Changed
- **Exact match size tolerance increased from 0.5% to 3.0%** — files at the same bitrate frequently differ slightly in size due to embedded artwork and tag overhead. The previous 0.5% threshold was causing valid exact matches to fall through to Standard Duplicates requiring manual review.
- **Quality detection changed to bitrate-only** — `unsorted_is_better()` previously used file size as a proxy for quality. Changed to compare bitrate only, since size differences at the same bitrate are tag/artwork noise rather than audio quality differences.

### Fixed
- **Mode 4 cross-file false positives** — `find_match()` now verifies that a filename match and a metadata match refer to the same organized file. Previously, a filename match against one file and a metadata match against a different file would both satisfy Mode 4 ("both must match"), causing incorrect duplicate detection.

---

## [3.0] - 2026-02-27

### Added
- **Multi-threaded scanning** — organized folder scanned in parallel using configurable thread count (`max_threads` in config, default auto-detect).
- **Metadata cache** — organized folder scan results saved to `music_cache.json`. Subsequent runs skip unchanged files for significantly faster startup.
- **Fuzzy metadata matching** — uses `rapidfuzz` to catch tag inconsistencies (e.g. `"The All-American Rejects"` vs `"All-American Rejects"`). Configurable threshold (default 88%).
- **Duration matching** — track length included in match criteria to reduce false positives from songs sharing a title. Configurable tolerance (default ±2s).
- **Four match modes** — Filename only, Metadata only, Either, or Both (recommended). Mode 4 requires both filename and metadata to match on the same file.
- **Resume capability** — interrupted runs save state to `music_resume.json` and offer to continue from where they left off.
- **Progress bars** — real-time progress display during scanning, matching, and fingerprinting using `tqdm`.
- **JSON config file** — all settings in `music_config.json` (folder paths, matching options, performance, resume, output).
- **CSV report** — full log of every file processed, every decision made, and every action taken. One file per run, timestamped.
- **Dry run mode** — `--dry-run` flag previews all actions without moving any files.
- **`--clear-cache`** — forces a full re-scan of the organized folder.
- **`--clear-resume`** — discards any saved interrupted run state.
- **`--config`** — specify an alternative config file.
- **`undo_duplicates.py`** — companion script that reads any previous CSV report and restores files to their original locations. Supports `--dry-run` and `--filter-category`.

### Changed
- Complete rewrite from v1/v2 single-pass script.

---

## [2.0] - 2026-02-27

### Added
- `undo_duplicates.py` — basic restore script to reverse a previous run using the log file.
- Improved log output with per-file detail.

---

## [1.0] - 2026-02-27

### Added
- Initial script — single-threaded scan of unsorted folder against organized library.
- Filename-based matching.
- Manual file moving with Notepad review list.
- Basic log output.
