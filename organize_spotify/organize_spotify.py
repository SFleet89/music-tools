#!/usr/bin/env python3
"""
organize_spotify.py  v1.1  2026-06-17

Reads audio tags from Spotify downloads (organised by playlist folders) and
re-organises them into  AlbumArtist / Album  folder structure inside a staging
folder.  Nothing is moved unless --apply is passed.

Usage
-----
  python organize_spotify.py --pick-source --pick-dest [--apply]
  python organize_spotify.py --path-source "C:\\..." --path-dest "C:\\..." [--apply]

Flags
-----
  --pick-source   Open a folder dialog to choose the Spotify/Streamrip source
  --path-source   Supply source path directly (quoted)
  --pick-dest     Open a folder dialog to choose the staging destination
  --path-dest     Supply destination path directly (quoted)
  --apply         Actually move files (default: dry run)

Requirements
------------
  pip install mutagen
"""

import sys
import csv
import shutil
import re
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Flag parsing
# ---------------------------------------------------------------------------
DRY_RUN      = "--apply"       not in sys.argv
PICK_SOURCE  = "--pick-source" in sys.argv
PICK_DEST    = "--pick-dest"   in sys.argv

def _get_flag(flag: str) -> str | None:
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1].strip('"')
    return None

PATH_SOURCE = _get_flag("--path-source")
PATH_DEST   = _get_flag("--path-dest")

AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".aac", ".wav", ".wma", ".ape", ".alac"}

SCRIPT_DIR     = Path(__file__).parent
REPORTS_FOLDER = SCRIPT_DIR / "reports"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pick_folder(title: str) -> Path | None:
    import tkinter as tk
    from tkinter import filedialog
    root_tk = tk.Tk()
    root_tk.withdraw()
    root_tk.attributes("-topmost", True)
    folder = filedialog.askdirectory(title=title)
    root_tk.destroy()
    return Path(folder) if folder else None


def sanitize(name: str) -> str:
    """Remove/replace characters that are invalid in Windows folder names."""
    name = name.strip()
    # Replace colon with space-dash-space (looks natural for album subtitles,
    # e.g. "Movie: Subtitle" → "Movie - Subtitle")
    name = name.replace(':', ' - ')
    # Replace remaining invalid Windows path characters
    name = re.sub(r'[\\/*?"<>|]', '_', name)
    # Collapse multiple spaces
    name = re.sub(r'\s{2,}', ' ', name)
    # Strip trailing dots/spaces (Windows doesn't allow them)
    name = name.rstrip('. ')
    return name or "Unknown"


def get_tags(file: Path) -> dict:
    """Return a dict with albumartist, album, title, tracknumber from audio tags."""
    result = {
        "albumartist": "Unknown Artist",
        "album":       "Unknown Album",
        "title":       file.stem,
        "tracknumber": "",
    }
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(str(file), easy=True)
        if audio is None:
            return result

        def first(tag):
            val = audio.tags.get(tag) if audio.tags else None
            return str(val[0]).strip() if val else ""

        albumartist = first("albumartist") or first("artist") or "Unknown Artist"
        album       = first("album")       or "Unknown Album"
        title       = first("title")       or file.stem
        tracknumber = first("tracknumber") or ""

        result["albumartist"] = albumartist
        result["album"]       = album
        result["title"]       = title
        result["tracknumber"] = tracknumber
    except Exception as e:
        result["_tag_error"] = str(e)
    return result


def dest_path_for(file: Path, dest_root: Path, tags: dict) -> Path:
    """Build the target path: dest_root / AlbumArtist / Album / filename."""
    artist_dir = sanitize(tags["albumartist"])
    album_dir  = sanitize(tags["album"])
    return dest_root / artist_dir / album_dir / file.name


