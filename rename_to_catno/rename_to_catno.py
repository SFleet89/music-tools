"""
Rename to CATNO  v1.5
======================
Renames album folders to: CATNO - Album Name
(e.g. "Above & Beyond - We Are All We Need (2015)" → "ANJCD043 - We Are All We Need")

Reads the catalogue number and album name from the embedded file tags of
the first audio file found in each folder. If no CATALOGNUMBER tag is found,
falls back to parsing the catno from the folder name itself.

Scans recursively — any folder that directly contains audio files is treated
as an album folder.

Requirements:
    pip install mutagen

Usage:
    python rename_to_catno.py                   # opens folder picker (dry run)
    python rename_to_catno.py --pick            # opens folder picker (dry run)
    python rename_to_catno.py --pick --apply    # opens folder picker and renames
    python rename_to_catno.py --path "C:\\Music" --apply

Output:
    Reports saved to: <script folder>\\reports\\rename_to_catno_YYYYMMDD_HHMMSS.csv
"""

import sys
import re
import shutil
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import (
    SUPPORTED_EXTENSIONS,
    pick_folder,
    write_csv,
    interactive_options,
)

# ── Optional mutagen ───────────────────────────────────────────────────────────
try:
    from mutagen import File as MutagenFile
    MUTAGEN_AVAILABLE = True
except ImportError:
    MutagenFile = None
    MUTAGEN_AVAILABLE = False
    print("ERROR: mutagen is required. Run: pip install mutagen")
    sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent

# Windows-illegal filename characters
_ILLEGAL_RE = re.compile(r'[\\/:*?"<>|]')

# ANJ catalogue number anywhere in a string
_CATNO_RE = re.compile(
    r'\b(ANJ(?:CD|DEEP|UNA|WW)?\s*-?\s*\d+[A-Z\d]*)\b',
    re.IGNORECASE
)

# Placeholder values that should be treated as no catno
_NONE_VALUES = {"none", "n/a", "na", "", "-"}

FIELDNAMES = [
    "folder_path", "original_name", "new_name",
    "catno", "album", "status", "notes",
]


def normalise_catno(catno):
    """
    Normalise catno to consistent format: remove internal hyphens/spaces
    between the letter prefix and the number.
    ANJ-001 -> ANJ001, ANJ CD007 -> ANJCD007
    """
    if not catno:
        return None
    c = re.sub(r'(ANJ(?:CD|DEEP|UNA|WW)?)\s*-?\s*(\d)', r'\1\2', catno,
               flags=re.IGNORECASE)
    return c.upper().strip()


def catno_from_folder_name(folder_name):
    """Extract ANJ catno from a folder name as fallback."""
    m = _CATNO_RE.search(folder_name)
    if m:
        return normalise_catno(m.group(1))
    return None


# ── Tag reading ────────────────────────────────────────────────────────────────

def _vorbis_get(tags, *keys):
    """Read first matching key from a VorbisComment tag dict (case-insensitive)."""
    for key in keys:
        for variant in (key.upper(), key.lower(), key):
            val = tags.get(variant)
            if val and str(val[0]).strip():
                return str(val[0]).strip()
    return None


def _id3_txxx(tags, *descriptions):
    """Read a TXXX frame by description from an ID3 tag dict."""
    for key in tags.keys():
        if key.upper().startswith("TXXX:"):
            desc = key[5:].upper().replace(" ", "")
            for d in descriptions:
                if desc == d.upper().replace(" ", ""):
                    frame = tags[key]
                    text  = frame.text[0] if hasattr(frame, "text") else str(frame)
                    if text.strip():
                        return text.strip()
    return None


def _mp4_get(tags, *keys):
    """Read a freeform atom from an MP4 tag dict."""
    for key in keys:
        val = tags.get(key)
        if val:
            try:
                return bytes(val[0]).decode("utf-8", errors="replace").strip()
            except Exception:
                return str(val[0]).strip()
    return None


