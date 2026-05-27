"""
Fix Featuring Tags  v1.5
=========================
Moves featuring credits from the Artist tag to the Title tag.

  Before:  Artist = "Above & Beyond feat. Zoë Johnston"
           Title  = "Sun & Moon"
  After:   Artist = "Above & Beyond"
           Title  = "Sun & Moon (feat. Zoë Johnston)"

If the title already contains the featuring credit, only the Artist tag
is cleaned — the credit is not added to the title a second time.

Handles variants: feat., ft., featuring (with or without brackets).
Only the Artist tag is modified — Album Artist is left untouched.

Supports: MP3, FLAC, AAC/M4A

Requirements:
    pip install mutagen

Usage:
    python fix_featuring.py                       # dry run, opens folder picker
    python fix_featuring.py --apply               # full scan + apply, opens folder picker
    python fix_featuring.py --from-csv            # apply from dry-run CSV (opens file picker)
    python fix_featuring.py --from-csv --apply    # same as above (--apply implied)

Output:
    Reports saved to: <script folder>\\reports\\fix_featuring_YYYYMMDD_HHMMSS.csv
"""

import sys
import re
import csv
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import (
    SUPPORTED_EXTENSIONS,
    pick_folder,
    write_csv,
    interactive_options,
)

try:
    from mutagen import File as MutagenFile
    MUTAGEN_AVAILABLE = True
except ImportError:
    MutagenFile = None
    MUTAGEN_AVAILABLE = False
    print("ERROR: mutagen is required. Run: pip install mutagen")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent

# ── Unicode normalization ──────────────────────────────────────────────────────
_UNICODE_MAP = str.maketrans({
    "․": ".",   "‥": "..",  "．": ".",
    "‐": "-",   "‑": "-",   "‒": "-",   "–": "-",
    "’": "'",   "‘": "'",
})

def normalize_text(s):
    return s.translate(_UNICODE_MAP)

_FEAT_RE = re.compile(
    r'\s*([\(\[]?)\s*(?:feat(?:uring)?\.?|ft\.)\s+([^\)\]]+?)([\)\]]?)\s*$',
    re.IGNORECASE
)
_TITLE_FEAT_RE = re.compile(r'(?:feat(?:uring)?\.?|ft\.)', re.IGNORECASE)

FIELDNAMES = [
    "file_path",
    "original_artist", "new_artist",
    "original_title",  "new_title",
    "status", "notes",
]


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def extract_featuring(artist):
    artist_norm = normalize_text(artist)
    m = _FEAT_RE.search(artist_norm)
    if not m:
        return artist, None
    clean       = artist_norm[:m.start()].strip().rstrip(",;&").strip()
    feat_name   = m.group(2).strip().rstrip(")].").strip()
    return clean, "feat. %s" % feat_name


def build_new_title(title, feat_string):
    if _TITLE_FEAT_RE.search(title):
        return None
    return "%s (%s)" % (title, feat_string)


def get_artist_title(audio_easy):
    artist = (audio_easy.get("artist", [None])[0] or "").strip()
    title  = (audio_easy.get("title",  [None])[0] or "").strip()
    return artist or None, title or None


def set_artist_title(audio_easy, artist, title):
    audio_easy["artist"] = [artist]
    audio_easy["title"]  = [title]
    audio_easy.save()


def _row(file_path, orig_artist, new_artist, orig_title, new_title, status, notes):
    return {
        "file_path":       str(file_path),
        "original_artist": orig_artist or "",
        "new_artist":      new_artist  or "",
        "original_title":  orig_title  or "",
        "new_title":       new_title   or "",
        "status":          status,
        "notes":           notes,
    }


