"""
Music Filename Scanner  v2.5
=============================
Scans your organized music folder and reports filenames that look messy
or malformed — so you know exactly where to focus your renaming tool.

Nothing is renamed. This script is read-only.

Outputs (all saved to the reports folder):
  scan_summary_TIMESTAMP.csv              — all flagged files, every issue
  scan_skipped_TIMESTAMP.csv             — files matched by skip list
  scan_01_underscores_TIMESTAMP.csv      — one CSV per issue type, in fix-first order
  scan_02_brackets_underscores_...
  scan_03_double_spaces_...
  ... etc.

Usage:
    python scan_music_filenames.py --pick                   # pick folder via dialog
    python scan_music_filenames.py --path "C:\\Music\\Organized"
    python scan_music_filenames.py --summary        # folder list only, no file detail
    python scan_music_filenames.py --issues         # add issue breakdown to console output

If neither --pick nor --path is given the script reads the 'organized' folder
from music_config.json at the project root.  If the config is also missing it
exits with an error.
"""

import sys
import re
import csv
from pathlib import Path
from datetime import datetime
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import pick_folder, config_organized_folder, interactive_options

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".aac", ".m4a"}

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR     = Path(__file__).parent
REPORTS_FOLDER = SCRIPT_DIR / "reports"

# Skip list: plain text file next to the script (one pattern per line).
# If the file doesn't exist no patterns are loaded and all files are scanned.
SKIP_LIST_FILE = SCRIPT_DIR / "scan_skip_list.txt"


# ══════════════════════════════════════════════════════════════════════════════
#  SKIP LIST
#  Plain text file — one artist name pattern per line.
#  A file is skipped if any pattern appears anywhere in its filename (case-insensitive).
#  Lines starting with # are comments. Blank lines are ignored.
# ══════════════════════════════════════════════════════════════════════════════

def load_skip_list(path) -> list:
    p = Path(path)
    if not p.exists():
        return []
    patterns = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line.lower())
    return patterns


def is_skipped(filename: str, patterns: list, folder_path: str = "") -> str:
    """Return the matching pattern if filename or its folder path should be skipped, else None."""
    fn_lower     = filename.lower()
    folder_lower = folder_path.lower()
    for pattern in patterns:
        if pattern in fn_lower or pattern in folder_lower:
            return pattern
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  ISSUE DETECTORS
# ══════════════════════════════════════════════════════════════════════════════

# Priority order — easiest/most mechanical fixes first
ISSUE_ORDER = [
    "underscores instead of spaces",
    "brackets/parentheses with underscores",
    "double spaces",
    "leading or trailing junk characters",
    "dots used as separators",
    "inconsistent spacing around dashes",
    "all caps or mostly uppercase",
    "starts with lowercase",
    "mixed separators (underscores/dots and dashes)",
]

ISSUE_SLUGS = {
    "underscores instead of spaces":                  "underscores",
    "brackets/parentheses with underscores":          "brackets_underscores",
    "double spaces":                                  "double_spaces",
    "leading or trailing junk characters":            "junk_characters",
    "dots used as separators":                        "dots_separators",
    "inconsistent spacing around dashes":             "dash_spacing",
    "all caps or mostly uppercase":                   "all_caps",
    "starts with lowercase":                          "lowercase",
    "mixed separators (underscores/dots and dashes)": "mixed_separators",
}


def check_underscores(stem):
    if "_" in stem:
        return "underscores instead of spaces"

def check_dots_as_separators(stem):
    if " - " in stem:
        return None
    cleaned = re.sub(r"^\d+\.", "", stem).strip()
    # Exempt all-uppercase acronym titles in 01. Title format: M.M.I.X, U.F.O, B.Y.O.B
    if re.match(r"^[A-Z](?:\.[A-Z])+\.?$", cleaned.strip()):
        return None
    segments = cleaned.split(".")
    non_empty = [s.strip() for s in segments if s.strip()]
    if len(non_empty) >= 3 and " " not in cleaned.replace(".", ""):
        return "dots used as separators"

def check_spacing_around_dashes(stem):
    if re.search(r"(?<! )- | -(?! )", stem):
        return "inconsistent spacing around dashes"

def check_brackets(stem):
    if re.search(r"[\(\[\{][^\)\]\}]*_[^\)\]\}]*[\)\]\}]", stem):
        return "brackets/parentheses with underscores"

def check_all_caps(stem):
    alpha = [c for c in stem if c.isalpha()]
    if len(alpha) > 4 and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.6:
        return "all caps or mostly uppercase"

def check_lowercase(stem):
    cleaned = re.sub(r"^\d+[\s\-_.]*", "", stem).strip()
    if cleaned and cleaned[0].islower():
        return "starts with lowercase"

def check_double_spaces(stem):
    if "  " in stem:
        return "double spaces"

