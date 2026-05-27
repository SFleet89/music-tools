"""
MusicBrainz Batch Lookup  v1.8
Generic version of anjuna_mb_lookup — works with any music collection.

Scans a folder of album subfolders, extracts search terms from each folder
name (catalogue number, artist, title, year), and looks them up on
MusicBrainz. Compares local file metadata against MB tracklists for
confidence scoring.

Folder name patterns supported:
  Year - Artist - Title [CatNo] Format
  Artist - Title [CatNo]
  Artist - Title (Year) [CatNo]
  [CatNo] Artist - Title
  Artist - Title [CatNo]
  Any folder with music files (falls back to file metadata search)

Requirements:
    pip install mutagen

Usage:
    python mb_lookup.py                    # opens folder picker
    python mb_lookup.py "C:\\path\\to\\folder"
    python mb_lookup.py "C:\\path\\to\\folder" --auto
    python mb_lookup.py "C:\\path\\to\\folder" --review

Output:
    Reports saved to: <script folder>\\reports\\mb_lookup_YYYYMMDD_HHMMSS.csv
"""

import sys
import os
import re
import csv
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime

# ── Optional mutagen ───────────────────────────────────────────────────────────
try:
    from mutagen import File as MutagenFile
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    print("WARNING: mutagen not installed — file metadata search disabled.")
    print("         Run: pip install mutagen\n")

# ── Shared module ──────────────────────────────────────────────────────────────
from music_mb_common import (
    SUPPORTED_EXTENSIONS, MB_API_BASE, USER_AGENT, REQUEST_DELAY,
    RESULT_LIMIT, FUZZY_THRESHOLD, CLEAR_WINNER_GAP, CLEAR_WINNER_MIN,
    CATNO_PREFIX_MAP,
    mb_get, mb_search, mb_search_catno, mb_search_artist_title,
    mb_search_title_only, mb_fetch_release,
    fuzzy_score, normalise, catno_search_variants, parse_folder_name,
    read_folder_metadata, scan_batch_folder,
    score_release, score_metadata, combined_score,
    release_label, get_mb_catnos,
    move_flagged_folders,
)

# ── Config ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent

# ── Flags ──────────────────────────────────────────────────────────────────────

# ── Main lookup ────────────────────────────────────────────────────────────────

def lookup_folder(folder, folder_meta, auto_mode):
    """
    Search MB for a folder using a tiered strategy:
    1. Catalogue number (if found in folder name)
    2. Artist + Title (if both found in folder name)
    3. Title only
    4. File metadata (album tag)
    Returns (releases, search_method) or ([], "")
    """
    parsed = parse_folder_name(folder.name)
    network_error = None

    # Strategy 1: catno (tries raw catno, then prefix-stripped and expanded variants)
    if parsed["catno"]:
        for catno_variant in catno_search_variants(parsed["catno"]):
            try:
                releases = mb_search_catno(catno_variant)
                if releases:
                    return releases, "catno: %s" % catno_variant
            except Exception as e:
                network_error = str(e)

    # Strategy 2: artist + title
    if parsed["artist"] and parsed["title"]:
        try:
            releases = mb_search_artist_title(parsed["artist"], parsed["title"])
            if releases:
                return releases, "artist+title"
        except Exception as e:
            network_error = str(e)

    # Strategy 3: title only
    if parsed["title"]:
        try:
            releases = mb_search_title_only(parsed["title"])
            if releases:
                return releases, "title"
        except Exception as e:
            network_error = str(e)

    # Strategy 4: album tag from files
    if folder_meta["albums"] and MUTAGEN_AVAILABLE:
        for album_tag in folder_meta["albums"]:
            if album_tag and len(album_tag) > 3:
                try:
                    releases = mb_search_title_only(album_tag)
                    if releases:
                        return releases, "file tag: %s" % album_tag
                except Exception as e:
                    network_error = str(e)

    if network_error:
        raise Exception(network_error)

    return [], ""


