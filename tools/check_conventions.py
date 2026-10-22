"""
Music Tools Convention Check  v1.1

Read-only check of the project's coding conventions. It opens files only to read
them and never writes, moves or deletes anything. (The GUI import check runs in a
child Python with bytecode writing switched off, so no __pycache__ is created.)

Checks the files git tracks plus new files that are not ignored yet, so a file is
checked before it is committed. Local-only folders (docs/, qobuz_upgrade_finder/,
...) are gitignored and therefore never scanned.

Usage:
    python -X utf8 tools/check_conventions.py                # check this project
    python -X utf8 tools/check_conventions.py --path "D:\\copy\\of\\repo"
    python -X utf8 tools/check_conventions.py --no-imports   # skip the GUI import check
    python -X utf8 tools/check_conventions.py --verbose      # also list allowlisted items
    python -X utf8 tools/check_conventions.py --allowlist "<file.json>"

Exit code: 0 = no failures (warnings allowed), 1 = at least one failure, or the
check itself could not run.

Known problems that are accepted for now live in tools/conventions_allowlist.json.
Each entry names a check, a finding key and a reason. An entry that no longer
matches anything is reported as a warning so the list stays tidy.

Returns (run_check_conventions): root / files / checks / failed / warned /
allowlisted / stale_allowlist / exit_code
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

VERSION = "1.1"

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = SCRIPT_DIR.parent

TEXT_EXTS = {
    ".py", ".cmd", ".bat", ".md", ".txt", ".html", ".htm", ".json", ".spec",
    ".css", ".js", ".csv", ".ini", ".cfg", ".toml", ".yml", ".yaml",
    ".gitignore", ".gitattributes",
}
# Folders whose .py files are not tool scripts (no README/CHANGELOG/.cmd rules,
# no version or module-level argv rules).
NON_TOOL_DIRS = {"gui", "diagnostics"}
PRIVATE_NAMES = {"music_config.json", "library_dupes_config.json", "music_cache.json",
                 "music_fp_cache.json", "music_resume.json"}
PRIVATE_EXTS = {".db", ".sqlite", ".sqlite3", ".exe", ".rar", ".zip", ".7z"}
BIG_FILE_BYTES = 1_000_000

# id -> (severity, title, plain-English meaning)
CHECKS = {
    "compile":      ("FAIL", "Python files compile",
                     "A file that doesn't compile stops every tool or panel that imports it."),
    "nul":          ("FAIL", "No NUL bytes in text files",
                     "NUL bytes are left behind by damaged edits; Python refuses to load such a file."),
    "imports":      ("FAIL", "Every GUI module imports",
                     "If a GUI module can't be imported, the app (or that panel) won't open."),
    "run-calls":    ("FAIL", "Panels call run_*() correctly",
                     "A panel passing an argument name run_*() doesn't accept makes every scan error out."),
    "panel-wiring": ("FAIL", "Every panel is wired into the main window",
                     "A panel file that main_window.py never imports can't be opened from the app."),
    "personal-path": ("FAIL", "No personal paths in published files",
                      "Your user folder path must not appear in files that go to the public repo."),
    "private-file": ("FAIL", "No private, binary or very large files published",
                     "Config files, databases, archives, executables and files over 1 MB need a deliberate OK."),
    "viewer-offline": ("FAIL", "Report viewer works offline",
                       "viewer.html must not load anything from the internet."),
    "run-exit":     ("FAIL", "run_*() never exits or asks for input",
                     "sys.exit() or input() inside run_*() freezes or closes the GUI (PW-02)."),
    "argv-module":  ("FAIL", "Flags are read in main(), not at import time",
                     "Reading sys.argv at module level means the GUI can't control the script (PW-01)."),
    "rename":       ("FAIL", "shutil.move is used, not rename",
                     "os.rename / Path.rename fail across drives (Rule 4)."),
    "folder-files": ("FAIL", "Each tool folder has README, CHANGELOG and Dry Run + Apply launchers",
                     "Rules 7 and 8."),
    "version-drift": ("WARN", "Version numbers agree (docstring vs TASKS.md vs CHANGELOG)",
                      "Warning only for now: a mismatch means the records weren't all updated."),
    "viewer-coverage": ("WARN", "CSV-writing scripts have a report viewer config",
                        "Warning only for now: some scripts may not need one."),
}


# ── File discovery and reading ───────────────────────────────────────────────

def list_files(root: Path) -> list[str]:
    """Tracked files plus untracked files that are not ignored (forward-slash paths)."""
    try:
        res = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
        )
    except FileNotFoundError:
        raise RuntimeError("git was not found on PATH; it is needed to list the project's files.")
    if res.returncode != 0:
        msg = res.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git ls-files failed in {root}: {msg}")
    names = res.stdout.decode("utf-8", errors="replace").split("\0")
    return sorted({n for n in names if n and (root / n).is_file()})


class Repo:
    def __init__(self, root: Path):
        self.root = root
        self.files = list_files(root)
        self._bytes: dict[str, bytes] = {}
        self._trees: dict[str, ast.Module | None] = {}

    def data(self, rel: str) -> bytes:
        if rel not in self._bytes:
            self._bytes[rel] = (self.root / rel).read_bytes()
        return self._bytes[rel]

    def text(self, rel: str) -> str:
        return self.data(rel).decode("utf-8", errors="replace")

    def tree(self, rel: str) -> ast.Module | None:
        """Parsed module, or None if it doesn't parse (the compile check reports that)."""
        if rel not in self._trees:
            try:
                self._trees[rel] = ast.parse(self.data(rel), filename=rel)
            except (SyntaxError, ValueError):
                self._trees[rel] = None
        return self._trees[rel]

    @property
    def py(self) -> list[str]:
        return [f for f in self.files if f.endswith(".py")]

    def is_text(self, rel: str) -> bool:
        name = rel.rsplit("/", 1)[-1].lower()
        return Path(name).suffix in TEXT_EXTS or name in TEXT_EXTS


