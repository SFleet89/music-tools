"""
Scan Progress Analyser  v1.1
==============================
Reads all scan_summary_*.csv files in your reports folder and produces a
progress report showing how your library cleanup is tracking over time.

For each scan it shows:
  - Total flagged files
  - Files fixed since the previous scan
  - New issues introduced since the previous scan
  - Issue type breakdown (underscores, all caps, etc.)

Writes a scan_progress_TIMESTAMP.csv and prints a summary to the console.
Open scan_progress_viewer.html to see the trend as a chart.

Usage:
    python scan_progress.py                          # read from configured reports folder
    python scan_progress.py --path "C:\\reports"     # override reports folder path
    python scan_progress.py --first-vs-last          # compare only first and most recent scan
"""

import sys
import csv
import re
from pathlib import Path
from datetime import datetime
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import interactive_options

# ── Config ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent

# ── Issue order (fix-first, matches scanner) ───────────────────────────────────
ISSUE_ORDER = [
    "underscores instead of spaces",
    "brackets/parentheses with underscores",
    "double spaces",
    "leading or trailing junk",
    "dots used as separators",
    "inconsistent spacing around dashes",
    "all caps or mostly uppercase",
    "starts with lowercase",
    "mixed separators",
]

ISSUE_SHORT = {
    "underscores instead of spaces":          "Underscores",
    "brackets/parentheses with underscores":  "Bracket underscores",
    "double spaces":                           "Double spaces",
    "leading or trailing junk":               "Junk characters",
    "dots used as separators":                "Dots",
    "inconsistent spacing around dashes":     "Dash spacing",
    "all caps or mostly uppercase":           "All caps",
    "starts with lowercase":                  "Lowercase",
    "mixed separators":                       "Mixed separators",
}


