# Changelog — MusicBrainz Tagger Tools

---

## v2.6 — 2026-05-25

### Changed (PW-01 — GUI-callable function extraction)
- Extracted `run_flac_to_cue()` as the GUI-callable core function. Parameters:
  `target`, `apply`, `recursive`, `skip_existing_cue`, `forced_mbid`,
  `reports_dir`, `confirm_callback`, `progress_callback`, `log_callback`.
  Returns dict: `rows`, `counts`, `csv_path`, `log_path`, `report_path`, `reports_dir`.
  Raises `ValueError` for bad paths instead of `sys.exit(1)`.
- Moved `DRY_RUN`, `PICK_DIR`, `SCAN_MODE`, `_path_flag`, `_url_flag`, and
  `interactive_options([])` inside `main()` — no module-level side effects on import.
- `setup_output_paths(dry_run, reports_dir=None)` — removes global `DRY_RUN`
  dependency; `reports_dir` can be overridden by the GUI.
- `setup_logger(log_path, log_callback=None)` — adds a custom `logging.Handler`
  that routes all INFO+ messages to the GUI callback. Clears stale handlers on
  repeated calls (safe when run multiple times in the same process).
- `process_audio()` — new params `dry_run=True` and `confirm_callback=None`.
  `confirm_callback(cue_path) -> bool` replaces the inline `input()` call;
  CLI `main()` passes its own lambda with y/n validation. When `confirm_callback`
  is `None`, writes are auto-confirmed (GUI pre-confirms before calling).

---

## v2.5 — 2026-05-23

### Added
- Added `interactive_options()` call: script now presents a numbered menu at startup so --apply (and any other flags) can be chosen interactively without needing separate launcher files.
- .cmd launchers updated: --pick and --recursive removed; Dry Run launcher passes no flags, Apply launcher passes only --apply.

## flac_to_cue.py

### v2.4 — 2026-05-20

#### Changed
- `pick_folder()` is no longer defined locally — now imported from `music_tools_common`. The local duplicate has been removed. `pick_folder_or_file()` (unique to this script — handles audio file + folder picking) remains local.

---

### v2.3 — 2026-05-18

#### Fixed
- `reports_dir` was pointing to `SCRIPT_DIR.parent / "reports"` instead of `SCRIPT_DIR / "reports"`. Standalone script — fixed to save next to the script.
- Stripped 7 null bytes of binary padding from end of file.

---

### v2.2 — 2026-05-17

#### Added
- `--url` flag: accepts a MusicBrainz release URL (e.g.
  `https://musicbrainz.org/release/<uuid>`) and extracts the MBID directly.
  When `--url` is provided the tag-reading and five-stage search fallback
  chain are skipped entirely — the MBID is used straight away. Useful for
  completely untagged WAV files where the MB release page is already known.
  Supersedes the separate `mbz2cue.py` script; this implementation uses
  the proper MusicBrainz JSON API instead of HTML scraping, and inherits
  all existing features (dry-run, per-file confirmation, reports, multi-disc
  support). Combine with `--path` or `--pick` to specify the audio file.

---

### v2.1 — 2026-05-16

#### Fixed
- Disc number detection for files whose name begins with a high track number
  prefix (e.g. `18 - [Universal Religion Chapter 6].mp3` inside a `CD2` folder).
  Previously step 3 (sequential file prefix) returned 18 as the disc number before
  step 4 (parent folder keyword check) could fire. Since 18 > 2 (number of discs),
  the script then fell back to disc 1 — the wrong disc.
- Fix: parent folder check is now step 3, sequential prefix is now step 4 and is
  additionally capped at ≤ 10 so that any track number above 10 can never be
  mistaken for a disc number.
- New priority order: scene prefix → keyword in filename → **parent folder keyword**
  → sequential prefix (1 < n ≤ 10) → DISCNUMBER tag.

---

### v2.0 — 2026-05-16

#### Added
- Multi-format support: WAV, AIFF, MP3, M4A (AAC and Apple Lossless), and
  Ogg Vorbis are now supported in addition to FLAC. `mutagen.File()` auto-detects
  the format and routes tag reading through the correct handler:
  VorbisComment for FLAC/OGG, ID3 frames for MP3/AIFF/WAV, MP4 atoms for M4A.
- `audio_format` column added to CSV report (shows the file extension processed).
- Dry-run mode is now the default. Running without `--apply` scans and resolves
  MB matches but does not write any `.cue` files. Report status shows `dry_run`
  for files that would have been written.
- Two standard launcher `.cmd` files replace the old menu-driven shortcut:
  - `Run - FLAC to CUE (Dry Run).cmd` — opens picker, runs in dry-run mode
  - `Run - FLAC to CUE (Apply).cmd`  — opens picker, writes confirmed CUE files
- File picker now includes all supported audio formats.

#### Changed
- Internal variables renamed from `flac_path`/`flac_filename` to
  `audio_path`/`audio_filename` throughout the script and CSV report.