def unique_path(path: Path) -> Path:
    """If path already exists, append (1), (2) … until unique."""
    if not path.exists():
        return path
    stem   = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def write_report(rows: list[dict], dry_run: bool) -> Path:
    REPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix    = "dry" if dry_run else "applied"
    out_path  = REPORTS_FOLDER / f"organize_spotify_{suffix}_{timestamp}.csv"

    fieldnames = ["status", "source_file", "destination", "albumartist", "album", "title", "note"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  organize_spotify.py  v1.1")
    print(f"  Mode : {'DRY RUN — no changes will be made' if DRY_RUN else 'APPLY — files will be moved'}")
    print("=" * 60)

    # --- Resolve source folder ---
    if PICK_SOURCE:
        source = pick_folder("Select Spotify/Streamrip source folder")
        if not source:
            print("No source folder selected. Exiting.")
            sys.exit(0)
    elif PATH_SOURCE:
        source = Path(PATH_SOURCE)
    else:
        print("ERROR: No source folder specified.")
        print("  Use --pick-source  or  --path-source \"C:\\path\\to\\folder\"")
        sys.exit(1)

    if not source.exists() or not source.is_dir():
        print(f"ERROR: Source folder not found: {source}")
        sys.exit(1)

    # --- Resolve destination folder ---
    if PICK_DEST:
        dest = pick_folder("Select staging destination folder")
        if not dest:
            print("No destination folder selected. Exiting.")
            sys.exit(0)
    elif PATH_DEST:
        dest = Path(PATH_DEST)
    else:
        # Default: source\Organized\
        dest = source / "Organized"
        print(f"  Destination not specified — defaulting to: {dest}")

    # Destination doesn't need to exist yet; we'll create it.
    # But if the path has a parent that doesn't exist, bail early.
    if not dest.parent.exists():
        print(f"ERROR: Destination parent folder not found: {dest.parent}")
        sys.exit(1)

    # Guard: don't let dest be inside source (causes infinite recursion)
    try:
        dest.resolve().relative_to(source.resolve())
        inside = True
    except ValueError:
        inside = False

    if inside:
        # dest IS inside source — that's fine (default behaviour), but warn
        print(f"  Note: destination is inside source folder — playlist subfolders will be skipped.\n")

    print(f"  Source      : {source}")
    print(f"  Destination : {dest}")
    print()

    # --- Collect audio files ---
    all_files = [f for f in source.rglob("*") if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS]

    # Exclude anything already inside the destination folder
    dest_resolved = dest.resolve() if dest.exists() else dest
    all_files = [
        f for f in all_files
        if not str(f.resolve()).startswith(str(dest_resolved))
    ]

    if not all_files:
        print("No audio files found in source folder. Exiting.")
        sys.exit(0)

    print(f"  Found {len(all_files)} audio file(s). Reading tags…\n")

    rows = []
    tag_errors = 0

    for file in sorted(all_files):
        tags   = get_tags(file)
        target = dest_path_for(file, dest, tags)

        note = tags.get("_tag_error", "")

        rows.append({
            "status":      "pending",
            "source_file": str(file),
            "destination": str(target),
            "albumartist": tags["albumartist"],
            "album":       tags["album"],
            "title":       tags["title"],
            "note":        f"tag error: {note}" if note else "",
        })

        if note:
            tag_errors += 1

    # --- Summary preview ---
    print(f"  {'[DRY RUN] ' if DRY_RUN else ''}Plan: move {len(rows)} file(s)")
    if tag_errors:
        print(f"  Warning: {tag_errors} file(s) had tag-read errors — will use filename as title, 'Unknown' for artist/album.")
    print()

    # Show first 20 planned moves
    preview_count = min(20, len(rows))
    print(f"  First {preview_count} planned moves:")
    for r in rows[:preview_count]:
        src_rel = Path(r["source_file"]).name
        dst_rel = Path(r["destination"]).relative_to(dest) if Path(r["destination"]).is_relative_to(dest) else r["destination"]
        print(f"    {src_rel}  →  {dst_rel}")
    if len(rows) > preview_count:
        print(f"    … and {len(rows) - preview_count} more (see report CSV)")
    print()

    # --- Confirm in apply mode ---
    if not DRY_RUN:
        confirm = input(f"  Move {len(rows)} file(s) to staging folder? (y/n): ").strip().lower()
        while confirm not in ("y", "n"):
            confirm = input("  Please enter y or n: ").strip().lower()
        if confirm != "y":
            print("  Aborted. No files were moved.")
            sys.exit(0)
        print()

    # --- Execute (or simulate) ---
    moved   = 0
    skipped = 0
    errors  = 0

    for r in rows:
        src    = Path(r["source_file"])
        target = Path(r["destination"])

        if DRY_RUN:
            r["status"] = "dry_run"
            moved += 1
            continue

        try:
            target = unique_path(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(target))
            r["status"]      = "moved"
            r["destination"] = str(target)
            moved += 1
        except Exception as e:
            r["status"] = "error"
            r["note"]   = str(e)
            errors += 1
            print(f"  ERROR moving {src.name}: {e}")

    # --- Write report ---
    report_path = write_report(rows, DRY_RUN)

    print()
    print("  ── Results ─────────────────────────────────────")
    if DRY_RUN:
        print(f"  Files that would be moved : {moved}")
    else:
        print(f"  Moved   : {moved}")
        print(f"  Errors  : {errors}")
    print(f"  Report  : {report_path}")
    print()
    if DRY_RUN:
        print("  This was a DRY RUN. Re-run with --apply to move files.")
    else:
        print("  Done.")


if __name__ == "__main__":
    main()