def top_dir(rel: str) -> str:
    return rel.split("/", 1)[0] if "/" in rel else ""


def is_tool_script(rel: str) -> bool:
    return "/" in rel and top_dir(rel) not in NON_TOOL_DIRS and rel.endswith(".py")


# Each finding: (check_id, key, message). The key is stable across edits (no line
# numbers) so the allowlist keeps matching when code moves.

# ── Checks ───────────────────────────────────────────────────────────────────

def check_compile(repo: Repo) -> list:
    out = []
    for f in repo.py:
        try:
            compile(repo.data(f), f, "exec", dont_inherit=True)
        except (SyntaxError, ValueError) as e:
            line = getattr(e, "lineno", None)
            where = f" (line {line})" if line else ""
            out.append(("compile", f, f"{f}{where}: {type(e).__name__}: {e.args[0] if e.args else e}"))
    return out


def check_nul(repo: Repo) -> list:
    out = []
    for f in repo.files:
        if repo.is_text(f):
            n = repo.data(f).count(b"\x00")
            if n:
                out.append(("nul", f, f"{f}: contains {n} NUL byte(s)"))
    return out


def check_imports(repo: Repo) -> list:
    gui = [f for f in repo.py if f.startswith("gui/") and f.count("/") == 1]
    if not gui:
        return []
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", QT_QPA_PLATFORM="offscreen",
               PYTHONIOENCODING="utf-8")
    mods = [f"gui.{Path(f).stem}" for f in gui]
    try:
        res = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", str(Path(__file__).resolve()),
             "--_import-worker", str(repo.root), *mods],
            capture_output=True, env=env, cwd=str(repo.root), timeout=300,
        )
    except subprocess.TimeoutExpired:
        return [("imports", "timeout", "GUI import check took over 5 minutes and was stopped")]
    text = res.stdout.decode("utf-8", errors="replace")
    out = []
    for line in text.splitlines():
        if line.startswith("IMPORTFAIL\t"):
            _, mod, err = line.split("\t", 2)
            out.append(("imports", mod, f"{mod}: {err}"))
    if res.returncode not in (0, 1) or ("IMPORTDONE" not in text):
        err = res.stderr.decode("utf-8", errors="replace").strip().splitlines()[-1:] or ["no output"]
        out.append(("imports", "worker", f"import check could not finish: {err[0][:200]}"))
    return out


def _import_worker(root: str, mods: list[str]) -> int:
    import importlib
    import io
    sys.path.insert(0, root)
    bad = 0
    real_stdout = sys.stdout
    for mod in mods:
        sys.stdout = io.StringIO()          # swallow prints made at import time
        try:
            importlib.import_module(mod)
        except BaseException as e:          # SystemExit too: a module must not exit on import
            bad += 1
            msg = f"{type(e).__name__}: {e}".replace("\n", " ")[:200]
            real_stdout.write(f"IMPORTFAIL\t{mod}\t{msg}\n")
        finally:
            sys.stdout = real_stdout
    real_stdout.write("IMPORTDONE\n")
    real_stdout.flush()
    return 1 if bad else 0


