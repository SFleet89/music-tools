"""
Library Duplicate Remover  v1.2
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
from music_tools_common import interactive_options
import csv
import json
import shutil
from pathlib import Path
from datetime import datetime
from collections import Counter

# -- Constants (no side effects on import) -------------------------------------
SCRIPT_DIR      = Path(__file__).parent
DEFAULT_CONFIG  = "library_dupes_config.json"
UNDO_LOG_PREFIX = "library_dupes_undo_"


# -- Config --------------------------------------------------------------------
def load_config(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        print(f"WARNING: Could not parse config {path}: {e}")
        return {}


# -- CSV parsing ---------------------------------------------------------------
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
        decision    = (row.get("Decision")    or "").strip().lower()
        remove_path = (row.get("Remove Path") or "").strip()
        if decision in ("remove",) and remove_path:
            result.append(row)
        elif decision in ("keep a", "keep b") and remove_path:
            # Pair view -- Remove Path is the one to move
            result.append(row)
    return result


# -- Undo log ------------------------------------------------------------------
def find_undo_log(decisions_csv: Path, reports_dir: Path) -> Path | None:
    """Find the undo log that matches this decisions CSV, if one exists."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    candidates = list(reports_dir.glob(f"{UNDO_LOG_PREFIX}*.json"))
    for c in sorted(candidates, reverse=True):   # most recent first
        try:
            with open(c, encoding="utf-8") as f:
                log = json.load(f)
            if log.get("decisions_csv") == str(decisions_csv):
                return c
        except Exception:
            continue
    return None


