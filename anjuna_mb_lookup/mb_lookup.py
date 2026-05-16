"""
MusicBrainz Batch Lookup  v2.7
================================
Generic music collection lookup — works with any folder of album subfolders.

Matching strategy (in priority order):
  0. AcoustID audio fingerprint  (requires fpcalc.exe)
  1. Catalogue number            (from folder name)
  2. Artist + Title              (from folder name)
  3. Title only                  (from folder name)
  4. Album tag from files        (from embedded metadata)

Folder name patterns supported:
  Year - Artist - Title [CatNo] Format
  Artist - Title [CatNo]
  Artist - Title (Year)
  [CatNo] Artist - Title
  Artist - Title
  Any folder with music files (falls back to file metadata search)

Requirements:
    pip install mutagen
    fpcalc.exe  (Chromaprint — place in tools folder or pass --fpcalc PATH)

Usage:
    python mb_lookup.py                          # opens folder picker
    python mb_lookup.py "C:\\path\\to\\folder"
    python mb_lookup.py "C:\\path\\to\\folder" --auto
    python mb_lookup.py "C:\\path\\to\\folder" --review
    python mb_lookup.py "C:\\path\\to\\folder" --no-fingerprint
    python mb_lookup.py "C:\\path\\to\\folder" --fpcalc "C:\\path\\to\\fpcalc.exe"

Output:
    Reports saved to: <script folder>\\reports\\mb_lookup_YYYYMMDD_HHMMSS.csv

Changes in v2.1:
    - Fixed candidate serialization bug: empty catnos now written as "-" to avoid
      false || split that corrupted candidate count in viewer

Changes in v2.0:
    - Added AcoustID fingerprint lookup as Strategy 0 (highest priority)
    - Added --fpcalc flag to specify fpcalc.exe path
    - Added --no-fingerprint flag to skip fingerprinting
    - Fixed false-positive bug: single results with combined score < 35 now flagged as review
    - Added acoustid_score column to CSV output
"""

import sys
import os
import re
import csv
import json
import time
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime
from collections import Counter

# ── Optional mutagen ───────────────────────────────────────────────────────────
try:
    from mutagen import File as MutagenFile
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    print("WARNING: mutagen not installed — file metadata search disabled.")
    print("         Run: pip install mutagen\n")

# ── Config ─────────────────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS   = {".mp3", ".flac", ".aac", ".m4a"}
MB_API_BASE            = "https://musicbrainz.org/ws/2"
ACOUSTID_API           = "https://api.acoustid.org/v2/lookup"
ACOUSTID_KEY           = "LA0hhbEjxv"
FPCALC_DEFAULT         = str(Path(__file__).parent.parent / "fpcalc.exe")  # tools/fpcalc.exe
USER_AGENT             = "MBLookup/2.0 ( music-tools )"
REQUEST_DELAY          = 1.1   # MusicBrainz rate limit
ACOUSTID_DELAY         = 0.4   # AcoustID rate limit
RESULT_LIMIT           = 10
FUZZY_THRESHOLD        = 70
CLEAR_WINNER_GAP       = 10   # min score gap between 1st and 2nd candidate to auto-pick
CLEAR_WINNER_MIN       = 75   # min combined score for the top candidate to qualify
FINGERPRINT_SAMPLE     = 3     # max files to fingerprint per folder
MIN_SINGLE_MATCH_SCORE = 35    # single-result matches below this → review
SCRIPT_DIR             = Path(__file__).parent

# ── Argument parsing ────────────────────────────────────────────────────────────
def _get_flag_value(flag_name):
    """Return the value after --flag VALUE, or None."""
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == flag_name and i + 1 < len(argv):
            return argv[i + 1]
    return None

_positional   = [a for a in sys.argv[1:] if not a.startswith("--")]
_flags        = [a for a in sys.argv[1:] if a.startswith("--")]
_fpcalc_arg   = _get_flag_value("--fpcalc")
NO_FINGERPRINT = "--no-fingerprint" in _flags


# ── Folder name parsing ────────────────────────────────────────────────────────
_BRACKET_RE = re.compile(r'\[([^\]]+)\]|\(([^)]+)\)')
_CATNO_RE   = re.compile(r'\[([^\]]+)\]')   # square brackets only — for catno extraction
_YEAR_RE    = re.compile(r'\b(19|20)\d{2}\b')
_FORMAT_RE  = re.compile(r'\b(WEB|CD|FLAC|MP3|LOSSLESS|320|V0|VINYL|SACD)\b', re.IGNORECASE)