- Version banner updated to v2.0.
- `Run - FLAC to CUE.cmd` (old menu-style shortcut) replaced with a notice
  pointing to the two new launchers.

---

### v1.5 — 2026-04-25

#### Fixed
- Disc number detection now checks the filename **before** the `DISCNUMBER` tag. Scene rips commonly have `DISCNUMBER=1` written on every disc, causing all CD2 files to be matched as disc 1. Filename is now the primary source of truth, with the tag used as a last resort only.
- Priority order for disc detection: scene prefix (`201-` = disc 2) → explicit keyword in filename (`CD2`, `Disc 2`) → sequential file prefix (`02.` = disc 2, only if value > 1) → parent folder keyword → `DISCNUMBER` tag.

### v1.4 — 2026-04-25

#### Fixed
- CUE index format for releases over 99 minutes. Previously `63:54:00` was written for a track starting at 63 minutes — CUE Splitter interprets this as HH:MM:SS and fails with "Can't skip to initial audio data". Now correctly written as `01:03:54:00` (HH:MM:SS:FF) for any release over 99 minutes.

#### Added
- Total duration check after disc matching: warns if MB data shows a combined track length over 200 minutes, which usually indicates the wrong release was matched (e.g. a multi-disc release being treated as a single disc).
- Total duration shown in the console and log during processing so mismatches are visible before you confirm.

### v1.3 — 2026-04-25

#### Fixed
- Tag reading now extracts catno from the ALBUM tag if no dedicated `CATALOGNUMBER` tag exists (e.g. `ANJCD008 VA - Anjunabeats Volume 5...` → catno `ANJCD008`). This was the primary cause of all 10 `no_match` results in the first run.
- Album tag cleaned before searching — strips leading catno prefix, `VA -` prefix, and scene formatting so MB receives `Anjunabeats Volume 5 (Mixed By Above And Beyond)` instead of the raw scene string.
- Log messages now accurately reflect what is actually being sent to the MB API.

#### Added
- Filename parsing as fallback strategies 4 and 5 for completely untagged files:
  - Strategy 4: extract ANJ*/ANJCD* catno from filename → catno search
  - Strategy 5: extract artist + title from filename → artist+album search
- `parse_filename()` strips scene tags (WEB, FLAC, TT, FOX etc.), track number prefixes, and disc suffixes (CD1, CD2) before searching.

### v1.2 — 2026-04-25

#### Added
- CSV report saved after every run — one row per FLAC processed, columns: file path, filename, disc number, MBID, MBID source, album, artist, track count, CUE path, status, notes.
- Log file capturing all console output with timestamps and severity levels (INFO/WARNING/ERROR). Both saved to shared `tools\reports\` folder.
- Status values in report: `written`, `skipped`, `no_match`, `api_error`, `write_error`.
- Tracks with unknown lengths flagged with a warning in both the console and notes column.

### v1.1 — 2026-04-25

#### Added
- `--scan` flag: recursively scans a folder tree for FLAC files that need CUE sheets. FLAC files that already have a matching `.cue` next to them are skipped automatically.
- Default scan root is the music library path (`SD\Music`). Pass a path after `--scan` to override: `python flac_to_cue.py --scan "D:\Music"`.
- `Run - FLAC to CUE.cmd` updated to offer scan vs picker choice at launch.

### v1.0 — 2026-04-25

#### Added
- Initial release.
- Reads `MUSICBRAINZ_ALBUMID` tag directly from FLAC files — no manual URL or configuration needed for files already tagged by the tagger.
- Falls back to catalogue number search, then artist + album title search if no MBID tag is present.
- Uses the MusicBrainz JSON API (not HTML scraping) for reliable, structured data.
- Handles multi-disc releases — matches each FLAC to its correct disc by `DISCNUMBER` tag, filename, or folder name (e.g. `CD1`, `Disc 2`).
- Release data cached per MBID — multi-disc folders only make one API call.
- Track lengths converted to CUE frames (MM:SS:FF at 75 frames/sec) for maximum split precision.
- Per-track PERFORMER set from MB artist-credit data, not hardcoded.
- Unknown track lengths handled gracefully with a warning rather than a crash.
- Output filename sanitised for Windows-illegal characters.
- Previews the first 12 lines of the CUE before asking for confirmation.
- Folder or file picker dialog when no path is specified on the command line.
- Output CUE written next to the source FLAC file.

---

## anjuna_mb_lookup.py

### v1.4 — 2026-04-13

#### Added
- `move_flagged_folders()` function: after lookup completes, `--move` prints which folders would move; `--move --apply` executes the moves.
  - `review` folders → `To Review\` subfolder next to source.
  - `not_found` folders → `No Match\` subfolder next to source.
  - `error` folders are left in place.

---

## anjuna_tagger.py

### v1.2 — 2026-04-12

#### Fixed
- Reports were being saved to the script's own subfolder instead of the shared `tools\reports\` folder. Fixed: path now uses `SCRIPT_DIR.parent / "reports"`.

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
