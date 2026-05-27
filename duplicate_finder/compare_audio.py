"""
compare_audio.py  v1.3  —  2026-05-25
========================================
Compare audio files by fingerprint — two-file and folder-scan modes.

TWO-FILE MODE  (--pick or --file1/--file2)
    Compare a single pair of files. Shows a side-by-side metadata table,
    fpcalc fingerprint similarity score, and a plain-English verdict.
    Files under 30 seconds are flagged — their fingerprints are too short
    to produce reliable scores and results should not be trusted.

FOLDER SCAN MODE  (--pick-folders or --folder1/--folder2)
    For every file in Folder A, find its best-matching file in Folder B
    (highest fingerprint similarity). Results are printed as a scored table
    and saved to a CSV in duplicate_finder/reports/.
    Pairs involving a file under 30 seconds are marked [!] — treat those
    scores as unreliable regardless of how high they appear.

Both modes use the identical fingerprint algorithm as find_music_duplicates.py
— scores are directly comparable to near-miss CSVs and scan reports.

Usage:
    python compare_audio.py --pick
        Two-file mode — opens two file-picker dialogs.

    python compare_audio.py --file1 "C:\\path\\a.mp3" --file2 "C:\\path\\b.mp3"
        Two-file mode — paths supplied directly.

    python compare_audio.py --pick-folders
        Folder scan mode — opens two folder-picker dialogs.

    python compare_audio.py --folder1 "C:\\Library" --folder2 "C:\\Unsorted"
        Folder scan mode — paths supplied directly.

This is a read-only diagnostic tool. No files are moved or modified.

Requirements:
    pip install mutagen
    fpcalc.exe must be present in the same folder as this script.
"""

import sys
import csv
import subprocess
import time
from pathlib import Path
from datetime import datetime

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

SCRIPT_DIR     = Path(__file__).parent
REPORTS_FOLDER = SCRIPT_DIR / "reports"

# fpcalc — use the copy in this folder if present, fall back to PATH
_fpcalc_local = SCRIPT_DIR / "fpcalc.exe"
FPCALC_PATH   = str(_fpcalc_local) if _fpcalc_local.exists() else "fpcalc"

# Thresholds matching find_music_duplicates.py defaults.
FP_SIMILARITY_THRESHOLD = 85.0   # duplicate finder match threshold
NEAR_MISS_LOW_THRESHOLD = 50.0   # bottom of the near-miss reporting zone

# Files shorter than this produce too few fingerprint data points to be
# reliable — same threshold used by find_music_duplicates.py v3.9.
FP_SHORT_FILE_SECONDS = 30

# Minimum fingerprint data points for a result to be considered reliable.
FP_MIN_LENGTH = 50

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".aac", ".m4a", ".wav", ".ogg", ".aiff"}

# Display widths (two-file mode)
_LINE_WIDTH  = 64
_LABEL_WIDTH = 12
_COL_WIDTH   = 22


# ══════════════════════════════════════════════════════════════════════════════
#  FLAG PARSING
# ══════════════════════════════════════════════════════════════════════════════

def _flag_val(flag: str) -> "str | None":
    return next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == flag and i + 1 < len(sys.argv)),
        None,
    )



# ══════════════════════════════════════════════════════════════════════════════
#  PICKERS
# ══════════════════════════════════════════════════════════════════════════════

def _tk_root():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root


def pick_file(title: str) -> "Path | None":
    """Open a native Windows file-picker dialog for a single audio file."""
    try:
        from tkinter import filedialog
    except ImportError:
        print("ERROR: tkinter is not available.")
        sys.exit(1)
    root = _tk_root()
    filetypes = [
        ("Audio files", "*.mp3 *.flac *.m4a *.aac *.wav *.ogg *.aiff"),
        ("All files",   "*.*"),
    ]
    path = filedialog.askopenfilename(title=title, filetypes=filetypes, parent=root)
    root.destroy()
    return Path(path) if path else None


def pick_folder(title: str) -> "Path | None":
    """Open a native Windows folder-picker dialog."""
    try:
        from tkinter import filedialog
    except ImportError:
        print("ERROR: tkinter is not available.")
        sys.exit(1)
    root = _tk_root()
    folder = filedialog.askdirectory(title=title, parent=root)
    root.destroy()
    return Path(folder) if folder else None


# ══════════════════════════════════════════════════════════════════════════════
#  METADATA READING
# ══════════════════════════════════════════════════════════════════════════════

