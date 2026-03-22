"""
Sort CD Tracks  v1.0
=====================
Reads the DISCNUMBER tag from music files in a folder and moves each file
into the correct CD subfolder (CD1, CD2, CD3 etc.).

Before:
  Brotherhood/
    01 - Electronic Battle Weapon 1.flac   (disc 1)
    01 - Believe.flac                      (disc 2)

After:
  Brotherhood/
    CD1/
      01 - Electronic Battle Weapon 1.flac
    CD2/
      01 - Believe.flac

Files with no DISCNUMBER tag are left in place with a warning.
Nothing is moved until you confirm. Dry run by default.

Usage:
    python sort_cd_tracks.py                          # dry run, folder picker (single album)
    python sort_cd_tracks.py --apply                  # move for real
    python sort_cd_tracks.py --recursive              # scan all album subfolders
    python sort_cd_tracks.py --recursive --apply      # sort all albums for real
    python sort_cd_tracks.py --path "C:\\Music\\Album"
    python sort_cd_tracks.py --path "C:\\Music\\Album" --apply
    python sort_cd_tracks.py --path "C:\\Music" --recursive --apply

Requirements:
    pip install mutagen
"""

import sys
import csv
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict

try:
    from mutagen import File as MutagenFile
except ImportError:
    print("ERROR: 'mutagen' is not installed.")
    print("       Run:  pip install mutagen")
    sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────
REPORTS_FOLDER = r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\tools\sort_cd_tracks\reports"
SUPPORTED_EXT  = {".mp3", ".flac", ".aac", ".m4a"}

# ── Flags ──────────────────────────────────────────────────────────────────────
DRY_RUN   = "--apply"     not in sys.argv
RECURSIVE = "--recursive" in sys.argv
_path     = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                  if a == "--path" and i+1 < len(sys.argv)), None)


# ══════════════════════════════════════════════════════════════════════════════
#  METADATA
# ══════════════════════════════════════════════════════════════════════════════

def read_disc_number(path: Path):
    """
    Read DISCNUMBER tag. Handles formats: "1", "2", "1/2", "2/2".
    Returns integer disc number or None if not found.
    """
    try:
        f = MutagenFile(path, easy=True)
        if f:
            for key in ("discnumber", "disc", "disk"):
                val = f.get(key)
                if val and val[0].strip():
                    raw = val[0].strip().split("/")[0].strip()
                    if raw.isdigit():
                        return int(raw)
    except Exception:
        pass
    return None


def get_music_files(folder: Path):
    return sorted(
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
    )


# ══════════════════════════════════════════════════════════════════════════════
#  FOLDER PICKER
# ══════════════════════════════════════════════════════════════════════════════

def pick_folder():
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
        title="Select album folder to sort into CD subfolders",
        parent=root_tk,
    )
    root_tk.destroy()
    return Path(folder) if folder else None


# ══════════════════════════════════════════════════════════════════════════════
#  REPORT
# ══════════════════════════════════════════════════════════════════════════════

