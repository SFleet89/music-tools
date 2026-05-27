"""
music_mb_common.py
==================
Shared library for the MusicBrainz lookup/tagging suite.

Provides:
  - Rate-limited MusicBrainz API access  (mb_get, mb_fetch_release,
    mb_search, mb_search_catno, mb_search_artist_title, mb_search_title_only)
  - Fuzzy string matching                (fuzzy_score)
  - Catalogue-number normalisation       (normalise, catno_search_variants)
  - Folder name parsing                  (parse_folder_name)
  - File metadata reading                (read_folder_metadata)
  - Folder scanning                      (scan_batch_folder)
  - Candidate scoring                    (score_release, score_metadata,
                                          combined_score)
  - Release display helpers              (build_artist_string, release_label,
                                          get_mb_catnos)
  - Folder mover                         (move_flagged_folders)

Used by:
  anjuna_mb_lookup/mb_lookup.py
  anjuna_mb_lookup/anjuna_mb_lookup.py
  anjuna_mb_lookup/tiesto_lookup.py
  anjuna_mb_lookup/mb_tagger.py

Rate-limiting state (_last_request) is module-level so all callers that
import this module share a single rate limiter across all MB requests.
"""

import re
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

# -- Optional mutagen ----------------------------------------------------------
try:
    from mutagen import File as MutagenFile
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

# -- Constants -----------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".aac", ".m4a"}
MB_API_BASE          = "https://musicbrainz.org/ws/2"
USER_AGENT           = "MBLookup/2.0 ( music-tools )"
REQUEST_DELAY        = 1.1    # seconds — MusicBrainz rate limit (1 req/sec)
RESULT_LIMIT         = 10     # max results per search
FUZZY_THRESHOLD      = 70     # minimum fuzzy score for a track title to count as matching
CLEAR_WINNER_GAP     = 10     # min score gap between 1st and 2nd candidate to auto-pick
CLEAR_WINNER_MIN     = 75     # min combined score for top candidate to qualify as clear winner

# -- Catalogue number prefix map -----------------------------------------------
# Maps label abbreviations / folder-name prefixes to the full label name as
# stored on MusicBrainz.  Some labels store catnos WITHOUT a label prefix
# (e.g. Magik Muzik uses bare numbers like "835-6"), so catno_search_variants()
# also tries stripping the prefix entirely.
CATNO_PREFIX_MAP = {
    "MM":          "Magik Muzik",
    "Magik Muzik": "Magik Muzik",
    "BH":          "Black Hole Recordings",
    "Black Hole":  "Black Hole Recordings",
    "BHDO":        "Black Hole Recordings Download Only",
    "DP":          "Dance Planet Ltd.",
    "NEB":         "Nebula",
    "K":           "Kontor Records",
    "D4L":         "Dance 4 Life",
}

# -- Folder name regexes -------------------------------------------------------
_BRACKET_RE = re.compile(r'\[([^\]]+)\]|\(([^)]+)\)')
_CATNO_RE   = re.compile(r'\[([^\]]+)\]')   # square brackets only
_YEAR_RE    = re.compile(r'\b(19|20)\d{2}\b')
_FORMAT_RE  = re.compile(r'\b(WEB|CD|FLAC|MP3|LOSSLESS|320|V0|VINYL|SACD)\b', re.IGNORECASE)

# -- Rate-limiting state -------------------------------------------------------
# Module-level so all callers share one rate limiter regardless of which
# script imports this module.
_last_request = 0.0


# ==============================================================================
#  MusicBrainz API
# ==============================================================================

def mb_get(url):
    """
    Make a rate-limited GET request to the MusicBrainz API.
    Enforces REQUEST_DELAY between calls.  Returns parsed JSON.
    Raises urllib.error.URLError / http.client.HTTPException on failure.
    """
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
    """
    Generic MB release search.
    query_params is a dict of Lucene field->value pairs, e.g.
      {"catno": "ANJ101"} or {"artist": "Tiesto", "release": "Sparkles"}.
    Returns a list of release dicts (may be empty).
    """
    parts  = ['%s:"%s"' % (k, v.replace('"', '\\"')) for k, v in query_params.items()]
    query  = " AND ".join(parts)
    params = urllib.parse.urlencode({"query": query, "fmt": "json", "limit": str(RESULT_LIMIT)})
    data   = mb_get("%s/release?%s" % (MB_API_BASE, params))
    return data.get("releases", [])


