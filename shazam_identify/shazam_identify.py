r"""
Shazam Identify  v1.0
======================
Identifies audio files using the Shazam API and optionally writes
the recognised tags (Artist, Title, Album, Year) back to each file.

Requires:
    pip install shazamio mutagen

Workflow:
  Step 1 -- Dry run (default):
    Select a folder of untagged or mystery audio files.
    Each file is fingerprinted and sent to Shazam for identification.
    A CSV report shows what was recognised and what tags would be written.
    No files are modified.

  Step 2 -- Apply:
    Re-run with --apply to write the identified tags to matched files.
    Only files with a confident Shazam match are tagged.
    Original tag values are saved in the report for reference.

Usage:
    python shazam_identify.py                     # dry run, pick folder
    python shazam_identify.py --apply             # write tags, pick folder
    python shazam_identify.py --path "C:\Music"   # specify folder directly
    python shazam_identify.py --delay 1.0         # seconds between requests (default: 0.5)
    python shazam_identify.py --skip-tagged       # skip files that already have Artist + Title tags
    python shazam_identify.py --apply --path "C:\Music" --skip-tagged
"""

import sys
import re
import csv
import time
import asyncio
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import pick_folder
from music_tools_common import interactive_options

# -- Optional dependencies -----------------------------------------------------
try:
    from shazamio import Shazam as _Shazam
    SHAZAM_AVAILABLE = True
except ImportError:
    SHAZAM_AVAILABLE = False

try:
    from mutagen import File as MutagenFile
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3NoHeaderError
    from mutagen.flac import FLAC
    from mutagen.mp4 import MP4
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    print("WARNING: mutagen not installed. Tag writing disabled.")
    print("         Run: pip install mutagen")

# -- Paths ---------------------------------------------------------------------
SCRIPT_DIR      = Path(__file__).parent
REPORTS_FOLDER  = SCRIPT_DIR / "reports"
SUPPORTED_EXTS  = {".mp3", ".flac", ".m4a", ".aac", ".ogg"}

# -- Parse flags ---------------------------------------------------------------
DRY_RUN      = "--apply"        not in sys.argv
SKIP_TAGGED  = "--skip-tagged"  in sys.argv

_path_flag = next(
    (sys.argv[i + 1] for i, a in enumerate(sys.argv)
     if a == "--path" and i + 1 < len(sys.argv)),
    None,
)
_delay_flag = next(
    (sys.argv[i + 1] for i, a in enumerate(sys.argv)
     if a == "--delay" and i + 1 < len(sys.argv)),
    None,
)
try:
    REQUEST_DELAY = float(_delay_flag) if _delay_flag else 0.5
except ValueError:
    REQUEST_DELAY = 0.5


# -- Tag helpers ---------------------------------------------------------------

def read_tags(path: Path) -> dict:
    """Read current Artist, Title, Album, Date from a file."""
    tags = {"artist": "", "title": "", "album": "", "date": ""}
    if not MUTAGEN_AVAILABLE:
        return tags
    try:
        f = MutagenFile(path, easy=True)
        if f is None:
            return tags
        def _first(key):
            val = f.get(key)
            return val[0].strip() if val else ""
        tags["artist"] = _first("artist")
        tags["title"]  = _first("title")
        tags["album"]  = _first("album")
        tags["date"]   = _first("date")
    except Exception:
        pass
    return tags


def write_tags(path: Path, artist: str, title: str, album: str, year: str) -> str:
    """
    Write tags to an audio file. Returns "Tagged" or an error message.
    Supports MP3 (EasyID3), FLAC, M4A/AAC (MP4), and generic easy tags.
    """
    if not MUTAGEN_AVAILABLE:
        return "Error: mutagen not available"
    try:
        ext = path.suffix.lower()
        if ext == ".mp3":
            try:
                f = EasyID3(str(path))
            except ID3NoHeaderError:
                f = EasyID3()
                f.save(str(path))
                f = EasyID3(str(path))
            if artist: f["artist"] = artist
            if title:  f["title"]  = title
            if album:  f["album"]  = album
            if year:   f["date"]   = year
            f.save()
        elif ext == ".flac":
            f = FLAC(str(path))
            if artist: f["artist"] = artist
            if title:  f["title"]  = title
            if album:  f["album"]  = album
            if year:   f["date"]   = year
            f.save()
        elif ext in (".m4a", ".aac"):
            f = MP4(str(path))
            tag_map = {
                "artist": "\xa9ART",
                "title":  "\xa9nam",
                "album":  "\xa9alb",
                "year":   "\xa9day",
            }
            if artist: f[tag_map["artist"]] = [artist]
            if title:  f[tag_map["title"]]  = [title]
            if album:  f[tag_map["album"]]  = [album]
            if year:   f[tag_map["year"]]   = [year]
            f.save()
        else:
            # Generic easy tags fallback
            f = MutagenFile(str(path), easy=True)
            if f is not None:
                if artist: f["artist"] = artist
                if title:  f["title"]  = title
                if album:  f["album"]  = album
                if year:   f["date"]   = year
                f.save()
        return "Tagged"
    except Exception as exc:
        return f"Error: {exc}"


