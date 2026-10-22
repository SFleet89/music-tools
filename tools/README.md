# tools/ — Developer checks

Read-only checks for the project itself. They don't touch your music.

## check_conventions.py

Checks the project's files against its coding conventions and prints a plain-English
report. It opens files only to read them and changes nothing.

It checks the files git tracks, plus new files that aren't gitignored yet, so a file
is checked before it is committed. Gitignored folders (`docs/`, the local-only tools)
are never scanned.

**Usage** (from the project folder, or double-click `Run - Check Conventions.cmd`):

```
python -B -X utf8 tools/check_conventions.py
python -B -X utf8 tools/check_conventions.py --no-imports   # skip the GUI import check (faster; no PySide6 needed)
python -B -X utf8 tools/check_conventions.py --verbose      # also list accepted (allowlisted) items
python -B -X utf8 tools/check_conventions.py --path "<other copy of the repo>"
python -B -X utf8 tools/check_conventions.py --allowlist "<file.json>"
```

**Exit code:** 0 = no failures (warnings are allowed), 1 = at least one failure, or
the check couldn't run (for example, git not found or the folder isn't a git repo).

**What it checks**

| Check | Fails when |
|---|---|
| compile | a `.py` file doesn't compile |
| nul | a text file contains NUL bytes |
| imports | a `gui/*.py` module can't be imported (runs offscreen, no window, no `__pycache__`) |
| run-calls | a panel passes an argument name its `run_*()` doesn't accept, or imports a `run_*()` that doesn't exist |
| panel-wiring | a `gui/*_panel.py` isn't imported by `gui/main_window.py` |
| personal-path | your Windows user name appears in a published file (worked out at run time, so it's never written in the code) |
| private-file | a personal config, database, archive or `.exe` file, or any file over 1 MB, is published |
| viewer-offline | `report_viewer/viewer.html` loads something from the internet |
| run-exit | a `run_*()` calls `sys.exit()`, `exit()`, `quit()` or `input()` (PW-02) |
| argv-module | a tool script reads `sys.argv` at module level (PW-01) |
| rename | `os.rename` / `Path.rename` is used instead of `shutil.move` (Rule 4) |
| folder-files | a tool folder lacks README, CHANGELOG, or a Dry Run / Apply `.cmd` (Rules 7, 8) |
| version-drift | *warning only:* docstring, CHANGELOG and `TASKS.md` versions disagree |
| viewer-coverage | *warning only:* a CSV-writing script has no report viewer config |

**Known limits:** `run-calls` only sees direct calls by name (`run_x(...)`), not calls
through a module (`mod.run_x(...)`) or the `_lookup_base` / `_tagger_base` helpers. It
doesn't check which result keys a panel reads. `version-drift` needs the local
`TASKS.md`. These checks read code; they don't run your tools.

## conventions_allowlist.json

Known problems accepted for now. Each entry has a `check`, a `key` (shown by
`--verbose`) and a `reason`. When you fix one, delete its entry. The check warns
about entries that no longer match anything.

## selftest_check_conventions.py

Proves the check can fail. It works only on throw-away copies in your temp folder:

1. copies the project and records today's findings as a baseline; the clean copy must pass;
2. breaks one thing at a time (17 cases: NUL byte, syntax error, bad import, wrong
   `run_*()` argument, unwired panel, personal path, private file, ...); each must fail
   on the right check;
3. replays a real broken commit (`227df61^`: NUL bytes in `mb_tagger.py`, wrong argument
   names in the Music Integrity panel); it must fail and name both.

```
python -B -X utf8 tools/selftest_check_conventions.py
python -B -X utf8 tools/selftest_check_conventions.py --rev <commit> --keep
```

Run it after any change to `check_conventions.py`.

## git-hooks/pre-commit

Runs `check_conventions.py --no-imports` (about 6 seconds) before every commit and
blocks the commit if any check fails, or if Python can't be found. Turn it on once
per copy of the repo:

```
git config core.hooksPath tools/git-hooks
```

It checks the files on disk, not exactly what's staged, and new files that aren't
gitignored count too. To skip it on purpose for one commit: `git commit --no-verify`.

## claude_guard.py

The hook script for Claude Code, wired up in `.claude/settings.json` (local only,
gitignored). Before a Bash or PowerShell command it blocks: `git push`, `reset --hard`,
`clean -f`, `branch -D`, `checkout .` / `restore .`, `--no-verify`, changes to
`core.hooksPath`, and anything naming `music_config.json` or `library_dupes_config.json`.
After Claude edits a file it scans for NUL bytes and compiles `.py` files, and tells
Claude straight away if something's wrong. Pushing stays your job.

It is a safety net, not a sandbox: a script Claude writes could still do these
things. A commit message that mentions "git push" is blocked too; reword it.
`git stash push` (saving work locally) is allowed.

`.claude/settings.json` sets `"onFailure": "block"`, so if the guard itself can't run
(e.g. Python missing) the command is blocked rather than let through. That setting needs
Claude Code 2.1.295 or later; older versions ignore it and let the command through.

## selftest_hooks.py

Proves the guard and the pre-commit hook can fail: every blocked command in both
shells, everyday commands that must stay allowed, broken and clean edited files, and
in a temp copy of the project a clean commit (allowed) and a NUL-byte commit (refused).

```
python -B -X utf8 tools/selftest_hooks.py
```

## Requirements

Python 3.12+, git on PATH. The GUI import check needs PySide6 (as the app does).
