# Changelog — Project Root / Shared Modules

---

## README.md

### v2.0 — 2026-05-26

#### Changed
- Full rewrite. Previous version (May 16) listed 5 tools and pointed to `duplicate_finder/` for config setup.
- Now covers all 36 scripts across 18 tool folders.
- Setup section updated: config is at project root `music_config.json`, created by `setup_music_tools.py` wizard.
- Added: `fix_featuring`, `music_integrity`, `repair_playlists`, `sort_by_artist`, `rename_music_files`, `rename_undo`, `rename_to_catno`, `flac_to_cue`, `pipeline`, `report_viewer`, `mbz2cue`, `create_test_environment`, `music_cache.db` note.
- Added shared modules section (`music_tools_common` v2.5, `music_mb_common` v1.0).
- Requirements table expanded with MusicBrainz and fingerprinting packages.

---

## gui/ — PySide6 Application

### v1.1.1 — 2026-10-20

#### Fixed
- `gui/music_integrity_panel.py` v0.3 → v0.4 — **the panel never worked.** It called
  `run_check_music_integrity(folder=..., quick=...)`, but the function takes `root=` and
  `run_integrity=`, so every scan ended in "Unexpected error". It also read result keys the
  script doesn't return (`results`/`scanned`/`issues` instead of `rows`/`counts`) and
  expected `folder`/`filename` per row instead of `file_path`. Now: correct arguments
  (Quick = `run_integrity=False`); table, counts and summary come from `rows`/`counts`;
  Folder/Filename split from `file_path`; Fix VBR (Apply) is enabled only when the dry run
  found `vbr_needs_fix` files (before, it could never be enabled).
  Verified: offscreen test (`docs/audit_2026-10-20_probes/integrity_panel_test.py`) runs the
  real worker as a Quick dry run on `testing_environment/clean_album_folders` (19 MP3s):
  10/10 checks pass; the same test fails 4 checks against the pre-fix panel. All GUI
  modules import. Not yet clicked through in the running app.

#### Changed
- `_pyinstaller_build.bat` — no longer bundles `music_config.json` (personal folder paths and
  AcoustID key) into the exe. A new user creates their own config via Settings → Save.
  Not yet verified in a built exe (Phase 6 smoke test).

### v1.1 — 2026-06-14

#### Added
- `gui/report_viewer_panel.py` v0.1 — **Phase 5: Built-in Report Viewer.**
  Native replacement for the external HTML viewers. Loads any script CSV
  report into a sortable, filterable QTableWidget. Key features:
  - **Decision column** prepended to every report: double-click any row to
    cycle Keep → Skip → Move → (clear); right-click for direct selection
    across multiple selected rows simultaneously.
  - **Live filter bar** searches all columns including the Decision column.
  - **Decision summary** label (Keep: N  |  Skip: N  |  Move: N) always visible.
  - **Export CSV** saves the current view (respects active filter) with the
    Decision column as the first column — compatible with scripts that read
    a `decision` column (e.g. `remove_library_dupes.py`).
  - **Recent files** menu tracks the last 8 opened reports (session memory).
  - **Right-click context menu**: Open in Explorer, Copy path, Copy row as text.
  - Category row colouring (exact / duplicate / better / no_match) inherited
    from `ReportViewerDialog` convention.
  - Pre-existing `Decision` column in a loaded CSV is detected and restored
    automatically, so previously exported decisions round-trip correctly.

#### Changed
- `gui/main_window.py` v1.0 → v1.1 — imported `ReportViewerPanel`; added
  `"Report Viewer"` sidebar entry between Appearance and `-- ORGANISATION --`;
  added `_PANEL_MAP` entry.

---

### v0.8 — 2026-05-29

