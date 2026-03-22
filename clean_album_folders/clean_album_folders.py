"""
Clean Album Folders  v1.0
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
    python clean_album_folders.py                        # dry run, folder picker
    python clean_album_folders.py --apply                # clean for real
    python clean_album_folders.py --path "C:\\Music"     # override folder
    python clean_album_folders.py --path "C:\\Music" --apply

Requirements:
    pip install mutagen
"""

import sys
import csv
import shutil
from pathlib import Path
from datetime import datetime
from collections import Counter

# ── Config ─────────────────────────────────────────────────────────────────────
DEFAULT_FOLDER  = r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\SD\Music"
HOLDING_FOLDER  = r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\tools\clean_album_folders\holding"
REPORTS_FOLDER  = r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\tools\clean_album_folders\reports"

# Music file extensions — always kept
MUSIC_EXT = {
    ".mp3", ".flac", ".aac", ".m4a", ".ogg", ".wma",
    ".wav", ".aiff", ".aif", ".ape", ".opus", ".wv"
}

# CUE file size threshold — keep CUE only if paired with audio file larger than this
CUE_SIZE_THRESHOLD_MB = 100

# ── Flags ──────────────────────────────────────────────────────────────────────
DRY_RUN = "--apply" not in sys.argv
_path   = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                if a == "--path" and i+1 < len(sys.argv)), None)


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def is_music_file(path: Path) -> bool:
    return path.suffix.lower() in MUSIC_EXT


def should_keep_cue(cue_file: Path) -> bool:
    """
    Keep a CUE file only if its parent folder contains exactly one large
    audio file (>100MB) — indicating a single-file rip needing splitting.
    """
    folder     = cue_file.parent
    audio_files = [f for f in folder.iterdir()
                   if f.is_file() and f.suffix.lower() in MUSIC_EXT]
    if len(audio_files) == 1:
        size_mb = audio_files[0].stat().st_size / (1024 * 1024)
        return size_mb > CUE_SIZE_THRESHOLD_MB
    return False


