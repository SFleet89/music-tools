"""
Album Folder Renamer  v2.6
===========================
Reads the album tag from music files in each subfolder and renames the folder
to match the album name.

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

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import (
    SUPPORTED_EXTENSIONS as SUPPORTED_EXT,
    sanitise_folder_name,
    get_music_files,
    read_file_tags,
    config_organized_folder,
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


def folder_depth(folder: Path, root: Path) -> int:
    """Return depth of folder relative to root (root children = 1)."""
    try:
        return len(folder.relative_to(root).parts)
    except ValueError:
        return 0


# Matches CD/Disc/Disk subfolder names: CD1, CD 1, Disc2, Disk 10 etc.
_CD_RE = re.compile(r'^(cd|disc|disk)\s*\d+$', re.IGNORECASE)


def get_cd_subfolders(folder: Path) -> list:
    """
    If ALL subdirectories of folder match the CD/Disc/Disk pattern, return
    them sorted. Otherwise return an empty list.
    """
    try:
        subdirs = [d for d in folder.iterdir() if d.is_dir()]
    except Exception:
        return []
    if not subdirs:
        return []
    cd_dirs = [d for d in subdirs if _CD_RE.match(d.name)]
    return sorted(cd_dirs) if len(cd_dirs) == len(subdirs) else []


def get_album_for_cd_parent(folder: Path):
    """
    Read album tags from all music files across all CD subfolders combined.
    Returns (album, status, file_tags).
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

def get_album_for_folder(folder: Path):
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
#  CONFLICT PROMPT  (CLI only — GUI supplies its own resolver via callback)
# ══════════════════════════════════════════════════════════════════════════════

def prompt_conflict(folder: Path, file_tags: list) -> str:
    """
    Show conflicting album tags with track titles and ask the user to choose.
    Returns chosen album name, or None to skip.
    """
    by_album = {}
    for t in file_tags:
        if t["album"]:
            by_album.setdefault(t["album"], []).append(t)

    print(f"\n  CONFLICT in: {folder.name}")
    print(f"  Path       : {folder}")
    print(f"  {len(by_album)} different album tags found:\n")

    options = sorted(by_album.items(), key=lambda x: -len(x[1]))
    for i, (album, tracks) in enumerate(options, start=1):
        print(f"    [{i}] {album}  ({len(tracks)} file(s))")
        sorted_tracks = sorted(tracks, key=lambda t: t.get("tracknumber") or "")
        for t in sorted_tracks[:4]:
            title  = t.get("title") or t["file"].name
            tn     = t.get("tracknumber")
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

def find_album_folders(root: Path, max_depth: int = None, filter_ok: bool = False) -> list:
    """
    Walk tree, find folders to rename. Handles normal and multi-CD structures.
    """
    all_dirs = sorted(
        (d for d in root.rglob("*") if d.is_dir()),
        key=lambda d: len(d.parts),
    )

    candidates   = []
    skip_folders = set()

    for folder in all_dirs:
        if folder in skip_folders:
            continue

        if max_depth is not None:
            if folder_depth(folder, root) != max_depth:
                continue

        try:
            rel = str(folder.relative_to(root))
        except ValueError:
            rel = str(folder)

        cd_dirs = get_cd_subfolders(folder)
        if cd_dirs:
            for cd in cd_dirs:
                skip_folders.add(cd)

            album, status, file_tags = get_album_for_cd_parent(folder)

            if filter_ok and status == "ok" and album:
                if sanitise_folder_name(album) == folder.name:
                    continue

            candidates.append({
                "folder":    folder,
                "rel":       rel,
                "status":    status,
                "album":     album,
                "file_tags": file_tags,
                "files":     [t["file"] for t in file_tags],
                "current":   folder.name,
                "new_name":  None,
                "multi_cd":  True,
                "cd_dirs":   cd_dirs,
            })
            continue

        files = get_music_files(folder)
        if not files:
            continue

        album, status, file_tags = get_album_for_folder(folder)

        if filter_ok and status == "ok" and album:
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

def pick_folders() -> list:
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

