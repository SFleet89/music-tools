#!/usr/bin/env python3
"""
acoustid_fingerprint.py  v1.6  2026-06-03

Generates Chromaprint audio fingerprints for every audio file in a folder,
submits them to the AcousticID API to retrieve MusicBrainz recording IDs,
and stores the fingerprints in music_cache.db (fp_cache table).

v1.1: adds optional tag-writing (--apply required).
  Writes MUSICBRAINZ_TRACKID, ACOUSTID_ID, and ACOUSTID_FINGERPRINT tags
  to files with a confidence score at or above --min-confidence (default 0.80).
  Supports FLAC, MP3, M4A/AAC/ALAC, OGG, Opus.

Outputs per run:
  1. fp_cache table in music_cache.db — fingerprints for future duplicate detection.
  2. CSV report — per-file results including match score, recording ID, tag status.
     Filename suffix: _dry (no tags written) or _applied (tags written).

Usage
-----
  python acoustid_fingerprint.py --pick                      # dry run — no tags written
  python acoustid_fingerprint.py --pick --apply              # fingerprint + lookup + write tags
  python acoustid_fingerprint.py --pick --no-lookup          # fingerprint only, skip API
  python acoustid_fingerprint.py --pick --include-cached     # re-run all files
  python acoustid_fingerprint.py --pick --min-confidence 0.90  # stricter threshold
  python acoustid_fingerprint.py --path "C:\\...\\Organized" --apply

Requirements
------------
  pip install requests mutagen
  fpcalc.exe — path set in music_config.json -> acoustid.fpcalc_path
  AcousticID API key — set in music_config.json -> acoustid.api_key
"""

import sys
import os
import csv
import json
import sqlite3
import subprocess
import time
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# -- Optional deps -------------------------------------------------------------
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import mutagen
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3, TXXX
    import mutagen.id3
    from mutagen.mp4 import MP4, MP4FreeForm
    from mutagen.oggvorbis import OggVorbis
    from mutagen.oggopus import OggOpus
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

# -- Constants -----------------------------------------------------------------
SCRIPT_DIR      = Path(__file__).parent
PROJECT_ROOT    = SCRIPT_DIR.parent
REPORTS_FOLDER  = SCRIPT_DIR / "reports"
CONFIG_PATH     = PROJECT_ROOT / "music_config.json"
DB_PATH         = PROJECT_ROOT / "music_cache.db"

AUDIO_EXTENSIONS    = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".aac", ".wav", ".wma", ".ape", ".alac"}
TAGGABLE_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".aac", ".alac"}
ACOUSTID_URL        = "https://api.acoustid.org/v2/lookup"
FP_SAMPLE_SECS      = 60      # seconds of audio fpcalc analyses per file
API_DELAY           = 0.35    # seconds between API requests (~3 req/s max)
FP_WORKERS          = 4       # parallel fpcalc processes
MIN_CONFIDENCE_DEFAULT = 0.80  # minimum AcousticID score to write tags

# -- Flag parsing --------------------------------------------------------------
DRY_RUN        = "--apply"          not in sys.argv
PICK_DIR       = "--pick"           in sys.argv
NO_LOOKUP      = "--no-lookup"      in sys.argv
INCLUDE_CACHED = "--include-cached" in sys.argv


def _get_flag(flag):
    for i, a in enumerate(sys.argv):
        if a == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1].strip('"')
    return None


_PATH_ARG = _get_flag("--path")
_MIN_CONF = _get_flag("--min-confidence")


# =============================================================================
#  CONFIG
# =============================================================================

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# =============================================================================
#  DATABASE
# =============================================================================

