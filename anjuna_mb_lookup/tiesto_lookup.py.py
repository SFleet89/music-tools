"""
MusicBrainz Batch Lookup  v1.0
================================
Generic version of anjuna_mb_lookup — works with any music collection.

Scans a folder of album subfolders, extracts search terms from each folder
name (catalogue number, artist, title, year), and looks them up on
MusicBrainz. Compares local file metadata against MB tracklists for
confidence scoring.

Folder name patterns supported:
  Year - Artist - Title [CatNo] Format
  Artist - Title [CatNo]
  Artist - Title (Year)
  [CatNo] Artist - Title
  Artist - Title
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

# ── Config ─────────────────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".aac", ".m4a"}
MB_API_BASE          = "https://musicbrainz.org/ws/2"
USER_AGENT           = "MBLookup/1.0 ( music-tools )"
REQUEST_DELAY        = 1.1
RESULT_LIMIT         = 10
FUZZY_THRESHOLD      = 70
SCRIPT_DIR           = Path(__file__).parent

# ── Flags ──────────────────────────────────────────────────────────────────────
_args  = [a for a in sys.argv[1:] if not a.startswith("--")]
_flags = [a for a in sys.argv[1:] if a.startswith("--")]


# ── Folder name parsing ────────────────────────────────────────────────────────

# Matches anything in square or round brackets e.g. [BH 118-5] or (2008)
_BRACKET_RE  = re.compile(r'\[([^\]]+)\]|\(([^)]+)\)')
_YEAR_RE     = re.compile(r'\b(19|20)\d{2}\b')
# Format tags at end of folder name
_FORMAT_RE   = re.compile(r'\b(WEB|CD|FLAC|MP3|LOSSLESS|320|V0|VINYL|SACD)\b', re.IGNORECASE)


def parse_folder_name(name):
    """
    Extract year, artist, title, catno from a folder name.
    Returns dict with keys: year, artist, title, catno, raw_catno
    All values are strings or empty string if not found.

    Handles patterns like:
      1999 - DJ Tiesto - Sparkles [BH 118-5] WEB
      Above & Beyond - Sun & Moon [ANJ196D] (2011)
      Anjunabeats - Anjunabeats Volume 10
      Massive Attack - Mezzanine
    """
    result = {"year": "", "artist": "", "title": "", "catno": "", "raw": name}

    # Extract year from brackets or standalone
    year_m = _YEAR_RE.search(name)
    if year_m:
        result["year"] = year_m.group(0)

    # Extract catno from square brackets (not years, not format tags)
    catnos = []
    for m in _BRACKET_RE.finditer(name):
        val = (m.group(1) or m.group(2) or "").strip()
        if not _YEAR_RE.fullmatch(val) and not _FORMAT_RE.fullmatch(val):
            catnos.append(val)
    if catnos:
        result["catno"] = catnos[0]

    # Strip brackets, format tags, and year to get clean text
    clean = _BRACKET_RE.sub(" ", name)
    clean = _FORMAT_RE.sub(" ", clean)
    clean = _YEAR_RE.sub(" ", clean)
    clean = re.sub(r'\s+', ' ', clean).strip(" -_.")

    # Split on " - " to get artist / title
    parts = [p.strip() for p in clean.split(" - ") if p.strip()]
    if len(parts) >= 2:
        result["artist"] = parts[0]
        result["title"]  = " - ".join(parts[1:])
    elif len(parts) == 1:
        result["title"] = parts[0]

    return result


# ── File metadata reading ──────────────────────────────────────────────────────

def read_folder_metadata(folder_path):
    result = {"track_count": 0, "titles": [], "artists": set(), "albums": set()}
    files  = sorted(
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


# ── MusicBrainz API ────────────────────────────────────────────────────────────

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


def mb_search(query_params):
    """Generic release search. query_params is a dict of Lucene query terms."""
    parts = []
    for k, v in query_params.items():
        parts.append('%s:"%s"' % (k, v.replace('"', '\\"')))
    query = " AND ".join(parts)
    params = urllib.parse.urlencode({"query": query, "fmt": "json", "limit": str(RESULT_LIMIT)})
    data   = mb_get("%s/release?%s" % (MB_API_BASE, params))
    return data.get("releases", [])


def mb_search_catno(catno):
    return mb_search({"catno": catno})


def mb_search_artist_title(artist, title):
    return mb_search({"artist": artist, "release": title})


def mb_search_title_only(title):
    params = urllib.parse.urlencode({
        "query": 'release:"%s"' % title.replace('"', '\\"'),
        "fmt":   "json",
        "limit": str(RESULT_LIMIT),
    })
    data = mb_get("%s/release?%s" % (MB_API_BASE, params))
    return data.get("releases", [])


def mb_fetch_release(mbid):
    params = urllib.parse.urlencode({"inc": "recordings artist-credits labels", "fmt": "json"})
    try:
        return mb_get("%s/release/%s?%s" % (MB_API_BASE, mbid, params))
    except Exception as e:
        print("          ! Fetch error for %s: %s" % (mbid, e))
        return None


# ── Scoring ────────────────────────────────────────────────────────────────────

def fuzzy_score(a, b):
    import difflib
    a = a.lower().strip()
    b = b.lower().strip()
    if a == b:
        return 100
    return int(difflib.SequenceMatcher(None, a, b).ratio() * 100)


def normalise(s):
    return s.upper().replace("-", "").replace(" ", "").strip()


def score_release(release, parsed, folder_meta):
    """
    Score a release against our search terms.
    Returns 0-100 overall score.
    """
    score = 0

    # Catno match (highest weight)
    if parsed["catno"]:
        target_norm = normalise(parsed["catno"])
        for li in release.get("label-info", []):
            mb_catno = normalise(li.get("catalog-number") or "")
            if mb_catno == target_norm:
                score += 60
                break
            if target_norm in mb_catno or mb_catno in target_norm:
                score += 40
                break

    # Title match
    mb_title = release.get("title", "")
    if parsed["title"] and mb_title:
        ts = fuzzy_score(parsed["title"], mb_title)
        score += int(ts * 0.25)

    # Year match
    mb_date = release.get("date", "") or ""
    if parsed["year"] and mb_date.startswith(parsed["year"]):
        score += 15

    return min(score, 100)


def score_metadata(folder_meta, release_detail):
    if not release_detail:
        return {"score": 0, "track_match": 0, "count_match": False, "details": "no tracklist"}

    mb_tracks = []
    for medium in release_detail.get("media", []):
        for t in medium.get("tracks", []):
            rec   = t.get("recording") or {}
            title = t.get("title") or rec.get("title", "")
            if title:
                mb_tracks.append(title.lower().strip())

    mb_count    = len(mb_tracks)
    local_count = folder_meta["track_count"]
    count_match = local_count == mb_count
    details     = []
    if not count_match:
        details.append("track count: local=%d MB=%d" % (local_count, mb_count))

    title_score = 0
    if folder_meta["titles"] and mb_tracks:
        matched = sum(
            1 for lt in folder_meta["titles"]
            if max((fuzzy_score(lt, mt) for mt in mb_tracks), default=0) >= FUZZY_THRESHOLD
        )
        title_score = int(matched / len(folder_meta["titles"]) * 100)
        if title_score < 100:
            details.append("title match: %d%%" % title_score)
    elif not folder_meta["titles"]:
        title_score = 50
        details.append("no title tags in files")
    else:
        title_score = 50

    if count_match and title_score >= 80:   overall = 100
    elif count_match and title_score >= 50: overall = 80
    elif title_score >= 80:                 overall = 70
    elif title_score >= 50:                 overall = 50
    else:                                   overall = 20

    return {
        "score":       overall,
        "track_match": title_score,
        "count_match": count_match,
        "details":     "; ".join(details) if details else "good match",
    }


def combined_score(search_score, meta_score):
    return int(search_score * 0.6 + meta_score * 0.4)


# ── Release formatting ─────────────────────────────────────────────────────────

def release_label(release):
    title  = release.get("title", "Unknown")
    artist = release.get("artist-credit-phrase", "")
    date   = release.get("date", "")
    label_info = release.get("label-info", [])
    catnos = ", ".join(li.get("catalog-number","") for li in label_info if li.get("catalog-number"))
    parts  = [title]
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
            results.append(sub)
    return results


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

    # Strategy 1: catno
    if parsed["catno"]:
        try:
            releases = mb_search_catno(parsed["catno"])
            if releases:
                return releases, "catno: %s" % parsed["catno"]
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
            candidate_parts.append("%s|%s|%s|search:%d meta:%d combined:%d" % (
                r.get("id",""), release_label(r), get_mb_catnos(r),
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
        else:
            status  = "review"
            best_id = ""
            notes   = "%d candidates via %s — needs manual review" % (len(releases), search_method)
            print("          ? REVIEW  %d candidates (best combined: %d)" % (
                len(releases), best["combined"]))

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
    print("  Matched (single result)    : %d" % counts.get("matched", 0))
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


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
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
                initialdir=r"C:\Users\neo_s\Downloads\To Move",
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
    reports_dir = SCRIPT_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    output_path = reports_dir / ("mb_lookup_%s.csv" % timestamp)

    print()
    print("=" * 60)
    print("  MusicBrainz Batch Lookup  v1.0")
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
    else:
        print("  No results to save.")


if __name__ == "__main__":
    main()