def check_trailing_leading_junk(stem):
    if re.search(r"^[\s\-_]+", stem):
        return "leading or trailing junk characters"
    if re.search(r"[\s\-_]+$", stem):
        return "leading or trailing junk characters"
    if re.search(r"\.{2,}$", stem):
        return "leading or trailing junk characters"

def check_mixed_separators(stem):
    has_underscore = "_" in stem
    cleaned_no_dotnames = re.sub(r"\b[A-Za-z](?:\.[A-Za-z])+\.?", "", stem)
    segments = [s.strip() for s in stem.split(".") if s.strip()]
    has_dot_sep = (
        " - " not in stem
        and len(segments) >= 3
        and " " not in stem.replace(".", "")
        and bool(re.search(r"[a-zA-Z]\.[a-zA-Z]", cleaned_no_dotnames))
    )
    if (has_underscore or has_dot_sep) and "-" in stem:
        return "mixed separators (underscores/dots and dashes)"


CHECKERS = [
    check_underscores,
    check_dots_as_separators,
    check_spacing_around_dashes,
    check_brackets,
    check_all_caps,
    check_lowercase,
    check_double_spaces,
    check_trailing_leading_junk,
    check_mixed_separators,
]


def get_issues(filename):
    stem = Path(filename).stem
    return [r for c in CHECKERS if (r := c(stem))]


# ══════════════════════════════════════════════════════════════════════════════
#  SCAN
# ══════════════════════════════════════════════════════════════════════════════

