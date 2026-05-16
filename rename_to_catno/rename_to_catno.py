"""
Rename to CATNO  v1.1
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
    python rename_to_catno.py                   # opens folder picker
    python rename_to_catno.py "C:\\path\\to\\Music"
    python rename_to_catno.py "C:\\path\\to\\Music" --apply

Output:
    Reports saved to: <script folder>\\reports\\rename_to_catno_YYYYMMDD_HHMMSS.csv

Changes in v1.1:
    - Catno falls back to folder name parsing if no tag present (or tag is
      a placeholder like "none"). Uses ANJ/ANJCD/ANJDEEP regex.
    - Catno normalised to no-hyphen format: ANJ-001 -> ANJ001.
    - Album " / " separators replaced with " & " (double A-side releases).
    - Double spaces collapsed after sanitising.

Changes in v1.0:
    - Initial release.
"""

import sys
import re
import csv
import shutil
from pathlib import Path
from datetime import datetime

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
SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".aac", ".m4a"}
SCRIPT_DIR           = Path(__file__).parent

# Windows-illegal filename characters
_ILLEGAL_RE = re.compile(r'[\\/:*?"<>|]')

# ANJ catalogue number anywhere in a string
_CATNO_RE = re.compile(
    r'\b(ANJ(?:CD|DEEP|UNA|WW)?\s*-?\s*\d+[A-Z\d]*)\b',
    re.IGNORECASE
)

# Placeholder values that should be treated as no catno
_NONE_VALUES = {"none", "n/a", "na", "", "-"}


def normalise_catno(catno):
    """
    Normalise catno to consistent format: remove internal hyphens/spaces
    between the letter prefix and the number.
    ANJ-001  -> ANJ001
    ANJ -001 -> ANJ001
    ANJ CD007 -> ANJCD007
    ANJ005RD stays ANJ005RD
    """
    if not catno:
        return None
    # Remove spaces/hyphens between prefix letters and digits
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
                catno  = _id3_txxx(tags, "CATALOGNUMBER", "CATALOGNUMBER", "CATALOG NUMBER")
                talb   = tags.get("TALB")
                album  = str(talb) if talb else None

            elif ext in (".m4a", ".aac"):
                catno  = _mp4_get(tags,
                    "----:com.apple.iTunes:CATALOGNUMBER",
                    "----:com.apple.iTunes:CATALOG NUMBER")
                alb    = tags.get("\xa9alb") or tags.get("©alb")
                album  = str(alb[0]) if alb else None

            else:
                # Generic fallback via easy tags
                easy = MutagenFile(f, easy=True)
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
    s = name.replace(" / ", " & ")          # double A-side: "A / B" -> "A & B"
    s = _ILLEGAL_RE.sub("", s)
    s = re.sub(r'  +', ' ', s)             # collapse double spaces
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


# ── Main logic ─────────────────────────────────────────────────────────────────

def run_rename(root_path, apply_mode):
    folders = find_album_folders(root_path)
    total   = len(folders)

    if total == 0:
        print("  No album folders found in: %s" % root_path)
        return []

    print()
    print("  Found %d album folder(s) to process." % total)
    print()

    rows = []

    for idx, folder in enumerate(folders, 1):
        catno, album = read_release_info(str(folder))
        original     = folder.name

        print("  [%d/%d]  %s" % (idx, total, original))

        # Guard placeholder catno values
        if catno and catno.lower().strip() in _NONE_VALUES:
            catno = None

        # Normalise catno format: ANJ-001 -> ANJ001
        if catno:
            catno = normalise_catno(catno)

        # Fallback: parse catno from folder name if tag missing
        if not catno:
            catno = catno_from_folder_name(original)
            if catno:
                print("          ~ No catno tag — parsed from folder name: %s" % catno)

        new_name = build_new_name(catno, album)

        if not catno:
            print("          ✗ No catalogue number tag found")
            rows.append(_row(folder, original, None, catno, album,
                             "skipped", "No catalogue number tag found"))
            continue

        if not album:
            print("          ✗ No album tag found")
            rows.append(_row(folder, original, None, catno, album,
                             "skipped", "No album tag found"))
            continue

        if new_name == original:
            print("          ~ Already correct name, skipping")
            rows.append(_row(folder, original, new_name, catno, album,
                             "skipped", "Name already correct"))
            continue

        dest = folder.parent / new_name

        if dest.exists():
            print("          ! Destination already exists: %s" % new_name)
            rows.append(_row(folder, original, new_name, catno, album,
                             "error", "Destination already exists: %s" % new_name))
            continue

        print("          → %s" % new_name)

        if not apply_mode:
            rows.append(_row(folder, original, new_name, catno, album,
                             "pending", "Dry run — would rename"))
            continue

        try:
            shutil.move(str(folder), str(dest))
            rows.append(_row(dest, original, new_name, catno, album,
                             "renamed", "OK"))
            print("          ✓ Renamed")
        except Exception as e:
            rows.append(_row(folder, original, new_name, catno, album,
                             "error", "Rename failed: %s" % e))
            print("          ! Error: %s" % e)

    return rows


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


# ── CSV output ─────────────────────────────────────────────────────────────────

FIELDNAMES = [
    "folder_path", "original_name", "new_name",
    "catno", "album", "status", "notes",
]


def write_csv(rows, output_path):
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows, apply_mode, output_path):
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    print()
    print("=" * 60)
    print("  SUMMARY  (%s)" % ("APPLY" if apply_mode else "DRY RUN"))
    print("=" * 60)
    if apply_mode:
        print("  Renamed            : %d" % counts.get("renamed", 0))
    else:
        print("  Would rename       : %d" % counts.get("pending", 0))
    print("  Already correct    : %d" % counts.get("skipped", 0))
    print("  Errors / conflicts : %d" % counts.get("error", 0))
    print()
    print("  Report saved to:")
    print("  %s" % output_path)
    print("=" * 60)


# ── Entry point ────────────────────────────────────────────────────────────────

def pick_folder():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(
            title="Select folder to rename album subfolders in",
            initialdir=r"C:\Users\neo_s\Downloads\To Move\Music",
        )
        root.destroy()
        return chosen or None
    except Exception as e:
        print("ERROR: Could not open folder picker: %s" % e)
        return None


def main():
    args       = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags      = [a for a in sys.argv[1:] if a.startswith("--")]
    apply_mode = "--apply" in flags

    if args:
        root_path = Path(args[0].strip('"'))
    else:
        chosen = pick_folder()
        if not chosen:
            print("No folder selected. Exiting.")
            sys.exit(0)
        root_path = Path(chosen)

    if not root_path.exists() or not root_path.is_dir():
        print("ERROR: Folder not found: %s" % root_path)
        sys.exit(1)

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports_dir = SCRIPT_DIR.parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    suffix      = "_applied" if apply_mode else "_dry"
    output_path = reports_dir / ("rename_to_catno_%s%s.csv" % (timestamp, suffix))

    print()
    print("=" * 60)
    print("  Rename to CATNO  v1.1")
    print("=" * 60)
    print("  Folder : %s" % root_path)
    print("  Mode   : %s" % ("APPLY — renaming for real" if apply_mode
                              else "DRY RUN — no changes made"))
    print("  Output : %s" % output_path)
    print("=" * 60)

    if apply_mode:
        confirm = input("\n  Proceed with renaming? (y/n): ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            sys.exit(0)

    rows = run_rename(str(root_path), apply_mode)

    if rows:
        write_csv(rows, str(output_path))
        print_summary(rows, apply_mode, str(output_path))
    else:
        print("  No results to save.")


if __name__ == "__main__":
    main()