# ── Catalogue number prefix expansion ─────────────────────────────────────────
# Maps label abbreviations/names used in folder names to their full label name.
# Some labels store catnos on MusicBrainz WITHOUT a label prefix (e.g. Magik Muzik
# uses bare numbers like "835-6"), so we also try stripping the prefix entirely.
# Add entries here as you discover new patterns in your collection.
CATNO_PREFIX_MAP = {
    # Abbreviation / folder prefix  →  full label name (as stored on MB)
    "MM":                            "Magik Muzik",
    "Magik Muzik":                   "Magik Muzik",
    "BH":                            "Black Hole Recordings",
    "Black Hole":                    "Black Hole Recordings",
    "BHDO":                          "Black Hole Recordings Download Only",
    "DP":                            "Dance Planet Ltd.",
    "NEB":                           "Nebula",
    "K":                             "Kontor Records",
    "D4L":                           "Dance 4 Life",
}

def catno_search_variants(catno):
    """
    Return a list of catno strings to try in order.
    Always tries the raw catno first, then — if it starts with a known label
    prefix — also tries the full label name variant, then the bare number.
    Full label name is tried before bare number because the bare number is less
    specific and risks matching unrelated releases on MB.
    Example: "MM 835-6"  →  ["MM 835-6", "Magik Muzik 835-6", "835-6"]
    """
    variants = [catno]
    upper = catno.upper()
    for prefix, full_name in CATNO_PREFIX_MAP.items():
        if upper.startswith(prefix.upper() + " "):
            number_part = catno[len(prefix):].strip()
            full_variant = "%s %s" % (full_name, number_part)
            if full_variant not in variants:
                variants.append(full_variant)
            if number_part and number_part not in variants:
                variants.append(number_part)
            break
    return variants


def parse_folder_name(name):
    """
    Extract year, artist, title, catno from a folder name.
    Returns dict with keys: year, artist, title, catno, raw
    """
    result = {"year": "", "artist": "", "title": "", "catno": "", "raw": name}

    year_m = _YEAR_RE.search(name)
    if year_m:
        result["year"] = year_m.group(0)

    # Skip literal 'no cat' placeholders (normalised to NOCAT* after stripping punctuation)
    catnos = []
    for m in _CATNO_RE.finditer(name):
        val = m.group(1).strip()
        val_norm = re.sub(r'[\s\.\-_#]', '', val).upper()
        if (not _YEAR_RE.fullmatch(val)
                and not _FORMAT_RE.fullmatch(val)
                and not val_norm.startswith("NOCAT")):
            catnos.append(val)
    if catnos:
        result["catno"] = catnos[0]

    clean = _BRACKET_RE.sub(" ", name)
    clean = _FORMAT_RE.sub(" ", clean)
    clean = _YEAR_RE.sub(" ", clean)
    clean = re.sub(r'\s+', ' ', clean).strip(" -_.")

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