#### Changed
- `gui/duplicate_finder_panel.py` — reworked to two-folder comparison mode (v0.1 → v0.2).
  - Added **Folder B** picker ("compare against"). Both folders are now explicit — no config dependency.
  - Removed Apply / Move Duplicates button. Panel is now scan-only (results shown, no files moved).
  - Worker updated to pass `organized_folder` explicitly to `run_find_music_duplicates`.
  - Tab column headers updated: "Unsorted File" → "File (A)", "Matched Library File" → "Matched in B".
- `gui/main_window.py` — bumped to v0.8.

---

### v0.7 — 2026-05-29

#### Added
- `gui/rename_cd_folders_panel.py` — Rename CD Folders. Folder picker, Dry Run / Apply, results table (Parent Folder / Old Name / New Name / Status). Completes Phase 3 — all sidebar panels are now wired.

#### Changed
- `gui/main_window.py` — imported `RenameCdFoldersPanel`; added `"Rename CD Folders"` to `_PANEL_MAP`. Bumped to v0.7.
- `rename_cd_folders/rename_cd_folders.py` — added `run_rename_cd_folders()` GUI-callable entry point. Bumped to v1.4.

---

### v0.6 — 2026-05-28

#### Added
- `gui/build_fp_cache_panel.py` — Build FP Cache. Folder picker, checkboxes (FP Only, Recheck, Rebuild), progress bar, summary. Added to sidebar under LIBRARY section.
- `gui/sort_albums_to_artists_panel.py` — Sort Albums to Artists. Folder picker, Dry Run / Apply, results table.
- `gui/sort_by_artist_panel.py` — Sort by Artist. Folder picker, Dry Run / Apply, results table.
- `gui/rename_album_folders_panel.py` — Rename Album Folders. Folder picker, Dry Run / Apply, results table.
- `gui/rename_music_files_panel.py` — Rename Music Files. Folder picker + template string input, Dry Run / Apply, results table.
- `gui/rename_to_catno_panel.py` — Rename to Cat No. Folder picker, Dry Run / Apply, results table.
- `gui/undo_renames_panel.py` — Undo Renames. CSV file picker, Dry Run / Undo Renames, results table.
- `gui/filename_scanner_panel.py` — Filename Scanner. Folder picker, Scan (read-only), results table.
- `gui/music_integrity_panel.py` — Music Integrity. Folder picker, Quick/Rebuild checkboxes, Scan / Fix VBR, results table.
- `gui/library_dupes_panel.py` — Library Dupes. No folder picker (reads config), FP/Filename/Rebuild checkboxes, results table.
- `gui/repair_playlists_panel.py` — Repair Playlists. Two folder pickers, Scan / Repair, results table.
- `gui/flac_to_cue_panel.py` — FLAC to CUE. File picker (not folder), Skip Existing checkbox, Dry Run / Write CUE.
- `gui/pipeline_panel.py` — Pipeline. Folder picker, step selection checkboxes, Dry Run / Run Pipeline, results table.

#### Changed
- `gui/main_window.py` — refactored `_build_stack()` to use `_PANEL_MAP` dict; added Build FP Cache to sidebar; wired 13 new panels; placeholder text now "Coming in Phase 4". Bumped to v0.6.

---

### v0.5 — 2026-05-27

#### Added
- `gui/_lookup_base.py` — Shared base panel for the three MB lookup scripts. Folder picker, Auto-match checkbox, Run Lookup button, progress bar, results table (Folder / Status / MB Artist / MB Title / Score), status colour coding.
- `gui/anjuna_mb_lookup_panel.py` — Anjuna MB Lookup (subclasses base).
- `gui/mb_lookup_panel.py` — MB Lookup (subclasses base; adds Skip Fingerprinting checkbox).
- `gui/tiesto_lookup_panel.py` — Tiesto Lookup (subclasses base).
- `gui/_tagger_base.py` — Shared base panel for both tagger scripts. CSV file picker, Skip Cover Art checkbox, Dry Run / Apply Tags buttons, progress bar, results table (Folder / Status / Files Tagged / New Folder / Notes).
- `gui/anjuna_tagger_panel.py` — Anjuna Tagger (subclasses base).
- `gui/mb_tagger_panel.py` — MB Tagger (subclasses base).
- `gui/tagger_undo_panel.py` — Tagger Undo. CSV picker, Dry Run / Undo Renames, results table (Original Folder / Tagged Folder / Status / Notes).
- `gui/move_from_report_panel.py` — Move from Report. CSV picker, Dry Run / Move Folders, summary labels (no table — script returns counts only).
- `gui/main_window.py` — wired all 7 new panels; bumped to v0.5.