def process_file(file_path, apply_mode):
    try:
        audio = MutagenFile(str(file_path), easy=True)
        if audio is None:
            return _row(file_path, None, None, None, None,
                        "skipped", "Unrecognised file format")
        orig_artist, orig_title = get_artist_title(audio)
        if not orig_artist:
            return _row(file_path, orig_artist, None, orig_title, None,
                        "skipped", "No artist tag")
        clean_artist, feat_string = extract_featuring(orig_artist)
        if feat_string is None:
            return _row(file_path, orig_artist, None, orig_title, None,
                        "no_featuring", "No featuring credit found")
        new_title = build_new_title(orig_title, feat_string) if orig_title else None
        notes_parts = ["artist cleaned"]
        if new_title:
            notes_parts.append("feat. appended to title")
        elif orig_title and _TITLE_FEAT_RE.search(orig_title):
            notes_parts.append("title already has feat. — not modified")
        else:
            notes_parts.append("no title tag — artist only")
        if apply_mode:
            final_title = new_title if new_title else orig_title
            set_artist_title(audio, clean_artist, final_title if final_title else "")
            status = "modified"
        else:
            status = "pending"
        return _row(file_path, orig_artist, clean_artist,
                    orig_title, new_title if new_title else orig_title,
                    status, "; ".join(notes_parts))
    except Exception as e:
        return _row(file_path, None, None, None, None,
                    "error", "Exception: %s" % e)