def read_file_info(path: Path) -> dict:
    """
    Read metadata from an audio file via mutagen (easy tags).
    Original tag case is preserved for readable display.
    """
    result = {
        "path":        path,
        "size":        0,
        "title":       "",
        "artist":      "",
        "album":       "",
        "duration":    None,
        "bitrate":     None,
        "acoustid_id": "",
        "format":      path.suffix.lower(),
        "error":       None,
    }
    try:
        result["size"] = path.stat().st_size
    except Exception as e:
        result["error"] = str(e)
        return result
    try:
        from mutagen import File as MutagenFile
        easy = MutagenFile(path, easy=True)
        if easy:
            def first(tag):
                val = easy.get(tag)
                return val[0].strip() if val else ""
            result["title"]  = first("title")
            result["artist"] = first("artist")
            result["album"]  = first("album")
            aid = easy.get("acoustid_id")
            if aid:
                result["acoustid_id"] = str(aid[0]).strip()
        audio = MutagenFile(path)
        if audio and hasattr(audio, "info"):
            info = audio.info
            if hasattr(info, "bitrate"):
                result["bitrate"] = info.bitrate
            if hasattr(info, "length"):
                result["duration"] = info.length
    except Exception as e:
        result["error"] = f"mutagen: {e}"
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  SHORT-FILE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def is_short_file(duration: "float | None") -> bool:
    """
    Return True if a file is under FP_SHORT_FILE_SECONDS (30s).
    Short files produce too few fingerprint data points for a reliable score —
    the same threshold used by find_music_duplicates.py v3.9.
    """
    return duration is not None and 0 < duration < FP_SHORT_FILE_SECONDS


def short_file_note(info: dict, label: str) -> "str | None":
    """Return a warning string if the file is short, otherwise None."""
    dur = info.get("duration")
    if is_short_file(dur):
        return (f"{label} is only {fmt_duration(dur)} long — fingerprint score "
                f"is unreliable for files under {FP_SHORT_FILE_SECONDS}s.")
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  FINGERPRINTING
# ══════════════════════════════════════════════════════════════════════════════

def get_fingerprint(path: Path) -> "tuple[str | None, float | None]":
    """
    Run fpcalc on a file and return (fingerprint_string, duration_seconds).
    Returns (None, None) on failure.
    """
    try:
        result = subprocess.run(
            [FPCALC_PATH, "-raw", str(path)],
            capture_output=True, text=True, timeout=120,
        )
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
        return fp, duration
    except Exception:
        return None, None


def is_valid_fingerprint(fp: str) -> bool:
    """Return True if the fingerprint has enough data points to be reliable."""
    try:
        return len(fp.split(",")) >= FP_MIN_LENGTH
    except Exception:
        return False


def fingerprint_similarity(fp1: str, fp2: str) -> float:
    """
    Compare two raw Chromaprint fingerprints, return 0–100 similarity.

    IDENTICAL algorithm to find_music_duplicates.py — scores are directly
    comparable to near-miss CSVs and scan reports.

    Fingerprints are comma-separated 32-bit integers. Similarity is measured
    by the fraction of bits that agree across the overlap of both fingerprints.
    """
    try:
        ints1 = list(map(int, fp1.split(",")))
        ints2 = list(map(int, fp2.split(",")))
        length = min(len(ints1), len(ints2))
        if length == 0:
            return 0.0
        total_bits = length * 32
        diff_bits  = sum(bin(a ^ b).count("1") for a, b in zip(ints1[:length], ints2[:length]))
        return (1 - diff_bits / total_bits) * 100
    except Exception:
        return 0.0


def fingerprint_batch(files: list, label: str) -> dict:
    """
    Compute fingerprints for a list of file-info dicts.
    Prints a dot per file processed.
    Returns {path_str: (fingerprint | None, duration | None)}.
    """
    results = {}
    print(f"  Fingerprinting {label} ({len(files)} file{'s' if len(files) != 1 else ''})...")
    print("  ", end="", flush=True)
    t_start = time.perf_counter()
    for info in files:
        path = info["path"]
        fp, dur = get_fingerprint(path)
        results[str(path)] = (fp if fp and is_valid_fingerprint(fp) else None, dur)
        print(".", end="", flush=True)
    elapsed = time.perf_counter() - t_start
    print(f"  done  ({elapsed:.1f}s)")
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  FOLDER SCANNING
# ══════════════════════════════════════════════════════════════════════════════

def scan_folder_audio(folder: Path) -> list:
    """
    Return file-info dicts for all supported audio files directly in folder
    (non-recursive). Sorted by filename for predictable output order.
    """
    files = sorted(
        (p for p in folder.iterdir()
         if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS),
        key=lambda p: p.name.lower(),
    )
    return [read_file_info(f) for f in files]


