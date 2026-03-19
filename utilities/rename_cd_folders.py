"""
CD Folder Renamer  v1.0
========================
Finds folders named "CD #" (with a space) and renames them to "CD#" (no space).

Examples:
    CD 1  →  CD1
    CD 2  →  CD2
    CD 10 →  CD10

Usage:
    python rename_cd_folders.py                      # dry run (default — safe)
    python rename_cd_folders.py --apply              # actually rename
    python rename_cd_folders.py --path "C:\\Music"   # specify root folder
    python rename_cd_folders.py --apply --path "C:\\Music"
"""

import sys
import re
import csv
from pathlib import Path
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────────────
DEFAULT_FOLDER  = r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\SD\Music"
REPORTS_FOLDER  = r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\tools\filename_scanner\reports"

# ── Parse flags ────────────────────────────────────────────────────────────────
DRY_RUN = "--apply" not in sys.argv

_path_flag = next(
    (sys.argv[i + 1] for i, a in enumerate(sys.argv)
     if a == "--path" and i + 1 < len(sys.argv)),
    None,
)

CD_PATTERN = re.compile(r'^(.*\bCD) (\d+)(.*)$', re.IGNORECASE)


def find_cd_folders(root: Path) -> list[dict]:
    """Find all folders matching 'CD #' pattern under root."""
    candidates = []
    for folder in sorted(root.rglob("*")):
        if not folder.is_dir():
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


def write_report(candidates: list[dict], root: Path, report_path: str, dry_run: bool):
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
    with open(report_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    folder_str = _path_flag or DEFAULT_FOLDER
    root = Path(folder_str.strip('"'))
    reports_dir = Path(REPORTS_FOLDER)

    if not root.exists() or not root.is_dir():
        print(f"ERROR: Folder not found: {root}")
        sys.exit(1)

    mode = "DRY RUN — no folders will be renamed" if DRY_RUN else "LIVE — folders will be renamed"
    print(f"\n{'=' * 60}")
    print(f"CD Folder Renamer")
    print(f"{'=' * 60}")
    print(f"  Mode   : {mode}")
    print(f"  Folder : {root}")
    print(f"{'=' * 60}\n")

    candidates = find_cd_folders(root)

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
    else:
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
                c["old_path"].rename(c["new_path"])
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

    # Write report
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp   = datetime.now().strftime('%Y%m%d_%H%M%S')
        suffix      = "dry" if DRY_RUN else "applied"
        report_path = str(reports_dir / f"rename_cd_folders_{suffix}_{timestamp}.csv")
        write_report(candidates, root, report_path, DRY_RUN)
        print(f"  Report saved: {report_path}\n")
    except Exception as e:
        print(f"  WARNING: Could not write report: {e}\n")