def get_relative_path(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return Path(path.name)


# ══════════════════════════════════════════════════════════════════════════════
#  FOLDER PICKER
# ══════════════════════════════════════════════════════════════════════════════

def pick_folder() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print("ERROR: tkinter is not available.")
        sys.exit(1)
    root_tk = tk.Tk()
    root_tk.withdraw()
    root_tk.attributes("-topmost", True)
    folder = filedialog.askdirectory(
        title="Select root folder to clean",
        parent=root_tk,
    )
    root_tk.destroy()
    return Path(folder) if folder else None


# ══════════════════════════════════════════════════════════════════════════════
#  SCAN
# ══════════════════════════════════════════════════════════════════════════════

def scan(root: Path) -> tuple[list[dict], list[dict]]:
    """
    Walk all files recursively.
    Returns (to_move, to_keep) lists of file dicts.
    """
    to_move = []
    to_keep = []

    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue

        ext = f.suffix.lower()
        rel = get_relative_path(f, root)

        # Always keep music files
        if is_music_file(f):
            to_keep.append({"file": f, "rel": rel, "reason": "music file"})
            continue

        # CUE files — conditional keep
        if ext == ".cue":
            if should_keep_cue(f):
                to_keep.append({"file": f, "rel": rel,
                                "reason": "CUE paired with large single-file rip"})
            else:
                to_move.append({"file": f, "rel": rel,
                                "ext": ext, "reason": "CUE not needed (multi-track rip)"})
            continue

        # Everything else — move
        to_move.append({"file": f, "rel": rel, "ext": ext, "reason": "non-music file"})

    return to_move, to_keep


# ══════════════════════════════════════════════════════════════════════════════
#  REPORT
# ══════════════════════════════════════════════════════════════════════════════

def write_report(to_move: list, to_keep: list, reports_dir: Path, dry_run: bool):
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix    = "dry" if dry_run else "applied"
        out_path  = reports_dir / f"clean_album_folders_{suffix}_{timestamp}.csv"

        fieldnames = ["File", "Extension", "Action", "Reason", "Status"]
        rows = []

        for entry in to_move:
            rows.append({
                "File":      str(entry["rel"]),
                "Extension": entry["ext"],
                "Action":    "move to holding",
                "Reason":    entry["reason"],
                "Status":    entry.get("status", "would move" if dry_run else "pending"),
            })
        for entry in to_keep:
            rows.append({
                "File":      str(entry["rel"]),
                "Extension": entry["file"].suffix.lower(),
                "Action":    "keep",
                "Reason":    entry["reason"],
                "Status":    "kept",
            })

        # Sort by file path
        rows.sort(key=lambda r: r["File"])

        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"  Report saved: {out_path}\n")
    except Exception as e:
        print(f"  WARNING: Could not write report: {e}\n")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    reports_dir = Path(REPORTS_FOLDER)
    holding_dir = Path(HOLDING_FOLDER)

    # ── Determine folder ───────────────────────────────────────────────────────
    if _path:
        root = Path(_path.strip('"'))
    else:
        root = pick_folder()
        if not root:
            print("\n  No folder selected. Exiting.\n")
            return

    if not root.exists() or not root.is_dir():
        print(f"ERROR: Folder not found: {root}")
        sys.exit(1)

    mode = "DRY RUN — nothing will be moved" if DRY_RUN else "LIVE — files will be moved"
    print(f"\n{'='*65}")
    print(f"Clean Album Folders  v1.0")
    print(f"{'='*65}")
    print(f"  Mode    : {mode}")
    print(f"  Folder  : {root}")
    print(f"  Holding : {holding_dir}")
    print(f"{'='*65}\n")

    # ── Scan ───────────────────────────────────────────────────────────────────
    print("  Scanning...\n")
    to_move, to_keep = scan(root)

    if not to_move and not to_keep:
        print("  No files found.\n")
        return

    # Extension breakdown of files to move
    ext_counts = Counter(e["ext"] for e in to_move)

    print(f"  Music files to keep  : {len(to_keep)}")
    print(f"  Files to move        : {len(to_move)}")
    if ext_counts:
        print(f"\n  By type:")
        for ext, count in ext_counts.most_common():
            print(f"    {count:>5}x  {ext or '(no extension)'}")
    print()

    # CUE files being kept
    cue_kept = [e for e in to_keep if e["file"].suffix.lower() == ".cue"]
    if cue_kept:
        print(f"  CUE files kept ({len(cue_kept)} — paired with large single-file rip):")
        for e in cue_kept:
            print(f"    {e['rel']}")
        print()

    if not to_move:
        print("  Nothing to move — folders are already clean.\n")
        write_report(to_move, to_keep, reports_dir, DRY_RUN)
        return

    # ── Preview sample ─────────────────────────────────────────────────────────
    print(f"  Sample of files that would be moved (first 15):")
    for entry in to_move[:15]:
        print(f"    {entry['rel']}")
    if len(to_move) > 15:
        print(f"    ... and {len(to_move)-15} more")
    print()

    if DRY_RUN:
        print(f"  Dry run complete. Run with --apply to move files.\n")
        write_report(to_move, to_keep, reports_dir, True)
        return

    # ── Confirm ────────────────────────────────────────────────────────────────
    confirm = input(f"  Move {len(to_move)} file(s) to holding folder? (y/n): ").strip().lower()
    while confirm not in ("y", "n"):
        confirm = input("  Please enter y or n: ").strip().lower()
    if confirm != "y":
        print("  Aborted.\n")
        return

    # ── Apply ──────────────────────────────────────────────────────────────────
    moved  = 0
    errors = 0

    for entry in to_move:
        src  = entry["file"]
        dest = holding_dir / entry["rel"]

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Handle collision
            if dest.exists():
                stem, suffix, counter = dest.stem, dest.suffix, 1
                while dest.exists():
                    dest = dest.parent / f"{stem}_({counter}){suffix}"
                    counter += 1
            shutil.move(str(src), str(dest))
            entry["status"] = "moved"
            moved += 1
        except Exception as e:
            print(f"  [ERROR] {src.name}: {e}")
            entry["status"] = f"error: {e}"
            errors += 1

    print(f"\n  {'='*40}")
    print(f"  Moved   : {moved}")
    print(f"  Kept    : {len(to_keep)}")
    print(f"  Errors  : {errors}")
    print(f"  Holding : {holding_dir}")
    print(f"  {'='*40}\n")

    write_report(to_move, to_keep, reports_dir, False)


if __name__ == "__main__":
    main()