def scan(root, skip_patterns):
    results = {}
    skipped = []

    music_files = sorted(
        f for f in root.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    for f in music_files:
        matched = is_skipped(f.name, skip_patterns, str(f.parent))
        if matched:
            skipped.append({
                "Folder":          str(f.parent.relative_to(root)) if f.parent != root else ".",
                "Filename":        f.name,
                "Full Path":       str(f),
                "Matched Pattern": matched,
            })
            continue

        issues = get_issues(f.name)
        if issues:
            folder = f.parent
            if folder not in results:
                results[folder] = []
            results[folder].append((f.name, issues))

    return results, skipped


# ══════════════════════════════════════════════════════════════════════════════
#  REPORT WRITERS
# ══════════════════════════════════════════════════════════════════════════════

def build_all_rows(results, root):
    rows = []
    for folder in sorted(results.keys()):
        for filename, issues in sorted(results[folder], key=lambda x: x[0]):
            rows.append({
                "Folder":      str(folder.relative_to(root)) if folder != root else ".",
                "Filename":    filename,
                "Full Path":   str(folder / filename),
                "Issues":      " | ".join(issues),
                "Issue Count": len(issues),
            })
    return rows


def write_summary_csv(rows, csv_path):
    fieldnames = ["Folder", "Filename", "Full Path", "Issues", "Issue Count"]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_issue_csv(rows, issue, csv_path):
    fieldnames = ["Folder", "Filename", "Full Path", "Other Issues"]
    issue_rows = []
    for row in rows:
        if issue in row["Issues"]:
            other = " | ".join(i for i in row["Issues"].split(" | ") if i.strip() != issue)
            issue_rows.append({
                "Folder":       row["Folder"],
                "Filename":     row["Filename"],
                "Full Path":    row["Full Path"],
                "Other Issues": other,
            })
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(issue_rows)
    return len(issue_rows)


def write_skipped_csv(skipped, csv_path):
    fieldnames = ["Folder", "Filename", "Full Path", "Matched Pattern"]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(skipped)


# ══════════════════════════════════════════════════════════════════════════════
#  CONSOLE OUTPUT
# ══════════════════════════════════════════════════════════════════════════════

def print_report(results, root, total_scanned, skipped_count, skip_list_loaded,
                 summary_only=False, show_issues=False):
    total_files = sum(len(v) for v in results.values())

    print("=" * 70)
    print("Music Filename Scanner  — Results")
    print("=" * 70)
    print(f"  Folder scanned : {root}")
    print(f"  Files scanned  : {total_scanned}")
    print(f"  Skip list      : {skip_list_loaded} pattern(s)  ({skipped_count} file(s) skipped)")
    print(f"  Messy files    : {total_files}  across  {len(results)} folder(s)")
    print("=" * 70)

    if not results:
        print("\n  All filenames look clean!")
        return

    for folder in sorted(results.keys()):
        files = results[folder]
        label = str(folder.relative_to(root)) if folder != root else "."
        print(f"\n  📁  {label}  ({len(files)} file(s))")

        if not summary_only:
            for filename, issues in sorted(files, key=lambda x: x[0]):
                print(f"       {filename}")
                for issue in issues:
                    print(f"         ⚠  {issue}")

    if show_issues:
        counter = Counter(
            issue
            for files in results.values()
            for _, issues in files
            for issue in issues
        )
        print("\n" + "=" * 70)
        print("  Issue breakdown (fix-first order):")
        for issue in ISSUE_ORDER:
            count = counter.get(issue, 0)
            if count:
                print(f"    {count:>4}x  {issue}")

    print("\n" + "=" * 70)
    if summary_only:
        print("  (Run without --summary to see individual filenames and issues)")
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_scan_music_filenames(
    folder: Path,
    summary_only: bool = False,
    show_issues: bool = False,
    skip_list_file: Path = None,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Scan folder for music files with malformed filenames.

    Args:
        folder:            Root folder to scan recursively.
        summary_only:      If True, only show folder totals (no per-file detail).
        show_issues:       If True, include issue type breakdown in log output.
        skip_list_file:    Path to skip list .txt file. Defaults to SKIP_LIST_FILE.
        progress_callback: Optional callable(current, total, message).
        log_callback:      Optional callable(message). Defaults to print().

    Returns:
        dict: total_scanned, flagged, skipped, skip_patterns, results,
              skipped_list, issue_counts, report_paths (list of Path)

    Raises:
        ValueError: folder does not exist or is not a directory.
    """
    log = log_callback or print

    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    if skip_list_file is None:
        skip_list_file = SKIP_LIST_FILE

    skip_patterns = load_skip_list(skip_list_file)

    all_music = sorted(
        f for f in folder.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    total_scanned = len(all_music)

    if progress_callback:
        progress_callback(0, total_scanned, "Scanning...")

    results, skipped = scan(folder, skip_patterns)

    if progress_callback:
        progress_callback(total_scanned, total_scanned, "Scan complete")

    all_rows      = build_all_rows(results, folder)
    total_flagged = len(all_rows)

    issue_counts = Counter(
        issue
        for files in results.values()
        for _, issues in files
        for issue in issues
    )

    # ── Write reports ──────────────────────────────────────────────────────────
    REPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_paths = []

    summary_path = REPORTS_FOLDER / f"scan_summary_{timestamp}.csv"
    write_summary_csv(all_rows, str(summary_path))
    report_paths.append(summary_path)
    log(f"  Report: scan_summary_{timestamp}.csv  ({total_flagged} files)")

    for i, issue in enumerate(ISSUE_ORDER, start=1):
        if issue_counts.get(issue, 0) == 0:
            continue
        slug     = ISSUE_SLUGS[issue]
        filename = f"scan_{i:02d}_{slug}_{timestamp}.csv"
        count    = write_issue_csv(all_rows, issue, str(REPORTS_FOLDER / filename))
        report_paths.append(REPORTS_FOLDER / filename)
        log(f"  Report: {filename}  ({count} files)")

    if skipped:
        skipped_path = REPORTS_FOLDER / f"scan_skipped_{timestamp}.csv"
        write_skipped_csv(skipped, str(skipped_path))
        report_paths.append(skipped_path)
        log(f"  Report: scan_skipped_{timestamp}.csv  ({len(skipped)} files)")

    return {
        "total_scanned":  total_scanned,
        "flagged":        total_flagged,
        "skipped":        len(skipped),
        "skip_patterns":  len(skip_patterns),
        "results":        results,
        "skipped_list":   skipped,
        "issue_counts":   issue_counts,
        "report_paths":   report_paths,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT  ← .cmd launchers call this; GUI does not
# ══════════════════════════════════════════════════════════════════════════════

def main():
    interactive_options([])

    summary_only = "--summary" in sys.argv
    show_issues  = "--issues"  in sys.argv
    pick_dir     = "--pick"    in sys.argv

    _path_flag = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--path" and i + 1 < len(sys.argv)),
        None,
    )

    # ── Resolve the folder to scan ─────────────────────────────────────────────
    if _path_flag:
        root = Path(_path_flag.strip('"'))
    elif pick_dir:
        root = pick_folder("Select your music library folder to scan")
        if not root:
            print("No folder selected. Exiting.")
            sys.exit(0)
    else:
        root = config_organized_folder()
        if not root:
            print("ERROR: No folder specified.")
            print("  Use --pick to open a folder dialog, or --path \"C:\\...\" to specify directly.")
            print("  (Or set 'folders.organized' in music_config.json at the project root.)")
            sys.exit(1)
        print(f"  Using organized folder from music_config.json: {root}")

    if not root.exists() or not root.is_dir():
        print(f"ERROR: Folder not found: {root}")
        sys.exit(1)

    print(f"\nScanning : {root}")
    skip_patterns = load_skip_list(SKIP_LIST_FILE)
    if skip_patterns:
        print(f"Skip list: {len(skip_patterns)} pattern(s) loaded")
    print("Please wait...\n")

    try:
        result = run_scan_music_filenames(
            root,
            summary_only=summary_only,
            show_issues=show_issues,
        )
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print_report(
        result["results"], root,
        result["total_scanned"], result["skipped"], result["skip_patterns"],
        summary_only=summary_only, show_issues=show_issues,
    )

    print("  Reports saved:")
    for p in result["report_paths"]:
        print(f"    {p.name}")
    print()


if __name__ == "__main__":
    main()
