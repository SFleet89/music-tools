"""
Rename Undo  v1.0
==================
Reverses folder renames made by rename_to_catno.py using its CSV report.

Reads the report and, for each row with status 'renamed', moves the folder
back to its original name. Does not touch any file tags.

Usage:
    python rename_undo.py                       # opens file picker
    python rename_undo.py "C:\\path\\to\\report.csv"
    python rename_undo.py "C:\\path\\to\\report.csv" --apply

Changes in v1.0:
    - Initial release.
"""

import sys
import csv
import shutil
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent


def pick_file():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askopenfilename(
            title="Select rename_to_catno report CSV",
            initialdir=str(SCRIPT_DIR.parent / "reports"),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        root.destroy()
        return chosen or None
    except Exception as e:
        print("ERROR: Could not open file picker: %s" % e)
        return None


def main():
    args       = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags      = [a for a in sys.argv[1:] if a.startswith("--")]
    apply_mode = "--apply" in flags

    if args:
        csv_path = Path(args[0].strip('"'))
    else:
        chosen = pick_file()
        if not chosen:
            print("No file selected. Exiting.")
            sys.exit(0)
        csv_path = Path(chosen)

    if not csv_path.exists():
        print("ERROR: File not found: %s" % csv_path)
        sys.exit(1)

    # Read the report
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    candidates = [r for r in rows if r.get("status") == "renamed"]

    print()
    print("=" * 60)
    print("  Rename Undo  v1.0")
    print("=" * 60)
    print("  Report : %s" % csv_path.name)
    print("  Mode   : %s" % ("APPLY — undoing renames" if apply_mode
                              else "DRY RUN — no changes made"))
    print("  Rows to undo: %d of %d total" % (len(candidates), len(rows)))
    print("=" * 60)

    if not candidates:
        print("\n  Nothing to undo (no rows with status 'renamed').")
        sys.exit(0)

    # Build undo plan
    plan   = []
    issues = []

    for r in candidates:
        folder_path   = Path(r["folder_path"])
        original_name = r.get("original_name", "")

        if not original_name:
            issues.append("  ! Missing original_name for: %s" % folder_path.name)
            continue

        if not folder_path.exists():
            issues.append("  ! Renamed folder no longer exists: %s" % folder_path)
            continue

        dest = folder_path.parent / original_name

        if dest.exists():
            issues.append("  ! Original path already exists, cannot undo: %s" % dest)
            continue

        plan.append((folder_path, dest, original_name))

    if issues:
        print()
        for msg in issues:
            print(msg)

    print()
    for src, dst, orig in plan:
        print("  %s" % src.name)
        print("  → %s" % orig)
        print()

    if not plan:
        print("  Nothing to undo after validation.")
        sys.exit(0)

    if not apply_mode:
        print("  %d rename(s) would be undone. Add --apply to execute." % len(plan))
        sys.exit(0)

    confirm = input("  Proceed with undoing %d rename(s)? (y/n): " % len(plan)).strip().lower()
    if confirm != "y":
        print("  Aborted.")
        sys.exit(0)

    # Write undo report
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports_dir = SCRIPT_DIR.parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    out_path    = reports_dir / ("rename_undo_%s.csv" % timestamp)

    out_rows = []
    moved = errors = 0

    for src, dst, orig in plan:
        try:
            shutil.move(str(src), str(dst))
            print("  ✓  %s" % orig)
            out_rows.append({"original_path": str(src), "restored_name": orig,
                             "status": "undone", "notes": "OK"})
            moved += 1
        except Exception as e:
            print("  !  Error restoring %s: %s" % (src.name, e))
            out_rows.append({"original_path": str(src), "restored_name": orig,
                             "status": "error", "notes": str(e)})
            errors += 1

    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["original_path", "restored_name",
                                               "status", "notes"])
        writer.writeheader()
        writer.writerows(out_rows)

    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print("  Undone : %d" % moved)
    if errors:
        print("  Errors : %d" % errors)
    print()
    print("  Report saved to:")
    print("  %s" % out_path)
    print("=" * 60)


if __name__ == "__main__":
    main()
