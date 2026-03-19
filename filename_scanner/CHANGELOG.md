# Changelog — scan_music_filenames.py

All notable changes to the Music Filename Scanner are documented here.

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
- **Bracket false positives** — `check_brackets` was flagging every file with parentheses, including standard music tags like `(Remix)`, `(feat. X)`, `(instrumental)`, and `(Radio Edit)`. Changed to only flag brackets that contain underscores, which are a reliable signal of messy formatting.
- **Trailing dot false positives** — `check_trailing_leading_junk` was flagging `Nitrous Oxide - K.O..mp3` and `Super8 & Tab - L.A..mp3` because the abbreviation ends with a dot before the extension. Updated to only flag trailing underscores, dashes, spaces, and multi-dot ellipsis patterns.

---

## [1.0] - 2026-03-06

### Added
- Initial script — scans organized music folder and flags filenames with:
  - Underscores instead of spaces
  - Dots used as word separators
  - Missing ` - ` separator
  - Inconsistent spacing around dashes
  - Brackets/parentheses in filename
  - All caps or mostly uppercase
  - Starts with lowercase
  - Double spaces
  - Leading or trailing junk characters
  - Mixed separators (underscores/dots and dashes)
- Outputs flagged files grouped by folder to console.
- `--path` flag to specify folder at runtime.
- `--summary` flag for folder-list-only output.
- `--issues` flag to show issue type breakdown.
- CSV report saved automatically on every run.
- `DEFAULT_FOLDER` constant for setting default scan path.