def get_sample_files(folder_path, n=FINGERPRINT_SAMPLE):
    """Return up to n audio files from the folder for fingerprinting."""
    files = sorted(
        f for f in Path(folder_path).iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not files:
        return []
    # Sample evenly across the tracklist
    if len(files) <= n:
        return files
    step = len(files) / n
    return [files[int(i * step)] for i in range(n)]


# ── AcoustID fingerprinting ────────────────────────────────────────────────────

_last_acoustid = 0


def run_fpcalc(file_path, fpcalc_path):
    """Run fpcalc on a file. Returns (fingerprint, duration) or (None, None)."""
    try:
        result = subprocess.run(
            [str(fpcalc_path), "-json", str(file_path)],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None, None
        data = json.loads(result.stdout)
        return data.get("fingerprint"), data.get("duration")
    except Exception:
        return None, None


def acoustid_lookup(fingerprint, duration):
    """Query AcoustID. Returns the parsed JSON response or None."""
    global _last_acoustid
    elapsed = time.time() - _last_acoustid
    if elapsed < ACOUSTID_DELAY:
        time.sleep(ACOUSTID_DELAY - elapsed)
    params = urllib.parse.urlencode({
        "client":      ACOUSTID_KEY,
        "fingerprint": fingerprint,
        "duration":    int(duration),
        "meta":        "recordings releases releasegroups tracks compress",
    })
    req = urllib.request.Request(
        "%s?%s" % (ACOUSTID_API, params),
        headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        _last_acoustid = time.time()
        return data
    except Exception:
        _last_acoustid = time.time()
        return None


def extract_release_ids_from_acoustid(response):
    """
    Parse AcoustID response and return a list of (mbid, score) tuples
    for all release IDs found, ordered by AcoustID score descending.
    """
    if not response or response.get("status") != "ok":
        return []
    id_scores = []
    for result in response.get("results", []):
        acoustid_score = result.get("score", 0)
        for recording in result.get("recordings", []):
            for release in recording.get("releases", []):
                mbid = release.get("id")
                if mbid:
                    id_scores.append((mbid, acoustid_score))
    return id_scores


def fingerprint_folder(folder_path, fpcalc_path):
    """
    Fingerprint sample files in a folder and return ranked MB release IDs.
    Returns list of MBIDs sorted by frequency * score, or [] if none found.
    """
    sample_files = get_sample_files(folder_path)
    if not sample_files:
        return []

    mbid_scores = {}  # mbid → cumulative score
    mbid_counts = Counter()

    for f in sample_files:
        fp, dur = run_fpcalc(f, fpcalc_path)
        if not fp or not dur:
            continue
        response = acoustid_lookup(fp, dur)
        if not response:
            continue
        for mbid, score in extract_release_ids_from_acoustid(response):
            mbid_scores[mbid] = mbid_scores.get(mbid, 0) + score
            mbid_counts[mbid] += 1

    if not mbid_scores:
        return []

    # Rank by count first (consensus), then by cumulative score
    ranked = sorted(
        mbid_scores.keys(),
        key=lambda m: (mbid_counts[m], mbid_scores[m]),
        reverse=True
    )
    return ranked


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
    parts  = ['%s:"%s"' % (k, v.replace('"', '\\"')) for k, v in query_params.items()]
    query  = " AND ".join(parts)
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


def build_artist_string(release):
    """Build artist string from artist-credit array (for direct fetches)."""
    phrase = release.get("artist-credit-phrase", "")
    if phrase:
        return phrase
    credits = release.get("artist-credit", [])
    parts = []
    for c in credits:
        if isinstance(c, dict):
            artist = c.get("artist", {})
            parts.append(artist.get("name", ""))
            join = c.get("joinphrase", "")
            if join:
                parts.append(join)
        elif isinstance(c, str):
            parts.append(c)
    return "".join(parts).strip()


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
    """Score a release against our search terms. Returns 0–100."""
    score = 0

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

    mb_title = release.get("title", "")
    if parsed["title"] and mb_title:
        ts = fuzzy_score(parsed["title"], mb_title)
        score += int(ts * 0.25)

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
    artist = build_artist_string(release)
    date   = release.get("date", "")
    catnos = ", ".join(
        li.get("catalog-number", "")
        for li in release.get("label-info", [])
        if li.get("catalog-number")
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

def lookup_folder(folder, folder_meta, auto_mode, fpcalc_path):
    """
    Search MB for a folder using a tiered strategy:
    0. AcoustID fingerprint (if fpcalc available)
    1. Catalogue number    (if found in folder name)
    2. Artist + Title      (if both found in folder name)
    3. Title only          (from folder name)
    4. File metadata       (album tag from files)

    Returns (releases, search_method, acoustid_mbids) or ([], "", [])
    """
    parsed        = parse_folder_name(folder.name)
    network_error = None
    acoustid_mbids = []

    # Strategy 0: AcoustID fingerprint
    if fpcalc_path and not NO_FINGERPRINT:
        try:
            acoustid_mbids = fingerprint_folder(str(folder), fpcalc_path)
            if acoustid_mbids:
                releases = []
                for mbid in acoustid_mbids[:5]:
                    r = mb_fetch_release(mbid)
                    if r:
                        releases.append(r)
                if releases:
                    return releases, "acoustid", acoustid_mbids
        except Exception as e:
            network_error = str(e)
            print("          ! AcoustID error: %s" % e)

    # Strategy 1: catno (tries raw catno, then prefix-stripped and expanded variants)
    if parsed["catno"]:
        for catno_variant in catno_search_variants(parsed["catno"]):
            try:
                releases = mb_search_catno(catno_variant)
                if releases:
                    return releases, "catno: %s" % catno_variant, acoustid_mbids
            except Exception as e:
                network_error = str(e)

    # Strategy 2: artist + title
    if parsed["artist"] and parsed["title"]:
        try:
            releases = mb_search_artist_title(parsed["artist"], parsed["title"])
            if releases:
                return releases, "artist+title", acoustid_mbids
        except Exception as e:
            network_error = str(e)

    # Strategy 3: title only
    if parsed["title"]:
        try:
            releases = mb_search_title_only(parsed["title"])
            if releases:
                return releases, "title", acoustid_mbids
        except Exception as e:
            network_error = str(e)

    # Strategy 4: album tag from files
    if folder_meta["albums"] and MUTAGEN_AVAILABLE:
        for album_tag in folder_meta["albums"]:
            if album_tag and len(album_tag) > 3:
                try:
                    releases = mb_search_title_only(album_tag)
                    if releases:
                        return releases, "file tag: %s" % album_tag, acoustid_mbids
                except Exception as e:
                    network_error = str(e)

    if network_error:
        raise Exception(network_error)

    return [], "", acoustid_mbids


def run_lookup(batch_path, auto_mode, fpcalc_path):
    folders = scan_batch_folder(batch_path)
    total   = len(folders)
    if total == 0:
        print("  No music subfolders found in: %s" % batch_path)
        return []

    fingerprint_active = bool(fpcalc_path) and not NO_FINGERPRINT

    print()
    print("  Found %d release folder(s) to process." % total)
    print("  Fingerprinting: %s" % ("enabled" if fingerprint_active else "disabled"))
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
            releases, search_method, acoustid_mbids = lookup_folder(
                folder, folder_meta, auto_mode, fpcalc_path
            )
        except Exception as e:
            network_error = str(e)
            releases       = []
            search_method  = ""
            acoustid_mbids = []

        if network_error and not releases:
            print("          ! Network error: %s" % network_error)
            rows.append(_make_row(folder, parsed, "error", {}, "", [], folder_meta,
                                  "Network error: %s" % network_error, search_method,
                                  acoustid_mbids=acoustid_mbids))
            continue

        if not releases:
            print("          ✗ Not found on MusicBrainz")
            rows.append(_make_row(folder, parsed, "not_found", {}, "", [], folder_meta,
                                  "No results found", search_method,
                                  acoustid_mbids=acoustid_mbids))
            continue

        print("          ~ %d result(s) via %s" % (len(releases), search_method))

        # Score all candidates
        scored = sorted(
            [(score_release(r, parsed, folder_meta), r) for r in releases],
            key=lambda x: -x[0]
        )

        # For AcoustID results the release IS the full detail already
        acoustid_mode = search_method == "acoustid"

        candidates_detail = []
        for ss, r in scored:
            mbid   = r.get("id", "")
            detail = r if acoustid_mode else (mb_fetch_release(mbid) if mbid else None)
            ms     = score_metadata(folder_meta, detail)
            mb_tc  = sum(len(m.get("tracks", [])) for m in detail.get("media", [])) if detail else ""
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
                r.get("id", ""), release_label(r), catnos,
                c["search_score"], c["meta_score"], c["combined"],
            ))
        candidates_str = "||".join(candidate_parts)

        # Determine status
        single_result = len(releases) == 1
        low_confidence = best["combined"] < MIN_SINGLE_MATCH_SCORE

        if single_result and low_confidence:
            status = "review"
            notes  = "Single result via %s — low confidence (combined %d) — %s" % (
                search_method, best["combined"], best["meta_details"])
            print("          ? LOW-CONF  %s  [combined:%d]  [MBID: %s]" % (
                release_label(best_r), best["combined"], best_id))
        elif single_result:
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
            best_r if status not in ("review",) else {},
            best_id if status not in ("review",) else "",
            candidates_detail, folder_meta, notes, search_method,
            best=best, candidates_str=candidates_str,
            acoustid_mbids=acoustid_mbids,
        ))

    return rows


