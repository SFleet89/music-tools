"""
Self-test for check_conventions.py  v1.0

Proves the convention check can fail. Works only on throw-away copies in a temp
folder; the project itself is only read (git ls-files / git archive).

1. Copies the project's files into a temp folder and records today's findings as
   a baseline, so only NEW problems count. The clean copy must exit 0.
2. Breaks one thing at a time in a fresh copy (NUL byte, syntax error, bad import,
   wrong run_*() argument, ...). Each must exit 1 and be reported by the right check.
3. Replays a real broken commit (default 227df61^: NUL bytes in mb_tagger.py and the
   Music Integrity panel's wrong argument names). It must exit 1 and name both.

Usage:
    python -X utf8 tools/selftest_check_conventions.py
    python -X utf8 tools/selftest_check_conventions.py --rev 227df61^ --keep

Exit code: 0 = every case behaved as expected, 1 = at least one did not.
--keep leaves the temp folder in place for inspection (its path is printed).
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
CHECKER = SCRIPT_DIR / "check_conventions.py"
sys.path.insert(0, str(SCRIPT_DIR))
import check_conventions as cc  # noqa: E402

USER = Path.home().name


def git(cwd: Path, *args: str, data: bytes | None = None) -> bytes:
    res = subprocess.run(["git", "-C", str(cwd), *args], input=data, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.decode('utf-8', 'replace')}")
    return res.stdout


def remove_temp(path: Path) -> None:
    """Delete one of this test's own temp copies (git marks its object files read-only)."""
    import os
    import stat

    def unlock(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onexc=unlock)


def make_repo(dest: Path) -> None:
    git(dest, "init", "-q")
    git(dest, "add", "-A")


def copy_live(dest: Path) -> None:
    dest.mkdir(parents=True)
    for rel in cc.list_files(ROOT):
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest / rel)
    if (ROOT / "TASKS.md").is_file():                 # gitignored, but the version check reads it
        shutil.copy2(ROOT / "TASKS.md", dest / "TASKS.md")
    make_repo(dest)


def export_rev(rev: str, dest: Path) -> None:
    dest.mkdir(parents=True)
    tar = git(ROOT, "archive", "--format=tar", rev)
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        t.extractall(dest, filter="data")
    make_repo(dest)


def run_cli(root: Path, allowlist: Path, imports: bool) -> tuple[int, str]:
    cmd = [sys.executable, "-B", "-X", "utf8", str(CHECKER), "--path", str(root), "--allowlist", str(allowlist)]
    if not imports:
        cmd.append("--no-imports")
    res = subprocess.run(cmd, capture_output=True)
    return res.returncode, res.stdout.decode("utf-8", errors="replace")


# ── Mutations: each takes the copy's root and breaks one thing ───────────────

def append(rel: str, text: str | bytes):
    def f(r: Path):
        p = r / rel
        p.write_bytes(p.read_bytes() + (text if isinstance(text, bytes) else text.encode("utf-8")))
    return f


def replace_once(rel: str, old: str, new: str):
    def f(r: Path):
        p = r / rel
        s = p.read_bytes()
        assert s.count(old.encode()) >= 1, f"anchor {old!r} not found in {rel}"
        p.write_bytes(s.replace(old.encode(), new.encode(), 1))
    return f


def new_file(rel: str, content: str, force_add: bool = False):
    def f(r: Path):
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text(content, encoding="utf-8")
        if force_add:
            git(r, "add", "-f", rel)
    return f


def delete(rel: str):
    def f(r: Path):
        (r / rel).unlink()
    return f


# (name, mutation, expected check id, text the finding must mention, needs imports, expected exit)
CASES = [
    ("NUL bytes in a shared module", append("music_tools_common.py", b"\x00\x00\x00"),
     "nul", "music_tools_common.py", False, 1),
    ("NUL bytes also stop compiling", append("music_tools_common.py", b"\x00\x00\x00"),
     "compile", "music_tools_common.py", False, 1),
    ("Syntax error", append("rename_undo/rename_undo.py", "\ndef broken(:\n"),
     "compile", "rename_undo/rename_undo.py", False, 1),
    ("GUI module that can't import", append("gui/report_viewer_panel.py", "\nimport selftest_no_such_module_xyz\n"),
     "imports", "gui.report_viewer_panel", True, 1),
    ("Panel passes a wrong argument name",
     append("gui/music_integrity_panel.py",
            "\ndef _selftest_call():\n"
            "    from music_integrity.check_music_integrity import run_check_music_integrity\n"
            "    run_check_music_integrity(selftest_bogus=1)\n"),
     "run-calls", "selftest_bogus", False, 1),
    ("Panel imports a run_*() that doesn't exist",
     append("gui/sort_by_artist_panel.py",
            "\ndef _selftest_import():\n"
            "    from sort_by_artist.sort_by_artist import run_selftest_missing\n"),
     "run-calls", "run_selftest_missing", False, 1),
    ("Panel not wired into main window", new_file("gui/selftest_orphan_panel.py", "X = 1\n"),
     "panel-wiring", "gui/selftest_orphan_panel.py", False, 1),
    ("Personal path in a script", append("sort_by_artist/sort_by_artist.py", f"\n# C:\\Users\\{USER}\\Music\n"),
     "personal-path", "sort_by_artist/sort_by_artist.py", False, 1),
    ("Personal config force-added to git", new_file("music_config.json", "{}\n", force_add=True),
     "private-file", "music_config.json", False, 1),
    ("Database file added", new_file("rename_undo/selftest.db", "x"),
     "private-file", "rename_undo/selftest.db", False, 1),
    ("Viewer loads from the internet",
     append("report_viewer/viewer.html", '\n<script src="https://cdn.example.com/x.js"></script>\n'),
     "viewer-offline", "cdn.example.com", False, 1),
    ("sys.exit() inside run_*()",
     append("sort_cd_tracks/sort_cd_tracks.py", "\ndef run_selftest_exit():\n    import sys\n    sys.exit(1)\n"),
     "run-exit", "run_selftest_exit", False, 1),
    ("input() inside run_*()",
     append("sort_cd_tracks/sort_cd_tracks.py", "\ndef run_selftest_input():\n    input('?')\n"),
     "run-exit", "run_selftest_input", False, 1),
    ("sys.argv read at module level", append("fix_featuring/fix_featuring.py", "\nSELFTEST_FLAG = '--x' in sys.argv\n"),
     "argv-module", "fix_featuring/fix_featuring.py", False, 1),
    ("Path.rename used", append("rename_undo/rename_undo.py", "\ndef _selftest_rename(p):\n    p.rename('x')\n"),
     "rename", "rename_undo/rename_undo.py", False, 1),
    ("Tool folder missing its README", delete("clean_album_folders/README.md"),
     "folder-files", "clean_album_folders/: no README.md", False, 1),
    ("Version drift is a warning, not a failure",
     replace_once("sort_by_artist/sort_by_artist.py", "v1.3", "v9.9"),
     "version-drift", "sort_by_artist/sort_by_artist.py", False, 0),
]

