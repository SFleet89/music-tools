"""
Anjunabeats MusicBrainz Batch Lookup  v1.6
===========================================
Scans a batch folder of Anjunabeats releases, extracts the catalogue
number from each subfolder name, and looks it up on MusicBrainz.

Also reads existing file metadata (title, artist, track count) and
compares it against MB tracklists to improve match confidence.

Requirements:
    pip install mutagen

Usage:
    python anjuna_mb_lookup.py "C:\\path\\to\\ANJ001-ANJ100-FLAC"
    python anjuna_mb_lookup.py "C:\\path\\to\\ANJ001-ANJ100-FLAC" --auto
    python anjuna_mb_lookup.py "C:\\path\\to\\ANJ001-ANJ100-FLAC" --review
    python anjuna_mb_lookup.py "C:\\path\\to\\ANJ001-ANJ100-FLAC" --move
    python anjuna_mb_lookup.py "C:\\path\\to\\ANJ001-ANJ100-FLAC" --move --apply

Output:
    Reports are saved next to the script in:
    <script folder>\\reports\\anjuna_lookup_YYYYMMDD_HHMMSS.csv

Changes in v1.5:
    - Merged v1.4a (RD variants + metadata fallback) with v1.4b (--move flag)
    - Added RD/R2D/R3D variants for remix releases (MusicBrainz commonly
      stores ANJ131R as ANJ131RD — digital release of a remix EP)
    - Added metadata fallback search: when all catno variants fail, parse
      artist + title from the folder name and search MB by those fields
    - Fallback results are scored normally and marked as [meta fallback] in
      the notes column
    - Added --move flag: after lookup, moves review folders to To Review/
      and not_found/no_catno folders to No Match/ next to the source folder
    - Add --apply to execute moves (default is dry run preview)

Changes in v1.4:
    - Added move_flagged_folders(): --move prints which folders would move;
      --move --apply executes the moves
      review folders -> To Review/ subfolder next to source
      not_found/no_catno folders -> No Match/ subfolder next to source

Changes in v1.3:
    - Reports now save next to the script, not inside the batch folder
    - Fixed catno scoring to normalise hyphens (ANJ101 == ANJ-101)
    - Improved variant handling for R/R2 remix releases
    - Variant search now skips D suffix when catno already has R suffix
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
    print("WARNING: mutagen not installed — file metadata comparison disabled.")
    print("         Run: pip install mutagen\n")

# ── Shared module ──────────────────────────────────────────────────────────────
from music_mb_common import (
    SUPPORTED_EXTENSIONS, MB_API_BASE, USER_AGENT, REQUEST_DELAY,
    RESULT_LIMIT, FUZZY_THRESHOLD,
    mb_get, mb_fetch_release,
    fuzzy_score, read_folder_metadata,
    combined_score, release_label, get_mb_catnos,
    move_flagged_folders,
)

# ── Config ─────────────────────────────────────────────────────────────────────

# Script directory — reports always save here regardless of batch folder location
SCRIPT_DIR = Path(__file__).parent

# Suffix variants to try if the exact catno returns no results.
# Grouped by catno type so we don't mix up remix (R) and digital (D) releases.
DIGITAL_VARIANTS = ["D", "EP", "E", "X"]
REMIX_VARIANTS   = ["R", "R2", "R3"]
OTHER_VARIANTS   = ["CD", "DJ", "DEEP"]

# ── Catalogue number extraction ────────────────────────────────────────────────

# Matches: ANJ101, ANJ101D, ANJ101R, ANJ101R2, ANJ101EP, ANJCD001, ANJDJ001
_CATNO_RE = re.compile(r'\b(ANJ[A-Z]*\d+(?:[A-Z]+\d*|\-\d+)?)', re.IGNORECASE)

def extract_catno(folder_name):
    match = _CATNO_RE.search(folder_name)
    if match:
        return match.group(1).upper()
    return None


def normalise_catno(catno):
    """Remove hyphens for comparison: ANJ-101 -> ANJ101."""
    return catno.upper().replace("-", "").strip()


def catno_base_and_suffix(catno):
    """
    Split catno into numeric base and trailing alpha suffix.
    ANJ111D  -> (ANJ111, D)
    ANJ196R2 -> (ANJ196, R2)
    ANJCD043 -> (ANJCD043, '')
    """
    m = re.match(r'^(ANJ[A-Z]*\d+)([A-Z]+\d*)$', catno, re.IGNORECASE)
    if m:
        return m.group(1).upper(), m.group(2).upper()
    return catno.upper(), ''


def generate_variants(catno):
    """
    Generate catno variants to try if the exact catno returns no results.
    Keeps remix (R) and digital (D) releases separate to avoid wrong matches.
    """
    base, suffix = catno_base_and_suffix(catno)
    variants = []

    if not suffix:
        # Bare catno — try digital suffixes first, then remix, then others
        for s in DIGITAL_VARIANTS + REMIX_VARIANTS + OTHER_VARIANTS:
            variants.append(base + s)
    elif suffix.startswith('R'):
        # Remix release — try bare base, RD variants (MusicBrainz commonly
        # stores ANJ131R as ANJ131RD), and other remix variants.
        # Do NOT try plain D variants as those are different releases.
        variants.append(base)
        variants.append(base + suffix + 'D')   # e.g. ANJ131R  -> ANJ131RD
        for s in REMIX_VARIANTS:
            if s != suffix:
                variants.append(base + s)
                variants.append(base + s + 'D')  # e.g. ANJ131R2 -> ANJ131R2D
    elif suffix == 'D' or suffix in DIGITAL_VARIANTS:
        # Digital release — try bare base and other digital variants
        variants.append(base)
        for s in DIGITAL_VARIANTS:
            if s != suffix:
                variants.append(base + s)
    else:
        # Other suffix — try bare base and all variants
        variants.append(base)
        for s in DIGITAL_VARIANTS + REMIX_VARIANTS + OTHER_VARIANTS:
            if s != suffix:
                variants.append(base + s)

    return variants


# ── MusicBrainz API calls ──────────────────────────────────────────────────────

def mb_search_catno(catno):
    params = urllib.parse.urlencode({
        "query": 'catno:"%s"' % catno,
        "fmt":   "json",
        "limit": str(RESULT_LIMIT),
    })
    data = mb_get("%s/release?%s" % (MB_API_BASE, params))
    return data.get("releases", [])


def get_mb_track_titles(release_detail):
    titles = []
    for medium in release_detail.get("media", []):
        for track in medium.get("tracks", []):
            title = (track.get("title") or
                     (track.get("recording") or {}).get("title") or "")
            if title:
                titles.append(title.strip().lower())
    return titles


def get_mb_track_count(release_detail):
    return sum(len(m.get("tracks", [])) for m in release_detail.get("media", []))


# ── Folder name parsing for metadata fallback ─────────────────────────────────

# Scene tags commonly appended after the title
_SCENE_TAG_RE = re.compile(
    r'\s*[-–]\s*(WEB|CD|VINYL|LOSSLESS|MP3|FLAC|320|256|GAF|MiNiMAL|'
    r'PARAKHODEN|TT|UL\d+|LOSSLESS[-\w]*).*$',
    re.IGNORECASE
)

def parse_folder_artist_title(folder_name):
    """
    Extract artist and title from folder name for metadata fallback search.
    e.g. 'ANJ131R Oceanlab - Lonely Girl (Part 2)-WEB-2009-LOSSLESS-GAF'
      -> ('Oceanlab', 'Lonely Girl (Part 2)')
    """
    # Remove catno prefix
    s = re.sub(r'^ANJ[A-Z]*\d+[A-Z\d]*\s+', '', folder_name, flags=re.IGNORECASE).strip()
    # Remove trailing scene tags
    s = _SCENE_TAG_RE.sub('', s).strip()
    if ' - ' in s:
        artist, title = s.split(' - ', 1)
        return artist.strip(), title.strip()
    return '', s.strip()


def mb_search_metadata(artist, title):
    """Search MusicBrainz by release title and artist name."""
    if not title:
        return []
    t = title.replace('"', '')
    a = artist.replace('"', '')
    query = ('release:"%s" AND artist:"%s"' % (t, a)) if a else ('release:"%s"' % t)
    params = urllib.parse.urlencode({
        "query": query,
        "fmt":   "json",
        "limit": str(RESULT_LIMIT),
    })
    data = mb_get("%s/release?%s" % (MB_API_BASE, params))
    return data.get("releases", [])


# ── Scoring ────────────────────────────────────────────────────────────────────

def score_catno_match(release, target_catno):
    """
    Score how well a release's catalogue numbers match the target.
    Normalises hyphens so ANJ101 == ANJ-101.
    Returns 0-100.
    """
    target_norm = normalise_catno(target_catno)
    label_info  = release.get("label-info", [])

    for li in label_info:
        mb_catno      = li.get("catalog-number") or ""
        mb_catno_norm = normalise_catno(mb_catno)
        if mb_catno_norm == target_norm:
            return 100
        if target_norm in mb_catno_norm or mb_catno_norm in target_norm:
            return 70

    title = release.get("title", "").upper()
    if normalise_catno(target_catno) in normalise_catno(title):
        return 40

    return 0


def score_metadata_match(folder_meta, release_detail):
    if not release_detail:
        return {"score": 0, "track_match": 0, "count_match": False,
                "details": "Could not fetch MB tracklist"}

    mb_titles      = get_mb_track_titles(release_detail)
    mb_track_count = get_mb_track_count(release_detail)
    local_count    = folder_meta["track_count"]
    local_titles   = folder_meta["titles"]
    details_parts  = []

    count_match = (local_count == mb_track_count)
    if not count_match:
        details_parts.append("track count: local=%d MB=%d" % (local_count, mb_track_count))

    title_score = 0
    if local_titles and mb_titles:
        matched = sum(
            1 for lt in local_titles
            if max((fuzzy_score(lt, mt) for mt in mb_titles), default=0) >= FUZZY_THRESHOLD
        )
        title_score = int(matched / len(local_titles) * 100)
        if title_score < 100:
            details_parts.append("title match: %d%%" % title_score)
    elif not local_titles:
        title_score = 50
        details_parts.append("no title tags in files")
    else:
        title_score = 50
        details_parts.append("no tracks in MB release")

    if count_match and title_score >= 80:
        overall = 100
    elif count_match and title_score >= 50:
        overall = 80
    elif not count_match and title_score >= 80:
        overall = 70
    elif title_score >= 50:
        overall = 50
    else:
        overall = 20

    details = "; ".join(details_parts) if details_parts else "good match"
    return {"score": overall, "track_match": title_score,
            "count_match": count_match, "details": details}


# ── Folder scanning ────────────────────────────────────────────────────────────

def scan_batch_folder(batch_path):
    results = []
    for sub in sorted(Path(batch_path).iterdir()):
        if not sub.is_dir():
            continue
        has_music = any(
            f.suffix.lower() in SUPPORTED_EXTENSIONS
            for f in sub.iterdir() if f.is_file()
        )
        if has_music:
            results.append((sub, extract_catno(sub.name)))
    return results


# ── Main lookup loop ───────────────────────────────────────────────────────────

def run_lookup(batch_path, auto_mode):
    folders = scan_batch_folder(batch_path)
    total   = len(folders)

    if total == 0:
        print("  No music subfolders found in: %s" % batch_path)
        return []

    meta_note = "with metadata comparison" if MUTAGEN_AVAILABLE else "without metadata comparison (install mutagen)"
    print()
    print("  Found %d release folder(s) to process (%s)." % (total, meta_note))
    print()

    rows = []

    for idx, (folder, catno) in enumerate(folders, 1):
        folder_name = folder.name
        print("  [%d/%d]  %s" % (idx, total, folder_name))

        folder_meta = read_folder_metadata(str(folder))
        print("          Files: %d" % folder_meta["track_count"])

        if not catno:
            print("          ✗ No catalogue number found in folder name")
            rows.append(_make_row(folder_name, str(folder), "", "", "no_catno",
                                  {}, None, [], folder_meta,
                                  "No ANJ* catalogue number found in folder name"))
            continue

        # Try exact catno, then variants
        catnos_to_try  = [catno] + generate_variants(catno)
        releases       = []
        searched_catno = catno
        network_error  = None
        meta_fallback  = False

        for try_catno in catnos_to_try:
            try:
                releases = mb_search_catno(try_catno)
            except Exception as e:
                network_error = str(e)
                print("          ! Network error for %s: %s" % (try_catno, e))
                break
            if releases:
                searched_catno = try_catno
                if try_catno != catno:
                    print("          ~ Variant matched: %s" % try_catno)
                break

        if network_error and not releases:
            rows.append(_make_row(folder_name, str(folder), catno, searched_catno,
                                  "error", {}, None, [], folder_meta,
                                  "Network error: %s" % network_error))
            continue

        if not releases:
            # Metadata fallback — parse artist/title from folder name and search MB
            fb_artist, fb_title = parse_folder_artist_title(folder_name)
            meta_fallback = False
            if fb_title:
                print("          ~ Trying metadata fallback: %r — %r" % (fb_artist, fb_title))
                try:
                    releases = mb_search_metadata(fb_artist, fb_title)
                except Exception as e:
                    print("          ! Metadata fallback error: %s" % e)
                if releases:
                    meta_fallback = True
                    print("          ~ Metadata fallback found %d result(s)" % len(releases))

        if not releases:
            print("          ✗ Not found on MusicBrainz (tried %d catno variant(s) + metadata fallback)" % len(catnos_to_try))
            rows.append(_make_row(folder_name, str(folder), catno, searched_catno,
                                  "not_found", {}, None, [], folder_meta,
                                  "No results after trying %d catno variants + metadata fallback" % len(catnos_to_try)))
            continue

        # Score all candidates
        scored = sorted(
            [(score_catno_match(r, searched_catno), r) for r in releases],
            key=lambda x: -x[0]
        )

        # Fetch full release details for each candidate
        candidates_detail = []
        for cs, r in scored:
            mbid   = r.get("id", "")
            detail = mb_fetch_release(mbid) if mbid else None
            ms     = score_metadata_match(folder_meta, detail)
            mb_tc  = get_mb_track_count(detail) if detail else ""
            combo  = combined_score(cs, ms["score"])
            candidates_detail.append({
                "release":      r,
                "catno_score":  cs,
                "meta_score":   ms["score"],
                "combined":     combo,
                "track_match":  ms["track_match"],
                "count_match":  ms["count_match"],
                "meta_details": ms["details"],
                "mb_tracks":    mb_tc,
            })

        candidates_detail.sort(key=lambda x: -x["combined"])
        best = candidates_detail[0]
        best_r = best["release"]
        best_mbid = best_r.get("id", "")

        # Build candidates string
        candidate_parts = []
        for c in candidates_detail:
            r = c["release"]
            candidate_parts.append("%s|%s|%s|catno:%d meta:%d combined:%d" % (
                r.get("id", ""), release_label(r), get_mb_catnos(r),
                c["catno_score"], c["meta_score"], c["combined"],
            ))
        candidates_str = "||".join(candidate_parts)

        if len(releases) == 1:
            status = "matched"
            fallback_tag = " [meta fallback]" if meta_fallback else ""
            notes  = "Single result — %s%s" % (best["meta_details"], fallback_tag)
            print("          ✓ %s  [catno:%d meta:%d]  [MBID: %s]" % (
                release_label(best_r), best["catno_score"], best["meta_score"], best_mbid))
        elif auto_mode:
            status = "auto_matched"
            fallback_tag = " [meta fallback]" if meta_fallback else ""
            notes  = "Auto-picked from %d candidates (combined %d) — %s%s" % (
                len(releases), best["combined"], best["meta_details"], fallback_tag)
            print("          ✓ AUTO  %s  [combined:%d]  [MBID: %s]" % (
                release_label(best_r), best["combined"], best_mbid))
        else:
            status    = "review"
            best_mbid = ""
            fallback_tag = " [meta fallback]" if meta_fallback else ""
            notes     = "%d candidates — needs manual review%s" % (len(releases), fallback_tag)
            print("          ? REVIEW  %d candidates (best combined: %d)" % (
                len(releases), best["combined"]))

        rows.append(_make_row(
            folder_name, str(folder), catno, searched_catno, status,
            best_r if status != "review" else {},
            best_mbid if status != "review" else "",
            candidates_detail, folder_meta, notes,
            best=best, candidates_str=candidates_str,
        ))

    return rows


def _make_row(folder_name, folder_path, catno, searched_catno, status,
              release, mbid, candidates_detail, folder_meta, notes,
              best=None, candidates_str=""):
    r = release or {}
    return {
        "folder":          folder_name,
        "folder_path":     folder_path,
        "extracted_catno": catno,
        "searched_catno":  searched_catno,
        "status":          status,
        "mbid":            mbid or "",
        "mb_title":        r.get("title", ""),
        "mb_artist":       r.get("artist-credit-phrase", ""),
        "mb_date":         r.get("date", ""),
        "mb_catnos":       get_mb_catnos(r) if r else "",
        "catno_score":     str(best["catno_score"]) if best else "",
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
    "extracted_catno", "searched_catno",
    "status", "mbid",
    "mb_title", "mb_artist", "mb_date", "mb_catnos",
    "catno_score", "meta_score", "combined_score",
    "track_match_pct", "count_match",
    "local_tracks", "mb_tracks",
    "candidates", "notes",
]

def write_csv(rows, output_path):
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


# ── Summary ────────────────────────────────────────────────────────────────────

def print_summary(rows, auto_mode, output_path):
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print("  Matched (single result)    : %d" % counts.get("matched", 0))
    if auto_mode:
        print("  Auto-picked (multi-result) : %d" % counts.get("auto_matched", 0))
    else:
        print("  Needs review (multi-result): %d" % counts.get("review", 0))
    print("  Not found on MusicBrainz   : %d" % counts.get("not_found", 0))
    print("  No catno in folder name    : %d" % counts.get("no_catno", 0))
    print("  Network errors             : %d" % counts.get("error", 0))
    print()
    print("  Report saved to:")
    print("  %s" % output_path)
    print("=" * 60)


# ── Entry point ────────────────────────────────────────────────────────────────

def pick_multiple_folders():
    """
    Open repeated folder picker dialogs, collecting folders until the user
    cancels or clicks Cancel. Returns a list of Path objects.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except ImportError:
        return None

    folders  = []

    root_tk = tk.Tk()
    root_tk.withdraw()
    root_tk.attributes("-topmost", True)

    while True:
        chosen = filedialog.askdirectory(
            title="Select Anjuna batch folder %d (Cancel when done)" % (len(folders) + 1),
            parent=root_tk,
        )
        if not chosen:
            break
        p = Path(chosen)
        if p not in folders:
            folders.append(p)
            initial = str(p.parent)   # start next picker in same parent

        # Ask whether to add another
        add_more = messagebox.askyesno(
            "Add another folder?",
            "Added:\n%s\n\n%d folder(s) selected so far.\n\nAdd another folder?" % (
                p.name, len(folders)
            ),
            parent=root_tk,
        )
        if not add_more:
            break

    root_tk.destroy()
    return folders if folders else None



# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_anjuna_mb_lookup(
    batch_path,
    auto_mode: bool = True,
    reports_dir=None,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Run an Anjuna MusicBrainz batch lookup on a folder of album subfolders.

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
    output_path = _reports / f"anjuna_lookup_{ts}.csv"
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


def main():
    args  = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    # ── Determine mode first ──
    if "--auto" in flags:
        auto_mode = True
    elif "--review" in flags:
        auto_mode = False
    else:
        print()
        print("=" * 60)
        print("  Multiple results mode")
        print("=" * 60)
        print("  Some catalogue numbers return multiple releases.")
        print("  How should these be handled?")
        print()
        print("  1 - Auto-pick  : select best match automatically")
        print("                   (uses catno + file metadata scoring)")
        print("  2 - Review     : flag for manual selection in the viewer")
        print("=" * 60)
        while True:
            choice = input("  Enter 1 or 2: ").strip()
            if choice == "1":   auto_mode = True;  break
            elif choice == "2": auto_mode = False; break
            print("  Please enter 1 or 2.")

    mode_label = "auto-pick" if auto_mode else "manual review"

    # ── Determine folders to process ──
    if args:
        # Paths passed on command line
        batch_folders = []
        for a in args:
            p = Path(a.strip('"'))
            if not p.exists() or not p.is_dir():
                print("ERROR: Folder not found: %s" % p)
                sys.exit(1)
            batch_folders.append(p)
    else:
        # Multi-folder picker
        batch_folders = pick_multiple_folders()
        if not batch_folders:
            print("No folders selected. Exiting.")
            sys.exit(0)

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports_dir = SCRIPT_DIR.parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    output_path = reports_dir / ("anjuna_lookup_%s.csv" % timestamp)

    print()
    print("=" * 60)
    print("  Anjunabeats MusicBrainz Batch Lookup  v1.6")
    print("=" * 60)
    print("  Folders   : %d selected" % len(batch_folders))
    for f in batch_folders:
        print("              %s" % f.name)
    print("  Mode      : %s" % mode_label)
    print("  Metadata  : %s" % ("enabled" if MUTAGEN_AVAILABLE else "disabled (install mutagen)"))
    print("  Output    : %s" % output_path)
    print("=" * 60)

    # Process all folders, accumulating rows into one combined report
    all_rows = []
    for idx, batch_path in enumerate(batch_folders, 1):
        if len(batch_folders) > 1:
            print()
            print("── Batch %d/%d: %s ──" % (idx, len(batch_folders), batch_path.name))
        rows = run_lookup(str(batch_path), auto_mode)
        all_rows.extend(rows)

    if all_rows:
        write_csv(all_rows, str(output_path))
        print_summary(all_rows, auto_mode, str(output_path))
        if "--move" in flags:
            move_flagged_folders(all_rows, apply_mode="--apply" in flags)
    else:
        print("  No results to save.")


if __name__ == "__main__":
    main()
