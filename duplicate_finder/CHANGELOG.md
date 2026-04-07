# Changelog — Duplicate Finder Tools

---

## music_report_viewer.html

### v1.1 — 2026-04-05

#### Fixed
- Font size buttons (A−/A+) now correctly resize all table text.

#### Changed
- Table fills the full window height.

#### Added
- Column resize handles — drag the right edge of any column header.

---

## undo_report_viewer.html

### v1.1 — 2026-04-05

#### Fixed
- Font size buttons (A−/A+) now correctly resize all table text.

#### Changed
- Table fills the full window height.

#### Added
- Column resize handles — drag the right edge of any column header.

---

## build_fp_cache.py

### v2.0 — 2026-04-02

#### Added
- **Fingerprint error classification** — flagged files are now split into two categories:
  - `too_small` — file duration under 30 seconds, or file size under 500 KB if duration is unreadable. These legitimately can't produce a meaningful fingerprint (interludes, short clips, etc.).
  - `corrupted` — normal-sized file where fingerprinting failed or returned a suspiciously short result. These warrant closer inspection.
- **`Category` column** added to the warnings CSV — makes it easy to sort and filter in the browser.
- **`--copy-errors` flag** — copies flagged files into `reports\fp_errors\too_small\` and `reports\fp_errors\corrupted\`, preserving relative folder structure. Without `--apply` it dry-runs and prints what would be copied. Add `--apply` to actually copy.
- **`--error-dest PATH` flag** — override the default copy destination.
- **`--apply` flag** — required to execute the file copy. Cache building is unaffected (always runs).
- New bat file: `Run - Copy FP Errors (Apply).bat` — runs `--fp-only --copy-errors --apply`.

#### Changed
- Warning output now shows `[too_small]` or `[corrupted]` label per file.
- Summary line added: count of too_small vs corrupted before the per-file list.
- Warnings CSV sorted by Category first, then Reason, Folder, Filename.

---

## find_music_duplicates.py

### v3.1 — (previous session)

See repository history.

---

## undo_duplicates.py

### v2.2 — (previous session)

See repository history.
