# Changelog — repair_playlists.py

---

## v1.5 — (current)

- Internal improvements and stability fixes.

---

## v1.1 — 2026-05-02

### Added
- Folder and file pickers now open by default — no need to type paths.
- `--playlists` and `--music` flags still accepted to skip pickers (used by .cmd files).
- `--selections` picker opens automatically in apply mode when ambiguous matches exist.
- `.cmd` files regenerated after every run with current paths.
- "Press Enter to close" prompt added so the terminal window does not vanish immediately.
- Next-steps instructions printed at end of dry run summary.

---

## v1.0 — 2026-04-29

### Added
- Initial release.
- Scans `.m3u` playlist files and repairs broken paths against current library.
- Fuzzy name matching (rapidfuzz or difflib fallback) with configurable threshold.
- Track-number-prefix stripping for robust stem matching.
- Three-bucket categorisation: resolved / ambiguous / missing.
- HTML selector for ambiguous matches — side-by-side album/path comparison with radio-button pick.
- Selections JSON and `--selections` flag for applying picks in a separate run.
- Relative path output (forward slashes) — playlists work across drives and machines.
- `--apply` flag required to write files (dry run by default).
- Confirmation prompt before writing repaired playlists.
- Reports: CSV, missing log (`.txt`), HTML selector.
- Graceful encoding fallback: UTF-8 then latin-1 for old playlists.
- Unresolved/missing entries preserved with `# REPAIR_UNRESOLVED` or `# REPAIR_MISSING` comments.
