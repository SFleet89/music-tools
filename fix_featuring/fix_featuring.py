"""
Fix Featuring Tags  v1.2
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

Changes in v1.2:
    - Added --from-csv flag: applies changes from a dry-run CSV report without
      re-scanning the library. A file picker opens to select the CSV.
      Only 'pending' rows are processed — skipped, errors, no_featuring ignored.
      Each file's current tags are verified against the dry-run snapshot before
      writing. A warning is shown if a tag changed between the dry run and now.

Changes in v1.1:
    - Fixed: Unicode lookalike characters (One Dot Leader U+2024, non-breaking
      hyphens, etc.) in artist tags were invisible to the regex, causing all
      files to report no_featuring. Tags are now normalized to ASCII before
      matching and when writing back.
    - Fixed: Reports folder was saved to parent of script folder instead of
      inside script folder.

Changes in v1.0:
    - Initial release.
"""

import sys
import re
import csv
from pathlib import Path
from datetime import datetime

# ── Optional mutagen ───────────────────────────────────────────────────────────
try:
    from mutagen import File as MutagenFile
    MUTAGEN_AVAILABLE = True
except ImportError:
    MutagenFile = None
    MUTAGEN_AVAILABLE = False
    print("ERROR: mutagen is required. Run: pip install mutagen")
    sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".aac", ".m4a"}
SCRIPT_DIR           = Path(__file__).parent

# ── Unicode normalization ──────────────────────────────────────────────────────
# Some tagging tools write visually identical but technically different characters.
# These must be normalized to ASCII before regex matching and before writing back.
_UNICODE_MAP = str.maketrans({
    "\u2024": ".",   # ONE DOT LEADER  ․  → .
    "\u2025": "..",  # TWO DOT LEADER  ‥  → ..
    "\uFF0E": ".",   # FULLWIDTH FULL STOP ．→ .
    "\u2010": "-",   # HYPHEN ‐ → -
    "\u2011": "-",   # NON-BREAKING HYPHEN ‑ → -
    "\u2012": "-",   # FIGURE DASH ‒ → -
    "\u2013": "-",   # EN DASH – → -
    "\u2019": "'",   # RIGHT SINGLE QUOTATION MARK ' → '
    "\u2018": "'",   # LEFT SINGLE QUOTATION MARK ' → '
})

def normalize_text(s):
    """Replace Unicode lookalike characters with their ASCII equivalents."""
    return s.translate(_UNICODE_MAP)


# Matches featuring credit anywhere in a string:
#   "Artist feat. Name"
#   "Artist (feat. Name)"
#   "Artist [ft. Name]"
#   "Artist featuring Name"
# Capture group 1 = opening bracket (or empty)
# Capture group 2 = the featuring name(s)
_FEAT_RE = re.compile(
    r'\s*([\(\[]?)\s*(?:feat(?:uring)?\.?|ft\.)\s+([^\)\]]+?)([\)\]]?)\s*$',
    re.IGNORECASE
)

# For detecting if title already has a featuring credit
_TITLE_FEAT_RE = re.compile(
    r'(?:feat(?:uring)?\.?|ft\.)',
    re.IGNORECASE
)


# ── Featuring extraction ───────────────────────────────────────────────────────

def extract_featuring(artist):
    """
    Parse a featuring credit from an artist string.
    Returns (clean_artist, feat_string) where feat_string is e.g. 'feat. Zoë Johnston'
    or (original, None) if no featuring found.
    """
    # Normalize Unicode lookalikes so the regex can match them
    artist_norm = normalize_text(artist)
    m = _FEAT_RE.search(artist_norm)
    if not m:
        return artist, None

    # Use match positions from the normalized string but apply to original
    clean       = artist_norm[:m.start()].strip().rstrip(",;&").strip()
    feat_name   = m.group(2).strip().rstrip(")].").strip()
    feat_string = "feat. %s" % feat_name

    return clean, feat_string


def build_new_title(title, feat_string):
    """
    Append feat_string to title if the title doesn't already contain it.
    Returns new title or None if no change needed.
    """
    if _TITLE_FEAT_RE.search(title):
        return None   # already has featuring info
    return "%s (%s)" % (title, feat_string)


# ── Tag reading/writing ────────────────────────────────────────────────────────

def get_artist_title(audio_easy):
    """Read artist and title from an easy-tag mutagen file."""
    artist = (audio_easy.get("artist", [None])[0] or "").strip()
    title  = (audio_easy.get("title",  [None])[0] or "").strip()
    return artist or None, title or None


def set_artist_title(audio_easy, artist, title):
    """Write artist and title back via easy tags."""
    audio_easy["artist"] = [artist]
    audio_easy["title"]  = [title]
    audio_easy.save()


# ── File processing ────────────────────────────────────────────────────────────

