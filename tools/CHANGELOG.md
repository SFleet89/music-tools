# Changelog — tools/

---

## check_conventions.py

### Allowlist update — 2026-10-21 (no code change)
- Accepted `duplicate_finder/fpcalc.exe`, `music_integrity/mp3val.exe` and
  `music_integrity/mp3val-frontend.exe` as deliberately shipped third-party tools (user OK).
  21 entries now. `report_viewer/old_viewers.rar` was made local-only (untracked +
  gitignored) instead, so the live tree now passes (exit 0, warnings only).
- The 18 personal-path findings in docs were fixed at the source, not allowlisted.

### v1.0 — 2026-10-20

#### Added
- New read-only convention check (audit Phase 1, step 1), grown from the audit's
  `probe.py`, `call_check.py` and `import_check.py`. 14 checks: compile, nul, imports,
  run-calls, panel-wiring, personal-path, private-file, viewer-offline, run-exit,
  argv-module, rename, folder-files (all fail), version-drift and viewer-coverage
  (warnings only). Exit 0/1.
- `conventions_allowlist.json`: 18 known problems accepted with reasons (3 run-exit,
  5 argv-module, 2 rename, 8 folder-files). Stale entries are reported.
- `Run - Check Conventions.cmd` launcher.

#### Verified
- Read-only: `git status --porcelain --ignored` is identical before and after a full run.
- `selftest_check_conventions.py` v1.0: clean copy exits 0; 17 injected defects each
  exit 1 (version drift exits 0 as a warning) on the right check; a folder that isn't a git repo
  exits 1; real broken commit `227df61^` exits 1 and is reported for NUL bytes and
  compile failure in `mb_tagger.py`, the failing `gui.main_window` import and the Music
  Integrity panel's wrong argument names (`folder`, `quick`).
- The self-test itself fails (exit 1) when the NUL check is disabled in a copy.
- Fixed before release: run-calls no longer reports "doesn't define run_x" when the
  source file can't be parsed (that's the compile check's finding).
