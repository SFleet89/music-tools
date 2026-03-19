"""
Library Duplicate Remover  v1.0
=================================
Reads a decisions CSV exported from library_dupes_viewer.html and moves the
files you marked for removal to a holding folder — safely, with a dry-run
option, full undo support, and conflict handling.

Nothing is permanently deleted. Files are moved to a holding folder so you
can review them before committing to deletion.

Workflow:
    1. Run find_library_dupes.py to generate the duplicate report
    2. Open library_dupes_viewer.html, review matches, mark decisions, download CSV
    3. Run this script (dry run first, then live):
         python remove_library_dupes.py decisions.csv --dry-run
         python remove_library_dupes.py decisions.csv
    4. Review the holding folder, then delete when satisfied
    5. To undo: python remove_library_dupes.py decisions.csv --undo

Usage:
    python remove_library_dupes.py <decisions_csv>
    python remove_library_dupes.py <decisions_csv> --dry-run
    python remove_library_dupes.py <decisions_csv> --undo
    python remove_library_dupes.py <decisions_csv> --list
    python remove_library_dupes.py <decisions_csv> --config other.json
"""

import sys
import os
import csv
import json
import shutil
from pathlib import Path
from datetime import datetime
from collections import Counter

# ── Parse flags ────────────────────────────────────────────────────────────────
DRY_RUN  = "--dry-run" in sys.argv
DO_UNDO  = "--undo"    in sys.argv
DO_LIST  = "--list"    in sys.argv

_cfg_flag = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                  if a == "--config" and i+1 < len(sys.argv)), None)

# ── Config ─────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = "library_dupes_config.json"