def process_file(file_path, apply_mode):
    """
    Process a single audio file. Returns a report row dict.
    """
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

        # Decide what to do with the title
        if orig_title:
            new_title = build_new_title(orig_title, feat_string)
        else:
            new_title = None   # no title to append to — still clean the artist

        notes_parts = ["artist cleaned"]
        if new_title:
            notes_parts.append("feat. appended to title")
        elif orig_title and _TITLE_FEAT_RE.search(orig_title):
            notes_parts.append("title already has feat. — not modified")
        else:
            notes_parts.append("no title tag — artist only")

        if apply_mode:
            final_title = new_title if new_title else orig_title
            set_artist_title(audio, clean_artist,
                             final_title if final_title else "")
            status = "modified"
        else:
            status = "pending"

        return _row(file_path,
                    orig_artist, clean_artist,
                    orig_title,  new_title if new_title else orig_title,
                    status, "; ".join(notes_parts))

    except Exception as e:
        return _row(file_path, None, None, None, None,
                    "error", "Exception: %s" % e)


def _row(file_path, orig_artist, new_artist, orig_title, new_title, status, notes):
    return {
        "file_path":     str(file_path),
        "original_artist": orig_artist or "",
        "new_artist":    new_artist   or "",
        "original_title": orig_title  or "",
        "new_title":     new_title    or "",
        "status":        status,
        "notes":         notes,
    }


# ── Folder scanning ────────────────────────────────────────────────────────────

def find_audio_files(root_path):
    """Recursively find all supported audio files under root_path."""
    results = []
    for p in sorted(Path(root_path).rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
            results.append(p)
    return results


# ── Main logic ─────────────────────────────────────────────────────────────────

def run(root_path, apply_mode):
    files = find_audio_files(root_path)
    total = len(files)

    if total == 0:
        print("  No audio files found in: %s" % root_path)
        return []

    print()
    print("  Found %d audio file(s) to process." % total)
    print()

    rows = []
    for idx, f in enumerate(files, 1):
        row = process_file(f, apply_mode)
        rows.append(row)

        if row["status"] in ("pending", "modified"):
            print("  [%d/%d]  %s" % (idx, total, f.name))
            print("          Artist : %s → %s" % (row["original_artist"],
                                                    row["new_artist"]))
            if row["new_title"] != row["original_title"]:
                print("          Title  : %s → %s" % (row["original_title"],
                                                        row["new_title"]))
            print("          %s" % row["notes"])

    return rows


# ── CSV output ─────────────────────────────────────────────────────────────────

FIELDNAMES = [
    "file_path",
    "original_artist", "new_artist",
    "original_title",  "new_title",
    "status", "notes",
]


def write_csv(rows, output_path):
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows, apply_mode, output_path):
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    print()
    print("=" * 60)
    print("  SUMMARY  (%s)" % ("APPLY" if apply_mode else "DRY RUN"))
    print("=" * 60)
    if apply_mode:
        print("  Modified           : %d" % counts.get("modified", 0))
    else:
        print("  Would modify       : %d" % counts.get("pending", 0))
    print("  No featuring found : %d" % counts.get("no_featuring", 0))
    print("  Skipped            : %d" % counts.get("skipped", 0))
    print("  Errors             : %d" % counts.get("error", 0))
    print()
    print("  Report saved to:")
    print("  %s" % output_path)
    print("=" * 60)


# ── CSV-driven apply ──────────────────────────────────────────────────────────

def load_pending_rows(csv_path):
    """Read a dry-run CSV and return only the rows with status 'pending'."""
    rows = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("status", "").strip() == "pending":
                rows.append(row)
    return rows


