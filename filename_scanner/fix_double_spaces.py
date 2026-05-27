"""
Music Filename Double Space Fixer  v2.2
========================================
Finds music files with double spaces in their filenames and renames them,
collapsing all consecutive spaces down to a single space.

Two sub-types are fixed:
  "01  Title.mp3"         → "01 Title.mp3"    (double space after track number)
  "Title  Subtitle.mp3"   → "Title Subtitle.mp3" (double space mid-title)

Usage:
    python fix_double_spaces.py --pick               # pick folder via dialog (dry run)
    python fix_double_spaces.py --pick --apply       # pick folder and rename
    python fix_double_spaces.py --path "C:\\Music"   # specify folder directly
    python fix_double_spaces.py --path "C:\\Music" --apply

If neither --pick nor --path is given the script reads the 'organized' folder
from music_config.json at the project root.  If the config is also missing it
exits with an error.

Requirements:
    pip install mutagen
"""

import sys
import re
import csv
import shutil
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import (
    pick_folder, config_organized_folder, interactive_options,
)

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".aac", ".m4a"}

SCRIPT_DIR     = Path(__file__).parent
REPORTS_FOLDER = SCRIPT_DIR / "reports"


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def fix_stem(stem: str) -> str:
    """Collapse all runs of 2+ spaces into a single space."""
    return re.sub(r"  +", " ", stem).strip()


def needs_fix(filename: str) -> bool:
    return "  " in Path(filename).stem


def get_new_name(filename: str) -> str:
    p = Path(filename)
    return fix_stem(p.stem) + p.suffix


def scan_for_doubles(root: Path) -> list:
    """Find all music files with double spaces. Returns list of candidate dicts."""
    candidates = []
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            if needs_fix(f.name):
                new_name = get_new_name(f.name)
                candidates.append({
                    "folder":   f.parent,
                    "old_name": f.name,
                    "new_name": new_name,
                    "old_path": f,
                    "new_path": f.parent / new_name,
                    "status":   "would rename",
                })
    return candidates


def write_report(candidates: list, root: Path, report_path: Path, dry_run: bool) -> None:
    fieldnames = ["Folder", "Original Filename", "New Filename", "Status"]
    rows = []
    for c in candidates:
        folder = str(c["folder"].relative_to(root)) if c["folder"] != root else "."
        rows.append({
            "Folder":            folder,
            "Original Filename": c["old_name"],
            "New Filename":      c["new_name"],
            "Status":            c.get("status", "would rename" if dry_run else "renamed"),
        })
    with open(report_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_fix_double_spaces(
    folder: Path,
    apply: bool = False,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Find and fix double-space filenames under folder.

    Args:
        folder:            Root folder to scan recursively.
        apply:             False = dry run; True = rename files.
        progress_callback: Optional callable(current, total, message).
        log_callback:      Optional callable(message). Defaults to print().

    Returns:
        dict: renamed, skipped, errors, results (list of candidate dicts),
              report_path (Path|None)

    Raises:
        ValueError: folder does not exist or is not a directory.
    """
    log = log_callback or print

    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    candidates = scan_for_doubles(folder)

    if not candidates:
        log("  No files with double spaces found.")
        return {"renamed": 0, "skipped": 0, "errors": 0,
                "results": [], "report_path": None}

    log(f"  Found {len(candidates)} file(s) with double spaces.")

    if not apply:
        REPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = REPORTS_FOLDER / f"fix_double_spaces_dry_{ts}.csv"
        write_report(candidates, folder, report_path, dry_run=True)
        log(f"  Report saved: {report_path}")
        return {"renamed": 0, "skipped": 0, "errors": 0,
                "results": candidates, "report_path": report_path}

    # ── Rename ─────────────────────────────────────────────────────────────────
    renamed = skipped = errors = 0

    for i, c in enumerate(candidates):
        if progress_callback:
            progress_callback(i + 1, len(candidates), c["old_name"])
        if c["new_path"].exists():
            log(f"  [SKIP] Target already exists: {c['new_name']}")
            c["status"] = "skipped — collision"
            skipped += 1
            continue
        try:
            shutil.move(str(c["old_path"]), str(c["new_path"]))
            c["status"] = "renamed"
            renamed += 1
        except Exception as e:
            log(f"  [ERROR] {c['old_name']}: {e}")
            c["status"] = f"error: {e}"
            errors += 1

    log(f"  Renamed: {renamed}  |  Skipped: {skipped}  |  Errors: {errors}")

    REPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_FOLDER / f"fix_double_spaces_applied_{ts}.csv"
    write_report(candidates, folder, report_path, dry_run=False)
    log(f"  Report saved: {report_path}")

    return {"renamed": renamed, "skipped": skipped, "errors": errors,
            "results": candidates, "report_path": report_path}


# ══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT  ← .cmd launchers call this; GUI does not
# ══════════════════════════════════════════════════════════════════════════════

def main():
    interactive_options([])

    dry_run  = "--apply" not in sys.argv
    _path_flag = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--path" and i + 1 < len(sys.argv)), None,
    )

    if _path_flag:
        folder = Path(_path_flag.strip('"'))
    elif "--pick" in sys.argv:
        folder = pick_folder("Select your music library folder")
        if not folder:
            print("No folder selected. Exiting.")
            sys.exit(0)
    else:
        folder = config_organized_folder()
        if not folder:
            print("ERROR: No folder specified. Use --pick or --path.")
            sys.exit(1)

    mode = "DRY RUN — no files will be renamed" if dry_run else "LIVE — files will be renamed"
    print(f"\n{'='*60}")
    print(f"Music Filename Double Space Fixer  v2.2")
    print(f"{'='*60}")
    print(f"  Mode   : {mode}")
    print(f"  Folder : {folder}")
    print(f"{'='*60}\n")

    try:
        result = run_fix_double_spaces(folder, apply=False)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    if not result["results"]:
        return

    for c in result["results"]:
        rel = str(c["folder"].relative_to(folder)) if c["folder"] != folder else "."
        print(f"  [{rel}]")
        print(f"    Before: {c['old_name']}")
        print(f"    After : {c['new_name']}\n")

    if dry_run:
        print("  Dry run complete. Run with --apply to rename.\n")
        return

    confirm = input(f"  Rename {len(result['results'])} file(s)? (y/n): ").strip().lower()
    while confirm not in ("y", "n"):
        confirm = input("  Please enter y or n: ").strip().lower()
    if confirm != "y":
        print("  Aborted.\n")
        return

    try:
        run_fix_double_spaces(folder, apply=True)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