def load_config(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        print(f"WARNING: Could not parse config {path}: {e}")
        return {}

CFG         = load_config(_cfg_flag or DEFAULT_CONFIG)
_folders    = CFG.get("folders", {})
REPORTS_DIR = Path(_folders.get("reports", "reports"))

# Holding folder — where removed files go
# Defaults to a 'library_dupes_removed' subfolder next to reports
_holding_default = str(REPORTS_DIR.parent / "library_dupes_removed")
HOLDING_FOLDER   = Path(_folders.get("holding", _holding_default))

# Undo log — one per removal run, stored in reports folder
UNDO_LOG_PREFIX = "library_dupes_undo_"


# ── CSV parsing ────────────────────────────────────────────────────────────────
def load_decisions(csv_path: Path) -> list[dict]:
    """Load decisions CSV exported from library_dupes_viewer.html."""
    rows = []
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def get_remove_rows(rows: list[dict]) -> list[dict]:
    """Return only rows where decision is 'remove' or 'keep A'/'keep B' with a remove path."""
    result = []
    for row in rows:
        decision = (row.get("Decision") or "").strip().lower()
        remove_path = (row.get("Remove Path") or "").strip()

        if decision in ("remove",) and remove_path:
            result.append(row)
        elif decision in ("keep a", "keep b") and remove_path:
            # Pair view — Remove Path is the one to move
            result.append(row)
    return result


# ── Undo log ───────────────────────────────────────────────────────────────────
def find_undo_log(decisions_csv: Path) -> Path | None:
    """Find the undo log that matches this decisions CSV, if one exists."""
    stem = decisions_csv.stem
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    candidates = list(REPORTS_DIR.glob(f"{UNDO_LOG_PREFIX}*.json"))
    for c in sorted(candidates, reverse=True):  # most recent first
        try:
            with open(c, encoding="utf-8") as f:
                log = json.load(f)
            if log.get("decisions_csv") == str(decisions_csv):
                return c
        except Exception:
            continue
    return None


def save_undo_log(decisions_csv: Path, moves: list[dict], timestamp: str):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = REPORTS_DIR / f"{UNDO_LOG_PREFIX}{timestamp}.json"
    log = {
        "decisions_csv": str(decisions_csv),
        "timestamp":     timestamp,
        "holding_folder": str(HOLDING_FOLDER),
        "moves": moves,  # [{original, destination, match_method}]
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)
    return log_path


# ── List ───────────────────────────────────────────────────────────────────────
def cmd_list(decisions_csv: Path):
    """Print a summary of what the decisions CSV contains."""
    if not decisions_csv.exists():
        print(f"ERROR: File not found: {decisions_csv}")
        sys.exit(1)

    rows = load_decisions(decisions_csv)
    remove_rows = get_remove_rows(rows)

    dec_counts = Counter((r.get("Decision") or "—").strip().lower() for r in rows)
    method_counts = Counter((r.get("Match Method") or "—").strip() for r in remove_rows)

    print("=" * 65)
    print("Library Duplicate Remover — Decisions Summary")
    print("=" * 65)
    print(f"  File     : {decisions_csv.name}")
    print(f"  Total rows       : {len(rows)}")
    print(f"  Files to remove  : {len(remove_rows)}")
    print()
    print("  Decision breakdown:")
    for dec, count in dec_counts.most_common():
        print(f"    {count:>5}  {dec}")
    print()
    if remove_rows:
        print("  Files to remove — by match method:")
        for m, count in method_counts.most_common():
            print(f"    {count:>5}  {m}")
        print()
        print(f"  Would move to: {HOLDING_FOLDER}")
        print()
        print("  File list:")
        for r in remove_rows:
            remove_path = (r.get("Remove Path") or "").strip()
            keep_path   = (r.get("Keep Path")   or "").strip()
            method      = (r.get("Match Method") or "").strip()
            p = Path(remove_path)
            print(f"    REMOVE: {p.name}")
            print(f"      {remove_path}")
            if keep_path:
                print(f"    KEEP  : {Path(keep_path).name}")
            if method:
                print(f"    Method: {method}")
            print()
    print("=" * 65)


# ── Remove ─────────────────────────────────────────────────────────────────────
def cmd_remove(decisions_csv: Path):
    if not decisions_csv.exists():
        print(f"ERROR: Decisions CSV not found: {decisions_csv}")
        sys.exit(1)

    rows        = load_decisions(decisions_csv)
    remove_rows = get_remove_rows(rows)

    print("=" * 65)
    print("Library Duplicate Remover")
    if DRY_RUN:
        print("*** DRY RUN: No files will be moved ***")
    print(f"  Started  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  CSV      : {decisions_csv.name}")
    print(f"  To remove: {len(remove_rows)} file(s)")
    print(f"  Holding  : {HOLDING_FOLDER}")
    print("=" * 65)
    print()

    if not remove_rows:
        print("  No files marked for removal in this decisions CSV.")
        print("  Open library_dupes_viewer.html, make decisions, and download the CSV.")
        return

    if not DRY_RUN:
        HOLDING_FOLDER.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    moves     = []
    moved     = 0
    skipped   = 0
    errors    = 0

    for r in remove_rows:
        remove_path_str = (r.get("Remove Path") or "").strip()
        keep_path_str   = (r.get("Keep Path")   or "").strip()
        method          = (r.get("Match Method") or "").strip()

        # Handle semicolon-separated remove paths (group view can have multiple)
        paths_to_remove = [p.strip() for p in remove_path_str.split(";") if p.strip()]

        for path_str in paths_to_remove:
            src = Path(path_str)

            if not src.exists():
                print(f"  [MISSING]  Already gone or moved:")
                print(f"             {src}")
                skipped += 1
                print()
                continue

            # Destination: flatten into holding folder preserving filename
            # If collision, add a numeric suffix
            dest = HOLDING_FOLDER / src.name
            if dest.exists():
                stem = src.stem
                suffix = src.suffix
                counter = 1
                while dest.exists():
                    dest = HOLDING_FOLDER / f"{stem}_{counter}{suffix}"
                    counter += 1

            if DRY_RUN:
                print(f"  [WOULD MOVE] {src.name}")
                print(f"    From : {src}")
                print(f"    To   : {dest}")
                if keep_path_str:
                    print(f"    Keep : {Path(keep_path_str.split(';')[0].strip()).name}")
                if method:
                    print(f"    Method: {method}")
                moved += 1
            else:
                try:
                    shutil.move(str(src), str(dest))
                    print(f"  [MOVED] {src.name}")
                    print(f"    From : {src}")
                    print(f"    To   : {dest}")
                    if method:
                        print(f"    Method: {method}")
                    moves.append({
                        "original":     str(src),
                        "destination":  str(dest),
                        "match_method": method,
                        "keep_path":    keep_path_str,
                    })
                    moved += 1
                except Exception as e:
                    print(f"  [ERROR]  {src.name}")
                    print(f"           {e}")
                    errors += 1
            print()

    # Save undo log
    if not DRY_RUN and moves:
        log_path = save_undo_log(decisions_csv, moves, timestamp)
        print(f"  Undo log saved: {log_path}")
        print()

    print("=" * 65)
    print("SUMMARY")
    if DRY_RUN:
        print(f"  Would move : {moved}")
    else:
        print(f"  Moved      : {moved}")
    print(f"  Skipped    : {skipped}")
    print(f"  Errors     : {errors}")
    if not DRY_RUN and moved:
        print(f"\n  Files are in: {HOLDING_FOLDER}")
        print(f"  To undo    : python remove_library_dupes.py \"{decisions_csv}\" --undo")
    print("=" * 65)


# ── Undo ───────────────────────────────────────────────────────────────────────
def cmd_undo(decisions_csv: Path):
    log_path = find_undo_log(decisions_csv)
    if not log_path:
        print(f"ERROR: No undo log found for {decisions_csv.name}")
        print(f"       Make sure you ran this script with the same decisions CSV.")
        sys.exit(1)

    with open(log_path, encoding="utf-8") as f:
        log = json.load(f)

    moves = log.get("moves", [])
    if not moves:
        print("Nothing to undo — no moves were recorded in the log.")
        return

    print("=" * 65)
    print("Library Duplicate Remover — Undo")
    if DRY_RUN:
        print("*** DRY RUN: No files will be moved ***")
    print(f"  Log file : {log_path.name}")
    print(f"  Moves    : {len(moves)}")
    print("=" * 65)
    print()

    restored = 0
    skipped  = 0
    errors   = 0

    for move in moves:
        src  = Path(move["destination"])   # currently in holding folder
        dest = Path(move["original"])      # back to original location

        if not src.exists():
            print(f"  [MISSING]  Not in holding folder — may already be restored:")
            print(f"             {src.name}")
            skipped += 1
            print()
            continue

        if dest.exists():
            print(f"  [SKIP]  File already exists at original location:")
            print(f"          {dest}")
            skipped += 1
            print()
            continue

        if DRY_RUN:
            print(f"  [WOULD RESTORE] {src.name}")
            print(f"    To: {dest}")
            restored += 1
        else:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
                print(f"  [RESTORED] {src.name}")
                print(f"    To: {dest}")
                restored += 1
            except Exception as e:
                print(f"  [ERROR]  {src.name}: {e}")
                errors += 1
        print()

    print("=" * 65)
    print("SUMMARY")
    if DRY_RUN:
        print(f"  Would restore : {restored}")
    else:
        print(f"  Restored      : {restored}")
    print(f"  Skipped       : {skipped}")
    print(f"  Errors        : {errors}")
    print("=" * 65)


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pos_args = [a for a in sys.argv[1:]
                if not a.startswith("--") and a != (_cfg_flag or "")]

    if not pos_args:
        print("Usage: python remove_library_dupes.py <decisions_csv> [options]")
        print()
        print("Options:")
        print("  --dry-run     Preview only, nothing moves")
        print("  --list        Show summary of decisions CSV and exit")
        print("  --undo        Restore files moved by the last run for this CSV")
        print("  --config FILE Use a different config file")
        print()
        print("Examples:")
        print('  python remove_library_dupes.py "library_dupes_decisions.csv" --dry-run')
        print('  python remove_library_dupes.py "library_dupes_decisions.csv" --list')
        print('  python remove_library_dupes.py "library_dupes_decisions.csv"')
        print('  python remove_library_dupes.py "library_dupes_decisions.csv" --undo')
        sys.exit(1)

    decisions_csv = Path(pos_args[0].strip('"'))

    if DO_LIST:
        cmd_list(decisions_csv)
    elif DO_UNDO:
        cmd_undo(decisions_csv)
    else:
        cmd_remove(decisions_csv)