---

### v0.4 — 2026-05-27

#### Added
- `gui/duplicate_finder_panel.py` — Phase 3 first panel. Source folder picker, Use Fingerprinting checkbox, Scan (Dry Run) / Move Duplicates buttons, QThread workers for both scan and apply. Results displayed in four tabs: Exact Matches (auto-move candidates), Duplicates, Better Quality, No Match. Tab labels show live counts. Apply button only enabled when there are actual matches to move. Auto-switches to the most relevant tab after scan.
- `gui/main_window.py` — wired `DuplicateFinderPanel`; sidebar horizontal scrollbar suppressed (`ScrollBarAlwaysOff`); placeholder label updated to "Coming in Phase 3". Bumped to v0.4.

---

### v0.3 — 2026-05-27

#### Added
- `gui/sort_cd_tracks_panel.py` — folder picker, Recursive checkbox, Dry Run / Apply, QThread worker, progress bar, results table (Filename / Disc / Destination / Status), summary row.
- `gui/clean_album_folders_panel.py` — folder picker, optional holding folder picker with Clear button, Dry Run / Apply, QThread worker, progress bar, results table (File / Extension / Action / Status), summary row.
- `gui/fix_featuring_panel.py` — folder picker, Dry Run / Apply, QThread worker, progress bar, results table showing original vs new Artist and Title tags, summary row.
- `gui/fix_double_spaces_panel.py` — folder picker, Dry Run / Apply, QThread worker, progress bar, results table (Folder / Original Filename / New Filename / Status), summary row.
- All four panels: colour-coded status cells (green = would move/modify/rename, grey = no change needed, yellow = skipped, red = error); Apply button only enabled after a dry run; log_message signal routes to the main log panel.
- `gui/main_window.py` — wired all four Phase 2 panels in place of their placeholders; imports added. Bumped to v0.3.

### v0.2 — 2026-05-26

#### Added
- `theme_panel.py` — Appearance panel with dark/light mode toggle and 8 accent colour swatches; settings saved to `gui_config.json` and applied live.

#### Changed
- `main_window.py` — wired `AppearancePanel`; added all 34 tools as placeholder panels ("Coming in Phase 2") with sidebar section headers.
- `theme.py` — added `ACCENT_PRESETS`, `_LIGHT_BASE` palette, `apply_theme()`, `load_gui_config()`, `save_gui_config()`; scrollbar styled with visible track and handle.
- `Run - Music Tools GUI.cmd` — switched from `python ... && pause` to `pythonw`; no console window opens on launch.

#### Removed
- Window opacity control removed from Appearance panel (affected whole window, not just title bar).

---

### v0.1 — 2026-05-26

#### Added
- Phase 1 GUI shell. New `gui/` subfolder with five modules:
  - `main.py` — `QApplication` entry point
  - `main_window.py` — `QMainWindow` with sidebar, `QStackedWidget`, log panel, status bar
  - `settings_panel.py` — fully wired settings form: reads/saves all sections of `music_config.json` via `load_config()`; folder browse dialogs via `QFileDialog`
  - `log_panel.py` — timestamped, colour-coded log widget with thread-safe `LogBridge` for use with `QThread`
  - `theme.py` — VS Code-style dark stylesheet and colour constants
- `Run - Music Tools GUI.cmd` launcher at project root.

---

## music_tools_common.py

### v2.5 — 2026-05-25