def write_report(candidates: list, reports_dir: Path, dry_run: bool) -> "Path | None":
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

        return out_path
    except Exception as e:
        print(f"  WARNING: Could not write report: {e}\n")
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_rename_album_folders(
    folder: Path,
    apply: bool = False,
    filter_ok: bool = False,
    max_depth: int = None,
    conflict_resolver=None,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Scan folder and rename album subfolders to match their album tags.

    Args:
        folder:            Root folder to scan recursively.
        apply:             False = dry run; True = rename folders.
        filter_ok:         Skip folders already correctly named.
        max_depth:         Only rename at this folder depth (None = all depths).
        conflict_resolver: Optional callable(folder, file_tags) -> str|None.
                           Called when files disagree on the album name.
                           GUI supplies its own UI; CLI uses prompt_conflict().
                           If None, conflicts are flagged but skipped.
        progress_callback: Optional callable(current, total, message).
        log_callback:      Optional callable(message). Defaults to print().

    Returns:
        dict: renamed, skipped, errors, conflicts, results (list of candidate
              dicts), report_path (Path|None)

    Raises:
        ValueError: folder does not exist or is not a directory.
    """
    log = log_callback or print

    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    log("  Scanning...")
    candidates = find_album_folders(folder, max_depth=max_depth, filter_ok=filter_ok)

    if not candidates:
        log("  No folders with music files found.")
        return {"renamed": 0, "skipped": 0, "errors": 0, "conflicts": 0,
                "results": [], "report_path": None}

    if progress_callback:
        progress_callback(len(candidates), len(candidates), "Scan complete")

    ok_folders       = [c for c in candidates if c["status"] == "ok"]
    conflict_folders = [c for c in candidates if c["status"] == "conflict"]
    empty_folders    = [c for c in candidates if c["status"] == "empty"]

    log(f"  Folders found      : {len(candidates)}")
    log(f"  Album tag clear    : {len(ok_folders)}")
    log(f"  Conflicts          : {len(conflict_folders)}")
    log(f"  No album tag       : {len(empty_folders)}")

    # ── Resolve conflicts ──────────────────────────────────────────────────────
    for c in conflict_folders:
        if conflict_resolver:
            chosen    = conflict_resolver(c["folder"], c["file_tags"])
            c["album"]  = chosen
            c["status"] = "resolved" if chosen else "skipped"
        else:
            c["status"] = "skipped — conflict needs resolution"

    # ── Cross-folder collision check ───────────────────────────────────────────
    collision_map = {}
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
        log(f"  WARNING: {len(collisions)} naming collision(s) detected — will be skipped.")
        for (parent, name), group in collisions.items():
            for c in group:
                c["status"] = "skipped — naming collision"

    # ── Resolve proposed names ─────────────────────────────────────────────────
    to_rename = []
    for c in candidates:
        album = c.get("album")
        if not album or c["status"] not in ("ok", "resolved"):
            continue
        new_name      = sanitise_folder_name(album)
        c["new_name"] = new_name
        if new_name != c["current"]:
            to_rename.append(c)
        else:
            c["status"] = "already correct"

    log(f"  To rename          : {len(to_rename)}")

    # ── Dry run ────────────────────────────────────────────────────────────────
    if not apply:
        report_path = write_report(candidates, REPORTS_FOLDER, dry_run=True)
        if report_path:
            log(f"  Report saved: {report_path}")
        renamed    = sum(1 for c in candidates if c.get("new_name") and c["new_name"] != c["current"])
        return {
            "renamed":    0,
            "pending":    renamed,
            "skipped":    sum(1 for c in candidates if "skipped" in c.get("status", "")),
            "errors":     0,
            "conflicts":  len(conflict_folders),
            "results":    candidates,
            "report_path": report_path,
        }

    # ── Apply ──────────────────────────────────────────────────────────────────
    renamed = 0
    errors  = 0

    for i, c in enumerate(to_rename):
        if progress_callback:
            progress_callback(i + 1, len(to_rename), c["current"])

        new_path = c["folder"].parent / c["new_name"]

        if new_path.exists() and new_path.resolve() != c["folder"].resolve():
            log(f"  [SKIP] Target already exists: {c['new_name']}")
            c["status"] = "skipped — target exists"
            continue

        try:
            shutil.move(str(c["folder"]), str(new_path))
            c["status"] = "renamed"
            renamed += 1
        except Exception as e:
            log(f"  [ERROR] {c['current']}: {e}")
            c["status"] = f"error: {e}"
            errors += 1

    log(f"  Renamed: {renamed}  |  Skipped: {sum(1 for c in candidates if 'skipped' in c.get('status',''))}  |  Errors: {errors}")

    report_path = write_report(candidates, REPORTS_FOLDER, dry_run=False)
    if report_path:
        log(f"  Report saved: {report_path}")

    return {
        "renamed":    renamed,
        "pending":    0,
        "skipped":    sum(1 for c in candidates if "skipped" in c.get("status", "")),
        "errors":     errors,
        "conflicts":  len(conflict_folders),
        "results":    candidates,
        "report_path": report_path,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT  ← .cmd launchers call this; GUI does not
# ══════════════════════════════════════════════════════════════════════════════

def main():
    interactive_options([])

    dry_run   = "--apply"  not in sys.argv
    pick_dir  = "--pick"   in sys.argv
    filter_ok = "--filter" in sys.argv

    _path  = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                   if a == "--path"  and i+1 < len(sys.argv)), None)
    _depth = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                   if a == "--depth" and i+1 < len(sys.argv)), None)
    max_depth = int(_depth) if _depth and _depth.isdigit() else None

    # ── Determine folders to scan ──────────────────────────────────────────────
    if _path:
        roots = [Path(_path.strip('"'))]
    elif pick_dir:
        roots = pick_folders()
        if not roots:
            print("\n  No folders selected. Exiting.\n")
            return
    else:
        cfg = config_organized_folder()
        if cfg:
            roots = [cfg]
        else:
            print("ERROR: No folder specified. Use --pick or --path.")
            sys.exit(1)

    for r in roots:
        if not r.exists() or not r.is_dir():
            print(f"ERROR: Folder not found: {r}")
            sys.exit(1)

    mode = "DRY RUN — nothing will be renamed" if dry_run else "LIVE — folders will be renamed"
    print(f"\n{'='*65}")
    print(f"Album Folder Renamer  v2.6")
    print(f"{'='*65}")
    print(f"  Mode      : {mode}")
    for r in roots:
        print(f"  Folder    : {r}")
    if max_depth:
        print(f"  Depth     : {max_depth} level(s) only")
    if filter_ok:
        print(f"  Filter    : skipping already-correct folders")
    print(f"{'='*65}\n")

    print("  Scanning...\n")
    candidates = []
    for root in roots:
        candidates.extend(find_album_folders(root, max_depth=max_depth, filter_ok=filter_ok))

    if not candidates:
        if filter_ok:
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

    if empty_folders:
        print(f"  WARNING: {len(empty_folders)} folder(s) have no album tag — will be left unchanged:")
        for c in empty_folders:
            print(f"    {c['rel']}")
        print()

    # ── Resolve conflicts interactively ────────────────────────────────────────
    if conflict_folders:
        print(f"  {len(conflict_folders)} conflict(s) need your input:\n")
        for c in conflict_folders:
            chosen      = prompt_conflict(c["folder"], c["file_tags"])
            c["album"]  = chosen
            c["status"] = "resolved" if chosen else "skipped"

    # ── Cross-folder collision check ───────────────────────────────────────────
    collision_map = {}
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

    # ── Preview ────────────────────────────────────────────────────────────────
    to_rename = []
    for c in candidates:
        album = c.get("album")
        if not album or c["status"] not in ("ok", "resolved"):
            continue
        new_name      = sanitise_folder_name(album)
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
              + (" (dry run):" if dry_run else ":"))
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

    if dry_run:
        print(f"  Dry run complete. Run with --apply to rename.\n")
        write_report(candidates, REPORTS_FOLDER, dry_run=True)
        return

    if not to_rename:
        write_report(candidates, REPORTS_FOLDER, dry_run=False)
        return

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

    write_report(candidates, REPORTS_FOLDER, dry_run=False)


if __name__ == "__main__":
    main()
