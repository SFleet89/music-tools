"""
Music Filename Double Space Fixer  v1.0
========================================
Finds music files with double spaces in their filenames and renames them,
collapsing all consecutive spaces down to a single space.

Two sub-types are fixed:
  "01  Title.mp3"         → "01 Title.mp3"    (double space after track number)
  "Title  Subtitle.mp3"   → "Title Subtitle.mp3" (double space mid-title)

Usage:
    python fix_double_spaces.py                      # dry run (default — safe)
    python fix_double_spaces.py --apply              # actually rename files
    python fix_double_spaces.py --path "C:\\Music"   # specify folder
    python fix_double_spaces.py --apply --path "C:\\Music"
"""

import sys
import re
import csv
from pathlib import Path
from datetime import datetime

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".aac", ".m4a"}

# ── Paths ──────────────────────────────────────────────────────────────────────
DEFAULT_FOLDER  = r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\SD\Music"
REPORTS_FOLDER  = r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\tools\filename_scanner\reports"

# ── Parse flags ────────────────────────────────────────────────────────────────
DRY_RUN = "--apply" not in sys.argv  # dry run unless --apply is passed

_path_flag = next(
    (sys.argv[i + 1] for i, a in enumerate(sys.argv)
     if a == "--path" and i + 1 < len(sys.argv)),
    None,
)


def fix_stem(stem: str) -> str:
    """Collapse all runs of 2+ spaces into a single space."""
    return re.sub(r"  +", " ", stem).strip()


def needs_fix(filename: str) -> bool:
    return "  " in Path(filename).stem


def get_new_name(filename: str) -> str:
    p = Path(filename)
    new_stem = fix_stem(p.stem)
    return new_stem + p.suffix


def scan_for_doubles(root: Path) -> list[dict]:
    """Find all music files with double spaces, return list of rename candidates."""
    candidates = []
    music_files = sorted(
        f for f in root.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    for f in music_files:
        if needs_fix(f.name):
            new_name = get_new_name(f.name)
            candidates.append({
                "folder":    f.parent,
                "old_name":  f.name,
                "new_name":  new_name,
                "old_path":  f,
                "new_path":  f.parent / new_name,
            })
    return candidates


def write_report(candidates: list[dict], root: Path, report_path: str, dry_run: bool):
    fieldnames = ["Folder", "Original Filename", "New Filename", "Status"]
    rows = []
    for c in candidates:
        folder = str(c["folder"].relative_to(root)) if c["folder"] != root else "."
        rows.append({
            "Folder":            folder,
            "Original Filename": c["old_name"],
            "New Filename":      c["new_name"],
            "Status":            "Would rename" if dry_run else c.get("status", "Renamed"),
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

    mode = "DRY RUN — no files will be renamed" if DRY_RUN else "LIVE — files will be renamed"
    print(f"\n{'=' * 60}")
    print(f"Music Filename Double Space Fixer")
    print(f"{'=' * 60}")
    print(f"  Mode   : {mode}")
    print(f"  Folder : {root}")
    print(f"{'=' * 60}\n")

    candidates = scan_for_doubles(root)

    if not candidates:
        print("  No files with double spaces found.\n")
        sys.exit(0)

    print(f"  Found {len(candidates)} file(s) with double spaces:\n")
    for c in candidates:
        folder = str(c["folder"].relative_to(root)) if c["folder"] != root else "."
        print(f"  [{folder}]")
        print(f"    Before: {c['old_name']}")
        print(f"    After : {c['new_name']}\n")

    if DRY_RUN:
        print(f"  Dry run complete. Run with --apply to rename.\n")
    else:
        confirm = input(f"  Rename {len(candidates)} file(s)? (y/n): ").strip().lower()
        while confirm not in ("y", "n"):
            confirm = input("  Please enter y or n: ").strip().lower()
        if confirm != "y":
            print("  Aborted.\n")
            sys.exit(0)

        renamed = 0
        errors  = 0
        for c in candidates:
            # Check for collision — don't overwrite an existing file
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
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        suffix    = "dry" if DRY_RUN else "applied"
        report_path = str(reports_dir / f"fix_double_spaces_{suffix}_{timestamp}.csv")
        write_report(candidates, root, report_path, DRY_RUN)
        print(f"  Report saved: {report_path}\n")
    except Exception as e:
        print(f"  WARNING: Could not write report: {e}\n")