def _run_defs(repo: Repo) -> dict[str, dict[str, ast.FunctionDef]]:
    """Top-level run_* functions in non-GUI files: file -> {name: node}."""
    defs = {}
    for f in repo.py:
        if f.startswith("gui/"):
            continue
        t = repo.tree(f)
        if t is None:
            continue
        found = {n.name: n for n in t.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("run_")}
        if found:
            defs[f] = found
    return defs


def check_run_calls(repo: Repo) -> list:
    defs = _run_defs(repo)
    by_name: dict[str, list[str]] = {}
    for f, d in defs.items():
        for name in d:
            by_name.setdefault(name, []).append(f)
    py_set = set(repo.py)
    out = []
    for g in repo.py:
        if not g.startswith("gui/"):
            continue
        t = repo.tree(g)
        if t is None:
            continue
        # Which file each run_* name is imported from in this panel.
        source: dict[str, str] = {}
        for node in ast.walk(t):
            if isinstance(node, ast.ImportFrom) and node.module:
                for a in node.names:
                    if not a.name.startswith("run_"):
                        continue
                    local = a.asname or a.name
                    cand = node.module.replace(".", "/") + ".py"
                    if cand not in py_set:      # bare "from script import run_x" after sys.path tweak
                        tail = node.module.rsplit(".", 1)[-1] + ".py"
                        hits = [p for p in py_set if p.endswith("/" + tail) or p == tail]
                        cand = hits[0] if len(hits) == 1 else cand
                    # An unparsable source file is the compile check's finding, not this one.
                    if cand in py_set and repo.tree(cand) is not None and a.name not in defs.get(cand, {}):
                        out.append(("run-calls", f"{g}::{a.name}",
                                    f"{g}: imports {a.name} from {node.module}, which doesn't define it"))
                    source[local] = (cand, a.name)
        for node in ast.walk(t):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            local = node.func.id
            if local in source:
                cand, real = source[local]
                fn = defs.get(cand, {}).get(real)
            elif local in by_name and len(by_name[local]) == 1:
                real = local
                fn = defs[by_name[local][0]][local]
            else:
                continue
            if fn is None or fn.args.kwarg is not None:
                continue
            a = fn.args
            accepted = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
            unknown = [k.arg for k in node.keywords if k.arg and k.arg not in accepted]
            if unknown:
                out.append(("run-calls", f"{g}::{real}::{','.join(sorted(unknown))}",
                            f"{g}:{node.lineno}: {real}() is given {unknown}; it accepts {sorted(accepted)}"))
    return out


def check_panel_wiring(repo: Repo) -> list:
    mw = "gui/main_window.py"
    if mw not in repo.files:
        return []
    t = repo.tree(mw)
    if t is None:
        return []
    imported = {n.module for n in ast.walk(t) if isinstance(n, ast.ImportFrom) and n.module}
    out = []
    for f in repo.py:
        if f.startswith("gui/") and f.count("/") == 1 and f.endswith("_panel.py"):
            mod = "gui." + Path(f).stem
            if mod not in imported:
                out.append(("panel-wiring", f, f"{f}: not imported by gui/main_window.py"))
    return out


def check_personal_paths(repo: Repo) -> list:
    user = Path.home().name
    if not user:
        return [("personal-path", "no-home", "could not work out your user name; check skipped")]
    pat = re.compile(re.escape(user), re.I)
    out = []
    for f in repo.files:
        if not repo.is_text(f) or f.startswith("tools/conventions_allowlist"):
            continue
        for n, line in enumerate(repo.text(f).splitlines(), 1):
            if pat.search(line):
                snippet = pat.sub("<you>", line.strip())[:90]
                out.append(("personal-path", f"{f}::{snippet}", f"{f}:{n}: {snippet}"))
    return out


def check_private_files(repo: Repo) -> list:
    out = []
    for f in repo.files:
        name = f.rsplit("/", 1)[-1]
        size = (repo.root / f).stat().st_size
        why = []
        if name.lower() in PRIVATE_NAMES:
            why.append("personal config/cache file")
        if Path(name).suffix.lower() in PRIVATE_EXTS:
            why.append(f"{Path(name).suffix.lower()} file")
        if size > BIG_FILE_BYTES:
            why.append(f"{size / 1e6:.1f} MB")
        if why:
            out.append(("private-file", f, f"{f}: {', '.join(why)}"))
    return out