def read_release_info(folder_path):
    """
    Read (catno, album) from the first audio file in the folder.
    Returns (None, None) if unavailable.
    """
    files = sorted(
        f for f in Path(folder_path).iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not files:
        return None, None

    for f in files:
        try:
            audio = MutagenFile(f)
            if audio is None or audio.tags is None:
                continue
            tags = audio.tags
            ext  = f.suffix.lower()

            if ext == ".flac":
                catno = _vorbis_get(tags, "CATALOGNUMBER", "CATALOG", "LABELNO")
                album = _vorbis_get(tags, "ALBUM")

            elif ext == ".mp3":
                catno  = _id3_txxx(tags, "CATALOGNUMBER", "CATALOG NUMBER")
                talb   = tags.get("TALB")
                album  = str(talb) if talb else None

            elif ext in (".m4a", ".aac"):
                catno  = _mp4_get(tags,
                    "----:com.apple.iTunes:CATALOGNUMBER",
                    "----:com.apple.iTunes:CATALOG NUMBER")
                alb    = tags.get("\xa9alb") or tags.get("©alb")
                album  = str(alb[0]) if alb else None

            else:
                easy  = MutagenFile(f, easy=True)
                catno = None
                album = None
                if easy:
                    catno = (easy.get("catalognumber", [None])[0] or "").strip() or None
                    album = (easy.get("album",         [None])[0] or "").strip() or None

            if catno or album:
                return (catno.strip() if catno else None,
                        album.strip() if album else None)

        except Exception:
            continue

    return None, None


# ── Folder scanning ────────────────────────────────────────────────────────────

def find_album_folders(root_path):
    """
    Recursively find all folders that directly contain audio files.
    Returns list of Path objects, sorted.
    """
    results = []
    try:
        for sub in sorted(Path(root_path).iterdir()):
            if not sub.is_dir():
                continue
            has_audio = any(
                f.suffix.lower() in SUPPORTED_EXTENSIONS
                for f in sub.iterdir() if f.is_file()
            )
            if has_audio:
                results.append(sub)
            else:
                results.extend(find_album_folders(sub))
    except PermissionError:
        pass
    return results


# ── Name building ──────────────────────────────────────────────────────────────

def sanitize(name):
    """Strip Windows-illegal characters, replace / separators, collapse spaces."""
    s = name.replace(" / ", " & ")
    s = _ILLEGAL_RE.sub("", s)
    s = re.sub(r'  +', ' ', s)
    return s.strip(" .")


def build_new_name(catno, album):
    """Build the target folder name: CATNO - Album Name."""
    c = sanitize(catno or "")
    a = sanitize(album or "")
    if c and a:
        return "%s - %s" % (c, a)
    if c:
        return c
    if a:
        return a
    return None


def _row(folder, original, new_name, catno, album, status, notes):
    return {
        "folder_path":   str(folder),
        "original_name": original,
        "new_name":      new_name or "",
        "catno":         catno or "",
        "album":         album or "",
        "status":        status,
        "notes":         notes,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_rename_to_catno(
    folder: Path,
    apply: bool = False,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Scan folder and rename album subfolders to CATNO - Album Name.

    Args:
        folder:            Root folder to scan recursively.
        apply:             False = dry run; True = rename folders.
        progress_callback: Optional callable(current, total, message).
        log_callback:      Optional callable(message). Defaults to print().

    Returns:
        dict: renamed, pending, skipped, errors, results (list of row dicts),
              report_path (Path|None)

    Raises:
        ValueError: folder does not exist or is not a directory.
    """
    log = log_callback or print

    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    folders = find_album_folders(folder)
    total   = len(folders)

    if total == 0:
        log(f"  No album folders found in: {folder}")
        return {"renamed": 0, "pending": 0, "skipped": 0, "errors": 0,
                "results": [], "report_path": None}

    log(f"  Found {total} album folder(s) to process.")

    rows = []

    for idx, f in enumerate(folders, 1):
        if progress_callback:
            progress_callback(idx, total, f.name)

        catno, album = read_release_info(str(f))
        original     = f.name

        if catno and catno.lower().strip() in _NONE_VALUES:
            catno = None

        if catno:
            catno = normalise_catno(catno)

        if not catno:
            catno = catno_from_folder_name(original)
            if catno:
                log(f"  [{idx}/{total}]  {original}")
                log(f"          ~ No catno tag — parsed from folder name: {catno}")

        new_name = build_new_name(catno, album)

        if not catno:
            log(f"  [{idx}/{total}]  {original}  → no catalogue number")
            rows.append(_row(f, original, None, catno, album,
                             "skipped", "No catalogue number tag found"))
            continue

        if not album:
            log(f"  [{idx}/{total}]  {original}  → no album tag")
            rows.append(_row(f, original, None, catno, album,
                             "skipped", "No album tag found"))
            continue

        if new_name == original:
            rows.append(_row(f, original, new_name, catno, album,
                             "skipped", "Name already correct"))
            continue

        dest = f.parent / new_name

        if dest.exists():
            log(f"  [{idx}/{total}]  {original}  → CONFLICT: {new_name}")
            rows.append(_row(f, original, new_name, catno, album,
                             "error", f"Destination already exists: {new_name}"))
            continue

        log(f"  [{idx}/{total}]  {original}")
        log(f"          → {new_name}")

        if not apply:
            rows.append(_row(f, original, new_name, catno, album,
                             "pending", "Dry run — would rename"))
            continue

        try:
            shutil.move(str(f), str(dest))
            rows.append(_row(dest, original, new_name, catno, album, "renamed", "OK"))
        except Exception as e:
            rows.append(_row(f, original, new_name, catno, album,
                             "error", f"Rename failed: {e}"))
            log(f"          ! Error: {e}")

    # ── Write report ───────────────────────────────────────────────────────────
    reports_dir = SCRIPT_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix  = "applied" if apply else "dry"
    report_path = reports_dir / f"rename_to_catno_{ts}_{suffix}.csv"
    write_csv(rows, str(report_path), fieldnames=FIELDNAMES)
    log(f"  Report saved: {report_path}")

    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    return {
        "renamed":     counts.get("renamed", 0),
        "pending":     counts.get("pending", 0),
        "skipped":     counts.get("skipped", 0),
        "errors":      counts.get("error", 0),
        "results":     rows,
        "report_path": report_path,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT  ← .cmd launchers call this; GUI does not
# ══════════════════════════════════════════════════════════════════════════════

def main():
    interactive_options([])

    args       = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags      = [a for a in sys.argv[1:] if a.startswith("--")]
    apply_mode = "--apply" in flags
    pick_dir   = "--pick"  in flags

    _path_flag = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--path" and i + 1 < len(sys.argv)),
        None,
    )

    if _path_flag:
        root_path = Path(_path_flag.strip('"'))
    elif args:
        root_path = Path(args[0].strip('"'))
    elif pick_dir or True:   # default to folder picker if no path given
        chosen = pick_folder("Select folder to rename album folders in")
        if not chosen:
            print("No folder selected. Exiting.")
            sys.exit(0)
        root_path = Path(chosen)

    if not root_path.exists() or not root_path.is_dir():
        print(f"ERROR: Folder not found: {root_path}")
        sys.exit(1)

    print()
    print("=" * 60)
    print("  Rename to CATNO  v1.5")
    print("=" * 60)
    print(f"  Folder : {root_path}")
    print(f"  Mode   : {'APPLY — renaming for real' if apply_mode else 'DRY RUN — no changes made'}")
    print("=" * 60)

    if apply_mode:
        confirm = input("\n  Proceed with renaming? (y/n): ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            sys.exit(0)

    try:
        result = run_rename_to_catno(root_path, apply=apply_mode)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    counts = {}
    for r in result["results"]:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    print()
    print("=" * 60)
    print(f"  SUMMARY  ({'APPLY' if apply_mode else 'DRY RUN'})")
    print("=" * 60)
    if apply_mode:
        print(f"  Renamed            : {counts.get('renamed', 0)}")
    else:
        print(f"  Would rename       : {counts.get('pending', 0)}")
    print(f"  Already correct    : {counts.get('skipped', 0)}")
    print(f"  Errors / conflicts : {counts.get('error', 0)}")
    print(f"  Report             : {result['report_path']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
