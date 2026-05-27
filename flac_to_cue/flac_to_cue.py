"""
Audio to CUE  v2.6
==================
Generates a CUE sheet for an audio file using MusicBrainz data.

Supports: FLAC, WAV, AIFF, MP3, M4A (AAC and Apple Lossless), Ogg Vorbis.

Reads the MusicBrainz Release ID (MBID) from the file's tags, fetches the
tracklist from the MusicBrainz API, and writes a CUE sheet ready to use
with CUETools for splitting.

If no MBID tag is found, falls back through a chain of search strategies:
  1. MBID tag
  2. CATALOGNUMBER tag -> catno search
  3. ARTIST + ALBUM tags -> artist+album search
  4. Catno parsed from filename (ANJCD008, ANJ131 etc.) -> catno search
  5. Artist + title parsed from filename -> artist+album search

Supports multi-disc releases -- generates one CUE per disc, matched to the
correct audio file automatically.

Requirements:
    pip install mutagen requests

Usage:
    python flac_to_cue.py                              # folder/file picker
    python flac_to_cue.py --pick                       # folder/file picker
    python flac_to_cue.py --pick --apply               # pick, then write CUEs
    python flac_to_cue.py --path "C:\\path\\to\\folder"  # all audio in folder
    python flac_to_cue.py --path "C:\\path\\to\\file.flac" --apply
    python flac_to_cue.py --scan                       # folder picker, recursive
    python flac_to_cue.py --scan --apply               # scan and write CUEs
    python flac_to_cue.py --url "https://musicbrainz.org/release/<id>" --pick
    python flac_to_cue.py --url "https://musicbrainz.org/release/<id>" --path "CD1.wav" --apply

--url flag:
    Provide a MusicBrainz release URL directly. The MBID is extracted from
    the URL and used immediately -- the tag-reading and search fallback chain
    are skipped entirely. Useful for untagged WAV files where you already
    know the MB release page.

    Combine with --path (single file or folder) or --pick (file/folder dialog).
    For multi-disc releases, point --path at the folder containing CD1.wav,
    CD2.wav etc. -- each file will be matched to its disc within the release.

Mode:
    Default (no --apply): DRY RUN — scans and resolves MB matches but does
        not write any .cue files. Shows what would be created.
    With --apply: resolves MB matches, shows CUE preview, asks confirmation
        per file, then writes.

Output:
    A .cue file written next to each audio file (in --apply mode):
    CD1.flac  ->  CD1.cue
    CD1.wav   ->  CD1.cue

    Audio files that already have a matching .cue are skipped automatically.

    Reports saved to: <script folder>\\..\\reports\\flac_to_cue_YYYYMMDD_HHMMSS.csv
    Logs saved to:    <script folder>\\..\\reports\\flac_to_cue_YYYYMMDD_HHMMSS.log

Changes in v2.6:
    - PW-01: Extracted run_flac_to_cue() as GUI-callable core function.
      Takes target, apply, recursive, skip_existing_cue, forced_mbid,
      reports_dir, confirm_callback, progress_callback, log_callback.
      Raises ValueError for bad paths instead of sys.exit(1).
      Returns dict: rows, counts, csv_path, log_path, report_path, reports_dir.
    - Moved module-level DRY_RUN, PICK_DIR, SCAN_MODE, _path_flag, _url_flag
      and interactive_options([]) inside main() — no module-level side effects.
    - setup_output_paths() now takes dry_run and optional reports_dir params
      (removes global DRY_RUN dependency).
    - setup_logger() now accepts optional log_callback — routes all log messages
      to the GUI via a custom logging.Handler (no double-routing).
    - process_audio() now takes dry_run=True and confirm_callback=None params;
      confirm_callback(cue_path) -> bool replaces the inline input() call so
      the GUI can supply a dialog. CLI main() passes its own lambda.
      When confirm_callback is None, writes are auto-confirmed (GUI pre-confirms).

Changes in v2.2:
    - Added --url flag: accepts a MusicBrainz release URL and extracts the
      MBID directly, bypassing the tag-reading and search fallback chain.
      Intended for untagged WAV files where the MB release page is known.
      Supersedes the separate mbz2cue.py script (which used HTML scraping);
      this implementation uses the proper MB JSON API.

Changes in v2.1:
    - Fixed disc number detection for files whose name begins with a high track
      number (e.g. "18 - Title.mp3" inside a CD2 folder). Previously the
      sequential prefix check (step 3) returned 18 as the disc number before the
      parent folder check (step 4) could return the correct value of 2. The
      priority order is now: scene prefix → keyword in filename → parent folder
      keyword → sequential prefix (capped at ≤ 10) → DISCNUMBER tag.

Changes in v2.0:
    - Added support for WAV, AIFF, MP3, M4A (AAC and Apple Lossless), and
      Ogg Vorbis in addition to FLAC. mutagen.File() now auto-detects the
      format and routes tag reading through format-appropriate logic
      (VorbisComment for FLAC/OGG, ID3 for MP3/AIFF/WAV, MP4 tags for M4A).
    - Added audio_format column to CSV report.
    - Added dry-run mode (default). Pass --apply to write CUE files.
    - Replaced combined menu .cmd with two standard .cmd launchers:
      "Run - FLAC to CUE (Dry Run).cmd" and "Run - FLAC to CUE (Apply).cmd".
    - Internal variables renamed from flac_* to audio_* for clarity.
    - File picker now includes all supported audio formats.

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
      if the matched disc has an unexpected number of tracks.
    - CUE preview now shows total duration so you can spot obvious mismatches.

Changes in v1.3:
    - Added filename parsing as fallback strategies 4 and 5.
    - Fixed log message bug: search strings now accurately reflect what is
      actually being sent to the MB API.
    - parse_filename() strips scene tags, track number prefixes, and disc
      suffixes before searching.

Changes in v1.2:
    - Added CSV report saved after every run (one row per file processed).
    - Added log file capturing all console output for later review.
    - Both report and log saved to shared tools\\reports\\ folder.
    - process_audio() now returns a result dict instead of a bare bool.

Changes in v1.1:
    - Added --scan flag with folder picker for recursive scanning.
    - Files that already have a .cue are skipped automatically.

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

sys.path.insert(0, str(Path(__file__).parent.parent))
from music_tools_common import pick_folder
from music_tools_common import interactive_options

# ── Optional mutagen ───────────────────────────────────────────────────────────
try:
    import mutagen
    from mutagen.id3 import ID3
    from mutagen.mp4 import MP4Tags
    MUTAGEN_OK = True
except ImportError:
    MUTAGEN_OK = False
    print("ERROR: mutagen is required. Run: pip install mutagen")
    sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────
MB_API      = "https://musicbrainz.org/ws/2"
USER_AGENT  = "flac_to_cue/2.1 ( https://github.com/neo_s )"
RATE_LIMIT  = 1.1
_last_call  = 0.0

SCRIPT_DIR  = Path(__file__).parent

_ILLEGAL_RE = re.compile(r'[\\/:*?"<>|]')

# MusicBrainz release UUID pattern (used to extract MBID from a URL)
_MBID_RE = re.compile(
    r'/release/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
    re.IGNORECASE,
)

# Supported audio formats (extensions without the dot)
AUDIO_EXTENSIONS = {".flac", ".wav", ".aiff", ".aif", ".mp3", ".m4a", ".ogg"}

REPORT_FIELDS = [
    "audio_path", "audio_filename", "audio_format", "disc_number",
    "mbid", "mbid_source", "album", "artist",
    "track_count", "cue_path", "status", "notes",
]


# ── Logging / reporting setup ──────────────────────────────────────────────────

def setup_output_paths(dry_run, reports_dir=None):
    """Create reports dir and return (csv_path, log_path) for this run."""
    if reports_dir is None:
        reports_dir = SCRIPT_DIR / "reports"
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix    = "dry" if dry_run else "applied"
    csv_path  = reports_dir / ("flac_to_cue_%s_%s.csv" % (suffix, timestamp))
    log_path  = reports_dir / ("flac_to_cue_%s_%s.log" % (suffix, timestamp))
    return csv_path, log_path


def setup_logger(log_path, log_callback=None):
    """Set up logging to console, log file, and optional GUI callback."""
    logger = logging.getLogger("flac_to_cue")
    logger.setLevel(logging.DEBUG)
    # Clear any handlers from a previous run (important when called from GUI)
    logger.handlers.clear()

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

    # GUI callback handler — routes INFO+ messages to the caller
    if log_callback:
        class _CallbackHandler(logging.Handler):
            def emit(self, record):
                try:
                    log_callback(self.format(record))
                except Exception:
                    pass
        cbh = _CallbackHandler()
        cbh.setLevel(logging.INFO)
        cbh.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(cbh)

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


# ── Audio tag reading ──────────────────────────────────────────────────────────

# ID3 frame ID map (MP3, AIFF, WAV-with-ID3)
_ID3_MAP = {
    "MUSICBRAINZ_ALBUMID": ["TXXX:MusicBrainz Album Id",
                            "TXXX:MUSICBRAINZ ALBUM ID"],
    "MBID":                ["TXXX:MusicBrainz Album Id"],
    "CATALOGNUMBER":       ["TXXX:CATALOGNUMBER", "TXXX:CatalogNumber"],
    "CATALOG":             ["TXXX:CATALOG"],
    "ALBUMARTIST":         ["TPE2"],
    "ARTIST":              ["TPE1"],
    "ALBUM":               ["TALB"],
    "DISCNUMBER":          ["TPOS"],   # often "disc/total"
    "TOTALDISCS":          ["TPOS"],
    "DISCTOTAL":           ["TPOS"],
}

# MP4 atom map (M4A — AAC and Apple Lossless share the same container)
_MP4_MAP = {
    "MUSICBRAINZ_ALBUMID": [
        "----:com.apple.iTunes:MusicBrainz Album Id",
        "----:com.apple.iTunes:MUSICBRAINZ_ALBUMID",
    ],
    "MBID":          ["----:com.apple.iTunes:MusicBrainz Album Id"],
    "CATALOGNUMBER": ["----:com.apple.iTunes:CATALOGNUMBER",
                      "----:com.apple.iTunes:CatalogNumber"],
    "CATALOG":       ["----:com.apple.iTunes:CATALOG"],
    "ALBUMARTIST":   ["aART"],
    "ARTIST":        ["\xa9ART"],   # ©ART
    "ALBUM":         ["\xa9alb"],   # ©alb
    "DISCNUMBER":    ["disk"],      # tuple (discnum, totaldiscs)
    "TOTALDISCS":    ["disk"],
    "DISCTOTAL":     ["disk"],
}


def read_audio_tags(audio_path):
    """
    Read useful tags from an audio file using mutagen's format auto-detection.

    Handles:
      - FLAC, Ogg Vorbis  → VorbisComment (dict-like, uppercase keys)
      - MP3, AIFF, WAV    → ID3 frames
      - M4A (AAC / ALAC)  → MP4 atoms

    Returns a dict with keys: mbid, catno, artist, album, discnumber, totaldiscs.
    All values may be None if not present or the format has no embedded tags.
    """
    try:
        audio = mutagen.File(str(audio_path))
    except Exception as e:
        print("  ! Could not read tags from %s: %s" % (audio_path.name, e))
        return {}

    if audio is None or audio.tags is None:
        # Format not recognised, or file has no embedded tags at all —
        # fall back to filename parsing (handled by resolve_mbid).
        return {}

    tags = audio.tags

    # ── Build a format-appropriate tag getter ──────────────────────────────────

    if isinstance(tags, ID3):
        # MP3, AIFF, WAV-with-ID3
        def get(key):
            for frame_id in _ID3_MAP.get(key.upper(), []):
                frame = tags.get(frame_id)
                if frame is None:
                    continue
                text = (frame.text[0] if hasattr(frame, "text") and frame.text
                        else str(frame))
                text = str(text).strip()
                if not text:
                    continue
                # TPOS carries "disc/total" — split accordingly
                if "/" in text:
                    if key.upper() in ("TOTALDISCS", "DISCTOTAL"):
                        text = text.split("/", 1)[1]
                    else:
                        text = text.split("/", 1)[0]
                return text or None
            return None

    elif isinstance(tags, MP4Tags):
        # M4A (AAC and Apple Lossless share the same container format)
        def get(key):
            for atom_key in _MP4_MAP.get(key.upper(), []):
                val = tags.get(atom_key)
                if val is None:
                    continue
                v = val[0] if isinstance(val, (list, tuple)) and val else val
                # disk atom returns a (discnum, totaldiscs) tuple
                if atom_key == "disk" and isinstance(v, tuple):
                    if key.upper() in ("TOTALDISCS", "DISCTOTAL"):
                        return str(v[1]) if len(v) > 1 and v[1] else None
                    return str(v[0]) if v[0] else None
                # Freeform atoms (----:...) return MP4FreeForm (bytes-like)
                if hasattr(v, "decode"):
                    return v.decode("utf-8", errors="replace").strip() or None
                return str(v).strip() or None
            return None

    else:
        # VorbisComment (FLAC, Ogg Vorbis) and other dict-like tag containers
        def get(key):
            val = tags.get(key.upper()) or tags.get(key.lower())
            return val[0].strip() if val else None

    # ── Extract fields (format-independent from here) ──────────────────────────

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


def guess_disc_number(tags, audio_path):
    """
    Determine which disc number an audio file represents.
    Priority: filename (most reliable) → DISCNUMBER tag (often wrong in scene rips).
    Returns int or None.
    """
    stem = audio_path.stem

    # 1. Scene format: 201-artist-title → disc 2
    m = _SCENE_DISC_RE.match(stem)
    if m:
        return int(m.group(1))

    # 2. Explicit keyword in filename: CD2, Disc 2 etc.
    m = _DISC_RE.search(stem)
    if m:
        return int(m.group(1))

    # 3. Parent folder name: "CD2" or "Disc 2" in folder
    #    Checked before the sequential prefix so that files named "18 - Title"
    #    (track number prefix) inside a "CD2" folder are correctly identified
    #    as disc 2 rather than disc 18.
    m = _DISC_RE.search(audio_path.parent.name)
    if m:
        return int(m.group(1))

    # 4. Sequential file prefix: "02. Title" → disc 2
    #    Only use if value is > 1 (avoids misidentifying track 01 as disc 1)
    #    and <= 10 (avoids misidentifying high track numbers like 18 as disc 18).
    m = _SEQ_PREFIX_RE.match(stem)
    if m:
        n = int(m.group(1))
        if 1 < n <= 10:
            return n

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


def build_cue(disc_tracks, audio_filename, album_title, album_artist):
    """
    Build CUE sheet content for one disc.

    disc_tracks:    list of MB recording dicts for this disc
    audio_filename: just the filename (e.g. CD1.flac or CD1.wav)
    """
    lines = []
    lines.append('PERFORMER "%s"' % album_artist)
    lines.append('TITLE "%s"'     % album_title)
    lines.append('FILE "%s" WAVE' % audio_filename)
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

def find_audio_files(path, recursive=False, skip_existing_cue=False):
    """
    Return list of supported audio files to process.

    path              : a file or folder path
    recursive         : if True, scan all subfolders
    skip_existing_cue : if True, skip files that already have a .cue next to them
    """
    p = Path(path)

    if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS:
        candidates = [p]
    elif p.is_dir():
        if recursive:
            candidates = sorted(
                f for f in p.rglob("*")
                if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
            )
        else:
            candidates = sorted(
                f for f in p.glob("*")
                if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
            )
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
            print("  ~ Skipping %d audio file(s) that already have a .cue" % skipped)
        return filtered

    return candidates


def pick_folder_or_file():
    """Open a picker for a single audio file (any supported format) or a folder."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askopenfilename(
            title="Select audio file (or cancel to pick a folder)",
            filetypes=[
                ("Audio files",
                 "*.flac *.wav *.aiff *.aif *.mp3 *.m4a *.ogg"),
                ("FLAC files",  "*.flac"),
                ("WAV files",   "*.wav *.aiff *.aif"),
                ("MP3 files",   "*.mp3"),
                ("M4A files",   "*.m4a"),
                ("Ogg files",   "*.ogg"),
                ("All files",   "*.*"),
            ],
        )
        if not chosen:
            chosen = filedialog.askdirectory(
                title="Select folder containing audio files",
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


def parse_filename(audio_path):
    """
    Extract (catno, artist, title) from an audio filename.
    Any value may be None if not parseable.

    Handles formats like:
      101-va-anjunabeats_volume_5__mixed_by_above_and_beyond-cd1-tt.flac
      Above & Beyond - Anjunabeats Volume Six CD1.wav
      01. VA - Anjunabeats Worldwide 02 (Continuous Mix by Super8 & Tab).mp3
      ANJCD008 VA - Anjunabeats Volume 5.m4a
    """
    stem = audio_path.stem

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

def extract_mbid_from_url(url):
    """
    Extract a MusicBrainz Release MBID (UUID) from a MB release URL.

    Accepts any of:
        https://musicbrainz.org/release/abc12345-...
        https://musicbrainz.org/release/abc12345-.../disc/1

    Returns the UUID string, or None if no valid MBID is found.
    """
    m = _MBID_RE.search(url)
    return m.group(1) if m else None


def resolve_mbid(tags, audio_path, log):
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
    fn_catno, fn_artist, fn_title = parse_filename(audio_path)
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


def process_audio(audio_path, release_data_cache, log,
                  dry_run=True, forced_mbid=None, confirm_callback=None):
    """
    Generate a CUE sheet for one audio file.
    In dry_run mode: resolves the MB match and shows a preview, but does not write.
    In apply mode: calls confirm_callback(cue_path) -> bool, then writes if True.

    forced_mbid    : if provided (via --url flag), skip tag reading and the
                     search fallback chain and use this MBID directly.
    confirm_callback: callable(cue_path) -> bool, or None.
                     CLI passes an input()-based lambda; GUI passes None
                     (meaning the caller pre-confirmed, so write unconditionally).

    Returns a report row dict.
    """
    row = {f: "" for f in REPORT_FIELDS}
    row["audio_path"]     = str(audio_path.parent)
    row["audio_filename"] = audio_path.name
    row["audio_format"]   = audio_path.suffix.lower().lstrip(".")

    log.info("")
    log.info("  File  : %s" % audio_path.name)
    log.info("  Format: %s" % row["audio_format"].upper())

    # Read tags
    tags     = read_audio_tags(audio_path)
    disc_num = guess_disc_number(tags, audio_path)
    row["disc_number"] = disc_num or ""
    log.info("  Disc  : %s" % (disc_num or "unknown — will try to infer from MB data"))

    # Resolve MBID — use forced value from --url if provided, otherwise search
    if forced_mbid:
        mbid   = forced_mbid
        method = "MB URL (--url)"
    else:
        mbid, method = resolve_mbid(tags, audio_path, log)

    if not mbid:
        msg = "Could not find a MusicBrainz match — tag this file first or provide a URL with --url"
        log.warning("  ! %s" % msg)
        row["status"] = "no_match"
        row["notes"]  = msg
        return row

    row["mbid"]        = mbid
    row["mbid_source"] = method
    log.info("  MBID  : %s  (via %s)" % (mbid, method))

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

    # Match this file to the correct disc
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
        disc_tracks    = tracks,
        audio_filename = audio_path.name,
        album_title    = album_title,
        album_artist   = album_artist,
    )

    # Preview (shown in both dry-run and apply modes)
    log.info("")
    log.info("  ── CUE preview ──────────────────────────────────────")
    for line in cue_content.splitlines()[:12]:
        log.info("  %s" % line)
    if len(cue_content.splitlines()) > 12:
        log.info("  ... (%d more lines)" % (len(cue_content.splitlines()) - 12))
    log.info("  ─────────────────────────────────────────────────────")

    cue_path = audio_path.with_suffix(".cue")
    row["cue_path"] = str(cue_path)

    # ── Dry-run: report match but do not write ─────────────────────────────────
    if dry_run:
        log.info("  [DRY RUN] Would write: %s" % cue_path.name)
        row["status"] = "dry_run"
        row["notes"]  = row["notes"] or "Match found — run with --apply to write"
        return row

    # ── Apply: confirm per file (via callback), then write ─────────────────────
    log.info("")
    if confirm_callback is not None:
        confirmed = confirm_callback(cue_path)
    else:
        confirmed = True  # GUI pre-confirms before calling; auto-proceed
    if not confirmed:
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


