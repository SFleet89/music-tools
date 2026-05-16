# Music Integrity Checker

Scans audio files for corruption and VBR header issues.

Two modes of checking:
- **VBR header check** (fast, always runs) — uses `mp3val` to detect missing or incorrect Xing/LAME/VBRI headers in MP3 files. In `--apply` mode, attempts to repair them in place.
- **Full decode integrity check** (slow, opt-in with `--integrity`) — uses `ffmpeg` to catch corrupt frames, truncated files, and audio stream errors. Results are informational only — corruption cannot be auto-repaired.

---

## Requirements

- `mp3val.exe` — included in this folder
- `ffmpeg` — must be installed and on your PATH (only needed for `--integrity` mode)

---

## Usage

```
python check_music_integrity.py              # dry run VBR check
python check_music_integrity.py --apply      # apply VBR header repairs
python check_music_integrity.py --integrity  # dry run + full decode check
python check_music_integrity.py --mp3-only   # skip FLAC/AAC/M4A files
```

---

## .cmd files

| File | What it does |
|---|---|
| `check_music_integrity_dry.cmd` | Dry run VBR check |
| `check_music_integrity_apply.cmd` | Apply VBR header repairs |
| `check_music_integrity_integrity.cmd` | Full decode integrity check |
| `check_music_integrity_apply_from_csv.cmd` | Apply repairs from a previous dry-run CSV |

---

## Reports

Saved to `music_integrity/reports/` with suffix: `_dry`, `_applied`, `_dry_integrity`, or `_applied_integrity`.

Status values: `vbr_needs_fix`, `vbr_fixed`, `vbr_unfixable`, `ok`, `error`

---

## Supported formats

MP3 (VBR check + integrity), FLAC / AAC / M4A (integrity check only unless `--mp3-only`)