def check_viewer_offline(repo: Repo) -> list:
    v = "report_viewer/viewer.html"
    if v not in repo.files:
        return []
    pat = re.compile(r"""(?:\b(?:src|href)\s*=\s*["']|@import\s+(?:url\()?["']?|\burl\(\s*["']?|"""
                     r"""\bfetch\(\s*["'`]|import\s*\(\s*["'`])\s*(?:https?:)?//""", re.I)
    out = []
    for n, line in enumerate(repo.text(v).splitlines(), 1):
        if pat.search(line):
            out.append(("viewer-offline", f"{v}::{line.strip()[:80]}", f"{v}:{n}: {line.strip()[:100]}"))
    return out


def check_run_exit(repo: Repo) -> list:
    out = []
    for f in repo.py:
        t = repo.tree(f)
        if t is None or f.startswith("tools/"):
            continue
        for fn in ast.walk(t):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name.startswith("run_"):
                bad = sorted({ast.unparse(c.func) for c in ast.walk(fn) if isinstance(c, ast.Call)
                              and ast.unparse(c.func) in ("sys.exit", "exit", "quit", "input")})
                for b in bad:
                    lines = [c.lineno for c in ast.walk(fn) if isinstance(c, ast.Call)
                             and ast.unparse(c.func) == b]
                    out.append(("run-exit", f"{f}::{fn.name}::{b}",
                                f"{f}: {fn.name}() calls {b}() (line {', '.join(map(str, lines[:5]))})"))
    return out


def check_argv_module(repo: Repo) -> list:
    out = []
    for f in repo.py:
        if not is_tool_script(f) or f.startswith("tools/"):
            continue
        t = repo.tree(f)
        if t is None:
            continue
        hits = [n.lineno for n in t.body
                if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.If))
                and "sys.argv" in ast.unparse(n)]
        if hits:
            out.append(("argv-module", f, f"{f}: reads sys.argv at module level (line {', '.join(map(str, hits[:6]))})"))
    return out


def check_rename(repo: Repo) -> list:
    out = []
    for f in repo.py:
        t = repo.tree(f)
        if t is None:
            continue
        for fn_name, node in _calls_with_owner(t):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "rename":
                call = ast.unparse(node.func)
                out.append(("rename", f"{f}::{fn_name}::{call}", f"{f}:{node.lineno}: {call}() in {fn_name}"))
    return out


def _calls_with_owner(tree: ast.Module):
    """Yield (enclosing function name or '<module>', Call node)."""
    def visit(node, owner):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name)
            else:
                if isinstance(child, ast.Call):
                    yield_list.append((owner, child))
                visit(child, owner)
    yield_list: list = []
    visit(tree, "<module>")
    return yield_list


def check_folder_files(repo: Repo) -> list:
    dirs = sorted({f.rsplit("/", 1)[0] for f in repo.py if is_tool_script(f)})
    out = []
    for d in dirs:
        names = [f.rsplit("/", 1)[1] for f in repo.files if f.rsplit("/", 1)[0] == d]
        cmds = [n.lower() for n in names if n.lower().endswith(".cmd")]
        for req in ("README.md", "CHANGELOG.md"):
            if req not in names:
                out.append(("folder-files", f"{d}::{req}", f"{d}/: no {req}"))
        if not any("dry" in c for c in cmds):
            out.append(("folder-files", f"{d}::dry-run-cmd", f"{d}/: no Dry Run .cmd launcher"))
        if not any("apply" in c for c in cmds):
            out.append(("folder-files", f"{d}::apply-cmd", f"{d}/: no Apply .cmd launcher"))
    return out


_VER = r"(\d+\.\d+(?:\.\d+)?)"


