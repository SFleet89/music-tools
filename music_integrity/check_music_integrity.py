"""
Music Integrity Checker  v1.6
==============================
Scans your music library for file integrity issues and repairs VBR headers
in MP3 files — equivalent to foobar2000's "Verify Integrity" and
"Fix VBR Header" functions.

Two independent checks are available:

  INTEGRITY   (all formats, slow — runs by default)
              Full decode pass via ffmpeg. Catches corrupt frames, truncated
              files, and audio stream errors. Results are informational only —
              corrupt audio cannot be automatically repaired.
              Use --quick to skip this check.

  VBR HEADER  (MP3 only, fast — always runs)
              Detects missing or incorrect Xing/LAME/VBRI headers. These
              cause players to mis-report track duration and seek incorrectly
              in variable-bitrate files. mp3val repairs them in --apply mode.

Report statuses:
  ok              No issues found
  vbr_needs_fix   VBR header issue detected (dry run)
  vbr_fixed       VBR header successfully repaired (apply mode)
  vbr_unfixable   mp3val found errors it cannot repair
  vbr_skipped     mp3val not found — VBR check not performed
  decode_ok        ffmpeg found no decode errors
  decode_errors    ffmpeg reported errors (informational, file may be corrupt)
  decode_skipped   ffmpeg not found or --quick used
  cached           result loaded from SQLite integrity cache (file unchanged)
  error           Unexpected exception during processing

Required tools — place next to this script OR add to system PATH:
  mp3val    http://mp3val.sourceforge.net/download.html
  ffmpeg    https://ffmpeg.org/download.html  (needed for integrity check)

Python requirements:
  pip install tqdm   (optional — enables progress bars)

Usage:
  python check_music_integrity.py                       # folder picker, VBR + full decode (default)
  python check_music_integrity.py --quick               # VBR check only, skip full decode
  python check_music_integrity.py --apply               # fix VBR headers (+ full decode)
  python check_music_integrity.py --apply --quick       # fix VBR headers only, no decode
  python check_music_integrity.py --from-csv            # apply fixes from dry-run CSV (file picker)
  python check_music_integrity.py "C:\\path\\Music"     # skip folder picker
  python check_music_integrity.py --mp3-only            # skip FLAC/AAC/M4A
  python check_music_integrity.py --rebuild-cache       # ignore cache, re-decode everything

Changes in v1.6:
  - PW-01: Extracted run_check_music_integrity() as GUI-callable core.
    Handles both standard scan mode and --from-csv mode. Parameters:
    root, apply, run_integrity, mp3_only, rebuild_cache, from_csv,
    reports_dir, progress_callback, log_callback.
    Raises ValueError for bad paths. Returns dict: rows, counts,
    report_path, reports_dir.
  - Moved module-level _args, APPLY_MODE, RUN_INTEGRITY, MP3_ONLY,
    FROM_CSV, REBUILD_CACHE, FOLDER_ARG, SCAN_EXTENSIONS, and
    interactive_options([]) inside main() — no module-level side effects.
  - check_tools() now takes run_integrity param (removed global dep).
  - find_audio_files() now takes mp3_only param; extensions computed
    internally (removed SCAN_EXTENSIONS / MP3_ONLY global deps).
  - run_scan() now takes rebuild_cache param (removed REBUILD_CACHE dep).
  - _run_sequential(), _run_parallel(), apply_from_csv() each accept
    optional progress_callback(current, total, filename).

Changes in v1.1:
  - Added --from-csv flag: applies VBR fixes from a dry-run CSV without
    rescanning the library. A file picker opens to select the CSV.
    Processes rows with vbr_needs_fix status plus any timeout errors
    (which are retried with a longer timeout).
  - Fixed timeout scaling: mp3val timeout now scales with file size
    (approx 1 second per MB, minimum 60s, maximum 600s). Large DJ mix
    files that previously timed out at 30s will now complete correctly.
"""

import os
import sys
import csv
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import (
    SUPPORTED_EXTENSIONS,
    pick_folder,
    write_csv,
    open_db,
    init_db,
    interactive_options,
)

# ── Optional tqdm ──────────────────────────────────────────────────────────────
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

SCRIPT_DIR = Path(__file__).parent

# ── Supported formats ──────────────────────────────────────────────────────────
MP3_ONLY_EXTENSIONS = {".mp3"}

# ── Progress bar helper ────────────────────────────────────────────────────────

def make_pbar(total, desc, unit="file"):
    if TQDM_AVAILABLE:
        return tqdm(total=total, desc=desc, unit=unit, ncols=80, dynamic_ncols=True)
    class _Noop:
        def update(self, n=1): pass
        def close(self):       pass
        def set_postfix_str(self, s): pass
    return _Noop()


