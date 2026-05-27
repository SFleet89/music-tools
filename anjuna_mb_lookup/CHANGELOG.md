# Changelog — MusicBrainz Tagger Tools

---

## v1.2 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## v1.2 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## v1.4 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## v1.3 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## anjuna_mb_lookup.py

### v1.8 — 2026-05-25

#### Changed
- **PW-01**: Added `run_anjuna_mb_lookup(batch_path, auto_mode, reports_dir, progress_callback, log_callback) -> dict` — GUI-callable entry point. Raises `ValueError` for missing path. Returns `matched`, `auto_matched`, `review`, `not_found`, `errors`, `rows`, `report_path`.
- Module-level `_args`/`_flags` variables removed; moved inside `main()`. No behaviour change when run from CLI.


### v1.7 — 2026-05-17

#### Fixed
- Removed hardcoded `initialdir` pointing to a machine-specific path (`C:\Users\neo_s\Downloads\To Move\Anjunabeats_FLAC`). Folder picker now opens at the OS default location.

### v1.6 — 2026-05-17

#### Changed
- Refactored: imports `SUPPORTED_EXTENSIONS`, `MB_API_BASE`, `USER_AGENT`, `REQUEST_DELAY`, `RESULT_LIMIT`, `FUZZY_THRESHOLD`, `mb_get`, `mb_fetch_release`, `fuzzy_score`, `read_folder_metadata`, `combined_score`, `release_label`, `get_mb_catnos`, `move_flagged_folders` from the new shared module `music_mb_common.py`. Local duplicate implementations removed.
- All Anjuna-specific code kept: `_CATNO_RE`, `DIGITAL_VARIANTS`, `REMIX_VARIANTS`, `OTHER_VARIANTS`, `extract_catno`, `normalise_catno`, `catno_base_and_suffix`, `generate_variants`, `parse_folder_artist_title`, `mb_search_catno` (local version), `mb_search_metadata`, `score_catno_match`, `score_metadata_match`, `scan_batch_folder` (returns tuples).
- No behaviour change.

### v1.5 — 2026-04-21

#### Added
- `RD`, `R2D`, `R3D` variant suffixes for remix releases. MusicBrainz commonly catalogues remix EPs as `ANJ131RD` rather than `ANJ131R` — these are now tried before falling back to other options.
- Metadata fallback search: when all catno variants return no results, the script parses artist and title from the folder name and searches MusicBrainz by those fields. Catches releases that exist in MusicBrainz but are not indexed by catalogue number.
- Matches found via the metadata fallback are tagged with `[meta fallback]` in the notes column.

### v1.4 — 2026-04-13

