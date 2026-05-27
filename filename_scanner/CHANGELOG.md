# Changelog — filename_scanner

All notable changes to the filename scanner scripts are documented here.

---

## scan_music_filenames.py v2.5 / scan_progress.py v1.1 — 2026-05-24

### Changed (pre-work PW-01: GUI-callable function extraction)
- **`scan_music_filenames.py`** — extracted `run_scan_music_filenames(folder, summary_only, show_issues, skip_list_file, progress_callback, log_callback) -> dict` as the callable core function. GUI can call this directly; CLI calls `main()` as before.
- **`scan_music_filenames.py`** — moved module-level flag parsing (`SUMMARY_ONLY`, `SHOW_ISSUES`, `PICK_DIR`, `_path_flag`) inside `main()`. Scripts no longer parse argv on import.
- **`scan_music_filenames.py`** — `print_report()` now takes `summary_only` and `show_issues` as explicit parameters instead of reading module-level variables.
- **`scan_music_filenames.py`** — added `interactive_options([])` call at top of `main()`.
- **`scan_music_filenames.py`** — `run_scan_music_filenames()` raises `ValueError` for bad folder instead of calling `sys.exit(1)`.
- **`scan_progress.py`** — extracted `run_scan_progress(reports_folder, first_vs_last, log_callback) -> dict` as the callable core function.
- **`scan_progress.py`** — moved module-level flag parsing (`FIRST_VS_LAST`, `_path_flag`, `_cfg_flag`) inside `main()`.
- **`scan_progress.py`** — removed `get_reports_folder()` helper; folder is now resolved in `main()` and passed directly to `run_scan_progress()`.
- **`scan_progress.py`** — added `interactive_options([])` call at top of `main()`.
- **`scan_progress.py`** — `run_scan_progress()` raises `ValueError` for bad folder instead of calling `sys.exit(1)`.

---

## v2.1 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## scan_compare_viewer.html

### v1.1 — 2026-04-05

#### Fixed
- Font size buttons (A−/A+) now correctly resize all table text.

#### Changed
- Table fills the full window height.

#### Added
- Column resize handles — drag the right edge of any column header.

---

## scan_report_viewer.html

### v1.1 — 2026-04-05

#### Fixed
- Font size buttons (A−/A+) now correctly resize all table text.

#### Changed
- Table fills the full window height.

#### Added
- Column resize handles — drag the right edge of any column header.

---

## scan_progress_viewer.html

### v1.1 — 2026-04-05

#### Fixed
- Font size buttons (A−/A+) now correctly resize all table text.

---

## scan_music_filenames.py v2.4 / fix_double_spaces.py v2.0 — 2026-05-22

### Fixed
- **`scan_music_filenames.py`** — removed hardcoded `DEFAULT_FOLDER` (`C:\Users\neo_s\Downloads\...`). Script now resolves the target folder via: `--path` flag → `--pick` folder dialog → `config_organized_folder()` from `music_tools_common` → error with usage hint.
- **`scan_music_filenames.py`** — `SKIP_LIST_FILE` was a hardcoded absolute path; changed to `SCRIPT_DIR / "scan_skip_list.txt"` (relative to script). Gracefully returns `[]` if file is absent.
- **`scan_music_filenames.py`** — `load_skip_list` type annotation changed from `path: str` to bare `path` to accept `Path` objects.
- **`fix_double_spaces.py`** — removed hardcoded `DEFAULT_FOLDER`; added `--pick` flag and `config_organized_folder()` fallback (same three-step resolution as above).
- **`fix_double_spaces.py`** — `Path.rename()` replaced with `shutil.move(str(...), str(...))` to work correctly across drives. Added `import shutil`.

### Added
- **`scan_music_filenames.py`** — `PICK_DIR = "--pick" in sys.argv` flag; opens folder dialog when passed.
- **`fix_double_spaces.py`** — `PICK_DIR = "--pick" in sys.argv` flag; opens folder dialog when passed.

---

## [2.3] — 2026-05-18

### Fixed
- **`scan_music_filenames.py`** — `REPORTS_FOLDER` was a hardcoded absolute path. Changed to `SCRIPT_DIR / "reports"` so reports always save next to the script regardless of where the tools are installed.
- **`fix_double_spaces.py`** — same hardcoded `REPORTS_FOLDER` fix; added `SCRIPT_DIR = Path(__file__).parent`.
- **`scan_progress.py`** — removed fragile approach of reading `REPORTS_FOLDER` out of `scan_music_filenames.py` source via regex (broken now that REPORTS_FOLDER is a Path expression, not a string literal). `get_reports_folder()` now falls back directly to `SCRIPT_DIR / "reports"`. Also stripped 502 null bytes of binary padding from the end of the file.