#### Added
- `load_config(config_path=None) -> dict` — shared JSON reader for `music_config.json`. Defaults to the project-root copy. Raises `ValueError` on missing file or invalid JSON. All scripts that previously had their own local `load_config()` now import this instead.

#### Fixed
- Reconstructed truncated `migrate_json_to_db()` function body — the file had been silently truncated mid-function, leaving `upsert_metadata_rows()` incomplete and `migrate_json_to_db()` missing entirely. Both functions restored.

---

### v2.4 — 2026-05-23

#### Added
- `interactive_options(available_options)` — presents a numbered menu at script startup and injects chosen flags into `sys.argv` so the rest of the script reads them normally. Skips the menu if any listed flag is already present (allows direct flag-passing to bypass the prompt). Used by all scripts for the interactive launch mode.

---

### v2.3 — 2026-05-22

#### Changed
- `config_organized_folder()` now reads `music_config.json` from the project root instead of `duplicate_finder/music_config.json`. Updated docstring and inline comment to match.

---

### v2.2 — 2026-05-22

#### Added
- `config_organized_folder()` — reads `folders.organized` from `music_config.json` and returns a `Path`. Returns `None` on any error. Used by scripts as a zero-config fallback when neither `--path` nor `--pick` is given.

---

### v2.1 — 2026-05-18

#### Added
- Schema versioning: `schema_version` table, `SCHEMA_VERSION = 2` constant, migration framework in `init_db`.
- `integrity_cache` table added to schema (used by `check_music_integrity.py`).

---

### v2.0 — 2026-05-17

#### Added
- **SQLite cache layer** — shared `music_cache.db` (WAL mode) replaces per-script JSON files.
  - `DB_PATH` — resolved `Path` pointing to `music_cache.db` next to this file (project root).
  - `open_db(db_path=None)` — opens (or creates) the database with `row_factory = sqlite3.Row`, WAL journal mode, and `synchronous=NORMAL` for safe concurrent reads/writes.
  - `init_db(conn)` — idempotent `CREATE TABLE IF NOT EXISTS` for both `metadata_cache` (18 columns) and `fp_cache` (4 columns), plus indexes on `artist` and `mb_track_id`. Safe to call on every run.
  - `upsert_metadata_rows(conn, rows)` — bulk `INSERT OR REPLACE` into `metadata_cache` using named placeholders; accepts a list of dicts.
  - `migrate_json_to_db(conn, script_dir)` — one-time migration: reads `music_cache.json` and `music_fp_cache.json`, imports all entries into SQLite, renames the originals to `.json.bak`. Returns `(meta_count, fp_count)`.
- **Expanded metadata schema** — `metadata_cache` now stores: `path_str`, `mtime`, `size`, `filename`, `file_format`, `title`, `artist`, `album_artist`, `album`, `year`, `track_number`, `disc_number`, `bitrate`, `sample_rate`, `bit_depth`, `duration`, `mb_track_id`, `mb_album_id`.
- `_META_COLS` tuple — canonical column order for bulk inserts; single source of truth for the schema.

#### Changed
- Added `import sqlite3` to the module imports.
- Module docstring updated to document all new public symbols.

### v1.0 — 2026-05-17 (initial extraction)

#### Added
- Initial extraction from project scripts into a shared module.
- `SUPPORTED_EXTENSIONS` — set of recognised audio file extensions (`.mp3`, `.flac`, `.aac`, `.m4a`).
- `pick_folder(title)` — native Windows folder-picker dialog via tkinter.
- `write_csv(rows, path, fieldnames)` — UTF-8-BOM CSV writer.
- `load_csv(path)` — UTF-8-BOM CSV reader returning list of dicts.
- `get_music_files(folder)` — sorted list of music files directly in a folder (non-recursive).
- `sanitise_folder_name(s)` — strips characters illegal in Windows folder names.
- `read_file_tags(path)` — reads `album`, `title`, `tracknumber` via Mutagen.
