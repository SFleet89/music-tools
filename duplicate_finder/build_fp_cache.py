"""
Music Cache Builder  v1.0
==========================
Pre-builds the cache files used by find_music_duplicates.py so that duplicate
scans start fast and the fingerprint pass runs near-instantly.

Two caches can be built:

  Metadata cache  (music_cache.json)
      Stores filename, tags, bitrate, and duration for every file in your
      organized library. find_music_duplicates.py uses this to skip re-reading
      metadata on files that haven't changed since the last scan.

  Fingerprint cache  (music_fp_cache.json)
      Stores the Chromaprint audio fingerprint for every file. The duplicate
      finder uses these during the optional fingerprint pass to identify renamed
      or retagged duplicates. Building this cache in advance means the
      fingerprint pass takes seconds rather than minutes.

Both caches are incremental by default — only new or changed files are
processed. Use --rebuild to force a full rebuild from scratch.

Running this script also serves as a library audit: any files that fail
fingerprinting or produce suspiciously short fingerprints are flagged and
saved to a CSV report.

Requirements:
    pip install mutagen tqdm
    fpcalc (Chromaprint) — required for fingerprint cache only
    Download from: https://acoustid.org/chromaprint

Usage:
    python build_fp_cache.py                    # build both caches (incremental)
    python build_fp_cache.py --metadata-only    # metadata cache only
    python build_fp_cache.py --fp-only          # fingerprint cache only
    python build_fp_cache.py --rebuild          # wipe and rebuild selected cache(s)
    python build_fp_cache.py --path "C:\\Music" # override organized folder path
    python build_fp_cache.py --config my.json   # use a different config file
    python build_fp_cache.py --threads 4        # override thread count
"""

import sys
import os
import json
import csv
import re
import hashlib
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Optional dependencies ──────────────────────────────────────────────────────
try:
    from mutagen import File as MutagenFile
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False
    print("ERROR: 'mutagen' is not installed.")
    print("       Run:  pip install mutagen")
    sys.exit(1)

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ── Constants ──────────────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".aac", ".m4a"}
FP_MIN_LENGTH        = 50      # fingerprints shorter than this are flagged as invalid


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

def load_config(config_path: str) -> dict:
    try:
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse config file: {e}")
        sys.exit(1)


def get_config_path() -> str:
    for i, arg in enumerate(sys.argv):
        if arg == "--config" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    # Look for music_config.json next to this script
    local = Path(__file__).parent / "music_config.json"
    if local.exists():
        return str(local)
    return "music_config.json"


# ── Parse CLI flags ────────────────────────────────────────────────────────────
REBUILD      = "--rebuild"      in sys.argv
META_ONLY    = "--metadata-only" in sys.argv
FP_ONLY      = "--fp-only"      in sys.argv
BUILD_META   = not FP_ONLY
BUILD_FP     = not META_ONLY

_path_arg    = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                     if a == "--path" and i+1 < len(sys.argv)), None)
_threads_arg = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                     if a == "--threads" and i+1 < len(sys.argv)), None)

# ── Load config ────────────────────────────────────────────────────────────────
CFG          = load_config(get_config_path())
_folders     = CFG.get("folders", {})
_perf        = CFG.get("performance", {})
_acoustid    = CFG.get("acoustid", {})
_output      = CFG.get("output", {})

ORGANIZED    = Path(_path_arg or _folders.get("organized", ""))
REPORTS_DIR  = Path(_output.get("log_folder", ""))
META_CACHE   = Path(_perf.get("cache_file", "music_cache.json"))
FP_CACHE     = Path(_acoustid.get("fp_cache_file", "music_fp_cache.json"))
FPCALC_PATH  = _acoustid.get("fpcalc_path", "fpcalc")

_max_t = int(_threads_arg) if _threads_arg and _threads_arg.isdigit() else int(_perf.get("max_threads", 0))
MAX_THREADS = _max_t if _max_t > 0 else (os.cpu_count() or 4)


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def make_pbar(total: int, desc: str, unit: str = "file"):
    if HAS_TQDM:
        return tqdm(total=total, desc=f"  {desc}", unit=unit, ncols=80)
    class _Dummy:
        def update(self, n=1): pass
        def close(self): pass
        def set_postfix_str(self, s): pass
    return _Dummy()


def load_json(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_json(data: dict, path: Path):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"  WARNING: Could not save cache to {path}: {e}")


def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ══════════════════════════════════════════════════════════════════════════════
#  METADATA CACHE
# ══════════════════════════════════════════════════════════════════════════════

_meta_lock = threading.Lock()


def _cache_key(path: Path) -> str:
    """Stable cache key: path + mtime + size."""
    import hashlib
    stat = path.stat()
    raw  = f"{path}|{stat.st_mtime}|{stat.st_size}"
    return hashlib.md5(raw.encode()).hexdigest()


