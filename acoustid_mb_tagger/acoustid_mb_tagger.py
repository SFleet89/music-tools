#!/usr/bin/env python3
"""
acoustid_mb_tagger.py  v1.0  2026-06-05

Reads ACOUSTID_ID tags (written by acoustid_fingerprint.py), queries the
AcoustID API and MusicBrainz for full metadata, and writes selected tags back
to audio files.

Three-state logic per file:
  no existing tags          → write all selected MB tags
  tags match MB fingerprint → write MB IDs only
  tags differ from MB       → flag for review (or override with --conflict)

All API results are cached in music_cache.db (mb_acoustid_cache table).
The apply pass after a dry run makes zero API calls.

Usage
-----
  python acoustid_mb_tagger.py --pick                          # dry run
  python acoustid_mb_tagger.py --pick --apply                  # write tags
  python acoustid_mb_tagger.py --path "E:\\Music\\..." --apply
  python acoustid_mb_tagger.py --pick --conflict mb_wins --apply

Flags
-----
  --pick                    open a folder picker dialog
  --path "C:\\..."          specify folder directly
  --apply                   write tags (dry run is default)
  --conflict flag           flag files where tags differ from MB (default)
  --conflict mb_wins        MB always overwrites existing tags
  --conflict keep_existing  never overwrite; write MB IDs only

Requirements
------------
  pip install requests mutagen musicbrainzngs
  AcoustID API key in music_config.json → acoustid.api_key
"""

import sys
import json
import time
import sqlite3
from pathlib import Path
from datetime import datetime

# -- Project imports -----------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
from music_tools_common import (
    SUPPORTED_EXTENSIONS, pick_folder, write_csv, load_config,
    DB_PATH, open_db, init_db,
)

# -- Optional deps -------------------------------------------------------------
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import musicbrainzngs
    HAS_MBZ = True
except ImportError:
    HAS_MBZ = False

try:
    from mutagen.flac import FLAC
    from mutagen.id3 import (
        ID3, TIT2, TPE1, TPE2, TALB, TDRC, TRCK, TPOS, TXXX,
    )
    import mutagen.id3
    from mutagen.mp4 import MP4, MP4FreeForm
    from mutagen.oggvorbis import OggVorbis
    from mutagen.oggopus import OggOpus
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

# -- Constants -----------------------------------------------------------------
SCRIPT_DIR      = Path(__file__).parent
REPORTS_DIR     = SCRIPT_DIR / "reports"
MB_USER_AGENT   = ("MusicTools", "1.0", "shrutesh.patel@gmail.com")
MB_RATE_DELAY   = 1.1    # seconds between MB API calls
ACOUSTID_URL    = "https://api.acoustid.org/v2/lookup"
ACOUSTID_DELAY  = 0.35   # seconds between AcoustID API calls

# Formats this script handles (SUPPORTED_EXTENSIONS + opus)
_TAGGABLE = SUPPORTED_EXTENSIONS | {".opus"}

# Logical tag names — groups
CORE_TAGS    = ("title", "artist", "album", "albumartist", "date",
                "tracknumber", "discnumber")
RELEASE_TAGS = ("label", "catalognumber", "country", "releasetype")
MB_ID_TAGS   = ("mb_recordingid", "mb_albumid", "mb_artistid", "mb_albumartistid")
ALL_TAG_KEYS = CORE_TAGS + RELEASE_TAGS + MB_ID_TAGS

# Default: write all core tags + MB recording ID + MB album ID
DEFAULT_TAG_CONFIG = {t: True for t in CORE_TAGS + ("mb_recordingid", "mb_albumid")}
DEFAULT_TAG_CONFIG.update({t: False for t in RELEASE_TAGS + ("mb_artistid", "mb_albumartistid")})

# -- CLI flag parsing ----------------------------------------------------------
DRY_RUN       = "--apply"    not in sys.argv
PICK_DIR      = "--pick"     in sys.argv
_PATH_ARG     = next(
    (sys.argv[i + 1] for i, a in enumerate(sys.argv)
     if a == "--path" and i + 1 < len(sys.argv)),
    None,
)
_CONFLICT_ARG = next(
    (sys.argv[i + 1] for i, a in enumerate(sys.argv)
     if a == "--conflict" and i + 1 < len(sys.argv)),
    "flag",
)


# =============================================================================
#  ACOUSTID_ID TAG READER  (separate from the main tag reader)
# =============================================================================

