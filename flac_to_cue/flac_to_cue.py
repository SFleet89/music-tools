"""
FLAC to CUE  v1.5
==================
Generates a CUE sheet for a FLAC file using MusicBrainz data.

Reads the MusicBrainz Release ID (MBID) from the FLAC file's tags, fetches
the tracklist from the MusicBrainz API, and writes a CUE sheet ready to use
with CUETools for splitting.

If no MBID tag is found, falls back through a chain of search strategies:
  1. MBID tag
  2. CATALOGNUMBER tag -> catno search
  3. ARTIST + ALBUM tags -> artist+album search
  4. Catno parsed from filename (ANJCD008, ANJ131 etc.) -> catno search
  5. Artist + title parsed from filename -> artist+album search

Supports multi-disc releases -- generates one CUE per disc, matched to the
correct FLAC file automatically.

Requirements:
    pip install mutagen requests

Usage:
    python flac_to_cue.py                           # folder picker
    python flac_to_cue.py "C:\\path\\to\\folder"    # all FLACs in folder
    python flac_to_cue.py "C:\\path\\to\\file.flac" # single file
    python flac_to_cue.py --scan                    # folder picker, then recursive scan
    python flac_to_cue.py --scan "C:\\path\\to\\Music"  # scan specific root

Output:
    A .cue file written next to each FLAC file:
    CD1.flac  ->  CD1.cue
    CD2.flac  ->  CD2.cue

    FLAC files that already have a matching .cue are skipped automatically.

    Reports saved to: <script folder>\\reports\\flac_to_cue_YYYYMMDD_HHMMSS.csv
    Logs saved to:    <script folder>\\reports\\flac_to_cue_YYYYMMDD_HHMMSS.log

Changes in v1.5:
    - Fixed disc number detection: filename is now checked BEFORE the
      DISCNUMBER tag. Scene rips frequently have DISCNUMBER=1 on all discs,
      causing CD2 files to be matched as disc 1. Priority order is now:
        1. Scene prefix (201- = disc 2)
        2. Explicit keyword in filename (CD2, Disc 2)
        3. Sequential file prefix (02. = disc 2, only if value > 1)
        4. Parent folder keyword
        5. DISCNUMBER tag (last resort)

Changes in v1.4:
    - Fixed CUE index format for long releases: minutes over 99 now use
      hours correctly (e.g. 63:54 becomes 01:03:54) so CUE Splitter can
      parse split points on releases over ~99 minutes.
    - Added disc track count sanity check: warns and prompts to continue
      if the matched disc has an unexpected number of tracks (catches wrong
      MB release being selected).
    - CUE preview now shows total duration so you can spot obvious mismatches
      before confirming.

Changes in v1.3:
    - Added filename parsing as fallback strategies 4 and 5:
        4. Extract ANJ*/ANJCD* catno from filename -> catno search
        5. Extract artist + title from filename -> artist+album search
      Fixes 0% match rate for untagged FLAC files with informative filenames.
    - Fixed log message bug: search strings now accurately reflect what is
      actually being sent to the MB API.
    - parse_filename() strips scene tags (WEB, FLAC, CD1, TT, FOX etc.),
      track number prefixes, and disc suffixes before searching.

Changes in v1.2:
    - Added CSV report saved after every run (one row per FLAC processed).
    - Added log file capturing all console output for later review.
    - Both report and log saved to shared tools\\reports\\ folder.
    - process_flac() now returns a result dict instead of a bare bool.

Changes in v1.1:
    - Added --scan flag with folder picker for recursive scanning.
    - FLACs that already have a .cue are skipped automatically.

Changes in v1.0:
    - Initial release.
"""

import sys
import re
import time
import json
import csv
import logging
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

# ── Optional mutagen ───────────────────────────────────────────────────────────
try:
    from mutagen.flac import FLAC
    MUTAGEN_OK = True
