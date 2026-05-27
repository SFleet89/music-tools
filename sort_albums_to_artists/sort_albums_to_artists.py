"""
Sort Albums Into Artist Folders  v1.5
======================================
Scans a folder of album subfolders, reads the Album Artist tag (falling back
to Artist if empty) from the music files inside each album, then moves each
album folder into a new or existing artist folder.

Before:
  Unsorted/
    Mezzanine/
    Pablo Honey/
    OK Computer/
    Blue Lines/

After:
  Unsorted/
    Massive Attack/
      Mezzanine/
      Blue Lines/
    Radiohead/
      Pablo Honey/
      OK Computer/

Conflict handling:
  - All files agree on Album Artist → used automatically
  - Files disagree → you are prompted to choose
  - No artist tag found → you are prompted to type a name

Nothing is moved until you confirm. Dry run by default.

Usage:
    python sort_albums_to_artists.py                       # dry run
    python sort_albums_to_artists.py --apply               # move for real
    python sort_albums_to_artists.py --pick                # pick folder with dialog
    python sort_albums_to_artists.py --pick --apply
    python sort_albums_to_artists.py --path "C:\\Music\\Unsorted"

Requirements:
    pip install mutagen
"""

import sys
import csv
import re
import shutil
from pathlib import Path
from datetime import datetime
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import (
    SUPPORTED_EXTENSIONS as SUPPORTED_EXT,
    pick_folder,
    sanitise_folder_name,
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

# ══════════════════════════════════════════════════════════════════════════════
#  METADATA HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def read_artist_tag(path: Path) -> str | None:
    """
    Read Album Artist tag, falling back to Artist if empty.
    Returns None if both are empty or file is unreadable.
    """
    try:
        f = MutagenFile(path, easy=True)
        if f:
            # Try Album Artist first
            for key in ("albumartist", "album artist", "album_artist"):
                val = f.get(key)
                if val and val[0].strip():
                    return val[0].strip()
            # Fall back to Artist
            val = f.get("artist")
            if val and val[0].strip():
                return val[0].strip()
    except Exception:
        pass
    return None




def get_all_music_files(folder: Path) -> list[Path]:
    """Return all music files recursively within a folder."""
    return sorted(
        f for f in folder.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ARTIST DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def get_artist_for_album(album_folder: Path) -> tuple[str | None, str]:
    """
    Read artist tags from all music files in album folder (recursively,
    to handle CD subfolders).
    Returns (artist_name, status) where status is:
      'ok'       — all files agree
      'conflict' — files disagree
      'empty'    — no artist tags found
      'no_files' — no music files found
    """
    files = get_all_music_files(album_folder)
    if not files:
        return None, "no_files"

    tags = [read_artist_tag(f) for f in files]
    tags = [t for t in tags if t]  # remove None

    if not tags:
        return None, "empty"

    counts = Counter(tags)
    if len(counts) == 1:
        return counts.most_common(1)[0][0], "ok"

    return None, "conflict"


# ══════════════════════════════════════════════════════════════════════════════
#  CONFLICT / EMPTY PROMPTS
# ══════════════════════════════════════════════════════════════════════════════

def prompt_conflict(album_folder: Path, files: list[Path]) -> str | None:
    """Show conflicting artist tags and ask user to choose."""
    tags: dict[str, list[str]] = {}
    for f in files:
        tag = read_artist_tag(f)
        if tag:
            tags.setdefault(tag, []).append(f.name)

    print(f"\n  CONFLICT in: {album_folder.name}")
    print(f"  Path       : {album_folder}")
    print(f"  Multiple Album Artist tags found:\n")

    options = sorted(tags.items(), key=lambda x: -len(x[1]))
    for i, (artist, filenames) in enumerate(options, start=1):
        print(f"    [{i}] {artist}  ({len(filenames)} file(s))")
        for fn in filenames[:3]:
            print(f"          {fn}")
        if len(filenames) > 3:
            print(f"          ... and {len(filenames)-3} more")
        print()

    print(f"    [s] Skip this album — leave it where it is")
    print(f"    [t] Type a custom name")

    while True:
        choice = input("  Your choice: ").strip().lower()
        if choice == "s":
            return None
        if choice == "t":
            custom = input("  Enter artist name: ").strip()
            return custom if custom else None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        except ValueError:
            pass
        print("  Invalid — enter a number, 's' to skip, or 't' to type.")


def prompt_empty(album_folder: Path) -> str | None:
    """Ask user to type an artist name for a folder with no tags."""
    print(f"\n  NO ARTIST TAG: {album_folder.name}")
    print(f"  Path         : {album_folder}")
    print(f"  No Album Artist or Artist tag found in any music file.")
    print(f"\n    [t] Type an artist name")
    print(f"    [s] Skip — leave this album where it is")

    while True:
        choice = input("  Your choice (t/s): ").strip().lower()
        if choice == "s":
            return None
        if choice == "t" or choice == "":
            name = input("  Artist name: ").strip()
            return name if name else None
        # If they just typed a name directly
        if len(choice) > 1:
            confirm = input(f"  Use '{choice}' as the artist name? (y/n): ").strip().lower()
            if confirm == "y":
                return choice
        print("  Please enter 't' to type a name or 's' to skip.")


# ══════════════════════════════════════════════════════════════════════════════
#  FOLDER PICKER
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
#  REPORT
# ══════════════════════════════════════════════════════════════════════════════

def write_report(results: list[dict], reports_dir: Path, dry_run: bool):
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix    = "dry" if dry_run else "applied"
        out_path  = reports_dir / f"sort_albums_to_artists_{suffix}_{timestamp}.csv"

        fieldnames = ["Album Folder", "Artist", "Destination", "Status"]
        rows = []
        for r in results:
            artist = r.get("artist") or ""
            dest   = r.get("dest") or ""
            rows.append({
                "Album Folder": r["album"],
                "Artist":       artist,
                "Destination":  dest,
                "Status":       r.get("status", ""),
            })

        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"  Report saved: {out_path}\n")
        return out_path
    except Exception as e:
        print(f"  WARNING: Could not write report: {e}\n")
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_sort_albums_to_artists(
    folder: Path,
    apply: bool = False,
    conflict_resolver=None,
    empty_resolver=None,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Sort album subfolders into artist subfolders by reading Album Artist tags.

    Args:
        folder:            Root folder containing album subfolders.
        apply:             False = dry run; True = move folders.
        conflict_resolver: Optional callable(album_folder, files) -> str|None.
                           Called when multiple artist tags disagree. Return the
                           chosen artist name, or None to skip the album.
                           Defaults to prompt_conflict() (interactive CLI prompt).
        empty_resolver:    Optional callable(album_folder) -> str|None.
                           Called when no artist tag is found. Return a typed
                           artist name, or None to skip. Defaults to prompt_empty().
        progress_callback: Optional callable(current, total, message).
        log_callback:      Optional callable(message). Defaults to print().

    Returns:
        dict: moved, pending, skipped, errors, results (list of dicts),
              report_path (Path|None)

    Raises:
        ValueError: folder does not exist or is not a directory.
    """
    log = log_callback or print

    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    _conflict_resolver = conflict_resolver or prompt_conflict
    _empty_resolver    = empty_resolver    or prompt_empty

    # ── Find album subfolders ──────────────────────────────────────────────────
    album_folders = sorted(
        d for d in folder.iterdir()
        if d.is_dir() and get_all_music_files(d)
    )

    if not album_folders:
        log("  No album folders found (subfolders containing music files).")
        return {"moved": 0, "pending": 0, "skipped": 0, "errors": 0,
                "results": [], "report_path": None}

    total = len(album_folders)
    log(f"  Found {total} album folder(s).")

    # ── Detect artist for each album ───────────────────────────────────────────
    album_data = []
    conflicts  = []
    empties    = []

    for idx, af in enumerate(album_folders, 1):
        if progress_callback:
            progress_callback(idx, total, af.name)
        artist, status = get_artist_for_album(af)
        entry = {"folder": af, "album": af.name, "artist": artist, "status": status}
        album_data.append(entry)
        if status == "conflict":
            conflicts.append(entry)
        elif status in ("empty", "no_files"):
            empties.append(entry)

    ok_count = sum(1 for a in album_data if a["status"] == "ok")
    log(f"  Artist tag clear : {ok_count}")
    log(f"  Conflicts        : {len(conflicts)}")
    log(f"  No artist tag    : {len(empties)}")

    # ── Resolve conflicts ──────────────────────────────────────────────────────
    for entry in conflicts:
        all_files = get_all_music_files(entry["folder"])
        chosen    = _conflict_resolver(entry["folder"], all_files)
        entry["artist"] = chosen
        entry["status"] = "resolved" if chosen else "skipped"

    # ── Resolve empties ────────────────────────────────────────────────────────
    for entry in empties:
        chosen = _empty_resolver(entry["folder"])
        entry["artist"] = chosen
        entry["status"] = "resolved" if chosen else "skipped"

    # ── Build move plan ────────────────────────────────────────────────────────
    to_move = []
    skipped = []
    results = []

    for entry in album_data:
        artist = entry.get("artist")
        if not artist or entry["status"] == "skipped":
            entry["dest"]   = ""
            entry["status"] = "skipped — no artist"
            skipped.append(entry)
            results.append(entry)
            continue

        artist_clean  = sanitise_folder_name(artist)
        artist_folder = folder / artist_clean
        dest          = artist_folder / entry["folder"].name

        entry["artist"]       = artist
        entry["artist_clean"] = artist_clean
        entry["dest"]         = str(dest)

        if entry["folder"].parent == artist_folder:
            entry["status"] = "already correct"
            skipped.append(entry)
            results.append(entry)
            continue

        if dest.exists():
            entry["status"] = "skipped — destination already exists"
            skipped.append(entry)
            results.append(entry)
            continue

        entry["status"] = "pending"
        to_move.append(entry)
        results.append(entry)

    if not apply:
        report_path = write_report(results, SCRIPT_DIR / "reports", dry_run=True)
        return {"moved": 0, "pending": len(to_move), "skipped": len(skipped),
                "errors": 0, "results": results, "report_path": report_path}

    # ── Apply ──────────────────────────────────────────────────────────────────
    moved  = 0
    errors = 0

    for i, entry in enumerate(to_move):
        if progress_callback:
            progress_callback(i + 1, len(to_move), entry["album"])
        src           = entry["folder"]
        artist_folder = folder / entry["artist_clean"]
        dest          = artist_folder / entry["folder"].name
        try:
            artist_folder.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            entry["status"] = "moved"
            entry["dest"]   = str(dest)
            log(f"  ✓  {entry['album']} → {entry['artist_clean']}/")
            moved += 1
        except Exception as e:
            log(f"  !  Error moving {entry['album']}: {e}")
            entry["status"] = f"error: {e}"
            errors += 1

    report_path = write_report(results, SCRIPT_DIR / "reports", dry_run=False)

    return {"moved": moved, "pending": 0, "skipped": len(skipped),
            "errors": errors, "results": results, "report_path": report_path}


# ══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT  ← .cmd launchers call this; GUI does not
# ══════════════════════════════════════════════════════════════════════════════

def main():
    interactive_options([])

    DRY_RUN  = "--apply" not in sys.argv
    PICK_DIR = "--pick"  in sys.argv

    _path = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                  if a == "--path" and i+1 < len(sys.argv)), None)

    # ── Determine folder to scan ───────────────────────────────────────────────
    if _path:
        root = Path(_path.strip('"'))
    else:
        root = pick_folder("Select folder to sort albums into artist subfolders")
        if not root:
            print("\n  No folder selected. Exiting.\n")
            return

    if not root.exists() or not root.is_dir():
        print(f"ERROR: Folder not found: {root}")
        sys.exit(1)

    mode = "DRY RUN — nothing will be moved" if DRY_RUN else "LIVE — albums will be moved"
    print(f"\n{'='*65}")
    print(f"Sort Albums Into Artist Folders  v1.5")
    print(f"{'='*65}")
    print(f"  Mode   : {mode}")
    print(f"  Folder : {root}")
    print(f"{'='*65}\n")

    print("  Scanning...\n")

    try:
        result = run_sort_albums_to_artists(
            folder=root,
            apply=False,
            conflict_resolver=prompt_conflict,
            empty_resolver=prompt_empty,
        )
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    results = result["results"]
    to_move = [r for r in results if r["status"] == "pending"]
    skipped = [r for r in results if r["status"] != "pending"]

    # ── Preview ────────────────────────────────────────────────────────────────
    if not to_move:
        print("  Nothing to move.\n")
    else:
        print(f"\n  {len(to_move)} album(s) to move (dry run):")
        print()
        by_artist: dict[str, list] = {}
        for entry in to_move:
            by_artist.setdefault(entry["artist_clean"], []).append(entry)
        for artist, albums in sorted(by_artist.items()):
            print(f"  → {artist}/")
            for a in albums:
                print(f"       {a['album']}")
            print()

    if skipped:
        print(f"  {len(skipped)} album(s) skipped:")
        for s in skipped:
            print(f"    {s['album']} — {s['status']}")
        print()

    if DRY_RUN:
        print("  Dry run complete. Run with --apply to move.\n")
        if result["report_path"]:
            print(f"  Report: {result['report_path']}\n")
        return

    if not to_move:
        if result["report_path"]:
            print(f"  Report: {result['report_path']}\n")
        return

    # ── Confirm ────────────────────────────────────────────────────────────────
    confirm = input(f"  Move {len(to_move)} album(s) into artist folders? (y/n): ").strip().lower()
    while confirm not in ("y", "n"):
        confirm = input("  Please enter y or n: ").strip().lower()
    if confirm != "y":
        print("  Aborted.\n")
        return

    # ── Apply ──────────────────────────────────────────────────────────────────
    moved  = 0
    errors = 0

    for entry in to_move:
        src           = entry["folder"]
        artist_folder = root / entry["artist_clean"]
        dest          = artist_folder / entry["folder"].name
        try:
            artist_folder.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            entry["status"] = "moved"
            entry["dest"]   = str(dest)
            moved += 1
        except Exception as e:
            print(f"  [ERROR] {entry['album']}: {e}")
            entry["status"] = f"error: {e}"
            errors += 1

    print(f"\n  {'='*40}")
    print(f"  Moved  : {moved}")
    print(f"  Skipped: {len(skipped)}")
    print(f"  Errors : {errors}")
    print(f"  {'='*40}\n")

    write_report(results, SCRIPT_DIR / "reports", dry_run=False)


if __name__ == "__main__":
    main()