def _read_acoustid_id(path: Path) -> "str | None":
    """Return the ACOUSTID_ID tag value from any supported file, or None."""
    suffix = path.suffix.lower()
    try:
        if suffix == ".flac":
            audio = FLAC(str(path))
            return _first_tag(audio, "ACOUSTID_ID") or _first_tag(audio, "acoustid_id")
        elif suffix == ".mp3":
            try:
                audio = ID3(str(path))
            except mutagen.id3.ID3NoHeaderError:
                return None
            for key in ("TXXX:AcoustID Id", "TXXX:acoustid_id", "TXXX:ACOUSTID_ID"):
                frame = audio.get(key)
                if frame and frame.text:
                    return str(frame.text[0]).strip() or None
            return None
        elif suffix in (".m4a", ".aac", ".alac"):
            audio = MP4(str(path))
            val = audio.get("----:com.apple.iTunes:AcoustID Id")
            if val:
                item = val[0]
                if isinstance(item, (bytes, MP4FreeForm)):
                    return bytes(item).decode("utf-8", errors="replace").strip() or None
            return None
        elif suffix == ".ogg":
            audio = OggVorbis(str(path))
            return _first_tag(audio, "ACOUSTID_ID") or _first_tag(audio, "acoustid_id")
        elif suffix == ".opus":
            audio = OggOpus(str(path))
            return _first_tag(audio, "ACOUSTID_ID") or _first_tag(audio, "acoustid_id")
    except Exception:
        pass
    return None


# =============================================================================
#  TAG READING — per format
# =============================================================================

def _first_tag(audio, key: str) -> "str | None":
    """Safely get the first value of a multi-valued tag field."""
    val = audio.get(key)
    if isinstance(val, list) and val:
        return str(val[0]).strip() or None
    return None


def _read_tags_from_file(path: Path) -> dict:
    """
    Read current tags from any supported audio file.
    Returns {logical_name: value_or_None} for all ALL_TAG_KEYS.
    """
    tags = {k: None for k in ALL_TAG_KEYS}
    if not HAS_MUTAGEN:
        return tags
    suffix = path.suffix.lower()
    try:
        if suffix == ".flac":
            _vorbis_to_logical(FLAC(str(path)), tags)
        elif suffix == ".mp3":
            try:
                audio = ID3(str(path))
            except mutagen.id3.ID3NoHeaderError:
                return tags
            _id3_to_logical(audio, tags)
        elif suffix in (".m4a", ".aac", ".alac"):
            _mp4_to_logical(MP4(str(path)), tags)
        elif suffix == ".ogg":
            _vorbis_to_logical(OggVorbis(str(path)), tags)
        elif suffix == ".opus":
            _vorbis_to_logical(OggOpus(str(path)), tags)
    except Exception:
        pass
    return tags


def _vorbis_to_logical(audio, tags: dict) -> None:
    """VorbisComment → logical tag dict (FLAC, OGG, Opus)."""
    def _get(*keys):
        for k in keys:
            v = _first_tag(audio, k)
            if v:
                return v
        return None

    tags["title"]           = _get("TITLE", "title")
    tags["artist"]          = _get("ARTIST", "artist")
    tags["album"]           = _get("ALBUM", "album")
    tags["albumartist"]     = _get("ALBUMARTIST", "albumartist", "ALBUM ARTIST")
    tags["date"]            = _get("DATE", "date")
    tags["tracknumber"]     = _get("TRACKNUMBER", "tracknumber")
    tags["discnumber"]      = _get("DISCNUMBER", "discnumber")
    tags["label"]           = _get("LABEL", "label")
    tags["catalognumber"]   = _get("CATALOGNUMBER", "catalognumber")
    tags["country"]         = _get("RELEASECOUNTRY", "releasecountry")
    tags["releasetype"]     = _get("RELEASETYPE", "releasetype")
    tags["mb_recordingid"]  = _get("MUSICBRAINZ_TRACKID", "musicbrainz_trackid")
    tags["mb_albumid"]      = _get("MUSICBRAINZ_ALBUMID", "musicbrainz_albumid")
    tags["mb_artistid"]     = _get("MUSICBRAINZ_ARTISTID", "musicbrainz_artistid")
    tags["mb_albumartistid"]= _get("MUSICBRAINZ_ALBUMARTISTID", "musicbrainz_albumartistid")


def _id3_to_logical(audio, tags: dict) -> None:
    """ID3 frames → logical tag dict (MP3)."""
    def _text(frame_key):
        f = audio.get(frame_key)
        return str(f).strip() if f else None

    def _txxx(desc):
        f = audio.get(f"TXXX:{desc}")
        return str(f.text[0]).strip() if f and f.text else None

    tags["title"]           = _text("TIT2")
    tags["artist"]          = _text("TPE1")
    tags["album"]           = _text("TALB")
    tags["albumartist"]     = _text("TPE2")
    tags["date"]            = _text("TDRC")
    tags["tracknumber"]     = _text("TRCK")
    tags["discnumber"]      = _text("TPOS")
    tags["mb_recordingid"]  = _txxx("MusicBrainz Recording Id")
    tags["mb_albumid"]      = _txxx("MusicBrainz Album Id")
    tags["mb_artistid"]     = _txxx("MusicBrainz Artist Id")
    tags["mb_albumartistid"]= _txxx("MusicBrainz Album Artist Id")