def save_undo_log(decisions_csv: Path, moves: list[dict], timestamp: str,
                  reports_dir: Path, holding_folder: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    log_path = reports_dir / f"{UNDO_LOG_PREFIX}{timestamp}.json"
    log = {
        "decisions_csv":  str(decisions_csv),
        "timestamp":      timestamp,
        "holding_folder": str(holding_folder),
        "moves":          moves,   # [{original, destination, match_method, keep_path}]
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)
    return log_path


# -- List mode -----------------------------------------------------------------
def cmd_list(decisions_csv: Path, holding_folder: Path,
             log_callback=None) -> dict:
    """Print a summary of what the decisions CSV contains."""
    _log = log_callback or print

    rows        = load_decisions(decisions_csv)
    remove_rows = get_remove_rows(rows)

    dec_counts    = Counter((r.get("Decision")    or "\u2014").strip().lower() for r in rows)
    method_counts = Counter((r.get("Match Method") or "\u2014").strip()        for r in remove_rows)

    _log("=" * 65)
    _log("Library Duplicate Remover \u2014 Decisions Summary")
    _log("=" * 65)
    _log(f"  File             : {decisions_csv.name}")
    _log(f"  Total rows       : {len(rows)}")
    _log(f"  Files to remove  : {len(remove_rows)}")
    _log("")
    _log("  Decision breakdown:")
    for dec, count in dec_counts.most_common():
        _log(f"    {count:>5}  {dec}")
    _log("")
    if remove_rows:
        _log("  Files to remove \u2014 by match method:")
        for m, count in method_counts.most_common():
            _log(f"    {count:>5}  {m}")
        _log("")
        _log(f"  Would move to: {holding_folder}")
        _log("")
        _log("  File list:")
        for r in remove_rows:
            remove_path = (r.get("Remove Path") or "").strip()
            keep_path   = (r.get("Keep Path")   or "").strip()
            method      = (r.get("Match Method") or "").strip()
            p = Path(remove_path)
            _log(f"    REMOVE: {p.name}")
            _log(f"      {remove_path}")
            if keep_path:
                _log(f"    KEEP  : {Path(keep_path).name}")
            if method:
                _log(f"    Method: {method}")
            _log("")
    _log("=" * 65)

    return {
        "rows":          rows,
        "remove_rows":   remove_rows,
        "dec_counts":    dict(dec_counts),
        "method_counts": dict(method_counts),
        "report_path":   None,
    }


# -- Remove mode ---------------------------------------------------------------
def cmd_remove(decisions_csv: Path, dry_run: bool, holding_folder: Path,
               reports_dir: Path, progress_callback=None, log_callback=None) -> dict:
    _log = log_callback or print

    rows        = load_decisions(decisions_csv)
    remove_rows = get_remove_rows(rows)

    _log("=" * 65)
    _log("Library Duplicate Remover")
    if dry_run:
        _log("*** DRY RUN: No files will be moved ***")
    _log(f"  Started  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _log(f"  CSV      : {decisions_csv.name}")
    _log(f"  To remove: {len(remove_rows)} file(s)")
    _log(f"  Holding  : {holding_folder}")
    _log("=" * 65)
    _log("")

    if not remove_rows:
        _log("  No files marked for removal in this decisions CSV.")
        _log("  Open library_dupes_viewer.html, make decisions, and download the CSV.")
        return {"moved": 0, "skipped": 0, "errors": 0,
                "undo_log_path": None, "report_path": None}

    if not dry_run:
        holding_folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    moves     = []
    moved     = 0
    skipped   = 0
    errors    = 0

    # Count total individual file paths for progress
    total = sum(
        len([p for p in (r.get("Remove Path") or "").split(";") if p.strip()])
        for r in remove_rows
    )
    done = 0

    for r in remove_rows:
        remove_path_str = (r.get("Remove Path") or "").strip()
        keep_path_str   = (r.get("Keep Path")   or "").strip()
        method          = (r.get("Match Method") or "").strip()

        # Handle semicolon-separated remove paths (group view can have multiple)
        paths_to_remove = [p.strip() for p in remove_path_str.split(";") if p.strip()]

        for path_str in paths_to_remove:
            src   = Path(path_str)
            done += 1

            if progress_callback:
                progress_callback(done, total, src.name)

            if not src.exists():
                _log(f"  [MISSING]  Already gone or moved:")
                _log(f"             {src}")
                skipped += 1
                _log("")
                continue

            # Destination: flatten into holding folder, add suffix on collision
            dest = holding_folder / src.name
            if dest.exists():
                stem    = src.stem
                suffix  = src.suffix
                counter = 1
                while dest.exists():
                    dest = holding_folder / f"{stem}_{counter}{suffix}"
                    counter += 1

            if dry_run:
                _log(f"  [WOULD MOVE] {src.name}")
                _log(f"    From  : {src}")
                _log(f"    To    : {dest}")
                if keep_path_str:
                    _log(f"    Keep  : {Path(keep_path_str.split(';')[0].strip()).name}")
                if method:
                    _log(f"    Method: {method}")
                moved += 1
            else:
                try:
                    shutil.move(str(src), str(dest))
                    _log(f"  [MOVED] {src.name}")
                    _log(f"    From  : {src}")
                    _log(f"    To    : {dest}")
                    if method:
                        _log(f"    Method: {method}")
                    moves.append({
                        "original":     str(src),
                        "destination":  str(dest),
                        "match_method": method,
                        "keep_path":    keep_path_str,
                    })
                    moved += 1
                except Exception as e:
                    _log(f"  [ERROR]  {src.name}")
                    _log(f"           {e}")
                    errors += 1
            _log("")

    undo_log_path = None
    if not dry_run and moves:
        undo_log_path = save_undo_log(
            decisions_csv, moves, timestamp, reports_dir, holding_folder
        )
        _log(f"  Undo log saved: {undo_log_path}")
        _log("")

    _log("=" * 65)
    _log("SUMMARY")
    if dry_run:
        _log(f"  Would move : {moved}")
    else:
        _log(f"  Moved      : {moved}")
    _log(f"  Skipped    : {skipped}")
    _log(f"  Errors     : {errors}")
    if not dry_run and moved:
        _log(f"\n  Files are in: {holding_folder}")
        _log(f'  To undo    : python remove_library_dupes.py "{decisions_csv}" --undo')
    _log("=" * 65)

    return {
        "moved":         moved,
        "skipped":       skipped,
        "errors":        errors,
        "undo_log_path": undo_log_path,
        "report_path":   str(undo_log_path) if undo_log_path else None,
    }


# -- Undo mode -----------------------------------------------------------------
def cmd_undo(decisions_csv: Path, dry_run: bool, reports_dir: Path,
             progress_callback=None, log_callback=None) -> dict:
    _log = log_callback or print

    log_path = find_undo_log(decisions_csv, reports_dir)
    if not log_path:
        raise ValueError(
            f"No undo log found for {decisions_csv.name}. "
            "Make sure you ran this script with the same decisions CSV."
        )

    with open(log_path, encoding="utf-8") as f:
        log = json.load(f)

    moves = log.get("moves", [])
    if not moves:
        _log("Nothing to undo \u2014 no moves were recorded in the log.")
        return {"restored": 0, "skipped": 0, "errors": 0, "report_path": None}

    _log("=" * 65)
    _log("Library Duplicate Remover \u2014 Undo")
    if dry_run:
        _log("*** DRY RUN: No files will be moved ***")
    _log(f"  Log file : {log_path.name}")
    _log(f"  Moves    : {len(moves)}")
    _log("=" * 65)
    _log("")

    restored = 0
    skipped  = 0
    errors   = 0
    total    = len(moves)

    for i, move in enumerate(moves, 1):
        src  = Path(move["destination"])   # currently in holding folder
        dest = Path(move["original"])      # back to original location

        if progress_callback:
            progress_callback(i, total, src.name)

        if not src.exists():
            _log("  [MISSING]  Not in holding folder \u2014 may already be restored:")
            _log(f"             {src.name}")
            skipped += 1
            _log("")
            continue

        if dest.exists():
            _log("  [SKIP]  File already exists at original location:")
            _log(f"          {dest}")
            skipped += 1
            _log("")
            continue

        if dry_run:
            _log(f"  [WOULD RESTORE] {src.name}")
            _log(f"    To: {dest}")
            restored += 1
        else:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
                _log(f"  [RESTORED] {src.name}")
                _log(f"    To: {dest}")
                restored += 1
            except Exception as e:
                _log(f"  [ERROR]  {src.name}: {e}")
                errors += 1
        _log("")

    _log("=" * 65)
    _log("SUMMARY")
    if dry_run:
        _log(f"  Would restore : {restored}")
    else:
        _log(f"  Restored      : {restored}")
    _log(f"  Skipped       : {skipped}")
    _log(f"  Errors        : {errors}")
    _log("=" * 65)

    return {"restored": restored, "skipped": skipped, "errors": errors,
            "report_path": None}


# -- GUI-callable core ---------------------------------------------------------
def run_remove_library_dupes(
    decisions_csv,
    mode="remove",          # "remove" | "list" | "undo"
    dry_run=True,
    config_file=None,
    reports_dir=None,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    GUI-callable entry point for the library duplicate remover.

    Parameters
    ----------
    decisions_csv : str | Path
        Path to the decisions CSV exported from library_dupes_viewer.html.
    mode : str
        "remove" -- move files marked for removal to the holding folder.
        "list"   -- summarise the CSV and return data; no files are moved.
        "undo"   -- restore files moved by the last removal run for this CSV.
    dry_run : bool
        If True, preview actions without moving anything (default: True).
    config_file : str | None
        Path to the JSON config file.  Defaults to library_dupes_config.json
        next to this script.
    reports_dir : str | Path | None
        Override the reports folder.  If None, taken from config.
    progress_callback : callable | None
        Called as progress_callback(current, total, filename).
    log_callback : callable | None
        Called as log_callback(message) for each log line.

    Returns
    -------
    dict
        Keys vary by mode (see cmd_list / cmd_remove / cmd_undo), plus
        report_path (str | None) -- path to the undo log for "remove" mode,
        None otherwise.

    Raises
    ------
    ValueError
        If decisions_csv does not exist, mode is invalid, or (for undo mode)
        no matching undo log is found.
    """
    # -- Validate decisions CSV
    decisions_csv = Path(decisions_csv)
    if not decisions_csv.exists():
        raise ValueError(f"Decisions CSV not found: {decisions_csv}")

    # -- Load config
    cfg_path = config_file or (SCRIPT_DIR / DEFAULT_CONFIG)
    cfg      = load_config(str(cfg_path))
    folders  = cfg.get("folders", {})

    # -- Resolve reports dir
    if reports_dir is not None:
        reports_dir = Path(reports_dir)
    else:
        reports_dir = SCRIPT_DIR / folders.get("reports", "reports")

    # -- Resolve holding folder
    holding_default = str(reports_dir.parent / "library_dupes_removed")
    holding_folder  = Path(folders.get("holding", holding_default))

    # -- Dispatch
    if mode == "list":
        return cmd_list(decisions_csv, holding_folder,
                        log_callback=log_callback)
    elif mode == "remove":
        return cmd_remove(decisions_csv, dry_run, holding_folder, reports_dir,
                          progress_callback=progress_callback,
                          log_callback=log_callback)
    elif mode == "undo":
        return cmd_undo(decisions_csv, dry_run, reports_dir,
                        progress_callback=progress_callback,
                        log_callback=log_callback)
    else:
        raise ValueError(
            f"Unknown mode: {mode!r}. Expected \'remove\', \'list\', or \'undo\'."
        )


# -- CLI entry point -----------------------------------------------------------
def main():
    interactive_options([
        ("--dry-run", "Dry run \u2014 preview only, no files changed  (default is live mode)"),
    ])

    DRY_RUN  = "--dry-run" in sys.argv
    DO_UNDO  = "--undo"    in sys.argv
    DO_LIST  = "--list"    in sys.argv

    _cfg_flag = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--config" and i + 1 < len(sys.argv)),
        None,
    )

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

    mode = "list" if DO_LIST else "undo" if DO_UNDO else "remove"

    try:
        run_remove_library_dupes(
            decisions_csv=decisions_csv,
            mode=mode,
            dry_run=DRY_RUN,
            config_file=_cfg_flag,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
