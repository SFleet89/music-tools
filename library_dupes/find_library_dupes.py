"""
Library Duplicate Finder  v1.3
================================
Scans your organized music library and finds songs that exist in more than one
top-level artist folder.

Examples of what this catches:
  Massive Attack - Teardrop  in both  Massive Attack/  and  Trip Hop/
  Daft Punk - Get Lucky      in both  Daft Punk/       and  Various Artists/

What it ignores:
  The same song appearing across multiple albums under the SAME artist folder.
  e.g. Massive Attack/Mezzanine/ and Massive Attack/Best Of/ — this is expected
  and is not flagged.

Matching methods (both used by default):
  1. Audio fingerprint  (fpcalc / Chromaprint) — catches renamed/retagged duplicates
  2. Filename fallback  — exact filename match OR Artist + Title parsed from filename

Nothing is moved or deleted. This script is completely read-only.

Requirements:
    pip install mutagen tqdm

Optional (for fingerprint matching):
    Download fpcalc from https://acoustid.org/chromaprint
    Set path in library_dupes_config.json under fingerprint.fpcalc_path

Usage:
    python find_library_dupes.py                      # full scan (fingerprint + filename)
    python find_library_dupes.py --no-fp              # filename matching only
    python find_library_dupes.py --no-filename        # fingerprint matching only
    python find_library_dupes.py --rebuild-cache      # clear fp cache and regenerate
    python find_library_dupes.py --path "C:\\Music"   # override organized folder
    python find_library_dupes.py --config my.json     # use a different config file

Changes in v1.3:
  - PW-01: Extracted run_find_library_dupes() as GUI-callable core.
    Parameters: organized_path, config_file, use_fp, use_filename,
    rebuild_cache, reports_dir, progress_callback, log_callback.
    Raises ValueError for bad paths/config. Returns dict: matches,
    fp_warnings, errors, report_path, log_path, reports_dir.
  - Moved module-level flags (REBUILD_CACHE, USE_FP, USE_FILENAME,
    _cfg_flag, _path_flag, CONFIG_FILE) and all config-derived constants
    (CFG, ORGANIZED, REPORTS_DIR, FP_ENABLED, FN_ENABLED, FP_THRESHOLD,
    DUR_TOL, FUZZY_ENABLED, FUZZY_THRESHOLD, FPCALC_PATH, FP_MIN_LEN,
    LSH_BANDS, LSH_BAND_SZ, MAX_THREADS) inside the run function.
    interactive_options([]) moved inside main(). No module-level side effects.
  - load_config() now raises ValueError instead of sys.exit().
  - is_valid_fp() takes min_fp_length param (removes FP_MIN_LEN global dep).
  - scan_library() takes max_threads param (removes MAX_THREADS global dep).
  - find_fp_duplicates() takes lsh_bands, lsh_band_size params.
  - find_filename_duplicates() takes dur_tol, fuzzy_enabled,
    fuzzy_threshold params (removes DUR_TOL/FUZZY_* global deps).
"""

import os
import sys
import re
import csv
import json
import hashlib
import logging
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── music_tools_common (project root) ─────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import open_db, init_db, DB_PATH
from music_tools_common import interactive_options

# ── Optional dependencies ──────────────────────────────────────────────────────
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    print("WARNING: 'tqdm' not installed. Progress bars disabled.")
    print("         Run:  pip install tqdm\n")

try:
    from rapidfuzz import fuzz as _fuzz
    def _fuzzy_score(a: str, b: str) -> float:
        return _fuzz.token_sort_ratio(a, b)
    HAS_RAPIDFUZZ = True
