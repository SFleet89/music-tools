"""
Move From Report  v1.2
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
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import load_csv
from music_tools_common import interactive_options

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
            initialdir=str(Path(__file__).parent.parent / "reports"),
        )
        root.destroy()
        return path or None
    except Exception as e:
        print("ERROR: Could not open file picker: %s" % e)
        return None



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



# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_move_from_report(
    csv_path,
    apply: bool = False,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Move folders from a lookup report CSV based on their status.

    review → <parent>/To Review/<folder>
    not_found / no_catno → <parent>/No Match/<folder>

    Args:
        csv_path:          Path to lookup CSV.
        apply:             False = dry run; True = move folders.
        progress_callback: Optional callable(current, total, message).
        log_callback:      Optional callable(message). Defaults to print().

    Returns:
        dict: moved, skipped_missing, would_move, errors

    Raises:
        ValueError: csv_path does not exist or is not a .csv file.
    """
    log      = log_callback or print
    csv_path = Path(csv_path)

    if not csv_path.exists():
        raise ValueError(f"CSV not found: {csv_path}")
    if csv_path.suffix.lower() != ".csv":
        raise ValueError(f"Expected a .csv file, got: {csv_path.name}")

    rows = load_csv(csv_path)

    moves           = []
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

    log(f"  Loaded {len(rows)} rows.")
    if skipped_missing:
        log(f"  Skipped — folder not found ({len(skipped_missing)})")

    if not moves:
        log("  No folders to move.")
        return {"moved": 0, "would_move": 0, "skipped_missing": len(skipped_missing), "errors": 0}

    log(f"  To Review : {sum(1 for _,_,_,l in moves if l == 'To Review')}")
    log(f"  No Match  : {sum(1 for _,_,_,l in moves if l == 'No Match')}")

    if not apply:
        return {"moved": 0, "would_move": len(moves), "skipped_missing": len(skipped_missing), "errors": 0}

    moved = errors = 0
    total = len(moves)
    seen_dirs = set()
    for idx, (src, dst, dest_dir, label) in enumerate(moves, 1):
        if progress_callback:
            progress_callback(idx, total, src.name)
        if dest_dir not in seen_dirs:
            dest_dir.mkdir(exist_ok=True)
            seen_dirs.add(dest_dir)
        try:
            shutil.move(str(src), str(dst))
            moved += 1
        except Exception as e:
            log(f"  ! Error moving {src.name}: {e}")
            errors += 1

    return {"moved": moved, "would_move": 0, "skipped_missing": len(skipped_missing), "errors": errors}


def main():
    interactive_options([])
    _args  = [a for a in sys.argv[1:] if not a.startswith("--")]
    _flags = [a for a in sys.argv[1:] if a.startswith("--")]
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
    print("  Move From Report  v1.1")
    print("=" * 60)
    print("  Report : %s" % csv_path.name)
    print("  Mode   : %s" % ("apply" if apply_mode else "dry run"))
    print("=" * 60)

    rows = load_csv(csv_path)
    print("  Loaded %d rows." % len(rows))

    move_flagged_folders(rows, apply_mode)


if __name__ == "__main__":
    main()
