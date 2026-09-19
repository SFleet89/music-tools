# Changelog — organize_spotify

## v1.1 — 2026-06-17

### Changed
- **Colon sanitization**: colons (`:`) in album/artist names are now replaced with
  ` - ` (space-dash-space) instead of `_`. This looks natural for album subtitles
  (e.g. `BLEACH the Movie: Fade to Black` → `BLEACH the Movie - Fade to Black`).
  All other forbidden Windows characters (`\ / * ? " < > |`) still become `_`.

## v1.0 — 2026-05-31

### Added
- Initial release
- Reads `albumartist`, `album`, `title` tags via mutagen
- Organises files into `AlbumArtist / Album` staging structure
- Dry-run by default; `--apply` required to move files
- `--pick-source` / `--pick-dest` folder dialogs
- `--path-source` / `--path-dest` for scripted use
- Defaults destination to `<source>\Organized\` if not specified
- Collision handling: appends `(1)`, `(2)` … to avoid overwrites
- Confirmation prompt before any moves in apply mode
- Timestamped CSV report saved to `reports\` after every run
- Two `.cmd` launchers (dry run and apply)
