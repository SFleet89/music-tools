"""
Self-test for the hooks  v1.0

Proves the Claude Code guard and the git pre-commit hook can fail. Works only on
sample input and throw-away copies in a temp folder; the project is only read.

1. claude_guard.py pre: each dangerous command (in Bash and PowerShell form) must
   be blocked (exit 2); everyday commands must be allowed (exit 0); unreadable
   input must be blocked.
2. claude_guard.py post: an edited file with NUL bytes or a syntax error must be
   reported (exit 2); clean files must pass (exit 0).
3. tools/git-hooks/pre-commit, in a temp copy of the project: a clean commit must
   succeed; a commit with a NUL byte must be refused and leave HEAD unchanged.
4. .claude/settings.json (if present) must parse and point at claude_guard.py.

Usage:
    python -B -X utf8 tools/selftest_hooks.py [--keep]

Exit code: 0 = every case behaved as expected, 1 = at least one did not.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
GUARD = SCRIPT_DIR / "claude_guard.py"
sys.path.insert(0, str(SCRIPT_DIR))
from selftest_check_conventions import copy_live, git, remove_temp  # noqa: E402

# (command, should be blocked)
COMMANDS = [
    ("git push origin main", True),
    ("git push --force", True),
    ("cd repo && git push", True),
    ("git -C 'C:/x' push", True),
    ("git stash push -m wip && git push", True),
    ("git -C stash-dir push", True),
    ("git reset --hard HEAD~1", True),
    ("git clean -fd", True),
    ("git clean -xfd", True),
    ("git branch -D old-branch", True),
    ("git checkout .", True),
    ("git checkout -- .", True),
    ("git restore .", True),
    ("git restore --staged .", True),
    ("git commit --no-verify -m x", True),
    ("git -c core.hooksPath=nul commit -m x", True),
    ("git config core.hooksPath tools", True),
    ("cat music_config.json", True),
    ("Get-Content .\\library_dupes\\library_dupes_config.json", True),
    ("git status --short", False),
    ("git stash push -m wip", False),
    ("git stash push -- tools/x.py", False),
    ("git commit -m 'add check'", False),
    ("git add -- tools/check_conventions.py", False),
    ("git log --oneline -5", False),
    ("git branch -d merged-branch", False),
    ("git checkout -b feature", False),
    ("git restore --staged tools/x.py", False),
    ("git clean -n", False),
    ("python -B -X utf8 tools/check_conventions.py", False),
    ("cat duplicate_finder/music_config.example.json", False),
]


def run_guard(mode: str, payload: bytes) -> tuple[int, str]:
    res = subprocess.run([sys.executable, "-B", "-X", "utf8", str(GUARD), mode],
                         input=payload, capture_output=True)
    return res.returncode, res.stderr.decode("utf-8", errors="replace").strip()


def event(tool: str, **tool_input) -> bytes:
    return json.dumps({"tool_name": tool, "tool_input": tool_input}).encode("utf-8")


def main() -> int:
    keep = "--keep" in sys.argv[1:]
    work = Path(tempfile.mkdtemp(prefix="hooks_selftest_"))
    print(f"Self-test for the hooks — temp folder: {work}")
    problems = []

    def expect(ok: bool, label: str, detail: str = ""):
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}{'' if ok else '  -> ' + detail}")
        if not ok:
            problems.append(label)

    try:
        print("\n1. Guard before shell commands")
        for cmd, blocked in COMMANDS:
            for tool in ("Bash", "PowerShell"):
                code, err = run_guard("pre", event(tool, command=cmd))
                want = 2 if blocked else 0
                expect(code == want, f"{tool}: {'blocks' if blocked else 'allows'} `{cmd}`",
                       f"exit {code} {err[:120]}")
        code, _ = run_guard("pre", b"not json")
        expect(code == 2, "Unreadable hook input is blocked", f"exit {code}")

        print("\n2. Guard after edits")
        samples = {
            "good.py": (b"x = 1\n", 0),
            "syntax.py": (b"def broken(:\n", 2),
            "nul.py": (b"x = 1\n\x00\x00", 2),
            "nul.md": (b"# notes\n\x00", 2),
            "good.md": (b"# notes\n", 0),
            "picture.png": (b"\x89PNG\x00\x00", 0),      # binary: not checked
        }
        for name, (data, want) in samples.items():
            p = work / name
            p.write_bytes(data)
            code, err = run_guard("post", event("Write", file_path=str(p)))
            expect(code == want, f"{name}: exit {want}", f"exit {code} {err[:120]}")
        code, _ = run_guard("post", event("Edit", file_path=str(work / "missing.py")))
        expect(code == 0, "Missing file is ignored", f"exit {code}")

        print("\n3. Git pre-commit hook (temp copy of the project)")
        repo = work / "repo"
        copy_live(repo)
        git(repo, "config", "core.hooksPath", "tools/git-hooks")
        ident = ["-c", "user.name=selftest", "-c", "user.email=selftest@example.invalid"]
        res = subprocess.run(["git", "-C", str(repo), *ident, "commit", "-q", "-m", "baseline"],
                             capture_output=True)
        expect(res.returncode == 0, "Clean commit is allowed",
               (res.stdout + res.stderr).decode("utf-8", "replace")[-400:])
        head = git(repo, "rev-parse", "HEAD").strip()
        target = repo / "music_tools_common.py"
        target.write_bytes(target.read_bytes() + b"\x00\x00")
        git(repo, "add", "music_tools_common.py")
        res = subprocess.run(["git", "-C", str(repo), *ident, "commit", "-q", "-m", "broken"],
                             capture_output=True)
        out = (res.stdout + res.stderr).decode("utf-8", "replace")
        expect(res.returncode != 0 and "BLOCKED" in out, "Commit with a NUL byte is refused",
               f"exit {res.returncode}: {out[-300:]}")
        expect(git(repo, "rev-parse", "HEAD").strip() == head, "Refused commit leaves HEAD unchanged")

        print("\n4. Claude Code settings")
        settings = ROOT / ".claude" / "settings.json"
        if settings.is_file():
            try:
                cfg = json.loads(settings.read_text(encoding="utf-8"))
                cmds = [h["command"] for ev in cfg.get("hooks", {}).values() for m in ev for h in m["hooks"]]
                expect(any("claude_guard.py\" pre" in c for c in cmds)
                       and any("claude_guard.py\" post" in c for c in cmds),
                       ".claude/settings.json runs claude_guard.py pre and post", f"commands: {cmds}")
                expect(any("music_config.json" in r for r in cfg.get("permissions", {}).get("deny", [])),
                       ".claude/settings.json denies reading music_config.json")
            except (ValueError, KeyError, TypeError) as e:
                expect(False, ".claude/settings.json parses", str(e))
        else:
            print("  [SKIP] no .claude/settings.json in this copy")
    except Exception as e:  # any crash in the harness is a failed self-test
        problems.append(f"harness error: {type(e).__name__}: {e}")
        print(f"\nERROR: {type(e).__name__}: {e}")
    finally:
        if keep:
            print(f"\nKept temp folder: {work}")
        else:
            remove_temp(work)

    print()
    if problems:
        print(f"SELF-TEST: FAIL — {len(problems)} case(s) did not behave as expected.")
        return 1
    print("SELF-TEST: PASS — the guard blocked and reported what it should, and the pre-commit hook refused the bad commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
