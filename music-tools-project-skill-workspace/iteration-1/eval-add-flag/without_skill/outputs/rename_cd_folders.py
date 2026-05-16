"""
CD Folder Renamer  v1.2
========================
Finds folders named "CD #" (with a space) and renames them to "CD#" (no space).

Examples:
    CD 1  →  CD1
    CD 2  →  CD2
    CD 10 →  CD10

Usage:
    python rename_cd_folders.py                      # dry run (default — safe)
    python rename_cd_folders.py --apply              # actually rename
    python rename_cd_folders.py --pick               # pick folder with a dialog
    python rename_cd_folders.py --pick --apply       # pick and rename
    python rename_cd_folders.py --path "E:\\Music"   # specify root folder
    python rename_cd_folders.py --apply --path "E:\\Music"
    python rename_cd_folders.py --depth 2            # only scan folders 2 levels below root
    python rename_cd_folders.py --apply --depth 2    # rename at exactly 2 levels below root
"""

import sys
import re
import csv
import shutil
from pathlib import Path
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR     = Path(__file__).parent
REPORTS_FOLDER = SCRIPT_DIR / "reports"

# ── Parse flags ────────────────────────────────────────────────────────────────
DRY_RUN  = "--apply" not in sys.argv
PICK_DIR = "--pick"  in sys.argv

_path_flag = next(
    (sys.argv[i + 1] for i, a in enumerate(sys.argv)
     if a == "--path" and i + 1 < len(sys.argv)),
    None,
)

_depth_flag = next(
    (sys.argv[i + 1] for i, a in enumerate(sys.argv)
     if a == "--depth" and i + 1 < len(sys.argv)),
    None,
)

if _depth_flag is not None:
    try:
        DEPTH_LIMIT = int(_depth_flag)
        if DEPTH_LIMIT < 1:
            raise ValueError
    except ValueError:
        print(f"ERROR: --depth must be a positive integer (got: {_depth_flag!r})")
        sys.exit(1)
else:
    DEPTH_LIMIT = None  # no limit — scan everything

CD_PATTERN = re.compile(r'^(.*\bCD) (\d+)(.*)$', re.IGNORECASE)


# ── Folder picker ───────────────────────────────────────────────────────────────

def pick_folder() -> Path | None:
    """Open a native folder-picker dialog and return the selected path."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print("ERROR: tkinter is not available on this system.")
        sys.exit(1)

    root_tk = tk.Tk()
    root_tk.withdraw()
    root_tk.attributes("-topmost", True)

    folder = filedialog.askdirectory(title="Select folder to scan for CD subfolders")
    root_tk.destroy()

    return Path(folder) if folder else None


# ── Scanner ─────────────────────────────────────────────────────────────────────

def find_cd_folders(root: Path, depth: int | None = None) -> list[dict]:
    """Find all folders matching 'CD #' pattern under root.

    If depth is given, only folders that are exactly `depth` levels below root
    are considered.  For example, depth=2 matches root/A/B but not root/A or
    root/A/B/C.  If depth is None every subfolder is scanned (original behaviour).
    """
    candidates = []
    root_depth = len(root.parts)

    for folder in sorted(root.rglob("*")):
        if not folder.is_dir():
            continue

        if depth is not None:
            folder_depth = len(folder.parts) - root_depth
            if folder_depth != depth:
                continue

        name = folder.name
        m = CD_PATTERN.match(name)
        if m:
            new_name = m.group(1) + m.group(2) + m.group(3)
            candidates.append({
                "parent":   folder.parent,
                "old_name": name,
                "new_name": new_name,
                "old_path": folder,
                "new_path": folder.parent / new_name,
            })
    return candidates


# ── Report ──────────────────────────────────────────────────────────────────────

def write_report(candidates: list[dict], root: Path, dry_run: bool):
    fieldnames = ["Parent Folder", "Original Name", "New Name", "Status"]
    rows = []
    for c in candidates:
        try:
            parent_rel = str(c["parent"].relative_to(root))
        except ValueError:
            parent_rel = str(c["parent"])
        rows.append({
            "Parent Folder": parent_rel,
            "Original Name": c["old_name"],
            "New Name":      c["new_name"],
            "Status":        "Would rename" if dry_run else c.get("status", "Renamed"),
        })

    try:
        REPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
        timestamp   = datetime.now().strftime('%Y%m%d_%H%M%S')
        suffix      = "dry" if dry_run else "applied"
        report_path = REPORTS_FOLDER / f"rename_cd_folders_{suffix}_{timestamp}.csv"
        with open(report_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"  Report saved: {report_path}\n")
    except Exception as e:
        print(f"  WARNING: Could not write report: {e}\n")


# ── Main ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # Determine root folder
    if PICK_DIR:
        root = pick_folder()
        if not root:
            print("\n  No folder selected. Exiting.\n")
            sys.exit(0)
    elif _path_flag:
        root = Path(_path_flag.strip('"'))
    else:
        print("ERROR: No folder specified.")
        print("       Use --pick to select a folder, or --path \"C:\\Your\\Music\" to specify one.")
        sys.exit(1)

    if not root.exists() or not root.is_dir():
        print(f"ERROR: Folder not found: {root}")
        sys.exit(1)

    mode = "DRY RUN — no folders will be renamed" if DRY_RUN else "LIVE — folders will be renamed"
    depth_label = f"depth {DEPTH_LIMIT}" if DEPTH_LIMIT is not None else "all levels"
    print(f"\n{'=' * 60}")
    print(f"CD Folder Renamer  v1.2")
    print(f"{'=' * 60}")
    print(f"  Mode   : {mode}")
    print(f"  Folder : {root}")
    print(f"  Depth  : {depth_label}")
    print(f"{'=' * 60}\n")

    candidates = find_cd_folders(root, depth=DEPTH_LIMIT)

    if not candidates:
        print("  No 'CD #' folders found.\n")
        sys.exit(0)

    print(f"  Found {len(candidates)} folder(s) to rename:\n")
    for c in candidates:
        try:
            parent_rel = str(c["parent"].relative_to(root))
        except ValueError:
            parent_rel = str(c["parent"])
        print(f"  [{parent_rel}]")
        print(f"    Before: {c['old_name']}")
        print(f"    After : {c['new_name']}\n")

    if DRY_RUN:
        print(f"  Dry run complete. Run with --apply to rename.\n")
        write_report(candidates, root, dry_run=True)
        sys.exit(0)

    # Confirmation prompt before any renaming
    confirm = input(f"  Rename {len(candidates)} folder(s)? (y/n): ").strip().lower()
    while confirm not in ("y", "n"):
        confirm = input("  Please enter y or n: ").strip().lower()
    if confirm != "y":
        print("  Aborted.\n")
        sys.exit(0)

    renamed = 0
    errors  = 0
    for c in candidates:
        if c["new_path"].exists():
            print(f"  [SKIP] Target already exists: {c['new_name']}")
            c["status"] = "Skipped — target exists"
            continue
        try:
            shutil.move(str(c["old_path"]), str(c["new_path"]))
            c["status"] = "Renamed"
            renamed += 1
        except Exception as e:
            print(f"  [ERROR] {c['old_name']}: {e}")
            c["status"] = f"Error: {e}"
            errors += 1

    print(f"\n  {'=' * 40}")
    print(f"  Renamed : {renamed}")
    print(f"  Errors  : {errors}")
    print(f"  {'=' * 40}\n")

    write_report(candidates, root, dry_run=False)