# -- Shazam result parser ------------------------------------------------------

def parse_shazam_result(result: dict) -> dict:
    """
    Extract Artist, Title, Album, Year from a raw shazamio result dict.
    Returns dict with keys: artist, title, album, year (all strings, may be empty).
    Returns None if no track was identified.
    """
    if not result:
        return None
    track = result.get("track")
    if not track:
        return None

    artist = track.get("subtitle", "") or ""
    title  = track.get("title", "")   or ""
    album  = ""
    year   = ""

    # Parse album and year from sections[].metadata[]
    sections = track.get("sections", [])
    for section in sections:
        if section.get("type") == "SONG":
            for meta in section.get("metadata", []):
                t = meta.get("title", "").lower()
                v = meta.get("text", "") or ""
                if t == "album":
                    album = v
                elif t in ("released", "release date"):
                    # Extract 4-digit year
                    m = re.search(r"\d{4}", v)
                    if m:
                        year = m.group()
            break

    if not title:
        return None

    return {"artist": artist, "title": title, "album": album, "year": year}


# -- Core identification --------------------------------------------------------

async def _identify_file_async(shazam: object, path: Path) -> dict:
    """
    Send one file to Shazam and return identification result.
    Returns dict with: path, shazam_artist, shazam_title, shazam_album,
                       shazam_year, status, current_artist, current_title
    """
    current = read_tags(path)
    try:
        raw = await shazam.recognize(str(path))
        parsed = parse_shazam_result(raw)
        if parsed:
            return {
                "path":           path,
                "filename":       path.name,
                "current_artist": current["artist"],
                "current_title":  current["title"],
                "shazam_artist":  parsed["artist"],
                "shazam_title":   parsed["title"],
                "shazam_album":   parsed["album"],
                "shazam_year":    parsed["year"],
                "status":         "Identified",
            }
        else:
            return {
                "path":           path,
                "filename":       path.name,
                "current_artist": current["artist"],
                "current_title":  current["title"],
                "shazam_artist":  "",
                "shazam_title":   "",
                "shazam_album":   "",
                "shazam_year":    "",
                "status":         "No match",
            }
    except Exception as exc:
        return {
            "path":           path,
            "filename":       path.name,
            "current_artist": current["artist"],
            "current_title":  current["title"],
            "shazam_artist":  "",
            "shazam_title":   "",
            "shazam_album":   "",
            "shazam_year":    "",
            "status":         f"Error: {exc}",
        }


async def _run_async(
    files: list,
    delay: float,
    progress_callback=None,
    log_callback=None,
) -> list:
    """Identify all files sequentially with a delay between requests."""
    def _log(msg):
        if log_callback:
            log_callback(msg)

    shazam  = _Shazam()
    results = []
    total   = len(files)

    for i, path in enumerate(files):
        if progress_callback:
            progress_callback(i, total, path.name)
        _log(f"[{i+1}/{total}] Identifying: {path.name}")
        result = await _identify_file_async(shazam, path)
        results.append(result)
        status = result["status"]
        if status == "Identified":
            _log(f"  -> {result['shazam_artist']} - {result['shazam_title']}")
        else:
            _log(f"  -> {status}")
        if i < total - 1:
            await asyncio.sleep(delay)

    if progress_callback:
        progress_callback(total, total, "")
    return results


# -- Report --------------------------------------------------------------------

def write_report(results: list, dry_run: bool) -> str:
    """Write CSV report and return the path as a string."""
    fieldnames = [
        "Filename", "Status",
        "Shazam Artist", "Shazam Title", "Shazam Album", "Shazam Year",
        "Original Artist", "Original Title",
    ]
    REPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix    = "dry" if dry_run else "applied"
    out_path  = REPORTS_FOLDER / f"shazam_identify_{suffix}_{timestamp}.csv"
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "Filename":        r["filename"],
                "Status":          r["status"],
                "Shazam Artist":   r["shazam_artist"],
                "Shazam Title":    r["shazam_title"],
                "Shazam Album":    r["shazam_album"],
                "Shazam Year":     r["shazam_year"],
                "Original Artist": r["current_artist"],
                "Original Title":  r["current_title"],
            })
    return str(out_path)


# -- GUI-callable entry point --------------------------------------------------

