"""
Anjunabeats MusicBrainz Batch Lookup  v1.3
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

Output:
    Reports are saved next to the script in:
    <script folder>\\reports\\anjuna_lookup_YYYYMMDD_HHMMSS.csv

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

# ── Config ─────────────────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS  = {".mp3", ".flac", ".aac", ".m4a"}
MB_API_BASE           = "https://musicbrainz.org/ws/2"
USER_AGENT            = "AnjunaMBLookup/1.2 ( music-tools )"
REQUEST_DELAY         = 1.1    # seconds between MB requests (rate limit: 1/sec)
RESULT_LIMIT          = 10     # max results per catno search
FUZZY_THRESHOLD       = 70     # minimum fuzzy score to count a track title as matching

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
        # Remix release — try bare base and other remix variants only
        # Do NOT try D variants as these are different releases
        variants.append(base)
        for s in REMIX_VARIANTS:
            if s != suffix:
                variants.append(base + s)
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


# ── Fuzzy string matching ──────────────────────────────────────────────────────

def fuzzy_score(a, b):
    import difflib
    a = a.lower().strip()
    b = b.lower().strip()
    if a == b:
        return 100
    return int(difflib.SequenceMatcher(None, a, b).ratio() * 100)


# ── File metadata reading ──────────────────────────────────────────────────────

def read_folder_metadata(folder_path):
    result = {"track_count": 0, "titles": [], "artists": set(), "albums": set()}

    files = sorted(
        f for f in Path(folder_path).iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    result["track_count"] = len(files)

    if not MUTAGEN_AVAILABLE:
        return result

    for f in files:
        try:
            audio = MutagenFile(f, easy=True)
            if audio:
                title  = (audio.get("title",  [""])[0] or "").strip().lower()
                artist = (audio.get("artist", [""])[0] or "").strip().lower()
                album  = (audio.get("album",  [""])[0] or "").strip().lower()
                if title:  result["titles"].append(title)
                if artist: result["artists"].add(artist)
                if album:  result["albums"].add(album)
        except Exception:
            pass

    return result


# ── MusicBrainz API calls ──────────────────────────────────────────────────────

_last_request = 0

def mb_get(url):
    global _last_request
    elapsed = time.time() - _last_request
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    _last_request = time.time()
    return data


def mb_search_catno(catno):
    params = urllib.parse.urlencode({
        "query": 'catno:"%s"' % catno,
        "fmt":   "json",
        "limit": str(RESULT_LIMIT),
    })
    data = mb_get("%s/release?%s" % (MB_API_BASE, params))
    return data.get("releases", [])


def mb_fetch_release(mbid):
    params = urllib.parse.urlencode({
        "inc": "recordings artist-credits labels",
        "fmt": "json",
    })
    try:
        return mb_get("%s/release/%s?%s" % (MB_API_BASE, mbid, params))
    except Exception as e:
        print("          ! Error fetching release %s: %s" % (mbid, e))
        return None


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


def combined_score(catno_score, meta_score):
    return int(catno_score * 0.6 + meta_score * 0.4)


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


# ── Formatting helpers ─────────────────────────────────────────────────────────

def release_label(release):
    title      = release.get("title", "Unknown")
    artist     = release.get("artist-credit-phrase", "")
    date       = release.get("date", "")
    label_info = release.get("label-info", [])
    catnos     = ", ".join(
        li.get("catalog-number", "")
        for li in label_info if li.get("catalog-number")
    )
    parts = [title]
    if artist: parts.append(artist)
    if date:   parts.append(date[:4])
    if catnos: parts.append("[%s]" % catnos)
    return "  —  ".join(parts)


def get_mb_catnos(release):
    return ", ".join(
        li.get("catalog-number", "")
        for li in release.get("label-info", [])
        if li.get("catalog-number")
    )


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
            print("          ✗ Not found on MusicBrainz (tried %d variant(s))" % len(catnos_to_try))
            rows.append(_make_row(folder_name, str(folder), catno, searched_catno,
                                  "not_found", {}, None, [], folder_meta,
                                  "No results after trying %d catno variants" % len(catnos_to_try)))
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
            notes  = "Single result — %s" % best["meta_details"]
            print("          ✓ %s  [catno:%d meta:%d]  [MBID: %s]" % (
                release_label(best_r), best["catno_score"], best["meta_score"], best_mbid))
        elif auto_mode:
            status = "auto_matched"
            notes  = "Auto-picked from %d candidates (combined %d) — %s" % (
                len(releases), best["combined"], best["meta_details"])
            print("          ✓ AUTO  %s  [combined:%d]  [MBID: %s]" % (
                release_label(best_r), best["combined"], best_mbid))
        else:
            status    = "review"
            best_mbid = ""
            notes     = "%d candidates — needs manual review" % len(releases)
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
    initial  = r"C:\Users\neo_s\Downloads\To Move\Anjunabeats_FLAC"

    root_tk = tk.Tk()
    root_tk.withdraw()
    root_tk.attributes("-topmost", True)

    while True:
        chosen = filedialog.askdirectory(
            title="Select Anjuna batch folder %d (Cancel when done)" % (len(folders) + 1),
            initialdir=initial,
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
    print("  Anjunabeats MusicBrainz Batch Lookup  v1.3")
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
    else:
        print("  No results to save.")


if __name__ == "__main__":
    main()
