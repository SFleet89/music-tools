#!/usr/bin/env python3
"""
compare_spotify_library.py  v1.1  2026-06-01

Compares a Spotify/Streamrip staging folder against your main music library
by querying the pre-built music_cache.db (SQLite) instead of scanning the
library folder — dramatically faster than reading tags from disk.

Matches tracks by tags (albumartist + album + title), then compares quality
(format + bitrate).  REPORT ONLY — no files are moved or deleted.

Usage
-----
  python compare_spotify_library.py --pick-spotify --pick-db
  python compare_spotify_library.py --path-spotify "C:\\..." --path-db "C:\\...\\music_cache.db"

Flags
-----
  --pick-spotify    Folder dialog for the Spotify staging folder
  --path-spotify    Supply Spotify path directly (quoted)
  --pick-db         File dialog to locate music_cache.db
  --path-db         Supply path to music_cache.db directly (quoted)

Requirements
------------
  pip install mutagen
  music_cache.db built by build_fp_cache.py (duplicate_finder tool)
"""

import sys
import csv
import re
import sqlite3
import unicodedata
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Flag parsing
# ---------------------------------------------------------------------------
PICK_SPOTIFY = "--pick-spotify" in sys.argv
PICK_DB      = "--pick-db"      in sys.argv

def _get_flag(flag: str) -> str | None:
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1].strip('"')
    return None

PATH_SPOTIFY = _get_flag("--path-spotify")
PATH_DB      = _get_flag("--path-db")

AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".aac", ".wav", ".wma", ".ape", ".alac"}

SCRIPT_DIR     = Path(__file__).parent
REPORTS_FOLDER = SCRIPT_DIR / "reports"

# Quality ranking: higher = better.
FORMAT_RANK = {
    ".flac":  100,
    ".alac":  95,
    ".ape":   90,
    ".wav":   85,
    ".ogg":   60,
    ".opus":  60,
    ".m4a":   55,
    ".aac":   50,
    ".mp3":   40,
    ".wma":   30,
}

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


def pick_file(title: str) -> Path | None:
    import tkinter as tk
    from tkinter import filedialog
    root_tk = tk.Tk()
    root_tk.withdraw()
    root_tk.attributes("-topmost", True)
    f = filedialog.askopenfilename(
        title=title,
        filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
    )
    root_tk.destroy()
    return Path(f) if f else None


def normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace, remove punctuation."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def match_key(tags: dict) -> str:
    """Primary match key: normalised albumartist + album + title."""
    return (
        normalize(tags.get("albumartist", ""))
        + "||"
        + normalize(tags.get("album", ""))
        + "||"
        + normalize(tags.get("title", ""))
    )


def loose_key(tags: dict) -> str:
    """Loose match key: normalised artist + title only (ignores album)."""
    artist = tags.get("albumartist", "") or tags.get("artist", "")
    return normalize(artist) + "||" + normalize(tags.get("title", ""))


def get_tags(file: Path) -> dict:
    """Return tags dict from audio file (Spotify staging files only)."""
    result = {
        "albumartist": "",
        "artist":      "",
        "album":       "",
        "title":       file.stem,
        "tracknumber": "",
        "bitrate":     0,
        "format":      file.suffix.lower(),
    }
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(str(file), easy=True)
        if audio is None:
            return result

        def first(tag):
            val = audio.tags.get(tag) if audio.tags else None
            return str(val[0]).strip() if val else ""

        result["albumartist"] = first("albumartist") or first("artist")
        result["artist"]      = first("artist")
        result["album"]       = first("album")
        result["title"]       = first("title") or file.stem
        result["tracknumber"] = first("tracknumber")

        if hasattr(audio.info, "bitrate"):
            result["bitrate"] = int(audio.info.bitrate / 1000)

    except Exception as e:
        result["_tag_error"] = str(e)
    return result


def db_row_to_tags(row: sqlite3.Row) -> dict:
    """
    Convert a metadata_cache DB row to the same tags dict shape used
    by the rest of the script.

    DB notes:
      - album_artist column (not albumartist)
      - bitrate stored in bps (e.g. 192000) → convert to kbps
      - file_format stored without dot (e.g. "mp3") → prepend "."
    """
    fmt     = (row["file_format"] or "").lower()
    fmt     = ("." + fmt) if fmt and not fmt.startswith(".") else fmt
    bitrate = int((row["bitrate"] or 0) / 1000)
    return {
        "albumartist": row["album_artist"] or row["artist"] or "",
        "artist":      row["artist"] or "",
        "album":       row["album"] or "",
        "title":       row["title"] or "",
        "tracknumber": row["track_number"] or "",
        "bitrate":     bitrate,
        "format":      fmt,
    }


def quality_score(tags: dict) -> int:
    """
    Composite quality score.
    Lossless: format rank * 1000  (bitrate not meaningful)
    Lossy:    format rank * 1000 + bitrate (kbps)
    """
    fmt      = tags.get("format", "").lower()
    rank     = FORMAT_RANK.get(fmt, 20)
    br       = tags.get("bitrate", 0)
    lossless = fmt in {".flac", ".alac", ".ape", ".wav"}
    return rank * 1000 + (0 if lossless else br)


def quality_label(tags: dict) -> str:
    fmt = tags.get("format", "").upper().lstrip(".")
    br  = tags.get("bitrate", 0)
    if fmt in {"FLAC", "ALAC", "APE", "WAV"}:
        return f"{fmt} (lossless)"
    if br:
        return f"{fmt} {br}kbps"
    return fmt


def recommendation(spotify_score: int, library_score: int) -> str:
    if spotify_score > library_score:
        return "UPGRADE — Spotify version is better quality"
    elif spotify_score == library_score:
        return "SAME — equal quality, keep library copy"
    else:
        return "SKIP — library copy is better or equal"


