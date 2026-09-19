"""
format_dupe_finder.py  v1.0  —  2026-06-13
============================================
Read-only diagnostic tool. Scans a music library for albums that exist in
both MP3 and FLAC format, verifies the FLAC copies, and reports which MP3
folders are safe to delete.

Detects two types of format pairs:
  Same folder  — a folder that contains both .mp3 and .flac files
  Sibling pair — two adjacent folders with similar names, one all-MP3,
                 one all-FLAC (e.g. "Album [MP3]" / "Album [FLAC]")

For each pair found:
  1. Runs an ffmpeg full-decode integrity check on every FLAC file
     (results cached in music_cache.db integrity_cache table)
  2. Fingerprints a sample of MP3 and FLAC tracks with fpcalc and
     compares the Chromaprint similarity scores
     (results cached in music_cache.db fp_cache table)
  3. Assigns a verdict:
       SAFE TO DELETE MP3  — all FLACs pass integrity, FP >= threshold,
                             track counts match
       NEEDS REVIEW        — track count mismatch, low/partial FP score,
                             or could not fingerprint
       FLAC CORRUPT        — one or more FLACs fail ffmpeg decode

Output:
  CSV report saved to format_dupe_finder/reports/

Usage:
  python format_dupe_finder.py --pick
  python format_dupe_finder.py --path "E:\\Music"
  python format_dupe_finder.py --pick --sample half
  python format_dupe_finder.py --pick --no-fp
  python format_dupe_finder.py --pick --threshold 90

Flags:
  --pick          Open a folder-picker dialog
  --path "..."    Specify root folder directly
  --sample N      Tracks to fingerprint per album: 3 (default), half, all
  --threshold N   FP similarity threshold % (default: from config, fallback 85)
  --no-fp         Skip fingerprinting — integrity + track count only

This script makes NO changes to any files.
"""

import math
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import (
    pick_folder,
    write_csv,
    open_db,
    init_db,
    load_config,
    interactive_options,
)

SCRIPT_DIR     = Path(__file__).parent
REPORTS_FOLDER = SCRIPT_DIR / "reports"

MP3_EXTS  = {".mp3"}
FLAC_EXTS = {".flac"}

# ffmpeg error noise to ignore
_FFMPEG_IGNORE = {
    "deprecated", "incorrect timestamps", "non monotonous",
    "past duration", "application provided invalid",
    "id3v1 tag", "encoder delay",
}

# Minimum fingerprint data points considered reliable
FP_MIN_POINTS = 50


# ══════════════════════════════════════════════════════════════════════════════
#  TOOL DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════

def _find_tool(name):
    import shutil as _sh
    for candidate in (SCRIPT_DIR / name, SCRIPT_DIR / (name + ".exe")):
        if candidate.exists():
            return str(candidate)
    return _sh.which(name)


# ══════════════════════════════════════════════════════════════════════════════
#  SQLITE CACHE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _fp_get(conn, path_str, mtime):
    row = conn.execute(
        "SELECT fingerprint, fp_duration, mtime FROM fp_cache WHERE path_str=?",
        (path_str,),
    ).fetchone()
    if row and abs(row[2] - mtime) < 1.0:
        return row[0], row[1]
    return None, None


def _fp_put(conn, path_str, mtime, fp, duration):
    conn.execute(
        "INSERT OR REPLACE INTO fp_cache (path_str, mtime, fingerprint, fp_duration) "
        "VALUES (?,?,?,?)",
        (path_str, mtime, fp, duration),
    )
    conn.commit()


def _integrity_get(conn, path_str, mtime, size):
    row = conn.execute(
        "SELECT integrity_status, integrity_detail, mtime, size "
        "FROM integrity_cache WHERE path_str=?",
        (path_str,),
    ).fetchone()
    if row and abs(row[2] - mtime) < 1.0 and row[3] == size:
        return row[0], row[1]
    return None, None


def _integrity_put(conn, path_str, mtime, size, status, detail):
    conn.execute(
        "INSERT OR REPLACE INTO integrity_cache "
        "(path_str, mtime, size, integrity_status, integrity_detail, checked_at) "
        "VALUES (?,?,?,?,?,?)",
        (path_str, mtime, size, status, detail or "", datetime.now().isoformat()),
    )
    conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  FINGERPRINTING
