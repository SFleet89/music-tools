"""
Music Cache Builder  v3.3
==========================
Pre-builds the cache files used by find_music_duplicates.py so that duplicate
scans start fast and the fingerprint pass runs near-instantly.

Two caches can be built, both stored in the shared music_cache.db (SQLite):

  Metadata cache  (metadata_cache table)
      Stores filename, tags, bitrate, and duration for every file in your
      organized library. find_music_duplicates.py uses this to skip re-reading
      metadata on files that haven't changed since the last scan.

  Fingerprint cache  (fp_cache table)
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
    python build_fp_cache.py --fp-only --recheck  # re-fingerprint previously failed files only
"""

import sys
import os
import json
import csv
import re
import hashlib
import shutil
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import (
    SUPPORTED_EXTENSIONS,
    pick_folder,
    DB_PATH,
    open_db,
    init_db,
    upsert_metadata_rows,
    migrate_json_to_db,
    interactive_options,
    load_config,
)

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
FP_MIN_LENGTH          = 50      # fingerprints shorter than this are flagged as invalid
TOO_SMALL_DURATION_SEC = 30.0    # files shorter than this (seconds) → classified as too_small
TOO_SMALL_SIZE_BYTES   = 500_000 # fallback if duration unreadable: files smaller than this → too_small
FP_SAMPLE_SECONDS      = 60      # seconds of audio fpcalc analyses per file (fpcalc default = 120)
                                 # 60 s is sufficient for reliable Chromaprint matching and halves
                                 # per-file processing time with no meaningful accuracy loss.
FP_WORKERS             = 4       # parallel fpcalc processes — tuned for i5-12450H (4 P-cores).
                                 # fpcalc is an external subprocess so Python's GIL is irrelevant;
                                 # each worker runs on its own core.


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

def get_config_path() -> str:
    for i, arg in enumerate(sys.argv):
        if arg == "--config" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    # music_config.json lives at the project root (one level up)
    return str(Path(__file__).parent.parent / "music_config.json")





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
            json.dump(data, f, separators=(",", ":"))
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
    """
    Read all tags and audio info from a music file.
    Returns a flat dict ready to insert directly into metadata_cache.
    """
    stat = path.stat()
    row = {
        "path_str":    str(path),
        "mtime":       stat.st_mtime,
        "size":        stat.st_size,
        "filename":    path.name.lower(),
        "file_format": path.suffix.lower().lstrip("."),
        "title":       None,
        "artist":      None,
        "album_artist":None,
        "album":       None,
        "year":        None,
        "track_number":None,
        "disc_number": None,
        "bitrate":     None,
        "sample_rate": None,
        "bit_depth":   None,
        "duration":    None,
        "mb_track_id": None,
        "mb_album_id": None,
        "acoustid_id": None,
    }
    try:
        audio = MutagenFile(path)
        if audio is not None:
            easy = MutagenFile(path, easy=True)
            if easy:
                def first(tag):
                    val = easy.get(tag)
                    return val[0].strip().lower() if val else None
                row["title"]        = first("title")
                row["artist"]       = first("artist")
                row["album_artist"] = first("albumartist")
                row["album"]        = first("album")
                row["year"]         = first("date") or first("year")
                row["track_number"] = first("tracknumber")
                row["disc_number"]  = first("discnumber")
                row["mb_track_id"]  = first("musicbrainz_trackid")
                row["mb_album_id"]  = first("musicbrainz_albumid")
                row["acoustid_id"]  = first("acoustid_id")
            if hasattr(audio, "info"):
                info = audio.info
                if hasattr(info, "bitrate"):
                    row["bitrate"]    = info.bitrate
                if hasattr(info, "length"):
                    row["duration"]   = info.length
                if hasattr(info, "sample_rate"):
                    row["sample_rate"] = info.sample_rate
                if hasattr(info, "bits_per_sample"):
                    row["bit_depth"]  = info.bits_per_sample
    except Exception:
        pass
    return row