def write_report(rows: list[dict]) -> Path:
    REPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path  = REPORTS_FOLDER / f"compare_spotify_library_{timestamp}.csv"

    fieldnames = [
        "match_type",
        "recommendation",
        "spotify_file",
        "spotify_quality",
        "library_file",
        "library_quality",
        "albumartist",
        "album",
        "title",
        "note",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 65)
    print("  compare_spotify_library.py  v1.1")
    print("  Mode : REPORT ONLY — no files will be moved or deleted")
    print("=" * 65)

    # --- Resolve Spotify staging folder ---
    if PICK_SPOTIFY:
        spotify_root = pick_folder("Select Spotify staging folder")
        if not spotify_root:
            print("No Spotify folder selected. Exiting.")
            sys.exit(0)
    elif PATH_SPOTIFY:
        spotify_root = Path(PATH_SPOTIFY)
    else:
        print("ERROR: No Spotify folder specified.")
        print("  Use --pick-spotify  or  --path-spotify \"C:\\path\\to\\folder\"")
        sys.exit(1)

    if not spotify_root.exists() or not spotify_root.is_dir():
        print(f"ERROR: Spotify folder not found: {spotify_root}")
        sys.exit(1)

    # --- Resolve music_cache.db ---
    if PICK_DB:
        db_path = pick_file("Select music_cache.db")
        if not db_path:
            print("No database file selected. Exiting.")
            sys.exit(0)
    elif PATH_DB:
        db_path = Path(PATH_DB)
    else:
        print("ERROR: No database specified.")
        print("  Use --pick-db  or  --path-db \"C:\\path\\to\\music_cache.db\"")
        sys.exit(1)

    if not db_path.exists() or not db_path.is_file():
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)

    print(f"  Spotify folder  : {spotify_root}")
    print(f"  Library DB      : {db_path}")
    print()

    # --- Scan Spotify staging ---
    print("  Scanning Spotify staging folder…")
    spotify_files = [
        f for f in spotify_root.rglob("*")
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
    ]
    print(f"  → {len(spotify_files)} audio file(s) found")

    if not spotify_files:
        print("No audio files found in Spotify folder. Exiting.")
        sys.exit(0)

    # --- Load library index from DB ---
    print("  Loading library index from database…")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    lib_primary = {}   # match_key → (path_str, tags)
    lib_loose   = {}   # loose_key → (path_str, tags)

    cur = conn.execute("SELECT * FROM metadata_cache")
    row_count = 0
    for row in cur:
        tags = db_row_to_tags(row)
        pk   = match_key(tags)
        lk   = loose_key(tags)
        if pk not in lib_primary:
            lib_primary[pk] = (row["path_str"], tags)
        if lk not in lib_loose:
            lib_loose[lk] = (row["path_str"], tags)
        row_count += 1

    conn.close()
    print(f"  → {row_count:,} library tracks loaded ({len(lib_primary):,} unique by primary key)")
    print()

    # --- Compare ---
    print("  Comparing Spotify files against library…")
    rows      = []
    matched   = 0
    unmatched = 0
    upgrades  = 0

    for sp_file in sorted(spotify_files):
        sp_tags  = get_tags(sp_file)
        sp_pk    = match_key(sp_tags)
        sp_lk    = loose_key(sp_tags)
        sp_score = quality_score(sp_tags)
        sp_label = quality_label(sp_tags)

        lib_match = None
        mtype     = ""

        if sp_pk in lib_primary:
            lib_path, lib_tags = lib_primary[sp_pk]
            lib_match = lib_path
            mtype = "exact"
        elif sp_lk in lib_loose:
            lib_path, lib_tags = lib_loose[sp_lk]
            lib_match = lib_path
            mtype = "loose (title+artist, album differs)"

        if lib_match:
            lib_score = quality_score(lib_tags)
            lib_label = quality_label(lib_tags)
            rec       = recommendation(sp_score, lib_score)
            if "UPGRADE" in rec:
                upgrades += 1
            matched += 1
            rows.append({
                "match_type":      mtype,
                "recommendation":  rec,
                "spotify_file":    str(sp_file),
                "spotify_quality": sp_label,
                "library_file":    lib_match,
                "library_quality": lib_label,
                "albumartist":     sp_tags.get("albumartist", ""),
                "album":           sp_tags.get("album", ""),
                "title":           sp_tags.get("title", ""),
                "note":            sp_tags.get("_tag_error", ""),
            })
        else:
            unmatched += 1
            rows.append({
                "match_type":      "no match",
                "recommendation":  "NEW — not in library",
                "spotify_file":    str(sp_file),
                "spotify_quality": sp_label,
                "library_file":    "",
                "library_quality": "",
                "albumartist":     sp_tags.get("albumartist", ""),
                "album":           sp_tags.get("album", ""),
                "title":           sp_tags.get("title", ""),
                "note":            sp_tags.get("_tag_error", ""),
            })

    # --- Write report ---
    report_path = write_report(rows)

    # --- Summary ---
    print()
    print("  ── Results ──────────────────────────────────────────")
    print(f"  Spotify files scanned  : {len(spotify_files)}")
    print(f"  Matched in library     : {matched}  ({matched - upgrades} skip/same,  {upgrades} potential upgrades)")
    print(f"  Not in library (new)   : {unmatched}")
    print(f"  Report                 : {report_path}")
    print()
    print("  Open the CSV to review.  Columns to focus on:")
    print("    recommendation = UPGRADE  → Spotify copy is higher quality")
    print("    recommendation = NEW      → track not in your library at all")
    print()
    print("  No files were moved or deleted.")


if __name__ == "__main__":
    main()