def _mp4_to_logical(audio, tags: dict) -> None:
    """MP4 atoms → logical tag dict (M4A / AAC / ALAC)."""
    def _atom(key):
        val = audio.get(key)
        if not val:
            return None
        item = val[0]
        if isinstance(item, (bytes, MP4FreeForm)):
            return bytes(item).decode("utf-8", errors="replace").strip() or None
        return str(item).strip() or None

    def _itunes(name):
        return _atom(f"----:com.apple.iTunes:{name}")

    tags["title"]           = _atom("\xa9nam")
    tags["artist"]          = _atom("\xa9ART")
    tags["album"]           = _atom("\xa9alb")
    tags["albumartist"]     = _atom("aART")
    tags["date"]            = _atom("\xa9day")

    trkn = audio.get("trkn")
    if trkn and isinstance(trkn[0], tuple):
        tags["tracknumber"] = str(trkn[0][0])
    disk = audio.get("disk")
    if disk and isinstance(disk[0], tuple):
        tags["discnumber"] = str(disk[0][0])

    tags["mb_recordingid"]  = _itunes("MusicBrainz Track Id")
    tags["mb_albumid"]      = _itunes("MusicBrainz Album Id")
    tags["mb_artistid"]     = _itunes("MusicBrainz Artist Id")
    tags["mb_albumartistid"]= _itunes("MusicBrainz Album Artist Id")


# =============================================================================
#  DATABASE — mb_acoustid_cache
# =============================================================================

def _get_mb_cache(conn: sqlite3.Connection, acoustid_id: str) -> "dict | None":
    """Return cached MB metadata for an acoustid_id, or None if not found.

    Returns None if the row doesn't exist OR if mb_recording_id is NULL
    (which indicates a previously failed/incomplete lookup that should be
    retried — e.g. due to an API bug on a prior run).
    """
    row = conn.execute(
        "SELECT mb_recording_id, title, artist, album, albumartist, date, "
        "tracknumber, discnumber, label, catalognumber, country, releasetype, "
        "mb_release_id, mb_artist_id, mb_albumartist_id, candidates_json "
        "FROM mb_acoustid_cache WHERE acoustid_id = ?",
        (acoustid_id,),
    ).fetchone()
    if not row or not row[0]:   # row[0] = mb_recording_id; NULL = treat as miss
        return None
    return {
        "mb_recordingid":   row[0],
        "title":            row[1],
        "artist":           row[2],
        "album":            row[3],
        "albumartist":      row[4],
        "date":             row[5],
        "tracknumber":      row[6],
        "discnumber":       row[7],
        "label":            row[8],
        "catalognumber":    row[9],
        "country":          row[10],
        "releasetype":      row[11],
        "mb_albumid":       row[12],
        "mb_artistid":      row[13],
        "mb_albumartistid": row[14],
        "candidates_json":  row[15],
    }


