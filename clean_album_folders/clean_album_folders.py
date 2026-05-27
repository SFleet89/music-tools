"""
Clean Album Folders  v1.4
==========================
Scans album folders and moves non-music files to a holding folder,
mirroring the original folder structure for easy undo.

Keeps:
  - Music files: MP3, FLAC, AAC, M4A, OGG, WMA, WAV, AIFF, APE, OPUS
  - CUE files: only if paired with a single large audio file (>100MB)
    (indicates a single-file rip that needs splitting)

Moves everything else to a holding folder, preserving the full
folder structure so files can be restored to their exact original location.

Nothing is moved until you confirm. Dry run by default.

Usage:
    python clean_album_folders.py                                    # dry run, folder picker
    python clean_album_folders.py --apply                            # clean for real
    python clean_album_folders.py --path "C:\\Music"                 # override folder
    python clean_album_folders.py --path "C:\\Music" --apply
    python clean_album_folders.py --holding "C:\\Holding"            # override holding folder
    python clean_album_folders.py --apply --holding "C:\\Holding"

Default holding folder (when --holding is not given):
    clean_album_folders/holding/   — created automatically on first run

Requirements:
    pip install mutagen
"""

import sys
import csv
import shutil
from pathlib import Path
from datetime import datetime
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import pick_folder, interactive_options

# ── Config ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR      = Path(__file__).parent
REPORTS_FOLDER  = SCRIPT_DIR / "reports"
DEFAULT_HOLDING = SCRIPT_DIR / "holding"

MUSIC_EXT = {
    ".mp3", ".flac", ".aac", ".m4a", ".ogg", ".wma",
    ".wav", ".aiff", ".aif", ".ape", ".opus", ".wv"
}
CUE_SIZE_THRESHOLD_MB = 100


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def is_music_file(path: Path) -> bool:
    return path.suffix.lower() in MUSIC_EXT


def should_keep_cue(cue_file: Path) -> bool:
    folder      = cue_file.parent
    audio_files = [f for f in folder.iterdir()
                   if f.is_file() and f.suffix.lower() in MUSIC_EXT]
    if len(audio_files) == 1:
        return audio_files[0].stat().st_size / (1024 * 1024) > CUE_SIZE_THRESHOLD_MB
    return False


