"""
Claude Code Guard  v1.1

Hook script for Claude Code (wired up in .claude/settings.json). Reads the hook
event as JSON on stdin. Changes nothing; it only allows, blocks or reports.

    python -B -X utf8 tools/claude_guard.py pre    # PreToolUse  on Bash | PowerShell
    python -B -X utf8 tools/claude_guard.py post   # PostToolUse on Edit | Write | MultiEdit

pre  — blocks (exit 2) shell commands that:
         * push, or discard work: git push, reset --hard, clean -f, branch -D,
           checkout . / restore .
         * skip the git hooks: --no-verify, or overriding core.hooksPath
         * mention a personal config file (music_config.json, library_dupes_config.json)
       Pushing stays the user's job: they run `git push` themselves.
post — after an edit: scans the file for NUL bytes and, for .py files, compiles it.
       On a problem it exits 2 so Claude is told at once (the edit itself has
       already happened and must be fixed).

Exit codes: 0 = allowed / clean, 2 = blocked or problem found (message on stderr).
A pre event that can't be read is blocked (fails closed).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

VERSION = "1.1"

PRIVATE_FILES = ("music_config.json", "library_dupes_config.json")

# (pattern, plain-English reason). Matched against the whole command text, so a
# commit message that merely mentions "git push" is also blocked — reword it.
BLOCKED = [
    # "git stash push" saves local work and is allowed; any other git ... push is not.
    (r"\bgit\b(?:(?!\bstash\s)[^\n|;&])*\bpush\b", "pushing is the user's job — ask them to run git push"),
    (r"\breset\b[^\n|;&]*--hard\b", "git reset --hard discards work"),
    (r"\bgit\b[^\n|;&]*\bclean\b[^\n|;&]*\s-[a-zA-Z]*f", "git clean -f deletes untracked files"),
    (r"\bgit\b[^\n|;&]*\bbranch\b[^\n|;&]*(\s-D\b|--delete\s+--force|--force\s+--delete)", "git branch -D deletes a branch"),
    (r"\bgit\b[^\n|;&]*\bcheckout\b\s+(--\s+)?\.(\s|$)", "git checkout . discards changes"),
    (r"\bgit\b[^\n|;&]*\brestore\b(\s+--?\S+)*\s+\.(\s|$)", "git restore . discards changes"),
    (r"--no-verify\b", "--no-verify skips the pre-commit convention check"),
    (r"core\.hooks[Pp]ath", "changing core.hooksPath switches off the pre-commit check"),
]

TEXT_EXTS = {".py", ".cmd", ".bat", ".md", ".txt", ".html", ".htm", ".json", ".spec",
             ".css", ".js", ".csv", ".ini", ".cfg", ".toml", ".yml", ".yaml"}


def check_command(command: str) -> str | None:
    """Return why the command is blocked, or None if it's allowed."""
    for pat, why in BLOCKED:
        flags = 0 if r"-D\b" in pat else re.I
        if re.search(pat, command, flags):
            return why
    low = command.lower()
    for name in PRIVATE_FILES:
        if name in low:
            return f"{name} is a personal config file; Claude must not open or touch it"
    return None


def check_file(path: Path) -> str | None:
    """Return the problem with an edited file, or None if it's fine."""
    if not path.is_file() or path.suffix.lower() not in TEXT_EXTS:
        return None
    data = path.read_bytes()
    problems = []
    n = data.count(b"\x00")
    if n:
        problems.append(f"contains {n} NUL byte(s)")
    if path.suffix.lower() == ".py":
        try:
            compile(data, str(path), "exec", dont_inherit=True)
        except (SyntaxError, ValueError) as e:
            line = getattr(e, "lineno", None)
            problems.append(f"does not compile{f' (line {line})' if line else ''}: {e.args[0] if e.args else e}")
    return "; ".join(problems) or None


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("pre", "post"):
        print("usage: claude_guard.py pre|post  (hook event JSON on stdin)", file=sys.stderr)
        return 2
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace") or "{}")
        tool_input = event.get("tool_input") or {}
    except (ValueError, AttributeError) as e:
        print(f"claude_guard: could not read the hook event ({e}); blocked to be safe.", file=sys.stderr)
        return 2 if mode == "pre" else 1

    if mode == "pre":
        why = check_command(str(tool_input.get("command", "")))
        if why:
            print(f"BLOCKED by tools/claude_guard.py: {why}.", file=sys.stderr)
            return 2
        return 0

    fp = tool_input.get("file_path") or (event.get("tool_response") or {}).get("filePath")
    if not fp:
        return 0
    problem = check_file(Path(fp))
    if problem:
        print(f"PROBLEM in {fp}: {problem}. Fix this file before doing anything else "
              f"(reported by tools/claude_guard.py).", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