# ── CSV loading ────────────────────────────────────────────────────────────────
def load_summary(csv_path: Path) -> dict:
    """
    Load a scan_summary CSV.
    Returns {full_path: set_of_issues} — keyed by Full Path for reliable matching.
    Falls back to Folder+Filename if Full Path is missing.
    """
    result = {}
    try:
        with open(csv_path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                key = (row.get("Full Path") or "").strip()
                if not key:
                    key = (row.get("Folder","") + "/" + row.get("Filename","")).strip()
                if not key:
                    continue
                issues_str = row.get("Issues") or ""
                issues = {i.strip() for i in issues_str.split("|") if i.strip()}
                result[key.lower()] = issues
    except Exception as e:
        print(f"  WARNING: Could not read {csv_path.name}: {e}")
    return result


def extract_timestamp(filename: str) -> str:
    """Extract YYYYMMDD_HHMMSS from filename, return as-is for sorting."""
    m = re.search(r'(\d{8}_\d{6})', filename)
    return m.group(1) if m else filename


def fmt_timestamp(ts: str) -> str:
    """Convert YYYYMMDD_HHMMSS to a readable date."""
    try:
        return datetime.strptime(ts, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts


# ── Analysis ───────────────────────────────────────────────────────────────────
def analyse(older: dict, newer: dict) -> dict:
    """Compare two scan dicts, return change breakdown."""
    old_keys = set(older)
    new_keys = set(newer)

    fixed      = old_keys - new_keys
    new_issues = new_keys - old_keys
    remaining  = old_keys & new_keys

    issue_counts = Counter()
    for issues in newer.values():
        for issue in issues:
            issue_counts[issue] += 1

    return {
        "total":       len(newer),
        "fixed":       len(fixed),
        "new_issues":  len(new_issues),
        "remaining":   len(remaining),
        "issue_counts": issue_counts,
        "fixed_paths": fixed,
        "new_paths":   new_issues,
    }


# ── CSV output ─────────────────────────────────────────────────────────────────
def write_progress_csv(scans: list, output_path: Path):
    """
    Write a CSV with one row per scan showing totals and issue type counts.
    scans = [{"timestamp", "label", "total", "fixed", "new_issues", "remaining", "issue_counts"}, ...]
    """
    issue_cols = [ISSUE_SHORT[i] for i in ISSUE_ORDER]
    fieldnames = ["Scan Date", "Timestamp", "Total Flagged",
                  "Fixed Since Previous", "New Issues Since Previous", "Still Flagged",
                  "Net Change"] + issue_cols

    rows = []
    for s in scans:
        net = s.get("net_change", "—")
        row = {
            "Scan Date":              s["label"],
            "Timestamp":              s["timestamp"],
            "Total Flagged":          s["total"],
            "Fixed Since Previous":   s.get("fixed", "—"),
            "New Issues Since Previous": s.get("new_issues", "—"),
            "Still Flagged":          s.get("remaining", "—"),
            "Net Change":             net,
        }
        ic = s.get("issue_counts", Counter())
        for issue in ISSUE_ORDER:
            row[ISSUE_SHORT[issue]] = ic.get(issue, 0)
        rows.append(row)

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_scan_progress(
    reports_folder: Path,
    first_vs_last: bool = False,
    log_callback=None,
) -> dict:
    """
    Analyse scan_summary_*.csv files in reports_folder and write a progress CSV.

    Args:
        reports_folder: Folder containing scan_summary_*.csv files.
        first_vs_last:  If True, compare only the first and most recent scan.
        log_callback:   Optional callable(message). Defaults to print().

    Returns:
        dict: scans_found, results (list of scan dicts), report_path (Path|None)

    Raises:
        ValueError: reports_folder does not exist or is not a directory.
    """
    log = log_callback or print

    if not reports_folder.exists() or not reports_folder.is_dir():
        raise ValueError(f"Reports folder not found: {reports_folder}")

    summary_files = sorted(
        reports_folder.glob("scan_summary_*.csv"),
        key=lambda p: extract_timestamp(p.name),
    )

    if not summary_files:
        log(f"  No scan_summary_*.csv files found in {reports_folder}")
        log(f"  Run scan_music_filenames.py to generate scan reports first.")
        return {"scans_found": 0, "results": [], "report_path": None}

    log(f"  Scans found: {len(summary_files)}")

    if first_vs_last and len(summary_files) >= 2:
        summary_files = [summary_files[0], summary_files[-1]]
        log("  --first-vs-last: comparing first and most recent scan only.")

    # Load all scans
    scans_data = []
    for f in summary_files:
        ts   = extract_timestamp(f.name)
        data = load_summary(f)
        scans_data.append({"timestamp": ts, "label": fmt_timestamp(ts),
                           "data": data, "file": f.name})

    # Analyse each scan relative to the previous one
    results = []
    for i, scan in enumerate(scans_data):
        entry = {
            "timestamp":    scan["timestamp"],
            "label":        scan["label"],
            "file":         scan["file"],
            "total":        len(scan["data"]),
            "issue_counts": Counter(
                issue for issues in scan["data"].values() for issue in issues
            ),
        }

        if i == 0:
            entry["fixed"]      = "—"
            entry["new_issues"] = "—"
            entry["remaining"]  = "—"
            entry["net_change"] = "—"
        else:
            prev = scans_data[i - 1]["data"]
            curr = scan["data"]
            a    = analyse(prev, curr)
            entry["fixed"]      = a["fixed"]
            entry["new_issues"] = a["new_issues"]
            entry["remaining"]  = a["remaining"]
            entry["net_change"] = len(curr) - len(prev)

        results.append(entry)

    # Write progress CSV
    try:
        timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = reports_folder / f"scan_progress_{timestamp}.csv"
        write_progress_csv(results, report_path)
        log(f"  Progress report saved: {report_path.name}")
    except Exception as e:
        log(f"  WARNING: Could not write progress CSV: {e}")
        report_path = None

    return {
        "scans_found": len(summary_files),
        "results":     results,
        "report_path": report_path,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT  ← .cmd launchers call this; GUI does not
# ══════════════════════════════════════════════════════════════════════════════

def main():
    interactive_options([])

    first_vs_last = "--first-vs-last" in sys.argv

    _path_flag = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--path" and i + 1 < len(sys.argv)),
        None,
    )

    reports_dir = Path(_path_flag.strip('"')) if _path_flag else SCRIPT_DIR / "reports"

    print(f"\n{'=' * 65}")
    print("Scan Progress Analyser  v1.1")
    print(f"{'=' * 65}")
    print(f"  Reports folder : {reports_dir}")
    print(f"{'=' * 65}\n")

    try:
        result = run_scan_progress(reports_dir, first_vs_last=first_vs_last)
    except ValueError as e:
        print(f"  ERROR: {e}")
        print(f"  Use --path to specify the folder containing your scan_summary_*.csv files.")
        sys.exit(1)

    if not result["results"]:
        return

    results = result["results"]

    # ── Console output ──────────────────────────────────────────────────────────
    print(f"  {'Scan Date':<20} {'Total':>7} {'Fixed':>7} {'New':>7} {'Net':>7}")
    print(f"  {'-'*20} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")

    for r in results:
        fixed   = f"{r['fixed']:>7}"     if isinstance(r['fixed'], int)      else f"{'—':>7}"
        new_iss = f"{r['new_issues']:>7}" if isinstance(r['new_issues'], int) else f"{'—':>7}"
        net     = f"{r['net_change']:>+7}" if isinstance(r['net_change'], int) else f"{'—':>7}"
        print(f"  {r['label']:<20} {r['total']:>7} {fixed} {new_iss} {net}")

    print()

    if len(results) >= 2:
        first = results[0]
        last  = results[-1]
        diff  = last["total"] - first["total"]
        pct   = (diff / first["total"] * 100) if first["total"] else 0
        sign  = "+" if diff > 0 else ""
        print(f"  Overall: {first['total']:,} flagged → {last['total']:,} flagged  "
              f"({sign}{diff:,} files, {sign}{pct:.1f}%)")

        print(f"\n  Issue breakdown  ({first['label']} → {last['label']})\n")
        print(f"  {'Issue':<35} {'First':>7} {'Latest':>7} {'Change':>8}")
        print(f"  {'-'*35} {'-'*7} {'-'*7} {'-'*8}")
        for issue in ISSUE_ORDER:
            short = ISSUE_SHORT[issue]
            f_cnt = first["issue_counts"].get(issue, 0)
            l_cnt = last["issue_counts"].get(issue, 0)
            if f_cnt == 0 and l_cnt == 0:
                continue
            chg  = l_cnt - f_cnt
            sign = "+" if chg > 0 else ""
            print(f"  {short:<35} {f_cnt:>7} {l_cnt:>7} {sign+str(chg):>8}")
        print()

    print(f"{'=' * 65}\n")


if __name__ == "__main__":
    main()