def open_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fp_cache (
            path_str    TEXT PRIMARY KEY,
            mtime       REAL    NOT NULL,
            fingerprint TEXT    NOT NULL,
            fp_duration REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS acoustid_cache (
            path_str        TEXT PRIMARY KEY,
            mtime           REAL    NOT NULL,
            acoustid_id     TEXT,
            score           REAL,
            mb_recording_id TEXT,
            mb_title        TEXT,
            mb_artist       TEXT,
            b64_fingerprint TEXT,
            lookup_date     REAL
        )
    """)
    conn.commit()
    return conn


def get_cached_fps(conn: sqlite3.Connection) -> dict:
    """Return {path_str: mtime} for all rows in fp_cache."""
    return {
        row[0]: row[1]
        for row in conn.execute("SELECT path_str, mtime FROM fp_cache")
    }


def upsert_fp(conn: sqlite3.Connection, path_str: str, mtime: float,
              fingerprint: str, duration: float, lock: threading.Lock):
    with lock:
        conn.execute(
            """INSERT INTO fp_cache (path_str, mtime, fingerprint, fp_duration)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(path_str) DO UPDATE SET
                   mtime=excluded.mtime,
                   fingerprint=excluded.fingerprint,
                   fp_duration=excluded.fp_duration""",
            (path_str, mtime, fingerprint, duration),
        )
        conn.commit()


def load_acoustid_cache(conn: sqlite3.Connection) -> dict:
    """Return {path_str: row_dict} for all rows in acoustid_cache."""
    result = {}
    for row in conn.execute(
        "SELECT path_str, mtime, acoustid_id, score, mb_recording_id, "
        "mb_title, mb_artist, b64_fingerprint FROM acoustid_cache"
    ):
        result[row[0]] = {
            "mtime":           row[1],
            "acoustid":        row[2],
            "score":           row[3],
            "mb_recording_id": row[4],
            "mb_title":        row[5],
            "mb_artist":       row[6],
            "b64_fingerprint": row[7],
        }
    return result


def upsert_acoustid_cache(conn: sqlite3.Connection, path_str: str, mtime: float,
                          match: dict):
    """Cache a successful AcousticID lookup result."""
    import time as _time
    conn.execute(
        """INSERT INTO acoustid_cache
               (path_str, mtime, acoustid_id, score, mb_recording_id,
                mb_title, mb_artist, b64_fingerprint, lookup_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(path_str) DO UPDATE SET
               mtime=excluded.mtime,
               acoustid_id=excluded.acoustid_id,
               score=excluded.score,
               mb_recording_id=excluded.mb_recording_id,
               mb_title=excluded.mb_title,
               mb_artist=excluded.mb_artist,
               b64_fingerprint=excluded.b64_fingerprint,
               lookup_date=excluded.lookup_date""",
        (path_str, mtime, match.get("acoustid", ""), match.get("score", 0),
         match.get("mb_recording_id", ""), match.get("mb_title", ""),
         match.get("mb_artist", ""), match.get("b64_fingerprint", ""),
         _time.time()),
    )
    conn.commit()


# =============================================================================
#  FINGERPRINTING (fpcalc)
# =============================================================================

def run_fpcalc(file: Path, fpcalc_path: str, raw: bool = True) -> tuple[str, float] | None:
    """
    Run fpcalc on a file. Returns (fingerprint, duration) or None on failure.
    raw=True  → comma-separated integers (for fp_cache storage, compatible with duplicate finder)
    raw=False → base64 Chromaprint string (required by AcousticID API)
    """
    try:
        args = [fpcalc_path]
        if raw:
            args.append("-raw")
        args += ["-length", str(FP_SAMPLE_SECS), str(file)]
        result = subprocess.run(
            args,
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return None
        fp       = None
        duration = None
        for line in result.stdout.splitlines():
            if line.startswith("FINGERPRINT="):
                fp = line.split("=", 1)[1].strip()
            elif line.startswith("DURATION="):
                try:
                    duration = float(line.split("=", 1)[1].strip())
                except ValueError:
                    pass
        if fp and duration is not None:
            return fp, duration
    except Exception:
        pass
    return None


# =============================================================================
#  ACOUSTID API LOOKUP
# =============================================================================

def lookup_acoustid(fingerprint: str, duration: float, api_key: str) -> dict:
    """
    Submit fingerprint to AcousticID. Returns best match dict or empty dict.
    Keys: acoustid, score, mb_recording_id, mb_title, mb_artist
    """
    if not HAS_REQUESTS:
        return {"error": "requests not installed"}
    try:
        params = {
            "client":      api_key,
            "fingerprint": fingerprint,
            "duration":    int(duration),
            "meta":        "recordings",
            "format":      "json",
        }
        resp = requests.get(ACOUSTID_URL, params=params, timeout=15)
        if not resp.ok:
            try:
                body = resp.json()
                err_code = body.get("error", {}).get("code", "")
                err_msg  = body.get("error", {}).get("message", resp.text[:200])
                return {"error": f"HTTP {resp.status_code} — {err_code}: {err_msg}"}
            except Exception:
                return {"error": f"HTTP {resp.status_code} — {resp.text[:200]}"}
        data = resp.json()

        if data.get("status") != "ok" or not data.get("results"):
            return {}

        best     = max(data["results"], key=lambda r: r.get("score", 0))
        score    = best.get("score", 0)
        acoustid = best.get("id", "")

        mb_recording_id = ""
        mb_title        = ""
        mb_artist       = ""

        recordings = best.get("recordings", [])
        if recordings:
            rec             = recordings[0]
            mb_recording_id = rec.get("id", "")
            mb_title        = rec.get("title", "")
            artists         = rec.get("artists", [])
            if artists:
                mb_artist = ", ".join(a.get("name", "") for a in artists)

        return {
            "acoustid":        acoustid,
            "score":           round(score, 3),
            "mb_recording_id": mb_recording_id,
            "mb_title":        mb_title,
            "mb_artist":       mb_artist,
        }

    except requests.RequestException as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
#  TAG WRITING (mutagen)
# =============================================================================

def write_tags_to_file(file: Path, acoustid_id: str, fingerprint: str) -> str:
    """
    Write AcousticID tags to an audio file using mutagen.
    Writes: ACOUSTID_ID, ACOUSTID_FINGERPRINT
    MUSICBRAINZ_TRACKID is intentionally omitted — Qobuz metadata is
    authoritative and the MB recording ID may point to a different release.
    Returns 'ok' or an error string.
    """
    if not HAS_MUTAGEN:
        return "mutagen not installed"
    suffix = file.suffix.lower()
    try:
        if suffix == ".flac":
            audio = FLAC(str(file))
            audio["ACOUSTID_ID"]          = acoustid_id
            audio["ACOUSTID_FINGERPRINT"] = fingerprint
            audio.save()

        elif suffix == ".mp3":
            try:
                audio = ID3(str(file))
            except mutagen.id3.ID3NoHeaderError:
                audio = ID3()
            audio.setall("TXXX:AcoustID Id",
                         [TXXX(encoding=3, desc="AcoustID Id",
                               text=acoustid_id)])
            audio.setall("TXXX:AcoustID Fingerprint",
                         [TXXX(encoding=3, desc="AcoustID Fingerprint",
                               text=fingerprint)])
            audio.save(str(file))

        elif suffix in (".m4a", ".aac", ".alac"):
            audio = MP4(str(file))
            def _m4a(val: str):
                return [MP4FreeForm(val.encode("utf-8"))]
            audio["----:com.apple.iTunes:AcoustID Id"]          = _m4a(acoustid_id)
            audio["----:com.apple.iTunes:AcoustID Fingerprint"] = _m4a(fingerprint)
            audio.save()

        elif suffix == ".ogg":
            audio = OggVorbis(str(file))
            audio["ACOUSTID_ID"]          = [acoustid_id]
            audio["ACOUSTID_FINGERPRINT"] = [fingerprint]
            audio.save()

        elif suffix == ".opus":
            audio = OggOpus(str(file))
            audio["ACOUSTID_ID"]          = [acoustid_id]
            audio["ACOUSTID_FINGERPRINT"] = [fingerprint]
            audio.save()

        else:
            return f"unsupported format: {suffix}"

        return "ok"

    except Exception as e:
        return str(e)


# =============================================================================
#  REPORT
# =============================================================================

def write_report(rows: list, dry_run: bool) -> Path:
    REPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix     = "dry" if dry_run else "applied"
    out_path   = REPORTS_FOLDER / f"acoustid_fingerprint_{suffix}_{timestamp}.csv"
    fieldnames = [
        "filename", "status", "duration_s", "acoustid_score",
        "acoustid_id", "mb_recording_id", "mb_title", "mb_artist",
        "tagged", "note",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return out_path


# =============================================================================
#  CORE — GUI-CALLABLE
# =============================================================================

def run_acoustid_fingerprint(
    folder: Path,
    db_path: Path         = None,
    fpcalc_path: str      = None,
    api_key: str          = "",
    skip_cached: bool     = True,
    do_lookup: bool       = True,
    write_tags: bool      = False,
    min_confidence: float = MIN_CONFIDENCE_DEFAULT,
    dry_run: bool         = True,
    api_delay: float      = API_DELAY,
    progress_callback     = None,
    log_callback          = None,
) -> dict:
    """
    Fingerprint all audio files in folder, optionally look up AcousticID,
    and optionally write MUSICBRAINZ_TRACKID / ACOUSTID_ID / ACOUSTID_FINGERPRINT
    tags to matched files.

    Parameters
    ----------
    folder          : root folder to scan (recurses)
    db_path         : path to music_cache.db (default: PROJECT_ROOT/music_cache.db)
    fpcalc_path     : path to fpcalc executable
    api_key         : AcousticID API key (empty = skip lookup)
    skip_cached     : skip files already in fp_cache with matching mtime
    do_lookup       : submit fingerprints to AcousticID API
    write_tags      : attempt to write tags (dry_run controls whether they're actually saved)
    min_confidence  : minimum AcousticID score required to write tags (0.0-1.0)
    dry_run         : if True, report what would be tagged but don't write anything
    api_delay       : seconds between API requests
    progress_callback : fn(current, total, filename)
    log_callback      : fn(message)

    Returns dict:
        results, total, fingerprinted, identified, no_match, errors,
        skipped, tagged, low_confidence, report_path
    """
    def log(msg):
        if log_callback:
            log_callback(msg)

    def prog(cur, tot, name=""):
        if progress_callback:
            progress_callback(cur, tot, name)

    # -- Config fallbacks --
    cfg       = load_config()
    _acoustid = cfg.get("acoustid", {})
    if db_path is None:
        db_path = DB_PATH
    if fpcalc_path is None:
        fpcalc_path = _acoustid.get("fpcalc_path", "fpcalc")
    if not api_key:
        api_key = _acoustid.get("api_key", "")

    # -- Validate --
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")
    if not Path(fpcalc_path).exists():
        raise ValueError(f"fpcalc not found: {fpcalc_path}")
    if not db_path.exists():
        raise ValueError(f"Database not found: {db_path}")
    if do_lookup and not api_key:
        raise ValueError(
            "AcousticID API key required for lookup. "
            "Add it to music_config.json -> acoustid.api_key, "
            "or enter it in the panel."
        )
    if do_lookup and not HAS_REQUESTS:
        raise ValueError("'requests' not installed. Run: pip install requests")
    if write_tags and not dry_run and not HAS_MUTAGEN:
        raise ValueError("'mutagen' not installed. Run: pip install mutagen")

    # -- Collect files --
    all_files = sorted(
        f for f in folder.rglob("*")
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
    )
    total = len(all_files)
    log(f"Found {total} audio file(s) in {folder}")

    # -- Open DB, load cache --
    conn    = open_db(db_path)
    db_lock = threading.Lock()
    cached  = get_cached_fps(conn) if skip_cached else {}

    # -------------------------------------------------------------------------
    #  Phase 1: Fingerprint
    # -------------------------------------------------------------------------
    log("Phase 1: Generating fingerprints...")
    fp_results = {}   # path_str -> {fingerprint, duration, mtime, error, skipped}
    skipped    = 0
    fp_errors  = 0

    def _fp_worker(file: Path):
        path_str = str(file)
        try:
            mtime = file.stat().st_mtime
        except Exception:
            return path_str, {"error": "stat failed"}
        if skip_cached:
            cached_mtime = cached.get(path_str)
            if cached_mtime is not None and abs(cached_mtime - mtime) < 0.01:
                return path_str, {"skipped": True, "mtime": mtime}
        result = run_fpcalc(file, fpcalc_path)
        if result is None:
            return path_str, {"error": "fpcalc failed", "mtime": mtime}
        fp, duration = result
        return path_str, {"fingerprint": fp, "duration": duration, "mtime": mtime}

    with ThreadPoolExecutor(max_workers=FP_WORKERS) as executor:
        futures = {executor.submit(_fp_worker, f): f for f in all_files}
        done = 0
        for future in as_completed(futures):
            done += 1
            file = futures[future]
            path_str, info = future.result()
            fp_results[path_str] = info
            prog(done, total, file.name)
            if info.get("skipped"):
                skipped += 1
            elif info.get("error"):
                fp_errors += 1
                log(f"  FP error: {file.name} -- {info['error']}")
            else:
                upsert_fp(conn, path_str, info["mtime"],
                          info["fingerprint"], info["duration"], db_lock)

    log(f"Phase 1 complete -- {total - skipped - fp_errors} fingerprinted, "
        f"{skipped} skipped, {fp_errors} errors")

    # -------------------------------------------------------------------------
    #  Phase 2: AcousticID lookup
    # -------------------------------------------------------------------------
    rows       = []
    identified = 0
    no_match   = 0
    api_errors = 0
    match_data = {}   # path_str -> match dict (used in Phase 3)

    if do_lookup and api_key:
        # Load acoustid_cache — skip API for files already looked up with same mtime
        ac_cache = load_acoustid_cache(conn)

        lookup_files = [
            f for f in all_files
            if not fp_results.get(str(f), {}).get("error")
        ]

        # Separate into cache-hits and files that need the API
        def _need_api(f: Path) -> bool:
            cached = ac_cache.get(str(f))
            if not cached:
                return True
            try:
                mtime = f.stat().st_mtime
            except Exception:
                return True
            return abs(cached["mtime"] - mtime) >= 0.01

        api_needed = [f for f in lookup_files if _need_api(f)]
        ac_hits    = len(lookup_files) - len(api_needed)
        log(f"Phase 2: AcousticID lookup ({len(lookup_files)} files"
            f" — {ac_hits} from cache, {len(api_needed)} need API)...")

        for i, file in enumerate(lookup_files, 1):
            path_str = str(file)
            info     = fp_results[path_str]
            prog(i, len(lookup_files), file.name)

            cached_match = ac_cache.get(path_str)
            if cached_match and not _need_api(file):
                # Use cached result — no API call, no fpcalc b64 run
                match = cached_match
                b64_dur = info.get("duration", 0)
            else:
                # Not cached (or file changed) — run fpcalc b64 + API
                b64_result = run_fpcalc(file, fpcalc_path, raw=False)
                if b64_result is None:
                    match = {"error": "fpcalc failed (base64 pass)"}
                    b64_dur = info.get("duration", 0)
                else:
                    b64_fp, b64_dur = b64_result
                    match = lookup_acoustid(b64_fp, b64_dur, api_key)
                    match["b64_fingerprint"] = b64_fp
                    if match.get("acoustid") and not match.get("error"):
                        try:
                            mtime = file.stat().st_mtime
                            upsert_acoustid_cache(conn, path_str, mtime, match)
                        except Exception:
                            pass
                    if i < len(api_needed):
                        time.sleep(api_delay)
            match_data[path_str] = match

            if match.get("error"):
                api_errors += 1
                status = "api_error"
                log(f"  API error: {file.name} -- {match['error']}")
            elif match.get("acoustid"):
                identified += 1
                status = "identified"
            else:
                no_match += 1
                status = "no_match"

            rows.append({
                "filename":        file.name,
                "status":          status,
                "duration_s":      round(info.get("duration", b64_dur), 1),
                "acoustid_score":  match.get("score", ""),
                "acoustid_id":     match.get("acoustid", ""),
                "mb_recording_id": match.get("mb_recording_id", ""),
                "mb_title":        match.get("mb_title", ""),
                "mb_artist":       match.get("mb_artist", ""),
                "tagged":          "",
                "note":            match.get("error", ""),
            })

        log(f"Phase 2 complete -- {identified} identified, "
            f"{no_match} no match, {api_errors} API errors")

    else:
        # No lookup — build rows from fingerprint phase only
        for file in all_files:
            path_str = str(file)
            info     = fp_results.get(path_str, {})
            if info.get("skipped"):
                status = "skipped (cached)"
            elif info.get("error"):
                status = f"error: {info['error']}"
            else:
                status = "fingerprinted"
            rows.append({
                "filename":        file.name,
                "status":          status,
                "duration_s":      round(info.get("duration", 0), 1),
                "acoustid_score":  "",
                "acoustid_id":     "",
                "mb_recording_id": "",
                "mb_title":        "",
                "mb_artist":       "",
                "tagged":          "n/a (no lookup)",
                "note":            "",
            })

    # -------------------------------------------------------------------------
    #  Phase 3: Tag writing
    # -------------------------------------------------------------------------
    tagged_count   = 0
    low_conf_count = 0

    if write_tags and do_lookup:
        if dry_run:
            log("Phase 3: Tag writing (DRY RUN -- no files will be modified)...")
        else:
            log("Phase 3: Writing tags...")

        row_by_name = {r["filename"]: r for r in rows}

        for file in all_files:
            path_str = str(file)
            info     = fp_results.get(path_str, {})
            match    = match_data.get(path_str, {})
            row      = row_by_name.get(file.name)

            if not row:
                continue
            if info.get("error"):   # skip only hard fingerprint failures, not cache-skips
                continue
            if match.get("error") or not match.get("acoustid"):
                row["tagged"] = "no_match"
                continue

            score = match.get("score", 0)
            if score < min_confidence:
                row["tagged"] = f"low_conf ({score:.2f} < {min_confidence})"
                low_conf_count += 1
                continue

            if file.suffix.lower() not in TAGGABLE_EXTENSIONS:
                row["tagged"] = "unsupported_format"
                continue

            if dry_run:
                row["tagged"] = f"would_tag (score {score:.2f})"
                tagged_count += 1
            else:
                tag_result = write_tags_to_file(
                    file,
                    acoustid_id = match.get("acoustid", ""),
                    fingerprint = match.get("b64_fingerprint", ""),
                )
                if tag_result == "ok":
                    row["tagged"] = "yes"
                    tagged_count += 1
                    log(f"  Tagged: {file.name}")
                else:
                    row["tagged"] = f"tag_error: {tag_result}"
                    log(f"  Tag error: {file.name} -- {tag_result}")

        if dry_run:
            log(f"Phase 3 complete -- {tagged_count} would be tagged, "
                f"{low_conf_count} skipped (low confidence < {min_confidence})")
        else:
            log(f"Phase 3 complete -- {tagged_count} tagged, "
                f"{low_conf_count} skipped (low confidence < {min_confidence})")

    conn.close()

    # -- Report --
    report_path = write_report(rows, dry_run)
    log(f"Report saved: {report_path}")

    return {
        "results":        rows,
        "total":          total,
        "fingerprinted":  total - skipped - fp_errors,
        "identified":     identified,
        "no_match":       no_match,
        "errors":         fp_errors + api_errors,
        "skipped":        skipped,
        "tagged":         tagged_count,
        "low_confidence": low_conf_count,
        "report_path":    str(report_path),
    }


# =============================================================================
#  CLI ENTRY POINT
# =============================================================================

def _pick_folder() -> Path | None:
    import tkinter as tk
    from tkinter import filedialog
    root_tk = tk.Tk()
    root_tk.withdraw()
    root_tk.attributes("-topmost", True)
    folder = filedialog.askdirectory(title="Select folder to fingerprint")
    root_tk.destroy()
    return Path(folder) if folder else None


def main():
    mode_label = ("DRY RUN -- tags will NOT be written"
                  if DRY_RUN else "APPLY -- tags will be written")
    min_conf   = float(_MIN_CONF) if _MIN_CONF else MIN_CONFIDENCE_DEFAULT

    print("=" * 65)
    print("  acoustid_fingerprint.py  v1.6")
    print("  Fingerprint audio files and look up AcousticID matches")
    print(f"  Mode : {mode_label}")
    print("=" * 65)

    if PICK_DIR:
        folder = _pick_folder()
        if not folder:
            print("No folder selected. Exiting.")
            sys.exit(0)
    elif _PATH_ARG:
        folder = Path(_PATH_ARG)
    else:
        print("ERROR: No folder specified.")
        print("  Use --pick  or  --path \"C:\\path\\to\\folder\"")
        sys.exit(1)

    cfg       = load_config()
    _acoustid = cfg.get("acoustid", {})
    fpcalc    = _acoustid.get("fpcalc_path", "fpcalc")
    api_key   = _acoustid.get("api_key", "")
    do_lookup = not NO_LOOKUP

    print(f"  Folder         : {folder}")
    print(f"  Database       : {DB_PATH}")
    print(f"  fpcalc         : {fpcalc}")
    print(f"  Lookup         : {'yes' if do_lookup else 'no (--no-lookup)'}")
    if DRY_RUN:
        print(f"  Write tags     : no (dry run -- add --apply to write tags)")
    else:
        print(f"  Write tags     : yes (score >= {min_conf})")
    print(f"  Min confidence : {min_conf}")
    print(f"  Skip cached    : {'yes' if not INCLUDE_CACHED else 'no (--include-cached)'}")
    print()

    if not DRY_RUN and do_lookup:
        print(f"  About to fingerprint, look up, and write tags in:")
        print(f"  {folder}")
        print(f"  Files with AcousticID score >= {min_conf} will have")
        print(f"  ACOUSTID_ID and ACOUSTID_FINGERPRINT written.")
        confirm = input("  Proceed? (y/n): ").strip().lower()
        while confirm not in ("y", "n"):
            confirm = input("  Please enter y or n: ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            sys.exit(0)
        print()

    try:
        result = run_acoustid_fingerprint(
            folder         = folder,
            fpcalc_path    = fpcalc,
            api_key        = api_key,
            skip_cached    = not INCLUDE_CACHED,
            do_lookup      = do_lookup,
            write_tags     = True,
            min_confidence = min_conf,
            dry_run        = DRY_RUN,
            log_callback   = lambda m: print(f"  {m}"),
            progress_callback = lambda c, t, n: print(
                f"  [{c}/{t}] {n}", end="\r", flush=True
            ) if n else None,
        )
    except (ValueError, RuntimeError) as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    print()
    print("  -- Results --------------------------------------------------")
    print(f"  Total files        : {result['total']}")
    print(f"  Fingerprinted      : {result['fingerprinted']}")

    print()

    print()
    print("  -- Results --------------------------------------------------")
    print(f"  Total files        : {result['total']}")
    print(f"  Fingerprinted      : {result['fingerprinted']}")
    print(f"  Skipped (cached)   : {result['skipped']}")
    print(f"  Identified         : {result['identified']}")
    print(f"  No AcousticID match: {result['no_match']}")
    print(f"  Errors             : {result['errors']}")
    if DRY_RUN:
        print(f"  Would be tagged    : {result['tagged']}")
    else:
        print(f"  Tagged             : {result['tagged']}")

    print(f"  Low confidence     : {result['low_confidence']}")
    print(f"  Report             : {result['report_path']}")


if __name__ == "__main__":
    main()
