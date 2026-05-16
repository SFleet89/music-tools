"""
Find Empty Folders  v1.0
=========================
Scans a folder recursively and lists any subfolders that contain no music
files — not even in nested subfolders.

A subfolder is considered "empty of music" if no .mp3, .flac, .aac, or .m4a
file exists anywhere within it (at any depth). The folder itself may still
contain other file types (images, NFOs, etc.) — it just has no music.

Nothing is deleted or moved. This is a read-only scan.

Usage:
    python find_empty_folders.py                    # folder picker
    python find_empty_folders.py --path "C:\\Music"  # override folder

Requirements:
    tkinter (built into Python — no install needed)
"""

import sys
import csv
from pathlib import Path
from datetime import datetime

# ── Config ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR     = Path(__file__).parent
DEFAULT_FOLDER = r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\SD\Music"
REPORTS_FOLDER = SCRIPT_DIR / "reports"

MUSIC_EXT = {".mp3", ".flac", ".aac", ".m4a"}

# ── Parse flags ────────────────────────────────────────────────────────────────
_path = next((sys.argv[i + 1] for i, a in enumerate(sys.argv)
              if a == "--path" and i + 1 < len(sys.argv)), None)


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def has_music(folder: Path) -> bool:
    """Return True if any music file exists anywhere inside folder."""
    for f in folder.rglob("*"):
        if f.is_file() and f.suffix.lower() in MUSIC_EXT:
            return True
    return False


def get_relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


# ══════════════════════════════════════════════════════════════════════════════
#  FOLDER PICKER
# ══════════════════════════════════════════════════════════════════════════════

def pick_folder() -> "Path | None":
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
        title="Select root folder to scan",
        parent=root_tk,
    )
    root_tk.destroy()
    return Path(folder) if folder else None


# ══════════════════════════════════════════════════════════════════════════════
#  SCAN
# ══════════════════════════════════════════════════════════════════════════════

def scan(root: Path) -> list:
    """
    Walk all immediate and nested subfolders.
    Return a list of folders that contain no music files at any depth.
    """
    empty = []

    # Walk shallowest-first so the listing is easy to read
    all_dirs = sorted(
        (d for d in root.rglob("*") if d.is_dir()),
        key=lambda d: len(d.parts),
    )

    for folder in all_dirs:
        if not has_music(folder):
            rel = get_relative_path(folder, root)
            try:
                total_files = sum(1 for f in folder.iterdir() if f.is_file())
                subdirs     = sum(1 for f in folder.iterdir() if f.is_dir())
            except PermissionError:
                total_files = -1
                subdirs     = -1
            empty.append({
                "folder":      folder,
                "rel":         rel,
                "total_files": total_files,
                "subdirs":     subdirs,
            })

    return empty


# ══════════════════════════════════════════════════════════════════════════════
#  REPORT
# ══════════════════════════════════════════════════════════════════════════════

def write_report(empty: list, root: Path, reports_dir: Path):
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path  = reports_dir / f"find_empty_folders_{timestamp}.csv"

        fieldnames = ["Relative Path", "Full Path", "Files (non-music)", "Subdirs"]
        rows = []
        for entry in empty:
            rows.append({
                "Relative Path":     entry["rel"],
                "Full Path":         str(entry["folder"]),
                "Files (non-music)": entry["total_files"] if entry["total_files"] >= 0 else "access error",
                "Subdirs":           entry["subdirs"]      if entry["subdirs"]      >= 0 else "access error",
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
    reports_dir = REPORTS_FOLDER

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

    print(f"\n{'='*65}")
    print(f"Find Empty Folders  v1.0")
    print(f"{'='*65}")
    print(f"  Folder : {root}")
    print(f"{'='*65}\n")

    # ── Scan ───────────────────────────────────────────────────────────────────
    print("  Scanning...\n")
    empty = scan(root)

    try:
        total_dirs = sum(1 for d in root.rglob("*") if d.is_dir())
    except Exception:
        total_dirs = len(empty)

    print(f"  Subfolders scanned   : {total_dirs}")
    print(f"  Empty of music       : {len(empty)}")
    print()

    if not empty:
        print("  No empty folders found — every subfolder contains music files.\n")
        return

    # ── List results ───────────────────────────────────────────────────────────
    print(f"  Folders with no music files:\n")
    for entry in empty:
        note = ""
        if entry["total_files"] > 0:
            note = f"  ({entry['total_files']} non-music file(s))"
        elif entry["total_files"] == 0 and entry["subdirs"] == 0:
            note = "  (completely empty)"
        print(f"    {entry['rel']}{note}")

    print()
    write_report(empty, root, reports_dir)


if __name__ == "__main__":
    main()