def mb_search_catno(catno):
    """Search MB for releases matching a catalogue number."""
    return mb_search({"catno": catno})


def mb_search_artist_title(artist, title):
    """Search MB for releases matching artist and release title."""
    return mb_search({"artist": artist, "release": title})


def mb_search_title_only(title):
    """Search MB for releases matching a release title only."""
    params = urllib.parse.urlencode({
        "query": 'release:"%s"' % title.replace('"', '\\"'),
        "fmt":   "json",
        "limit": str(RESULT_LIMIT),
    })
    data = mb_get("%s/release?%s" % (MB_API_BASE, params))
    return data.get("releases", [])


def mb_fetch_release(mbid):
    """
    Fetch a full release record from MB including recordings, artist credits,
    and label info.  Returns the parsed release dict, or None on error.

    Note: mb_tagger.py requires the additional 'release-groups' include — it
    keeps its own local version of this function with that extra parameter.
    """
    params = urllib.parse.urlencode({
        "inc": "recordings artist-credits labels",
        "fmt": "json",
    })
    try:
        return mb_get("%s/release/%s?%s" % (MB_API_BASE, mbid, params))
    except Exception as e:
        print("          ! Fetch error for %s: %s" % (mbid, e))
        return None


# ==============================================================================
#  Fuzzy string matching
# ==============================================================================

def fuzzy_score(a, b):
    """
    Return an integer 0-100 representing how similar two strings are.
    Case-insensitive.  Returns 100 for exact matches.
    """
    import difflib
    a = a.lower().strip()
    b = b.lower().strip()
    if a == b:
        return 100
    return int(difflib.SequenceMatcher(None, a, b).ratio() * 100)


# ==============================================================================
#  Catalogue number helpers
# ==============================================================================

def normalise(s):
    """
    Normalise a catalogue number for comparison:
    upper-case, strip hyphens and spaces.
    Example: "ANJ-101" -> "ANJ101", "BH 118-5" -> "BH1185"
    """
    return s.upper().replace("-", "").replace(" ", "").strip()


def catno_search_variants(catno):
    """
    Return a list of catno strings to try against MusicBrainz, in priority order.

    Always tries the raw catno first, then -- if it starts with a known label
    prefix from CATNO_PREFIX_MAP -- also tries the full label-name variant,
    then the bare number.

    Full label name is tried before bare number because the bare number is less
    specific and risks matching unrelated releases.

    Example: "MM 835-6" -> ["MM 835-6", "Magik Muzik 835-6", "835-6"]
    """
    variants = [catno]
    upper = catno.upper()
    for prefix, full_name in CATNO_PREFIX_MAP.items():
        if upper.startswith(prefix.upper() + " "):
            number_part  = catno[len(prefix):].strip()
            full_variant = "%s %s" % (full_name, number_part)
            if full_variant not in variants:
                variants.append(full_variant)
            if number_part and number_part not in variants:
                variants.append(number_part)
            break
    return variants


# ==============================================================================
#  Folder name parsing
# ==============================================================================