def find_best_matches(files_a: list, fp_a: dict, fp_b: dict, files_b: list) -> list:
    """
    For each file in files_a, find the file in files_b with the highest
    fingerprint similarity score.

    Each result dict includes:
        info_a, info_b, score, fp_ok_a, fp_ok_b, short_a, short_b
    where short_* flags indicate files under FP_SHORT_FILE_SECONDS.
    Results are sorted by score descending.
    """
    results = []
    for info_a in files_a:
        key_a        = str(info_a["path"])
        fp_a_val, fp_a_dur = fp_a.get(key_a, (None, None))
        fp_ok_a      = fp_a_val is not None

        # Use fpcalc duration if available (more accurate), else mutagen
        dur_a   = fp_a_dur if fp_a_dur is not None else info_a.get("duration")
        short_a = is_short_file(dur_a)

        best_score   = 0.0
        best_info_b  = files_b[0] if files_b else None
        best_short_b = False
        fp_ok_b      = False

        if fp_ok_a and files_b:
            for info_b in files_b:
                key_b         = str(info_b["path"])
                fp_b_val, fp_b_dur = fp_b.get(key_b, (None, None))
                if fp_b_val is None:
                    continue
                score = fingerprint_similarity(fp_a_val, fp_b_val)
                if score > best_score:
                    best_score   = score
                    best_info_b  = info_b
                    fp_ok_b      = True
                    dur_b        = fp_b_dur if fp_b_dur is not None else info_b.get("duration")
                    best_short_b = is_short_file(dur_b)

        results.append({
            "info_a":  info_a,
            "info_b":  best_info_b,
            "score":   best_score,
            "fp_ok_a": fp_ok_a,
            "fp_ok_b": fp_ok_b,
            "short_a": short_a,
            "short_b": best_short_b,
        })

    results.sort(key=lambda r: -r["score"])
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  FORMATTING HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def fmt_duration(d) -> str:
    if d is None:
        return "Unknown"
    m, s = divmod(int(d), 60)
    return f"{m}:{s:02d}"


def fmt_bitrate(br) -> str:
    if br is None:
        return "Unknown"
    return f"{br // 1000} kbps"


def fmt_size(b: int) -> str:
    if b == 0:
        return "Unknown"
    if b < 1024 ** 2:
        return f"{b / 1024:.1f} KB"
    return f"{b / 1024 ** 2:.1f} MB"


def trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def verdict_label(score: float, fp_ok: bool) -> str:
    if not fp_ok:
        return "NO FINGERPRINT"
    if score >= FP_SIMILARITY_THRESHOLD:
        return "SAME RECORDING"
    if score >= NEAR_MISS_LOW_THRESHOLD:
        return "NEAR MISS"
    return "DIFFERENT"


# ══════════════════════════════════════════════════════════════════════════════
#  TWO-FILE MODE — OUTPUT
# ══════════════════════════════════════════════════════════════════════════════

def rule(char="─", width=None):
    print(char * (width or _LINE_WIDTH))


def section(title: str, width=None):
    print()
    rule(width=width)
    print(f"  {title}")
    rule(width=width)


def tbl_row(label: str, v1: str, v2: str):
    l  = label.ljust(_LABEL_WIDTH)
    c1 = trunc(v1, _COL_WIDTH).ljust(_COL_WIDTH)
    c2 = trunc(v2, _COL_WIDTH)
    print(f"  {l}  {c1}  {c2}")


def print_metadata_table(info1: dict, info2: dict):
    section("Metadata")
    print()
    tbl_row("", "FILE 1", "FILE 2")
    tbl_row("", "─" * 6, "─" * 6)
    tbl_row("Title",    info1["title"]  or "(none)", info2["title"]  or "(none)")
    tbl_row("Artist",   info1["artist"] or "(none)", info2["artist"] or "(none)")
    tbl_row("Album",    info1["album"]  or "(none)", info2["album"]  or "(none)")
    tbl_row("Duration", fmt_duration(info1["duration"]), fmt_duration(info2["duration"]))
    tbl_row("Bitrate",  fmt_bitrate(info1["bitrate"]),   fmt_bitrate(info2["bitrate"]))
    tbl_row("Size",     fmt_size(info1["size"]),          fmt_size(info2["size"]))
    tbl_row("Format",   info1["format"],                  info2["format"])
    aid1 = trunc(info1["acoustid_id"], 16) if info1["acoustid_id"] else "(none)"
    aid2 = trunc(info2["acoustid_id"], 16) if info2["acoustid_id"] else "(none)"
    tbl_row("AcoustID", aid1, aid2)
    print()