# ══════════════════════════════════════════════════════════════════════════════

def _get_fingerprint(path, fpcalc_path, conn):
    """Run fpcalc with cache. Returns (fp_str, duration) or (None, None)."""
    path_str = str(path)
    try:
        mtime = path.stat().st_mtime
    except Exception:
        return None, None

    fp, dur = _fp_get(conn, path_str, mtime)
    if fp:
        return fp, dur

    try:
        result = subprocess.run(
            [fpcalc_path, "-raw", str(path)],
            capture_output=True, text=True, timeout=120,
        )
        fp, dur = None, None
        for line in result.stdout.splitlines():
            if line.startswith("FINGERPRINT="):
                fp = line.split("=", 1)[1].strip()
            elif line.startswith("DURATION="):
                try:
                    dur = float(line.split("=", 1)[1].strip())
                except ValueError:
                    pass
        if fp and len(fp.split(",")) >= FP_MIN_POINTS:
            _fp_put(conn, path_str, mtime, fp, dur)
            return fp, dur
        return None, None
    except Exception:
        return None, None


def _fp_similarity(fp1, fp2):
    """Chromaprint bit-level similarity, 0–100. Same algorithm as find_music_duplicates."""
    try:
        ints1 = list(map(int, fp1.split(",")))
        ints2 = list(map(int, fp2.split(",")))
        length = min(len(ints1), len(ints2))
        if length == 0:
            return 0.0
        diff = sum(bin(a ^ b).count("1") for a, b in zip(ints1[:length], ints2[:length]))
        return (1 - diff / (length * 32)) * 100
    except Exception:
        return 0.0


# ══════════════════════════════════════════════════════════════════════════════
#  INTEGRITY CHECK
# ══════════════════════════════════════════════════════════════════════════════