except ImportError:
    import difflib
    def _fuzzy_score(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio() * 100
    HAS_RAPIDFUZZ = False
    print("WARNING: 'rapidfuzz' not installed. Falling back to difflib for fuzzy matching.")
    print("         For better performance run:  pip install rapidfuzz\n")

try:
    from mutagen import File as MutagenFile
except ImportError:
    print("ERROR: 'mutagen' is not installed.")
    print("       Run:  pip install mutagen")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG = "library_dupes_config.json"
SUPPORTED_EXT  = {".mp3", ".flac", ".aac", ".m4a"}

def load_config(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ValueError(
            "Config file not found: %s\n"
            "Run from the library_dupes folder, or use --config." % path
        )
    except json.JSONDecodeError as e:
        raise ValueError("Could not parse config file %s: %s" % (path, e))


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def make_pbar(total: int, desc: str, unit: str = "file"):
    if HAS_TQDM:
        return tqdm(total=total, desc=f"  {desc}", unit=unit, ncols=80)
    class _Dummy:
        def update(self, n=1): pass
        def close(self): pass
        def set_postfix_str(self, s): pass
    return _Dummy()


def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_duration(secs) -> str:
    if secs is None:
        return ""
    m, s = divmod(int(secs), 60)
    return f"{m}:{s:02d}"


def fmt_bitrate(bps) -> str:
    if bps is None:
        return ""
    return f"{bps // 1000} kbps"


def top_level_folder(path: Path, root: Path) -> str:
    """Return the first path component relative to root."""
    try:
        parts = path.relative_to(root).parts
        return parts[0] if parts else ""
    except ValueError:
        return str(path.parent)


# ══════════════════════════════════════════════════════════════════════════════
#  FILE SCANNING & METADATA
# ══════════════════════════════════════════════════════════════════════════════

_scan_lock = threading.Lock()


def get_file_info(path: Path) -> dict | None:
    """Read metadata from a music file. Returns None on hard error."""
    try:
        size = path.stat().st_size
    except Exception as e:
        return None

    meta = {"title": "", "artist": "", "album": "", "bitrate": None, "duration": None}
    try:
        audio = MutagenFile(path)
        if audio is not None:
            easy = MutagenFile(path, easy=True)
            if easy:
                def first(tag):
                    val = easy.get(tag)
                    return val[0].strip().lower() if val else ""
                meta["title"]  = first("title")
                meta["artist"] = first("artist")
                meta["album"]  = first("album")
            if hasattr(audio, "info"):
                info = audio.info
                if hasattr(info, "bitrate"):
                    meta["bitrate"] = info.bitrate
                if hasattr(info, "length"):
                    meta["duration"] = info.length
    except Exception:
        pass  # metadata errors are non-fatal — file still included

    return {
        "path":     path,
        "filename": path.name,
        "stem":     path.stem,
        "size":     size,
        "metadata": meta,
    }


def scan_library(root: Path, errors: list, max_threads: int = 4) -> list[dict]:
    """Recursively scan root for music files. Appends scan errors to errors list."""
    all_paths = []
    try:
        all_paths = [
            p for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXT
        ]
    except Exception as e:
        errors.append(f"ERROR scanning folder {root}: {e}")
        return []

    results = []
    pbar    = make_pbar(len(all_paths), "Scanning library")

    def process(path):
        try:
            info = get_file_info(path)
            if info is None:
                errors.append(f"SCAN ERROR: Could not read {path}")
            return info
        except Exception as e:
            errors.append(f"SCAN ERROR: {path} — {e}")
            return None

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {executor.submit(process, p): p for p in all_paths}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                errors.append(f"THREAD ERROR: {futures[future]} — {e}")
            pbar.update(1)

    pbar.close()
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  FINGERPRINTING
# ══════════════════════════════════════════════════════════════════════════════

def check_fpcalc(path: str) -> bool:
    try:
        r = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def get_fingerprint(path: Path, fpcalc_path: str) -> str | None:
    try:
        r = subprocess.run(
            [fpcalc_path, "-raw", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        for line in r.stdout.splitlines():
            if line.startswith("FINGERPRINT="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


def is_valid_fp(fp: str, min_fp_length: int = 50) -> bool:
    try:
        return bool(fp) and len(fp.split(",")) >= min_fp_length
    except Exception:
        return False


def fp_similarity(fp1: str, fp2: str) -> float:
    """Hamming-distance similarity between two raw Chromaprint fingerprints (0–100)."""
    try:
        i1 = list(map(int, fp1.split(",")))
        i2 = list(map(int, fp2.split(",")))
        length = min(len(i1), len(i2))
        if length == 0:
            return 0.0
        total = length * 32
        diff  = sum(bin(a ^ b).count("1") for a, b in zip(i1[:length], i2[:length]))
        return (1 - diff / total) * 100
    except Exception:
        return 0.0


def build_fp_index(files: list, fpcalc_path: str, conn, errors: list,
                   min_fp_length: int = 50) -> tuple[list, list]:
    """
    Generate fingerprints for all files, caching results in the shared
    music_cache.db fp_cache table (via music_tools_common).

    Returns (fp_index, fp_warnings).
    fp_index    = list of {file, fingerprint} for valid files
    fp_warnings = list of (path_str, reason) for invalid/failed files
    """
    index    = []
    warnings = []
    pbar     = make_pbar(len(files), "Fingerprinting")

    for f in files:
        path_str = str(f["path"])
        fp = None

        # ── Cache lookup ───────────────────────────────────────────────────────
        try:
            actual_mtime = f["path"].stat().st_mtime
        except Exception:
            actual_mtime = 0.0

        row = conn.execute(
            "SELECT fingerprint, mtime FROM fp_cache WHERE path_str = ?",
            (path_str,)
        ).fetchone()

        if row and abs(row["mtime"] - actual_mtime) < 1.0:
            # Cache hit — use stored fingerprint (may be "" for a known failure)
            fp = row["fingerprint"] or None
        else:
            # Cache miss or stale — compute and store
            fp = get_fingerprint(f["path"], fpcalc_path)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO fp_cache "
                    "(path_str, mtime, fingerprint, fp_duration) VALUES (?, ?, ?, ?)",
                    (path_str, actual_mtime, fp or "", f.get("duration"))
                )
                conn.commit()
            except Exception:
                pass

        # ── Classify result ────────────────────────────────────────────────────
        if fp:
            if is_valid_fp(fp, min_fp_length=min_fp_length):
                index.append({"file": f, "fingerprint": fp})
            else:
                warnings.append((path_str, f"short fingerprint ({len(fp.split(','))} integers) — file may be corrupted or silent"))
        else:
            warnings.append((path_str, "fingerprint generation failed"))
            errors.append(f"FP ERROR: {path_str} — fingerprint generation failed")

        pbar.update(1)

    pbar.close()
    return index, warnings


# ══════════════════════════════════════════════════════════════════════════════
#  LSH — FAST CANDIDATE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def lsh_bands(fp_str: str, n_bands: int, band_size: int) -> list[int]:
    """
    Split a fingerprint into bands and return a hash for each band.
    Used for fast candidate pair detection — files sharing any band hash
    are compared with full similarity.
    """
    try:
        ints   = list(map(int, fp_str.split(",")))
        needed = n_bands * band_size
        if len(ints) < needed:
            return []
        result = []
        for i in range(n_bands):
            band = tuple(ints[i * band_size : (i + 1) * band_size])
            result.append(hash(band))
        return result
    except Exception:
        return []


def find_fp_candidates(fp_index: list, n_bands: int, band_size: int) -> set:
    """
    Use LSH band hashing to find candidate duplicate pairs efficiently.
    Returns a set of (i, j) index pairs where i < j.
    O(n) bucket building, much faster than O(n²) direct comparison.
    """
    buckets = defaultdict(list)
    for idx, item in enumerate(fp_index):
        bands = lsh_bands(item["fingerprint"], n_bands, band_size)
        for b_num, b_hash in enumerate(bands):
            buckets[(b_num, b_hash)].append(idx)

    candidates = set()
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a = min(bucket[i], bucket[j])
                b = max(bucket[i], bucket[j])
                candidates.add((a, b))

    return candidates


# ══════════════════════════════════════════════════════════════════════════════
#  FILENAME MATCHING
# ══════════════════════════════════════════════════════════════════════════════

_TRACK_NUM_RE = re.compile(r'^\d+\s*[-\.]\s*', re.IGNORECASE)

# Generic structural track names that appear on almost every album/OST.
# Exact filename matching is skipped for these — they should only be matched
# by audio fingerprint (which compares actual audio) or Artist + Title
# (which requires the artist to also match).
GENERIC_STEMS = {
    "intro",
    "outro",
    "interlude",
    "main title",
    "main theme",
    "title theme",
    "title screen",
    "opening theme",
    "opening",
    "ending",
    "end credits",
    "credits",
    "epilogue",
    "prologue",
    "prelude",
    "overture",
    "game over",
    "victory",
    "fanfare",
    "jingle",
    "[untitled]",
    "untitled",
    "track",
    "bonus track",
    "hidden track",
}


def parse_artist_title(stem: str) -> tuple[str, str]:
    """
    Try to extract (artist, title) from a filename stem.
    Handles: Artist - Title, 01 - Artist - Title, 01 - Title.
    Returns ("", title) if no artist separator found.
    """
    # Strip leading track number
    s = _TRACK_NUM_RE.sub("", stem).strip()
    parts = s.split(" - ")
    if len(parts) >= 2:
        artist = parts[0].strip().lower()
        title  = " - ".join(parts[1:]).strip().lower()
        return artist, title
    return "", s.strip().lower()


def filename_key(stem: str) -> str:
    """Normalised filename key for exact matching."""
    return _TRACK_NUM_RE.sub("", stem).strip().lower()


def is_generic_stem(key: str) -> bool:
    """Return True if this stem is too generic for reliable exact filename matching."""
    return key in GENERIC_STEMS or key == ""


def find_filename_duplicates(
    files: list[dict],
    root: Path,
    existing_pairs: set,
    dur_tol: float = 2.0,
    fuzzy_enabled: bool = True,
    fuzzy_threshold: float = 88.0,
) -> list[dict]:
    """
    Find cross-folder duplicates by:
      1. Exact filename match (after stripping track number) — skips generic names
      2. Artist + Title from embedded metadata tags — requires both to be non-empty

    Skips pairs already found by fingerprint matching.
    Returns list of match dicts.
    """
    # Build lookup indices
    by_filename     = defaultdict(list)   # normalised stem → files
    by_meta_tags    = defaultdict(list)   # normalised (artist, title) → files
    tagged_files    = []                  # files with both tags — for fuzzy pass

    for f in files:
        fkey   = filename_key(f["stem"])
        meta   = f.get("metadata", {})
        artist = (meta.get("artist") or "").strip().lower()
        title  = (meta.get("title")  or "").strip().lower()

        by_filename[fkey].append(f)

        if artist and title:
            by_meta_tags[(artist, title)].append(f)
            tagged_files.append((artist, title, f))

    matches = []
    seen_pairs = set(existing_pairs)

    def add_match(fa, fb, method):
        key = tuple(sorted([str(fa["path"]), str(fb["path"])]))
        if key in seen_pairs:
            return
        # Cross-folder check
        ta = top_level_folder(fa["path"], root)
        tb = top_level_folder(fb["path"], root)
        if ta == tb:
            return
        # Duration check
        dur_a = fa.get("metadata", {}).get("duration")
        dur_b = fb.get("metadata", {}).get("duration")
        if dur_a and dur_b and abs(dur_a - dur_b) > dur_tol:
            return
        seen_pairs.add(key)
        matches.append({
            "file_a":  fa,
            "file_b":  fb,
            "method":  method,
            "score":   None,
        })

    # Exact filename matches — skip generic structural names
    skipped_generic = 0
    for fkey, group in by_filename.items():
        if len(group) < 2:
            continue
        if is_generic_stem(fkey):
            skipped_generic += len(group)
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                add_match(group[i], group[j], "exact filename")
    if skipped_generic:
        print(f"  Skipped {skipped_generic} file(s) with generic names (intro, outro, main title, etc.)")

    # Exact metadata tag matches — artist AND title must both match exactly
    meta_skipped = 0
    for (artist, title), group in by_meta_tags.items():
        if len(group) < 2:
            continue
        if is_generic_stem(title):
            meta_skipped += 1
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                add_match(group[i], group[j], "metadata tags")
    if meta_skipped:
        print(f"  Skipped {meta_skipped} metadata group(s) with generic titles")

    # Fuzzy metadata matching — catches slight tag inconsistencies
    # e.g. "The Beatles" vs "Beatles", "feat." vs "ft."
    if fuzzy_enabled and len(tagged_files) > 1:
        for i in range(len(tagged_files)):
            artist_i, title_i, fi = tagged_files[i]
            if is_generic_stem(title_i):
                continue
            for j in range(i + 1, len(tagged_files)):
                artist_j, title_j, fj = tagged_files[j]
                if is_generic_stem(title_j):
                    continue
                # Quick exact check first to avoid fuzzy overhead
                if artist_i == artist_j and title_i == title_j:
                    continue  # already handled by exact pass
                # Fuzzy check — title must be very similar, artist reasonably similar
                title_score  = _fuzzy_score(title_i, title_j)
                artist_score = _fuzzy_score(artist_i, artist_j)
                if title_score >= fuzzy_threshold and artist_score >= fuzzy_threshold:
                    add_match(fi, fj, f"metadata tags (fuzzy {title_score:.0f}%)")

    return matches


# ══════════════════════════════════════════════════════════════════════════════
#  FINGERPRINT MATCHING
# ══════════════════════════════════════════════════════════════════════════════

def find_fp_duplicates(
    fp_index: list[dict],
    root: Path,
    threshold: float,
    dur_tol: float,
    errors: list,
    lsh_bands: int = 20,
    lsh_band_size: int = 6,
) -> tuple[list[dict], set]:
    """
    Compare candidate pairs from LSH, return confirmed cross-folder duplicates.
    Returns (matches, seen_path_pairs).
    """
    candidates = find_fp_candidates(fp_index, lsh_bands, lsh_band_size)
    matches     = []
    seen_pairs  = set()

    pbar = make_pbar(len(candidates), "Comparing candidates")

    for (i, j) in candidates:
        try:
            ia = fp_index[i]
            ib = fp_index[j]
            fa = ia["file"]
            fb = ib["file"]

            # Only flag cross-folder duplicates
            ta = top_level_folder(fa["path"], root)
            tb = top_level_folder(fb["path"], root)
            if ta == tb:
                pbar.update(1)
                continue

            # Duration check
            dur_a = fa["metadata"].get("duration")
            dur_b = fb["metadata"].get("duration")
            if dur_a and dur_b and abs(dur_a - dur_b) > dur_tol:
                pbar.update(1)
                continue

            score = fp_similarity(ia["fingerprint"], ib["fingerprint"])
            if score >= threshold:
                pair_key = tuple(sorted([str(fa["path"]), str(fb["path"])]))
                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    matches.append({
                        "file_a": fa,
                        "file_b": fb,
                        "method": f"audio fingerprint ({score:.0f}%)",
                        "score":  score,
                    })

        except Exception as e:
            errors.append(f"FP COMPARE ERROR: indices ({i},{j}) — {e}")

        pbar.update(1)

    pbar.close()
    return matches, seen_pairs


# ══════════════════════════════════════════════════════════════════════════════
#  REPORTING
# ══════════════════════════════════════════════════════════════════════════════

def make_csv_row(match: dict, root: Path) -> dict:
    fa = match["file_a"]
    fb = match["file_b"]
    meta_a = fa["metadata"]
    meta_b = fb["metadata"]

    def rel(f):
        try:
            return str(f["path"].relative_to(root))
        except ValueError:
            return str(f["path"])

    return {
        "Match Method":        match["method"],
        "FP Score":            f"{match['score']:.1f}%" if match["score"] else "",
        "File A - Filename":   fa["filename"],
        "File A - Top Folder": top_level_folder(fa["path"], root),
        "File A - Folder":     str(fa["path"].parent.relative_to(root)) if fa["path"].is_relative_to(root) else str(fa["path"].parent),
        "File A - Size":       fmt_size(fa["size"]),
        "File A - Bitrate":    fmt_bitrate(meta_a.get("bitrate")),
        "File A - Duration":   fmt_duration(meta_a.get("duration")),
        "File A - Title":      meta_a.get("title", ""),
        "File A - Artist":     meta_a.get("artist", ""),
        "File A - Album":      meta_a.get("album", ""),
        "File A - Full Path":  str(fa["path"]),
        "File B - Filename":   fb["filename"],
        "File B - Top Folder": top_level_folder(fb["path"], root),
        "File B - Folder":     str(fb["path"].parent.relative_to(root)) if fb["path"].is_relative_to(root) else str(fb["path"].parent),
        "File B - Size":       fmt_size(fb["size"]),
        "File B - Bitrate":    fmt_bitrate(meta_b.get("bitrate")),
        "File B - Duration":   fmt_duration(meta_b.get("duration")),
        "File B - Title":      meta_b.get("title", ""),
        "File B - Artist":     meta_b.get("artist", ""),
        "File B - Album":      meta_b.get("album", ""),
        "File B - Full Path":  str(fb["path"]),
    }


CSV_FIELDS = [
    "Match Method", "FP Score",
    "File A - Filename", "File A - Top Folder", "File A - Folder",
    "File A - Size", "File A - Bitrate", "File A - Duration",
    "File A - Title", "File A - Artist", "File A - Album", "File A - Full Path",
    "File B - Filename", "File B - Top Folder", "File B - Folder",
    "File B - Size", "File B - Bitrate", "File B - Duration",
    "File B - Title", "File B - Artist", "File B - Album", "File B - Full Path",
]


def write_csv(path: Path, rows: list, root: Path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows([make_csv_row(r, root) for r in rows])


def write_fp_warnings_csv(path: Path, warnings: list, root: Path):
    fields = ["Folder", "Filename", "Full Path", "Reason", "Fingerprint Length"]
    rows   = []
    for path_str, reason in warnings:
        p = Path(path_str)
        try:
            folder = str(p.parent.relative_to(root))
        except ValueError:
            folder = str(p.parent)
        m      = re.search(r'\((\d+) integers?\)', reason)
        fp_len = int(m.group(1)) if m else ""
        clean  = re.sub(r'\s*\(\d+ integers?\)', '', reason).strip()
        rows.append({
            "Folder":             folder,
            "Filename":           p.name,
            "Full Path":          path_str,
            "Reason":             clean,
            "Fingerprint Length": fp_len,
        })
    rows.sort(key=lambda r: (r["Reason"], r["Folder"], r["Filename"]))
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def run_find_library_dupes(
    organized_path=None,
    config_file=None,
    use_fp=True,
    use_filename=True,
    rebuild_cache=False,
    reports_dir=None,
    progress_callback=None,
    log_callback=None,
):
    """
    GUI-callable core for Library Duplicate Finder.

    Parameters
    ----------
    organized_path  : str, Path, or None — override folders.organized from config.
    config_file     : str or None — path to JSON config (default: library_dupes_config.json).
    use_fp          : bool — enable audio fingerprint matching (default True).
    use_filename    : bool — enable filename/metadata matching (default True).
    rebuild_cache   : bool — clear and rebuild the fingerprint cache.
    reports_dir     : str, Path, or None — override reports directory from config.
    progress_callback : callable(current, total, filename) or None.
    log_callback    : callable(message) or None — key status lines sent here.

    Returns
    -------
    dict with keys:
        matches     — list of match dicts (one per duplicate pair found)
        fp_warnings — list of (path_str, reason) for fingerprinting failures
        errors      — list of error strings accumulated during the run
        report_path — Path to the main CSV report
        log_path    — Path to the log file
        reports_dir — Path to the reports directory used
    """
    def _log(msg):
        print(msg)
        if log_callback:
            try:
                log_callback(msg)
            except Exception:
                pass

    # -- Load config -----------------------------------------------------------
    cfg_path = config_file or DEFAULT_CONFIG
    cfg      = load_config(cfg_path)   # raises ValueError on missing/bad file

    _folders = cfg.get("folders",     {})
    _matching = cfg.get("matching",   {})
    _perf    = cfg.get("performance", {})
    _fp_cfg  = cfg.get("fingerprint", {})

    # Config-derived settings
    fp_enabled      = use_fp       and bool(_matching.get("fp_enabled",           True))
    fn_enabled      = use_filename and bool(_matching.get("filename_fallback",     True))
    fp_threshold    = float(_matching.get("fp_similarity_threshold",  85))
    dur_tol         = float(_matching.get("duration_tolerance_seconds", 2))
    fuzzy_enabled   = bool(_matching.get("fuzzy_enabled",             True))
    fuzzy_threshold = float(_matching.get("fuzzy_threshold",           88))
    fpcalc_path     = _fp_cfg.get("fpcalc_path", "fpcalc")
    fp_min_len      = int(_fp_cfg.get("min_fp_length",  50))
    lsh_bands_n     = int(_fp_cfg.get("lsh_bands",      20))
    lsh_band_sz     = int(_fp_cfg.get("lsh_band_size",   6))
    _max_t          = int(_perf.get("max_threads", 0))
    max_threads     = _max_t if _max_t > 0 else (os.cpu_count() or 4)

    # -- Validate inputs -------------------------------------------------------
    if not fp_enabled and not fn_enabled:
        raise ValueError("Both fingerprint and filename matching are disabled. Nothing to do.")

    organized = Path(organized_path or _folders.get("organized", ""))
    if not organized or not organized.exists():
        raise ValueError("Organized folder not found: %s\n"
                         "Set folders.organized in config or pass organized_path." % organized)

    rdir = Path(reports_dir) if reports_dir else Path(_folders.get("reports", "reports"))
    if not rdir.is_absolute():
        rdir = Path(path).parent / rdir   # relative to library_dupes folder
    rdir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    errors     = []
    fp_warnings = []

    # -- Logging ---------------------------------------------------------------
    log_path = rdir / ("library_dupes_log_%s.txt" % timestamp)
    logger   = logging.getLogger("find_library_dupes_%s" % timestamp)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fh = logging.FileHandler(str(log_path), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)

    def log(msg):
        logger.info(msg)
        _log(msg)

    # -- Header ----------------------------------------------------------------
    mode_parts = []
    if fp_enabled: mode_parts.append("fingerprint")
    if fn_enabled: mode_parts.append("filename")
    mode_label = " + ".join(mode_parts)

    log("")
    log("=" * 60)
    log("Library Duplicate Finder  v1.3")
    log("=" * 60)
    log("  Started   : %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log("  Folder    : %s" % organized)
    log("  Mode      : %s" % mode_label)
    log("  Threads   : %d" % max_threads)
    if fp_enabled:
        log("  FP thresh : %.0f%%" % fp_threshold)
        log("  FP cache  : %s (fp_cache table)" % DB_PATH)
    log("=" * 60)
    log("")

    # -- Scan library ----------------------------------------------------------
    log("-- Scanning library ------------------------------------------------")
    log("")
    files = scan_library(organized, errors, max_threads=max_threads)
    log("\n  Files found : %d" % len(files))

    if not files:
        log("\n  No files found. Check your organized folder path.\n")
        return {
            "matches":     [],
            "fp_warnings": [],
            "errors":      errors,
            "report_path": None,
            "log_path":    log_path,
            "reports_dir": rdir,
        }

    # -- Fingerprint pass ------------------------------------------------------
    all_matches  = []
    fp_seen_pairs = set()

    if fp_enabled:
        log("")
        log("-- Fingerprint matching --------------------------------------------")
        log("")

        fpcalc_ok = check_fpcalc(fpcalc_path)
        if not fpcalc_ok:
            msg = "  fpcalc not found at '%s' -- skipping fingerprint matching." % fpcalc_path
            log(msg)
            errors.append("CONFIG WARNING: %s" % msg.strip())
        else:
            log("  fpcalc OK. Opening fingerprint cache (music_cache.db)...")
            conn = open_db()
            init_db(conn)

            if rebuild_cache:
                conn.execute("DELETE FROM fp_cache")
                conn.commit()
                log("  Fingerprint cache cleared.")

            cache_count = conn.execute("SELECT COUNT(*) FROM fp_cache").fetchone()[0]
            log("  Cache entries loaded: %d" % cache_count)
            log("")

            fp_index, fp_warnings = build_fp_index(
                files, fpcalc_path, conn, errors, min_fp_length=fp_min_len
            )

            log("\n  Valid fingerprints : %d" % len(fp_index))
            log("  FP warnings        : %d" % len(fp_warnings))

            if fp_warnings:
                log("\n  WARNING: %d file(s) produced invalid fingerprints:" % len(fp_warnings))
                for path_str, reason in fp_warnings:
                    log("    ! %s -- %s" % (Path(path_str).name, reason))
                    log("      %s" % path_str)

            log("")
            log("  Finding candidates with LSH (%d bands x %d integers)..." % (lsh_bands_n, lsh_band_sz))
            fp_matches, fp_seen_pairs = find_fp_duplicates(
                fp_index, organized, fp_threshold, dur_tol, errors,
                lsh_bands=lsh_bands_n, lsh_band_size=lsh_band_sz,
            )
            all_matches.extend(fp_matches)
            log("\n  Fingerprint matches found : %d" % len(fp_matches))

    # -- Filename fallback -----------------------------------------------------
    if fn_enabled:
        log("")
        log("-- Filename + metadata matching ------------------------------------")
        log("")
        fn_matches = find_filename_duplicates(
            files, organized, fp_seen_pairs,
            dur_tol=dur_tol,
            fuzzy_enabled=fuzzy_enabled,
            fuzzy_threshold=fuzzy_threshold,
        )
        all_matches.extend(fn_matches)
        log("  Filename/metadata matches found : %d" % len(fn_matches))

    # -- Sort results ----------------------------------------------------------
    all_matches.sort(key=lambda m: (
        m["method"],
        top_level_folder(m["file_a"]["path"], organized),
        m["file_a"]["filename"],
    ))

    # -- Write reports ---------------------------------------------------------
    log("")
    log("-- Writing reports -------------------------------------------------")
    log("")

    csv_path = rdir / ("library_dupes_%s.csv" % timestamp)
    try:
        write_csv(csv_path, all_matches, organized)
        log("  Report saved   : %s" % csv_path)
    except Exception as e:
        errors.append("CSV WRITE ERROR: %s" % e)
        log("  ERROR writing CSV: %s" % e)

    if fp_warnings:
        warn_path = rdir / ("library_dupes_fp_warnings_%s.csv" % timestamp)
        try:
            write_fp_warnings_csv(warn_path, fp_warnings, organized)
            log("  FP warnings    : %s" % warn_path)
        except Exception as e:
            errors.append("FP WARNINGS CSV ERROR: %s" % e)

    if errors:
        err_path = rdir / ("library_dupes_errors_%s.txt" % timestamp)
        try:
            with open(err_path, "w", encoding="utf-8") as ef:
                ef.write("Library Duplicate Finder -- Error Log\n")
                ef.write("Run: %s\n" % timestamp)
                ef.write("=" * 60 + "\n\n")
                for e in errors:
                    ef.write(e + "\n")
            log("  Error log      : %s  (%d error(s))" % (err_path, len(errors)))
        except Exception as e:
            log("  WARNING: Could not write error log: %s" % e)

    # -- Summary ---------------------------------------------------------------
    fp_count = sum(1 for m in all_matches if "fingerprint" in m["method"])
    fn_count = sum(1 for m in all_matches if "fingerprint" not in m["method"])

    log("")
    log("=" * 60)
    log("SUMMARY")
    log("  Files scanned              : %d" % len(files))
    log("  Cross-folder duplicates    : %d" % len(all_matches))
    if fp_enabled:
        log("    -- by fingerprint        : %d" % fp_count)
        log("    -- FP warnings           : %d" % len(fp_warnings))
    if fn_enabled:
        log("    -- by filename/metadata  : %d" % fn_count)
    log("  Errors logged              : %d" % len(errors))
    log("\n  Report : %s" % csv_path)
    log("  Log    : %s" % log_path)
    log("=" * 60)
    log("")

    return {
        "matches":     all_matches,
        "fp_warnings": fp_warnings,
        "errors":      errors,
        "report_path": csv_path,
        "log_path":    log_path,
        "reports_dir": rdir,
    }


def main():
    # -- Flag parsing ----------------------------------------------------------
    REBUILD_CACHE = "--rebuild-cache" in sys.argv
    USE_FP        = "--no-fp"       not in sys.argv
    USE_FILENAME  = "--no-filename" not in sys.argv

    _cfg_flag  = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                       if a == "--config" and i+1 < len(sys.argv)), None)
    _path_flag = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                       if a == "--path"   and i+1 < len(sys.argv)), None)

    interactive_options([
        ("--rebuild-cache", "Rebuild cache -- ignore cached fingerprints, re-fingerprint all"),
    ])

    try:
        run_find_library_dupes(
            organized_path = _path_flag,
            config_file    = _cfg_flag or DEFAULT_CONFIG,
            use_fp         = USE_FP,
            use_filename   = USE_FILENAME,
            rebuild_cache  = REBUILD_CACHE,
        )
    except ValueError as exc:
        print("ERROR: %s" % exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