def run_flac_to_cue(
    target,
    apply=False,
    recursive=False,
    skip_existing_cue=False,
    forced_mbid=None,
    reports_dir=None,
    confirm_callback=None,
    progress_callback=None,
    log_callback=None,
):
    """
    GUI-callable core for Audio to CUE.

    Parameters
    ----------
    target            : str or Path — audio file or folder to process.
    apply             : bool — False = dry run (default), True = write CUE files.
    recursive         : bool — scan subfolders recursively (--scan mode).
    skip_existing_cue : bool — skip audio files that already have a .cue next to them.
    forced_mbid       : str or None — use this MBID directly, skipping tag/search
                        fallback (equivalent to --url on the CLI).
    reports_dir       : Path or None — override the default reports directory.
    confirm_callback  : callable(cue_path: Path) -> bool, or None.
                        Called before writing each CUE in apply mode.
                        Return True to write, False to skip.
                        If None, writes are auto-confirmed (GUI pre-confirms).
    progress_callback : callable(current: int, total: int, filename: str) or None.
    log_callback      : callable(message: str) or None — receives all INFO+ log lines.

    Returns
    -------
    dict with keys:
        rows        — list of report row dicts (one per audio file processed)
        counts      — dict mapping status string to count
        csv_path    — Path to the CSV report written this run
        log_path    — Path to the log file written this run
        report_path — alias for csv_path (PW-01 convention)
        reports_dir — Path to the reports directory used
    """
    target = Path(target)
    if not target.exists():
        raise ValueError("Path not found: %s" % target)
    if not (target.is_file() or target.is_dir()):
        raise ValueError("Path is not a file or directory: %s" % target)

    dry_run = not apply

    csv_path, log_path = setup_output_paths(dry_run, reports_dir)
    log = setup_logger(log_path, log_callback=log_callback)

    mode_label = ("DRY RUN — no files will be written" if dry_run
                  else "APPLY — CUE files will be written")

    log.info("")
    log.info("=" * 60)
    log.info("  Audio to CUE  v2.6")
    log.info("=" * 60)
    log.info("  Mode    : %s" % mode_label)
    if forced_mbid:
        log.info("  MBID    : %s  (from --url)" % forced_mbid)
    if recursive:
        log.info("  Scanning: %s" % target)
        log.info("  (audio files with existing .cue will be skipped)")
    else:
        log.info("  Target  : %s" % target)
    log.info("=" * 60)

    audio_files = find_audio_files(target, recursive=recursive,
                                   skip_existing_cue=skip_existing_cue)

    if not audio_files:
        log.info("")
        log.info("  No audio files found that need CUE sheets.")
        return {
            "rows":        [],
            "counts":      {},
            "csv_path":    csv_path,
            "log_path":    log_path,
            "report_path": csv_path,
            "reports_dir": csv_path.parent,
        }

    total = len(audio_files)
    log.info("  Found %d audio file(s) to process" % total)
    log.info("  Report : %s" % csv_path.name)
    log.info("  Log    : %s" % log_path.name)
    log.info("=" * 60)

    release_cache = {}
    rows          = []

    for i, audio_path in enumerate(audio_files, 1):
        if progress_callback:
            progress_callback(i, total, audio_path.name)
        row = process_audio(
            audio_path, release_cache, log,
            dry_run=dry_run,
            forced_mbid=forced_mbid,
            confirm_callback=confirm_callback,
        )
        rows.append(row)

    write_csv(rows, csv_path)

    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    log.info("")
    log.info("=" * 60)
    log.info("  SUMMARY (%s)" % ("DRY RUN" if dry_run else "APPLIED"))
    log.info("=" * 60)
    if dry_run:
        log.info("  Would write   : %d" % counts.get("dry_run",     0))
    else:
        log.info("  Written       : %d" % counts.get("written",     0))
        log.info("  Skipped       : %d" % counts.get("skipped",     0))
    log.info("  No MB match   : %d" % counts.get("no_match",    0))
    log.info("  API errors    : %d" % counts.get("api_error",   0))
    if not dry_run:
        log.info("  Write errors  : %d" % counts.get("write_error", 0))
    log.info("")
    log.info("  Report : %s" % csv_path)
    log.info("  Log    : %s" % log_path)
    log.info("=" * 60)
    if dry_run:
        log.info("")
        log.info("  This was a DRY RUN. Re-run with --apply to write CUE files.")
        log.info("=" * 60)

    return {
        "rows":        rows,
        "counts":      counts,
        "csv_path":    csv_path,
        "log_path":    log_path,
        "report_path": csv_path,
        "reports_dir": csv_path.parent,
    }


