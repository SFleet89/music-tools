# Changelog — MusicBrainz Tagger Tools

---

## anjuna_tagger.py

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

## mb_tagger.py

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