def _check_integrity(path, ffmpeg_path, conn):
    """ffmpeg full-decode with cache. Returns (status, detail)."""
    path_str = str(path)
    try:
        st = path.stat()
        mtime, size = st.st_mtime, st.st_size
    except Exception:
        return "error", "stat failed"

    status, detail = _integrity_get(conn, path_str, mtime, size)
    if status:
        return status, detail

    try:
        result = subprocess.run(
            [ffmpeg_path, "-v", "error", "-i", str(path), "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
        bad = [
            l.strip() for l in result.stderr.splitlines()
            if l.strip() and not any(ig in l.lower() for ig in _FFMPEG_IGNORE)
        ]
        if bad:
            status, detail = "decode_errors", "; ".join(bad[:5])
        else:
            status, detail = "decode_ok", ""
    except subprocess.TimeoutExpired:
        status, detail = "timeout", "ffmpeg timed out"
    except Exception as e:
        status, detail = "error", str(e)

    _integrity_put(conn, path_str, mtime, size, status, detail)
    return status, detail


# ══════════════════════════════════════════════════════════════════════════════
#  PAIR DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def _direct_files(folder, exts):
    """Non-recursive list of files in folder matching exts."""
    try:
        return sorted(f for f in folder.iterdir()
                      if f.is_file() and f.suffix.lower() in exts)
    except PermissionError:
        return []


def _normalise_name(name):
    """Strip format tags for sibling-folder comparison."""
    s = name.lower()
    s = re.sub(r"[\[\(]?\s*(mp3|flac|320|v0|v2|lossless)\s*[\]\)]?", "", s)
    return re.sub(r"\s+", " ", s).strip(" -_")


def find_pairs(root):
    """
    Walk root and return list of (mp3_folder, flac_folder) pairs.
    Handles same-folder mixed content and sibling folder pairs.
    """
    root = Path(root)
    pairs = []
    seen = set()

    all_dirs = sorted(
        [root] + [d for d in root.rglob("*") if d.is_dir()],
        key=lambda d: len(d.parts),
    )

    # Option A: same folder has both MP3 and FLAC
    for folder in all_dirs:
        if _direct_files(folder, MP3_EXTS) and _direct_files(folder, FLAC_EXTS):
            key = (str(folder), str(folder))
            if key not in seen:
                pairs.append((folder, folder))
                seen.add(key)

    # Option B: sibling folders — one all-MP3, one all-FLAC, similar names
    parent_groups = {}
    for folder in all_dirs:
        parent_groups.setdefault(str(folder.parent), []).append(folder)

    for _parent_str, siblings in parent_groups.items():
        if len(siblings) < 2:
            continue
        mp3_only = [s for s in siblings
                    if _direct_files(s, MP3_EXTS) and not _direct_files(s, FLAC_EXTS)]
        flac_only = [s for s in siblings
                     if _direct_files(s, FLAC_EXTS) and not _direct_files(s, MP3_EXTS)]
        for mp3_sib in mp3_only:
            for flac_sib in flac_only:
                if _normalise_name(mp3_sib.name) == _normalise_name(flac_sib.name):
                    key = (str(mp3_sib), str(flac_sib))
                    if key not in seen:
                        pairs.append((mp3_sib, flac_sib))
                        seen.add(key)

    return pairs


# ══════════════════════════════════════════════════════════════════════════════
#  SAMPLING
# ══════════════════════════════════════════════════════════════════════════════

def _sample_files(files, mode):
    """Return a sample from files: mode is '3', 'half', or 'all'."""
    n = len(files)
    if n == 0:
        return []
    if mode == "all":
        return list(files)
    if mode == "half":
        return list(files[:max(1, math.ceil(n / 2))])
    return list(files[:min(3, n)])  # default: first 3


# ══════════════════════════════════════════════════════════════════════════════
#  PAIR ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def _analyse_pair(mp3_folder, flac_folder, conn,
                  fpcalc_path, ffmpeg_path, threshold, sample_mode, no_fp, log):
    """Analyse one pair. Returns a dict for the CSV row."""
    mp3_files  = _direct_files(mp3_folder,  MP3_EXTS)
    flac_files = _direct_files(flac_folder, FLAC_EXTS)

    mp3_count  = len(mp3_files)
    flac_count = len(flac_files)

    label = (mp3_folder.name if mp3_folder == flac_folder
             else f"{mp3_folder.name} ↔ {flac_folder.name}")
    log(f"  {label}")
    log(f"    MP3 tracks: {mp3_count}   FLAC tracks: {flac_count}")

    track_count_match = (mp3_count == flac_count and mp3_count > 0)
    notes = []
    if not track_count_match:
        notes.append(f"Track count mismatch: {mp3_count} MP3 vs {flac_count} FLAC")

    # ── FLAC integrity ──────────────────────────────────────────────────────
    integrity_pass = integrity_fail = 0
    if ffmpeg_path and flac_files:
        for flac in flac_files:
            status, detail = _check_integrity(flac, ffmpeg_path, conn)
            if status == "decode_ok":
                integrity_pass += 1
            else:
                integrity_fail += 1
                notes.append(f"{flac.name}: {status}")
        if integrity_fail == 0:
            flac_integrity = "PASS"
        elif integrity_fail == flac_count:
            flac_integrity = "FAIL"
        else:
            flac_integrity = f"PARTIAL ({integrity_pass}/{flac_count} pass)"
    elif not ffmpeg_path:
        flac_integrity = "SKIPPED (no ffmpeg)"
        log("    [!] ffmpeg not found — skipping integrity check")
    else:
        flac_integrity = "NO FLAC FILES"

    log(f"    FLAC integrity: {flac_integrity}")

    # ── Fingerprint comparison ──────────────────────────────────────────────
    fp_scores = []
    fp_failed = 0
    fp_similarity_str = "N/A"

    if not no_fp and fpcalc_path and mp3_files and flac_files:
        mp3_sample  = _sample_files(mp3_files,  sample_mode)
        flac_sample = _sample_files(flac_files, sample_mode)
        pairs_to_fp = list(zip(mp3_sample, flac_sample))
        log(f"    Fingerprinting {len(pairs_to_fp)} track pair(s)...")

        for m, f in pairs_to_fp:
            fp_m, _ = _get_fingerprint(m, fpcalc_path, conn)
            fp_f, _ = _get_fingerprint(f, fpcalc_path, conn)
            if fp_m and fp_f:
                score = _fp_similarity(fp_m, fp_f)
                fp_scores.append(score)
                log(f"      {m.name} ↔ {f.name}: {score:.1f}%")
            else:
                fp_failed += 1
                log(f"      [!] fpcalc failed on: {m.name} or {f.name}")

        if fp_failed:
            notes.append(f"fpcalc failed on {fp_failed} pair(s)")

        if fp_scores:
            avg = sum(fp_scores) / len(fp_scores)
            fp_similarity_str = f"{avg:.1f}"
            log(f"    FP avg score: {avg:.1f}%")
        else:
            fp_similarity_str = "FAILED"
            log("    FP score: FAILED (could not fingerprint any pair)")

    elif no_fp:
        fp_similarity_str = "SKIPPED (--no-fp)"
    elif not fpcalc_path:
        fp_similarity_str = "SKIPPED (no fpcalc)"
        log("    [!] fpcalc not found — skipping fingerprint check")

    # ── Verdict ─────────────────────────────────────────────────────────────
    flac_corrupt = integrity_fail > 0 and bool(ffmpeg_path)

    if flac_corrupt:
        verdict = "FLAC CORRUPT"
    elif fp_scores:
        avg = sum(fp_scores) / len(fp_scores)
        if avg >= threshold and track_count_match:
            verdict = "SAFE TO DELETE MP3"
        elif avg >= 50:
            verdict = "NEEDS REVIEW"
        else:
            verdict = "NEEDS REVIEW"
            notes.append(f"Low FP similarity ({avg:.1f}%) — possible different master")
    elif no_fp or not fpcalc_path:
        # No fingerprint — can only assess integrity + track counts
        if flac_integrity == "PASS" and track_count_match:
            verdict = "NEEDS REVIEW"
            notes.append("No FP check — verify manually before deleting")
        else:
            verdict = "NEEDS REVIEW"
    else:
        verdict = "NEEDS REVIEW"

    if not track_count_match and verdict == "SAFE TO DELETE MP3":
        verdict = "NEEDS REVIEW"

    log(f"    Verdict: {verdict}\n")

    return {
        "mp3_folder":       str(mp3_folder),
        "flac_folder":      str(flac_folder),
        "mp3_track_count":  mp3_count,
        "flac_track_count": flac_count,
        "tracks_match":     "YES" if track_count_match else "NO",
        "flac_integrity":   flac_integrity,
        "fp_similarity":    fp_similarity_str,
        "verdict":          verdict,
        "notes":            " | ".join(notes),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  GUI-CALLABLE CORE
# ══════════════════════════════════════════════════════════════════════════════

def run_format_dupe_finder(root, threshold=85.0, sample_mode="3", no_fp=False,
                           fpcalc_path=None, ffmpeg_path=None,
                           progress_callback=None, log_callback=None):
    """
    Scan root for format duplicate album pairs (MP3 + FLAC).

    Returns dict:
        pairs_found, safe_to_delete, needs_review, flac_corrupt,
        rows (list), report_path (Path | None)
    """
    log = log_callback or print
    root = Path(root)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Folder not found: {root}")

    conn = open_db()
    init_db(conn)

    # Tool discovery (fallback if not supplied by caller)
    if fpcalc_path is None:
        fpcalc_path = _find_tool("fpcalc")
    if ffmpeg_path is None:
        ffmpeg_path = _find_tool("ffmpeg")

    log(f"  fpcalc  : {fpcalc_path or 'NOT FOUND'}")
    log(f"  ffmpeg  : {ffmpeg_path or 'NOT FOUND'}")
    log(f"  Threshold   : {threshold}%")
    log(f"  Sample mode : {sample_mode} tracks per album")
    log("")

    log("  Scanning for format duplicate pairs...")
    pairs = find_pairs(root)
    log(f"  Found {len(pairs)} pair(s)\n")

    rows = []
    for i, (mp3_folder, flac_folder) in enumerate(pairs, 1):
        if progress_callback:
            progress_callback(i, len(pairs), flac_folder.name)
        label = (mp3_folder.name if mp3_folder == flac_folder
                 else f"{flac_folder.name}")
        log(f"[{i}/{len(pairs)}] {label}")
        row = _analyse_pair(
            mp3_folder, flac_folder, conn,
            fpcalc_path, ffmpeg_path, threshold, sample_mode, no_fp, log,
        )
        rows.append(row)

    safe    = sum(1 for r in rows if r["verdict"] == "SAFE TO DELETE MP3")
    review  = sum(1 for r in rows if r["verdict"] == "NEEDS REVIEW")
    corrupt = sum(1 for r in rows if r["verdict"] == "FLAC CORRUPT")

    report_path = None
    if rows:
        REPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = REPORTS_FOLDER / f"format_dupe_finder_{ts}.csv"
        fieldnames = [
            "mp3_folder", "flac_folder", "mp3_track_count", "flac_track_count",
            "tracks_match", "flac_integrity", "fp_similarity", "verdict", "notes",
        ]
        write_csv(rows, report_path, fieldnames)
        log(f"\n  Report saved: {report_path}")

    log("\n  ── Summary " + "─" * 37)
    log(f"  Pairs found      : {len(pairs)}")
    log(f"  Safe to delete   : {safe}")
    log(f"  Needs review     : {review}")
    log(f"  FLAC corrupt     : {corrupt}")

    conn.close()

    return {
        "pairs_found":    len(pairs),
        "safe_to_delete": safe,
        "needs_review":   review,
        "flac_corrupt":   corrupt,
        "rows":           rows,
        "report_path":    report_path,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    interactive_options([
        ("--no-fp",       "Skip fingerprints — integrity + track count only (faster)"),
        ("--sample 3",    "Sample: first 3 tracks per album (default)"),
        ("--sample half", "Sample: first half of each album"),
        ("--sample all",  "Sample: every track (most thorough)"),
    ])

    NO_FP    = "--no-fp" in sys.argv
    PICK_DIR = "--pick"  in sys.argv

    def _flag_val(flag):
        return next(
            (sys.argv[i + 1] for i, a in enumerate(sys.argv)
             if a == flag and i + 1 < len(sys.argv)),
            None,
        )

    _path_flag      = _flag_val("--path")
    _threshold_flag = _flag_val("--threshold")
    _sample_flag    = _flag_val("--sample")

    # Banner
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║      Format Duplicate Finder   v1.0         ║")
    print("  ║  Finds albums with both MP3 and FLAC        ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    print("  Mode : Read-only scan — no files will be modified or deleted")
    print()

    # Config
    threshold  = 85.0
    fpcalc_path = None
    try:
        cfg = load_config()
        threshold   = float(cfg.get("acoustid", {}).get("similarity_threshold", 85))
        fpcalc_path = cfg.get("acoustid", {}).get("fpcalc_path", "").strip() or None
    except Exception:
        pass

    if _threshold_flag:
        try:
            threshold = float(_threshold_flag)
        except ValueError:
            print(f"  WARNING: Invalid --threshold '{_threshold_flag}' — using {threshold}")

    sample_mode = "3"
    if _sample_flag:
        if _sample_flag in ("3", "half", "all"):
            sample_mode = _sample_flag
        else:
            print(f"  WARNING: Invalid --sample '{_sample_flag}'. Use: 3, half, all. Defaulting to 3.")

    # Folder selection
    if PICK_DIR:
        root = pick_folder("Select library root to scan")
        if not root:
            print("  No folder selected. Exiting.")
            sys.exit(0)
    elif _path_flag:
        root = Path(_path_flag.strip('"'))
    else:
        print("  ERROR: No folder specified.")
        print("  Use --pick to open a folder dialog, or --path \"C:\\...\" to specify directly.")
        sys.exit(1)

    if not root.exists() or not root.is_dir():
        print(f"  ERROR: Folder not found: {root}")
        sys.exit(1)

    print(f"  Scanning : {root}")
    print(f"  Threshold: {threshold}%")
    print(f"  Sample   : {sample_mode} tracks per album pair")
    if NO_FP:
        print("  FP check : SKIPPED (--no-fp)")
    print()

    try:
        run_format_dupe_finder(
            root=root,
            threshold=threshold,
            sample_mode=sample_mode,
            no_fp=NO_FP,
            fpcalc_path=fpcalc_path,
        )
    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
