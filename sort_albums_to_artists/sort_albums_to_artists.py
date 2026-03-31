"""
Sort Albums Into Artist Folders  v1.0
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

try:
    from mutagen import File as MutagenFile
except ImportError:
    print("ERROR: 'mutagen' is not installed.")
    print("       Run:  pip install mutagen")
    sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────
DEFAULT_FOLDER  = r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\SD\Music"
REPORTS_FOLDER  = r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\tools\reports"
SUPPORTED_EXT   = {".mp3", ".flac", ".aac", ".m4a"}

# ── Flags ──────────────────────────────────────────────────────────────────────
DRY_RUN  = "--apply" not in sys.argv
PICK_DIR = "--pick"  in sys.argv

_path = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
              if a == "--path" and i+1 < len(sys.argv)), None)


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


def sanitise_folder_name(name: str) -> str:
    """Remove characters illegal in Windows folder names."""
    for ch in r'<>:"/\\|?*':
        name = name.replace(ch, "")
    return name.strip(". ")


def get_music_files(folder: Path) -> list[Path]:
    """Return all music files directly in this folder."""
    return sorted(
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
    )


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

def pick_folder() -> Path | None:
    """Open a native folder-picker dialog. Returns selected Path or None."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print("ERROR: tkinter is not available on this system.")
        sys.exit(1)

    root_tk = tk.Tk()
    root_tk.withdraw()
    root_tk.attributes("-topmost", True)
    folder = filedialog.askdirectory(
        title="Select folder containing album subfolders",
        parent=root_tk,
    )
    root_tk.destroy()
    return Path(folder) if folder else None


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
    except Exception as e:
        print(f"  WARNING: Could not write report: {e}\n")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    reports_dir = Path(REPORTS_FOLDER)

    # ── Determine folder to scan ───────────────────────────────────────────────
    if PICK_DIR or (not _path and not PICK_DIR):
        # Always open picker if no path specified — more useful than a hardcoded default
        root = pick_folder()
        if not root:
            print("\n  No folder selected. Exiting.\n")
            return
    elif _path:
        root = Path(_path.strip('"'))
    else:
        root = Path(DEFAULT_FOLDER)

    if not root.exists() or not root.is_dir():
        print(f"ERROR: Folder not found: {root}")
        sys.exit(1)

    mode = "DRY RUN — nothing will be moved" if DRY_RUN else "LIVE — albums will be moved"
    print(f"\n{'='*65}")
    print(f"Sort Albums Into Artist Folders  v1.0")
    print(f"{'='*65}")
    print(f"  Mode   : {mode}")
    print(f"  Folder : {root}")
    print(f"{'='*65}\n")

    # ── Find album subfolders (direct children that contain music) ─────────────
    print("  Scanning...\n")
    album_folders = sorted(
        d for d in root.iterdir()
        if d.is_dir() and get_all_music_files(d)
    )

    if not album_folders:
        print("  No album folders found (subfolders containing music files).\n")
        return

    print(f"  Found {len(album_folders)} album folder(s).\n")

    # ── Detect artist for each album ───────────────────────────────────────────
    album_data = []
    conflicts  = []
    empties    = []

    for folder in album_folders:
        artist, status = get_artist_for_album(folder)
        entry = {"folder": folder, "album": folder.name, "artist": artist, "status": status}
        album_data.append(entry)
        if status == "conflict":
            conflicts.append(entry)
        elif status in ("empty", "no_files"):
            empties.append(entry)

    ok_count = sum(1 for a in album_data if a["status"] == "ok")
    print(f"  Artist tag clear : {ok_count}")
    print(f"  Conflicts        : {len(conflicts)}")
    print(f"  No artist tag    : {len(empties)}")
    print()

    # ── Resolve conflicts ──────────────────────────────────────────────────────
    if conflicts:
        print(f"  {len(conflicts)} conflict(s) need your input:\n")
        for entry in conflicts:
            all_files = get_all_music_files(entry["folder"])
            chosen = prompt_conflict(entry["folder"], all_files)
            entry["artist"] = chosen
            entry["status"] = "resolved" if chosen else "skipped"

    # ── Resolve empties ────────────────────────────────────────────────────────
    if empties:
        print(f"\n  {len(empties)} album(s) have no artist tag:\n")
        for entry in empties:
            chosen = prompt_empty(entry["folder"])
            entry["artist"] = chosen
            entry["status"] = "resolved" if chosen else "skipped"

    # ── Build move plan ────────────────────────────────────────────────────────
    to_move  = []
    skipped  = []
    results  = []

    for entry in album_data:
        artist = entry.get("artist")
        if not artist or entry["status"] == "skipped":
            entry["dest"]   = ""
            entry["status"] = "skipped — no artist"
            skipped.append(entry)
            results.append(entry)
            continue

        artist_clean  = sanitise_folder_name(artist)
        artist_folder = root / artist_clean
        dest          = artist_folder / entry["folder"].name

        entry["artist"]       = artist
        entry["artist_clean"] = artist_clean
        entry["dest"]         = str(dest)

        # Skip if already in the right place
        if entry["folder"].parent == artist_folder:
            entry["status"] = "already correct"
            skipped.append(entry)
            results.append(entry)
            continue

        # Collision check — dest already exists
        if dest.exists():
            entry["status"] = "skipped — destination already exists"
            skipped.append(entry)
            results.append(entry)
            continue

        entry["status"] = "would move" if DRY_RUN else "pending"
        to_move.append(entry)
        results.append(entry)

    # ── Preview ────────────────────────────────────────────────────────────────
    if not to_move:
        print("  Nothing to move.\n")
    else:
        print(f"\n  {len(to_move)} album(s) to move"
              + (" (dry run):" if DRY_RUN else ":"))
        print()

        # Group by artist for a cleaner display
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
        write_report(results, reports_dir, dry_run=True)
        return

    if not to_move:
        write_report(results, reports_dir, dry_run=False)
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
        src          = entry["folder"]
        artist_folder = root / entry["artist_clean"]
        dest         = artist_folder / entry["folder"].name

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

    write_report(results, reports_dir, dry_run=False)


if __name__ == "__main__":
    main()
