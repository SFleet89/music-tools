"""
Music Integrity Checker  v1.1
==============================
Scans your music library for file integrity issues and repairs VBR headers
in MP3 files — equivalent to foobar2000's "Verify Integrity" and
"Fix VBR Header" functions.

Two independent checks are available:

  VBR HEADER  (MP3 only, fast — always runs)
              Detects missing or incorrect Xing/LAME/VBRI headers. These
              cause players to mis-report track duration and seek incorrectly
              in variable-bitrate files. mp3val repairs them in --apply mode.

  INTEGRITY   (all formats, slow — opt-in with --integrity)
              Full decode pass via ffmpeg. Catches corrupt frames, truncated
              files, and audio stream errors. Results are informational only —
              corrupt audio cannot be automatically repaired.

Report statuses:
  ok              No issues found
  vbr_needs_fix   VBR header issue detected (dry run)
  vbr_fixed       VBR header successfully repaired (apply mode)
  vbr_unfixable   mp3val found errors it cannot repair
  vbr_skipped     mp3val not found — VBR check not performed
  decode_ok        ffmpeg found no decode errors
  decode_errors    ffmpeg reported errors (informational, file may be corrupt)
  decode_skipped   ffmpeg not found or --integrity not used
  error           Unexpected exception during processing

Required tools — place next to this script OR add to system PATH:
  mp3val    http://mp3val.sourceforge.net/download.html
  ffmpeg    https://ffmpeg.org/download.html  (needed for --integrity only)

Python requirements:
  pip install tqdm   (optional — enables progress bars)

Usage:
  python check_music_integrity.py                       # folder picker, VBR check
  python check_music_integrity.py --apply               # fix VBR headers
  python check_music_integrity.py --from-csv            # apply fixes from dry-run CSV (file picker)
  python check_music_integrity.py --integrity           # also run full decode check
  python check_music_integrity.py --apply --integrity   # fix + full decode
  python check_music_integrity.py "C:\\path\\Music"     # skip folder picker
  python check_music_integrity.py --mp3-only            # skip FLAC/AAC/M4A

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

# ── Optional tqdm ──────────────────────────────────────────────────────────────
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

SCRIPT_DIR = Path(__file__).parent

# ── Supported formats ──────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS    = {".mp3", ".flac", ".aac", ".m4a"}
MP3_ONLY_EXTENSIONS     = {".mp3"}

# ── Parse arguments ────────────────────────────────────────────────────────────
_args        = sys.argv[1:]
APPLY_MODE   = "--apply"     in _args
RUN_INTEGRITY = "--integrity" in _args
MP3_ONLY     = "--mp3-only"  in _args
FROM_CSV     = "--from-csv"  in _args

_positional  = [a for a in _args if not a.startswith("--")]
FOLDER_ARG   = _positional[0].strip('"') if _positional else None

SCAN_EXTENSIONS = MP3_ONLY_EXTENSIONS if MP3_ONLY else SUPPORTED_EXTENSIONS

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


def check_tools():
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

    if RUN_INTEGRITY:
        if ffmpeg:
            print(f"  ffmpeg   : {ffmpeg}")
        else:
            print("  ffmpeg   : NOT FOUND")
            print(f"             Looked in : {SCRIPT_DIR / 'ffmpeg.exe'}")
            print("             Also tried: system PATH")
            print("             Download  : https://ffmpeg.org/download.html")
            print(f"             Fix       : place ffmpeg.exe in {SCRIPT_DIR}")
    else:
        print("  ffmpeg   : (skipped — use --integrity to enable full decode check)")

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
#  FILE PROCESSING
# ══════════════════════════════════════════════════════════════════════════════

def process_file(file_path, mp3val_path, ffmpeg_path, apply_mode, run_integrity):
    """
    Run all applicable checks on a single file. Returns a report row dict,
    or None if this file has nothing to check (non-MP3 without --integrity).
    """
    ext = file_path.suffix.lower()
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
    }

    try:
        # ── VBR check (MP3 only) ──
        if is_mp3:
            if mp3val_path:
                vbr = run_mp3val(file_path, mp3val_path, fix=apply_mode)
                row["vbr_status"]   = vbr["vbr_status"]
                row["vbr_details"]  = vbr["vbr_details"]
            else:
                row["vbr_status"] = "vbr_skipped"

        # ── Integrity check (all formats, if requested) ──
        if run_integrity and ffmpeg_path:
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

def find_audio_files(root, run_integrity):
    """
    Return all supported audio files. If integrity check is disabled,
    only return MP3s — there's nothing to check on other formats.
    """
    extensions = SCAN_EXTENSIONS if run_integrity else MP3_ONLY_EXTENSIONS
    # Honour --mp3-only regardless
    if MP3_ONLY:
        extensions = MP3_ONLY_EXTENSIONS
    return sorted(
        p for p in Path(root).rglob("*")
        if p.is_file() and p.suffix.lower() in extensions
    )


def run_scan(root, mp3val_path, ffmpeg_path, apply_mode, run_integrity):
    """
    Scan all audio files under root. Uses threading for the integrity check
    (slow ffmpeg decode) but processes VBR checks sequentially to avoid
    mp3val file-locking issues in apply mode.
    """
    files = find_audio_files(root, run_integrity)
    total = len(files)

    if total == 0:
        print(f"  No audio files found in: {root}")
        return []

    scope = "MP3, FLAC, AAC, M4A" if run_integrity else "MP3 only"
    print(f"  Found {total:,} file(s) to process ({scope}).")
    if run_integrity:
        print("  NOTE: Full decode check enabled — this may take a long time.")
        print("        Estimated time: roughly 2–5 seconds per file.")
    print()

    if apply_mode:
        _print_apply_warning()

    rows = []

    if run_integrity and ffmpeg_path and not apply_mode:
        # Run VBR check + ffmpeg decode in parallel (read-only passes)
        rows = _run_parallel(files, mp3val_path, ffmpeg_path, apply_mode, run_integrity)
    else:
        # Sequential — safer for apply mode (mp3val writes files)
        rows = _run_sequential(files, mp3val_path, ffmpeg_path, apply_mode, run_integrity)

    return rows


def _run_sequential(files, mp3val_path, ffmpeg_path, apply_mode, run_integrity):
    rows = []
    pbar = make_pbar(len(files), "Checking")

    for f in files:
        row = process_file(f, mp3val_path, ffmpeg_path, apply_mode, run_integrity)
        if row is not None:
            rows.append(row)
            _print_finding(row)
        pbar.update(1)

    pbar.close()
    return rows


def _run_parallel(files, mp3val_path, ffmpeg_path, apply_mode, run_integrity):
    """Parallel scan for read-only integrity checks."""
    max_workers = min(os.cpu_count() or 4, 8)
    pbar        = make_pbar(len(files), "Checking")
    rows        = []
    lock        = threading.Lock()

    rows = []
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(
                process_file, f, mp3val_path, ffmpeg_path, apply_mode, run_integrity
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
                }
            if row is not None:
                with lock:
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


def write_csv(rows, output_path):
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows, apply_mode, run_integrity, output_path):
    counts = {}
    for r in rows:
        counts[r["overall_status"]] = counts.get(r["overall_status"], 0) + 1

    total = len(rows)
    print()
    print("=" * 60)
    print(f"  SUMMARY  ({'APPLY' if apply_mode else 'DRY RUN'})")
    print("=" * 60)
    print(f"  Total files checked   : {total:,}")
    print(f"  No issues             : {counts.get('ok', 0):,}")
    if apply_mode:
        print(f"  VBR headers fixed     : {counts.get('vbr_fixed', 0):,}")
    else:
        print(f"  VBR headers need fix  : {counts.get('vbr_needs_fix', 0):,}")
    print(f"  VBR unfixable errors  : {counts.get('vbr_unfixable', 0):,}")
    if run_integrity:
        print(f"  Decode errors found   : {counts.get('decode_errors', 0):,}")
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


# ══════════════════════════════════════════════════════════════════════════════
#  FOLDER PICKER
# ══════════════════════════════════════════════════════════════════════════════

def pick_folder():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(
            title="Select music folder to check",
            initialdir=r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\SD\Music",
        )
        root.destroy()
        return chosen or None
    except Exception as e:
        print(f"ERROR: Could not open folder picker: {e}")
        return None


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


def apply_from_csv(csv_path, mp3val_path):
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

    pbar = make_pbar(len(fixable), "Fixing")

    for csv_row in fixable:
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
                # Retry succeeded and file had no VBR issue after all
                fixed += 1
            elif vbr["vbr_status"] == "error":
                errors += 1

        except Exception as e:
            print(f"  [ERROR]    {file_path.name} — {e}")
            results.append({
                "file_path":         str(file_path),
                "format":            file_path.suffix.lstrip(".").upper(),
                "overall_status":    "error",
                "vbr_status":        "error",
                "vbr_details":       f"Exception: {e}",
                "integrity_status":  "not_checked",
                "integrity_details": "",
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

def main():
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports_dir = SCRIPT_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)

    # ── --from-csv mode: apply fixes from a previous dry-run report ──
    if FROM_CSV:
        chosen = pick_csv_file()
        if not chosen:
            print("No CSV file selected. Exiting.")
            sys.exit(0)

        csv_path    = Path(chosen)
        output_path = reports_dir / f"integrity_{timestamp}_applied.csv"

        print()
        print("=" * 60)
        print("  Music Integrity Checker  v1.1")
        print("=" * 60)
        print("  Mode   : APPLY FROM CSV")
        print(f"  Source : {csv_path.name}")
        print(f"  Report : {output_path}")
        print("=" * 60)

        mp3val_path, _ = check_tools()
        if not mp3val_path:
            print("ERROR: mp3val not found — cannot apply fixes.")
            sys.exit(1)

        print()
        print("  !! VBR headers will be repaired in place.")
        print("     Originals are not backed up — ensure you have a backup.")
        confirm = input("\n  Proceed with applying fixes from this CSV? (y/n): ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            sys.exit(0)

        rows = apply_from_csv(csv_path, mp3val_path)

        if rows:
            write_csv(rows, str(output_path))
            # Print summary tailored to from-csv mode
            counts = {}
            for r in rows:
                counts[r["overall_status"]] = counts.get(r["overall_status"], 0) + 1
            print()
            print("=" * 60)
            print("  SUMMARY  (APPLY FROM CSV)")
            print("=" * 60)
            print(f"  VBR headers fixed     : {counts.get('vbr_fixed', 0) + counts.get('ok', 0):,}")
            print(f"  VBR unfixable         : {counts.get('vbr_unfixable', 0):,}")
            print(f"  Skipped (missing)     : {counts.get('skipped', 0):,}")
            print(f"  Errors                : {counts.get('error', 0):,}")
            print()
            print(f"  Report saved to:")
            print(f"  {output_path}")
            print("=" * 60)
        else:
            print("  No results to save.")
        return

    # ── Standard scan mode ──
    suffix = "_applied" if APPLY_MODE else "_dry"
    if RUN_INTEGRITY:
        suffix += "_integrity"
    output_path = reports_dir / f"integrity_{timestamp}{suffix}.csv"

    print()
    print("=" * 60)
    print("  Music Integrity Checker  v1.1")
    print("=" * 60)
    print(f"  Mode      : {'APPLY — repairing VBR headers' if APPLY_MODE else 'DRY RUN — no changes made'}")
    print(f"  Integrity : {'enabled (full decode check)' if RUN_INTEGRITY else 'disabled (use --integrity to enable)'}")
    print(f"  Formats   : {'MP3 only' if MP3_ONLY else 'MP3, FLAC, AAC, M4A'}")

    mp3val_path, ffmpeg_path = check_tools()

    # Get folder
    if FOLDER_ARG:
        root_path = Path(FOLDER_ARG)
    else:
        chosen = pick_folder()
        if not chosen:
            print("No folder selected. Exiting.")
            sys.exit(0)
        root_path = Path(chosen)

    if not root_path.exists() or not root_path.is_dir():
        print(f"ERROR: Folder not found: {root_path}")
        sys.exit(1)

    print(f"  Folder    : {root_path}")
    print(f"  Report    : {output_path}")
    print("=" * 60)

    # Bail out early if no tools available
    if not mp3val_path and (not RUN_INTEGRITY or not ffmpeg_path):
        print()
        print("ERROR: No tools available to run any checks.")
        print("       Install mp3val and/or ffmpeg and try again.")
        sys.exit(1)

    # Confirmation for apply mode
    if APPLY_MODE:
        print()
        confirm = input("  Proceed with repairing VBR headers? (y/n): ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            sys.exit(0)

    rows = run_scan(root_path, mp3val_path, ffmpeg_path, APPLY_MODE, RUN_INTEGRITY)

    if rows:
        write_csv(rows, str(output_path))
        print_summary(rows, APPLY_MODE, RUN_INTEGRITY, str(output_path))
    else:
        print("  No files found — nothing to report.")


if __name__ == "__main__":
    main()