def get_relative_path(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return Path(path.name)


def scan(root: Path) -> tuple:
    """Walk all files recursively. Returns (to_move, to_keep) lists of file dicts."""
    to_move, to_keep = [], []
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        rel = get_relative_path(f, root)
        if is_music_file(f):
            to_keep.append({"file": f, "rel": rel, "reason": "music file"})
        elif ext == ".cue":
            if should_keep_cue(f):
                to_keep.append({"file": f, "rel": rel,
                                "reason": "CUE paired with large single-file rip"})
            else:
                to_move.append({"file": f, "rel": rel, "ext": ext,
                                "reason": "CUE not needed (multi-track rip)"})
        else:
            to_move.append({"file": f, "rel": rel, "ext": ext, "reason": "non-music file"})
    return to_move, to_keep


def write_report(to_move: list, to_keep: list, reports_dir: Path, dry_run: bool) -> "Path | None":
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix     = "dry" if dry_run else "applied"
        out_path   = reports_dir / f"clean_album_folders_{suffix}_{timestamp}.csv"
        fieldnames = ["File", "Extension", "Action", "Reason", "Status"]
        rows = []
        for entry in to_move:
            rows.append({
                "File": str(entry["rel"]), "Extension": entry["ext"],
                "Action": "move to holding", "Reason": entry["reason"],
                "Status": entry.get("status", "would move" if dry_run else "pending"),
            })
        for entry in to_keep:
            rows.append({
                "File": str(entry["rel"]),
                "Extension": entry["file"].suffix.lower(),
                "Action": "keep", "Reason": entry["reason"], "Status": "kept",
            })
        rows.sort(key=lambda r: r["File"])
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return out_path
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_clean_album_folders(
    folder: Path,
    apply: bool = False,
    holding_dir: Path = None,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Scan folder and move non-music files to holding_dir.

    Args:
        folder:            Root folder to scan.
        apply:             False = dry run; True = move files.
        holding_dir:       Destination for moved files. Defaults to
                           clean_album_folders/holding/.
        progress_callback: Optional callable(current, total, message).
        log_callback:      Optional callable(message). Defaults to print().

    Returns:
        dict with keys: moved, kept, errors, results (list), report_path (Path|None)

    Raises:
        ValueError: folder does not exist or is not a directory.
    """
    log = log_callback or print

    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    holding = holding_dir or DEFAULT_HOLDING

    log("  Scanning...")
    to_move, to_keep = scan(folder)

    total = len(to_move) + len(to_keep)
    if progress_callback and total:
        progress_callback(total, total, "Scan complete")

    if not to_move and not to_keep:
        log("  No files found.")
        return {"moved": 0, "kept": 0, "errors": 0, "results": [], "report_path": None}

    ext_counts = Counter(e["ext"] for e in to_move)
    log(f"  Music files to keep : {len(to_keep)}")
    log(f"  Files to move       : {len(to_move)}")
    if ext_counts:
        log("  By type:")
        for ext, count in ext_counts.most_common():
            log(f"    {count:>5}x  {ext or '(no extension)'}")

    if not to_move:
        log("  Nothing to move — folders are already clean.")
        report_path = write_report(to_move, to_keep, REPORTS_FOLDER, dry_run=True)
        if report_path:
            log(f"  Report saved: {report_path}")
        return {"moved": 0, "kept": len(to_keep), "errors": 0,
                "results": to_keep, "report_path": report_path}

    if not apply:
        report_path = write_report(to_move, to_keep, REPORTS_FOLDER, dry_run=True)
        if report_path:
            log(f"  Report saved: {report_path}")
        return {"moved": 0, "kept": len(to_keep), "errors": 0,
                "results": to_move + to_keep, "report_path": report_path}

    # ── Move files ─────────────────────────────────────────────────────────────
    moved  = 0
    errors = 0

    for i, entry in enumerate(to_move):
        src  = entry["file"]
        dest = holding / entry["rel"]
        if progress_callback:
            progress_callback(i + 1, len(to_move), src.name)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                stem, suffix_ext, counter = dest.stem, dest.suffix, 1
                while dest.exists():
                    dest = dest.parent / f"{stem}_({counter}){suffix_ext}"
                    counter += 1
            shutil.move(str(src), str(dest))
            entry["status"] = "moved"
            moved += 1
        except Exception as e:
            log(f"  [ERROR] {src.name}: {e}")
            entry["status"] = f"error: {e}"
            errors += 1

    log(f"  Moved: {moved}  |  Kept: {len(to_keep)}  |  Errors: {errors}")
    log(f"  Holding folder: {holding}")
    report_path = write_report(to_move, to_keep, REPORTS_FOLDER, dry_run=False)
    if report_path:
        log(f"  Report saved: {report_path}")

    return {"moved": moved, "kept": len(to_keep), "errors": errors,
            "results": to_move + to_keep, "report_path": report_path}


# ══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT  ← .cmd launchers call this; GUI does not
# ══════════════════════════════════════════════════════════════════════════════

def main():
    interactive_options([])

    dry_run  = "--apply" not in sys.argv
    _path    = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                     if a == "--path"    and i+1 < len(sys.argv)), None)
    _holding = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                     if a == "--holding" and i+1 < len(sys.argv)), None)

    holding_dir = Path(_holding.strip('"')) if _holding else DEFAULT_HOLDING

    if _path:
        folder = Path(_path.strip('"'))
    else:
        folder = pick_folder("Select folder to clean")
        if not folder:
            print("\n  No folder selected. Exiting.\n")
            return

    mode = "DRY RUN — nothing will be moved" if dry_run else "LIVE — files will be moved"
    print(f"\n{'='*65}")
    print(f"Clean Album Folders  v1.4")
    print(f"{'='*65}")
    print(f"  Mode    : {mode}")
    print(f"  Folder  : {folder}")
    print(f"  Holding : {holding_dir}")
    print(f"{'='*65}\n")

    try:
        result = run_clean_album_folders(folder, apply=False, holding_dir=holding_dir)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    if dry_run or not result["results"]:
        return

    to_move = [e for e in result["results"] if e.get("reason") != "music file"
               and "CUE paired" not in e.get("reason", "")]
    to_move = [e for e in result["results"]
               if e.get("status", "would move") not in ("kept",)]

    # Re-scan to get the actual to_move list cleanly
    to_move_list, _ = scan(folder)
    if not to_move_list:
        return

    print(f"\n  Sample of files that would be moved (first 15):")
    for entry in to_move_list[:15]:
        print(f"    {entry['rel']}")
    if len(to_move_list) > 15:
        print(f"    ... and {len(to_move_list)-15} more")
    print()

    confirm = input(f"  Move {len(to_move_list)} file(s) to holding folder? (y/n): ").strip().lower()
    while confirm not in ("y", "n"):
        confirm = input("  Please enter y or n: ").strip().lower()
    if confirm != "y":
        print("  Aborted.\n")
        return

    try:
        run_clean_album_folders(folder, apply=True, holding_dir=holding_dir)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