def main():
    # ── Flag parsing ───────────────────────────────────────────────────────────
    DRY_RUN   = "--apply" not in sys.argv
    PICK_DIR  = "--pick"  in sys.argv
    SCAN_MODE = "--scan"  in sys.argv

    _path_flag = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--path" and i + 1 < len(sys.argv)),
        None,
    )

    _url_flag = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--url" and i + 1 < len(sys.argv)),
        None,
    )

    interactive_options([])

    # ── Validate --url if provided ─────────────────────────────────────────────
    forced_mbid = None
    if _url_flag:
        forced_mbid = extract_mbid_from_url(_url_flag)
        if not forced_mbid:
            print("ERROR: Could not extract a MusicBrainz Release ID from the URL.")
            print("       Expected format: https://musicbrainz.org/release/<uuid>")
            print("       Got: %s" % _url_flag)
            sys.exit(1)

    # ── Determine target path ──────────────────────────────────────────────────
    if SCAN_MODE:
        if _path_flag:
            target = _path_flag.strip('"')
        else:
            target = pick_folder(title="Select folder to scan for audio files")
            if not target:
                print("No folder selected. Exiting.")
                sys.exit(0)
        recursive = True
        skip_cue  = True

    elif _path_flag:
        target    = _path_flag.strip('"')
        recursive = False
        skip_cue  = False

    elif PICK_DIR:
        chosen = pick_folder_or_file()
        if not chosen:
            print("No file or folder selected. Exiting.")
            sys.exit(0)
        target    = chosen
        recursive = False
        skip_cue  = False

    else:
        # No flag — fall back to picker (keeps original double-click behaviour)
        chosen = pick_folder_or_file()
        if not chosen:
            print("No file or folder selected. Exiting.")
            sys.exit(0)
        target    = chosen
        recursive = False
        skip_cue  = False

    # ── CLI per-file confirmation callback ────────────────────────────────────
    def cli_confirm(cue_path):
        answer = input("  Write CUE to %s ? (y/n): " % cue_path.name).strip().lower()
        while answer not in ("y", "n"):
            answer = input("  Please enter y or n: ").strip().lower()
        return answer == "y"

    # ── Run ───────────────────────────────────────────────────────────────────
    try:
        run_flac_to_cue(
            target            = target,
            apply             = not DRY_RUN,
            recursive         = recursive,
            skip_existing_cue = skip_cue,
            forced_mbid       = forced_mbid,
            confirm_callback  = cli_confirm if not DRY_RUN else None,
        )
    except ValueError as exc:
        print("ERROR: %s" % exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
und that need CUE sheets.")
        return {
            "rows":        [],
            "counts":      {},
            "csv_path":    csv_path,
            "log_path":    log_path,
            "report_path": csv_path,
            "reports_dir": csv_path.parent,
        }

    total = len(audio_files)
    log.info("  Found %d audio file(s) to process" % total)
    log.info("  Report : %s" % csv_path.name)
    log.info("  Log    : %s" % log_path.name)
    log.info("=" * 60)

    release_cache = {}
    rows          = []

    for i, audio_path in enumerate(audio_files, 1):
        if progress_callback:
            progress_callback(i, total, audio_path.name)
        row = process_audio(
            audio_path, release_cache, log,
            dry_run=dry_run,
            forced_mbid=forced_mbid,
            confirm_callback=confirm_callback,
        )
        rows.append(row)

    write_csv(rows, csv_path)

    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    log.info("")
    log.info("=" * 60)
    log.info("  SUMMARY (%s)" % ("DRY RUN" if dry_run else "APPLIED"))
    log.info("=" * 60)
    if dry_run:
        log.info("  Would write   : %d" % counts.get("dry_run",     0))
    else:
        log.info("  Written       : %d" % counts.get("written",     0))
        log.info("  Skipped       : %d" % counts.get("skipped",     0))
    log.info("  No MB match   : %d" % counts.get("no_match",    0))
    log.info("  API errors    : %d" % counts.get("api_error",   0))
    if not dry_run:
        log.info("  Write errors  : %d" % counts.get("write_error", 0))
    log.info("")
    log.info("  Report : %s" % csv_path)
    log.info("  Log    : %s" % log_path)
    log.info("=" * 60)
    if dry_run:
        log.info("")
        log.info("  This was a DRY RUN. Re-run with --apply to write CUE files.")
        log.info("=" * 60)

    return {
        "rows":        rows,
        "counts":      counts,
        "csv_path":    csv_path,
        "log_path":    log_path,
        "report_path": csv_path,
        "reports_dir": csv_path.parent,
    }


def main():
    # -- Flag parsing -----------------------------------------------------------
    DRY_RUN   = "--apply" not in sys.argv
    PICK_DIR  = "--pick"  in sys.argv
    SCAN_MODE = "--scan"  in sys.argv

    _path_flag = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--path" and i + 1 < len(sys.argv)),
        None,
    )

    _url_flag = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--url" and i + 1 < len(sys.argv)),
        None,
    )

    interactive_options([])

    # -- Validate --url if provided --------------------------------------------
    forced_mbid = None
    if _url_flag:
        forced_mbid = extract_mbid_from_url(_url_flag)
        if not forced_mbid:
            print("ERROR: Could not extract a MusicBrainz Release ID from the URL.")
            print("       Expected format: https://musicbrainz.org/release/<uuid>")
            print("       Got: %s" % _url_flag)
            sys.exit(1)

    # -- Determine target path -------------------------------------------------
    if SCAN_MODE:
        if _path_flag:
            target = _path_flag.strip('"')
        else:
            target = pick_folder(title="Select folder to scan for audio files")
            if not target:
                print("No folder selected. Exiting.")
                sys.exit(0)
        recursive = True
        skip_cue  = True

    elif _path_flag:
        target    = _path_flag.strip('"')
        recursive = False
        skip_cue  = False

    elif PICK_DIR:
        chosen = pick_folder_or_file()
        if not chosen:
            print("No file or folder selected. Exiting.")
            sys.exit(0)
        target    = chosen
        recursive = False
        skip_cue  = False

    else:
        # No flag -- fall back to picker (keeps original double-click behaviour)
        chosen = pick_folder_or_file()
        if not chosen:
            print("No file or folder selected. Exiting.")
            sys.exit(0)
        target    = chosen
        recursive = False
        skip_cue  = False

    # -- CLI per-file confirmation callback ------------------------------------
    def cli_confirm(cue_path):
        answer = input("  Write CUE to %s ? (y/n): " % cue_path.name).strip().lower()
        while answer not in ("y", "n"):
            answer = input("  Please enter y or n: ").strip().lower()
        return answer == "y"

    # -- Run -------------------------------------------------------------------
    try:
        run_flac_to_cue(
            target            = target,
            apply             = not DRY_RUN,
            recursive         = recursive,
            skip_existing_cue = skip_cue,
            forced_mbid       = forced_mbid,
            confirm_callback  = cli_confirm if not DRY_RUN else None,
        )
    except ValueError as exc:
        print("ERROR: %s" % exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

    try:
        run_flac_to_cue(
            target            = target,
            apply             = not DRY_RUN,
            recursive         = recursive,
            skip_existing_cue = skip_cue,
            forced_mbid       = forced_mbid,
            confirm_callback  = cli_confirm if not DRY_RUN else None,
        )
    except ValueError as exc:
        print("ERROR: %s" % exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
rint("ERROR: %s" % exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