def print_verdict(score: "float | None", info1: dict, info2: dict,
                  short1: bool = False, short2: bool = False):
    """Print a plain-English verdict. Caveats score if either file is short."""
    section("Verdict")
    print()

    aid1 = info1["acoustid_id"].lower() if info1["acoustid_id"] else ""
    aid2 = info2["acoustid_id"].lower() if info2["acoustid_id"] else ""
    aid_match = bool(aid1 and aid2 and aid1 == aid2)

    # Short-file caveat — printed first so it frames everything that follows
    if short1 or short2:
        which = "File 1" if (short1 and not short2) else \
                "File 2" if (short2 and not short1) else "Both files"
        dur1_str = fmt_duration(info1["duration"]) if short1 else ""
        dur2_str = fmt_duration(info2["duration"]) if short2 else ""
        dur_str  = dur1_str or dur2_str
        print(f"  WARNING — SHORT FILE")
        print(f"  {which} is only {dur_str} long.")
        print(f"  Files under {FP_SHORT_FILE_SECONDS}s produce too few fingerprint data")
        print(f"  points for a reliable score. Treat the result below with caution.")
        print()

    if score is None:
        print("  FINGERPRINT UNAVAILABLE")
        print("  Could not compute similarity — fpcalc failed on one or both files.")
        if aid_match:
            print()
            print(f"  AcoustID tags MATCH ({aid1[:16]}...)")
            print("  Both files share the same AcoustID — same recording confirmed by tag.")
        elif aid1 and aid2:
            print()
            print("  AcoustID tags are DIFFERENT — these identify distinct recordings.")
        print()
        return

    score_str = f"{score:.1f}%"

    if short1 or short2:
        # Score exists but is not trustworthy — report it but don't make a firm call
        print(f"  Score : {score_str}  (unreliable — see short-file warning above)")
        print(f"  Cannot draw a confident conclusion from this score.")
    elif score >= 95:
        print(f"  SAME RECORDING  ({score_str} similarity)")
        print(f"  Very high confidence — this is almost certainly identical audio.")
    elif score >= FP_SIMILARITY_THRESHOLD:
        print(f"  SAME RECORDING  ({score_str} similarity)")
        print(f"  Above the duplicate finder threshold ({FP_SIMILARITY_THRESHOLD:.0f}%).")
        print(f"  A duplicate scan would flag these as the same track.")
    elif score >= NEAR_MISS_LOW_THRESHOLD:
        print(f"  NEAR MISS — below threshold  ({score_str} similarity)")
        print(f"  In the near-miss zone ({NEAR_MISS_LOW_THRESHOLD:.0f}–{FP_SIMILARITY_THRESHOLD:.0f}%).")
        print(f"  The duplicate finder would NOT automatically match these.")
        print(f"  Possible causes: different mastering, encoding, or version.")
    else:
        print(f"  DIFFERENT RECORDINGS  ({score_str} similarity)")
        print(f"  These files do not sound alike.")
        print(f"  The duplicate finder match was almost certainly a false positive.")

    # Quality comparison (only meaningful if not a short-file situation)
    if not (short1 or short2):
        br1 = info1["bitrate"] or 0
        br2 = info2["bitrate"] or 0
        if br1 and br2 and br1 != br2:
            print()
            if br1 > br2:
                print(f"  File 1 is higher quality: {fmt_bitrate(info1['bitrate'])} vs {fmt_bitrate(info2['bitrate'])}")
                if score >= FP_SIMILARITY_THRESHOLD:
                    print(f"  If keeping one, keep File 1 and discard File 2.")
            else:
                print(f"  File 2 is higher quality: {fmt_bitrate(info2['bitrate'])} vs {fmt_bitrate(info1['bitrate'])}")
                if score >= FP_SIMILARITY_THRESHOLD:
                    print(f"  If keeping one, keep File 2 and discard File 1.")
        elif br1 and br1 == br2:
            print()
            print(f"  Both files have the same bitrate ({fmt_bitrate(info1['bitrate'])}).")

    # AcoustID confirmation
    print()
    if aid_match:
        print(f"  AcoustID tags MATCH ({aid1[:16]}...)")
        print(f"  Tag confirms same recording regardless of fingerprint score.")
    elif aid1 and aid2:
        print(f"  AcoustID tags are DIFFERENT — these identify distinct recordings.")
    elif aid1 or aid2:
        print(f"  AcoustID: only one file has a tag — cannot confirm via tag comparison.")
    else:
        print(f"  AcoustID: neither file has a tag — fingerprint score is the only signal.")
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  FOLDER SCAN MODE — OUTPUT AND CSV
# ══════════════════════════════════════════════════════════════════════════════

_SCAN_LINE_WIDTH = 90


