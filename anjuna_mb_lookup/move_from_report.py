"""
Move From Report  v1.0
Reads an existing mb_lookup / tiesto_lookup / anjuna_mb_lookup CSV report
and moves folders based on their status — without re-running the lookup.

  status = review              → <parent>/To Review/<folder>
  status = not_found|no_catno → <parent>/No Match/<folder>
  status = error               → skipped (likely a network blip)

Dry run by default. Add --apply to execute moves.

Usage:
    python move_from_report.py                          # file picker
    python move_from_report.py "path\\to\\report.csv"
    python move_from_report.py "path\\to\\report.csv" --apply
"""

import sys
import csv
import shutil
from pathlib import Path

# ── Flags ──────────────────────────────────────────────────────────────────────
_args  = [a for a in sys.argv[1:] if not a.startswith("--")]
_flags = [a for a in sys.argv[1:] if a.startswith("--")]

DEST_MAP = {
    "review":    "To Review",
    "not_found": "No Match",
    "no_catno":  "No Match",
}


def pick_csv():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="Select a lookup report CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\tools\reports",
        )
        root.destroy()
        return path or None
    except Exception as e:
        print("ERROR: Could not open file picker: %s" % e)
        return None


def load_csv(csv_path):
    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def move_flagged_folders(rows, apply_mode):
    moves = []
    skipped_missing = []

    for row in rows:
        dest_name = DEST_MAP.get(row.get("status", ""))
        if not dest_name:
            continue
        src = Path(row.get("folder_path", ""))
        if not src.exists():
            skipped_missing.append(src)
            continue
        dest_dir = src.parent / dest_name
        moves.append((src, dest_dir / src.name, dest_dir, dest_name))

    print()
    print("=" * 60)
    print("  MOVE FROM REPORT  (%s)" % ("APPLY" if apply_mode else "DRY RUN"))
    print("=" * 60)

    if skipped_missing:
        print()
        print("  Skipped — folder no longer at original path (%d):" % len(skipped_missing))
        for p in skipped_missing:
            print("    %s" % p.name)

    if not moves:
        print()
        print("  No folders to move.")
        print("=" * 60)
        return

    review_count  = sum(1 for _, _, _, l in moves if l == "To Review")
    nomatch_count = sum(1 for _, _, _, l in moves if l == "No Match")
    print()
    print("  To Review  : %d folder(s)" % review_count)
    print("  No Match   : %d folder(s)" % nomatch_count)
    print()

    for src, dst, dest_dir, label in moves:
        print("  [%-10s]  %s" % (label, src.name))

    if not apply_mode:
        print()
        print("  %d folder(s) would be moved. Add --apply to execute." % len(moves))
        print("=" * 60)
        return

    # Confirm before executing
    print()
    confirm = input("  Proceed with moving %d folder(s)? [y/N]: " % len(moves)).strip().lower()
    if confirm != "y":
        print("  Aborted.")
        print("=" * 60)
        return

    moved = errors = 0
    seen_dirs = set()
    for src, dst, dest_dir, label in moves:
        if dest_dir not in seen_dirs:
            dest_dir.mkdir(exist_ok=True)
            seen_dirs.add(dest_dir)
        try:
            shutil.move(str(src), str(dst))
            moved += 1
        except Exception as e:
            print("  ! Error moving %s: %s" % (src.name, e))
            errors += 1

    print()
    print("  Moved : %d" % moved)
    if errors:
        print("  Errors: %d" % errors)
    print("=" * 60)


def main():
    apply_mode = "--apply" in _flags

    if _args:
        csv_path = Path(_args[0].strip('"'))
    else:
        chosen = pick_csv()
        if not chosen:
            print("No file selected. Exiting.")
            sys.exit(0)
        csv_path = Path(chosen)

    if not csv_path.exists():
        print("ERROR: File not found: %s" % csv_path)
        sys.exit(1)
    if csv_path.suffix.lower() != ".csv":
        print("ERROR: Expected a .csv file, got: %s" % csv_path.name)
        sys.exit(1)

    print()
    print("=" * 60)
    print("  Move From Report  v1.0")
    print("=" * 60)
    print("  Report : %s" % csv_path.name)
    print("  Mode   : %s" % ("apply" if apply_mode else "dry run"))
    print("=" * 60)

    rows = load_csv(csv_path)
    print("  Loaded %d rows." % len(rows))

    move_flagged_folders(rows, apply_mode)


if __name__ == "__main__":
    main()