def run_shazam_identify(
    folder,
    apply=False,
    skip_tagged=False,
    delay=0.5,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    GUI-callable entry point.

    Parameters
    ----------
    folder            : str | Path  -- folder of audio files to identify.
    apply             : bool        -- False = dry run, True = write tags.
    skip_tagged       : bool        -- skip files that already have Artist + Title.
    delay             : float       -- seconds between Shazam requests (default 0.5).
    progress_callback : callable(current, total, filename) | None
    log_callback      : callable(message) | None

    Returns
    -------
    dict with keys:
        results      : list[dict]  -- one entry per file
        identified   : int         -- files successfully identified
        tagged       : int         -- files tagged (apply mode only)
        no_match     : int         -- files Shazam could not identify
        errors       : int         -- files that caused errors
        skipped      : int         -- files skipped (skip_tagged)
        report_path  : str | None  -- path to CSV report
    """
    root = Path(folder)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Folder not found: {root}")

    def _log(msg):
        if log_callback:
            log_callback(msg)

    # Collect audio files
    files = sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )
    if not files:
        raise ValueError(f"No supported audio files found in: {root}")

    # Optionally skip files that already have tags
    skipped = []
    to_process = []
    if skip_tagged:
        for f in files:
            tags = read_tags(f)
            if tags["artist"] and tags["title"]:
                skipped.append({
                    "path": f, "filename": f.name,
                    "current_artist": tags["artist"],
                    "current_title":  tags["title"],
                    "shazam_artist": "", "shazam_title": "",
                    "shazam_album":  "", "shazam_year":  "",
                    "status": "Skipped (already tagged)",
                })
            else:
                to_process.append(f)
    else:
        to_process = files

    _log(f"Files to identify: {len(to_process)}"
         + (f"  |  Skipped (tagged): {len(skipped)}" if skipped else ""))

    # Run async identification
    results = asyncio.run(_run_async(
        to_process, delay, progress_callback, log_callback
    ))
    results = skipped + results

    # Apply: write tags for identified files
    tagged   = 0
    no_match = 0
    errors   = 0

    for r in results:
        if r["status"] == "Identified":
            if apply:
                tag_result = write_tags(
                    r["path"],
                    r["shazam_artist"], r["shazam_title"],
                    r["shazam_album"],  r["shazam_year"],
                )
                r["status"] = tag_result
                if tag_result == "Tagged":
                    tagged += 1
                    _log(f"[TAG] {r['filename']} -> {r['shazam_artist']} - {r['shazam_title']}")
                else:
                    errors += 1
                    _log(f"[ERR] {r['filename']}: {tag_result}")
            # In dry run, count identified as pending
        elif "No match" in r["status"]:
            no_match += 1
        elif "Error" in r["status"]:
            errors += 1

    identified = sum(1 for r in results if "Identified" in r["status"] or r["status"] == "Tagged")

    # Save report
    report_path = None
    try:
        report_path = write_report(results, dry_run=not apply)
        _log(f"Report saved: {report_path}")
    except Exception as exc:
        _log(f"WARNING: Could not write report: {exc}")

    return {
        "results":     results,
        "identified":  identified,
        "tagged":      tagged,
        "no_match":    no_match,
        "errors":      errors,
        "skipped":     len(skipped),
        "report_path": report_path,
    }


# -- Main ----------------------------------------------------------------------

if __name__ == "__main__":
    if _path_flag:
        root = Path(_path_flag.strip('"'))
    else:
        root = pick_folder()
        if not root:
            print("\n  No folder selected. Exiting.\n")
            sys.exit(0)

    if not root.exists() or not root.is_dir():
        print(f"ERROR: Folder not found: {root}")
        sys.exit(1)

    mode = "DRY RUN -- no tags will be written" if DRY_RUN else "LIVE -- tags will be written"
    print(f"\n{'=' * 60}")
    print(f"Shazam Identify  v1.0")
    print(f"{'=' * 60}")
    print(f"  Mode   : {mode}")
    print(f"  Folder : {root}")
    print(f"  Delay  : {REQUEST_DELAY}s between requests")
    if SKIP_TAGGED:
        print(f"  Skipping files that already have Artist + Title tags")
    print(f"{'=' * 60}\n")

    def _progress(current, total, filename):
        if filename:
            pct = int(current / total * 100) if total else 0
            print(f"  [{pct:3d}%] {filename}")

    result = run_shazam_identify(
        folder=root,
        apply=not DRY_RUN,
        skip_tagged=SKIP_TAGGED,
        delay=REQUEST_DELAY,
        progress_callback=_progress,
        log_callback=print,
    )

    identified = result["identified"]
    no_match   = result["no_match"]
    errors     = result["errors"]
    skipped    = result["skipped"]

    print(f"\n  {'=' * 40}")
    if DRY_RUN:
        print(f"  Would tag : {identified}")
    else:
        print(f"  Tagged    : {result['tagged']}")
    print(f"  No match  : {no_match}")
    print(f"  Errors    : {errors}")
    if skipped:
        print(f"  Skipped   : {skipped}")
    print(f"  {'=' * 40}\n")

    if DRY_RUN and identified:
        print("  Dry run complete. Run with --apply to write tags.\n")
