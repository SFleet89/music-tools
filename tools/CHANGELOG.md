# Changelog — tools/

---

## Hooks — claude_guard.py, git-hooks/pre-commit, selftest_hooks.py

### claude_guard.py v1.1 — 2026-10-21

#### Fixed
- `git stash push` was blocked as if it were `git push`. The push rule now skips
  `stash push`; a real push is still blocked, including one chained after a stash
  (`git stash push && git push`) and `git -C stash-dir push`.

#### Verified
- `selftest_hooks.py`: 4 new command cases. They failed before the fix (4 FAIL) and pass after;
  whole self-test PASS.
- `"onFailure": "block"` in `.claude/settings.json` checked against the Claude Code hooks
  docs: it is a real setting (blocks the command if the guard can't run). Needs Claude Code
  2.1.295+; the `claude` CLI on PATH here is 2.1.211, which ignores it (README notes this).

### v1.0 — 2026-10-21

#### Added
- `git-hooks/pre-commit`: runs the quick convention check before every commit; blocks on
  failure or missing Python. LF endings forced in `.gitattributes`. Enabled with
  `git config core.hooksPath tools/git-hooks`.
- `claude_guard.py`: Claude Code hook script. `pre` blocks destructive git commands,
  pushing, skipping the hooks, and naming the personal config files; `post` NUL-scans and
  compiles edited files. Wired in `.claude/settings.json` (gitignored), which also denies
  reading the two config files.
- `selftest_hooks.py`.

#### Verified
- Self-test passes: 55 guard command cases, 7 edited-file cases, pre-commit allows a
  clean commit and refuses a NUL-byte commit (HEAD unchanged), settings wiring.
- Self-test fails (exit 1) when a guard rule is removed, and when the pre-commit hook
  ignores a failed check (both on copies).
- Live: the guard blocked a `git config core.hooksPath` command in the session that
  created it.

#### Not verified
- The pre-commit hook on a real commit in the live repo (waits for the user to set
  `core.hooksPath`). The Read-deny rule was not triggered.

---

## check_conventions.py

### v1.1 — 2026-10-21

#### Fixed
- `viewer-coverage` warned about scripts whose reports are saved under a different name than
  the script (`anjuna_mb_lookup.py` → `anjuna_lookup_*.csv`, `find_library_dupes.py` →
  `library_dupes_*.csv`), although viewer.html has configs for those names. It now also reads
  the report filename prefixes from the script's `.csv` strings and tests them against every
  `filePattern` in viewer.html. Warnings 5 → 3; the 3 left are real (`build_fp_cache`,
  `compare_audio`, `repair_playlists` have no viewer config). The warning text now lists the
  prefixes it tried.

#### Verified
- `selftest_check_conventions.py`: new injected case (Anjuna `filePattern` removed) must be
  reported by `viewer-coverage`; whole self-test PASS.

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