def build_metadata_cache(folder: Path, conn) -> tuple[int, int]:
    """
    Scan folder and build/update the metadata_cache table.

    Strategy:
    - Load existing (path_str → (mtime, size)) from DB at the start.
    - Worker threads check against that snapshot — no DB calls in threads.
    - Collect new/updated rows, then bulk-upsert once at the end.

    Returns (new_count, cached_count).
    """
    # Snapshot of what's already in the DB (path → (mtime, size))
    existing = {
        row["path_str"]: (row["mtime"], row["size"])
        for row in conn.execute("SELECT path_str, mtime, size FROM metadata_cache")
    }

    all_paths = [
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    new_rows     = []
    new_count    = 0
    cached_count = 0
    _lock        = threading.Lock()
    pbar         = make_pbar(len(all_paths), "Scanning metadata")

    def process(path):
        path_str = str(path)
        try:
            stat = path.stat()
        except Exception:
            return None, False
        cached = existing.get(path_str)
        if cached and abs(cached[0] - stat.st_mtime) < 0.01 and cached[1] == stat.st_size:
            return None, False   # still valid — no rescan needed
        return get_file_metadata(path), True

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = {executor.submit(process, p): p for p in all_paths}
        for future in as_completed(futures):
            try:
                row, is_new = future.result()
                if is_new and row:
                    with _lock:
                        new_rows.append(row)
                    new_count += 1
                else:
                    cached_count += 1
            except Exception:
                pass
            pbar.update(1)

    pbar.close()

    if new_rows:
        upsert_metadata_rows(conn, new_rows)

    return new_count, cached_count


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


def get_fingerprint(path: Path, fpcalc_path: str) -> tuple:
    """
    Run fpcalc and return (fingerprint_string, duration_seconds, stderr_text).
    fpcalc always outputs both fp and duration; we capture both.
    Returns (None, None, stderr_text) on failure.
    Decodes output as UTF-8 with errors='replace' so a bad character in fpcalc's
    stderr never silently swallows the result via a UnicodeDecodeError.
    """
    stderr_text = ""
    try:
        result = subprocess.run(
            [fpcalc_path, "-raw", "-length", str(FP_SAMPLE_SECONDS), str(path)],
            capture_output=True, timeout=90,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr_text = result.stderr.decode("utf-8", errors="replace").strip()
        fp = None
        duration = None
        for line in stdout.splitlines():
            if line.startswith("FINGERPRINT="):
                fp = line.split("=", 1)[1].strip()
            elif line.startswith("DURATION="):
                try:
                    duration = float(line.split("=", 1)[1].strip())
                except ValueError:
                    pass
        return fp, duration, stderr_text
    except Exception as exc:
        return None, None, str(exc)


def is_valid_fingerprint(fp: str) -> bool:
    try:
        return len(fp.split(",")) >= FP_MIN_LENGTH
    except Exception:
        return False


def get_duration(path: Path) -> float | None:
    """Return audio duration in seconds via mutagen, or None if unreadable."""
    try:
        audio = MutagenFile(path)
        if audio and hasattr(audio, "info") and hasattr(audio.info, "length"):
            return audio.info.length
    except Exception:
        pass
    return None


def classify_warning(path_str: str) -> str:
    """
    Classify a fingerprint warning as 'too_small' or 'corrupted'.

    too_small  — file is too short to produce a meaningful fingerprint
                 (duration < TOO_SMALL_DURATION_SEC, or tiny file if duration unreadable)
    corrupted  — file appears normal-sized but fingerprinting failed or returned
                 a suspiciously short result, suggesting audio data is damaged
    """
    p = Path(path_str)
    try:
        duration = get_duration(p)
        if duration is not None:
            return "too_small" if duration < TOO_SMALL_DURATION_SEC else "corrupted"
        # Duration unreadable — fall back to file size
        size = p.stat().st_size
        return "too_small" if size < TOO_SMALL_SIZE_BYTES else "corrupted"
    except Exception:
        return "corrupted"


def build_fingerprint_cache(
    folder: Path,
    conn,
    fpcalc_path: str,
    recheck: bool = False,
    use_db_index: bool = False,
) -> tuple[int, int, list]:
    """
    Fingerprint all files in folder, updating the fp_cache table.

    Cached entries (mtime unchanged) are re-used without re-running fpcalc.
    New/changed files are fingerprinted in parallel using FP_WORKERS processes.
    Results are bulk-inserted at the end of the run.

    use_db_index=True: build the file list from metadata_cache (fast DB query)
    instead of rglob. Ideal for --fp-only runs where metadata is already current.
    Falls back to rglob automatically if metadata_cache is empty.

    Returns (new_count, cached_count, warnings).
    warnings = list of (path_str, reason) for invalid/failed fingerprints.
    """
    # --recheck fast path: query the DB directly for failures, no directory scan needed.
    # Normal path: rglob the folder and split into cached vs. to-fingerprint.
    warnings     = []
    cached_count = 0

    if recheck:
        failed_rows = list(conn.execute(
            "SELECT path_str, mtime FROM fp_cache WHERE fingerprint = ''"
        ))
        to_fingerprint = []
        for row in failed_rows:
            p = Path(row["path_str"])
            if p.exists():
                try:
                    to_fingerprint.append((p, row["path_str"], p.stat().st_mtime))
                except Exception:
                    pass
        total_for_pbar = len(to_fingerprint)
        print(f"  Found {total_for_pbar} previously failed file(s) to retry.\n")
    else:
        # Load existing entries: path → (mtime, fingerprint)
        existing = {
            row["path_str"]: (row["mtime"], row["fingerprint"])
            for row in conn.execute("SELECT path_str, mtime, fingerprint FROM fp_cache")
        }

        # Build the file list — from metadata_cache (fast) or rglob (thorough).
        # Fall back to rglob if metadata_cache is empty.
        if use_db_index:
            meta_count = conn.execute(
                "SELECT COUNT(*) FROM metadata_cache"
            ).fetchone()[0]
            if meta_count == 0:
                print("  NOTE: metadata_cache is empty — falling back to directory scan.")
                use_db_index = False

        if use_db_index:
            rows = conn.execute("SELECT path_str FROM metadata_cache").fetchall()
            all_paths = [
                Path(r["path_str"]) for r in rows
                if r["path_str"].lower().endswith(tuple(SUPPORTED_EXTENSIONS))
            ]
            print(f"  Using metadata index: {len(all_paths):,} files\n")
        else:
            print("  Scanning library", end="", flush=True)
            all_paths = []
            for p in folder.rglob("*"):
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                    all_paths.append(p)
                    if len(all_paths) % 1000 == 0:
                        print(".", end="", flush=True)
            print(f" {len(all_paths):,} files\n")

        # Pre-split: cached (mtime unchanged) vs. needs fingerprinting
        cached_items   = []   # (path_str, fp)
        to_fingerprint = []   # (path, path_str, current_mtime)

        for path in all_paths:
            path_str = str(path)
            try:
                current_mtime = path.stat().st_mtime
            except Exception:
                continue
            if path_str in existing and abs(existing[path_str][0] - current_mtime) < 0.01:
                cached_items.append((path_str, existing[path_str][1]))
            else:
                to_fingerprint.append((path, path_str, current_mtime))

        # Collect warnings from cached entries (no fingerprinting needed)
        cached_count = len(cached_items)
        for path_str, fp in cached_items:
            if fp and not is_valid_fingerprint(fp):
                warnings.append((path_str, f"short fingerprint ({len(fp.split(','))} integers) — file may be corrupted or silent"))
            elif not fp:
                warnings.append((path_str, "fingerprint generation failed (cached)"))

        total_for_pbar = len(all_paths)

    # Parallel fingerprinting for new / changed files
    new_rows  = []
    new_count = 0
    pbar = make_pbar(total_for_pbar, "Fingerprinting files")
    pbar.update(cached_count)   # jump past the already-cached entries

    def _fingerprint_one(args):
        """Worker: runs fpcalc on one file. Called from a thread pool."""
        path, path_str, current_mtime = args
        fp, fp_dur, stderr = get_fingerprint(path, fpcalc_path)
        pbar.update(1)
        return path_str, current_mtime, fp, fp_dur, stderr

    with ThreadPoolExecutor(max_workers=FP_WORKERS) as executor:
        for path_str, current_mtime, fp, fp_dur, stderr in executor.map(
            _fingerprint_one, to_fingerprint
        ):
            new_count += 1
            if fp:
                new_rows.append({
                    "path_str": path_str, "mtime": current_mtime,
                    "fingerprint": fp, "fp_duration": fp_dur,
                })
                if not is_valid_fingerprint(fp):
                    warnings.append((path_str, f"short fingerprint ({len(fp.split(','))} integers) — file may be corrupted or silent"))
            else:
                # Cache the failure so we don't retry every run
                new_rows.append({
                    "path_str": path_str, "mtime": current_mtime,
                    "fingerprint": "", "fp_duration": None,
                })
                reason = "fingerprint generation failed"
                if stderr:
                    stderr_short = stderr[:200].replace("\n", " | ")
                    reason = f"fingerprint generation failed — fpcalc: {stderr_short}"
                warnings.append((path_str, reason))

    pbar.close()

    if new_rows:
        conn.executemany(
            "INSERT OR REPLACE INTO fp_cache "
            "(path_str, mtime, fingerprint, fp_duration) "
            "VALUES (:path_str, :mtime, :fingerprint, :fp_duration)",
            new_rows,
        )
        conn.commit()

    return new_count, cached_count, warnings


# ══════════════════════════════════════════════════════════════════════════════
#  FP CACHE PRUNING
# ══════════════════════════════════════════════════════════════════════════════

def prune_fp_cache(conn) -> int:
    """
    Delete fp_cache rows for files that no longer exist on disk.
    Stale entries accumulate as files are moved or deleted — pruning
    keeps the database lean without requiring a full rebuild.

    Returns the number of entries removed.
    """
    all_paths = [row["path_str"] for row in conn.execute("SELECT path_str FROM fp_cache")]
    stale = [p for p in all_paths if not Path(p).exists()]
    if stale:
        conn.executemany("DELETE FROM fp_cache WHERE path_str = ?", [(p,) for p in stale])
        conn.commit()
    return len(stale)


# ══════════════════════════════════════════════════════════════════════════════
#  WARNINGS CSV
# ══════════════════════════════════════════════════════════════════════════════

def write_warnings_csv(csv_path: Path, warnings_classified: list, organized_root: Path):
    """warnings_classified: list of (path_str, reason, category) tuples."""
    fieldnames = ["Category", "Folder", "Filename", "Full Path", "Reason", "Fingerprint Length"]
    rows = []
    for path_str, reason, category in warnings_classified:
        p = Path(path_str)
        try:
            folder = str(p.parent.relative_to(organized_root))
        except ValueError:
            folder = str(p.parent)
        m = re.search(r'\((\d+) integers?\)', reason)
        fp_len = int(m.group(1)) if m else ""
        clean_reason = re.sub(r'\s*\(\d+ integers?\)', '', reason).strip()
        rows.append({
            "Category":           category,
            "Folder":             folder,
            "Filename":           p.name,
            "Full Path":          path_str,
            "Reason":             clean_reason,
            "Fingerprint Length": fp_len,
        })
    rows.sort(key=lambda r: (r["Category"], r["Reason"], r["Folder"], r["Filename"]))
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def copy_error_files(
    warnings_classified: list,
    error_dest: Path,
    organized_root: Path,
    apply: bool,
):
    """
    Copy flagged files into error_dest/too_small/ and error_dest/corrupted/,
    preserving relative folder structure.

    Dry run (apply=False): prints a plan, copies nothing.
    Live run (apply=True): creates folders and copies files.
    """
    too_small = [(p, r) for p, r, c in warnings_classified if c == "too_small"]
    corrupted = [(p, r) for p, r, c in warnings_classified if c == "corrupted"]

    dest_small = error_dest / "too_small"
    dest_corrupt = error_dest / "corrupted"

    print(f"\n── Error File Copy {'(DRY RUN)' if not apply else '(LIVE)'}" + " ─" * 10 + "\n")

    if not apply:
        print(f"  Add --apply to actually copy files.\n")

    print(f"  Destination  : {error_dest}")
    print(f"  Too small    : {len(too_small)} file(s) → too_small\\")
    print(f"  Corrupted    : {len(corrupted)} file(s) → corrupted\\")

    if not apply:
        if too_small:
            print(f"\n  Would copy to too_small\\:")
            for path_str, _ in too_small:
                p = Path(path_str)
                try:
                    rel = p.relative_to(organized_root)
                except ValueError:
                    rel = Path(p.name)
                print(f"    {rel}")
        if corrupted:
            print(f"\n  Would copy to corrupted\\:")
            for path_str, _ in corrupted:
                p = Path(path_str)
                try:
                    rel = p.relative_to(organized_root)
                except ValueError:
                    rel = Path(p.name)
                print(f"    {rel}")
        return

    # ── Live copy ──────────────────────────────────────────────────────────────
    copied = 0
    skipped = 0
    errors = []

    for category_list, dest_dir in [(too_small, dest_small), (corrupted, dest_corrupt)]:
        if not category_list:
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        for path_str, _ in category_list:
            p = Path(path_str)
            if not p.exists():
                errors.append(f"Source not found: {path_str}")
                skipped += 1
                continue
            try:
                rel = p.relative_to(organized_root)
            except ValueError:
                rel = Path(p.name)
            dest_file = dest_dir / rel
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            if dest_file.exists():
                skipped += 1
                continue
            shutil.copy2(p, dest_file)
            copied += 1

    print(f"\n  Copied  : {copied} file(s)")
    if skipped:
        print(f"  Skipped : {skipped} (already exist or source missing)")
    if errors:
        print(f"  Errors  :")
        for e in errors:
            print(f"    ! {e}")
    print(f"\n  Review at: {error_dest}")


# ══════════════════════════════════════════════════════════════════════════════
#  GUI-CALLABLE CORE
# ══════════════════════════════════════════════════════════════════════════════

def run_build_fp_cache(
    root,
    build_meta=True,
    build_fp=True,
    rebuild=False,
    recheck=False,
    copy_errors=False,
    error_dest=None,
    apply_errors=False,
    fpcalc_path="fpcalc",
    max_threads=None,
    reports_dir=None,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    GUI-callable entry point for the fingerprint/metadata cache builder.

    Parameters
    ----------
    root : str | Path
        The organized music library folder to scan.
    build_meta : bool
        Build / update the metadata cache (default: True).
    build_fp : bool
        Build / update the fingerprint cache (default: True).
    rebuild : bool
        Wipe the selected cache(s) before rebuilding (default: False).
    recheck : bool
        Re-fingerprint only previously failed files (default: False).
    copy_errors : bool
        Copy corrupted files to error_dest (default: False).
    error_dest : str | Path | None
        Destination folder for corrupted files when copy_errors=True.
    apply_errors : bool
        If True, actually move error files (not dry-run copy).
    fpcalc_path : str
        Path to fpcalc executable (default: "fpcalc" — relies on PATH).
    max_threads : int | None
        Override the thread count for fingerprinting.
    reports_dir : str | Path | None
        Override the reports folder (default: <script_dir>/reports/).
    progress_callback : callable | None
        Called as progress_callback(current, total, filename).
    log_callback : callable | None
        Called as log_callback(message) for each output line.

    Returns
    -------
    dict: new_meta, cached_meta, new_fp, cached_fp, warnings_count,
          report_path (str | None), reports_dir (str).

    Raises
    ------
    ValueError
        If root does not exist or is not a directory.
    """
    root = Path(root)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Folder not found: {root}")

    script_dir  = Path(__file__).parent
    _reports    = Path(reports_dir) if reports_dir else script_dir / "reports"
    _max_t      = max_threads or os.cpu_count() or 4
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")

    build_label   = ("metadata + fingerprint" if (build_meta and build_fp)
                     else "metadata only" if build_meta else "fingerprint only")
    rebuild_label = "FULL REBUILD" if rebuild else "incremental"

    print(f"\n{'=' * 60}")
    print("Music Cache Builder  v3.2")
    print(f"{'=' * 60}")
    print(f"  Mode      : {build_label}  [{rebuild_label}]")
    if recheck:
        print("  Recheck   : re-fingerprinting previously failed files")
    print(f"  Folder    : {root}")
    print(f"  Threads   : {_max_t}")
    print(f"  Database  : {DB_PATH}")
    if build_fp:
        print(f"  fpcalc    : {fpcalc_path}")
        print(f"  FP sample : {FP_SAMPLE_SECONDS} s per file")
        print(f"  FP workers: {FP_WORKERS} parallel processes")
        print("  File list : metadata_cache (DB index)")
    print(f"{'=' * 60}\n")

    conn = open_db()
    init_db(conn)

    if (script_dir / "music_cache.json").exists() or (script_dir / "music_fp_cache.json").exists():
        print("── Migration ───────────────────────────────────────────────\n")
        migrate_json_to_db(conn, script_dir)
        print()

    if rebuild:
        if build_meta:
            conn.execute("DELETE FROM metadata_cache")
            conn.commit()
            print("  Existing metadata cache cleared.\n")
        if build_fp:
            conn.execute("DELETE FROM fp_cache")
            conn.commit()
            print("  Existing fingerprint cache cleared.\n")

    result = {
        "new_meta": 0, "cached_meta": 0,
        "new_fp": 0, "cached_fp": 0,
        "warnings_count": 0,
        "report_path": None,
        "reports_dir": str(_reports),
    }

    if build_meta:
        print("── Metadata Cache ──────────────────────────────────────────\n")
        new_meta, cached_meta = build_metadata_cache(root, conn)
        result["new_meta"]    = new_meta
        result["cached_meta"] = cached_meta
        db_size = fmt_size(DB_PATH.stat().st_size) if DB_PATH.exists() else "—"
        print(f"\n  Files scanned   : {new_meta + cached_meta:,}")
        print(f"  New / updated   : {new_meta:,}")
        print(f"  From cache      : {cached_meta:,}")
        print(f"  Database size   : {db_size}")
        print()

    if build_fp:
        print("── Fingerprint Cache ───────────────────────────────────────\n")
        if not check_fpcalc(fpcalc_path):
            print(f"  ERROR: fpcalc not found at '{fpcalc_path}'.")
            print("  Download from: https://acoustid.org/chromaprint")
            print("  Then set 'acoustid.fpcalc_path' in music_config.json.\n")
            if not build_meta:
                raise ValueError(f"fpcalc not found at: {fpcalc_path}")
            print("  Skipping fingerprint cache.\n")
        else:
            new_fp, cached_fp, warnings = build_fingerprint_cache(
                root, conn, fpcalc_path, recheck=recheck, use_db_index=True
            )
            result["new_fp"]    = new_fp
            result["cached_fp"] = cached_fp

            pruned_count = prune_fp_cache(conn)
            valid_fp = conn.execute(
                "SELECT COUNT(*) FROM fp_cache WHERE fingerprint != ''"
            ).fetchone()[0]

            db_size = fmt_size(DB_PATH.stat().st_size) if DB_PATH.exists() else "—"
            print(f"\n  Files processed : {new_fp + cached_fp:,}")
            print(f"  New / updated   : {new_fp:,}")
            print(f"  From cache      : {cached_fp:,}")
            print(f"  Stale pruned    : {pruned_count:,}")
            print(f"  Valid           : {valid_fp:,}")
            print(f"  Warnings        : {len(warnings):,}")
            print(f"  Database size   : {db_size}")

            warnings_classified = [
                (path_str, reason, classify_warning(path_str))
                for path_str, reason in warnings
                if classify_warning(path_str) != "too_small"
            ]
            result["warnings_count"] = len(warnings_classified)

            if warnings_classified:
                print(f"\n  WARNING: {len(warnings_classified)} file(s) flagged as corrupted:")
                print("    (too-small files are silently skipped)\n")
                for path_str, reason, category in warnings_classified:
                    print(f"    [corrupted]  {Path(path_str).name}")
                    print(f"               {reason}")
                    print(f"               {path_str}")

                _reports.mkdir(parents=True, exist_ok=True)
                csv_path = _reports / f"fp_warnings_{timestamp}.csv"
                write_warnings_csv(csv_path, warnings_classified, root)
                result["report_path"] = str(csv_path)
                print(f"\n  Warnings CSV    : {csv_path}")

                if copy_errors and error_dest:
                    copy_error_files(
                        warnings_classified, root, Path(error_dest), apply_errors
                    )

    conn.close()
    print(f"\n{'=' * 60}")
    print("Done.")
    print(f"{'=' * 60}\n")
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    interactive_options([
        ("--fp-only", "Fingerprints only \u2014 skip metadata, just rebuild fingerprint cache"),
        ("--recheck", "Re-check \u2014 retry only previously failed fingerprint files"),
    ])

    REBUILD      = "--rebuild"       in sys.argv
    META_ONLY    = "--metadata-only" in sys.argv
    FP_ONLY      = "--fp-only"       in sys.argv
    BUILD_META   = not FP_ONLY
    BUILD_FP     = not META_ONLY
    COPY_ERRORS  = "--copy-errors"   in sys.argv
    APPLY        = "--apply"         in sys.argv
    RECHECK      = "--recheck"       in sys.argv

    _error_dest_arg = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                            if a == "--error-dest" and i+1 < len(sys.argv)), None)
    _path_arg    = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                         if a == "--path" and i+1 < len(sys.argv)), None)
    _threads_arg = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                         if a == "--threads" and i+1 < len(sys.argv)), None)

    try:
        cfg = load_config(get_config_path())
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    _folders     = cfg.get("folders", {})
    _perf        = cfg.get("performance", {})
    _acoustid    = cfg.get("acoustid", {})
    _output      = cfg.get("output", {})

    _org_str = (_path_arg or _folders.get("organized", "") or "").strip()
    organized = Path(_org_str) if _org_str else None

    _log_folder = _output.get("log_folder", "").strip()
    reports_dir = Path(_log_folder) if _log_folder else Path(__file__).parent / "reports"

    fpcalc_path = _acoustid.get("fpcalc_path", "fpcalc")

    _max_t = (int(_threads_arg) if _threads_arg and _threads_arg.isdigit()
              else int(_perf.get("max_threads", 0)))
    max_threads = _max_t if _max_t > 0 else None

    if not organized or not organized.exists():
        if _path_arg:
            print(f"ERROR: Folder not found: {organized}")
            sys.exit(1)
        chosen = pick_folder()
        if not chosen:
            print("No folder selected. Exiting.")
            sys.exit(0)
        if not chosen.exists():
            print(f"ERROR: Selected folder does not exist: {chosen}")
            sys.exit(1)
        organized = chosen

    try:
        run_build_fp_cache(
            root=organized,
            build_meta=BUILD_META,
            build_fp=BUILD_FP,
            rebuild=REBUILD,
            recheck=RECHECK,
            copy_errors=COPY_ERRORS,
            error_dest=_error_dest_arg,
            apply_errors=APPLY,
            fpcalc_path=fpcalc_path,
            max_threads=max_threads,
            reports_dir=reports_dir,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