def run_lookup(batch_path, auto_mode):
    folders = scan_batch_folder(batch_path)
    total   = len(folders)
    if total == 0:
        print("  No music subfolders found in: %s" % batch_path)
        return []

    print()
    print("  Found %d release folder(s) to process." % total)
    print()

    rows = []
    for idx, folder in enumerate(folders, 1):
        print("  [%d/%d]  %s" % (idx, total, folder.name))

        folder_meta   = read_folder_metadata(str(folder))
        parsed        = parse_folder_name(folder.name)
        network_error = None

        print("          Files: %d  |  Catno: %s  |  Artist: %s  |  Title: %s" % (
            folder_meta["track_count"],
            parsed["catno"] or "—",
            parsed["artist"][:30] if parsed["artist"] else "—",
            parsed["title"][:30] if parsed["title"] else "—",
        ))

        try:
            releases, search_method = lookup_folder(folder, folder_meta, auto_mode)
        except Exception as e:
            network_error = str(e)
            releases      = []
            search_method = ""

        if network_error and not releases:
            print("          ! Network error: %s" % network_error)
            rows.append(_make_row(folder, parsed, "error", {}, "", [], folder_meta,
                                  "Network error: %s" % network_error, search_method))
            continue

        if not releases:
            print("          ✗ Not found on MusicBrainz")
            rows.append(_make_row(folder, parsed, "not_found", {}, "", [], folder_meta,
                                  "No results found", search_method))
            continue

        print("          ~ %d result(s) via %s" % (len(releases), search_method))

        # Score all candidates
        scored = sorted(
            [(score_release(r, parsed, folder_meta), r) for r in releases],
            key=lambda x: -x[0]
        )

        # Fetch full details for scoring
        candidates_detail = []
        for ss, r in scored:
            mbid   = r.get("id", "")
            detail = mb_fetch_release(mbid) if mbid else None
            ms     = score_metadata(folder_meta, detail)
            mb_tc  = sum(len(m.get("tracks",[])) for m in detail.get("media",[])) if detail else ""
            combo  = combined_score(ss, ms["score"])
            candidates_detail.append({
                "release":      r,
                "search_score": ss,
                "meta_score":   ms["score"],
                "combined":     combo,
                "track_match":  ms["track_match"],
                "count_match":  ms["count_match"],
                "meta_details": ms["details"],
                "mb_tracks":    mb_tc,
            })

        candidates_detail.sort(key=lambda x: -x["combined"])
        best    = candidates_detail[0]
        best_r  = best["release"]
        best_id = best_r.get("id", "")

        candidate_parts = []
        for c in candidates_detail:
            r = c["release"]
            catnos = get_mb_catnos(r) or "-"   # avoid empty field creating false || split
            candidate_parts.append("%s|%s|%s|search:%d meta:%d combined:%d" % (
                r.get("id",""), release_label(r), catnos,
                c["search_score"], c["meta_score"], c["combined"],
            ))
        candidates_str = "||".join(candidate_parts)

        if len(releases) == 1:
            status = "matched"
            notes  = "Single result via %s — %s" % (search_method, best["meta_details"])
            print("          ✓ %s  [combined:%d]  [MBID: %s]" % (
                release_label(best_r), best["combined"], best_id))
        elif auto_mode:
            status = "auto_matched"
            notes  = "Auto-picked from %d candidates via %s (combined %d) — %s" % (
                len(releases), search_method, best["combined"], best["meta_details"])
            print("          ✓ AUTO  %s  [combined:%d]  [MBID: %s]" % (
                release_label(best_r), best["combined"], best_id))
        elif (len(candidates_detail) >= 2
              and best["combined"] >= CLEAR_WINNER_MIN
              and best["combined"] - candidates_detail[1]["combined"] >= CLEAR_WINNER_GAP):
            gap    = best["combined"] - candidates_detail[1]["combined"]
            status = "matched"
            notes  = "Clear winner from %d candidates via %s (gap: +%d) — %s" % (
                len(releases), search_method, gap, best["meta_details"])
            print("          ✓ CLEAR  %s  [combined:%d  gap:+%d]  [MBID: %s]" % (
                release_label(best_r), best["combined"], gap, best_id))
        else:
            status  = "review"
            best_id = ""
            notes   = "%d candidates via %s — needs manual review" % (len(releases), search_method)
            print("          ? REVIEW  %d candidates (best combined: %d)" % (
                len(releases), best["combined"]))

        # Safety check: title match 0% despite having title tags means the release
        # is almost certainly wrong — demote to review regardless of other scores.
        if status == "matched" and best["track_match"] == 0 and folder_meta["titles"]:
            status  = "review"
            best_id = ""
            notes   += " — demoted: title match 0%"
            print("          ⚠ DEMOTED to review (title match 0%)")

        rows.append(_make_row(
            folder, parsed, status,
            best_r if status != "review" else {},
            best_id if status != "review" else "",
            candidates_detail, folder_meta, notes, search_method,
            best=best, candidates_str=candidates_str,
        ))

    return rows