def write_report(results, reports_dir, dry_run):
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix    = "dry" if dry_run else "applied"
        out_path  = reports_dir / f"sort_cd_tracks_{suffix}_{timestamp}.csv"
        fieldnames = ["Filename", "Disc Number", "Destination Folder", "Status"]
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"  Report saved: {out_path}\n")
    except Exception as e:
        print(f"  WARNING: Could not write report: {e}\n")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    reports_dir = Path(REPORTS_FOLDER)

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
    print(f"Sort CD Tracks  v1.0")
    print(f"{'='*65}")
    print(f"  Mode   : {mode}")
    print(f"  Folder : {root}")
    print(f"{'='*65}\n")

    # ── Determine which folders to process ────────────────────────────────────
    if RECURSIVE:
        # Find ALL folders at any depth that have music files directly inside
        # and are NOT already CD-style folders themselves
        import re
        _CD_RE = re.compile(r'^(cd|disc|disk)\s*\d+$', re.IGNORECASE)
        folders_to_process = sorted(
            d for d in root.rglob("*")
            if d.is_dir()
            and not _CD_RE.match(d.name)
            and get_music_files(d)
        )
        if not folders_to_process:
            print("  No album folders with unsorted music files found.\n")
            return
        print(f"  Found {len(folders_to_process)} album folder(s) to check.\n")
    else:
        folders_to_process = [root]

    # ── Process each folder ────────────────────────────────────────────────────
    all_to_move = []
    all_results = []
    skipped_albums = []

    for folder in folders_to_process:
        files = get_music_files(folder)
        if not files:
            continue

        by_disc  = defaultdict(list)
        no_disc  = []

        for f in files:
            disc = read_disc_number(f)
            if disc is not None:
                by_disc[disc].append(f)
            else:
                no_disc.append(f)

        if not by_disc:
            if RECURSIVE:
                skipped_albums.append((folder.name, "no disc tags"))
            else:
                print("  No DISCNUMBER tags found in any files.")
                print("  Tag the files with disc numbers in Picard or MP3Tag first.\n")
            continue

        if len(by_disc) < 2:
            disc_num = list(by_disc.keys())[0]
            if RECURSIVE:
                skipped_albums.append((folder.name, f"single disc only (disc {disc_num})"))
            else:
                print(f"  Only one disc number found (Disc {disc_num}). Nothing to sort.\n")
            continue

        # Build move plan for this folder
        for disc in sorted(by_disc):
            cd_folder = folder / f"CD{disc}"
            for f in by_disc[disc]:
                dest = cd_folder / f.name
                try:
                    _rel_folder = str(folder.relative_to(root))
                except Exception:
                    _rel_folder = folder.name
                rel  = f"{_rel_folder}/CD{disc}" if RECURSIVE else f"CD{disc}"
                if dest.exists():
                    all_results.append({
                        "Filename":           f.name,
                        "Disc Number":        disc,
                        "Destination Folder": rel,
                        "Status":             "skipped — destination already exists",
                    })
                    continue
                all_to_move.append({
                    "file": f, "disc": disc,
                    "cd_folder": cd_folder, "dest": dest,
                    "album": str(folder),
                })
                all_results.append({
                    "Filename":           f.name,
                    "Disc Number":        disc,
                    "Destination Folder": rel,
                    "Status":             "would move" if DRY_RUN else "pending",
                })

        for f in no_disc:
            all_results.append({
                "Filename":           f.name,
                "Disc Number":        "",
                "Destination Folder": "",
                "Status":             "no disc tag — left in place",
            })

    if not all_to_move:
        print("  Nothing to move.\n")
        write_report(all_results, reports_dir, DRY_RUN)
        return

    # ── Preview ────────────────────────────────────────────────────────────────
    print(f"  {len(all_to_move)} file(s) to move" + (" (dry run):" if DRY_RUN else ":"))
    print()

    # Group preview by album folder
    seen_albums = []
    for entry in all_to_move:
        if entry["album"] not in seen_albums:
            seen_albums.append(entry["album"])

    for album in seen_albums:
        album_moves = [e for e in all_to_move if e["album"] == album]
        if RECURSIVE:
            try:
                album_label = str(Path(album).relative_to(str(root))) if Path(album).is_absolute() else album
            except Exception:
                album_label = album
            print(f"  [{album_label}]")
        for disc in sorted(set(e["disc"] for e in album_moves)):
            disc_moves = [e for e in album_moves if e["disc"] == disc]
            indent = "    " if RECURSIVE else "  "
            print(f"{indent}-> CD{disc}/  ({len(disc_moves)} files)")
            for e in disc_moves:
                print(f"{indent}     {e['file'].name}")
        print()

    if skipped_albums:
        print(f"  Skipped albums ({len(skipped_albums)}):")
        for name, reason in skipped_albums:
            print(f"    {name} — {reason}")
        print()

    if DRY_RUN:
        print("  Dry run complete. Run with --apply to move files.\n")
        write_report(all_results, reports_dir, True)
        return

    # ── Confirm ────────────────────────────────────────────────────────────────
    confirm = input(f"  Move {len(all_to_move)} file(s) into CD subfolders? (y/n): ").strip().lower()
    while confirm not in ("y", "n"):
        confirm = input("  Please enter y or n: ").strip().lower()
    if confirm != "y":
        print("  Aborted.\n")
        return

    # ── Apply ──────────────────────────────────────────────────────────────────
    moved  = 0
    errors = 0

    for entry in all_to_move:
        try:
            entry["cd_folder"].mkdir(parents=True, exist_ok=True)
            shutil.move(str(entry["file"]), str(entry["dest"]))
            for r in all_results:
                if r["Filename"] == entry["file"].name and r["Status"] == "pending":
                    r["Status"] = "moved"
                    break
            moved += 1
        except Exception as e:
            print(f"  [ERROR] {entry['file'].name}: {e}")
            for r in all_results:
                if r["Filename"] == entry["file"].name:
                    r["Status"] = f"error: {e}"
                    break
            errors += 1

    print(f"\n  {'='*40}")
    print(f"  Moved  : {moved}")
    print(f"  Errors : {errors}")
    if skipped_albums:
        print(f"  Albums skipped: {len(skipped_albums)}")
    print(f"  {'='*40}\n")

    write_report(all_results, reports_dir, False)


if __name__ == "__main__":
    main()