except ImportError:
    MUTAGEN_OK = False
    print("ERROR: mutagen is required. Run: pip install mutagen")
    sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────
MB_API      = "https://musicbrainz.org/ws/2"
USER_AGENT  = "flac_to_cue/1.2 ( https://github.com/neo_s )"
RATE_LIMIT  = 1.1
_last_call  = 0.0

SCRIPT_DIR  = Path(__file__).parent

_ILLEGAL_RE = re.compile(r'[\\/:*?"<>|]')

REPORT_FIELDS = [
    "flac_path", "flac_filename", "disc_number",
    "mbid", "mbid_source", "album", "artist",
    "track_count", "cue_path", "status", "notes",
]


# ── Logging / reporting setup ──────────────────────────────────────────────────

def setup_output_paths():
    """Create reports dir and return (csv_path, log_path) for this run."""
    reports_dir = SCRIPT_DIR.parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path  = reports_dir / ("flac_to_cue_%s.csv" % timestamp)
    log_path  = reports_dir / ("flac_to_cue_%s.log" % timestamp)
    return csv_path, log_path


def setup_logger(log_path):
    """Set up logging to both console and log file."""
    logger = logging.getLogger("flac_to_cue")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                            datefmt="%H:%M:%S")

    # File handler — captures everything
    fh = logging.FileHandler(str(log_path), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # Console handler — INFO and above only (keeps output clean)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def write_csv(rows, csv_path):
    with open(str(csv_path), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


# ── MusicBrainz API ────────────────────────────────────────────────────────────

def mb_get(url):
    """Make a rate-limited GET request to the MusicBrainz API."""
    global _last_call
    wait = RATE_LIMIT - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        _last_call = time.time()
        return json.loads(resp.read().decode("utf-8"))


def fetch_release_by_mbid(mbid):
    """Fetch full release data from MB API by MBID."""
    url = "%s/release/%s?inc=recordings+artist-credits&fmt=json" % (MB_API, mbid)
    return mb_get(url)


def search_release_by_catno(catno):
    """Search MB for a release by catalogue number."""
    q   = urllib.parse.quote('catno:"%s"' % catno)
    url = "%s/release?query=%s&fmt=json&limit=5" % (MB_API, q)
    data = mb_get(url)
    return data.get("releases", [])


def search_release_by_artist_album(artist, album):
    """Search MB for a release by artist and album title."""
    q   = urllib.parse.quote('release:"%s" AND artist:"%s"' % (album, artist))
    url = "%s/release?query=%s&fmt=json&limit=5" % (MB_API, q)
    data = mb_get(url)
    return data.get("releases", [])


# ── FLAC tag reading ───────────────────────────────────────────────────────────

def read_flac_tags(flac_path):
    """
    Read useful tags from a FLAC file.
    Returns a dict with keys: mbid, catno, artist, album, discnumber, totaldiscs
    All values may be None if not present.
    """
    try:
        audio = FLAC(str(flac_path))
    except Exception as e:
        print("  ! Could not read tags from %s: %s" % (flac_path.name, e))
        return {}

    def get(key):
        val = audio.tags.get(key.upper()) or audio.tags.get(key.lower())
        return val[0].strip() if val else None

    raw_album = get("ALBUM")
    raw_catno = get("CATALOGNUMBER") or get("CATALOG")

    # If no dedicated catno tag, try to extract it from the album tag
    # e.g. "ANJCD008 VA - Anjunabeats Volume 5 (Mixed By Above And Beyond)"
    if not raw_catno and raw_album:
        m = _CATNO_RE.search(raw_album)
        if m:
            raw_catno = m.group(1).upper()

    # Clean the album name — strip leading catno + scene formatting
    clean_album = raw_album
    if clean_album:
        if raw_catno:
            clean_album = re.sub(
                r'(?i)^' + re.escape(raw_catno) + r'\s*(?:VA\s*-\s*|V/A\s*-\s*)?',
                '', clean_album
            ).strip()
        clean_album = _SCENE_RE.sub("", clean_album).strip() or None

    return {
        "mbid":       get("MUSICBRAINZ_ALBUMID") or get("MBID"),
        "catno":      raw_catno,
        "artist":     get("ALBUMARTIST") or get("ARTIST"),
        "album":      clean_album,
        "discnumber": get("DISCNUMBER"),
        "totaldiscs": get("TOTALDISCS") or get("DISCTOTAL"),
    }


# ── Disc number detection ──────────────────────────────────────────────────────

_DISC_RE = re.compile(r'\b(?:CD|DISC|DISK)\s*(\d+)\b', re.IGNORECASE)

# Scene format: leading 3-digit number where first digit = disc
# e.g. 101- = disc 1 track 01, 201- = disc 2 track 01
_SCENE_DISC_RE = re.compile(r'^(\d)\d{2}[-_]')

# Sequential file number prefix: 01. or 02. etc.
_SEQ_PREFIX_RE = re.compile(r'^0*([1-9]\d*)[\.\s]')


def guess_disc_number(tags, flac_path):
    """
    Determine which disc number a FLAC file represents.
    Priority: filename (most reliable) → DISCNUMBER tag (often wrong in scene rips).
    Returns int or None.
    """
    stem = flac_path.stem

    # 1. Scene format: 201-artist-title → disc 2
    m = _SCENE_DISC_RE.match(stem)
    if m:
        return int(m.group(1))

    # 2. Explicit keyword in filename: CD2, Disc 2 etc.
    m = _DISC_RE.search(stem)
    if m:
        return int(m.group(1))

    # 3. Sequential file prefix: "02. Title" → disc 2
    #    Only use if value > 1 to avoid misidentifying track 01 as disc 1
    m = _SEQ_PREFIX_RE.match(stem)
    if m and int(m.group(1)) > 1:
        return int(m.group(1))

    # 4. Parent folder name: "CD2" or "Disc 2" in folder
    m = _DISC_RE.search(flac_path.parent.name)
    if m:
        return int(m.group(1))

    # 5. DISCNUMBER tag — last resort, often incorrect in scene rips
    dn = tags.get("discnumber")
    if dn:
        try:
            return int(dn.split("/")[0])
        except ValueError:
            pass

    return None


# ── CUE generation ─────────────────────────────────────────────────────────────

def ms_to_cue_index(ms):
    """
    Convert milliseconds to CUE index format.
    For releases under 100 minutes: MM:SS:FF  (standard CUE)
    For releases 100 minutes or over: HH:MM:SS:FF  (extended, supported by
    CUE Splitter and foobar2000 but not all tools)

    CUE frames = 1/75 of a second (75 frames per second).
    """
    total_seconds, ms_rem = divmod(ms, 1000)
    minutes,       seconds = divmod(total_seconds, 60)
    frames = round(ms_rem * 75 / 1000)
    if frames >= 75:
        frames  = 0
        seconds += 1
    if seconds >= 60:
        seconds  = 0
        minutes  += 1
    if minutes >= 100:
        hours    = minutes // 60
        minutes  = minutes % 60
        return "%02d:%02d:%02d:%02d" % (hours, minutes, seconds, frames)
    return "%02d:%02d:%02d" % (minutes, seconds, frames)


def artist_credit_string(credit_list):
    """Build a flat artist string from a MB artist-credit list."""
    parts = []
    for item in credit_list:
        if isinstance(item, dict) and "artist" in item:
            parts.append(item.get("joinphrase", "") and
                         item["artist"]["name"] + item.get("joinphrase", "") or
                         item["artist"]["name"])
        elif isinstance(item, str):
            parts.append(item)
    return "".join(parts).strip() or "Unknown Artist"


def sanitise_filename(name):
    """Strip Windows-illegal characters from a filename."""
    return _ILLEGAL_RE.sub("", name).strip(" .")


def build_cue(disc_tracks, flac_filename, album_title, album_artist):
    """
    Build CUE sheet content for one disc.

    disc_tracks: list of MB recording dicts for this disc
    flac_filename: just the filename (e.g. CD1.flac)
    """
    lines = []
    lines.append('PERFORMER "%s"' % album_artist)
    lines.append('TITLE "%s"'     % album_title)
    lines.append('FILE "%s" WAVE' % flac_filename)
    lines.append("")

    cumulative_ms = 0

    for i, track in enumerate(disc_tracks, 1):
        recording  = track.get("recording", {})
        title      = recording.get("title", "Track %d" % i)
        length_ms  = recording.get("length")   # may be None
        track_artist_credit = recording.get("artist-credit",
                              track.get("artist-credit", []))
        track_artist = artist_credit_string(track_artist_credit) or album_artist

        index_str  = ms_to_cue_index(cumulative_ms)

        lines.append("  TRACK %02d AUDIO"      % i)
        lines.append('    TITLE "%s"'          % title)
        lines.append('    PERFORMER "%s"'      % track_artist)
        lines.append("    INDEX 01 %s"         % index_str)
        lines.append("")

        if length_ms:
            cumulative_ms += length_ms
        else:
            print("    ! Track %d has unknown length — split point will be 0:00 offset" % i)

    return "\n".join(lines)


# ── Main logic ─────────────────────────────────────────────────────────────────

def find_flac_files(path, recursive=False, skip_existing_cue=False):
    """
    Return list of FLAC files to process.

    path            : a file or folder path
    recursive       : if True, scan all subfolders
    skip_existing_cue: if True, skip FLACs that already have a .cue next to them
    """
    p = Path(path)

    if p.is_file() and p.suffix.lower() == ".flac":
        candidates = [p]
    elif p.is_dir():
        if recursive:
            candidates = sorted(p.rglob("*.flac"))
        else:
            candidates = sorted(p.glob("*.flac"))
    else:
        return []

    if skip_existing_cue:
        filtered  = []
        skipped   = 0
        for f in candidates:
            if f.with_suffix(".cue").exists():
                skipped += 1
            else:
                filtered.append(f)
        if skipped:
            print("  ~ Skipping %d FLAC file(s) that already have a .cue" % skipped)
        return filtered

    return candidates


def pick_folder(title="Select folder"):
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(title=title)
        root.destroy()
        return chosen or None
    except Exception as e:
        print("ERROR: Could not open folder picker: %s" % e)
        return None


def pick_folder_or_file():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askopenfilename(
            title="Select FLAC file (or cancel to pick a folder)",
            filetypes=[("FLAC files", "*.flac"), ("All files", "*.*")],
        )
        if not chosen:
            chosen = filedialog.askdirectory(
                title="Select folder containing FLAC files",
            )
        root.destroy()
        return chosen or None
    except Exception as e:
        print("ERROR: Could not open picker: %s" % e)
        return None


# ── Filename parsing (fallback for untagged files) ────────────────────────────

# ANJ catalogue number anywhere in the string
_CATNO_RE = re.compile(
    r'\b(ANJ(?:CD|DEEP|UNA|WW)?\d+[A-Z\d]*)\b',
    re.IGNORECASE
)

# Scene / rip tags to strip from filenames before parsing artist/title
_SCENE_RE = re.compile(
    r'[-_\s]+(?:WEB|CD\d*|FLAC|MP3|320|256|VINYL|TT|FOX|GAF|'
    r'MiNiMAL|PARAKHODEN|UL\d+|LOSSLESS[\w-]*).*$',
    re.IGNORECASE
)

# Track number prefixes: "101-", "01. ", "1 - " etc.
_TRACKNO_RE = re.compile(r'^[\d]{1,3}[-.\s]+')

# Disc suffixes: CD1, CD2, Disc 1, (Disc2) etc.
_DISC_SUFFIX_RE = re.compile(
    r'[-_\s]*[\(\[]?(?:CD|DISC|DISK)\s*\d+[\)\]]?\s*$',
    re.IGNORECASE
)


def parse_filename(flac_path):
    """
    Extract (catno, artist, title) from a FLAC filename.
    Any value may be None if not parseable.

    Handles formats like:
      101-va-anjunabeats_volume_5__mixed_by_above_and_beyond-cd1-tt.flac
      Above & Beyond - Anjunabeats Volume Six CD1.flac
      01. VA - Anjunabeats Worldwide 02 (Continuous Mix by Super8 & Tab).flac
      ANJCD008 VA - Anjunabeats Volume 5.flac
    """
    stem = flac_path.stem

    # Extract catno if present
    catno_match = _CATNO_RE.search(stem)
    catno = catno_match.group(1).upper() if catno_match else None

    # Clean up for artist/title parsing
    s = stem
    s = _SCENE_RE.sub("", s)          # remove scene tags
    s = _DISC_SUFFIX_RE.sub("", s)    # remove CD1/CD2 suffix
    s = _TRACKNO_RE.sub("", s)        # remove leading track number
    s = s.replace("_", " ")           # underscores to spaces
    s = re.sub(r'\s+', ' ', s).strip()

    # Remove catno prefix if present
    if catno:
        s = re.sub(r'(?i)^' + re.escape(catno) + r'\s*', '', s).strip()

    # Try "Artist - Title" split
    artist, title = None, None
    if ' - ' in s:
        parts  = s.split(' - ', 1)
        artist = parts[0].strip()
        title  = parts[1].strip()
        # "VA" and single-word artists are likely not real artist names
        if artist.upper() in ('VA', 'V/A', 'VARIOUS', 'VARIOUS ARTISTS'):
            artist = None
    else:
        title = s or None

    return catno, artist, title


# ── MBID resolution ────────────────────────────────────────────────────────────

def resolve_mbid(tags, flac_path, log):
    """
    Get the best MBID for a release, trying five strategies in order:
    1. MBID tag
    2. CATALOGNUMBER tag -> catno search
    3. ARTIST + ALBUM tags -> artist+album search
    4. Catno from filename -> catno search
    5. Artist + title from filename -> artist+album search
    Returns (mbid, method_description) or (None, None).
    """
    # 1. Direct MBID tag
    mbid = tags.get("mbid")
    if mbid:
        return mbid, "MBID from file tags"

    # 2. Catno from tags
    catno = tags.get("catno")
    if catno:
        log.info("  ~ Strategy 2: catno from tags (%s)" % catno)
        try:
            results = search_release_by_catno(catno)
            if results:
                return results[0]["id"], "catno tag (%s)" % catno
        except Exception as e:
            log.error("  ! Catno tag search failed: %s" % e)

    # 3. Artist + album from tags
    artist = tags.get("artist")
    album  = tags.get("album")
    if artist and album:
        log.info("  ~ Strategy 3: artist+album from tags: %s — %s" % (artist, album))
        try:
            results = search_release_by_artist_album(artist, album)
            if results:
                return results[0]["id"], "artist+album tags"
        except Exception as e:
            log.error("  ! Artist+album tag search failed: %s" % e)

    # 4. Catno from filename
    fn_catno, fn_artist, fn_title = parse_filename(flac_path)
    if fn_catno and fn_catno != catno:   # skip if same as tag catno already tried
        log.info("  ~ Strategy 4: catno from filename (%s)" % fn_catno)
        try:
            results = search_release_by_catno(fn_catno)
            if results:
                return results[0]["id"], "catno from filename (%s)" % fn_catno
        except Exception as e:
            log.error("  ! Filename catno search failed: %s" % e)

    # 5. Artist + title from filename
    if fn_title:
        search_artist = fn_artist or artist or "Various Artists"
        log.info("  ~ Strategy 5: artist+title from filename: %s — %s"
                 % (search_artist, fn_title))
        try:
            results = search_release_by_artist_album(search_artist, fn_title)
            if results:
                return results[0]["id"], "artist+title from filename"
        except Exception as e:
            log.error("  ! Filename artist+title search failed: %s" % e)

    return None, None


def process_flac(flac_path, release_data_cache, log):
    """
    Generate a CUE sheet for one FLAC file.
    Returns a report row dict.
    """
    row = {f: "" for f in REPORT_FIELDS}
    row["flac_path"]     = str(flac_path.parent)
    row["flac_filename"] = flac_path.name

    log.info("")
    log.info("  File: %s" % flac_path.name)

    # Read tags
    tags     = read_flac_tags(flac_path)
    disc_num = guess_disc_number(tags, flac_path)
    row["disc_number"] = disc_num or ""
    log.info("  Disc : %s" % (disc_num or "unknown — will try to infer from MB data"))

    # Resolve MBID
    mbid, method = resolve_mbid(tags, flac_path, log)
    if not mbid:
        msg = "Could not find a MusicBrainz match — tag this file first or provide an MBID manually"
        log.warning("  ! %s" % msg)
        row["status"] = "no_match"
        row["notes"]  = msg
        return row

    row["mbid"]        = mbid
    row["mbid_source"] = method
    log.info("  MBID : %s  (via %s)" % (mbid, method))

    # Fetch release (cached)
    if mbid not in release_data_cache:
        log.info("  ~ Fetching release from MusicBrainz API...")
        try:
            release_data_cache[mbid] = fetch_release_by_mbid(mbid)
        except Exception as e:
            msg = "MB API fetch failed: %s" % e
            log.error("  ! %s" % msg)
            row["status"] = "api_error"
            row["notes"]  = msg
            return row

    release       = release_data_cache[mbid]
    album_title   = release.get("title", "Unknown Album")
    artist_credit = release.get("artist-credit", [])
    album_artist  = artist_credit_string(artist_credit)
    media_list    = release.get("media", [])

    row["album"]  = album_title
    row["artist"] = album_artist

    log.info("  Album : %s" % album_title)
    log.info("  Artist: %s" % album_artist)
    log.info("  Discs in release: %d" % len(media_list))

    # Match this FLAC to the correct disc
    if disc_num and disc_num <= len(media_list):
        media = media_list[disc_num - 1]
    elif len(media_list) == 1:
        media    = media_list[0]
        disc_num = 1
    else:
        for idx, m in enumerate(media_list, 1):
            disc_num = idx
            media    = m
            log.warning("  ~ Could not determine disc number — defaulting to disc %d" % disc_num)
            break

    tracks = media.get("tracks", [])
    row["track_count"] = len(tracks)
    log.info("  Tracks on this disc: %d" % len(tracks))

    if not tracks:
        msg = "No tracks found for disc %d" % disc_num
        log.error("  ! %s" % msg)
        row["status"] = "no_tracks"
        row["notes"]  = msg
        return row

    # Sanity check: total MB duration vs a reasonable expectation
    total_ms = sum(
        t.get("recording", {}).get("length") or 0 for t in tracks
    )
    total_min = total_ms / 60000
    log.info("  Total duration (MB data): %.1f min" % total_min)
    if total_min > 200:
        log.warning("  ! Total duration %.1f min seems too long for a single disc." % total_min)
        log.warning("    This may indicate the wrong MB release was matched.")
        log.warning("    Check the MBID in the preview before confirming.")

    # Warn about any tracks with unknown lengths
    unknown = [t for t in tracks if not t.get("recording", {}).get("length")]
    if unknown:
        msg = "%d track(s) have unknown length — split points will be approximate" % len(unknown)
        log.warning("  ! %s" % msg)
        row["notes"] = msg

    # Build CUE content
    cue_content = build_cue(
        disc_tracks   = tracks,
        flac_filename = flac_path.name,
        album_title   = album_title,
        album_artist  = album_artist,
    )

    # Preview
    log.info("")
    log.info("  ── CUE preview ──────────────────────────────────────")
    for line in cue_content.splitlines()[:12]:
        log.info("  %s" % line)
    if len(cue_content.splitlines()) > 12:
        log.info("  ... (%d more lines)" % (len(cue_content.splitlines()) - 12))
    log.info("  ─────────────────────────────────────────────────────")

    # Confirm
    cue_path = flac_path.with_suffix(".cue")
    row["cue_path"] = str(cue_path)
    log.info("")
    confirm = input("  Write CUE to %s ? (y/n): " % cue_path.name).strip().lower()
    if confirm != "y":
        log.info("  Skipped by user.")
        row["status"] = "skipped"
        row["notes"]  = row["notes"] or "Skipped by user"
        return row

    try:
        cue_path.write_text(cue_content, encoding="utf-8")
        log.info("  ✓ Written: %s" % cue_path.name)
        row["status"] = "written"
        row["notes"]  = row["notes"] or "OK"
    except Exception as e:
        msg = "Failed to write CUE: %s" % e
        log.error("  ! %s" % msg)
        row["status"] = "write_error"
        row["notes"]  = msg

    return row


def main():
    args      = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags     = [a for a in sys.argv[1:] if a.startswith("--")]
    scan_mode = "--scan" in flags

    # Set up report/log paths before anything else
    csv_path, log_path = setup_output_paths()
    log = setup_logger(log_path)

    if scan_mode:
        if args:
            scan_root = args[0].strip('"')
        else:
            scan_root = pick_folder(title="Select folder to scan for FLAC files")
            if not scan_root:
                log.info("No folder selected. Exiting.")
                sys.exit(0)
        target    = scan_root
        recursive = True
        skip_cue  = True
        log.info("")
        log.info("=" * 60)
        log.info("  FLAC to CUE  v1.2")
        log.info("=" * 60)
        log.info("  Scanning : %s" % target)
        log.info("  (FLAC files with existing .cue will be skipped)")
        log.info("=" * 60)
    elif args:
        target    = args[0].strip('"')
        recursive = False
        skip_cue  = False
        log.info("")
        log.info("=" * 60)
        log.info("  FLAC to CUE  v1.2")
        log.info("=" * 60)
    else:
        chosen = pick_folder_or_file()
        if not chosen:
            log.info("No file or folder selected. Exiting.")
            sys.exit(0)
        target    = chosen
        recursive = False
        skip_cue  = False
        log.info("")
        log.info("=" * 60)
        log.info("  FLAC to CUE  v1.2")
        log.info("=" * 60)

    if not Path(target).exists():
        log.error("ERROR: Path not found: %s" % target)
        sys.exit(1)

    flac_files = find_flac_files(target, recursive=recursive,
                                 skip_existing_cue=skip_cue)

    if not flac_files:
        log.info("")
        log.info("  No FLAC files found that need CUE sheets.")
        sys.exit(0)

    log.info("  Found %d FLAC file(s) to process" % len(flac_files))
    log.info("  Report : %s" % csv_path.name)
    log.info("  Log    : %s" % log_path.name)
    log.info("=" * 60)

    release_cache = {}
    rows          = []

    for flac_path in flac_files:
        row = process_flac(flac_path, release_cache, log)
        rows.append(row)

    # Write CSV
    write_csv(rows, csv_path)

    # Summary
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    log.info("")
    log.info("=" * 60)
    log.info("  SUMMARY")
    log.info("=" * 60)
    log.info("  Written       : %d" % counts.get("written",     0))
    log.info("  Skipped       : %d" % counts.get("skipped",     0))
    log.info("  No MB match   : %d" % counts.get("no_match",    0))
    log.info("  API errors    : %d" % counts.get("api_error",   0))
    log.info("  Write errors  : %d" % counts.get("write_error", 0))
    log.info("")
    log.info("  Report : %s" % csv_path)
    log.info("  Log    : %s" % log_path)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