def _make_row(folder, parsed, status, release, mbid, candidates_detail, folder_meta,
              notes, search_method, best=None, candidates_str="", acoustid_mbids=None):
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
        "mb_artist":       build_artist_string(r) if r else "",
        "mb_date":         r.get("date", ""),
        "mb_catnos":       get_mb_catnos(r) if r else "",
        "search_score":    str(best["search_score"]) if best else "",
        "meta_score":      str(best["meta_score"]) if best else "",
        "combined_score":  str(best["combined"]) if best else "",
        "track_match_pct": str(best["track_match"]) if best else "",
        "count_match":     str(best["count_match"]) if best else "",
        "local_tracks":    str(folder_meta["track_count"]),
        "mb_tracks":       str(best["mb_tracks"]) if best else "",
        "acoustid_mbids":  "|".join((acoustid_mbids or [])[:5]),
        "candidates":      candidates_str,
        "notes":           notes,
    }


# ── Folder mover ───────────────────────────────────────────────────────────────

def move_flagged_folders(rows, apply_mode):
    """
    Move review/not_found/no_catno folders into subfolders next to their
    current location:
      status=review              → <parent>/To Review/<folder>
      status=not_found|no_catno → <parent>/No Match/<folder>
    Dry run by default; pass apply_mode=True to execute moves.
    """
    import shutil as _shutil

    DEST_MAP = {
        "review":    "To Review",
        "not_found": "No Match",
        "no_catno":  "No Match",
    }

    moves = []
    for row in rows:
        dest_name = DEST_MAP.get(row.get("status", ""))
        if not dest_name:
            continue
        src = Path(row["folder_path"])
        if not src.exists():
            continue
        dest_dir = src.parent / dest_name
        moves.append((src, dest_dir / src.name, dest_dir, dest_name))

    print()
    print("=" * 60)
    print("  FOLDER MOVE  (%s)" % ("APPLY" if apply_mode else "DRY RUN"))
    print("=" * 60)

    if not moves:
        print("  No folders to move.")
        print("=" * 60)
        return

    for src, dst, dest_dir, label in moves:
        print("  [%-10s]  %s" % (label, src.name))

    if not apply_mode:
        print()
        print("  %d folder(s) would be moved. Add --apply to execute." % len(moves))
        print("=" * 60)
        return

    moved = errors = 0
    seen_dirs = set()
    for src, dst, dest_dir, label in moves:
        if dest_dir not in seen_dirs:
            dest_dir.mkdir(exist_ok=True)
            seen_dirs.add(dest_dir)
        try:
            _shutil.move(str(src), str(dst))
            moved += 1
        except Exception as e:
            print("  ! Error moving %s: %s" % (src.name, e))
            errors += 1

    print()
    print("  Moved : %d" % moved)
    if errors:
        print("  Errors: %d" % errors)
    print("=" * 60)