# Real defects that commit 227df61^ contained (check id, text the finding must mention).
HISTORICAL = [
    ("nul", "anjuna_mb_lookup/mb_tagger.py"),
    ("compile", "anjuna_mb_lookup/mb_tagger.py"),
    ("imports", "gui.main_window"),
    ("run-calls", "gui/music_integrity_panel.py"),
]


def finding_texts(res: dict, cid: str) -> list[str]:
    return [msg for _, msg in res["checks"][cid]["findings"]]


def main() -> int:
    argv = sys.argv[1:]
    rev = next((argv[i + 1] for i, a in enumerate(argv) if a == "--rev" and i + 1 < len(argv)), "227df61^")
    keep = "--keep" in argv
    work = Path(tempfile.mkdtemp(prefix="check_conventions_selftest_"))
    print(f"Self-test for check_conventions.py — temp folder: {work}")
    problems = []

    def expect(ok: bool, label: str, detail: str = ""):
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}{'' if ok else '  -> ' + detail}")
        if not ok:
            problems.append(label)

    try:
        # 1. Baseline
        clean = work / "clean"
        copy_live(clean)
        live_allow = ROOT / "tools" / "conventions_allowlist.json"
        base = cc.run_check_conventions(clean, live_allow, imports=True)
        entries = cc.load_allowlist(live_allow)
        for cid, r in base["checks"].items():
            for key, _ in r["findings"]:
                entries.append({"check": cid, "key": key, "reason": "selftest baseline"})
        baseline = work / "baseline_allowlist.json"
        baseline.write_text(json.dumps({"entries": entries}, indent=1), encoding="utf-8")
        print(f"\n1. Baseline: {sum(len(r['findings']) for r in base['checks'].values())} existing finding(s) "
              f"recorded so only new problems count")
        code, out = run_cli(clean, baseline, imports=True)
        expect(code == 0, "Clean copy exits 0", f"exit {code}\n{out}")

        # 2. Injected defects
        print("\n2. Injected defects (one per fresh copy)")
        for i, (name, mutate, cid, needle, imports, want) in enumerate(CASES):
            case = work / f"case{i:02d}"
            shutil.copytree(clean, case)
            mutate(case)
            git(case, "add", "-A")
            code, out = run_cli(case, baseline, imports)
            res = cc.run_check_conventions(case, baseline, imports=imports)
            hit = any(needle in m for m in finding_texts(res, cid))
            expect(code == want and hit, f"{name}: exit {want}, reported by '{cid}'",
                   f"exit {code}, {cid} findings: {finding_texts(res, cid)}")
            if code == want and hit:
                remove_temp(case)

        # Not a git repository at all
        plain = work / "not_a_repo"
        plain.mkdir()
        code, out = run_cli(plain, baseline, imports=False)
        expect(code == 1 and "could not run" in out, "Folder that isn't a git repo: exit 1 with an error",
               f"exit {code}: {out.strip()[:200]}")

        # 3. Historical broken commit
        print(f"\n3. Real broken commit {rev}")
        hist = work / "historical"
        export_rev(rev, hist)
        code, out = run_cli(hist, baseline, imports=True)
        expect(code == 1, f"{rev} exits 1", f"exit {code}")
        res = cc.run_check_conventions(hist, baseline, imports=True)
        for cid, needle in HISTORICAL:
            texts = finding_texts(res, cid)
            expect(any(needle in m for m in texts), f"{rev}: '{cid}' reports {needle}", f"findings: {texts}")
        print("\n   What the check reported on the broken commit:")
        for cid in res["failed"]:
            for m in finding_texts(res, cid):
                print(f"     {cid}: {m}")
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
    print("SELF-TEST: PASS — every injected and historical defect was caught; the clean copy passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