def run_from_csv(csv_path):
    """
    Apply tag changes from a dry-run CSV report.

    For each pending row:
      1. Verify the file still exists.
      2. Re-read the current artist tag and compare to the dry-run snapshot.
         If it has changed since the dry run, warn and skip — don't overwrite
         unexpected state.
      3. Write new_artist and new_title from the CSV directly to the file.

    Returns a list of result row dicts for the output report.
    """
    pending = load_pending_rows(csv_path)

    if not pending:
        print("  No pending rows found in the CSV. Nothing to apply.")
        return []

    print()
    print("  %d pending change(s) loaded from CSV." % len(pending))
    print()

    results   = []
    modified  = 0
    skipped   = 0
    warnings  = 0
    errors    = 0

    for idx, csv_row in enumerate(pending, 1):
        file_path   = Path(csv_row.get("file_path", "").strip())
        new_artist  = csv_row.get("new_artist",  "").strip()
        new_title   = csv_row.get("new_title",   "").strip()
        dry_artist  = csv_row.get("original_artist", "").strip()

        # ── File must still exist ──
        if not file_path.exists():
            print("  [%d/%d]  MISSING  %s" % (idx, len(pending), file_path.name))
            print("           File no longer exists — skipping.")
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
            current_artist_norm = normalize_text(current_artist or "")
            dry_artist_norm     = normalize_text(dry_artist)

            # ── Warn if the artist tag changed since the dry run ──
            if current_artist_norm != dry_artist_norm:
                print("  [%d/%d]  WARNING  %s" % (idx, len(pending), file_path.name))
                print("           Artist tag changed since dry run:")
                print("           Dry run : %s" % dry_artist)
                print("           Current : %s" % (current_artist or "(empty)"))
                print("           Skipping to avoid overwriting unexpected state.")
                results.append(_row(file_path, current_artist, new_artist,
                                    current_title, new_title,
                                    "skipped",
                                    "Artist changed since dry run — not modified"))
                skipped  += 1
                warnings += 1
                continue

            # ── Write the tags ──
            set_artist_title(audio, new_artist, new_title)

            print("  [%d/%d]  %s" % (idx, len(pending), file_path.name))
            print("          Artist : %s → %s" % (dry_artist, new_artist))
            if new_title != csv_row.get("original_title", ""):
                print("          Title  : %s → %s" % (
                    csv_row.get("original_title", ""), new_title))

            results.append(_row(file_path, dry_artist, new_artist,
                                csv_row.get("original_title", ""), new_title,
                                "modified", csv_row.get("notes", "")))
            modified += 1

        except Exception as e:
            print("  [%d/%d]  ERROR    %s — %s" % (idx, len(pending), file_path.name, e))
            results.append(_row(file_path, dry_artist, new_artist,
                                csv_row.get("original_title", ""), new_title,
                                "error", "Exception: %s" % e))
            errors += 1

    print()
    print("  Done.  Modified: %d  |  Skipped: %d  |  Errors: %d" % (
        modified, skipped, errors))
    if warnings:
        print("  NOTE: %d file(s) had artist tags that changed since the dry run "
              "and were skipped." % warnings)

    return results


# ── Entry point ────────────────────────────────────────────────────────────────

def pick_folder():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(
            title="Select folder to scan for featuring tags",
            initialdir=r"C:\Users\neo_s\Downloads\To Move\Music",
        )
        root.destroy()
        return chosen or None
    except Exception as e:
        print("ERROR: Could not open folder picker: %s" % e)
        return None


def pick_csv_file():
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


def main():
    args       = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags      = [a for a in sys.argv[1:] if a.startswith("--")]
    apply_mode = "--apply"    in flags
    from_csv   = "--from-csv" in flags

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports_dir = SCRIPT_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)

    # ── --from-csv mode: apply from a previous dry-run report ──
    if from_csv:
        chosen = pick_csv_file()
        if not chosen:
            print("No CSV file selected. Exiting.")
            sys.exit(0)

        csv_path = Path(chosen)
        if not csv_path.exists():
            print("ERROR: File not found: %s" % csv_path)
            sys.exit(1)

        output_path = reports_dir / ("fix_featuring_%s_applied.csv" % timestamp)

        print()
        print("=" * 60)
        print("  Fix Featuring Tags  v1.2")
        print("=" * 60)
        print("  Mode   : APPLY FROM CSV")
        print("  Source : %s" % csv_path.name)
        print("  Output : %s" % output_path)
        print("=" * 60)

        confirm = input("\n  Apply changes from this CSV? (y/n): ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            sys.exit(0)

        rows = run_from_csv(csv_path)

        if rows:
            write_csv(rows, str(output_path))
            print_summary(rows, apply_mode=True, output_path=str(output_path))
        else:
            print("  No results to save.")
        return

    # ── Standard mode: full folder scan ──
    if args:
        root_path = Path(args[0].strip('"'))
    else:
        chosen = pick_folder()
        if not chosen:
            print("No folder selected. Exiting.")
            sys.exit(0)
        root_path = Path(chosen)

    if not root_path.exists() or not root_path.is_dir():
        print("ERROR: Folder not found: %s" % root_path)
        sys.exit(1)

    suffix      = "_applied" if apply_mode else "_dry"
    output_path = reports_dir / ("fix_featuring_%s%s.csv" % (timestamp, suffix))

    print()
    print("=" * 60)
    print("  Fix Featuring Tags  v1.2")
    print("=" * 60)
    print("  Folder : %s" % root_path)
    print("  Mode   : %s" % ("APPLY — writing tags" if apply_mode
                              else "DRY RUN — no changes made"))
    print("  Output : %s" % output_path)
    print("=" * 60)

    if apply_mode:
        confirm = input("\n  Proceed with modifying tags? (y/n): ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            sys.exit(0)

    rows = run(str(root_path), apply_mode)

    if rows:
        write_csv(rows, str(output_path))
        print_summary(rows, apply_mode, str(output_path))
    else:
        print("  No results to save.")


if __name__ == "__main__":
    main()