#### Added
- `move_flagged_folders()` function: after lookup completes, `--move` prints which folders would move; `--move --apply` executes the moves.
  - `review` folders → `To Review\` subfolder next to source.
  - `not_found` folders → `No Match\` subfolder next to source.
  - `error` folders are left in place.

---

## anjuna_tagger.py

### v1.4 — 2026-05-25

#### Changed
- **PW-01**: Added `run_anjuna_tagger(csv_path, apply, skip_art, reports_dir, progress_callback, log_callback) -> dict` — GUI-callable entry point. Raises `ValueError` for missing CSV. Returns `tagged`, `would_tag`, `partial`, `skipped`, `errors`, `results`, `report_path`.
- Module-level `interactive_options([])`, `APPLY`, `SKIP_ART`, `DRY_RUN` removed; moved inside `main()`. No behaviour change when run from CLI.


### v1.2 — 2026-05-18

#### Changed
- Added `sys.path.insert` + `from music_tools_common import SUPPORTED_EXTENSIONS, sanitise_folder_name, load_csv`. Removes three local duplicate implementations.
- Renamed local `get_music_files()` to `_get_audio_files()` to avoid shadowing the common module function. Logic unchanged (CD-subfolder-aware, different from common version).

#### Fixed
- Reports were being saved to the script's own subfolder instead of the shared `tools\reports\` folder. Fixed: path now uses `SCRIPT_DIR.parent / "reports"` for both the output path and the file picker `initialdir`.

### v1.1 — 2026-03-23

#### Changed
- **Dry run by default** — now consistent with all other tools. Run without flags to preview, add `--apply` to tag for real.
- Added y/n confirmation prompt before live run.
- Report filename now uses `_dry` / `_applied` suffix instead of just timestamp.

### v1.0 — 2026-03-22

#### Added
- Initial release.
- Reads exported anjuna_lookup CSV, fetches full release data from MusicBrainz.
- Writes title, artist, album artist, track number, disc number, year, label, catalogue number tags.
- Embeds front cover art from Cover Art Archive.
- Renames folder to: Artist - Title (Year).
- Handles multi-disc albums (CD1/CD2 subfolders).
- Collision detection on folder rename.
- `--skip-art` flag to skip cover art download.
- CSV report saved after every run.
- File picker dialog when no CSV path specified.

---

## mb_lookup.py

### v3.1 — 2026-05-25

#### Changed
- **PW-01**: Added `run_mb_lookup(batch_path, auto_mode, no_fingerprint, fpcalc_path, reports_dir, progress_callback, log_callback) -> dict` — GUI-callable entry point. Raises `ValueError` for missing path. Returns `matched`, `auto_matched`, `review`, `not_found`, `errors`, `rows`, `report_path`.
- Module-level `_positional`, `_flags`, `_fpcalc_arg`, `NO_FINGERPRINT` removed; moved inside `main()`. No behaviour change when run from CLI.


### v3.0 — 2026-05-18

#### Added
- `run_fpcalc()` now checks the shared SQLite `fp_cache` table (in `music_cache.db`) before calling fpcalc. If the file's path and mtime match a cached entry, the stored fingerprint and duration are returned immediately — fpcalc is skipped. Falls through to fpcalc silently if the cache is unavailable or the entry is stale.
- Added `sys.path.insert` and `from music_tools_common import open_db, DB_PATH` to support the cache lookup.

### v2.9 — 2026-05-17

#### Fixed
- Removed hardcoded `initialdir` pointing to a machine-specific path (`C:\Users\neo_s\Downloads\To Move`). Folder picker now opens at the OS default location.

### v2.8 — 2026-05-17

#### Changed
- Refactored: imports shared constants and functions from `music_mb_common.py` — `SUPPORTED_EXTENSIONS`, `MB_API_BASE`, `USER_AGENT`, `REQUEST_DELAY`, `RESULT_LIMIT`, `FUZZY_THRESHOLD`, `CLEAR_WINNER_GAP`, `CLEAR_WINNER_MIN`, `CATNO_PREFIX_MAP`, `mb_get`, `mb_search`, `mb_search_catno`, `mb_search_artist_title`, `mb_search_title_only`, `mb_fetch_release`, `fuzzy_score`, `normalise`, `catno_search_variants`, `parse_folder_name`, `read_folder_metadata`, `scan_batch_folder`, `score_release`, `score_metadata`, `combined_score`, `build_artist_string`, `release_label`, `get_mb_catnos`, `move_flagged_folders`. Local duplicate implementations removed.
- AcoustID-specific code (`ACOUSTID_API`, `ACOUSTID_KEY`, `ACOUSTID_DELAY`, `FPCALC_DEFAULT`, `FINGERPRINT_SAMPLE`, `MIN_SINGLE_MATCH_SCORE`, `_last_acoustid`, `run_fpcalc`, `acoustid_lookup`, `extract_release_ids_from_acoustid`, `fingerprint_folder`, `get_sample_files`) kept local.
- No behaviour change.

### v2.7 — 2026-04-13

#### Fixed
- `catno_search_variants()` now tries the full label name variant (e.g. `Magik Muzik 845-0`) before the bare number (`845-0`). Previously the bare number was tried first, which could match unrelated releases on MB and stop the search before the more specific label name variant was attempted.

### v2.6 — 2026-04-13

#### Added
- `move_flagged_folders()` function: after lookup completes, `--move` prints which folders would move; `--move --apply` executes the moves.
  - `review` folders → `To Review\` subfolder next to source.
  - `not_found` folders → `No Match\` subfolder next to source.

### v2.5 — 2026-04-13

#### Changed
- Matched results with `track_match_pct = 0` and at least one title tag present are now demoted to `review` instead of `matched`. Prevents clearly wrong single-result matches (e.g. catno collision returning an unrelated release) from being silently accepted.

### v2.4 — 2026-04-13

#### Fixed
- Folder names containing `[no cat. #]`, `[No Cat-#]`, `[no cat]` and similar "no catalogue number" placeholders no longer produce a spurious catno search. Any bracket value that normalises to `NOCAT*` (after stripping spaces, dots, hyphens, `#`) is now skipped.

### v2.3 — 2026-04-13

#### Added
- **Clear winner auto-match**: when multiple candidates are found and the top result scores ≥ `CLEAR_WINNER_MIN` (75) with a gap of ≥ `CLEAR_WINNER_GAP` (10) over second place, it is promoted to `matched` rather than `review`. Both thresholds are configurable constants near the top of the script.

### v2.2 — 2026-04-12

#### Fixed
- Catno extraction now uses square brackets only. Previously round brackets `()` were also matched, causing e.g. `(Remixes)` to be picked up as a catno instead of the actual `[BH 118-5]`.

#### Added
- `CATNO_PREFIX_MAP` table mapping known label abbreviations to full names (`MM` → Magik Muzik, `BH` → Black Hole Recordings, etc.).
- `catno_search_variants()` function: when Strategy 1 (catno search) finds no results, retries with the bare number and full label name variants before falling through to artist+title. E.g. `MM 835-6` tries: `MM 835-6`, `835-6`, `Magik Muzik 835-6`.

### v2.1 — 2026-04-05

#### Fixed
- Candidate serialization bug: empty catalogue numbers are now written as `-` instead of blank. Previously, a release with no catno produced `mbid|label||scores` which collided with the `||` candidate separator, causing affected candidates to appear broken or split in the viewer. Affected releases like Suburban Train and Adagio for Strings.

---

### v2.0 — 2026-03-29

#### Changed
- **AcoustID fingerprinting added as Strategy 0** (highest priority). Samples up to 3 files per folder, queries AcoustID, collects MB release IDs by consensus across tracks, then scores them through the existing pipeline.
- **False positive fix** — single-result matches with a combined score below 35 are now flagged as `review` (LOW-CONF) instead of `matched`. Fixes cases like Numbernin6 where a single irrelevant MB result was being accepted.
- Fixed artist string extraction for releases fetched directly by MBID (was returning blank).
- Added `acoustid_mbids` column to CSV output.

#### Added
- `--fpcalc PATH` flag — specify fpcalc.exe location (defaults to shared tools folder).
- `--no-fingerprint` flag — skip AcoustID entirely for faster runs.
- Graceful warning if fpcalc.exe not found — continues without fingerprinting instead of crashing.

### v1.0 — 2026-03-23

#### Added
- Initial release — generic version of anjuna_mb_lookup.py.
- Works with any music collection, not just Anjunabeats.
- Parses folder names to extract: catalogue number (from brackets), artist, title, year.
- Four-tier search strategy: catno → artist+title → title only → file album tag.
- Handles folder name formats:
  - `Year - Artist - Title [CatNo] Format`
  - `Artist - Title [CatNo]`
  - `Artist - Title (Year)`
  - `Artist - Title`
- Same scoring system as anjuna_mb_lookup (search score + metadata score → combined score).
- Same CSV output format — compatible with anjuna_lookup_viewer.html and mb_tagger.py.
- Auto-pick and manual review modes.
- Folder picker dialog when no path specified.

---

## tiesto_lookup.py

### v2.0 — 2026-05-25

#### Changed
- **PW-01**: Added `run_tiesto_lookup(batch_path, auto_mode, reports_dir, progress_callback, log_callback) -> dict` — GUI-callable entry point. Raises `ValueError` for missing path. Returns `matched`, `auto_matched`, `review`, `not_found`, `errors`, `rows`, `report_path`.
- Module-level `_args`, `_flags` removed; moved inside `main()`. No behaviour change when run from CLI.


### v1.9 — 2026-05-17

#### Fixed
- Removed hardcoded `initialdir` pointing to a machine-specific path (`C:\Users\neo_s\Downloads\To Move`). Folder picker now opens at the OS default location.

### v1.8 — 2026-05-17

#### Changed
- Refactored: imports shared constants and functions from `music_mb_common.py` — same set as mb_lookup.py v2.8, minus AcoustID items. Local duplicate implementations removed.
- No behaviour change.

### v1.7 — 2026-04-13

#### Fixed
- Empty catalogue number fields in candidate strings now use `-` as a placeholder instead of blank. Previously, a release with no catno produced `mbid|label||scores` which collided with the `||` candidate separator, causing the score string to appear as a phantom candidate row in the viewer. Same fix as mb_lookup v2.1.

### v1.6 — 2026-04-13

#### Fixed
- Same `catno_search_variants()` ordering fix as mb_lookup v2.7.

### v1.5 — 2026-04-13

#### Added
- `move_flagged_folders()` function: same as mb_lookup v2.6 — `--move` for dry run, `--move --apply` to execute.

### v1.4 — 2026-04-13

#### Changed
- Matched results with `track_match_pct = 0` and at least one title tag present are demoted to `review`. Same logic as mb_lookup v2.5.

### v1.3 — 2026-04-13

#### Fixed
- `[no cat. #]` and similar placeholders no longer trigger a catno search. Same fix as mb_lookup v2.4.

### v1.2 — 2026-04-13

#### Added
- Clear winner auto-match: same logic and thresholds as mb_lookup v2.3.

### v1.1 — 2026-04-12

#### Fixed
- Same bracket bug fix as mb_lookup v2.2 (catno extracted from square brackets only).
- `_YEAR_RE` regex was accidentally deleted during an edit; restored. Confirmed all four regex vars present: `_BRACKET_RE`, `_CATNO_RE`, `_YEAR_RE`, `_FORMAT_RE`.

#### Added
- Same `CATNO_PREFIX_MAP` and `catno_search_variants()` as mb_lookup v2.2.

### v1.0 — 2026-03-29

#### Added
- Renamed from mb_lookup.py v1.0 — no code changes.
- Preserved as a dedicated script for the Tiesto collection, which uses a consistent `Year - Artist - Title [CatNo] Format` folder naming convention that the original parser handles well.

---

## tagger_undo.py

### v1.3 — 2026-05-25

#### Changed
- **PW-01**: Added `run_tagger_undo(csv_path, apply, reports_dir, progress_callback, log_callback) -> dict` — GUI-callable entry point. Raises `ValueError` for missing CSV. Returns `undone`, `would_undo`, `errors`, `results`, `report_path`.
- Module-level `interactive_options([])`, `APPLY`, `DRY_RUN` removed; moved inside `main()`. No behaviour change when run from CLI.


### v1.1 — 2026-05-18

#### Changed
- Added `sys.path.insert` + `from music_tools_common import load_csv`. Removes local duplicate `load_csv()` function.

---

### v1.0 — 2026-04-12

#### Added
- Initial release.
- Reverses folder renames made by `anjuna_tagger.py` and `mb_tagger.py` using the tagger's CSV report as input.
- Reads the `folder_path` (original) and `new_folder_path` (renamed) columns; renames back if the renamed folder exists.
- Dry run by default (`--apply` to execute).
- Skips rows where the rename never happened or was already undone.
- CSV report saved after every run.
- File picker dialog when no CSV path specified.

---

## move_from_report.py

### v1.3 — 2026-05-25

#### Changed
- **PW-01**: Added `run_move_from_report(csv_path, apply, progress_callback, log_callback) -> dict` — GUI-callable entry point. Raises `ValueError` for missing or non-CSV path. Returns `moved`, `would_move`, `skipped_missing`, `errors`.
- Module-level `_args`, `_flags` and trailing `interactive_options([])` call removed; moved inside `main()`. No behaviour change when run from CLI.


### v1.1 — 2026-05-18

#### Changed
- Added `sys.path.insert` + `from music_tools_common import load_csv`. Removes local duplicate `load_csv()` function.
- Fixed hardcoded `initialdir` in file picker: was pointing to `C:\Users\neo_s\Downloads\ThinQ Back Up 2024\tools\reports`; now resolves to `<project root>/reports` dynamically.

---

### v1.0 — 2026-04-13

#### Added
- Initial release.
- Reads an existing lookup CSV report and moves folders based on their `status` column — without re-running the lookup.
  - `review` → `To Review\` subfolder next to source.
  - `not_found` / `no_catno` → `No Match\` subfolder next to source.
  - `error` rows are skipped.
- Dry run by default (`--apply` to execute).
- Confirmation prompt before any moves are made.
- Reports folders skipped because they no longer exist at their original path.
- File picker dialog when no CSV path is specified.
- Works with reports from all three lookup scripts.

---

## mb_tagger.py

### v1.5 — 2026-05-25

#### Changed
- **PW-01**: Added `run_mb_tagger(csv_path, apply, skip_art, reports_dir, progress_callback, log_callback) -> dict` — GUI-callable entry point. Raises `ValueError` for missing CSV. Returns `tagged`, `would_tag`, `partial`, `skipped`, `errors`, `results`, `report_path`.
- Module-level `interactive_options([])`, `APPLY`, `SKIP_ART`, `DRY_RUN` removed; moved inside `main()`. No behaviour change when run from CLI.


### v1.3 — 2026-05-18

#### Fixed
- `reports_dir` and `initialdir` in the CSV file picker were pointing to `SCRIPT_DIR / "reports"` (inside `anjuna_mb_lookup/`) instead of `SCRIPT_DIR.parent / "reports"` (the shared suite-root reports folder). Fixed to match all other suite scripts.
- Truncation bug: file ended with `if __name__ == "__main__` cut mid-line. Restored closing `":\n    main()`.

---

### v1.2 — 2026-05-17

#### Changed
- Refactored: imports `SUPPORTED_EXTENSIONS`, `MB_API_BASE`, `USER_AGENT`, `REQUEST_DELAY`, `mb_get` from shared module `music_mb_common.py`. Local `_last_request` variable and `mb_get` function removed.
- Local `mb_fetch_release` kept — it uses `inc="recordings artist-credits labels release-groups"` (the extra `release-groups` is required by `get_release_year()`; the shared module omits it).
- No behaviour change.

### v1.1 — 2026-04-12

#### Fixed
- Reports were being saved to the script's own subfolder instead of the shared `tools\reports\` folder. Fixed: path now uses `SCRIPT_DIR.parent / "reports"`.

### v1.0 — 2026-03-23

#### Added
- Initial release — generic version of anjuna_tagger.py.
- Works with any lookup CSV that has `folder_path` and `mbid` columns.
- Compatible with output from both anjuna_mb_lookup.py and mb_lookup.py.
- Identical tag writing and folder renaming logic to anjuna_tagger.py.
- Dry run by default, `--apply` to tag for real.
- `--skip-art` flag.
- y/n confirmation before live run.
- CSV report saved after every run.
- File picker dialog when no CSV path specified.