def get_file_metadata(path: Path) -> dict:
    """Read tags, bitrate, and duration from a music file."""
    size = path.stat().st_size
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
        pass
    return {
        "filename": path.name.lower(),
        "size":     size,
        "metadata": meta,
        "path_str": str(path),
    }


def build_metadata_cache(folder: Path, existing_cache: dict) -> tuple[dict, int, int]:
    """
    Scan folder and build/update metadata cache.
    Returns (new_cache, new_count, cached_count).
    """
    all_paths = [
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    new_cache   = {}
    new_count   = 0
    cached_count = 0
    pbar = make_pbar(len(all_paths), "Scanning metadata")

    def process(path):
        key = _cache_key(path)
        with _meta_lock:
            if key in existing_cache:
                return key, existing_cache[key], False
        info = get_file_metadata(path)
        return key, info, True

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = {executor.submit(process, p): p for p in all_paths}
        for future in as_completed(futures):
            try:
                key, info, is_new = future.result()
                with _meta_lock:
                    new_cache[key] = info
                if is_new:
                    new_count += 1
                else:
                    cached_count += 1
            except Exception as e:
                pass
            pbar.update(1)

    pbar.close()
    return new_cache, new_count, cached_count


# ══════════════════════════════════════════════════════════════════════════════
#  FINGERPRINT CACHE
# ══════════════════════════════════════════════════════════════════════════════

def check_fpcalc(fpcalc_path: str) -> bool:
    try:
        result = subprocess.run(
            [fpcalc_path, "-version"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_fingerprint(path: Path, fpcalc_path: str) -> str | None:
    try:
        result = subprocess.run(
            [fpcalc_path, "-raw", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        for line in result.stdout.splitlines():
            if line.startswith("FINGERPRINT="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


def is_valid_fingerprint(fp: str) -> bool:
    try:
        return len(fp.split(",")) >= FP_MIN_LENGTH
    except Exception:
        return False


def build_fingerprint_cache(
    folder: Path,
    existing_cache: dict,
    fpcalc_path: str,
) -> tuple[dict, int, int, list]:
    """
    Fingerprint all files in folder, updating the existing cache.
    Returns (new_cache, new_count, cached_count, warnings).
    warnings = list of (path_str, reason) for invalid/failed fingerprints.
    """
    all_paths = [
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    new_cache    = dict(existing_cache)  # start from existing
    new_count    = 0
    cached_count = 0
    warnings     = []
    pbar = make_pbar(len(all_paths), "Fingerprinting files")

    for path in all_paths:
        path_str = str(path)

        # Use cached fingerprint if present (and not rebuilding)
        if path_str in existing_cache:
            fp = existing_cache[path_str]
            cached_count += 1
            # Still validate — warn if cached fingerprint is bad
            if fp and not is_valid_fingerprint(fp):
                warnings.append((path_str, f"short fingerprint ({len(fp.split(','))} integers) — file may be corrupted or silent"))
            elif not fp:
                warnings.append((path_str, "fingerprint generation failed (cached)"))
            pbar.update(1)
            continue

        # Generate new fingerprint
        fp = get_fingerprint(path, fpcalc_path)
        new_count += 1

        if fp:
            new_cache[path_str] = fp
            if not is_valid_fingerprint(fp):
                warnings.append((path_str, f"short fingerprint ({len(fp.split(','))} integers) — file may be corrupted or silent"))
        else:
            new_cache[path_str] = ""   # cache the failure so we don't retry every run
            warnings.append((path_str, "fingerprint generation failed"))

        pbar.update(1)

    pbar.close()
    return new_cache, new_count, cached_count, warnings


# ══════════════════════════════════════════════════════════════════════════════
#  WARNINGS CSV
# ══════════════════════════════════════════════════════════════════════════════

def write_warnings_csv(csv_path: Path, warnings: list, organized_root: Path):
    fieldnames = ["Folder", "Filename", "Full Path", "Reason", "Fingerprint Length"]
    rows = []
    for path_str, reason in warnings:
        p = Path(path_str)
        try:
            folder = str(p.parent.relative_to(organized_root))
        except ValueError:
            folder = str(p.parent)
        m = re.search(r'\((\d+) integers?\)', reason)
        fp_len = int(m.group(1)) if m else ""
        clean_reason = re.sub(r'\s*\(\d+ integers?\)', '', reason).strip()
        rows.append({
            "Folder":             folder,
            "Filename":           p.name,
            "Full Path":          path_str,
            "Reason":             clean_reason,
            "Fingerprint Length": fp_len,
        })
    rows.sort(key=lambda r: (r["Reason"], r["Folder"], r["Filename"]))
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Validate folder ────────────────────────────────────────────────────────
    if not ORGANIZED or not ORGANIZED.exists():
        print(f"ERROR: Organized folder not found: {ORGANIZED}")
        print("       Set 'organized' in music_config.json or use --path.")
        sys.exit(1)

    # ── Header ─────────────────────────────────────────────────────────────────
    build_label = (
        "metadata + fingerprint" if (BUILD_META and BUILD_FP)
        else "metadata only" if BUILD_META
        else "fingerprint only"
    )
    rebuild_label = "FULL REBUILD" if REBUILD else "incremental"

    print(f"\n{'=' * 60}")
    print(f"Music Cache Builder")
    print(f"{'=' * 60}")
    print(f"  Mode      : {build_label}  [{rebuild_label}]")
    print(f"  Folder    : {ORGANIZED}")
    print(f"  Threads   : {MAX_THREADS}")
    if BUILD_META:
        print(f"  Meta cache: {META_CACHE}")
    if BUILD_FP:
        print(f"  FP cache  : {FP_CACHE}")
        print(f"  fpcalc    : {FPCALC_PATH}")
    print(f"{'=' * 60}\n")

    # ── Metadata cache ─────────────────────────────────────────────────────────
    if BUILD_META:
        print("── Metadata Cache ──────────────────────────────────────────\n")

        if REBUILD and META_CACHE.exists():
            META_CACHE.unlink()
            print("  Existing metadata cache cleared.\n")

        existing_meta = load_json(META_CACHE) if not REBUILD else {}
        meta_cache, new_meta, cached_meta = build_metadata_cache(ORGANIZED, existing_meta)
        save_json(meta_cache, META_CACHE)

        total_meta = new_meta + cached_meta
        print(f"\n  Files scanned   : {total_meta:,}")
        print(f"  New / updated   : {new_meta:,}")
        print(f"  From cache      : {cached_meta:,}")
        print(f"  Cache saved to  : {META_CACHE}")

        if META_CACHE.exists():
            print(f"  Cache file size : {fmt_size(META_CACHE.stat().st_size)}")
        print()

    # ── Fingerprint cache ──────────────────────────────────────────────────────
    if BUILD_FP:
        print("── Fingerprint Cache ───────────────────────────────────────\n")

        if not check_fpcalc(FPCALC_PATH):
            print(f"  ERROR: fpcalc not found at '{FPCALC_PATH}'.")
            print(f"  Download from: https://acoustid.org/chromaprint")
            print(f"  Then set 'acoustid.fpcalc_path' in music_config.json.\n")
            if not BUILD_META:
                sys.exit(1)
            print("  Skipping fingerprint cache.\n")
        else:
            if REBUILD and FP_CACHE.exists():
                FP_CACHE.unlink()
                print("  Existing fingerprint cache cleared.\n")

            existing_fp = load_json(FP_CACHE) if not REBUILD else {}
            fp_cache, new_fp, cached_fp, warnings = build_fingerprint_cache(
                ORGANIZED, existing_fp, FPCALC_PATH
            )
            save_json(fp_cache, FP_CACHE)

            total_fp = new_fp + cached_fp
            valid_fp = sum(1 for v in fp_cache.values() if v and is_valid_fingerprint(v))

            print(f"\n  Files processed : {total_fp:,}")
            print(f"  New / updated   : {new_fp:,}")
            print(f"  From cache      : {cached_fp:,}")
            print(f"  Valid           : {valid_fp:,}")
            print(f"  Warnings        : {len(warnings):,}")
            print(f"  Cache saved to  : {FP_CACHE}")

            if FP_CACHE.exists():
                print(f"  Cache file size : {fmt_size(FP_CACHE.stat().st_size)}")

            # ── Print and save warnings ────────────────────────────────────────
            if warnings:
                print(f"\n  WARNING: {len(warnings)} file(s) flagged:\n")
                for path_str, reason in warnings:
                    print(f"    ! {Path(path_str).name}")
                    print(f"      {reason}")
                    print(f"      {path_str}")

                if REPORTS_DIR:
                    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
                    warn_csv = REPORTS_DIR / f"fp_warnings_{timestamp}.csv"
                else:
                    warn_csv = Path(f"fp_warnings_{timestamp}.csv")

                write_warnings_csv(warn_csv, warnings, ORGANIZED)
                print(f"\n  Warnings saved to: {warn_csv}")
            else:
                print(f"\n  No fingerprint warnings — all files processed cleanly.")

            print()

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"{'=' * 60}")
    print(f"Done  [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    if BUILD_META:
        print(f"  Metadata cache : {META_CACHE}")
    if BUILD_FP:
        print(f"  FP cache       : {FP_CACHE}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