def print_scan_results(matches: list):
    """Print the scored results table for folder scan mode."""
    W       = _SCAN_LINE_WIDTH
    fn_w    = 30
    has_any_short = any(m["short_a"] or m["short_b"] for m in matches)

    section("Results — best match per file in Folder A", width=W)
    print()

    # Header
    flag_col = "    " if has_any_short else ""
    print(f"  {flag_col} Score    Verdict            {'File A':<{fn_w}}  Best match in B")
    print(f"  {flag_col} {'─'*7}  {'─'*17}  {'─'*fn_w}  {'─'*30}")

    for m in matches:
        info_a  = m["info_a"]
        info_b  = m["info_b"]
        score   = m["score"]
        fp_ok   = m["fp_ok_a"] and m["fp_ok_b"]
        short   = m["short_a"] or m["short_b"]

        score_str = f"{score:5.1f}%"  if fp_ok else "  N/A  "
        verdict   = verdict_label(score, fp_ok)
        fn_a      = trunc(info_a["path"].name, fn_w)
        fn_b      = trunc(info_b["path"].name, 30) if info_b else "(no match)"

        if has_any_short:
            flag = "[!]" if short else "   "
            print(f"  {flag}  {score_str}   {verdict:<17}  {fn_a:<{fn_w}}  {fn_b}")
        else:
            print(f"  {score_str}   {verdict:<17}  {fn_a:<{fn_w}}  {fn_b}")

    if has_any_short:
        print()
        print("  [!] = file under 30s — fingerprint score is unreliable, ignore the verdict")
    print()


