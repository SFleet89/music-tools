# Changelog — Anjuna MusicBrainz Batch Lookup

---

## v1.2 — 2026-03-22

### Fixed
- **Catno scoring bug** — releases were scoring 0 on catno even when correctly matched, because MusicBrainz uses hyphens in catalogue numbers (`ANJ-101`) while folder names don't (`ANJ101`). Hyphens are now stripped before comparison so `ANJ101 == ANJ-101`.
- **Remix variant handling** — R/R2 remix releases were falling through to D (digital) suffix variants, causing incorrect matches. Variant generation is now type-aware: remix releases only try other R variants, digital releases only try other D variants.

### Changed
- **Report output location** — reports now save to a `reports\` folder next to the script (`anjuna_mb_lookup\reports\`) instead of inside the batch folder being processed.
- **Folder picker** — running the script with no arguments now opens a tkinter folder picker dialog instead of printing usage and exiting. Command line path argument still works as before.
- Internal refactor of `_make_row()` helper to reduce code duplication.

---

## v1.1 — 2026-03-22

### Added
- **File metadata comparison** — reads title, artist, and track count from existing file tags using mutagen, then fetches the full MusicBrainz tracklist for each candidate and fuzzy-matches titles. This adds a `meta_score` to complement the `catno_score`.
- **Combined scoring** — `combined_score` is a weighted average of catno (60%) and metadata (40%) scores, used to rank candidates and drive auto-pick decisions.
- **New CSV columns** — `catno_score`, `meta_score`, `combined_score`, `track_match_pct`, `count_match`, `local_tracks`, `mb_tracks`.
- **Score bars in viewer** — `combined_score` and `track_match_pct` now render as colour-coded progress bars (green ≥80, amber ≥50, red <50).
- **Track count column in viewer** — shows local/MB track count in green if they match, red if they don't.
- **Candidate scores in viewer** — the candidates expand panel now shows catno/meta/combined scores for each candidate so you can see why one was ranked above another.
- Graceful fallback if mutagen is not installed — script runs in catno-only mode with a warning.

---

## v1.0 — 2026-03-22

### Initial release
- Scans a batch folder of Anjunabeats releases
- Extracts ANJ*/ANJCD*/ANJDJ* catalogue numbers from subfolder names
- Searches MusicBrainz by catalogue number
- Tries suffix variants (D, R, EP, CD, DJ, DEEP) if exact catno returns no results
- Auto-pick and manual review modes for multi-result cases
- CSV report with folder, MBID, MB title/artist/date, and candidates list
- HTML viewer with status filter pills, search, sortable columns, and candidate picker
- MusicBrainz rate limit respected (1.1 second delay between requests)
