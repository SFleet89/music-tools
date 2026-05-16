"""
Tagger Undo  v1.0
==================
Reverses folder renames made by anjuna_tagger.py or mb_tagger.py.

Reads a tagger report CSV and, for each row with status "tagged" or "partial",
moves the renamed folder (new_folder) back to the original folder name
(derived from the original folder_path).

Does NOT undo tag writes — file tags are left as-is. This only reverses
the folder rename.

Usage:
    python tagger_undo.py                              # opens file picker, dry run
    python tagger_undo.py --apply                      # opens file picker, undo for real
    python tagger_undo.py "path\\to\\report.csv"       # dry run with specific CSV
    python tagger_undo.py "path\\to\\report.csv" --apply

Output:
    Reports saved to: <tools folder>\\reports\\tagger_undo_YYYYMMDD_HHMMSS.csv
"""

import sys
import csv
import shutil
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent

APPLY   = "--apply" in sys.argv
DRY_RUN = not APPLY


# ── CSV loading ────────────────────────────────────────────────────────────────

def load_csv(csv_path):
    with open(csv_path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def filter_undoable(rows):
    """Rows where a rename actually happened: status tagged/partial AND new_folder differs from original."""
    result = []
    for r in rows:
        status      = r.get("status", "").strip()
        folder_path = r.get("folder_path", "").strip()
        new_folder  = r.get("new_folder", "").strip()
        if status not in ("tagged", "partial"):
            continue
        if not folder_path or not new_folder:
            continue
        original_name = Path(folder_path).name
        if original_name == new_folder:
            continue   # folder was not renamed — nothing to undo
        result.append(r)
    return result


# ── Processing ─────────────────────────────────────────────────────────────────

def process_row(row, dry_run):
    folder_path   = Path(row["folder_path"].strip())
    new_folder    = row["new_folder"].strip()
    original_name = folder_path.name
    parent        = folder_path.parent

    current_path  = parent / new_folder    # where the folder is now
    original_path = parent / original_name # where it should go back to

    result = {
        "original_folder": original_name,
        "tagged_folder":   new_folder,
        "folder_path":     str(folder_path),
        "status":          "",
        "notes":           "",
    }

    if not current_path.exists():
        result["status"] = "error"
        result["notes"]  = "Renamed folder not found: %s" % current_path
        return result

    if original_path.exists() and original_path != current_path:
        result["status"] = "error"
        result["notes"]  = "Original folder path already exists — cannot restore: %s" % original_path
        return result

    if dry_run:
        result["status"] = "would_undo"
        result["notes"]  = "%s → %s" % (new_folder, original_name)
        return result

    try:
        shutil.move(str(current_path), str(original_path))
        result["status"] = "undone"
        result["notes"]  = "%s → %s" % (new_folder, original_name)
    except Exception as e:
        result["status"] = "error"
        result["notes"]  = "Move failed: %s" % e

    return result


# ── Report ─────────────────────────────────────────────────────────────────────

FIELDNAMES = ["original_folder", "tagged_folder", "folder_path", "status", "notes"]

def write_report(results, output_path):
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)


def print_summary(results, dry_run, output_path):
    from collections import Counter
    counts = Counter(r["status"] for r in results)
    print()
    print("=" * 60)
    print("  SUMMARY%s" % (" [DRY RUN]" if dry_run else ""))
    print("=" * 60)
    if dry_run:
        print("  Would undo : %d" % counts.get("would_undo", 0))
    else:
        print("  Undone     : %d" % counts.get("undone", 0))
    print("  Errors     : %d" % counts.get("error", 0))
    print()
    print("  Report saved to:")
    print("  %s" % output_path)
    print("=" * 60)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    reports_dir = SCRIPT_DIR.parent / "reports"

    if not args:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            chosen = filedialog.askopenfilename(
                title="Select tagger report CSV to undo",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialdir=str(reports_dir),
            )
            root.destroy()
            if not chosen:
                print("No file selected. Exiting.")
                sys.exit(0)
            csv_path = Path(chosen)
        except Exception as e:
            print("ERROR: Could not open file picker: %s" % e)
            print("Usage: python tagger_undo.py [path_to_report.csv] [--apply]")
            sys.exit(1)
    else:
        csv_path = Path(args[0].strip('"'))

    if not csv_path.exists():
        print("ERROR: CSV not found: %s" % csv_path)
        sys.exit(1)

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports_dir.mkdir(exist_ok=True)
    suffix      = "_dry" if DRY_RUN else "_applied"
    output_path = reports_dir / ("tagger_undo%s_%s.csv" % (suffix, timestamp))

    print()
    print("=" * 60)
    print("  Tagger Undo  v1.0")
    print("=" * 60)
    print("  CSV    : %s" % csv_path)
    print("  Mode   : %s" % ("DRY RUN — nothing will be changed" if DRY_RUN else "LIVE — folders will be renamed back"))
    print("  Output : %s" % output_path)
    print("=" * 60)

    all_rows  = load_csv(str(csv_path))
    undoable  = filter_undoable(all_rows)
    skipped   = len(all_rows) - len(undoable)

    print()
    print("  Total rows in CSV        : %d" % len(all_rows))
    print("  Rows with folder renames : %d" % len(undoable))
    print("  Rows skipped (no rename) : %d" % skipped)
    print()

    if not undoable:
        print("  Nothing to undo.")
        return

    if not DRY_RUN:
        confirm = input("  Undo %d folder rename(s)? (y/n): " % len(undoable)).strip().lower()
        while confirm not in ("y", "n"):
            confirm = input("  Please enter y or n: ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            return
        print()

    results = []
    for idx, row in enumerate(undoable, 1):
        new_folder    = row.get("new_folder", "")
        original_name = Path(row.get("folder_path", "")).name
        print("  [%d/%d]  %s" % (idx, len(undoable), new_folder))
        result = process_row(row, DRY_RUN)
        sym = {"undone": "✓", "would_undo": "~", "error": "✗"}.get(result["status"], "?")
        print("          %s %s" % (sym, result["notes"]))
        results.append(result)

    write_report(results, str(output_path))
    print_summary(results, DRY_RUN, str(output_path))


if __name__ == "__main__":
    main()
