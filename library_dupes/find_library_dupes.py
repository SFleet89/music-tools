"""
Library Duplicate Finder  v1.0
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

# CLI flags
REBUILD_CACHE  = "--rebuild-cache" in sys.argv
USE_FP         = "--no-fp"       not in sys.argv
USE_FILENAME   = "--no-filename" not in sys.argv

_cfg_flag  = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                   if a == "--config" and i+1 < len(sys.argv)), None)
_path_flag = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                   if a == "--path"   and i+1 < len(sys.argv)), None)

CONFIG_FILE = _cfg_flag or DEFAULT_CONFIG


def load_config(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {path}")
        print("       Run from the library_dupes folder, or use --config.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse config: {e}")
        sys.exit(1)


CFG          = load_config(CONFIG_FILE)
_folders     = CFG.get("folders", {})
_matching    = CFG.get("matching", {})
_perf        = CFG.get("performance", {})
_fp_cfg      = CFG.get("fingerprint", {})

ORGANIZED    = Path(_path_flag or _folders.get("organized", ""))
REPORTS_DIR  = Path(_folders.get("reports", "reports"))
FP_ENABLED      = USE_FP and bool(_matching.get("fp_enabled", True))
FN_ENABLED      = USE_FILENAME and bool(_matching.get("filename_fallback", True))
FP_THRESHOLD    = float(_matching.get("fp_similarity_threshold", 85))
DUR_TOL         = float(_matching.get("duration_tolerance_seconds", 2))
FUZZY_ENABLED   = bool(_matching.get("fuzzy_enabled", True))
FUZZY_THRESHOLD = float(_matching.get("fuzzy_threshold", 88))
FPCALC_PATH  = _fp_cfg.get("fpcalc_path", "fpcalc")
FP_CACHE_FILE = Path(_fp_cfg.get("fp_cache_file", "library_fp_cache.json"))
FP_MIN_LEN   = int(_fp_cfg.get("min_fp_length", 50))
LSH_BANDS    = int(_fp_cfg.get("lsh_bands", 20))
LSH_BAND_SZ  = int(_fp_cfg.get("lsh_band_size", 6))

_max_t       = int(_perf.get("max_threads", 0))
MAX_THREADS  = _max_t if _max_t > 0 else (os.cpu_count() or 4)


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


def scan_library(root: Path, errors: list) -> list[dict]:
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

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
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


def is_valid_fp(fp: str) -> bool:
    try:
        return bool(fp) and len(fp.split(",")) >= FP_MIN_LEN
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


def load_fp_cache(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_fp_cache(cache: dict, path: Path):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"  WARNING: Could not save fingerprint cache: {e}")


def build_fp_index(files: list, fpcalc_path: str, cache: dict, errors: list) -> tuple[list, list]:
    """
    Generate fingerprints for all files.
    Returns (fp_index, fp_warnings).
    fp_index  = list of {file, fingerprint} for valid files
    fp_warnings = list of (path_str, reason) for invalid/failed files
    """
    index    = []
    warnings = []
    pbar     = make_pbar(len(files), "Fingerprinting")

    for f in files:
        path_str = str(f["path"])
        fp = cache.get(path_str) or get_fingerprint(f["path"], fpcalc_path)

        if fp:
            cache[path_str] = fp
            if is_valid_fp(fp):
                index.append({"file": f, "fingerprint": fp})
            else:
                warnings.append((path_str, f"short fingerprint ({len(fp.split(','))} integers) — file may be corrupted or silent"))
        else:
            cache[path_str] = ""
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
        if dur_a and dur_b and abs(dur_a - dur_b) > DUR_TOL:
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
    if FUZZY_ENABLED and len(tagged_files) > 1:
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
                if title_score >= FUZZY_THRESHOLD and artist_score >= FUZZY_THRESHOLD:
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
) -> tuple[list[dict], set]:
    """
    Compare candidate pairs from LSH, return confirmed cross-folder duplicates.
    Returns (matches, seen_path_pairs).
    """
    candidates = find_fp_candidates(fp_index, LSH_BANDS, LSH_BAND_SZ)
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

def main():
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    errors     = []   # accumulated error list — written to log at end
    fp_warnings = []

    # ── Validate config ────────────────────────────────────────────────────────
    if not ORGANIZED or not ORGANIZED.exists():
        print(f"\nERROR: Organized folder not found: {ORGANIZED}")
        print("       Set 'folders.organized' in library_dupes_config.json or use --path.\n")
        sys.exit(1)

    if not FP_ENABLED and not FN_ENABLED:
        print("\nERROR: Both --no-fp and --no-filename specified. Nothing to do.\n")
        sys.exit(1)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Set up logging ─────────────────────────────────────────────────────────
    log_path = REPORTS_DIR / f"library_dupes_log_{timestamp}.txt"
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    log = logging.getLogger()

    # ── Header ─────────────────────────────────────────────────────────────────
    mode_parts = []
    if FP_ENABLED:   mode_parts.append("fingerprint")
    if FN_ENABLED:   mode_parts.append("filename")
    mode_label = " + ".join(mode_parts)

    log.info("")
    log.info("=" * 60)
    log.info("Library Duplicate Finder  v1.0")
    log.info("=" * 60)
    log.info(f"  Started   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"  Folder    : {ORGANIZED}")
    log.info(f"  Mode      : {mode_label}")
    log.info(f"  Threads   : {MAX_THREADS}")
    if FP_ENABLED:
        log.info(f"  FP thresh : {FP_THRESHOLD}%")
        log.info(f"  FP cache  : {FP_CACHE_FILE}")
    log.info("=" * 60)
    log.info("")

    # ── Scan library ───────────────────────────────────────────────────────────
    log.info("── Scanning library ────────────────────────────────────────")
    log.info("")
    files = scan_library(ORGANIZED, errors)
    log.info(f"\n  Files found : {len(files):,}")

    if not files:
        log.info("\n  No files found. Check your organized folder path.\n")
        sys.exit(0)

    # ── Fingerprint pass ───────────────────────────────────────────────────────
    all_matches  = []
    fp_seen_pairs = set()

    if FP_ENABLED:
        log.info("")
        log.info("── Fingerprint matching ────────────────────────────────────")
        log.info("")

        fpcalc_ok = check_fpcalc(FPCALC_PATH)
        if not fpcalc_ok:
            msg = f"  fpcalc not found at '{FPCALC_PATH}' — skipping fingerprint matching."
            log.info(msg)
            errors.append(f"CONFIG WARNING: {msg.strip()}")
        else:
            log.info(f"  fpcalc OK. Loading cache...")
            if REBUILD_CACHE and FP_CACHE_FILE.exists():
                FP_CACHE_FILE.unlink()
                log.info("  Fingerprint cache cleared.")

            fp_cache = load_fp_cache(FP_CACHE_FILE)
            log.info(f"  Cache entries loaded: {len(fp_cache):,}")
            log.info("")

            fp_index, fp_warnings = build_fp_index(files, FPCALC_PATH, fp_cache, errors)
            save_fp_cache(fp_cache, FP_CACHE_FILE)

            log.info(f"\n  Valid fingerprints : {len(fp_index):,}")
            log.info(f"  FP warnings        : {len(fp_warnings):,}")

            if fp_warnings:
                log.info(f"\n  WARNING: {len(fp_warnings)} file(s) produced invalid fingerprints:")
                for path_str, reason in fp_warnings:
                    log.info(f"    ! {Path(path_str).name} — {reason}")
                    log.info(f"      {path_str}")

            log.info("")
            log.info(f"  Finding candidates with LSH ({LSH_BANDS} bands × {LSH_BAND_SZ} integers)...")
            fp_matches, fp_seen_pairs = find_fp_duplicates(
                fp_index, ORGANIZED, FP_THRESHOLD, DUR_TOL, errors
            )
            all_matches.extend(fp_matches)
            log.info(f"\n  Fingerprint matches found : {len(fp_matches):,}")

    # ── Filename fallback ──────────────────────────────────────────────────────
    if FN_ENABLED:
        log.info("")
        log.info("── Filename + metadata matching ────────────────────────────")
        log.info("")

        fn_matches = find_filename_duplicates(files, ORGANIZED, fp_seen_pairs)
        all_matches.extend(fn_matches)
        log.info(f"  Filename/metadata matches found : {len(fn_matches):,}")

    # ── Sort results ───────────────────────────────────────────────────────────
    # Sort by match method, then by File A top folder, then filename
    all_matches.sort(key=lambda m: (
        m["method"],
        top_level_folder(m["file_a"]["path"], ORGANIZED),
        m["file_a"]["filename"],
    ))

    # ── Write reports ──────────────────────────────────────────────────────────
    log.info("")
    log.info("── Writing reports ─────────────────────────────────────────")
    log.info("")

    # Main CSV
    csv_path = REPORTS_DIR / f"library_dupes_{timestamp}.csv"
    try:
        write_csv(csv_path, all_matches, ORGANIZED)
        log.info(f"  Report saved   : {csv_path}")
    except Exception as e:
        errors.append(f"CSV WRITE ERROR: {e}")
        log.info(f"  ERROR writing CSV: {e}")

    # FP warnings CSV
    if fp_warnings:
        warn_path = REPORTS_DIR / f"library_dupes_fp_warnings_{timestamp}.csv"
        try:
            write_fp_warnings_csv(warn_path, fp_warnings, ORGANIZED)
            log.info(f"  FP warnings    : {warn_path}")
        except Exception as e:
            errors.append(f"FP WARNINGS CSV ERROR: {e}")

    # Error log
    if errors:
        err_path = REPORTS_DIR / f"library_dupes_errors_{timestamp}.txt"
        try:
            with open(err_path, "w", encoding="utf-8") as f:
                f.write(f"Library Duplicate Finder — Error Log\n")
                f.write(f"Run: {timestamp}\n")
                f.write("=" * 60 + "\n\n")
                for e in errors:
                    f.write(e + "\n")
            log.info(f"  Error log      : {err_path}  ({len(errors)} error(s))")
        except Exception as e:
            log.info(f"  WARNING: Could not write error log: {e}")

    # ── Summary ────────────────────────────────────────────────────────────────
    fp_count = sum(1 for m in all_matches if "fingerprint" in m["method"])
    fn_count = sum(1 for m in all_matches if "fingerprint" not in m["method"])

    log.info("")
    log.info("=" * 60)
    log.info("SUMMARY")
    log.info(f"  Files scanned              : {len(files):,}")
    log.info(f"  Cross-folder duplicates    : {len(all_matches):,}")
    if FP_ENABLED:
        log.info(f"    — by fingerprint         : {fp_count:,}")
        log.info(f"    — FP warnings            : {len(fp_warnings):,}")
    if FN_ENABLED:
        log.info(f"    — by filename/metadata   : {fn_count:,}")
    log.info(f"  Errors logged              : {len(errors):,}")
    log.info(f"\n  Report : {csv_path}")
    log.info(f"  Log    : {log_path}")
    log.info("=" * 60)
    log.info("")


if __name__ == "__main__":
    main()