def _make_row(folder, parsed, status, release, mbid, candidates_detail, folder_meta,
              notes, search_method, best=None, candidates_str=""):
    r = release or {}
    return {
        "folder":          folder.name,
        "folder_path":     str(folder),
        "parsed_artist":   parsed.get("artist", ""),
        "parsed_title":    parsed.get("title", ""),
        "parsed_year":     parsed.get("year", ""),
        "extracted_catno": parsed.get("catno", ""),
        "search_method":   search_method,
        "status":          status,
        "mbid":            mbid or "",
        "mb_title":        r.get("title", ""),
        "mb_artist":       r.get("artist-credit-phrase", ""),
        "mb_date":         r.get("date", ""),
        "mb_catnos":       get_mb_catnos(r) if r else "",
        "search_score":    str(best["search_score"]) if best else "",
        "meta_score":      str(best["meta_score"]) if best else "",
        "combined_score":  str(best["combined"]) if best else "",
        "track_match_pct": str(best["track_match"]) if best else "",
        "count_match":     str(best["count_match"]) if best else "",
        "local_tracks":    str(folder_meta["track_count"]),
        "mb_tracks":       str(best["mb_tracks"]) if best else "",
        "candidates":      candidates_str,
        "notes":           notes,
    }


# ── CSV output ─────────────────────────────────────────────────────────────────

FIELDNAMES = [
    "folder", "folder_path",
    "parsed_artist", "parsed_title", "parsed_year", "extracted_catno",
    "search_method", "status", "mbid",
    "mb_title", "mb_artist", "mb_date", "mb_catnos",
    "search_score", "meta_score", "combined_score",
    "track_match_pct", "count_match", "local_tracks", "mb_tracks",
    "candidates", "notes",
]

def write_csv(rows, output_path):
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows, auto_mode, output_path):
    from collections import Counter
    counts = Counter(r["status"] for r in rows)
    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    matched_total = counts.get("matched", 0)
    print("  Matched                    : %d" % matched_total)
    if auto_mode:
        print("  Auto-picked (multi-result) : %d" % counts.get("auto_matched", 0))
    else:
        print("  Needs review (multi-result): %d" % counts.get("review", 0))
    print("  Not found on MusicBrainz   : %d" % counts.get("not_found", 0))
    print("  Network errors             : %d" % counts.get("error", 0))
    print()
    print("  Report saved to:")
    print("  %s" % output_path)
    print("=" * 60)



# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_tiesto_lookup(
    batch_path,
    auto_mode: bool = True,
    reports_dir=None,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Run a Tiesto MusicBrainz batch lookup on a folder of album subfolders.

    Args:
        batch_path:        Root folder containing album subfolders.
        auto_mode:         True = auto-pick best match; False = flag for review.
        reports_dir:       Where to save; defaults to <script folder>/../reports.
        progress_callback: Optional callable(current, total, message).
        log_callback:      Optional callable(message). Defaults to print().

    Returns:
        dict: matched, auto_matched, review, not_found, errors,
              rows (list), report_path (Path|None)

    Raises:
        ValueError: batch_path does not exist or is not a directory.
    """
    from collections import Counter
    log        = log_callback or print
    batch_path = Path(batch_path)

    if not batch_path.exists() or not batch_path.is_dir():
        raise ValueError(f"Folder not found: {batch_path}")

    rows = run_lookup(str(batch_path), auto_mode)

    if not rows:
        return {"matched": 0, "auto_matched": 0, "review": 0,
                "not_found": 0, "errors": 0, "rows": [], "report_path": None}

    _reports = Path(reports_dir) if reports_dir else SCRIPT_DIR.parent / "reports"
    _reports.mkdir(parents=True, exist_ok=True)
    ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = _reports / f"tiesto_lookup_{ts}.csv"
    write_csv(rows, str(output_path))

    counts = Counter(r["status"] for r in rows)
    return {
        "matched":      counts.get("matched", 0),
        "auto_matched": counts.get("auto_matched", 0),
        "review":       counts.get("review", 0),
        "not_found":    counts.get("not_found", 0),
        "errors":       counts.get("error", 0),
        "rows":         rows,
        "report_path":  output_path,
    }


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    _args  = [a for a in sys.argv[1:] if not a.startswith("--")]
    _flags = [a for a in sys.argv[1:] if a.startswith("--")]

    if "--auto" in _flags:
        auto_mode = True
    elif "--review" in _flags:
        auto_mode = False
    else:
        print()
        print("=" * 60)
        print("  Multiple results mode")
        print("=" * 60)
        print("  1 - Auto-pick  : select best match automatically")
        print("  2 - Review     : flag for manual selection in viewer")
        print("=" * 60)
        while True:
            choice = input("  Enter 1 or 2: ").strip()
            if choice == "1":   auto_mode = True;  break
            elif choice == "2": auto_mode = False; break
            print("  Please enter 1 or 2.")

    if not _args:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            chosen = filedialog.askdirectory(
                title="Select folder of album subfolders to look up",
            )
            root.destroy()
            if not chosen:
                print("No folder selected. Exiting.")
                sys.exit(0)
            batch_path = Path(chosen)
        except Exception as e:
            print("ERROR: Could not open folder picker: %s" % e)
            sys.exit(1)
    else:
        batch_path = Path(_args[0].strip('"'))

    if not batch_path.exists() or not batch_path.is_dir():
        print("ERROR: Folder not found: %s" % batch_path)
        sys.exit(1)

    mode_label  = "auto-pick" if auto_mode else "manual review"
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports_dir = SCRIPT_DIR.parent / "reports"  # writes to parent folder's reports/ (e.g. tools/reports/)
    reports_dir.mkdir(exist_ok=True)
    output_path = reports_dir / ("mb_lookup_%s.csv" % timestamp)

    print()
    print("=" * 60)
    print("  MusicBrainz Batch Lookup  v1.8")
    print("=" * 60)
    print("  Folder    : %s" % batch_path)
    print("  Mode      : %s" % mode_label)
    print("  Metadata  : %s" % ("enabled" if MUTAGEN_AVAILABLE else "disabled"))
    print("  Output    : %s" % output_path)
    print("=" * 60)

    rows = run_lookup(str(batch_path), auto_mode)

    if rows:
        write_csv(rows, str(output_path))
        print_summary(rows, auto_mode, str(output_path))
        if "--move" in _flags:
            move_flagged_folders(rows, apply_mode="--apply" in _flags)
    else:
        print("  No results to save.")


if __name__ == "__main__":
    main()
