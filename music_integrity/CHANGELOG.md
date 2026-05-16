# Changelog — check_music_integrity.py

---

## v1.0 — 2026-05-02

### Added
- Initial release.
- VBR header check for MP3 files via `mp3val` (fast, always runs).
  - Detects missing or incorrect Xing/LAME/VBRI headers.
  - In `--apply` mode, repairs headers in place via `mp3val -f`.
  - Reports `vbr_needs_fix` / `vbr_fixed` / `vbr_unfixable`.
- Full decode integrity check via `ffmpeg` (slow, opt-in with `--integrity`).
  - Catches corrupt frames, truncated files, audio stream errors.
  - Informational only — cannot auto-repair corruption.
- Parallel processing for read-only checks (up to 8 threads).
- Sequential processing for apply mode (safer for file writes).
- Folder picker (tkinter) — no path typing needed.
- Reports saved to `<script_folder>/reports/`.
- Descriptive filename suffix: `_dry`, `_applied`, `_dry_integrity`, `_applied_integrity`.
- `--mp3-only` flag to skip FLAC/AAC/M4A files.
- Tool discovery: checks next to script first, then PATH.
- Graceful degradation if `mp3val` or `ffmpeg` not found.