---

## [2.2] - 2026-03-14

### Added
- **`scan_progress.py`** — reads all `scan_summary_*.csv` files in the reports folder sorted by timestamp and produces a progress report: total flagged per scan, files fixed between each run, new issues introduced, net change, and a full issue type breakdown comparing first scan to latest. Writes `scan_progress_TIMESTAMP.csv`. Supports `--first-vs-last`, `--path`, and `--config` flags.
- **`scan_progress_viewer.html`** — visual viewer for progress reports. Shows a trend chart of flagged files over time (drawn with vanilla canvas, no dependencies), an issue breakdown table with progress bars showing the % fixed per issue type between first and latest scan, and a full scan history table with fixed/new/net columns.

---

## [2.1] - 2026-03-14

### Added
- **Skip list queue persistence** — the Skip List Queue in `scan_report_viewer.html` now saves to browser localStorage automatically. Closing and reopening the viewer restores the previous queue, with a banner confirming the restore. The queue is cleared if you manually click Clear queue.
- **`scan_compare_viewer.html`** — new standalone comparison tool. Drop an older scan CSV on the left and a newer one on the right to see what's been fixed, what's newly flagged, and what's still outstanding. Results are categorised as Fixed (green), New issues (red), and Still flagged (amber), each with its own filter tab. Still-flagged files show a before/after issue breakdown side by side.

---

## [2.0] - 2026-03-07

### Added
- **Per-issue CSV reports** — every run now produces a separate CSV for each issue type, named and numbered in fix-first order (e.g. `scan_01_underscores_TIMESTAMP.csv`, `scan_02_brackets_underscores_TIMESTAMP.csv`). Tackle one issue at a time in your rename utility instead of working through one overwhelming list.
- **Summary report** — `scan_summary_TIMESTAMP.csv` contains every flagged file with all its issues in one place for a full overview.
- **Skip list** (`scan_skip_list.txt`) — plain text file, one artist name pattern per line. Files matching any pattern are excluded from all issue reports and logged separately. Useful for artists with intentionally unconventional formatting (lowercase names, all-caps OST titles, stylised punctuation).
- **Skipped files report** — `scan_skipped_TIMESTAMP.csv` lists every file matched by the skip list, showing which pattern triggered the skip. Only generated when at least one file is skipped.
- **Issue priority ordering** — issues are ordered in all output from easiest/most mechanical fixes first (underscores, bracket underscores, double spaces, junk characters, dots) through to those requiring more judgement (dash spacing, all caps, lowercase, mixed separators).
- **`REPORTS_FOLDER` and `SKIP_LIST_FILE` constants** — paths to the reports output folder and skip list file are now defined at the top of the script for easy configuration.

### Changed
- Reports now save to a dedicated `reports\` subfolder rather than the parent of the scanned music folder.
- Console issue breakdown (shown with `--issues`) now follows fix-first priority order rather than alphabetical.
- Version bump to v2.0.

---

## [1.2] - 2026-03-06

### Fixed
- **Missing separator false positives** — `check_no_dash_separator` was incorrectly flagging artists whose names start with a number (`2Pac`, `50 Cent`, `3 One Oh`) because the pattern `^[^-\d]` excluded them. Replaced with a simpler check: if ` - ` appears anywhere in the stem, the file passes.
- **Mixed-case dot artist names** — `Will.i.am`, `LM.C`, `B.o.B`, `Who.Is` were being flagged as "dots used as separators". Updated dot detection to only flag files where dots are clearly the primary separator throughout (3+ segments, no spaces, no ` - `), leaving artist name dots untouched.
- **Acronym dots in `01. Title` format** — song titles that are acronyms (`M.M.I.X`, `U.F.O`, `B.Y.O.B`) were being flagged because the `01. Title` format has no ` - ` separator to exempt them. Fixed by additionally exempting all-uppercase dot-separated patterns in title position.

### Removed
- **`check_no_dash_separator`** — removed entirely. The separator check was generating over 7,700 false positives (DJ mixes, game soundtracks, single-title tracks) for minimal real benefit. Files without a ` - ` separator are not inherently messy.

---

## [1.1] - 2026-03-06

### Fixed
- **`01. Title` format false positives** — `check_no_dash_separator` was flagging `01. Dunya Salam.mp3` and similar track+dot+title filenames as missing a separator. Added explicit pattern matching for `01. Title` and `01 - Title` as acceptable formats.
- **Bracket false positives** — `check_brackets` was flagging every file with parentheses, includi