def _put_mb_cache(conn: sqlite3.Connection, acoustid_id: str, mb_data: dict) -> None:
    """Write (or update) MB metadata in the cache, keyed by acoustid_id."""
    conn.execute(
        """INSERT INTO mb_acoustid_cache
               (acoustid_id, mb_recording_id, title, artist, album, albumartist,
                date, tracknumber, discnumber, label, catalognumber, country,
                releasetype, mb_release_id, mb_artist_id, mb_albumartist_id,
                candidates_json, looked_up_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(acoustid_id) DO UPDATE SET
               mb_recording_id   = excluded.mb_recording_id,
               title             = excluded.title,
               artist            = excluded.artist,
               album             = excluded.album,
               albumartist       = excluded.albumartist,
               date              = excluded.date,
               tracknumber       = excluded.tracknumber,
               discnumber        = excluded.discnumber,
               label             = excluded.label,
               catalognumber     = excluded.catalognumber,
               country           = excluded.country,
               releasetype       = excluded.releasetype,
               mb_release_id     = excluded.mb_release_id,
               mb_artist_id      = excluded.mb_artist_id,
               mb_albumartist_id = excluded.mb_albumartist_id,
               candidates_json   = excluded.candidates_json,
               looked_up_at      = excluded.looked_up_at""",
        (
            acoustid_id,
            mb_data.get("mb_recordingid"),
            mb_data.get("title"),
            mb_data.get("artist"),
            mb_data.get("album"),
            mb_data.get("albumartist"),
            mb_data.get("date"),
            mb_data.get("tracknumber"),
            mb_data.get("discnumber"),
            mb_data.get("label"),
            mb_data.get("catalognumber"),
            mb_data.get("country"),
            mb_data.get("releasetype"),
            mb_data.get("mb_albumid"),
            mb_data.get("mb_artistid"),
            mb_data.get("mb_albumartistid"),
            mb_data.get("candidates_json"),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()


def _get_recording_id_from_acoustid_cache(
    conn: sqlite3.Connection, path_str: str
) -> "str | None":
    """
    Check the acoustid_cache table (written by acoustid_fingerprint.py) for a
    previously resolved mb_recording_id for this file path.
    Returns None if not found or if the table doesn't exist.
    """
    try:
        row = conn.execute(
            "SELECT mb_recording_id FROM acoustid_cache WHERE path_str = ?",
            (path_str,),
        ).fetchone()
        return (row[0] or "").strip() or None if row else None
    except sqlite3.OperationalError:
        # Table doesn't exist (pre-Phase-1 DB)
        return None


# =============================================================================
#  ACOUSTID API — lookup by track ID
# =============================================================================

def _acoustid_lookup_by_trackid(acoustid_id: str, api_key: str) -> list:
    """
    Query AcoustID API with a known acoustid_id UUID to get associated
    MB recording IDs. Returns list of recording dicts (may be empty).
    """
    if not HAS_REQUESTS:
        return []
    try:
        resp = requests.get(
            ACOUSTID_URL,
            params={
                "client":  api_key,
                "trackid": acoustid_id,
                "meta":    "recordings+releases+releasegroups",
                "format":  "json",
            },
            timeout=15,
        )
        if not resp.ok:
            return []
        data = resp.json()
        if data.get("status") != "ok":
            return []
        recordings = []
        for result in data.get("results", []):
            recordings.extend(result.get("recordings", []))
        return recordings
    except Exception:
        return []


# =============================================================================
#  MUSICBRAINZ LOOKUP
# =============================================================================

def _build_artist_credit(artist_credit: list) -> "str | None":
    """Build a display artist string from a MB artist-credit list."""
    parts = []
    for item in artist_credit:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and "artist" in item:
            parts.append(item["artist"].get("name", ""))
            joinphrase = item.get("joinphrase", "")
            if joinphrase:
                parts.append(joinphrase)
    result = "".join(parts).strip()
    return result or None


def _first_artist_id(artist_credit: list) -> "str | None":
    for item in artist_credit:
        if isinstance(item, dict) and "artist" in item:
            return item["artist"].get("id")
    return None


def _pick_best_release(releases: list) -> dict:
    """Pick the most useful release — prefer official with date and label info."""
    def _score(r):
        status = (r.get("status") or "").lower()
        return (
            1 if status == "official" else 0,
            1 if r.get("date") else 0,
            1 if r.get("label-info-list") else 0,
        )
    return max(releases, key=_score) if releases else {}


def _mb_lookup_recording(mb_recording_id: str, log=print) -> dict:
    """
    Fetch full MB metadata for a recording ID via musicbrainzngs.
    Returns flat dict of {logical_name: value} or empty dict on failure.
    """
    if not HAS_MBZ:
        log("  [WARN] musicbrainzngs not installed")
        return {}
    try:
        result = musicbrainzngs.get_recording_by_id(
            mb_recording_id,
            includes=["artists", "releases", "artist-credits"],
        )
    except musicbrainzngs.WebServiceError as exc:
        log(f"  [WARN] MB lookup failed ({mb_recording_id[:8]}...): {exc}")
        return {}
    except Exception as exc:
        log(f"  [WARN] MB lookup error ({mb_recording_id[:8]}...): {exc}")
        return {}

    rec   = result.get("recording", {})
    title = rec.get("title", "")

    artist_credit = rec.get("artist-credit", [])
    artist        = _build_artist_credit(artist_credit)
    artist_id     = _first_artist_id(artist_credit)

    mb_data = {
        "mb_recordingid":   mb_recording_id,
        "title":            title or None,
        "artist":           artist,
        "albumartist":      None,
        "album":            None,
        "date":             None,
        "tracknumber":      None,
        "discnumber":       None,
        "label":            None,
        "catalognumber":    None,
        "country":          None,
        "releasetype":      None,
        "mb_albumid":       None,
        "mb_artistid":      artist_id,
        "mb_albumartistid": None,
        "candidates_json":  None,
    }

    releases = rec.get("release-list", [])
    if not releases:
        return mb_data

    rel = _pick_best_release(releases)
    mb_data["album"]      = rel.get("title")
    mb_data["mb_albumid"] = rel.get("id")
    mb_data["country"]    = rel.get("country")

    # Year only from date string
    raw_date = rel.get("date", "")
    mb_data["date"] = raw_date[:4] if raw_date else None

    # Release type from release-group
    rg = rel.get("release-group", {})
    mb_data["releasetype"] = rg.get("primary-type")

    # Album artist from release-group artist-credit
    rg_ac = rg.get("artist-credit", [])
    if rg_ac:
        mb_data["albumartist"]      = _build_artist_credit(rg_ac)
        mb_data["mb_albumartistid"] = _first_artist_id(rg_ac)
    else:
        # Fall back to recording artist
        mb_data["albumartist"]      = artist
        mb_data["mb_albumartistid"] = artist_id

    # Label + catalogue number
    label_info = rel.get("label-info-list", [])
    if label_info:
        li = label_info[0]
        mb_data["label"]        = (li.get("label") or {}).get("name")
        mb_data["catalognumber"]= li.get("catalog-number")

    # Track + disc number (first medium, first track)
    medium_list = rel.get("medium-list", [])
    if medium_list:
        med = medium_list[0]
        disc_pos = med.get("position")
        if disc_pos:
            mb_data["discnumber"] = str(disc_pos)
        track_list = med.get("track-list", [])
        if track_list:
            track_num = track_list[0].get("number") or track_list[0].get("position")
            if track_num:
                mb_data["tracknumber"] = str(track_num)

    # Store all candidate recording IDs as JSON (for GUI multi-candidate picker)
    if len(releases) > 1:
        mb_data["candidates_json"] = json.dumps(
            [{"id": r.get("id"), "title": r.get("title"), "date": r.get("date")}
             for r in releases[:10]],
            ensure_ascii=False,
        )

    return mb_data


# =============================================================================
#  THREE-STATE TAG LOGIC
# =============================================================================

def _classify_file(current: dict, mb: dict, conflict_behaviour: str) -> str:
    """
    Classify how to handle a file's tags:
      'write_all'      — write all selected MB tags
      'write_ids_only' — only write MB ID tags (existing metadata is kept)
      'flag'           — conflict; do not write until user reviews
    """
    if conflict_behaviour == "mb_wins":
        return "write_all"
    if conflict_behaviour == "keep_existing":
        return "write_ids_only"

    # Default: 'flag' behaviour — compare existing vs MB
    has_tags = any(current.get(t) for t in ("title", "artist", "album"))
    if not has_tags:
        return "write_all"

    def _norm(s):
        return (s or "").strip().lower()

    title_match  = _norm(current.get("title"))  == _norm(mb.get("title"))
    artist_match = _norm(current.get("artist")) == _norm(mb.get("artist"))

    if title_match and artist_match:
        return "write_ids_only"
    return "flag"


def _build_write_tags(mb: dict, tag_config: dict, action: str) -> dict:
    """Build the dict of tags to actually write based on action and config."""
    if action == "write_all":
        return {
            k: mb.get(k) for k in ALL_TAG_KEYS
            if tag_config.get(k) and mb.get(k) is not None
        }
    if action == "write_ids_only":
        return {
            k: mb.get(k) for k in MB_ID_TAGS
            if tag_config.get(k) and mb.get(k) is not None
        }
    return {}


# =============================================================================
#  TAG WRITING — per format
# =============================================================================

# FLAC / OGG / Opus: VorbisComment field names
_VORBIS_FIELD = {
    "title":           "TITLE",
    "artist":          "ARTIST",
    "album":           "ALBUM",
    "albumartist":     "ALBUMARTIST",
    "date":            "DATE",
    "tracknumber":     "TRACKNUMBER",
    "discnumber":      "DISCNUMBER",
    "label":           "LABEL",
    "catalognumber":   "CATALOGNUMBER",
    "country":         "RELEASECOUNTRY",
    "releasetype":     "RELEASETYPE",
    "mb_recordingid":  "MUSICBRAINZ_TRACKID",
    "mb_albumid":      "MUSICBRAINZ_ALBUMID",
    "mb_artistid":     "MUSICBRAINZ_ARTISTID",
    "mb_albumartistid":"MUSICBRAINZ_ALBUMARTISTID",
}

# MP3: TXXX frame descriptions for MB ID tags
_MP3_TXXX = {
    "mb_recordingid":  "MusicBrainz Recording Id",
    "mb_albumid":      "MusicBrainz Album Id",
    "mb_artistid":     "MusicBrainz Artist Id",
    "mb_albumartistid":"MusicBrainz Album Artist Id",
}

# M4A: iTunes freeform atom names for MB ID tags
_M4A_ITUNES = {
    "mb_recordingid":  "MusicBrainz Track Id",
    "mb_albumid":      "MusicBrainz Album Id",
    "mb_artistid":     "MusicBrainz Artist Id",
    "mb_albumartistid":"MusicBrainz Album Artist Id",
}


def write_tags_to_file(path: Path, tags: dict, log=print) -> bool:
    """
    Write a {logical_name: value} dict to an audio file.
    Only non-None values are written. Returns True on success.
    """
    if not HAS_MUTAGEN:
        log("  [ERROR] mutagen not installed — cannot write tags")
        return False
    suffix = path.suffix.lower()
    try:
        if suffix == ".flac":
            return _write_vorbis(FLAC(str(path)), path, tags)
        elif suffix == ".mp3":
            return _write_mp3(path, tags)
        elif suffix in (".m4a", ".aac", ".alac"):
            return _write_m4a(path, tags)
        elif suffix == ".ogg":
            return _write_vorbis(OggVorbis(str(path)), path, tags)
        elif suffix == ".opus":
            return _write_vorbis(OggOpus(str(path)), path, tags)
        elif suffix == ".wav":
            log(f"  [WARN] WAV tag support is limited: {path.name}")
            return False
        else:
            log(f"  [SKIP] Unsupported format: {suffix}")
            return False
    except Exception as exc:
        log(f"  [ERROR] {path.name}: {exc}")
        return False


def _write_vorbis(audio, path: Path, tags: dict) -> bool:
    """Write tags to a VorbisComment-based file (FLAC, OGG, Opus)."""
    for logical, field in _VORBIS_FIELD.items():
        val = tags.get(logical)
        if val is not None:
            audio[field] = [str(val)]
    audio.save()
    return True


def _write_mp3(path: Path, tags: dict) -> bool:
    """Write tags to an MP3 file using ID3 frames."""
    try:
        audio = ID3(str(path))
    except mutagen.id3.ID3NoHeaderError:
        audio = ID3()

    if tags.get("title"):
        audio.setall("TIT2", [TIT2(encoding=3, text=tags["title"])])
    if tags.get("artist"):
        audio.setall("TPE1", [TPE1(encoding=3, text=tags["artist"])])
    if tags.get("album"):
        audio.setall("TALB", [TALB(encoding=3, text=tags["album"])])
    if tags.get("albumartist"):
        audio.setall("TPE2", [TPE2(encoding=3, text=tags["albumartist"])])
    if tags.get("date"):
        audio.setall("TDRC", [TDRC(encoding=3, text=tags["date"])])
    if tags.get("tracknumber"):
        audio.setall("TRCK", [TRCK(encoding=3, text=str(tags["tracknumber"]))])
    if tags.get("discnumber"):
        audio.setall("TPOS", [TPOS(encoding=3, text=str(tags["discnumber"]))])

    for logical, desc in _MP3_TXXX.items():
        val = tags.get(logical)
        if val:
            audio.setall(f"TXXX:{desc}", [TXXX(encoding=3, desc=desc, text=str(val))])

    audio.save(str(path))
    return True


def _write_m4a(path: Path, tags: dict) -> bool:
    """Write tags to an M4A / AAC / ALAC file using MP4 atoms."""
    audio = MP4(str(path))

    def _ff(val):
        return [MP4FreeForm(str(val).encode("utf-8"))]

    if tags.get("title"):       audio["\xa9nam"] = [tags["title"]]
    if tags.get("artist"):      audio["\xa9ART"] = [tags["artist"]]
    if tags.get("album"):       audio["\xa9alb"] = [tags["album"]]
    if tags.get("albumartist"): audio["aART"]    = [tags["albumartist"]]
    if tags.get("date"):        audio["\xa9day"] = [tags["date"]]

    if tags.get("tracknumber"):
        try:
            t = int(str(tags["tracknumber"]).split("/")[0])
            audio["trkn"] = [(t, 0)]
        except (ValueError, TypeError):
            pass
    if tags.get("discnumber"):
        try:
            d = int(str(tags["discnumber"]).split("/")[0])
            audio["disk"] = [(d, 0)]
        except (ValueError, TypeError):
            pass

    for logical, name in _M4A_ITUNES.items():
        val = tags.get(logical)
        if val:
            audio[f"----:com.apple.iTunes:{name}"] = _ff(val)

    audio.save()
    return True


# =============================================================================
#  REPORT
# =============================================================================

_REPORT_FIELDNAMES = [
    "filepath", "filename", "acoustid_id",
    "status", "action",
    "current_title", "current_artist", "current_album",
    "mb_title", "mb_artist", "mb_album", "mb_date",
    "mb_recordingid", "mb_albumid",
    "tags_written", "note",
]


def _write_report(rows: list, dry_run: bool) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix  = "dry" if dry_run else "applied"
    out     = REPORTS_DIR / f"acoustid_mb_tagger_{suffix}_{ts}.csv"
    write_csv(rows, out, fieldnames=_REPORT_FIELDNAMES)
    return out


# =============================================================================
#  CORE — GUI-CALLABLE
# =============================================================================

def run_acoustid_mb_tagger(
    folder,
    apply: bool             = False,
    tag_config: dict        = None,
    conflict_behaviour: str = "flag",
    progress_callback       = None,
    log_callback            = None,
) -> dict:
    """
    Scan folder for files with ACOUSTID_ID tags, look up MusicBrainz metadata,
    and write (or preview) tags according to tag_config and conflict_behaviour.

    Parameters
    ----------
    folder              : str or Path — root folder to scan (recurses)
    apply               : if False (default), dry run — no tags written
    tag_config          : {logical_name: bool} — which tags to write.
                          None uses DEFAULT_TAG_CONFIG.
    conflict_behaviour  : 'flag' (default) | 'mb_wins' | 'keep_existing'
    progress_callback   : fn(current, total, filename)
    log_callback        : fn(message)

    Returns
    -------
    {
        tagged        : int   — files tagged (apply) or would-tag (dry)
        would_tag     : int   — same as tagged
        flagged       : int   — files with conflicts, not written
        no_match      : int   — files with no MB result
        errors        : int   — files that raised exceptions
        results       : list  — one dict per file
        report_path   : Path  — CSV report path
    }
    """
    folder = Path(folder)
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")
    if not HAS_MUTAGEN:
        raise RuntimeError("mutagen is required: pip install mutagen")
    if not HAS_MBZ:
        raise RuntimeError("musicbrainzngs is required: pip install musicbrainzngs")

    tag_config = tag_config or DEFAULT_TAG_CONFIG.copy()

    log  = log_callback  or print
    prog = progress_callback or (lambda c, t, n: None)

    # -- Config --
    cfg     = load_config()
    api_key = cfg.get("acoustid", {}).get("api_key", "")

    # -- MB user agent --
    musicbrainzngs.set_useragent(*MB_USER_AGENT)

    # -- DB --
    conn = open_db()
    init_db(conn)

    # -- Scan for files --
    log(f"\n  Scanning: {folder}")
    all_files = sorted(
        f for f in folder.rglob("*")
        if f.is_file() and f.suffix.lower() in _TAGGABLE
    )
    log(f"  Found {len(all_files):,} audio files")

    # Collect files that have an ACOUSTID_ID tag
    log("  Reading ACOUSTID_ID tags...")
    candidates = []
    for f in all_files:
        acoustid_id = _read_acoustid_id(f)
        if acoustid_id:
            current_tags = _read_tags_from_file(f)
            candidates.append((f, acoustid_id, current_tags))

    total = len(candidates)
    log(f"  {total:,} files have an ACOUSTID_ID tag")
    if total == 0:
        conn.close()
        return {
            "tagged": 0, "would_tag": 0, "flagged": 0,
            "no_match": 0, "errors": 0, "results": [],
            "report_path": _write_report([], dry_run=not apply),
        }

    # -- Process --
    results  = []
    tagged = flagged = no_match = errors = 0
    _last_api_call = [0.0]  # mutable for rate-limit closure

    for idx, (f, acoustid_id, current_tags) in enumerate(candidates, 1):
        prog(idx, total, f.name)
        row = {
            "filepath":       str(f),
            "filename":       f.name,
            "acoustid_id":    acoustid_id,
            "status":         "",
            "action":         "",
            "current_title":  current_tags.get("title")  or "",
            "current_artist": current_tags.get("artist") or "",
            "current_album":  current_tags.get("album")  or "",
            "mb_title":       "",
            "mb_artist":      "",
            "mb_album":       "",
            "mb_date":        "",
            "mb_recordingid": "",
            "mb_albumid":     "",
            "tags_written":   "",
            "note":           "",
        }

        try:
            # ── Step 1: mb_acoustid_cache hit? ────────────────────────────
            mb_data = _get_mb_cache(conn, acoustid_id)

            if mb_data is None:
                # ── Step 2: acoustid_cache from Phase 1 has recording ID? ─
                mb_rec_id = _get_recording_id_from_acoustid_cache(conn, str(f))

                if not mb_rec_id:
                    # ── Step 3: AcoustID API lookup ────────────────────────
                    if not api_key:
                        row["status"] = "error"
                        row["note"]   = "No AcoustID API key in music_config.json"
                        errors += 1
                        results.append(row)
                        continue

                    _wait_for_rate(ACOUSTID_DELAY, _last_api_call)
                    recordings = _acoustid_lookup_by_trackid(acoustid_id, api_key)
                    _last_api_call[0] = time.time()

                    if recordings:
                        mb_rec_id = recordings[0].get("id", "").strip() or None

                if mb_rec_id:
                    # ── Step 4: Full MB metadata lookup ───────────────────
                    _wait_for_rate(MB_RATE_DELAY, _last_api_call)
                    mb_data = _mb_lookup_recording(mb_rec_id, log=log)
                    _last_api_call[0] = time.time()
                else:
                    mb_data = {}

                # Cache result (even empty — avoids re-hitting API on re-run)
                _put_mb_cache(conn, acoustid_id, mb_data)

            # ── No MB result ───────────────────────────────────────────────
            if not mb_data or not mb_data.get("mb_recordingid"):
                row["status"] = "no_match"
                no_match += 1
                results.append(row)
                continue

            # ── Populate MB columns ────────────────────────────────────────
            row["mb_title"]       = mb_data.get("title")         or ""
            row["mb_artist"]      = mb_data.get("artist")        or ""
            row["mb_album"]       = mb_data.get("album")         or ""
            row["mb_date"]        = mb_data.get("date")          or ""
            row["mb_recordingid"] = mb_data.get("mb_recordingid") or ""
            row["mb_albumid"]     = mb_data.get("mb_albumid")    or ""

            # ── Step 5: Three-state classify ──────────────────────────────
            action = _classify_file(current_tags, mb_data, conflict_behaviour)
            row["action"] = action

            if action == "flag":
                row["status"] = "flagged"
                flagged += 1
                results.append(row)
                continue

            # ── Build tags to write ────────────────────────────────────────
            write_tags = _build_write_tags(mb_data, tag_config, action)
            row["tags_written"] = ", ".join(write_tags.keys())

            if not apply:
                row["status"] = "would_tag"
                tagged += 1
            else:
                ok = write_tags_to_file(f, write_tags, log=log)
                if ok:
                    row["status"] = "tagged"
                    tagged += 1
                else:
                    row["status"] = "error"
                    row["note"]   = "write_tags_to_file returned False"
                    errors += 1

        except Exception as exc:
            row["status"] = "error"
            row["note"]   = str(exc)
            errors += 1
            log(f"  [ERROR] {f.name}: {exc}")

        results.append(row)

    conn.close()

    # -- Report --
    report_path = _write_report(results, dry_run=not apply)
    label = "Would tag" if not apply else "Tagged"
    log(f"\n  {label}: {tagged}  |  Flagged: {flagged}  |  No match: {no_match}  |  Errors: {errors}")
    log(f"  Report : {report_path}")

    return {
        "tagged":      tagged,
        "would_tag":   tagged,
        "flagged":     flagged,
        "no_match":    no_match,
        "errors":      errors,
        "results":     results,
        "report_path": report_path,
    }


def _wait_for_rate(min_gap: float, last_call: list) -> None:
    """Pause if needed to respect the API rate limit."""
    elapsed = time.time() - last_call[0]
    if elapsed < min_gap:
        time.sleep(min_gap - elapsed)


# =============================================================================
#  CLI MAIN
# =============================================================================

def main():
    from music_tools_common import interactive_options
    interactive_options([
        ("--apply",                  "Apply — write tags for real  (default is dry run)"),
        ("--conflict flag",          "Conflict: flag for review when tags differ from MB (default)"),
        ("--conflict mb_wins",       "Conflict: MB always overwrites existing tags"),
        ("--conflict keep_existing", "Conflict: never overwrite — write MB IDs only"),
    ])

    # Re-parse after interactive_options may have injected flags
    _dry    = "--apply"    not in sys.argv
    _pick   = "--pick"     in sys.argv
    _path   = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--path" and i + 1 < len(sys.argv)),
        None,
    )
    _conf   = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv)
         if a == "--conflict" and i + 1 < len(sys.argv)),
        "flag",
    ).strip().lower()

    print("=" * 60)
    print("  AcousticID → MusicBrainz Tagger  v1.0")
    print(f"  Mode : {'DRY RUN — no changes will be made' if _dry else 'APPLY — tags will be written'}")
    print("=" * 60)

    if _pick:
        folder = pick_folder("Select folder to tag")
        if not folder:
            print("  No folder selected. Exiting.")
            sys.exit(0)
    elif _path:
        folder = Path(_path.strip('"'))
    else:
        print("  ERROR: No folder specified. Use --pick or --path.")
        sys.exit(1)

    if not folder.exists() or not folder.is_dir():
        print(f"  ERROR: Folder not found: {folder}")
        sys.exit(1)

    if _conf not in ("flag", "mb_wins", "keep_existing"):
        print(f"  ERROR: --conflict must be flag, mb_wins, or keep_existing (got: {_conf})")
        sys.exit(1)

    # -- Dry-run scan (always) --
    print(f"\n  Scanning: {folder}")
    result = run_acoustid_mb_tagger(
        folder,
        apply=False,
        conflict_behaviour=_conf,
    )

    print(f"\n  Preview:")
    print(f"    Would tag : {result['tagged']}")
    print(f"    Flagged   : {result['flagged']}")
    print(f"    No match  : {result['no_match']}")
    print(f"    Errors    : {result['errors']}")
    print(f"\n  Report    : {result['report_path']}")

    if _dry or result["tagged"] == 0:
        print("\n  Dry run complete. Pass --apply to write tags.")
        print("  Review the report above for flagged / no-match files.")
        return

    # -- Confirmation before apply --
    confirm = input(
        f"\n  Write tags to {result['tagged']} file(s)? "
        f"(review the report first if needed) (y/n): "
    ).strip().lower()
    while confirm not in ("y", "n"):
        confirm = input("  Please enter y or n: ").strip().lower()
    if confirm != "y":
        print("  Aborted.")
        sys.exit(0)

    # -- Apply --
    print("\n  Applying tags...")
    result = run_acoustid_mb_tagger(
        folder,
        apply=True,
        conflict_behaviour=_conf,
    )

    print(f"\n  Done.")
    print(f"    Tagged  : {result['tagged']}")
    print(f"    Flagged : {result['flagged']}")
    print(f"    No match: {result['no_match']}")
    print(f"    Errors  : {result['errors']}")


if __name__ == "__main__":
    main()