# ══════════════════════════════════════════════════════════════════════════════
#  TOOL DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════

def find_tool(name):
    """
    Look for an executable next to this script first, then fall back to PATH.
    Returns the full path string if found, or None.
    """
    # Windows executables
    candidates = [name, name + ".exe"]
    for candidate in candidates:
        local = SCRIPT_DIR / candidate
        if local.exists():
            return str(local)

    # PATH lookup
    import shutil as _shutil
    found = _shutil.which(name)
    return found  # None if not found


def check_tools(run_integrity=True):
    """
    Discover mp3val and ffmpeg. Print status for each.
    Returns (mp3val_path, ffmpeg_path) — either may be None.
    """
    mp3val = find_tool("mp3val")
    ffmpeg = find_tool("ffmpeg")

    print()
    if mp3val:
        print(f"  mp3val   : {mp3val}")
    else:
        print("  mp3val   : NOT FOUND")
        print(f"             Looked in : {SCRIPT_DIR / 'mp3val.exe'}")
        print("             Also tried: system PATH")
        print("             Download  : http://mp3val.sourceforge.net/download.html")
        print(f"             Fix       : place mp3val.exe in {SCRIPT_DIR}")

    if run_integrity:
        if ffmpeg:
            print(f"  ffmpeg   : {ffmpeg}")
        else:
            print("  ffmpeg   : NOT FOUND")
            print(f"             Looked in : {SCRIPT_DIR / 'ffmpeg.exe'}")
            print("             Also tried: system PATH")
            print("             Download  : https://ffmpeg.org/download.html")
            print(f"             Fix       : place ffmpeg.exe in {SCRIPT_DIR}")
    else:
        print("  ffmpeg   : (skipped — use --quick to disable full decode check)")

    print()
    return mp3val, ffmpeg


# ══════════════════════════════════════════════════════════════════════════════
#  VBR CHECK (mp3val)
# ══════════════════════════════════════════════════════════════════════════════

# mp3val output prefixes we care about
_MP3VAL_WARNING = "warning:"
_MP3VAL_ERROR   = "error:"
_MP3VAL_FIXED   = "fixed:"

# Messages that indicate a VBR header issue specifically
_VBR_KEYWORDS = {
    "xing", "vbr", "lame", "vbri",
    "wrong number of frames",
    "tag is not valid",
    "no valid frames",
}


def _has_vbr_keyword(line):
    low = line.lower()
    return any(kw in low for kw in _VBR_KEYWORDS)


def _mp3val_timeout(file_path):
    """
    Calculate a sensible mp3val timeout based on file size.
    mp3val reads the whole file sequentially, so large files take longer.
    Rule: ~1 second per MB, minimum 60s, maximum 600s (10 min).
    A 500MB DJ mix at ~1s/MB = 500s — comfortably within the cap.
    """
    try:
        size_mb = Path(file_path).stat().st_size / (1024 * 1024)
        return max(60, min(int(size_mb), 600))
    except Exception:
        return 60


