# Changelog — report_viewer/viewer.html

---

## v2.4 — 2026-05-23

### Added
- `check_audio_tags` report config: tabs (Bad ID / Bad Fingerprint / Both / Read Errors / All); status badges for each issue type; path and fingerprint columns set to wrap. Detects by filename prefix `check_audio_tags_` or by column headers.

---

## v2.3 — 2026-05-23

### Fixed
- `renderLdView` → `ldRenderView`: library dupes CSV would crash on load due to function name mismatch.

### Added
- **"📋 Copy undo command" button** in the duplicates report toolbar. Copies `python undo_duplicates.py "reports\<filename>.csv"` to clipboard with a toast reminder to run from the `duplicate_finder` folder. Falls back to `execCommand` for non-secure contexts.
- `state.fileName` — stores the loaded CSV filename for use by the undo command generator.

---

## v2.2 — 2026-05-22

### Added
- **Library Dupes decisions UI** (`customRender: 'library_dupes'`). Two views:
  - *Pairs view* — card per matched pair; Keep File A / Keep File B / Keep both / Skip buttons.
  - *Groups view* — union-find clustering groups all copies of a song; mark individual files to keep, or skip the group.
  - Method filter pills (FP / Metadata / Fuzzy / Filename), sort selector, Clear filters button.
  - Fixed-bottom decisions panel (Decided / Pending counts, Download decisions CSV, Clear all).
  - Download generates a decisions CSV with Decision / Keep Path / Remove Path columns.
- **`rename_music_files` report config** — tabs (To Review / Good / Skipped / Issues / All); columns: status, original_name, new_name, title, artist, album, track, year, format, kbps, missing_tags, original_path.

---

## v2.1 — 2026-05-22

### Added
- **Scan Progress dashboard** (`customRender: 'scan_progress'`). Summary stat cards (scans analysed, first/latest total, total fixed, total new issues); trend chart (Chart.js via CDN — only external dependency); issue breakdown table (first vs latest, with progress bars); full scan history table.

---

## v2.0 — 2026-05-22

### Added
- **Duplicates Report decisions UI** (`customRender: 'duplicates'`). Card-per-row layout replacing generic table. Category pills, FP confidence tier pills, method + action dropdowns. Per-row Keep Library / Keep Unsorted / Skip buttons. Fixed-bottom decisions panel with Download decisions CSV.
- **`scan_progress` report config** added to `REPORT_CONFIGS`.
- **`library_dupes` report config** added to `REPORT_CONFIGS`.

---

## v1.3 — 2026-05-18

### Added
- Viewer configs for: `rename_album_folders`, `rename_cd_folders`, `rename_undo`, `library_dupes` (standard table fallback before custom render was added).

---

## v1.2 — 2026-05-17

### Added
- Resizable columns (drag handle on each `th`).
- Font size A−/A+ (10–20 px range).
- Light/dark mode toggle; preferences saved to `localStorage`.

---

## v1.1 — 2026-05-17

### Fixed
- `anjuna_lookup` filePattern corrected (`/^anjuna_mb_lookup_/` → `/^anjuna_lookup_/`).

### Added
- Viewer configs for: `sort_albums_to_artists`, `sort_cd_tracks`, `flac_to_cue`.

---

## v1.0 — 2026-05-17

### Added
- Universal report viewer: auto-detects report type from CSV filename prefix and column headers; applies layout, status colours, and filters per type. Replaces all individual per-script HTML viewers.
- Dark mode fix: font-size display and "All statuses" dropdown colour corrected in dark mode.
