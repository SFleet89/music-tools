# Changelog — Move For Review

## v1.3 — 2026-06-18

### Added
- **89 new bad-fingerprint filenames** added to `BAD_FINGERPRINT_FILES` from the
  `acoustid_fingerprint_applied_20260618_204854.csv` run. These are files where AcoustID
  returned a high-confidence match but the matched artist has no relationship to the
  filename artist (detected by zero word-overlap between filename artist and mb_artist).
  Their album folders will now be flagged for review on the next apply run.
- BAD_FINGERPRINT_FILES set now grouped with dated comments so future additions are traceable.

## v1.2 — (existing, imported 2026-06-18)

- Supports both main mode (`--csv`, `--source`, `--dest`) and undo mode (`--undo --csv`)
- Moves album folders (artist/album/), not individual files, preserving relative path structure
- Undo reads `item` column (v1.2) with fallback to `filename` column (v1.0/v1.1)
- `BAD_FINGERPRINT_FILES` set for known wrong AcoustID matches
- Reports saved to `reports/` next to the script
- Confirmation prompt before any destructive action in apply mode

## v1.1 — (prior)

- Added undo mode

## v1.0 — (prior)

- Initial release
