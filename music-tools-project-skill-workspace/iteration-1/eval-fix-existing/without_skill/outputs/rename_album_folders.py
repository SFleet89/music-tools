"""
Album Folder Renamer  v2.3
===========================
Reads the album tag from music files in each subfolder and renames the folder
to match the album name.

New in v2.0:
  - Reports saved after every run (dry and live)
  - Track titles shown in conflict prompt to help identify the right album
  - --filter flag: skip folders already correctly named (faster on large libraries)
  - --depth N flag: only rename at a specific folder depth (e.g. 2 for Artist/Album)
  - Cross-folder collision detection before renaming

Conflict handling:
  - If all files agree on the album name → rename automatically
  - If files disagree → prompted to choose, with track titles shown per option
  - If no album tag is found → folder left unchanged with a warning

Nothing is renamed until you confirm. Dry run by default.

Usage:
    python rename_album_folders.py                       # dry run on default folder
    python rename_album_folders.py --apply               # rename for real
    python rename_album_folders.py --pick                # pick folder(s) with a dialog
    python rename_album_folders.py --pick --apply        # pick and rename
    python rename_album_folders.py --path "C:\\Music"    # override folder
    python rename_album_folders.py --filter              # skip already-correct folders
    python rename_album_folders.py --depth 2             # only rename at depth 2
    python rename_album_folders.py --filter --depth 2 --apply

Requirements:
    pip install mutagen
    tkinter (built into Python — no install needed)
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

# ── Parse flags ────────────────────────────────────────────────────────────────
DRY_RUN    = "--apply"  not in sys.argv
PICK_DIR   = "--pick"   in sys.argv
FILTER_OK  = "--filter" in sys.argv   # skip folders already correctly named

_path  = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
               if a == "--path"  and i+1 < len(sys.argv)), None)
_depth = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
               if a == "--depth" and i+1 < len(sys.argv)), None)
MAX_DEPTH  = int(_depth) if _depth and _depth.isdigit() else None


# ══════════════════════════════════════════════════════════════════════════════
#  METADATA HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def read_file_tags(path: Path) -> dict:
    """Read album, title, and tracknumber from a music file."""
    result = {"album": None, "title": None, "tracknumber": None}
    try:
        f = MutagenFile(path, easy=True)
        if f:
            for key in ("album", "title", "tracknumber"):
                val = f.get(key)
                if val:
                    result[key] = val[0].strip() or None
    except Exception:
        pass
    return result


def sanitise_folder_name(name: str) -> str:
    """Remove characters illegal in Windows folder names."""
    for ch in r'<>:"/\\|?*':
        name = name.replace(ch, "")
    return name.strip(". ")


def get_music_files(folder: Path) -> list[Path]:
    """Return all music files directly in this folder (not recursive)."""
    return sorted(
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
    )


def folder_depth(folder: Path, root: Path) -> int:
    """Return depth of folder relative to root (root children = 1)."""
    try:
        return len(folder.relative_to(root).parts)
    except ValueError:
        return 0




# Matches CD/Disc/Disk subfolder names: CD1, CD 1, Disc2, Disk 10 etc.
_CD_RE = re.compile(r'^(cd|disc|disk)\s*\d+$', re.IGNORECASE)


def get_cd_subfolders(folder: Path) -> list[Path]:
    """
    If ALL subdirectories of folder match the CD/Disc/Disk pattern, return
    them sorted. Otherwise return an empty list.
    Only triggers when every subdir looks like a disc folder — prevents false
    positives on folders with one oddly-named subfolder.
    """
    try:
        subdirs = [d for d in folder.iterdir() if d.is_dir()]
    except Exception:
        return []
    if not subdirs:
        return []
    cd_dirs = [d for d in subdirs if _CD_RE.match(d.name)]
    return sorted(cd_dirs) if len(cd_dirs) == len(subdirs) else []


def get_album_for_cd_parent(folder: Path) -> tuple[str | None, str, list[dict]]:
    """
    Read album tags from all music files across all CD subfolders combined.
    Returns same (album, status, file_tags) signature as get_album_for_folder.
    """
    cd_dirs = get_cd_subfolders(folder)
    if not cd_dirs:
        return None, "no_files", []

    all_file_tags = []
    for cd in cd_dirs:
        for f in get_music_files(cd):
            tags = read_file_tags(f)
            all_file_tags.append({"file": f, **tags})

    if not all_file_tags:
        return None, "empty", all_file_tags

    albums = [t["album"] for t in all_file_tags if t["album"]]
    if not albums:
        return None, "empty", all_file_tags

    counts = Counter(albums)
    if len(counts) == 1:
        return counts.most_common(1)[0][0], "ok", all_file_tags
    return None, "conflict", all_file_tags

# ══════════════════════════════════════════════════════════════════════════════
#  ALBUM DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def get_album_for_folder(folder: Path) -> tuple[str | None, str, list[dict]]:
    """
    Read tags from all music files in folder.
    Returns (album_name, status, file_tags) where:
      status = 'ok' | 'conflict' | 'empty' | 'no_files'
      file_tags = list of {file, album, title, tracknumber}
    """
    files = get_music_files(folder)
    if not files:
        return None, "no_files", []

    file_tags = []
    for f in files:
        tags = read_file_tags(f)
        file_tags.append({"file": f, **tags})

    albums = [t["album"] for t in file_tags if t["album"]]
    if not albums:
        return None, "empty", file_tags

    counts = Counter(albums)
    if len(counts) == 1:
        return counts.most_common(1)[0][0], "ok", file_tags
    return None, "conflict", file_tags


# ══════════════════════════════════════════════════════════════════════════════
#  CONFLICT PROMPT
# ══════════════════════════════════════════════════════════════════════════════

def prompt_conflict(folder: Path, file_tags: list[dict]) -> str | None:
    """
    Show conflicting album tags with track titles and ask the user to choose.
    Returns chosen album name, or None to skip.
    """
    # Group files by album tag
    by_album: dict[str, list[dict]] = {}
    for t in file_tags:
        if t["album"]:
            by_album.setdefault(t["album"], []).append(t)

    print(f"\n  CONFLICT in: {folder.name}")
    print(f"  Path       : {folder}")
    print(f"  {len(by_album)} different album tags found:\n")

    options = sorted(by_album.items(), key=lambda x: -len(x[1]))
    for i, (album, tracks) in enumerate(options, start=1):
        print(f"    [{i}] {album}  ({len(tracks)} file(s))")
        # Show up to 4 track titles to help identify the album
        sorted_tracks = sorted(tracks, key=lambda t: t.get("tracknumber") or "")
        for t in sorted_tracks[:4]:
            title = t.get("title") or t["file"].name
            tn    = t.get("tracknumber")
            prefix = f"{tn}. " if tn else "    "
            print(f"         {prefix}{title}")
        if len(tracks) > 4:
            print(f"         ... and {len(tracks)-4} more")
        print()

    print(f"    [s] Skip this folder")
    print(f"    [t] Type a custom name")

    while True:
        choice = input("  Your choice: ").strip().lower()
        if choice == "s":
            return None
        if choice == "t":
            custom = input("  Enter album name: ").strip()
            return custom if custom else None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        except ValueError:
            pass
        print("  Invalid — enter a number, 's' to skip, or 't' to type.")


# ══════════════════════════════════════════════════════════════════════════════
#  SCAN
# ══════════════════════════════════════════════════════════════════════════════

def find_album_folders(root: Path) -> list[dict]:
    """
    Walk tree, find folders to rename. Handles two structures:
      1. Normal: folder contains music files directly
      2. Multi-CD: folder contains only CD1/CD2/Disc1/Disc2 subfolders

    For multi-CD folders the PARENT is renamed — the CD subfolders are left
    untouched. Traversal is depth-first (shallow before deep) so parents are
    always evaluated before their children, which is required for correct
    multi-CD detection.

    Respects MAX_DEPTH and FILTER_OK flags.
    """
    # Collect all subdirectories, sorted shallowest-first so parents are
    # always visited before their children.
    all_dirs = sorted(
        (d for d in root.rglob("*") if d.is_dir()),
        key=lambda d: len(d.parts)
    )

    candidates  = []
    skip_folders: set[Path] = set()   # CD subfolders claimed by a parent

    for folder in all_dirs:
        if folder in skip_folders:
            continue

        # Depth filter
        if MAX_DEPTH is not None:
            if folder_depth(folder, root) != MAX_DEPTH:
                continue

        try:
            rel = str(folder.relative_to(root))
        except ValueError:
            rel = str(folder)

        # ── Multi-CD check: does this folder contain only CD subfolders? ──
        cd_dirs = get_cd_subfolders(folder)
        if cd_dirs:
            # Mark all CD subfolders so they are skipped later
            for cd in cd_dirs:
                skip_folders.add(cd)

            album, status, file_tags = get_album_for_cd_parent(folder)

            if FILTER_OK and status == "ok" and album:
                if sanitise_folder_name(album) == folder.name:
                    continue

            all_files = [t["file"] for t in file_tags]
            candidates.append({
                "folder":    folder,
                "rel":       rel,
                "status":    status,
                "album":     album,
                "file_tags": file_tags,
                "files":     all_files,
                "current":   folder.name,
                "new_name":  None,
                "multi_cd":  True,
                "cd_dirs":   cd_dirs,
            })
            continue

        # ── Normal check: does this folder contain music files directly? ──
        files = get_music_files(folder)
        if not files:
            continue

        album, status, file_tags = get_album_for_folder(folder)

        if FILTER_OK and status == "ok" and album:
            if sanitise_folder_name(album) == folder.name:
                continue

        candidates.append({
            "folder":    folder,
            "rel":       rel,
            "status":    status,
            "album":     album,
            "file_tags": file_tags,
            "files":     files,
            "current":   folder.name,
            "new_name":  None,
            "multi_cd":  False,
        })

    return candidates


# ══════════════════════════════════════════════════════════════════════════════
#  FOLDER PICKER
# ══════════════════════════════════════════════════════════════════════════════

def pick_folders() -> list[Path]:
    """Open a native folder-picker dialog. Allows picking multiple folders."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except ImportError:
        print("ERROR: tkinter is not available on this system.")
        sys.exit(1)

    root_tk = tk.Tk()
    root_tk.withdraw()
    root_tk.attributes("-topmost", True)

    selected = []
    while True:
        folder = filedialog.askdirectory(
            title=f"Select folder to scan (selected: {len(selected)})",
            parent=root_tk,
        )
        if not folder:
            break
        p = Path(folder)
        if p not in selected:
            selected.append(p)
        if not messagebox.askyesno(
            "Add another folder?",
            f"Added:\n{p.name}\n\nAdd another folder to scan?",
            parent=root_tk,
        ):
            break

    root_tk.destroy()
    return selected