def check_version_drift(repo: Repo) -> list:
    tasks_path = repo.root / "TASKS.md"       # local-only file; absent in a bare copy
    if not tasks_path.is_file():
        return []
    tasks = tasks_path.read_text(encoding="utf-8", errors="replace")
    out = []
    for f in repo.py:
        if not is_tool_script(f):
            continue
        t = repo.tree(f)
        doc = (ast.get_docstring(t) or "") if t else ""
        m = re.search(rf"\bv{_VER}\b", doc[:1500])
        doc_v = m.group(1) if m else None
        tm = re.search(rf"^### .*{re.escape(f)} — v{_VER}", tasks, re.M)
        t_v = tm.group(1) if tm else None
        folder = f.rsplit("/", 1)[0]
        cl_v = None
        if sum(1 for p in repo.py if p.rsplit("/", 1)[0] == folder) == 1 and f"{folder}/CHANGELOG.md" in repo.files:
            cm = re.search(rf"^##+\s*\[?v?{_VER}", repo.text(f"{folder}/CHANGELOG.md"), re.M)
            cl_v = cm.group(1) if cm else None
        if not t_v:
            out.append(("version-drift", f"{f}::no-tasks-heading", f"{f}: no '### {f} — vX.Y' heading in TASKS.md"))
            continue
        vals = {v for v in (doc_v, t_v, cl_v) if v}
        if len(vals) > 1:
            out.append(("version-drift", f"{f}::{doc_v}/{cl_v}/{t_v}",
                        f"{f}: docstring v{doc_v}, CHANGELOG v{cl_v}, TASKS.md v{t_v}"))
    return out


def viewer_file_patterns(viewer: str) -> list:
    """The filePattern of every REPORT_CONFIGS entry, as Python regexes (JS /.../i or plain string)."""
    pats = []
    for m in re.finditer(r"filePattern:\s*(?:/((?:[^/\\\n]|\\.)+)/([a-z]*)|'([^'\n]+)'|\"([^\"\n]+)\")", viewer):
        if m.group(1) is not None:
            try:
                pats.append(re.compile(m.group(1), re.I if "i" in m.group(2) else 0))
            except re.error:
                pass
        else:
            pats.append(re.compile(re.escape((m.group(3) or m.group(4)).lower()), re.I))
    return pats


def report_name_prefixes(t: ast.AST) -> set:
    """Report filename prefixes a script writes, e.g. 'anjuna_lookup_' from f"anjuna_lookup_{ts}.csv"."""
    out = set()
    for n in ast.walk(t):
        s = None
        if isinstance(n, ast.JoinedStr) and n.values and isinstance(n.values[0], ast.Constant) \
                and any(isinstance(v, ast.Constant) and ".csv" in str(v.value) for v in n.values):
            s = str(n.values[0].value)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.endswith(".csv"):
            s = n.value
        if s:
            m = re.match(r"([a-z0-9_]+?_)(?:%|\{|$|[0-9])", s, re.I)
            if m:
                out.add(m.group(1))
    return out


def check_viewer_coverage(repo: Repo) -> list:
    v = "report_viewer/viewer.html"
    if v not in repo.files:
        return []
    viewer = repo.text(v)
    pats = viewer_file_patterns(viewer)
    out = []
    for f in repo.py:
        if not is_tool_script(f) or f.startswith("tools/"):
            continue
        t = repo.tree(f)
        if t is None:
            continue
        writes = any(isinstance(c, ast.Call) and ast.unparse(c.func).split(".")[-1]
                     in ("writer", "DictWriter", "to_csv", "write_csv") for c in ast.walk(t))
        if not writes or Path(f).stem in viewer:
            continue
        # The script's own name isn't in the viewer; it may still be covered under the
        # name its reports are saved with (anjuna_mb_lookup.py writes anjuna_lookup_*.csv).
        samples = [p + "20260101_000000.csv" for p in report_name_prefixes(t)]
        if any(p.search(s) for p in pats for s in samples):
            continue
        names = ", ".join(sorted(report_name_prefixes(t))) or "none found"
        out.append(("viewer-coverage", f, f"{f}: writes CSV but no viewer.html config matches it "
                                          f"(script name '{Path(f).stem}', report prefixes: {names})"))
    return out


ALL_CHECKS = [
    check_compile, check_nul, check_imports, check_run_calls, check_panel_wiring,
    check_personal_paths, check_private_files, check_viewer_offline, check_run_exit,
    check_argv_module, check_rename, check_folder_files, check_version_drift,
    check_viewer_coverage,
]


# ── Allowlist and runner ─────────────────────────────────────────────────────

def load_allowlist(path: Path | None) -> list[dict]:
    if path is None or not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries", []) if isinstance(data, dict) else data
    for e in entries:
        if not (isinstance(e, dict) and e.get("check") in CHECKS and e.get("key") and e.get("reason")):
            raise ValueError(f"allowlist entry needs a known 'check', a 'key' and a 'reason': {e}")
    return entries