def find_audio_files(root_path):
    return sorted(
        p for p in Path(root_path).rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def print_summary(rows, apply_mode, output_path, log=print):
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    log("=" * 60)
    log("  SUMMARY  (%s)" % ("APPLY" if apply_mode else "DRY RUN"))
    log("=" * 60)
    if apply_mode:
        log("  Modified           : %d" % counts.get("modified", 0))
    else:
        log("  Would modify       : %d" % counts.get("pending", 0))
    log("  No featuring found : %d" % counts.get("no_featuring", 0))
    log("  Skipped            : %d" % counts.get("skipped", 0))
    log("  Errors             : %d" % counts.get("error", 0))
    log("  Report: %s" % output_path)
    log("=" * 60)


def load_pending_rows(csv_path):
    rows = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("status", "").strip() == "pending":
                rows.append(row)
    return rows


def _pick_csv_file():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askopenfilename(
            title="Select dry-run CSV report to apply",
            initialdir=str(SCRIPT_DIR / "reports"),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        root.destroy()
        return chosen or None
    except Exception as e:
        print("ERROR: Could not open file picker: %s" % e)
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_fix_featuring(
    folder: Path,
    apply: bool = False,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Scan folder and move featuring credits from Artist tag to Title tag.

    Args:
        folder:            Root folder to scan recursively.
        apply:             False = dry run; True = write tags.
        progress_callback: Optional callable(current, total, message).
        log_callback:      Optional callable(message). Defaults to print().

    Returns:
        dict: modified, pending, no_featuring, skipped, errors,
              results (list of row dicts), report_path (Path|None)

    Raises:
        ValueError: folder does not exist or is not a directory.
    """
    log = log_callback or print

    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    files = find_audio_files(folder)
    if not files:
        log(f"  No audio files found in: {folder}")
        return {"modified": 0, "pending": 0, "no_featuring": 0,
                "skipped": 0, "errors": 0, "results": [], "report_path": None}

    log(f"  Found {len(files)} audio file(s) to scan.")
    rows = []

    for idx, f in enumerate(files):
        if progress_callback:
            progress_callback(idx + 1, len(files), f.name)
        row = process_file(f, apply_mode=apply)
        rows.append(row)
        if row["status"] in ("pending", "modified"):
            log(f"  [{idx+1}/{len(files)}]  {f.name}")
            log(f"          Artist : {row['original_artist']} → {row['new_artist']}")
            if row["new_title"] != row["original_title"]:
                log(f"          Title  : {row['original_title']} → {row['new_title']}")

    reports_dir = SCRIPT_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "applied" if apply else "dry"
    report_path = reports_dir / f"fix_featuring_{ts}_{suffix}.csv"
    write_csv(rows, str(report_path), fieldnames=FIELDNAMES)
    log(f"  Report saved: {report_path}")

    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    return {
        "modified":     counts.get("modified", 0),
        "pending":      counts.get("pending", 0),
        "no_featuring": counts.get("no_featuring", 0),
        "skipped":      counts.get("skipped", 0),
        "errors":       counts.get("error", 0),
        "results":      rows,
        "report_path":  report_path,
    }


def run_fix_featuring_from_csv(
    csv_path: Path,
    log_callback=None,
) -> dict:
    """
    Apply tag changes from a previous dry-run CSV. GUI or CLI can call this.

    Raises:
        ValueError: csv_path does not exist.
    """
    log = log_callback or print

    if not csv_path.exists():
        raise ValueError(f"CSV not found: {csv_path}")

    pending = load_pending_rows(csv_path)
    if not pending:
        log("  No pending rows found in the CSV. Nothing to apply.")
        return {"modified": 0, "skipped": 0, "errors": 0,
                "results": [], "report_path": None}

    log(f"  {len(pending)} pending change(s) loaded from CSV.")
    results  = []
    modified = skipped = warnings = errors = 0

    for idx, csv_row in enumerate(pending, 1):
        file_path  = Path(csv_row.get("file_path", "").strip())
        new_artist = csv_row.get("new_artist",  "").strip()
        new_title  = csv_row.get("new_title",   "").strip()
        dry_artist = csv_row.get("original_artist", "").strip()

        if not file_path.exists():
            log(f"  [{idx}/{len(pending)}]  MISSING  {file_path.name}")
            results.append(_row(file_path, dry_artist, new_artist,
                                csv_row.get("original_title", ""), new_title,
                                "skipped", "File not found"))
            skipped += 1
            continue
        try:
            audio = MutagenFile(str(file_path), easy=True)
            if audio is None:
                raise ValueError("Unrecognised file format")
            current_artist, current_title = get_artist_title(audio)
            if normalize_text(current_artist or "") != normalize_text(dry_artist):
                log(f"  [{idx}/{len(pending)}]  WARNING  {file_path.name} — artist changed since dry run, skipping")
                results.append(_row(file_path, current_artist, new_artist,
                                    current_title, new_title, "skipped",
                                    "Artist changed since dry run"))
                skipped += 1
                warnings += 1
                continue
            set_artist_title(audio, new_artist, new_title)
            log(f"  [{idx}/{len(pending)}]  {file_path.name} — {dry_artist} → {new_artist}")
            results.append(_row(file_path, dry_artist, new_artist,
                                csv_row.get("original_title", ""), new_title,
                                "modified", csv_row.get("notes", "")))
            modified += 1
        except Exception as e:
            log(f"  [{idx}/{len(pending)}]  ERROR  {file_path.name} — {e}")
            results.append(_row(file_path, dry_artist, new_artist,
                                csv_row.get("original_title", ""), new_title,
                                "error", f"Exception: {e}"))
            errors += 1

    log(f"  Done. Modified: {modified}  |  Skipped: {skipped}  |  Errors: {errors}")
    if warnings:
        log(f"  NOTE: {warnings} file(s) had artist tags that changed since the dry run.")

    reports_dir = SCRIPT_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"fix_featuring_{ts}_applied.csv"
    write_csv(results, str(report_path), fieldnames=FIELDNAMES)
    log(f"  Report saved: {report_path}")

    return {"modified": modified, "skipped": skipped, "errors": errors,
            "results": results, "report_path": report_path}


# ══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT  ← .cmd launchers call this; GUI does not
# ══════════════════════════════════════════════════════════════════════════════

def main():
    interactive_options([])

    flags      = [a for a in sys.argv[1:] if a.startswith("--")]
    apply_mode = "--apply"    in flags
    from_csv   = "--from-csv" in flags

    print()
    print("=" * 60)
    print("  Fix Featuring Tags  v1.5")
    print("=" * 60)

    # ── --from-csv mode ────────────────────────────────────────────────────────
    if from_csv:
        chosen = _pick_csv_file()
        if not chosen:
            print("No CSV file selected. Exiting.")
            sys.exit(0)
        print(f"  Mode   : APPLY FROM CSV")
        print(f"  Source : {Path(chosen).name}")
        print("=" * 60)
        confirm = input("\n  Apply changes from this CSV? (y/n): ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            sys.exit(0)
        try:
            run_fix_featuring_from_csv(Path(chosen))
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
        return

    # ── Standard folder scan mode ──────────────────────────────────────────────
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        folder = Path(args[0].strip('"'))
    else:
        folder = pick_folder("Select folder to scan for featuring tags")
        if not folder:
            print("No folder selected. Exiting.")
            sys.exit(0)

    print(f"  Folder : {folder}")
    print(f"  Mode   : {'APPLY — writing tags' if apply_mode else 'DRY RUN — no changes made'}")
    print("=" * 60)

    if apply_mode:
        confirm = input("\n  Proceed with modifying tags? (y/n): ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            sys.exit(0)

    try:
        result = run_fix_featuring(folder, apply=apply_mode)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print_summary(result["results"], apply_mode, result["report_path"])


if __name__ == "__main__":
    main()