# ══════════════════════════════════════════════════════════════════════════════
#  REPORT
# ══════════════════════════════════════════════════════════════════════════════

def write_report(candidates: list[dict], reports_dir: Path, dry_run: bool):
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix    = "dry" if dry_run else "applied"
        out_path  = reports_dir / f"rename_album_folders_{suffix}_{timestamp}.csv"

        fieldnames = ["Relative Path", "Current Name", "New Name",
                      "Album Tag", "Status", "Files", "Multi-CD"]
        rows = []
        for c in candidates:
            album    = c.get("album") or ""
            new_name = c.get("new_name") or (sanitise_folder_name(album) if album else "")
            status   = c.get("status", "")

            if dry_run:
                if album and new_name and new_name != c["current"]:
                    label = f"Would rename to: {new_name}"
                elif album and new_name == c["current"]:
                    label = "Already correct"
                elif status == "skipped":
                    label = "Skipped (conflict — no choice made)"
                elif status == "empty":
                    label = "No album tag — left unchanged"
                else:
                    label = status
            else:
                label = status

            rows.append({
                "Relative Path": c["rel"],
                "Current Name":  c["current"],
                "New Name":      new_name,
                "Album Tag":     album,
                "Status":        label,
                "Files":         len(c.get("files", [])),
                "Multi-CD":      "Yes" if c.get("multi_cd") else "No",
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

    # ── Determine folders to scan ──────────────────────────────────────────────
    if PICK_DIR:
        roots = pick_folders()
        if not roots:
            print("\n  No folders selected. Exiting.\n")
            return
    elif _path:
        roots = [Path(_path.strip('"'))]
    else:
        roots = [Path(DEFAULT_FOLDER)]

    for r in roots:
        if not r.exists() or not r.is_dir():
            print(f"ERROR: Folder not found: {r}")
            sys.exit(1)

    # ── Header ─────────────────────────────────────────────────────────────────
    mode = "DRY RUN — nothing will be renamed" if DRY_RUN else "LIVE — folders will be renamed"
    print(f"\n{'='*65}")
    print(f"Album Folder Renamer  v2.3")
    print(f"{'='*65}")
    print(f"  Mode      : {mode}")
    for r in roots:
        print(f"  Folder    : {r}")
    if MAX_DEPTH:
        print(f"  Depth     : {MAX_DEPTH} level(s) only")
    if FILTER_OK:
        print(f"  Filter    : skipping already-correct folders")
    print(f"{'='*65}\n")

    # ── Scan ───────────────────────────────────────────────────────────────────
    print("  Scanning...\n")
    candidates = []
    for root in roots:
        candidates.extend(find_album_folders(root))
    display_root = roots[0]

    if not candidates:
        if FILTER_OK:
            print("  All folders are already correctly named — nothing to do.\n")
        else:
            print("  No folders with music files found.\n")
        return

    ok_folders       = [c for c in candidates if c["status"] == "ok"]
    conflict_folders = [c for c in candidates if c["status"] == "conflict"]
    empty_folders    = [c for c in candidates if c["status"] == "empty"]

    print(f"  Folders found      : {len(candidates)}")
    print(f"  Album tag clear    : {len(ok_folders)}")
    print(f"  Conflicts          : {len(conflict_folders)}")
    print(f"  No album tag       : {len(empty_folders)}")
    print()

    # ── Warnings for empty ─────────────────────────────────────────────────────
    if empty_folders:
        print(f"  WARNING: {len(empty_folders)} folder(s) have no album tag — will be left unchanged:")
        for c in empty_folders:
            print(f"    {c['rel']}")
        print()

    # ── Resolve conflicts ──────────────────────────────────────────────────────
    if conflict_folders:
        print(f"  {len(conflict_folders)} conflict(s) need your input:\n")
        for c in conflict_folders:
            chosen = prompt_conflict(c["folder"], c["file_tags"])
            c["album"]  = chosen
            c["status"] = "resolved" if chosen else "skipped"

    # ── Cross-folder collision check ───────────────────────────────────────────
    # Build a map of (parent_path, proposed_new_name) → list of candidates
    # If two different folders would rename to the same name under the same parent,
    # flag them before any renaming happens.
    collision_map: dict[tuple, list] = {}
    for c in candidates:
        album = c.get("album")
        if not album or c["status"] not in ("ok", "resolved"):
            continue
        new_name = sanitise_folder_name(album)
        if new_name == c["current"]:
            continue
        key = (c["folder"].parent, new_name)
        collision_map.setdefault(key, []).append(c)

    collisions = {k: v for k, v in collision_map.items() if len(v) > 1}
    if collisions:
        print(f"  WARNING: {len(collisions)} naming collision(s) detected — these folders")
        print(f"  would rename to the same name under the same parent and will be skipped:\n")
        for (parent, name), group in collisions.items():
            print(f"    Target name: {name}  (in {parent})")
            for c in group:
                print(f"      {c['current']}")
                c["status"] = "skipped — naming collision"
        print()

    # ── Preview renames ────────────────────────────────────────────────────────
    to_rename = []
    for c in candidates:
        album = c.get("album")
        if not album or c["status"] not in ("ok", "resolved"):
            continue
        new_name = sanitise_folder_name(album)
        c["new_name"] = new_name
        if new_name != c["current"]:
            to_rename.append(c)
        else:
            c["status"] = "already correct"

    already_correct = [c for c in candidates if c.get("status") == "already correct"]

    if not to_rename:
        print("  All folders already match their album tags. Nothing to rename.\n")
    else:
        print(f"\n  {len(to_rename)} folder(s) to rename"
              + (" (dry run):" if DRY_RUN else ":"))
        print()
        for c in to_rename:
            cd_note = f"  ← multi-CD ({len(c.get('cd_dirs', []))} discs)" if c.get("multi_cd") else ""
            print(f"  [{c['rel']}]{cd_note}")
            print(f"    Before : {c['current']}")
            print(f"    After  : {c['new_name']}")
            print()

    if already_correct:
        print(f"  {len(already_correct)} folder(s) already named correctly — skipped.")
        print()

    if DRY_RUN:
        print(f"  Dry run complete. Run with --apply to rename.\n")
        write_report(candidates, reports_dir, dry_run=True)
        return

    if not to_rename:
        write_report(candidates, reports_dir, dry_run=False)
        return

    # ── Confirm ────────────────────────────────────────────────────────────────
    confirm = input(f"  Rename {len(to_rename)} folder(s)? (y/n): ").strip().lower()
    while confirm not in ("y", "n"):
        confirm = input("  Please enter y or n: ").strip().lower()
    if confirm != "y":
        print("  Aborted.\n")
        return

    # ── Apply ──────────────────────────────────────────────────────────────────
    renamed = 0
    errors  = 0

    for c in to_rename:
        new_path = c["folder"].parent / c["new_name"]

        # Same-parent collision check (safety net — cross-folder check above
        # handles most cases, but an existing folder could also be in the way)
        if new_path.exists() and new_path.resolve() != c["folder"].resolve():
            print(f"  [SKIP] Target already exists: {c['new_name']}")
            c["status"] = "skipped — target exists"
            continue

        try:
            shutil.move(str(c["folder"]), str(new_path))
            c["status"] = "renamed"
            renamed += 1
        except Exception as e:
            print(f"  [ERROR] {c['current']}: {e}")
            c["status"] = f"error: {e}"
            errors += 1

    print(f"\n  {'='*40}")
    print(f"  Renamed : {renamed}")
    print(f"  Errors  : {errors}")
    print(f"  {'='*40}\n")

    write_report(candidates, reports_dir, dry_run=False)


if __name__ == "__main__":
    main()
