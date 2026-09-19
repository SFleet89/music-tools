# Changelog — Qobuz Upgrade Finder

## v1.6 — 2026-06-19

### Fixed
- **Excel color scheme** — artist summary rows now use a light blue background (#EFF6FF)
  with dark navy text, replacing the previous dark slate. Quality badges (LOSSLESS,
  MIXED, 320) now use light green / light amber / light blue backgrounds with dark text,
  making them clearly readable without expanding any group.
- **ALAC misclassification** — M4A files at ≥ 1000 kbps (Apple Lossless in .m4a
  container) are now correctly classified as `LOSSLESS_PRESENT` and excluded from the
  upgrade targets list. Previously, Run the Jewels and similar ALAC collections appeared
  as "at 320 — no lossless" despite being lossless.

## v1.5 — 2026-06-19

### Changed
- **Collapsible artist groups** — each sheet now groups albums under an artist summary
  row. Groups start collapsed; click the [+] button on the left margin to expand.
  Summary rows use a slate-blue background to distinguish them from album rows.
- **Artist summary shows quality indicator** — the Download Quality cell on each
  artist row shows `LOSSLESS` (green), `320` (grey), or `MIXED` (amber) based on
  the albums in that group. Makes it easy to see at a glance which artists need
  attention without expanding.
- **Album & track count per artist** — summary row shows e.g. "3 albums · 45 tracks"
  in the count column.
- **Header count updated** — now shows "X artists · Y albums" instead of just album count.
- **Auto-filter on header row** — dropdown filter arrows added to all columns. Filter
  by Download Quality, Format, or any other column without leaving Excel.
- **Muted artist column in detail rows** — artist name is still written (needed for
  `--from-excel` compatibility) but styled in light grey so repeated values don't
  dominate visually.
- **`read_excel_preferences` fix** — now skips artist summary rows (blank Album)
  correctly, preventing empty-key entries in the preferences dict.

## v1.4 — 2026-06-18

### Added
- **Download Quality column** — every bitrate-band sheet in the Excel workbook now has a
  "Download Quality" column (between Album and Bitrate). Values are `LOSSLESS` or `320`,
  auto-populated from keyword detection. LOSSLESS rows are highlighted green; 320 rows are
  styled in muted grey so the important ones stand out.
- **Keyword-based auto-classification** — albums are automatically marked LOSSLESS if their
  artist or album name matches any keyword in `DEFAULT_LOSSLESS_KEYWORDS` (soundtracks, OSTs,
  classical, orchestral, trance, progressive, ambient, jazz, etc.).
- **`music_config.json` support** — place a `music_config.json` in the script folder to
  customise matching without editing the script. Supported keys:
  `lossless_keywords`, `lossless_artists`, `lossless_albums`.
- **`--from-excel` flag** — use with `--apply` to generate quality-split rip command files
  after editing the Download Quality column in the Excel. Produces:
  - `rip_lossless_<timestamp>.txt` — `rip url "..." --quality 2` (FLAC 16-bit)
  - `rip_320_<timestamp>.txt`      — `rip url "..." --quality 1` (320 kbps MP3)
- `read_excel_preferences()` — reads (artist, album) → quality pairs back from the Excel.
  Defaults any unrecognised value to `320`.
- Dry-run summary now reports how many albums were auto-classified LOSSLESS and shows a tip
  to review the Excel and re-run with `--from-excel`.
- URL list annotates each album with its quality preference when `--from-excel` is used.

### Changed
- `_categorise_for_excel()`, `write_excel()`, `write_reports()` — accept `config` dict.
- `write_qobuz_outputs()` — accepts `quality_prefs`; switches between single-file and
  split-file output accordingly.

## v1.3 — 2026-06-16

### Added
- **Downloads cross-reference** — every scan now checks upgrade candidates against three
  Spotify downloads folders (`Organized`, `Still needs fixing`, `Streamrip` inside
  `C:\Users\neo_s\Downloads\ThinQ Back Up 2024\Spotify\`).
- Matched albums are routed to a new **"Already Downloaded"** sheet in the Excel workbook
  (appears first), keeping the bitrate-band sheets clean and actionable.
- "Already Downloaded" sheet has an extra **Found In** column showing which subfolder
  contained the match, so you know where the downloaded copy lives.
- `scan_downloads_folders()` — walks artist/album/tracks folder structure; silently
  skips missing folders so the script works on any machine.
- `find_downloaded_match()` — fuzzy artist+album matching using `difflib.SequenceMatcher`
  (album threshold 0.80, artist threshold 0.70); built-in, no extra pip install.
- `_normalize_name()` — strips punctuation and collapses whitespace before comparison.
- Summary output now shows an "Already in downloads folders" line when matches exist.

## v1.2 — 2026-06-16

### Added
- **Excel export** — every dry run and apply now also produces `qobuz_upgrade_report_<timestamp>.xlsx`
  alongside the existing CSVs. Requires `openpyxl` (graceful skip with warning if not installed).
- Multi-sheet workbook matching the project's standard dark-header format:
  - **AT 320 - No Lossless** — prime Qobuz upgrade targets
  - **256–319 kbps / 192–255 kbps / 128–191 kbps / Under 128 kbps** — below-threshold albums by min bitrate band
  - **Mixed Format** — folders with multiple audio format types (MP3 + M4A etc.)
  - **Suspicious Bitrate** — folders where max bitrate exceeds 5,000 kbps (corrupt tag)
- Each sheet: dark header row (#1F2937), alternating grey rows (#F3F4F6), freeze pane A2,
  album count in H1, footer note on last row
- `SUSPICIOUS_BITRATE_THRESHOLD = 5000` constant (module level)
- `_bitrate_str()` helper — formats as `min–max` with en dash
- `_categorise_for_excel()` — pure categorisation logic, separate from rendering

## v1.1 — 2026-06-07

- **Threading**: `scan_library` now uses `ThreadPoolExecutor` (up to 8 threads) for parallel
  metadata reads — dramatically faster on large libraries (e.g. 38 k files)
- Thread-safe album dict updates protected by `threading.Lock`
- Progress counter updated every 500 files from within worker threads
- New optional `max_workers` parameter on `scan_library` (default: `min(cpu_count, 8)`)

## v1.0 — 2026-06-06

Initial release.

- Scans library for audio files using mutagen; detects bitrate for MP3, AAC, OGG, WMA, Opus
- Classifies albums as LOSSLESS_PRESENT / AT_THRESHOLD_NO_LOSSLESS / BELOW_THRESHOLD / UNKNOWN
- Dry run: writes two CSV reports (below threshold + at threshold / no lossless)
- Apply mode: logs in to Qobuz via streamrip credentials, searches for each candidate album
- Outputs: updated CSVs with Qobuz URLs, plain URL list, streamrip rip commands file
- Reads streamrip config from standard Windows/Linux paths (supports Python 3.11+ tomllib, tomli, regex fallback)
- Argparse flags: --pick, --path, --apply, --min-bitrate, --qobuz-email, --qobuz-password, --qobuz-app-id, --search-delay
- Confirmation prompt before Qobuz API calls
- Reports saved to reports/ subfolder