def run_check_conventions(root: Path, allowlist_path: Path | None = None,
                          imports: bool = True) -> dict:
    """Run every check. Read-only. Raises RuntimeError if git can't list the files."""
    root = Path(root).resolve()
    repo = Repo(root)
    if allowlist_path is None:
        allowlist_path = root / "tools" / "conventions_allowlist.json"
    allow = load_allowlist(allowlist_path)
    allow_keys = {(e["check"], e["key"]): e for e in allow}
    used = set()

    results = {cid: {"findings": [], "allowed": [], "skipped": False} for cid in CHECKS}
    for fn in ALL_CHECKS:
        if fn is check_imports and not imports:
            results["imports"]["skipped"] = True
            continue
        for cid, key, msg in fn(repo):
            if (cid, key) in allow_keys:
                used.add((cid, key))
                results[cid]["allowed"].append((key, msg, allow_keys[(cid, key)]["reason"]))
            else:
                results[cid]["findings"].append((key, msg))

    stale = [e for e in allow if (e["check"], e["key"]) not in used
             and not (e["check"] == "imports" and not imports)]
    failed = [c for c, r in results.items() if r["findings"] and CHECKS[c][0] == "FAIL"]
    warned = [c for c, r in results.items() if r["findings"] and CHECKS[c][0] == "WARN"]
    return {
        "root": root,
        "files": len(repo.files),
        "checks": results,
        "failed": failed,
        "warned": warned,
        "allowlisted": sum(len(r["allowed"]) for r in results.values()),
        "stale_allowlist": stale,
        "allowlist_path": allowlist_path,
        "exit_code": 1 if failed else 0,
    }


def print_report(res: dict, verbose: bool = False) -> None:
    print(f"Music Tools Convention Check v{VERSION}")
    print("Mode : READ-ONLY — nothing is changed")
    print(f"Root : {res['root']}")
    print(f"Files: {res['files']} (tracked + new, not ignored)")
    print()
    for cid, (sev, title, meaning) in CHECKS.items():
        r = res["checks"][cid]
        if r["skipped"]:
            print(f"[SKIP] {title}  (--no-imports)")
            continue
        n = len(r["findings"])
        tag = "OK  " if n == 0 else sev
        extra = f"  ({len(r['allowed'])} accepted in allowlist)" if r["allowed"] else ""
        print(f"[{tag}] {title}{'' if n == 0 else f' — {n} problem(s)'}{extra}")
        if n:
            print(f"       {meaning}")
            for _, msg in r["findings"]:
                print(f"       - {msg}")
        if verbose:
            for _, msg, reason in r["allowed"]:
                print(f"       ~ accepted: {msg}  [{reason}]")
    if res["stale_allowlist"]:
        print()
        print(f"[WARN] {len(res['stale_allowlist'])} allowlist entr(y/ies) no longer match anything "
              f"(fixed? remove from {res['allowlist_path']}):")
        for e in res["stale_allowlist"]:
            print(f"       - {e['check']}: {e['key']}")
    print()
    print(f"Accepted via allowlist: {res['allowlisted']}  ({res['allowlist_path']})")
    if res["failed"]:
        print(f"RESULT: FAIL — {len(res['failed'])} check(s) failed: {', '.join(res['failed'])}. Exit code 1.")
    else:
        w = f" with {len(res['warned'])} warning(s)" if res["warned"] else ""
        print(f"RESULT: PASS{w}. Exit code 0.")


def main() -> int:
    argv = sys.argv[1:]
    if argv[:1] == ["--_import-worker"]:
        return _import_worker(argv[1], argv[2:])

    def value(flag):
        return next((argv[i + 1] for i, a in enumerate(argv) if a == flag and i + 1 < len(argv)), None)

    root = Path(value("--path").strip('"')) if value("--path") else DEFAULT_ROOT
    allow = Path(value("--allowlist").strip('"')) if value("--allowlist") else None
    if not root.is_dir():
        print(f"ERROR: Folder not found: {root}")
        return 1
    try:
        res = run_check_conventions(root, allow, imports="--no-imports" not in argv)
    except (RuntimeError, ValueError, OSError) as e:
        print(f"ERROR: the check could not run: {e}")
        return 1
    print_report(res, verbose="--verbose" in argv)
    return res["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