# ── CSV output ─────────────────────────────────────────────────────────────────

FIELDNAMES = [
    "folder", "folder_path",
    "parsed_artist", "parsed_title", "parsed_year", "extracted_catno",
    "search_method", "status", "mbid",
    "mb_title", "mb_artist", "mb_date", "mb_catnos",
    "search_score", "meta_score", "combined_score",
    "track_match_pct", "count_match", "local_tracks", "mb_tracks",
    "acoustid_mbids", "candidates", "notes",
]


def write_csv(rows, output_path):
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows, auto_mode, output_path):
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
    # Resolve fpcalc path
    if _fpcalc_arg:
        fpcalc_path = Path(_fpcalc_arg)
    else:
        fpcalc_path = Path(FPCALC_DEFAULT)

    if NO_FINGERPRINT:
        fpcalc_path = None
        print("  Fingerprinting disabled (--no-fingerprint)")
    elif not fpcalc_path.exists():
        print("  WARNING: fpcalc not found at: %s" % fpcalc_path)
        print("           Fingerprinting will be skipped.")
        print("           Use --fpcalc PATH to specify location, or --no-fingerprint to suppress this warning.")
        fpcalc_path = None

    # Auto/review mode
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

    # Folder selection
    if not _positional:
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
        batch_path = Path(_positional[0].strip('"'))

    if not batch_path.exists() or not batch_path.is_dir():
        print("ERROR: Folder not found: %s" % batch_path)
        sys.exit(1)

    mode_label  = "auto-pick" if auto_mode else "manual review"
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports_dir = SCRIPT_DIR.parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    output_path = reports_dir / ("mb_lookup_%s.csv" % timestamp)

    print()
    print("=" * 60)
    print("  MusicBrainz Batch Lookup  v2.7")
    print("=" * 60)
    print("  Folder        : %s" % batch_path)
    print("  Mode          : %s" % mode_label)
    print("  Fingerprinting: %s" % ("enabled (%s)" % fpcalc_path if fpcalc_path else "disabled"))
    print("  Metadata      : %s" % ("enabled" if MUTAGEN_AVAILABLE else "disabled"))
    print("  Output        : %s" % output_path)
    print("=" * 60)

    rows = run_lookup(str(batch_path), auto_mode, fpcalc_path)

    if rows:
        write_csv(rows, str(output_path))
        print_summary(rows, auto_mode, str(output_path))
        if "--move" in _flags:
            move_flagged_folders(rows, apply_mode="--apply" in _flags)
    else:
        print("  No results to save.")


if __name__ == "__main__":
    main()