def write_scan_csv(matches: list, csv_path: Path):
    """Save folder scan results to a CSV report."""
    fieldnames = [
        "Score (%)", "Verdict",
        "File A — Filename", "File A — Full Path",
        "File A — Artist",   "File A — Title",
        "File A — Duration", "File A — Bitrate",
        "File B — Filename", "File B — Full Path",
        "File B — Artist",   "File B — Title",
        "File B — Duration", "File B — Bitrate",
        "AcoustID Match",    "Notes",
    ]
    rows = []
    for m in matches:
        a       = m["info_a"]
        b       = m["info_b"]
        score   = m["score"]
        fp_ok   = m["fp_ok_a"] and m["fp_ok_b"]
        verdict = verdict_label(score, fp_ok)

        aid_a  = a["acoustid_id"].lower() if a["acoustid_id"] else ""
        aid_b  = (b["acoustid_id"].lower() if b and b["acoustid_id"] else "") if b else ""
        aid_match = "Yes" if (aid_a and aid_b and aid_a == aid_b) else ""

        # Build notes — short-file warning takes priority
        notes_parts = []
        if m["short_a"]:
            notes_parts.append(f"File A is {fmt_duration(a['duration'])} — under {FP_SHORT_FILE_SECONDS}s, score unreliable")
        if m["short_b"] and b:
            notes_parts.append(f"File B is {fmt_duration(b['duration'])} — under {FP_SHORT_FILE_SECONDS}s, score unreliable")
        if not m["fp_ok_a"]:
            notes_parts.append("File A fingerprint failed")
        elif not m["fp_ok_b"]:
            notes_parts.append("No valid fingerprint in Folder B")
        notes = "; ".join(notes_parts)

        rows.append({
            "Score (%)":         f"{score:.1f}" if fp_ok else "",
            "Verdict":           verdict,
            "File A — Filename": a["path"].name,
            "File A — Full Path":str(a["path"]),
            "File A — Artist":   a["artist"],
            "File A — Title":    a["title"],
            "File A — Duration": fmt_duration(a["duration"]),
            "File A — Bitrate":  fmt_bitrate(a["bitrate"]),
            "File B — Filename": b["path"].name if b else "",
            "File B — Full Path":str(b["path"]) if b else "",
            "File B — Artist":   b["artist"]   if b else "",
            "File B — Title":    b["title"]    if b else "",
            "File B — Duration": fmt_duration(b["duration"]) if b else "",
            "File B — Bitrate":  fmt_bitrate(b["bitrate"])   if b else "",
            "AcoustID Match":    aid_match,
            "Notes":             notes,
        })

    REPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_scan_summary(matches: list, csv_path: Path):
    W = _SCAN_LINE_WIDTH
    rule(width=W)
    print("  Summary")
    rule(width=W)

    same   = sum(1 for m in matches if m["fp_ok_a"] and m["fp_ok_b"] and not m["short_a"] and not m["short_b"] and m["score"] >= FP_SIMILARITY_THRESHOLD)
    near   = sum(1 for m in matches if m["fp_ok_a"] and m["fp_ok_b"] and not m["short_a"] and not m["short_b"] and NEAR_MISS_LOW_THRESHOLD <= m["score"] < FP_SIMILARITY_THRESHOLD)
    diff   = sum(1 for m in matches if m["fp_ok_a"] and m["fp_ok_b"] and not m["short_a"] and not m["short_b"] and m["score"] < NEAR_MISS_LOW_THRESHOLD)
    short  = sum(1 for m in matches if m["short_a"] or m["short_b"])
    no_fp  = sum(1 for m in matches if not m["fp_ok_a"] or not m["fp_ok_b"])

    print(f"  Same recording  (≥{FP_SIMILARITY_THRESHOLD:.0f}%) : {same}")
    print(f"  Near miss       ({NEAR_MISS_LOW_THRESHOLD:.0f}–{FP_SIMILARITY_THRESHOLD:.0f}%)  : {near}")
    print(f"  Different       (<{NEAR_MISS_LOW_THRESHOLD:.0f}%)  : {diff}")
    if short:
        print(f"  Short file [!]  (<{FP_SHORT_FILE_SECONDS}s)   : {short}  (score unreliable — excluded from counts above)")
    if no_fp:
        print(f"  No fingerprint              : {no_fp}")
    print()
    print(f"  CSV saved to: {csv_path}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  CHECK FPCALC
# ══════════════════════════════════════════════════════════════════════════════

def check_fpcalc() -> bool:
    if _fpcalc_local.exists():
        return True
    try:
        subprocess.run(["fpcalc", "-version"], capture_output=True, timeout=5)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return True


# ══════════════════════════════════════════════════════════════════════════════
#  FOLDER SCAN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def run_folder_scan(folder_a: Path, folder_b: Path,
                    progress_callback=None, log_callback=None):
    W = _SCAN_LINE_WIDTH
    print()
    print("=" * W)
    print("  compare_audio.py  v1.3  \u2014  Folder Scan")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * W)

    for folder, label in [(folder_a, "Folder A"), (folder_b, "Folder B")]:
        if not folder.exists() or not folder.is_dir():
            raise ValueError(f"{label} not found: {folder}")

    files_a = scan_folder_audio(folder_a)
    files_b = scan_folder_audio(folder_b)

    print()
    print(f"  Folder A : {folder_a}")
    print(f"             {len(files_a)} audio file{'s' if len(files_a) != 1 else ''} found")
    print(f"  Folder B : {folder_b}")
    print(f"             {len(files_b)} audio file{'s' if len(files_b) != 1 else ''} found")

    if not files_a:
        print("\n  ERROR: No supported audio files found in Folder A.")
        sys.exit(1)
    if not files_b:
        print("\n  ERROR: No supported audio files found in Folder B.")
        sys.exit(1)

    if not check_fpcalc():
        print(f"\n  ERROR: fpcalc.exe not found.")
        print(f"  Expected: {_fpcalc_local}")
        print(f"  Download from https://acoustid.org/chromaprint")
        sys.exit(1)

    print(f"\n  Using fpcalc : {FPCALC_PATH}")

    # Warn about short files before fingerprinting starts
    short_a_files = [f for f in files_a if is_short_file(f.get("duration"))]
    if short_a_files:
        print(f"\n  NOTE: {len(short_a_files)} file(s) in Folder A are under {FP_SHORT_FILE_SECONDS}s "
              f"— their scores will be marked [!] and are not reliable:")
        for f in short_a_files:
            print(f"    {f['path'].name}  ({fmt_duration(f['duration'])})")

    print()
    fp_a = fingerprint_batch(files_a, "Folder A")
    fp_b = fingerprint_batch(files_b, "Folder B")

    matches = find_best_matches(files_a, fp_a, fp_b, files_b)

    print_scan_results(matches)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path  = REPORTS_FOLDER / f"compare_audio_{timestamp}.csv"
    write_scan_csv(matches, csv_path)

    print_scan_summary(matches, csv_path)
    print("=" * W)
    print()

    return {
        "matches":     matches,
        "csv_path":    str(csv_path),
        "report_path": str(csv_path),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  TWO-FILE ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def run_file_compare(file1: Path, file2: Path,
                     progress_callback=None, log_callback=None):
    print()
    print("=" * _LINE_WIDTH)
    print("  compare_audio.py  v1.3  \u2014  Audio File Comparison")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * _LINE_WIDTH)

    for f, label in [(file1, "File 1"), (file2, "File 2")]:
        if not f.exists():
            raise ValueError(f"{label} not found: {f}")
        if not f.is_file():
            raise ValueError(f"{label} is not a file: {f}")

    print()
    print(f"  File 1 : {file1.name}")
    print(f"           {file1.parent}")
    print(f"  File 2 : {file2.name}")
    print(f"           {file2.parent}")

    print()
    print("  Reading metadata...", end="", flush=True)
    info1 = read_file_info(file1)
    info2 = read_file_info(file2)
    print("  done")

    if info1.get("error"):
        print(f"  WARNING: Could not read all tags from File 1 — {info1['error']}")
    if info2.get("error"):
        print(f"  WARNING: Could not read all tags from File 2 — {info2['error']}")

    # Warn about short files early — before the metadata table so it's seen first
    note1 = short_file_note(info1, "File 1")
    note2 = short_file_note(info2, "File 2")
    if note1 or note2:
        print()
        print("  NOTE — SHORT FILE DETECTED:")
        if note1:
            print(f"  ! {note1}")
        if note2:
            print(f"  ! {note2}")

    print_metadata_table(info1, info2)

    section("Audio Fingerprint")
    print()

    if not check_fpcalc():
        print("  ERROR: fpcalc.exe not found.")
        print(f"  Expected: {_fpcalc_local}")
        print(f"  Download from https://acoustid.org/chromaprint and place in: {SCRIPT_DIR}")
        print()
        print_verdict(None, info1, info2,
                      short1=is_short_file(info1.get("duration")),
                      short2=is_short_file(info2.get("duration")))
        print("=" * _LINE_WIDTH)
        return

    print(f"  Using : {FPCALC_PATH}")
    print()

    print("  File 1 : computing...", end="", flush=True)
    t1 = time.perf_counter()
    fp1, fp1_dur = get_fingerprint(file1)
    t1 = time.perf_counter() - t1
    if fp1 and is_valid_fingerprint(fp1):
        print(f"  done  ({t1:.1f}s, {len(fp1.split(','))} points)")
    elif fp1:
        print(f"  WARNING: short fingerprint ({len(fp1.split(','))} points — may be unreliable)")
    else:
        print("  FAILED")

    print("  File 2 : computing...", end="", flush=True)
    t2 = time.perf_counter()
    fp2, fp2_dur = get_fingerprint(file2)
    t2 = time.perf_counter() - t2
    if fp2 and is_valid_fingerprint(fp2):
        print(f"  done  ({t2:.1f}s, {len(fp2.split(','))} points)")
    elif fp2:
        print(f"  WARNING: short fingerprint ({len(fp2.split(','))} points — may be unreliable)")
    else:
        print("  FAILED")

    print()

    # Use fpcalc duration if available (more accurate), fall back to mutagen
    dur1 = fp1_dur if fp1_dur is not None else info1.get("duration")
    dur2 = fp2_dur if fp2_dur is not None else info2.get("duration")
    short1 = is_short_file(dur1)
    short2 = is_short_file(dur2)

    if fp1 and fp2:
        score      = fingerprint_similarity(fp1, fp2)
        bar_filled = round(score / 100 * 30)
        bar        = "█" * bar_filled + "░" * (30 - bar_filled)

        if short1 or short2:
            tier = "UNRELIABLE — short file"
        elif score >= 95:
            tier = "very high confidence"
        elif score >= FP_SIMILARITY_THRESHOLD:
            tier = "above threshold"
        elif score >= NEAR_MISS_LOW_THRESHOLD:
            tier = "near-miss zone"
        else:
            tier = "below near-miss zone"

        print(f"  Similarity : {score:.1f}%  [{bar}]  {tier}")

        if fp1_dur is not None and fp2_dur is not None:
            dur_diff = abs(fp1_dur - fp2_dur)
            print(f"  Duration   : {fmt_duration(fp1_dur)} / {fmt_duration(fp2_dur)}"
                  f"  (difference: {dur_diff:.1f}s)")

        if not (short1 or short2):
            print()
            print(f"  Threshold reference:")
            print(f"    {FP_SIMILARITY_THRESHOLD:.0f}%  — duplicate finder match threshold")
            print(f"    {NEAR_MISS_LOW_THRESHOLD:.0f}%  — near-miss zone lower bound")
    else:
        score  = None
        short1 = is_short_file(info1.get("duration"))
        short2 = is_short_file(info2.get("duration"))
        if not fp1:
            print("  File 1 : fingerprint failed — check the file is not corrupted.")
        if not fp2:
            print("  File 2 : fingerprint failed — check the file is not corrupted.")

    print_verdict(score, info1, info2, short1=short1, short2=short2)
    print("=" * _LINE_WIDTH)
    print()

    return {
        "score":       score,
        "file1":       str(file1),
        "file2":       str(file2),
        "report_path": None,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  GUI-CALLABLE CORE
# ══════════════════════════════════════════════════════════════════════════════

def run_compare_audio(
    mode,                  # "file" | "folder"
    file1=None,
    file2=None,
    folder_a=None,
    folder_b=None,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    GUI-callable entry point for compare_audio.

    Parameters
    ----------
    mode : str
        "file"   -- compare two individual audio files.
        "folder" -- find the best match per file across two folders.
    file1, file2 : str | Path | None
        Required for mode="file". Raises ValueError if missing or not found.
    folder_a, folder_b : str | Path | None
        Required for mode="folder". Raises ValueError if missing or not found.
    progress_callback : callable | None
        Called as progress_callback(current, total, filename).
    log_callback : callable | None
        Called as log_callback(message) for each output line.

    Returns
    -------
    dict with report_path (str | None) plus mode-specific keys.

    Raises
    ------
    ValueError
        If required paths are missing, not found, or mode is invalid.
    """
    if mode == "folder":
        if not folder_a or not folder_b:
            raise ValueError("folder_a and folder_b are both required for folder mode")
        return run_folder_scan(
            Path(folder_a), Path(folder_b),
            progress_callback=progress_callback,
            log_callback=log_callback,
        )
    elif mode == "file":
        if not file1 or not file2:
            raise ValueError("file1 and file2 are both required for file mode")
        return run_file_compare(
            Path(file1), Path(file2),
            progress_callback=progress_callback,
            log_callback=log_callback,
        )
    else:
        raise ValueError(f"Unknown mode: {mode!r}. Expected \'file\' or \'folder\'.")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN — DISPATCH
# ══════════════════════════════════════════════════════════════════════════════

def main():
    PICK_FILES   = "--pick"         in sys.argv
    PICK_FOLDERS = "--pick-folders" in sys.argv
    _file1_flag   = _flag_val("--file1")
    _file2_flag   = _flag_val("--file2")
    _folder1_flag = _flag_val("--folder1")
    _folder2_flag = _flag_val("--folder2")

    # ── Folder scan mode ──────────────────────────────────────────────────────
    if PICK_FOLDERS or _folder1_flag or _folder2_flag:
        if PICK_FOLDERS:
            print("\n  Pick Folder A (e.g. your library copies)...")
            folder_a = pick_folder("Select Folder A — e.g. library copies")
            if not folder_a:
                print("  No folder selected. Exiting.")
                sys.exit(0)
            print(f"  Selected : {folder_a}")

            print("\n  Pick Folder B (e.g. unsorted / new downloads)...")
            folder_b = pick_folder("Select Folder B — e.g. unsorted copies")
            if not folder_b:
                print("  No folder selected. Exiting.")
                sys.exit(0)
            print(f"  Selected : {folder_b}")

        elif _folder1_flag and _folder2_flag:
            folder_a = Path(_folder1_flag.strip('"'))
            folder_b = Path(_folder2_flag.strip('"'))

        else:
            print("\n  ERROR: Both --folder1 and --folder2 must be supplied together.")
            print("\n  Usage:")
            print("    python compare_audio.py --pick-folders")
            print('    python compare_audio.py --folder1 "C:\\Library" --folder2 "C:\\Unsorted"')
            sys.exit(1)

        try:
            run_folder_scan(folder_a, folder_b)
        except ValueError as exc:
            print(f"\n  ERROR: {exc}")
            sys.exit(1)
        return

    # ── Two-file mode ─────────────────────────────────────────────────────────
    if PICK_FILES:
        print("\n  Pick File 1 (e.g. from your library)...")
        file1 = pick_file("Select File 1 — e.g. the library copy")
        if not file1:
            print("  No file selected. Exiting.")
            sys.exit(0)
        print(f"  Selected : {file1.name}")

        print("\n  Pick File 2 (e.g. from unsorted / new downloads)...")
        file2 = pick_file("Select File 2 — e.g. the unsorted copy")
        if not file2:
            print("  No file selected. Exiting.")
            sys.exit(0)
        print(f"  Selected : {file2.name}")

        try:
            run_file_compare(file1, file2)
        except ValueError as exc:
            print(f"\n  ERROR: {exc}")
            sys.exit(1)
        return

    if _file1_flag and _file2_flag:
        try:
            run_file_compare(
                Path(_file1_flag.strip('"')),
                Path(_file2_flag.strip('"')),
            )
        except ValueError as exc:
            print(f"\n  ERROR: {exc}")
            sys.exit(1)
        return

    # ── No valid mode ─────────────────────────────────────────────────────────
    print()
    print("  compare_audio.py  v1.3  \u2014  Audio File Comparison")
    print()
    print("  ERROR: No mode specified.")
    print()
    print("  Two-file mode:")
    print("    python compare_audio.py --pick")
    print('    python compare_audio.py --file1 "path\\a.mp3" --file2 "path\\b.mp3"')
    print()
    print("  Folder scan mode (best match per file):")
    print("    python compare_audio.py --pick-folders")
    print('    python compare_audio.py --folder1 "C:\\Library" --folder2 "C:\\Unsorted"')
    print()
    sys.exit(1)


if __name__ == "__main__":
    main()