def run_mp3val(file_path, mp3val_path, fix=False):
    """
    Run mp3val on a single MP3 file.

    fix=False  → check only (dry run), returns what would be fixed
    fix=True   → repair in place, returns what was done

    Returns dict:
      vbr_status   : ok | needs_fix | fixed | unfixable | error
      vbr_details  : human-readable summary of findings
    """
    cmd = [mp3val_path]
    if fix:
        cmd.append("-f")
    cmd.append(str(file_path))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_mp3val_timeout(file_path),
        )
        output = (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return {"vbr_status": "error", "vbr_details": "mp3val timed out"}
    except Exception as e:
        return {"vbr_status": "error", "vbr_details": f"mp3val failed: {e}"}

    lines     = output.splitlines()
    warnings  = [l for l in lines if l.lower().startswith(_MP3VAL_WARNING)]
    errors    = [l for l in lines if l.lower().startswith(_MP3VAL_ERROR)]
    fixed     = [l for l in lines if l.lower().startswith(_MP3VAL_FIXED)]

    # Filter to VBR-related findings only
    vbr_warnings = [l for l in warnings if _has_vbr_keyword(l)]
    vbr_errors   = [l for l in errors   if _has_vbr_keyword(l)]
    vbr_fixed    = [l for l in fixed    if _has_vbr_keyword(l)]

    # Hard errors (not VBR-related) — something wrong with the file itself
    hard_errors  = [l for l in errors if not _has_vbr_keyword(l)]

    if fix:
        if vbr_fixed:
            detail = "; ".join(_clean_mp3val_line(l) for l in vbr_fixed)
            return {"vbr_status": "vbr_fixed", "vbr_details": detail}
        if vbr_errors or hard_errors:
            detail = "; ".join(_clean_mp3val_line(l) for l in (vbr_errors + hard_errors))
            return {"vbr_status": "vbr_unfixable", "vbr_details": detail}
        return {"vbr_status": "ok", "vbr_details": ""}
    else:
        # Dry run
        if vbr_warnings:
            detail = "; ".join(_clean_mp3val_line(l) for l in vbr_warnings)
            return {"vbr_status": "vbr_needs_fix", "vbr_details": detail}
        if vbr_errors or hard_errors:
            detail = "; ".join(_clean_mp3val_line(l) for l in (vbr_errors + hard_errors))
            return {"vbr_status": "vbr_unfixable", "vbr_details": detail}
        return {"vbr_status": "ok", "vbr_details": ""}


def _clean_mp3val_line(line):
    """Strip the filename prefix from mp3val output lines for cleaner detail text."""
    # mp3val lines look like: "WARNING: C:\path\file.mp3 (offset 0x..): message"
    # We just want the message part after the path
    parts = line.split(":", 2)
    if len(parts) >= 3:
        # Strip the file path portion (second segment)
        msg = parts[2].strip()
        # Remove offset prefix if present
        if msg.startswith("(offset"):
            msg = msg.split(")", 1)[-1].strip()
        return msg
    return line.strip()


# ══════════════════════════════════════════════════════════════════════════════
#  INTEGRITY CHECK (ffmpeg full decode)
# ══════════════════════════════════════════════════════════════════════════════

# ffmpeg error lines we treat as decode errors vs noise
_FFMPEG_IGNORE = {
    "deprecated",
    "incorrect timestamps",
    "non monotonous",
    "past duration",
    "application provided invalid",  # common benign tag issue
    "id3v1 tag",
    "encoder delay",
}


def run_ffmpeg_integrity(file_path, ffmpeg_path):
    """
    Full decode pass via ffmpeg. Returns dict:
      integrity_status  : decode_ok | decode_errors
      integrity_details : error lines from ffmpeg (truncated to 5)
    """
    cmd = [
        ffmpeg_path,
        "-v", "error",          # show errors only
        "-i", str(file_path),
        "-f", "null",           # discard output
        "-",                    # write to stdout (discarded)
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,        # 2 min max per file
        )
        # ffmpeg writes errors to stderr
        error_lines = [
            l.strip() for l in result.stderr.splitlines()
            if l.strip()
            and not any(ig in l.lower() for ig in _FFMPEG_IGNORE)
        ]
    except subprocess.TimeoutExpired:
        return {
            "integrity_status":  "decode_errors",
            "integrity_details": "ffmpeg timed out (file may be very large or corrupt)",
        }
    except Exception as e:
        return {
            "integrity_status":  "decode_errors",
            "integrity_details": f"ffmpeg failed: {e}",
        }

    if error_lines:
        # Show up to 3 error lines — keep the report readable
        summary = "; ".join(error_lines[:3])
        if len(error_lines) > 3:
            summary += f" (+{len(error_lines) - 3} more)"
        return {"integrity_status": "decode_errors", "integrity_details": summary}

    return {"integrity_status": "decode_ok", "integrity_details": ""}


# ══════════════════════════════════════════════════════════════════════════════
#  INTEGRITY CACHE (SQLite)
# ══════════════════════════════════════════════════════════════════════════════

def load_integrity_snapshot(conn):
    """
    Load all rows from integrity_cache into a dict keyed by path_str.
    Each value is (mtime, size, status, detail).
    Returns an empty dict if the table doesn't exist yet.
    """
    try:
        rows = conn.execute(
            "SELECT path_str, mtime, size, integrity_status, integrity_detail "
            "FROM integrity_cache"
        ).fetchall()
        return {r[0]: (r[1], r[2], r[3], r[4]) for r in rows}
    except Exception:
        return {}


def check_integrity_cache(file_path, snapshot):
    """
    Return a cached integrity result dict if the file is unchanged since last
    check, or None if the file must be re-checked.
    """
    if not snapshot:
        return None
    key = str(file_path)
    entry = snapshot.get(key)
    if entry is None:
        return None
    cached_mtime, cached_size, status, detail = entry
    try:
        stat = file_path.stat()
        if abs(stat.st_mtime - cached_mtime) < 1.0 and stat.st_size == cached_size:
            return {"integrity_status": status, "integrity_details": detail or ""}
    except Exception:
        pass
    return None


def save_integrity_results(conn, rows):
    """
    Bulk-upsert integrity results for files that were freshly checked
    (i.e. rows where from_cache is False).
    """
    checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    to_save = []
    for row in rows:
        if row.get("from_cache"):
            continue
        fp = row["file_path"]
        try:
            stat = Path(fp).stat()
            mtime, size = stat.st_mtime, stat.st_size
        except Exception:
            continue
        to_save.append((
            fp,
            mtime,
            size,
            row["integrity_status"],
            row.get("integrity_details", ""),
            checked_at,
        ))
    if to_save:
        conn.executemany(
            "INSERT OR REPLACE INTO integrity_cache "
            "(path_str, mtime, size, integrity_status, integrity_detail, checked_at) "
            "VALUES (?,?,?,?,?,?)",
            to_save,
        )
        conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  FILE PROCESSING
# ══════════════════════════════════════════════════════════════════════════════

def process_file(file_path, mp3val_path, ffmpeg_path, apply_mode, run_integrity,
                 integrity_snapshot=None):
    """
    Run all applicable checks on a single file. Returns a report row dict,
    or None if this file has nothing to check (non-MP3 without --integrity).

    integrity_snapshot — dict from load_integrity_snapshot(). When provided,
    the ffmpeg decode is skipped for files whose mtime+size match the cache.
    """
    ext    = file_path.suffix.lower()
    is_mp3 = ext == ".mp3"

    # Skip non-MP3 files entirely when integrity check is not enabled —
    # there is nothing useful to report for them in VBR-only mode.
    if not is_mp3 and not run_integrity:
        return None

    row = {
        "file_path":         str(file_path),
        "format":            ext.lstrip(".").upper(),
        "vbr_status":        "n/a",
        "vbr_details":       "",
        "integrity_status":  "not_checked",
        "integrity_details": "",
        "overall_status":    "ok",
        "from_cache":        False,
    }

    try:
        # ── VBR check (MP3 only) ──
        if is_mp3:
            if mp3val_path:
                vbr = run_mp3val(file_path, mp3val_path, fix=apply_mode)
                row["vbr_status"]  = vbr["vbr_status"]
                row["vbr_details"] = vbr["vbr_details"]
            else:
                row["vbr_status"] = "vbr_skipped"

        # ── Integrity check (all formats, if requested) ──
        if run_integrity and ffmpeg_path:
            cached = check_integrity_cache(file_path, integrity_snapshot)
            if cached:
                row["integrity_status"]  = cached["integrity_status"]
                row["integrity_details"] = cached["integrity_details"]
                row["from_cache"]        = True
            else:
                integrity = run_ffmpeg_integrity(file_path, ffmpeg_path)
                row["integrity_status"]  = integrity["integrity_status"]
                row["integrity_details"] = integrity["integrity_details"]
        elif run_integrity and not ffmpeg_path:
            row["integrity_status"] = "decode_skipped"

        # ── Roll up overall status ──
        row["overall_status"] = _overall_status(row)

    except Exception as e:
        row["vbr_status"]       = "error"
        row["integrity_status"] = "error"
        row["overall_status"]   = "error"
        row["vbr_details"]      = f"Exception: {e}"

    return row


def _overall_status(row):
    vbr  = row["vbr_status"]
    intg = row["integrity_status"]

    if vbr in ("error",) or intg in ("error",):
        return "error"
    if vbr == "vbr_unfixable":
        return "vbr_unfixable"
    if intg == "decode_errors":
        return "decode_errors"
    if vbr == "vbr_fixed":
        return "vbr_fixed"
    if vbr == "vbr_needs_fix":
        return "vbr_needs_fix"
    return "ok"


# ══════════════════════════════════════════════════════════════════════════════
#  SCAN
# ══════════════════════════════════════════════════════════════════════════════

def find_audio_files(root, run_integrity, mp3_only=False):
    """
    Return all supported audio files. If integrity check is disabled,
    only return MP3s — there's nothing to check on other formats.
    mp3_only=True forces MP3-only regardless of run_integrity.
    """
    if mp3_only or not run_integrity:
        extensions = MP3_ONLY_EXTENSIONS
    else:
        extensions = SUPPORTED_EXTENSIONS
    return sorted(
        p for p in Path(root).rglob("*")
        if p.is_file() and p.suffix.lower() in extensions
    )


def run_scan(root, mp3val_path, ffmpeg_path, apply_mode, run_integrity,
             rebuild_cache=False, mp3_only=False, progress_callback=None):
    """
    Scan all audio files under root. Uses threading for the integrity check
    (slow ffmpeg decode) but processes VBR checks sequentially to avoid
    mp3val file-locking issues in apply mode.

    When run_integrity is True, loads the integrity_cache from SQLite so
    unchanged files are not re-decoded. New results are saved back to the
    cache after the scan.

    progress_callback: callable(current, total, filename) or None.
    """
    files = find_audio_files(root, run_integrity, mp3_only=mp3_only)
    total = len(files)

    if total == 0:
        print(f"  No audio files found in: {root}")
        return []

    # ── Load integrity cache ───────────────────────────────────────────────────
    integrity_snapshot = {}
    conn = None
    if run_integrity and not rebuild_cache:
        try:
            conn = open_db()
            init_db(conn)
            integrity_snapshot = load_integrity_snapshot(conn)
        except Exception as e:
            print(f"  WARNING: Could not load integrity cache: {e}")
            conn = None
    elif run_integrity and rebuild_cache:
        try:
            conn = open_db()
            init_db(conn)
        except Exception as e:
            print(f"  WARNING: Could not open integrity cache: {e}")
            conn = None

    cache_hits = sum(
        1 for f in files
        if check_integrity_cache(f, integrity_snapshot) is not None
    ) if integrity_snapshot else 0

    scope = "MP3, FLAC, AAC, M4A" if run_integrity else "MP3 only"
    print(f"  Found {total:,} file(s) to process ({scope}).")
    if run_integrity:
        if cache_hits:
            print(f"  Integrity cache  : {cache_hits:,} file(s) unchanged (will skip decode).")
            print(f"                     {total - cache_hits:,} file(s) need checking.")
        else:
            print(f"  Integrity cache  : not used (first run or --rebuild-cache).")
        print()

    if apply_mode:
        _print_apply_warning()

    if run_integrity and ffmpeg_path and not apply_mode:
        rows = _run_parallel(files, mp3val_path, ffmpeg_path, apply_mode,
                             run_integrity, integrity_snapshot,
                             progress_callback=progress_callback)
    else:
        rows = _run_sequential(files, mp3val_path, ffmpeg_path, apply_mode,
                               run_integrity, integrity_snapshot,
                               progress_callback=progress_callback)

    # ── Save new integrity results to cache ───────────────────────────────────
    if run_integrity and conn:
        try:
            save_integrity_results(conn, rows)
        except Exception as e:
            print(f"  WARNING: Could not save integrity cache: {e}")
        finally:
            conn.close()

    return rows


def _run_sequential(files, mp3val_path, ffmpeg_path, apply_mode, run_integrity,
                    integrity_snapshot=None, progress_callback=None):
    rows  = []
    total = len(files)
    pbar  = make_pbar(total, "Checking")

    for i, f in enumerate(files, 1):
        if progress_callback:
            progress_callback(i, total, f.name)
        row = process_file(f, mp3val_path, ffmpeg_path, apply_mode,
                           run_integrity, integrity_snapshot)
        if row is not None:
            rows.append(row)
            _print_finding(row)
        pbar.update(1)

    pbar.close()
    return rows


def _run_parallel(files, mp3val_path, ffmpeg_path, apply_mode, run_integrity,
                  integrity_snapshot=None, progress_callback=None):
    """Parallel scan for read-only integrity checks."""
    max_workers = min(os.cpu_count() or 4, 8)
    total       = len(files)
    pbar        = make_pbar(total, "Checking")
    rows        = []
    lock        = threading.Lock()
    done_count  = [0]   # mutable counter shared across threads

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(
                process_file, f, mp3val_path, ffmpeg_path, apply_mode,
                run_integrity, integrity_snapshot
            ): i
            for i, f in enumerate(files)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                row = future.result()
            except Exception as e:
                row = {
                    "file_path": str(files[idx]),
                    "format":    files[idx].suffix.lstrip(".").upper(),
                    "vbr_status": "error", "vbr_details": str(e),
                    "integrity_status": "error", "integrity_details": "",
                    "overall_status": "error",
                    "from_cache": False,
                }
            if row is not None:
                with lock:
                    done_count[0] += 1
                    if progress_callback:
                        progress_callback(done_count[0], total,
                                          Path(files[idx]).name)
                    rows.append(row)
                    _print_finding(row)
            pbar.update(1)

    pbar.close()
    return rows


def _print_finding(row):
    """Print a single-line summary for any non-ok result."""
    status = row["overall_status"]
    if status == "ok":
        return

    label = {
        "vbr_needs_fix":  "[VBR]     ",
        "vbr_fixed":      "[FIXED]   ",
        "vbr_unfixable":  "[VBR ERR] ",
        "decode_errors":  "[CORRUPT] ",
        "error":          "[ERROR]   ",
    }.get(status, "[?]       ")

    name   = Path(row["file_path"]).name
    detail = row["vbr_details"] or row["integrity_details"] or ""
    if detail:
        print(f"  {label} {name}")
        print(f"             {detail}")
    else:
        print(f"  {label} {name}")


def _print_apply_warning():
    print("  !! APPLY MODE: VBR headers will be repaired in place.")
    print("     Originals are not backed up — ensure you have a backup.")
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  CSV REPORT
# ══════════════════════════════════════════════════════════════════════════════

FIELDNAMES = [
    "file_path",
    "format",
    "overall_status",
    "vbr_status",
    "vbr_details",
    "integrity_status",
    "integrity_details",
]


def print_summary(rows, apply_mode, run_integrity, output_path):
    counts = {}
    for r in rows:
        counts[r["overall_status"]] = counts.get(r["overall_status"], 0) + 1

    cache_hits   = sum(1 for r in rows if r.get("from_cache"))
    freshly_checked = sum(1 for r in rows if run_integrity and not r.get("from_cache")
                          and r.get("integrity_status") not in ("not_checked", "decode_skipped"))

    total = len(rows)
    print()
    print("=" * 60)
    print(f"  SUMMARY  ({'APPLY' if apply_mode else 'DRY RUN'})")
    print("=" * 60)
    print(f"  Total files           : {total:,}")
    print(f"  No issues             : {counts.get('ok', 0):,}")
    if apply_mode:
        print(f"  VBR headers fixed     : {counts.get('vbr_fixed', 0):,}")
    else:
        print(f"  VBR headers need fix  : {counts.get('vbr_needs_fix', 0):,}")
    print(f"  VBR unfixable errors  : {counts.get('vbr_unfixable', 0):,}")
    if run_integrity:
        print(f"  Decode errors found   : {counts.get('decode_errors', 0):,}")
        print(f"  From integrity cache  : {cache_hits:,}")
        print(f"  Freshly decoded       : {freshly_checked:,}")
    print(f"  Processing errors     : {counts.get('error', 0):,}")
    print()
    print(f"  Report saved to:")
    print(f"  {output_path}")
    print("=" * 60)

    if not apply_mode and counts.get("vbr_needs_fix", 0) > 0:
        print()
        print(f"  To fix VBR headers, run with --apply:")
        print(f"  python check_music_integrity.py --apply")

    if counts.get("decode_errors", 0) > 0:
        print()
        print(f"  NOTE: {counts['decode_errors']} file(s) have decode errors.")
        print(f"        These cannot be auto-repaired. Open the CSV report,")
        print(f"        filter by 'decode_errors', and inspect those files manually.")


def pick_csv_file():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askopenfilename(
            title="Select dry-run integrity CSV report to apply",
            initialdir=str(SCRIPT_DIR / "reports"),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        root.destroy()
        return chosen or None
    except Exception as e:
        print(f"ERROR: Could not open file picker: {e}")
        return None


def apply_from_csv(csv_path, mp3val_path, progress_callback=None):
    """
    Apply VBR fixes from a dry-run CSV report without rescanning.

    Processes two categories of rows:
      vbr_needs_fix  — detected during dry run, ready to fix
      error          — these were likely timeouts; retried with scaled timeout

    For each file:
      1. Verifies it still exists
      2. Runs mp3val -f to repair in place
      3. Reports the result

    Returns a list of result row dicts for the output report.
    """
    # Load fixable rows from CSV
    fixable = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            status = row.get("overall_status", "").strip()
            if status in ("vbr_needs_fix", "error"):
                fixable.append(row)

    if not fixable:
        print("  No fixable rows found in the CSV.")
        print("  (Looking for rows with status: vbr_needs_fix or error)")
        return []

    needs_fix = [r for r in fixable if r.get("overall_status") == "vbr_needs_fix"]
    retries   = [r for r in fixable if r.get("overall_status") == "error"]

    print()
    print(f"  {len(needs_fix)} VBR header(s) to fix.")
    if retries:
        print(f"  {len(retries)} timeout error(s) to retry with extended timeout.")
    print()

    results  = []
    fixed    = 0
    unfixable = 0
    skipped  = 0
    errors   = 0

    total = len(fixable)
    pbar  = make_pbar(total, "Fixing")

    for done_i, csv_row in enumerate(fixable, 1):
        if progress_callback:
            fp_name = Path(csv_row.get("file_path", "")).name
            progress_callback(done_i, total, fp_name)
        file_path   = Path(csv_row.get("file_path", "").strip())
        was_timeout = csv_row.get("overall_status") == "error"

        # File must still exist
        if not file_path.exists():
            print(f"  [MISSING]  {file_path.name}")
            results.append({
                "file_path":         str(file_path),
                "format":            file_path.suffix.lstrip(".").upper(),
                "overall_status":    "skipped",
                "vbr_status":        "skipped",
                "vbr_details":       "File no longer exists",
                "integrity_status":  "not_checked",
                "integrity_details": "",
            })
            skipped += 1
            pbar.update(1)
            continue

        try:
            vbr = run_mp3val(file_path, mp3val_path, fix=True)

            row = {
                "file_path":         str(file_path),
                "format":            file_path.suffix.lstrip(".").upper(),
                "overall_status":    vbr["vbr_status"],
                "vbr_status":        vbr["vbr_status"],
                "vbr_details":       vbr["vbr_details"],
                "integrity_status":  "not_checked",
                "integrity_details": "",
            }
            results.append(row)
            _print_finding(row)

            if vbr["vbr_status"] == "vbr_fixed":
                fixed += 1
            elif vbr["vbr_status"] == "vbr_unfixable":
                unfixable += 1
            elif vbr["vbr_status"] == "ok" and was_timeout:
                # Retry succeeded — file had no VBR issue after all
                fixed += 1
            elif vbr["vbr_status"] == "error":
                errors += 1

        except Exception as e:
            print(f"  [ERROR]    {file_path.name} -- {e}")
            results.append({
                "file_path":         str(file_path),
                "format":            file_path.suffix.lstrip(".").upper(),
                "overall_status":    "error",
                "vbr_status":        "error",
                "vbr_details":       f"Exception: {e}",
                "integrity_status":  "not_checked",
                "integrity_details": "",
                "from_cache":        False,
            })
            errors += 1

        pbar.update(1)

    pbar.close()

    print()
    print(f"  Done.  Fixed: {fixed}  |  Unfixable: {unfixable}  |  "
          f"Skipped: {skipped}  |  Errors: {errors}")

    return results


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def run_check_music_integrity(
    root=None,
    apply=False,
    run_integrity=True,
    mp3_only=False,
    rebuild_cache=False,
    from_csv=None,
    reports_dir=None,
    progress_callback=None,
    log_callback=None,
):
    """
    GUI-callable core for Music Integrity Checker.

    Parameters
    ----------
    root            : str or Path or None — folder to scan. Required unless
                      from_csv is provided.
    apply           : bool — False = dry run (default), True = fix VBR headers.
    run_integrity   : bool — True = full ffmpeg decode check (default).
    mp3_only        : bool — True = skip FLAC/AAC/M4A files.
    rebuild_cache   : bool — True = ignore SQLite cache, re-decode everything.
    from_csv        : str, Path, or None — path to a dry-run CSV for from-csv
                      mode. When provided, root is ignored.
    reports_dir     : Path or None — override the default reports directory.
    progress_callback : callable(current, total, filename) or None.
    log_callback    : callable(message) or None — key status lines sent here.

    Returns
    -------
    dict with keys:
        rows        — list of report row dicts
        counts      — dict mapping overall_status -> count
        report_path — Path to the CSV report written this run
        reports_dir — Path to the reports directory used
    """
    def _log(msg):
        print(msg)
        if log_callback:
            try:
                log_callback(msg)
            except Exception:
                pass

    rdir = Path(reports_dir) if reports_dir else SCRIPT_DIR / "reports"
    rdir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    mp3val_path, ffmpeg_path = check_tools(run_integrity=run_integrity)

    # ── from-csv mode ──────────────────────────────────────────────────────────
    if from_csv is not None:
        csv_src = Path(from_csv)
        if not csv_src.exists():
            raise ValueError("CSV file not found: %s" % csv_src)

        output_path = rdir / ("integrity_%s_applied.csv" % timestamp)

        _log("")
        _log("=" * 60)
        _log("  Music Integrity Checker  v1.6")
        _log("=" * 60)
        _log("  Mode   : APPLY FROM CSV")
        _log("  Source : %s" % csv_src.name)
        _log("  Report : %s" % output_path.name)
        _log("=" * 60)

        if not mp3val_path:
            raise ValueError("mp3val not found -- cannot apply VBR fixes")

        rows = apply_from_csv(csv_src, mp3val_path,
                              progress_callback=progress_callback)
        if rows:
            write_csv(rows, str(output_path))
            _log("")
            _log("  Report saved to:")
            _log("  %s" % output_path)

        counts = {}
        for r in rows:
            counts[r["overall_status"]] = counts.get(r["overall_status"], 0) + 1

        return {
            "rows":        rows,
            "counts":      counts,
            "report_path": output_path,
            "reports_dir": rdir,
        }

    # ── standard scan mode ─────────────────────────────────────────────────────
    if root is None:
        raise ValueError("root must be provided when not using from_csv mode")
    root = Path(root)
    if not root.exists() or not root.is_dir():
        raise ValueError("Folder not found: %s" % root)

    suffix = "_applied" if apply else "_dry"
    if run_integrity:
        suffix += "_integrity"
    if rebuild_cache:
        suffix += "_rebuild"
    output_path = rdir / ("integrity_%s%s.csv" % (timestamp, suffix))

    sep = "=" * 60
    _log("")
    _log(sep)
    _log("  Music Integrity Checker  v1.6")
    _log(sep)
    mode_label = "APPLY - repairing VBR headers" if apply else "DRY RUN - no changes made"
    intg_label = "enabled (full decode check)" if run_integrity else "disabled (--quick)"
    fmt_label  = "MP3 only" if mp3_only else "MP3, FLAC, AAC, M4A"
    _log("  Mode      : %s" % mode_label)
    _log("  Integrity : %s" % intg_label)
    _log("  Formats   : %s" % fmt_label)
    if rebuild_cache:
        _log("  Cache     : REBUILD (ignoring existing integrity cache)")
    _log("  Report    : %s" % output_path.name)
    _log(sep)

    if not mp3val_path and (not run_integrity or not ffmpeg_path):
        raise ValueError(
            "No tools available (mp3val and/or ffmpeg not found). "
            "Place executables next to the script or add to PATH."
        )

    _log("")
    _log("  Scanning  : %s" % root)
    _log("")

    rows = run_scan(
        root, mp3val_path, ffmpeg_path,
        apply_mode=apply,
        run_integrity=run_integrity,
        rebuild_cache=rebuild_cache,
        mp3_only=mp3_only,
        progress_callback=progress_callback,
    )

    if rows:
        write_csv(rows, str(output_path))
        print_summary(rows, apply, run_integrity, str(output_path))
    else:
        _log("")
        _log("  No files processed.")

    counts = {}
    for r in rows:
        counts[r["overall_status"]] = counts.get(r["overall_status"], 0) + 1

    return {
        "rows":        rows,
        "counts":      counts,
        "report_path": output_path,
        "reports_dir": rdir,
    }


def main():
    # -- Flag parsing ----------------------------------------------------------
    _args         = sys.argv[1:]
    APPLY_MODE    = "--apply"         in _args
    RUN_INTEGRITY = "--quick"         not in _args
    MP3_ONLY      = "--mp3-only"      in _args
    FROM_CSV      = "--from-csv"      in _args
    REBUILD_CACHE = "--rebuild-cache" in _args

    _positional   = [a for a in _args if not a.startswith("--")]
    FOLDER_ARG    = _positional[0].strip('"') if _positional else None

    interactive_options([
        ("--quick",         "Quick -- VBR check only, skip full ffmpeg decode (faster)"),
        ("--rebuild-cache", "Rebuild cache -- ignore cached results, re-check all files"),
    ])

    # -- from-csv mode ---------------------------------------------------------
    if FROM_CSV:
        chosen = pick_csv_file()
        if not chosen:
            print("No CSV file selected. Exiting.")
            sys.exit(0)
        try:
            run_check_music_integrity(from_csv=chosen)
        except ValueError as exc:
            print("ERROR: %s" % exc)
            sys.exit(1)
        return

    # -- Standard scan mode ----------------------------------------------------
    if FOLDER_ARG:
        root_path = Path(FOLDER_ARG)
        if not root_path.exists() or not root_path.is_dir():
            print("ERROR: Folder not found: %s" % root_path)
            sys.exit(1)
    else:
        root_path = pick_folder("Select folder to scan")
        if not root_path:
            print("No folder selected. Exiting.")
            sys.exit(0)

    try:
        run_check_music_integrity(
            root          = root_path,
            apply         = APPLY_MODE,
            run_integrity = RUN_INTEGRITY,
            mp3_only      = MP3_ONLY,
            rebuild_cache = REBUILD_CACHE,
        )
    except ValueError as exc:
        print("ERROR: %s" % exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