def parse_folder_name(name):
    """
    Extract year, artist, title, and catno from a music folder name.
    Returns a dict with keys: year, artist, title, catno, raw.
    All values are strings; empty string if not found.

    Handles patterns like:
      1999 - DJ Tiesto - Sparkles [BH 118-5] WEB
      Above & Beyond - Sun & Moon [ANJ196D] (2011)
      Massive Attack - Mezzanine
    """
    result = {"year": "", "artist": "", "title": "", "catno": "", "raw": name}

    year_m = _YEAR_RE.search(name)
    if year_m:
        result["year"] = year_m.group(0)

    # Extract catno from square brackets only; skip years, format tags,
    # and "no cat" placeholders.
    catnos = []
    for m in _CATNO_RE.finditer(name):
        val      = m.group(1).strip()
        val_norm = re.sub(r'[\s\.\-_#]', '', val).upper()
        if (not _YEAR_RE.fullmatch(val)
                and not _FORMAT_RE.fullmatch(val)
                and not val_norm.startswith("NOCAT")):
            catnos.append(val)
    if catnos:
        result["catno"] = catnos[0]

    # Strip brackets, format tags, and year; split on " - " for artist/title
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


# ==============================================================================
#  File metadata reading
# ==============================================================================

def read_folder_metadata(folder_path):
    """
    Read embedded tags from all supported audio files in folder_path.
    Returns a dict:
      track_count  - number of audio files found
      titles       - list of lowercased track title strings
      artists      - set of lowercased artist strings
      albums       - set of lowercased album strings

    If mutagen is not installed, returns counts only (titles/artists/albums empty).
    """
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


# ==============================================================================
#  Folder scanning
# ==============================================================================

def scan_batch_folder(batch_path):
    """
    Return a sorted list of Path objects for every direct subfolder of
    batch_path that contains at least one supported audio file.

    Note: anjuna_mb_lookup.py has its own local scan_batch_folder that returns
    (path, catno) tuples — do not replace that one with this function.
    """
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


# ==============================================================================
#  Scoring
# ==============================================================================

def score_release(release, parsed, folder_meta):
    """
    Score a MB release dict against parsed folder-name data.
    Returns an integer 0-100.

    Weights:
      Catno exact match   -> +60
      Catno partial match -> +40
      Title fuzzy match   -> up to +25  (fuzzy_score * 0.25)
      Year match          -> +15
    """
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
        score += int(fuzzy_score(parsed["title"], mb_title) * 0.25)

    mb_date = release.get("date", "") or ""
    if parsed["year"] and mb_date.startswith(parsed["year"]):
        score += 15

    return min(score, 100)


def score_metadata(folder_meta, release_detail):
    """
    Score a fetched MB release against local file metadata (track count +
    title fuzzy matching).  Returns a dict:
      score        - overall integer 0-100
      track_match  - integer 0-100 (percentage of local titles matched)
      count_match  - bool (local track count == MB track count)
      details      - human-readable summary string
    """
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
    """Combine a search/catno score and a metadata score into one 0-100 integer."""
    return int(search_score * 0.6 + meta_score * 0.4)


# ==============================================================================
#  Release display helpers
# ==============================================================================

def build_artist_string(release):
    """
    Build a display artist string from a release's artist-credit array.
    Falls back to artist-credit-phrase if present.
    Returns an empty string if no artist data is available.
    """
    phrase = release.get("artist-credit-phrase", "")
    if phrase:
        return phrase
    credits = release.get("artist-credit", [])
    parts   = []
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


def release_label(release):
    """
    Build a compact one-line display string for a release:
      Title  --  Artist  --  Year  --  [CatNo]
    Any missing fields are omitted.
    """
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
    return "  --  ".join(parts)


def get_mb_catnos(release):
    """
    Return a comma-separated string of all catalogue numbers from a release's
    label-info list.  Returns an empty string if none are present.
    """
    return ", ".join(
        li.get("catalog-number", "")
        for li in release.get("label-info", [])
        if li.get("catalog-number")
    )


# ==============================================================================
#  Folder mover
# ==============================================================================

def move_flagged_folders(rows, apply_mode):
    """
    Move review/not_found/no_catno folders into subfolders next to their
    current location:
      status=review              -> <parent>/To Review/<folder>
      status=not_found|no_catno -> <parent>/No Match/<folder>

    Dry run by default.  Pass apply_mode=True to execute the moves.
    rows must be a list of dicts each containing at least 'folder_path'
    and 'status' keys (i.e. the row dicts produced by any of the lookup scripts).
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
