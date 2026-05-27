"""
Sort CD Tracks  v1.4
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

import re
import sys
import csv
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import (
    SUPPORTED_EXTENSIONS as SUPPORTED_EXT,
    pick_folder,
    get_music_files,
    interactive_options,
)

try:
    from mutagen import File as MutagenFile
except ImportError:
    print("ERROR: 'mutagen' is not installed.")
    print("       Run:  pip install mutagen")
    sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR     = Path(__file__).parent
REPORTS_FOLDER = SCRIPT_DIR / "reports"
_CD_RE         = re.compile(r'^(cd|disc|disk)\s*\d+$', re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
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


def write_report(results: list, reports_dir: Path, dry_run: bool) -> Path | None:
    """Write a timestamped CSV report. Returns the report path, or None on failure."""
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix     = "dry" if dry_run else "applied"
        out_path   = reports_dir / f"sort_cd_tracks_{suffix}_{timestamp}.csv"
        fieldnames = ["Filename", "Disc Number", "Destination Folder", "Status"]
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        return out_path
    except Exception as e:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_sort_cd_tracks(
    folder: Path,
    apply: bool = False,
    recursive: bool = False,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Sort music files into CD subfolders by DISCNUMBER tag.

    This function contains all the real logic. The CLI main() and the GUI
    both call this — main() after parsing flags, the GUI directly with its
    own folder selection and confirmation.

    Args:
        folder:            Root folder to process.
        apply:             False = dry run only; True = move files.
        recursive:         If True, process all album subfolders under folder.
        progress_callback: Optional callable(current, total, message) for
                           progress bar updates. Called once per file processed.
        log_callback:      Optional callable(message) for log output. If None,
                           falls back to print().

    Returns:
        dict with keys:
            moved         (int)  — files successfully moved (0 in dry run)
            skipped       (int)  — destinations already existed
            errors        (int)  — move failures
            no_tag        (int)  — files with no DISCNUMBER tag
            skipped_albums(int)  — folders with no disc tags at all
            results       (list) — full row dicts for the CSV report
            report_path   (Path|None) — path to written report, or None

    Raises:
        ValueError:   folder does not exist or is not a directory.
    """
    log = log_callback or print

    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    # ── Determine folders to process ───────────────────────────────────────────
    if recursive:
        folders_to_process = sorted(
            d for d in folder.rglob("*")
            if d.is_dir()
            and not _CD_RE.match(d.name)
            and get_music_files(d)
        )
        if not folders_to_process:
            log("  No album folders with unsorted music files found.")
            return {
                "moved": 0, "skipped": 0, "errors": 0,
                "no_tag": 0, "skipped_albums": 0,
                "results": [], "report_path": None,
            }
        log(f"  Found {len(folders_to_process)} album folder(s) to check.")
    else:
        # Auto-detect: if root has no direct music files but subfolders do,
        # switch to recursive automatically.
        direct_music = get_music_files(folder)
        if not direct_music:
            subfolder_has_music = any(
                get_music_files(d)
                for d in folder.iterdir()
                if d.is_dir() and not _CD_RE.match(d.name)
            )
            if subfolder_has_music:
                recursive = True
                log("  No music files found directly — scanning subfolders instead.")
                folders_to_process = sorted(
                    d for d in folder.rglob("*")
                    if d.is_dir()
                    and not _CD_RE.match(d.name)
                    and get_music_files(d)
                )
            else:
                log("  No music files found.")
                return {
                    "moved": 0, "skipped": 0, "errors": 0,
                    "no_tag": 0, "skipped_albums": 0,
                    "results": [], "report_path": None,
                }
        else:
            folders_to_process = [folder]

    # ── Scan each folder ────────────────────────────────────────────────────────
    all_to_move    = []
    all_results    = []
    skipped_albums = []
    total_files    = sum(len(get_music_files(d)) for d in folders_to_process)
    processed      = 0

    for album_folder in folders_to_process:
        files   = get_music_files(album_folder)
        by_disc = defaultdict(list)
        no_disc = []

        for f in files:
            disc = read_disc_number(f)
            if disc is not None:
                by_disc[disc].append(f)
            else:
                no_disc.append(f)
            processed += 1
            if progress_callback:
                progress_callback(processed, total_files, f.name)

        if not by_disc:
            skipped_albums.append((album_folder.name, "no disc tags"))
            for f in no_disc:
                all_results.append({
                    "Filename": f.name, "Disc Number": "",
                    "Destination Folder": "", "Status": "no disc tag — left in place",
                })
            continue

        for disc in sorted(by_disc):
            cd_folder = album_folder / f"CD{disc}"
            for f in by_disc[disc]:
                dest = cd_folder / f.name
                try:
                    rel_folder = str(album_folder.relative_to(folder))
                except Exception:
                    rel_folder = album_folder.name
                rel = f"{rel_folder}/CD{disc}" if recursive else f"CD{disc}"

                if dest.exists():
                    all_results.append({
                        "Filename": f.name, "Disc Number": disc,
                        "Destination Folder": rel,
                        "Status": "skipped — destination already exists",
                    })
                    continue

                all_to_move.append({
                    "file": f, "disc": disc,
                    "cd_folder": cd_folder, "dest": dest,
                    "album": str(album_folder),
                })
                all_results.append({
                    "Filename": f.name, "Disc Number": disc,
                    "Destination Folder": rel,
                    "Status": "would move" if not apply else "pending",
                })

        for f in no_disc:
            all_results.append({
                "Filename": f.name, "Disc Number": "",
                "Destination Folder": "", "Status": "no disc tag — left in place",
            })

    # ── Dry run: report and return ─────────────────────────────────────────────
    if not apply:
        log(f"  {len(all_to_move)} file(s) would be moved (dry run).")
        if skipped_albums:
            log(f"  {len(skipped_albums)} album(s) skipped — no disc tags.")
        report_path = write_report(all_results, REPORTS_FOLDER, dry_run=True)
        if report_path:
            log(f"  Report saved: {report_path}")
        return {
            "moved": 0,
            "skipped": sum(1 for r in all_results if "already exists" in r["Status"]),
            "errors": 0,
            "no_tag": sum(1 for r in all_results if "no disc tag" in r["Status"]),
            "skipped_albums": len(skipped_albums),
            "results": all_results,
            "report_path": report_path,
        }

    # ── Apply: move files ──────────────────────────────────────────────────────
    if not all_to_move:
        log("  Nothing to move.")
        report_path = write_report(all_results, REPORTS_FOLDER, dry_run=False)
        return {
            "moved": 0, "skipped": 0, "errors": 0,
            "no_tag": sum(1 for r in all_results if "no disc tag" in r["Status"]),
            "skipped_albums": len(skipped_albums),
            "results": all_results, "report_path": report_path,
        }

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
            log(f"  [ERROR] {entry['file'].name}: {e}")
            for r in all_results:
                if r["Filename"] == entry["file"].name:
                    r["Status"] = f"error: {e}"
                    break
            errors += 1

    log(f"  Moved: {moved}  |  Errors: {errors}  |  Albums skipped: {len(skipped_albums)}")
    report_path = write_report(all_results, REPORTS_FOLDER, dry_run=False)
    if report_path:
        log(f"  Report saved: {report_path}")

    return {
        "moved": moved,
        "skipped": sum(1 for r in all_results if "already exists" in r["Status"]),
        "errors": errors,
        "no_tag": sum(1 for r in all_results if "no disc tag" in r["Status"]),
        "skipped_albums": len(skipped_albums),
        "results": all_results,
        "report_path": report_path,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT  ← .cmd launchers call this; GUI does not
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # ── Interactive options menu ───────────────────────────────────────────────
    interactive_options([
        ("--recursive", "Recursive — scan all subfolders automatically"),
    ])

    # ── Parse flags ────────────────────────────────────────────────────────────
    dry_run   = "--apply"     not in sys.argv
    recursive = "--recursive" in sys.argv
    _path     = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                      if a == "--path" and i+1 < len(sys.argv)), None)

    # ── Folder selection ───────────────────────────────────────────────────────
    if _path:
        folder = Path(_path.strip('"'))
    else:
        folder = pick_folder("Select album folder (or library root for --recursive)")
        if not folder:
            print("\n  No folder selected. Exiting.\n")
            return

    # ── Banner ─────────────────────────────────────────────────────────────────
    mode = "DRY RUN — nothing will be moved" if dry_run else "LIVE — files will be moved"
    print(f"\n{'='*65}")
    print(f"Sort CD Tracks  v1.4")
    print(f"{'='*65}")
    print(f"  Mode   : {mode}")
    print(f"  Folder : {folder}")
    print(f"{'='*65}\n")

    # ── Run core logic ─────────────────────────────────────────────────────────
    try:
        result = run_sort_cd_tracks(
            folder    = folder,
            apply     = False,          # Always scan first in CLI
            recursive = recursive,
        )
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # ── Preview and confirm before applying ────────────────────────────────────
    if dry_run or not result["results"]:
        return

    to_move = [r for r in result["results"] if r["Status"] == "would move"]
    if not to_move:
        return

    # Show preview grouped by destination
    print(f"  {len(to_move)} file(s) to move:\n")
    seen = []
    for r in to_move:
        dest = r["Destination Folder"]
        if dest not in seen:
            seen.append(dest)
            count = sum(1 for x in to_move if x["Destination Folder"] == dest)
            print(f"  -> {dest}/  ({count} files)")

    print()
    confirm = input(f"  Move {len(to_move)} file(s) into CD subfolders? (y/n): ").strip().lower()
    while confirm not in ("y", "n"):
        confirm = input("  Please enter y or n: ").strip().lower()
    if confirm != "y":
        print("  Aborted.\n")
        return

    # ── Apply ──────────────────────────────────────────────────────────────────
    try:
        run_sort_cd_tracks(
            folder    = folder,
            apply     = True,
            recursive = recursive,
        )
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
