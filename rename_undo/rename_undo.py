"""
Rename Undo  v1.4
==================
Reverses folder renames made by rename_to_catno.py using its CSV report.

Reads the report and, for each row with status 'renamed', moves the folder
back to its original name. Does not touch any file tags.

Usage:
    python rename_undo.py                       # opens file picker (dry run)
    python rename_undo.py --pick                # opens file picker (dry run)
    python rename_undo.py --pick --apply        # opens file picker and undoes
    python rename_undo.py --path "C:\\report.csv" --apply
"""

import sys
import shutil
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import write_csv, load_csv, interactive_options

SCRIPT_DIR = Path(__file__).parent

FIELDNAMES = ["original_path", "restored_name", "status", "notes"]


def pick_file():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askopenfilename(
            title="Select rename_to_catno report CSV",
            initialdir=str(SCRIPT_DIR / "reports"),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        root.destroy()
        return chosen or None
    except Exception as e:
        print("ERROR: Could not open file picker: %s" % e)
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_rename_undo(
    csv_path: Path,
    apply: bool = False,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Undo folder renames recorded in a rename_to_catno CSV report.

    Args:
        csv_path:          Path to the rename_to_catno report CSV.
        apply:             False = dry run; True = move folders back.
        progress_callback: Optional callable(current, total, message).
        log_callback:      Optional callable(message). Defaults to print().

    Returns:
        dict: undone, skipped, errors, results (list of row dicts),
              report_path (Path|None)

    Raises:
        ValueError: csv_path does not exist.
    """
    log = log_callback or print

    if not csv_path.exists():
        raise ValueError(f"CSV not found: {csv_path}")

    rows       = load_csv(csv_path)
    candidates = [r for r in rows if r.get("status") == "renamed"]

    log(f"  Rows to undo: {len(candidates)} of {len(rows)} total")

    if not candidates:
        log("  Nothing to undo (no rows with status 'renamed').")
        return {"undone": 0, "skipped": 0, "errors": 0,
                "results": [], "report_path": None}

    # ── Build plan ─────────────────────────────────────────────────────────────
    plan   = []
    issues = []

    for r in candidates:
        folder_path   = Path(r["folder_path"])
        original_name = r.get("original_name", "")

        if not original_name:
            issues.append(f"  ! Missing original_name for: {folder_path.name}")
            continue

        if not folder_path.exists():
            issues.append(f"  ! Renamed folder no longer exists: {folder_path}")
            continue

        dest = folder_path.parent / original_name

        if dest.exists():
            issues.append(f"  ! Original path already exists, cannot undo: {dest}")
            continue

        plan.append((folder_path, dest, original_name))

    for msg in issues:
        log(msg)

    for src, dst, orig in plan:
        log(f"  {src.name}")
        log(f"  → {orig}")

    if not plan:
        log("  Nothing to undo after validation.")
        return {"undone": 0, "skipped": len(issues), "errors": 0,
                "results": [], "report_path": None}

    out_rows = []

    if not apply:
        log(f"  {len(plan)} rename(s) would be undone.")
        reports_dir = SCRIPT_DIR / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"rename_undo_{ts}_dry.csv"
        for src, dst, orig in plan:
            out_rows.append({"original_path": str(src), "restored_name": orig,
                             "status": "pending", "notes": "Dry run — would undo"})
        write_csv(out_rows, str(report_path), fieldnames=FIELDNAMES)
        log(f"  Report saved: {report_path}")
        return {"undone": 0, "pending": len(plan), "skipped": len(issues),
                "errors": 0, "results": out_rows, "report_path": report_path}

    # ── Apply ──────────────────────────────────────────────────────────────────
    undone = errors = 0

    for i, (src, dst, orig) in enumerate(plan):
        if progress_callback:
            progress_callback(i + 1, len(plan), orig)
        try:
            shutil.move(str(src), str(dst))
            log(f"  ✓  {orig}")
            out_rows.append({"original_path": str(src), "restored_name": orig,
                             "status": "undone", "notes": "OK"})
            undone += 1
        except Exception as e:
            log(f"  !  Error restoring {src.name}: {e}")
            out_rows.append({"original_path": str(src), "restored_name": orig,
                             "status": "error", "notes": str(e)})
            errors += 1

    reports_dir = SCRIPT_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"rename_undo_{ts}_applied.csv"
    write_csv(out_rows, str(report_path), fieldnames=FIELDNAMES)
    log(f"  Report saved: {report_path}")

    return {"undone": undone, "pending": 0, "skipped": len(issues),
            "errors": errors, "results": out_rows, "report_path": report_path}


# ══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT  ← .cmd launchers call this; GUI does not
# ══════════════════════════════════════════════════════════════════════════════

def main():
    interactive_options([])

    args       = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags      = [a for a in sys.argv[1:] if a.startswith("--")]
    apply_mode = "--apply" in flags
    pick_flag  = "--pick"  in flags

    _path_flag = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--path" and i + 1 < len(sys.argv)),
        None,
    )

    if _path_flag:
        csv_path = Path(_path_flag.strip('"'))
    elif args:
        csv_path = Path(args[0].strip('"'))
    else:
        chosen = pick_file()
        if not chosen:
            print("No file selected. Exiting.")
            sys.exit(0)
        csv_path = Path(chosen)

    if not csv_path.exists():
        print(f"ERROR: File not found: {csv_path}")
        sys.exit(1)

    rows       = load_csv(csv_path)
    candidates = [r for r in rows if r.get("status") == "renamed"]

    print()
    print("=" * 60)
    print("  Rename Undo  v1.4")
    print("=" * 60)
    print(f"  Report : {csv_path.name}")
    print(f"  Mode   : {'APPLY — undoing renames' if apply_mode else 'DRY RUN — no changes made'}")
    print(f"  Rows to undo: {len(candidates)} of {len(rows)} total")
    print("=" * 60)

    if not candidates:
        print("\n  Nothing to undo (no rows with status 'renamed').")
        sys.exit(0)

    if apply_mode:
        confirm = input(f"\n  Proceed with undoing {len(candidates)} rename(s)? (y/n): ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            sys.exit(0)

    try:
        result = run_rename_undo(csv_path, apply=apply_mode)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    if apply_mode:
        print(f"  Undone : {result['undone']}")
    else:
        print(f"  Would undo : {result['pending']}")
    if result["errors"]:
        print(f"  Errors : {result['errors']}")
    if result["report_path"]:
        print(f"  Report : {result['report_path']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
