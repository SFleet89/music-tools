"""
Playlist Repair Tool  v1.8
===========================
Scans .m3u playlist files and repairs broken paths by searching
your music library for each track.

Matching strategy (in order):
  1. Metadata match  -- parse Artist + Title from playlist filename,
                        compare against library tags (mutagen/cache)
  2. Title-only match -- when no artist can be parsed from the filename
  3. Filename stem   -- fuzzy match on stem as fallback for untagged files

Auto-resolution: ambiguous matches are automatically resolved when:
  - All candidates are the same song in different locations
    (prefers non-compilation albums)
  - Playlist filename implies an artist that narrows candidates to one

Uses the shared SQLite cache (music_cache.db) built by build_fp_cache.py
or find_music_duplicates.py if available.

Workflow:
  Step 1 -- Dry run (default):
    Double-click repair_playlists_dry.cmd
    Select playlists folder and music library folder via dialog.
    Generates reports in <script folder>/reports/

  Step 2 -- Resolve ambiguous matches (if any):
    Open playlist_selector_TIMESTAMP.html in your browser.
    Auto-selected tab: review pre-picked matches, override if needed.
    To Review tab: manually pick from remaining ambiguous matches.
    Missing tab: reference only.
    Click Download selections.json and save to the reports folder.

  Step 3 -- Apply:
    Double-click repair_playlists_apply.cmd
    Select selections.json via dialog if prompted.
    Repaired playlists written to <playlists folder>/repaired/

Options:
  --playlists    Folder containing .m3u files (opens picker if omitted)
  --music        Root of your music library (opens picker if omitted)
  --cache        Path to music_cache.db (defaults to project root)
  --output-dir   Where to write repaired playlists (default: <playlists>/repaired)
  --apply        Write repaired playlists (default: dry run)
  --selections   Path to selections JSON (opens picker if omitted in apply mode)
  --threshold    Fuzzy match threshold 0-100 (default: 85)
  --reports-dir  Where to save reports (default: <script folder>/reports)
"""

import os
import sys
import re
import csv
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

# ── Shared project helpers ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from music_tools_common import DB_PATH, open_db
    _COMMON_AVAILABLE = True
except ImportError:
    _COMMON_AVAILABLE = False
    DB_PATH = None

# ── Optional dependencies ───────────────────────────────────────────────────

try:
    from rapidfuzz import fuzz as _fuzz, process as _fuzz_process
    def fuzzy_score(a: str, b: str) -> float:
        return _fuzz.token_sort_ratio(a, b)
    def fuzzy_best(query: str, choices: list, threshold: float):
        result = _fuzz_process.extractOne(query, choices, score_cutoff=threshold)
        return (result[0], result[1]) if result else None
    FUZZY_AVAILABLE = True
except ImportError:
    import difflib
    def fuzzy_score(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio() * 100
    def fuzzy_best(query: str, choices: list, threshold: float):
        best = None
        best_score = 0.0
        for c in choices:
            s = fuzzy_score(query, c)
            if s > best_score and s >= threshold:
                best_score = s
                best = (c, s)
        return best
    FUZZY_AVAILABLE = False
    print("WARNING: 'rapidfuzz' not installed. Using difflib (slower).")
    print("         Run: pip install rapidfuzz\n")

try:
    from mutagen import File as MutagenFile
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    print("WARNING: 'mutagen' not installed. Cache building disabled.")
    print("         Run: pip install mutagen\n")

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".aac", ".m4a"}
TRACK_NUM_RE  = re.compile(r"^\d{1,3}[\s\-_.]+")
FEAT_RE       = re.compile(r"\s*[\(\[]?(?:feat|ft|featuring)\.?\s+[^\)\]]*[\)\]]?", re.IGNORECASE)
HASH_RE       = re.compile(r"-[0-9a-f]{8}(?=\.|$)", re.IGNORECASE)
FORMAT_PRIORITY = {".flac": 0, ".m4a": 1, ".aac": 1, ".mp3": 2}
COMPILATION_RE = re.compile(
    r"\b(greatest hits?|best of|collection|compilation|anthology|essentials?|"
    r"singles|rarities|b.?sides?|deluxe|remaster|remastered|edition)\b",
    re.IGNORECASE,
)
SCRIPT_DIR    = Path(__file__).parent
# Default cache is the shared SQLite database in the project root.
# Falls back to None if music_tools_common could not be imported.
DEFAULT_CACHE = DB_PATH  # Path set by music_tools_common; None if unavailable


# ══════════════════════════════════════════════════════════════════════════════
#  ARGUMENT PARSING
# ══════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Repair broken .m3u playlists by re-matching tracks against your music library.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--playlists",   default=None)
    p.add_argument("--music",       default=None)
    p.add_argument("--cache",       default=None)
    p.add_argument("--output-dir",  default=None)
    p.add_argument("--apply",       action="store_true")
    p.add_argument("--selections",  default=None)
    p.add_argument("--threshold",   type=float, default=85.0)
    p.add_argument("--reports-dir", default=None)
    return p.parse_args()


# ══════════════════════════════════════════════════════════════════════════════
#  PICKERS  (PowerShell on Windows, tkinter fallback elsewhere)
# ══════════════════════════════════════════════════════════════════════════════

def pick_folder(title: str, initial: str = "") -> Path:
    if sys.platform == "win32":
        return _pick_folder_powershell(title, initial)
    return _pick_folder_tkinter(title, initial)

def pick_file(title: str, filetypes: list, initial: str = "") -> Path:
    if sys.platform == "win32":
        return _pick_file_win32(title, filetypes, initial)
    return _pick_file_tkinter(title, filetypes, initial)

def _pick_folder_powershell(title: str, initial: str = "") -> Path:
    import subprocess
    safe_title   = title.replace("'", "''")
    safe_initial = (initial or str(Path.home())).replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
        f"$d.Description = '{safe_title}'; "
        f"$d.SelectedPath = '{safe_initial}'; "
        "$d.ShowNewFolderButton = $false; "
        "$r = $d.ShowDialog(); "
        "if ($r -eq 'OK') { Write-Output $d.SelectedPath }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=120,
    )
    path = result.stdout.strip()
    if not path:
        print("  Cancelled: no folder selected.")
        sys.exit(0)
    return Path(path)

def _pick_file_win32(title: str, filetypes: list, initial: str = "") -> Path:
    import subprocess
    safe_title   = title.replace("'", "''")
    safe_initial = (initial or str(SCRIPT_DIR / "reports")).replace("'", "''")
    filter_parts = [f"{desc} ({pat})|{pat}" for desc, pat in filetypes if pat != "*.*"]
    filter_parts.append("All files (*.*)|*.*")
    filter_str = "|".join(filter_parts).replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.OpenFileDialog; "
        f"$d.Title = '{safe_title}'; "
        f"$d.InitialDirectory = '{safe_initial}'; "
        f"$d.Filter = '{filter_str}'; "
        "$r = $d.ShowDialog(); "
        "if ($r -eq 'OK') { Write-Output $d.FileName }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=120,
    )
    path = result.stdout.strip()
    if not path:
        print("  Cancelled: no file selected.")
        sys.exit(0)
    return Path(path)

def _pick_folder_tkinter(title: str, initial: str = "") -> Path:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title=title, initialdir=initial or str(Path.home()))
        root.destroy()
        if not folder:
            print("  Cancelled."); sys.exit(0)
        return Path(folder)
    except Exception as e:
        print(f"ERROR: Could not open folder picker: {e}"); sys.exit(1)

def _pick_file_tkinter(title: str, filetypes: list, initial: str = "") -> Path:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        fp = filedialog.askopenfilename(title=title, filetypes=filetypes,
                                         initialdir=initial or str(SCRIPT_DIR / "reports"))
        root.destroy()
        if not fp:
            print("  Cancelled."); sys.exit(0)
        return Path(fp)
    except Exception as e:
        print(f"ERROR: Could not open file picker: {e}"); sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
#  TEXT NORMALISATION
# ══════════════════════════════════════════════════════════════════════════════

def norm(text: str) -> str:
    text = str(text).lower()
    text = FEAT_RE.sub("", text)
    text = text.replace("&", "and")
    text = text.replace("_", " ").replace(".", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text

def norm_stem(filename: str) -> str:
    stem = Path(filename).stem
    stem = TRACK_NUM_RE.sub("", stem).strip()
    return norm(stem)

def parse_artist_title(filename: str) -> tuple:
    """
    Split playlist filename into (artist, title) or (None, title).
    Handles: Artist - Title, 01 - Artist - Title, 01_artist_-_title,
             01-artist-title, 03-artist-hi-lo-93a3e08b
    """
    stem = Path(filename).stem
    stem = HASH_RE.sub("", stem)
    stem = stem.replace("_", " ")
    stem = TRACK_NUM_RE.sub("", stem).strip()

    # Strategy 1: explicit " - " separator
    if " - " in stem:
        parts  = stem.split(" - ", 1)
        artist = norm(parts[0])
        title  = norm(parts[1])
        if artist and not artist.isdigit():
            return artist, title
        return None, norm(stem)

    # Strategy 2: multi-word artist with dash separator
    if "-" in stem:
        m = re.match(r"^([a-zA-Z][a-zA-Z0-9]*(?:\s+[a-zA-Z0-9&']+)+)\s*-\s*(.+)$", stem)
        if m:
            artist = norm(m.group(1))
            title  = norm(m.group(2))
            if artist and title and not artist.isdigit():
                return artist, title

    # Strategy 3: single-word artist with dash separator
    if "-" in stem:
        parts = stem.split("-", 1)
        first = parts[0].strip()
        rest  = parts[1].strip()
        if re.match(r"^[a-zA-Z]{3,}$", first) and rest and len(rest) > 2:
            return norm(first), norm(rest)

    return None, norm(stem)


def parse_playlist_artist_album(playlist_name: str) -> tuple:
    """
    Extract (artist, album) from the playlist filename.
    Returns (artist, album) -- either can be empty string.

    Examples:
      Above & Beyond - Acoustic II.m3u              -> (above and beyond, acoustic ii)
      Dr. Dre - Compton OST.m3u                     -> (dr dre, compton)
      Evanescence - Synthesis.m3u                   -> (evanescence, synthesis)
      Guardians of the Galaxy - Awesome Mix Vol.1.m3u -> (guardians of the galaxy, awesome mix vol 1)
      ASOT 642.m3u                                  -> (, )
    """
    stem = Path(playlist_name).stem.replace("_", " ").replace("&", "and")

    for sep in [" - ", " – "]:
        if sep in stem:
            parts      = stem.split(sep, 1)
            artist_raw = parts[0].strip()
            album_raw  = parts[1].strip()
            # Strip OST/Soundtrack label from end of album only
            album_raw = re.sub(
                r"\s+(ost|original\s+soundtrack|soundtrack)$",
                "", album_raw, flags=re.IGNORECASE).strip()
            artist = norm(artist_raw)
            album  = norm(album_raw)
            if artist and not artist.replace(" ", "").isdigit():
                return artist, album

    return "", ""

def normalize_path(path_str: str) -> str:
    p = path_str.strip()
    p = re.sub(r"^\\\\[^\\]+\\([a-zA-Z])\\",
               lambda m: m.group(1).upper() + ":\\", p)
    return p

def load_from_cache(cache_path: Path) -> list:
    """Load library metadata from the shared SQLite cache (music_cache.db)."""
    print(f"  Loading cache: {cache_path}")
    entries = []
    seen = {}
    try:
        conn = open_db(cache_path)
        try:
            rows = conn.execute(
                "SELECT path_str, filename, title, artist, album "
                "FROM metadata_cache"
            ).fetchall()
        finally:
            conn.close()
    except Exception as e:
        print(f"  ERROR: Could not read cache: {e}")
        return []
    for row in rows:
        path_str = normalize_path(row["path_str"] or "")
        if not path_str or path_str in seen:
            continue
        seen[path_str] = True
        entries.append({
            "path":     Path(path_str),
            "filename": row["filename"] or Path(path_str).name,
            "title":    norm(row["title"] or ""),
            "artist":   norm(row["artist"] or ""),
            "album":    norm(row["album"] or ""),
        })
    print(f"  Cache loaded: {len(entries)} unique files.")
    return entries

def scan_library(music_root: Path) -> list:
    if not MUTAGEN_AVAILABLE:
        print("  ERROR: mutagen not installed and no cache available.")
        print("         Run: pip install mutagen")
        sys.exit(1)
    print(f"  No cache found. Scanning library...")
    entries   = []
    all_paths = [p for p in music_root.rglob("*")
                 if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]
    print(f"  Found {len(all_paths)} files. Reading tags...")
    for path in all_paths:
        title = artist = album = ""
        try:
            easy = MutagenFile(path, easy=True)
            if easy:
                def first(tag):
                    val = easy.get(tag)
                    return val[0].strip() if val else ""
                title  = first("title")
                artist = first("artist")
                album  = first("album")
        except Exception:
            pass
        entries.append({"path": path, "filename": path.name,
                         "title": norm(title), "artist": norm(artist), "album": norm(album)})
    print(f"  Scanned {len(entries)} files.")
    return entries

def build_indexes(entries: list) -> dict:
    artist_title = {}
    title_idx    = {}
    stem_idx     = {}
    for entry in entries:
        t = entry["title"]
        a = entry["artist"]
        s = norm_stem(entry["filename"])
        if t and a:
            artist_title.setdefault((a, t), []).append(entry)
        if t:
            title_idx.setdefault(t, []).append(entry)
        if s:
            stem_idx.setdefault(s, []).append(entry)
    return {"artist_title": artist_title, "title": title_idx, "stem": stem_idx}


# ══════════════════════════════════════════════════════════════════════════════
#  AUTO-RESOLUTION
# ══════════════════════════════════════════════════════════════════════════════

def is_compilation(entry: dict) -> bool:
    """Return True if the entry looks like it's from a compilation album."""
    album = entry.get("album", "")
    path  = str(entry.get("path", ""))
    return bool(COMPILATION_RE.search(album) or COMPILATION_RE.search(path))

def pick_best_candidate(candidates: list) -> int:
    """
    From a list of candidates for the same song, pick the best index.
    Priority: (1) non-compilation, (2) lossless format (FLAC > AAC/M4A > MP3).
    """
    def score(entry):
        comp = 1 if is_compilation(entry) else 0
        ext  = Path(str(entry.get("path", ""))).suffix.lower()
        fmt  = FORMAT_PRIORITY.get(ext, 2)
        return (comp, fmt)
    return min(range(len(candidates)), key=lambda i: score(candidates[i]))

def try_auto_resolve(candidates: list, playlist_artist: str,
                     playlist_album: str = "") -> tuple:
    """
    Try to automatically resolve an ambiguous match.
    Returns (candidate_index, reason) or (None, "") if cannot auto-resolve.

    Rules:
      1. All candidates are the same song (same artist+title) -> pick non-compilation
      2. Playlist artist+album both known -> filter by both -> if one match, pick it
      3. Playlist artist known -> filter by artist -> if one match, pick it
      4. Playlist artist known -> filter by artist -> if all same song, pick non-compilation
    """
    if not candidates:
        return None, ""

    # Rule 1: all candidates share the same normalised artist+title
    artists = {c.get("artist", "") for c in candidates}
    titles  = {c.get("title",  "") for c in candidates}
    all_same_song = (len(artists) == 1 and len(titles) == 1
                     and next(iter(artists)) and next(iter(titles)))

    if all_same_song:
        idx = pick_best_candidate(candidates)
        return idx, "same song in multiple locations — picked non-compilation"

    # Rule 2: playlist artist AND album known — filter by both
    if playlist_artist and playlist_album:
        both_matches = [
            i for i, c in enumerate(candidates)
            if (fuzzy_score(c.get("artist", ""), playlist_artist) >= 85 and
                fuzzy_score(c.get("album",  ""), playlist_album)  >= 85)
        ]
        if len(both_matches) == 1:
            return both_matches[0], (f"only candidate matching playlist artist "
                                     f"'{playlist_artist}' + album '{playlist_album}'")
        if len(both_matches) > 1:
            filtered  = [candidates[i] for i in both_matches]
            f_artists = {c.get("artist", "") for c in filtered}
            f_titles  = {c.get("title",  "") for c in filtered}
            if len(f_artists) == 1 and len(f_titles) == 1:
                sub_idx  = pick_best_candidate(filtered)
                real_idx = both_matches[sub_idx]
                return real_idx, (f"same song, filtered by artist '{playlist_artist}' "
                                  f"+ album '{playlist_album}'")

    # Rule 3: playlist artist known — filter by artist only
    if playlist_artist:
        artist_matches = [
            i for i, c in enumerate(candidates)
            if fuzzy_score(c.get("artist", ""), playlist_artist) >= 88
        ]
        if len(artist_matches) == 1:
            return artist_matches[0], f"only candidate matching playlist artist '{playlist_artist}'"

        # Rule 4: multiple artist matches but same song
        if len(artist_matches) > 1:
            filtered  = [candidates[i] for i in artist_matches]
            f_artists = {c.get("artist", "") for c in filtered}
            f_titles  = {c.get("title",  "") for c in filtered}
            if len(f_artists) == 1 and len(f_titles) == 1:
                sub_idx  = pick_best_candidate(filtered)
                real_idx = artist_matches[sub_idx]
                return real_idx, f"same song, filtered by playlist artist '{playlist_artist}'"

    return None, ""


# ══════════════════════════════════════════════════════════════════════════════
#  MATCHING
# ══════════════════════════════════════════════════════════════════════════════

def _dedupe_entries(entries: list) -> list:
    seen = set()
    out  = []
    for e in entries:
        key = str(e["path"]).lower()
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out

def match_entry(entry: dict, indexes: dict, threshold: float,
                playlist_artist: str = "", playlist_album: str = "") -> dict:
    """Find library matches for one playlist path entry."""
    if entry["type"] != "path":
        return {**entry, "status": "skip", "candidates": [], "score": None,
                "match_method": "", "parsed_artist": "", "parsed_title": "",
                "auto_index": None, "auto_reason": ""}

    filename = entry["filename"]
    artist, title = parse_artist_title(filename)
    stem = norm_stem(filename)

    # If no artist was parsed from the filename but the playlist artist is known,
    # check whether the title starts with the playlist artist name (e.g.
    # "dr dre intro" with playlist artist "dr dre" -> artist="dr dre", title="intro").
    # This handles abbreviated names like "dr._dre" where the dot breaks parsing.
    if not artist and playlist_artist and title:
        pa_words = playlist_artist.split()
        ti_words = title.split()
        if len(pa_words) >= 1 and ti_words[:len(pa_words)] == pa_words and len(ti_words) > len(pa_words):
            artist = playlist_artist
            title  = " ".join(ti_words[len(pa_words):])

    def make_result(candidates, score, method):
        candidates = _dedupe_entries(candidates)
        auto_idx, auto_reason = try_auto_resolve(candidates, playlist_artist, playlist_album)
        if auto_idx is not None:
            status = "auto"
        elif len(candidates) == 1:
            status = "resolved"
            auto_idx = 0
            auto_reason = ""
        else:
            status = "ambiguous"
        return {**entry, "status": status, "candidates": candidates,
                "score": score, "match_method": method,
                "parsed_artist": artist or "", "parsed_title": title or "",
                "auto_index": auto_idx, "auto_reason": auto_reason}

    # 1. Exact metadata: artist + title
    if artist and title:
        key = (artist, title)
        if key in indexes["artist_title"]:
            return make_result(indexes["artist_title"][key], 100.0,
                               "metadata: artist+title (exact)")

    # 2. Exact metadata: title only
    if title and title in indexes["title"]:
        method = ("metadata: title only (exact)" if not artist
                  else "metadata: title only (no artist match)")
        return make_result(indexes["title"][title], 100.0, method)

    # 3. Fuzzy metadata: artist + title
    if artist and title:
        query   = f"{artist} {title}"
        at_keys = [f"{a} {t}" for a, t in indexes["artist_title"].keys()]
        best = fuzzy_best(query, at_keys, threshold)
        if best:
            matched_str, score = best
            for (a, t) in indexes["artist_title"]:
                if f"{a} {t}" == matched_str:
                    return make_result(indexes["artist_title"][(a, t)],
                                       round(score, 1), "metadata: artist+title (fuzzy)")

    # 4. Fuzzy metadata: title only
    if title:
        best = fuzzy_best(title, list(indexes["title"].keys()), threshold)
        if best:
            matched_title, score = best
            return make_result(indexes["title"][matched_title],
                               round(score, 1), "metadata: title only (fuzzy)")

    # 5. Filename stem exact
    if stem in indexes["stem"]:
        return make_result(indexes["stem"][stem], 100.0, "filename stem (exact)")

    # 6. Filename stem fuzzy
    best = fuzzy_best(stem, list(indexes["stem"].keys()), threshold)
    if best:
        matched_stem, score = best
        return make_result(indexes["stem"][matched_stem],
                           round(score, 1), "filename stem (fuzzy)")

    return {**entry, "status": "missing", "candidates": [], "score": None,
            "match_method": "none", "parsed_artist": artist or "",
            "parsed_title": title or "", "auto_index": None, "auto_reason": ""}


# ══════════════════════════════════════════════════════════════════════════════
#  M3U PARSING
# ══════════════════════════════════════════════════════════════════════════════

def parse_m3u(playlist_path: Path) -> list:
    try:
        try:
            text = playlist_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = playlist_path.read_text(encoding="latin-1")
    except Exception as e:
        print(f"  ERROR reading {playlist_path.name}: {e}")
        return []
    lines = []
    for i, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            lines.append({"line_num": i, "raw": raw, "type": "blank", "filename": ""})
        elif stripped.startswith("#"):
            lines.append({"line_num": i, "raw": stripped, "type": "comment", "filename": ""})
        else:
            filename = Path(stripped.replace("\\", "/")).name
            lines.append({"line_num": i, "raw": stripped, "type": "path", "filename": filename})
    return lines

def match_all(playlists: list, indexes: dict, threshold: float) -> dict:
    results = {}
    for pl_path in playlists:
        pl_artist, pl_album = parse_playlist_artist_album(pl_path.name)
        hint = ""
        if pl_artist and pl_album:
            hint = f"  [artist: {pl_artist} | album: {pl_album}]"
        elif pl_artist:
            hint = f"  [artist: {pl_artist}]"
        print(f"  Matching: {pl_path.name}" + hint)
        lines = parse_m3u(pl_path)
        results[pl_path] = [
            {**match_entry(line, indexes, threshold, pl_artist, pl_album),
             "playlist_album": pl_album}
            for line in lines
        ]
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  PATH HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def to_relative_path(song_path: Path, playlist_path: Path) -> str:
    rel = os.path.relpath(str(song_path), str(playlist_path.parent))
    return rel.replace("\\", "/")


# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
#  HTML SELECTOR  (tabbed: To Review / Auto-selected / Missing)
#  Features:
#    - Playlist filter + bulk album assignment in To Review tab
#    - Manual path entry per card
#    - Auto-selected tab with override support
#    - Missing tab (read-only reference)
# ══════════════════════════════════════════════════════════════════════════════

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Playlist Repair - Resolve Matches</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; padding-bottom: 100px; }
  header { background: #1a1d2e; border-bottom: 1px solid #2d3148; padding: 14px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
  .header-left { display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 15px; font-weight: 600; color: #fff; }
  .progress-text { font-size: 13px; color: #64748b; }
  .progress-bar-wrap { height: 3px; background: #2d3148; position: sticky; top: 49px; z-index: 99; }
  .progress-bar-fill { height: 100%; background: #6366f1; transition: width 0.3s ease; }
  .tabs { display: flex; gap: 0; padding: 0 24px; background: #1a1d2e; border-bottom: 1px solid #2d3148; position: sticky; top: 52px; z-index: 98; }
  .tab { padding: 10px 20px; font-size: 13px; cursor: pointer; color: #64748b; border-bottom: 2px solid transparent; transition: color 0.15s, border-color 0.15s; white-space: nowrap; }
  .tab:hover { color: #e2e8f0; }
  .tab.active { color: #e2e8f0; border-bottom-color: #6366f1; }
  .tab .count { display: inline-block; background: #2d3148; color: #94a3b8; font-size: 11px; padding: 1px 7px; border-radius: 10px; margin-left: 6px; }
  .tab.active .count { background: #6366f133; color: #a5b4fc; }
  .tab-warn .count { background: #7c2d1222; color: #fb923c; }
  .container { max-width: 900px; margin: 0 auto; padding: 24px; }
  .tab-panel { display: none; }
  .tab-panel.active { display: block; }

  /* Filter + bulk assign bar */
  .filter-bar { background: #1a1d2e; border: 1px solid #2d3148; border-radius: 10px; padding: 14px 18px; margin-bottom: 18px; display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
  .filter-bar label { font-size: 12px; color: #64748b; display: block; margin-bottom: 4px; }
  .filter-bar select { background: #0f1117; border: 1px solid #2d3148; border-radius: 6px; color: #e2e8f0; padding: 6px 10px; font-size: 13px; cursor: pointer; outline: none; min-width: 220px; }
  .filter-bar select:focus { border-color: #6366f1; }
  .bulk-panel { display: none; flex-wrap: wrap; gap: 10px; align-items: flex-end; border-top: 1px solid #2d3148; padding-top: 12px; margin-top: 4px; width: 100%; }
  .bulk-panel.visible { display: flex; }
  .bulk-panel label { font-size: 12px; color: #f59e0b; display: block; margin-bottom: 4px; }
  .bulk-panel select { background: #0f1117; border: 1px solid #374151; border-radius: 6px; color: #e2e8f0; padding: 6px 10px; font-size: 13px; cursor: pointer; outline: none; min-width: 260px; }
  .btn-bulk { background: #1e3a5f; border: 1px solid #3b82f6; border-radius: 6px; color: #93c5fd; padding: 7px 16px; font-size: 13px; cursor: pointer; transition: background 0.15s; white-space: nowrap; }
  .btn-bulk:hover { background: #1d4ed8; color: #fff; }
  .filter-count { font-size: 12px; color: #64748b; margin-left: auto; align-self: center; }

  /* Cards */
  .card { background: #1a1d2e; border: 1px solid #2d3148; border-radius: 10px; margin-bottom: 14px; overflow: hidden; transition: border-color 0.2s; }
  .card.resolved-card { border-color: #22c55e44; }
  .card.skipped-card  { border-color: #64748b44; opacity: 0.6; }
  .card.hidden-by-filter { display: none; }
  .card-header { padding: 12px 16px 10px; border-bottom: 1px solid #2d3148; display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
  .card-meta { display: flex; gap: 7px; align-items: center; margin-bottom: 4px; flex-wrap: wrap; }
  .card-num { font-size: 11px; color: #4b5563; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px; }
  .card-playlist { font-size: 11px; color: #6366f1; font-weight: 500; }
  .card-method { font-size: 11px; color: #f59e0b; }
  .card-auto-reason { font-size: 11px; color: #22c55e; font-style: italic; }
  .card-parsed { font-size: 12px; margin-bottom: 3px; }
  .card-original { font-family: "Consolas","Courier New",monospace; font-size: 11px; color: #4b5563; word-break: break-all; }
  .score-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; white-space: nowrap; flex-shrink: 0; }
  .score-100  { background: #14532d; color: #86efac; }
  .score-high { background: #1e3a5f; color: #93c5fd; }
  .score-low  { background: #3b1f6e; color: #c4b5fd; }
  .candidates { padding: 10px 16px 6px; }
  .candidate { display: flex; align-items: flex-start; gap: 10px; padding: 8px 10px; border-radius: 7px; cursor: pointer; transition: background 0.15s; margin-bottom: 5px; border: 1px solid transparent; }
  .candidate:hover { background: #12151f; }
  .candidate.selected-candidate { background: #1e2044; border-color: #6366f1; }
  .candidate.auto-pick { background: #0f2a1a; border-color: #22c55e44; }
  .candidate.auto-pick.selected-candidate { border-color: #22c55e; }
  .candidate input[type=radio] { margin-top: 2px; accent-color: #6366f1; flex-shrink: 0; cursor: pointer; }
  .cand-info { font-size: 12px; line-height: 1.6; min-width: 0; }
  .cand-tags { margin-bottom: 2px; }
  .cand-tags .artist { color: #c4b5fd; }
  .cand-tags .sep { color: #4b5563; }
  .cand-tags .title { color: #93c5fd; }
  .cand-tags .album { color: #64748b; }
  .cand-path { font-family: "Consolas","Courier New",monospace; font-size: 11px; color: #64748b; word-break: break-all; }
  .selected-candidate .cand-path { color: #94a3b8; }
  .selected-candidate .cand-path .fname { color: #e2e8f0; }
  .cand-path .fname { color: #94a3b8; }

  /* Manual path option */
  .manual-option { display: flex; align-items: flex-start; gap: 10px; padding: 8px 10px; border-radius: 7px; margin-bottom: 5px; border: 1px solid transparent; }
  .manual-option.selected-candidate { background: #1e2044; border-color: #6366f1; }
  .manual-option input[type=radio] { margin-top: 8px; accent-color: #6366f1; flex-shrink: 0; cursor: pointer; }
  .manual-input-wrap { flex: 1; }
  .manual-input-wrap label { font-size: 12px; color: #64748b; display: block; margin-bottom: 5px; cursor: pointer; }
  .manual-path-input { width: 100%; background: #0f1117; border: 1px solid #374151; border-radius: 6px; color: #e2e8f0; padding: 7px 10px; font-size: 12px; font-family: "Consolas","Courier New",monospace; outline: none; }
  .manual-path-input:focus { border-color: #6366f1; }
  .manual-path-input::placeholder { color: #4b5563; }

  .card-actions { padding: 3px 16px 12px; display: flex; align-items: center; gap: 8px; }
  .btn-skip { font-size: 12px; padding: 4px 12px; border-radius: 6px; border: 1px solid #2d3148; background: none; color: #64748b; cursor: pointer; transition: all 0.15s; }
  .btn-skip:hover { color: #e2e8f0; border-color: #64748b; }
  .btn-skip.active { color: #e2e8f0; border-color: #64748b; background: #1f2937; }
  .status-icon { font-size: 13px; margin-left: auto; }
  .missing-card { background: #1a1d2e; border: 1px solid #2d3148; border-radius: 8px; padding: 12px 16px; margin-bottom: 10px; }
  .missing-playlist { font-size: 11px; color: #6366f1; margin-bottom: 4px; }
  .missing-original { font-family: "Consolas","Courier New",monospace; font-size: 11px; color: #64748b; word-break: break-all; }
  .missing-parsed { font-size: 12px; color: #94a3b8; margin-bottom: 3px; }
  /* Library search */
  .lib-search-wrap { position: relative; flex: 1; min-width: 200px; }
  .lib-search-input { width: 100%; background: #0f1117; border: 1px solid #2d3148; border-radius: 6px; color: #e2e8f0; padding: 6px 10px; font-size: 13px; outline: none; }
  .lib-search-input:focus { border-color: #6366f1; }
  .lib-search-input.album-search:focus { border-color: #f59e0b; }
  .lib-dropdown { display: none; }
  .manual-search-wrap { display: flex; gap: 6px; align-items: flex-start; flex-wrap: wrap; margin-top: 4px; }

  /* Search modal (command-palette style) */
  .search-modal-backdrop { display: none; position: fixed; inset: 0; background: #00000088; z-index: 500; align-items: flex-start; justify-content: center; padding-top: 80px; }
  .search-modal-backdrop.visible { display: flex; }
  .search-modal { background: #1a1d2e; border: 1px solid #374151; border-radius: 12px; width: min(720px, 92vw); max-height: 70vh; display: flex; flex-direction: column; box-shadow: 0 24px 60px #000000bb; overflow: hidden; }
  .search-modal-header { padding: 14px 18px 12px; border-bottom: 1px solid #2d3148; display: flex; align-items: center; gap: 12px; }
  .search-modal-label { font-size: 12px; color: #64748b; white-space: nowrap; }
  .search-modal-input { flex: 1; background: #0f1117; border: 1px solid #374151; border-radius: 6px; color: #e2e8f0; padding: 8px 12px; font-size: 14px; outline: none; }
  .search-modal-input:focus { border-color: #6366f1; }
  .search-modal-input.album-modal-input:focus { border-color: #f59e0b; }
  .search-modal-close { background: none; border: none; color: #64748b; cursor: pointer; font-size: 18px; padding: 2px 6px; line-height: 1; }
  .search-modal-close:hover { color: #e2e8f0; }
  .search-modal-results { overflow-y: auto; flex: 1; }
  .search-modal-empty { padding: 32px; text-align: center; color: #4b5563; font-size: 14px; }
  .search-modal-hint { padding: 32px; text-align: center; color: #4b5563; font-size: 13px; }
  .lib-item { padding: 14px 18px; cursor: pointer; border-bottom: 1px solid #2d314822; transition: background 0.1s; }
  .lib-item:hover, .lib-item.active { background: #23263a; }
  .li-title { color: #93c5fd; font-weight: 600; font-size: 14px; }
  .li-artist { color: #c4b5fd; font-size: 14px; }
  .li-album { color: #64748b; font-size: 13px; }
  .li-path { font-family: "Consolas","Courier New",monospace; font-size: 12px; color: #6b7280; margin-top: 4px; word-break: break-all; line-height: 1.5; }
  .li-path .li-fname { color: #94a3b8; font-weight: 500; }
  .li-album-name { font-size: 15px; color: #e2e8f0; font-weight: 600; }
  .li-album-meta { font-size: 13px; color: #64748b; margin-top: 3px; }
  .search-modal-footer { padding: 8px 18px; border-top: 1px solid #2d3148; font-size: 11px; color: #4b5563; display: flex; gap: 16px; }
  .search-modal-footer kbd { background: #2d3148; border-radius: 3px; padding: 1px 5px; color: #94a3b8; font-size: 11px; }
  .empty-tab { text-align: center; padding: 60px 24px; color: #4b5563; font-size: 14px; }
  .footer-bar { position: fixed; bottom: 0; left: 0; right: 0; background: #1a1d2e; border-top: 1px solid #2d3148; padding: 12px 24px; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
  .footer-status { font-size: 13px; color: #94a3b8; }
  .footer-status strong { color: #e2e8f0; }
  .btn-download { background: #6366f1; color: #fff; border: none; border-radius: 8px; padding: 9px 20px; font-size: 13px; font-weight: 600; cursor: pointer; transition: background 0.15s, opacity 0.15s; }
  .btn-download:hover:not(:disabled) { background: #4f46e5; }
  .btn-download:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
</head>
<body>
<header>
  <div class="header-left">
    <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="#6366f1" stroke-width="2">
      <path stroke-linecap="round" stroke-linejoin="round" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"/>
    </svg>
    <h1>Playlist Repair</h1>
  </div>
  <span class="progress-text" id="progress-text"></span>
</header>
<div class="progress-bar-wrap"><div class="progress-bar-fill" id="progress-fill" style="width:0%"></div></div>

<div class="tabs">
  <div class="tab active" id="tab-review"  onclick="showTab('review')">To Review <span class="count" id="cnt-review">0</span></div>
  <div class="tab" id="tab-auto"   onclick="showTab('auto')">Auto-selected <span class="count" id="cnt-auto">0</span></div>
  <div class="tab" id="tab-missing" onclick="showTab('missing')">Missing <span class="count tab-warn" id="cnt-missing">0</span></div>
</div>

<div class="container">
  <!-- TO REVIEW TAB -->
  <div class="tab-panel active" id="panel-review">
    <div class="filter-bar">
      <div>
        <label for="pl-filter">Filter by playlist</label>
        <select id="pl-filter" onchange="applyFilter()">
          <option value="">All playlists</option>
        </select>
      </div>
      <div class="filter-count" id="filter-count"></div>
      <div class="bulk-panel" id="bulk-panel">
        <div style="width:100%">
          <label style="font-size:12px;color:#f59e0b;display:block;margin-bottom:8px">Bulk assign album to filtered tracks</label>
          <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap">
            <div style="flex:1;min-width:200px">
              <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px">From candidates</label>
              <select id="bulk-album" style="width:100%;background:#0f1117;border:1px solid #374151;border-radius:6px;color:#e2e8f0;padding:6px 10px;font-size:13px;outline:none;cursor:pointer">
                <option value="">-- select album --</option>
              </select>
            </div>
            <div style="flex:1;min-width:200px">
              <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px">Search full library</label>
              <div style="display:flex;gap:6px;align-items:center">
                <input type="text" class="lib-search-input" id="bulk-album-display"
                  placeholder="No album selected"
                  readonly style="flex:1;cursor:pointer;background:#0f1117"
                  onclick="openAlbumModal()">
                <button type="button" class="btn-bulk" style="white-space:nowrap"
                  onclick="openAlbumModal()">&#128269; Browse</button>
              </div>
            </div>
            <button class="btn-bulk" onclick="applyBulkAlbum()">Apply to all matching</button>
          </div>
        </div>
      </div>
    </div>
    <div id="cards-review"></div>
  </div>

  <!-- AUTO-SELECTED TAB -->
  <div class="tab-panel" id="panel-auto"><div id="cards-auto"></div></div>

  <!-- MISSING TAB -->
  <div class="tab-panel" id="panel-missing"><div id="cards-missing"></div></div>
</div>

<!-- Track search modal -->
<div class="search-modal-backdrop" id="track-modal-backdrop" onclick="closeTrackModal(event)">
  <div class="search-modal">
    <div class="search-modal-header">
      <span class="search-modal-label">Search library</span>
      <input type="text" class="search-modal-input" id="track-modal-input"
        placeholder="Type title, artist, album or filename..."
        oninput="onTrackModalInput()" onkeydown="onTrackModalKey(event)" autocomplete="off">
      <button class="search-modal-close" onclick="closeTrackModalBtn()">&#x2715;</button>
    </div>
    <div class="search-modal-results" id="track-modal-results">
      <div class="search-modal-hint">Start typing to search your music library</div>
    </div>
    <div class="search-modal-footer">
      <span><kbd>&uarr;</kbd><kbd>&darr;</kbd> navigate</span>
      <span><kbd>Enter</kbd> select</span>
      <span><kbd>Esc</kbd> close</span>
    </div>
  </div>
</div>

<!-- Album search modal -->
<div class="search-modal-backdrop" id="album-modal-backdrop" onclick="closeAlbumModal(event)">
  <div class="search-modal">
    <div class="search-modal-header">
      <span class="search-modal-label">Search albums</span>
      <input type="text" class="search-modal-input album-modal-input" id="album-modal-input"
        placeholder="Type album name or artist..."
        oninput="onAlbumModalInput()" onkeydown="onAlbumModalKey(event)" autocomplete="off">
      <button class="search-modal-close" onclick="closeAlbumModalBtn()">&#x2715;</button>
    </div>
    <div class="search-modal-results" id="album-modal-results">
      <div class="search-modal-hint">Start typing to search albums in your library</div>
    </div>
    <div class="search-modal-footer">
      <span><kbd>&uarr;</kbd><kbd>&darr;</kbd> navigate</span>
      <span><kbd>Enter</kbd> select</span>
      <span><kbd>Esc</kbd> close</span>
    </div>
  </div>
</div>

<div class="footer-bar">
  <div class="footer-status" id="footer-status"></div>
  <button class="btn-download" id="download-btn" onclick="downloadSelections()">Download selections.json</button>
</div>

<script>
const AMBIG      = PLACEHOLDER_AMBIG;
const LIB_TRACKS = PLACEHOLDER_LIB_TRACKS;
const LIB_ALBUMS = PLACEHOLDER_LIB_ALBUMS;
const AUTO    = PLACEHOLDER_AUTO;
const MISSING = PLACEHOLDER_MISSING;

const selections      = {};   // id -> {type:'candidate'|'manual', index, path}
const auto_selections = {};   // id -> index
AUTO.forEach(item => { auto_selections[item.id] = item.auto_index; });

let currentFilter = '';

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function scoreClass(s){if(!s||s<90)return 'score-low';if(s<100)return 'score-high';return 'score-100';}
function parsePath(p){const parts=p.replace(/\\/g,'/').split('/');const n=parts.length;return{artist:n>=3?parts[n-3]:'',album:n>=2?parts[n-2]:'',file:parts[n-1]||p};}

// ── Playlist filter ─────────────────────────────────────────────────────────
function buildPlaylistFilter() {
  const playlists = [...new Set(AMBIG.map(i => i.playlist))].sort();
  const sel = document.getElementById('pl-filter');
  playlists.forEach(pl => {
    const opt = document.createElement('option');
    opt.value = opt.textContent = pl;
    sel.appendChild(opt);
  });
}

function applyFilter() {
  currentFilter = document.getElementById('pl-filter').value;
  let visible = 0;
  AMBIG.forEach((item, idx) => {
    const card = document.getElementById('card-r-' + idx);
    if (!card) return;
    const show = !currentFilter || item.playlist === currentFilter;
    card.classList.toggle('hidden-by-filter', !show);
    if (show) visible++;
  });
  const total = currentFilter ? AMBIG.filter(i => i.playlist === currentFilter).length : AMBIG.length;
  document.getElementById('filter-count').textContent =
    currentFilter ? `${visible} track${visible !== 1 ? 's' : ''} shown` : '';

  // Show/hide bulk panel and populate album list
  const bulkPanel = document.getElementById('bulk-panel');
  if (currentFilter) {
    bulkPanel.classList.add('visible');
    buildBulkAlbumList();
  } else {
    bulkPanel.classList.remove('visible');
  }
  updateProgress();
}

// ── Bulk album assignment ────────────────────────────────────────────────────
function buildBulkAlbumList() {
  const albumMap = {};  // album_norm -> {display, candidates: [{itemIdx, candIdx}]}
  AMBIG.forEach((item, idx) => {
    if (item.playlist !== currentFilter) return;
    item.candidates.forEach((cand, ci) => {
      const album = (cand.tags && cand.tags.album) ? cand.tags.album : '';
      if (!album) return;
      const key = album.toLowerCase();
      if (!albumMap[key]) albumMap[key] = { display: cand.tags.album, items: [] };
      albumMap[key].items.push({ itemIdx: idx, candIdx: ci });
    });
  });

  const sel = document.getElementById('bulk-album');
  sel.innerHTML = '<option value="">-- select album --</option>';
  Object.entries(albumMap)
    .sort((a, b) => a[0].localeCompare(b[0]))
    .forEach(([key, val]) => {
      const uniqueItems = new Set(val.items.map(i => i.itemIdx)).size;
      const opt = document.createElement('option');
      opt.value = key;
      opt.textContent = `${val.display}  (${uniqueItems} track${uniqueItems !== 1 ? 's' : ''})`;
      sel.appendChild(opt);
    });
}

function applyBulkAlbum() {
  const albumKey = document.getElementById('bulk-album').value;
  if (!albumKey) return;

  let applied = 0;
  AMBIG.forEach((item, idx) => {
    if (item.playlist !== currentFilter) return;
    // Find best candidate matching this album
    const match = item.candidates.findIndex(
      c => c.tags && c.tags.album && c.tags.album.toLowerCase() === albumKey
    );
    if (match >= 0) {
      selectCandidate(item.id, idx, match, false, true);
      applied++;
    }
  });

  if (applied === 0) {
    alert('No tracks in this playlist have candidates from that album.');
  }
  updateProgress();
}

// ── Card rendering ───────────────────────────────────────────────────────────
function renderCandidates(item, idx, isAuto) {
  const autoIdx = isAuto ? item.auto_index : null;
  const cands = item.candidates.map((cv, ci) => {
    const p    = parsePath(cv.abs_path);
    const tags = cv.tags || {};
    const isAutoPick = isAuto && ci === autoIdx;
    return `<div class="candidate${isAutoPick?' auto-pick':''}" id="cand-${idx}-${ci}" onclick="selectCandidate('${esc(item.id)}',${idx},${ci},${isAuto})">
      <input type="radio" name="sel-${idx}" id="radio-${idx}-${ci}" value="${ci}"${isAutoPick?' checked':''}>
      <div class="cand-info">
        <div class="cand-tags">
          ${tags.artist?`<span class="artist">${esc(tags.artist)}</span><span class="sep"> -- </span>`:''}
          <span class="title">${esc(tags.title||p.file)}</span>
          ${tags.album?`<span class="sep"> · </span><span class="album">${esc(tags.album)}</span>`:''}
        </div>
        <div class="cand-path">${esc(p.artist)}${p.artist?' / ':''}${esc(p.album)}${p.album?' / ':''}<span class="fname">${esc(p.file)}</span></div>
      </div></div>`;
  }).join('');

  // Manual path option (only on To Review tab, not Auto)
  const manualHtml = isAuto ? '' : `
    <div class="manual-option" id="manual-opt-${idx}">
      <input type="radio" name="sel-${idx}" id="radio-${idx}-manual" value="manual" onclick="selectManual('${esc(item.id)}',${idx})">
      <div class="manual-input-wrap">
        <label onclick="selectManual('${esc(item.id)}',${idx})" style="cursor:pointer">None of these — search library or enter path manually</label>
        <div class="manual-search-wrap">
          <button type="button" class="btn-skip" style="white-space:nowrap;padding:6px 14px"
            onclick="openTrackModal('${esc(item.id)}',${idx})">&#128269; Search library</button>
          <input type="text" class="manual-path-input" id="manual-path-${idx}"
            placeholder="E:\\Music\\Artist\\Album\\Song.mp3"
            oninput="onManualPathInput('${esc(item.id)}',${idx})"
            onclick="selectManual('${esc(item.id)}',${idx})"
            style="flex:1;min-width:180px;margin-top:0">
        </div>
      </div>
    </div>`;

  return cands + manualHtml;
}

function renderReviewCards() {
  const c = document.getElementById('cards-review');
  if (!AMBIG.length) { c.innerHTML='<div class="empty-tab">No tracks need manual review.</div>'; return; }
  c.innerHTML = AMBIG.map((item, idx) => {
    const sl  = item.score===100?'Exact match':`${item.score?item.score.toFixed(0):'?'}% match`;
    const cls = scoreClass(item.score);
    const parsedInfo = (item.parsed_artist||item.parsed_title) ?
      `<div class="card-parsed"><span style="color:#4b5563">Parsed: </span>${item.parsed_artist?`<span style="color:#c4b5fd">${esc(item.parsed_artist)}</span><span style="color:#4b5563"> -- </span>`:''}<span style="color:#93c5fd">${esc(item.parsed_title||'')}</span></div>` : '';
    return `<div class="card" id="card-r-${idx}" data-playlist="${esc(item.playlist)}">
      <div class="card-header">
        <div style="flex:1;min-width:0">
          <div class="card-meta">
            <span class="card-num">Track ${idx+1} of ${AMBIG.length}</span>
            <span class="card-playlist">${esc(item.playlist)}</span>
            <span class="card-method">${esc(item.match_method)}</span>
          </div>
          ${parsedInfo}
          <div class="card-original">${esc(item.original)}</div>
        </div>
        <span class="score-badge ${cls}">${sl}</span>
      </div>
      <div class="candidates">${renderCandidates(item,idx,false)}</div>
      <div class="card-actions">
        <button class="btn-skip" id="skip-r-${idx}" onclick="skipCard('${esc(item.id)}',${idx})">Skip this track</button>
        <span class="status-icon" id="status-r-${idx}"></span>
      </div></div>`;
  }).join('');
}

function renderAutoCards() {
  const c = document.getElementById('cards-auto');
  if (!AUTO.length) { c.innerHTML='<div class="empty-tab">No auto-selected matches.</div>'; return; }
  c.innerHTML = AUTO.map((item,idx) => {
    const sl  = item.score===100?'Exact match':`${item.score?item.score.toFixed(0):'?'}% match`;
    const cls = scoreClass(item.score);
    return `<div class="card" id="card-a-${idx}">
      <div class="card-header">
        <div style="flex:1;min-width:0">
          <div class="card-meta">
            <span class="card-num">Track ${idx+1} of ${AUTO.length}</span>
            <span class="card-playlist">${esc(item.playlist)}</span>
            <span class="card-method">${esc(item.match_method)}</span>
          </div>
          <div class="card-auto-reason">Auto: ${esc(item.auto_reason)}</div>
          <div class="card-original">${esc(item.original)}</div>
        </div>
        <span class="score-badge ${cls}">${sl}</span>
      </div>
      <div class="candidates">${renderCandidates(item,idx,true)}</div>
      <div class="card-actions">
        <button class="btn-skip" id="skip-a-${idx}" onclick="skipAutoCard('${esc(item.id)}',${idx})">Remove auto-pick</button>
        <span class="status-icon" id="status-a-${idx}">✓</span>
      </div></div>`;
  }).join('');
}

function renderMissingCards() {
  const c = document.getElementById('cards-missing');
  if (!MISSING.length) { c.innerHTML='<div class="empty-tab">No missing tracks.</div>'; return; }
  c.innerHTML = MISSING.map(item =>
    `<div class="missing-card">
      <div class="missing-playlist">${esc(item.playlist)}</div>
      ${(item.parsed_artist||item.parsed_title)?`<div class="missing-parsed">${item.parsed_artist?`<span style="color:#c4b5fd">${esc(item.parsed_artist)}</span> -- `:''}<span style="color:#93c5fd">${esc(item.parsed_title||'')}</span></div>`:''}
      <div class="missing-original">${esc(item.original)}</div>
    </div>`
  ).join('');
}

// ── Selection handlers ───────────────────────────────────────────────────────
function selectCandidate(id, cardIdx, candIdx, isAuto, fromBulk) {
  if (isAuto) {
    auto_selections[id] = candIdx;
    document.querySelectorAll(`[id^="cand-${cardIdx}-"]`).forEach(el => {
      el.classList.remove('selected-candidate');
    });
    document.getElementById(`cand-${cardIdx}-${candIdx}`).classList.add('selected-candidate');
    document.getElementById(`radio-${cardIdx}-${candIdx}`).checked = true;
    document.getElementById(`skip-a-${cardIdx}`).textContent = 'Remove auto-pick';
    document.getElementById(`skip-a-${cardIdx}`).classList.remove('active');
    document.getElementById(`status-a-${cardIdx}`).textContent = '✓';
  } else {
    selections[id] = { type: 'candidate', index: candIdx };
    document.querySelectorAll(`[id^="cand-${cardIdx}-"]`).forEach(el => el.classList.remove('selected-candidate'));
    const manOpt = document.getElementById(`manual-opt-${cardIdx}`);
    if (manOpt) manOpt.classList.remove('selected-candidate');
    document.getElementById(`cand-${cardIdx}-${candIdx}`).classList.add('selected-candidate');
    document.getElementById(`radio-${cardIdx}-${candIdx}`).checked = true;
    document.getElementById(`card-r-${cardIdx}`).classList.remove('skipped-card');
    document.getElementById(`card-r-${cardIdx}`).classList.add('resolved-card');
    document.getElementById(`skip-r-${cardIdx}`).classList.remove('active');
    document.getElementById(`status-r-${cardIdx}`).textContent = '✓';
  }
  if (!fromBulk) updateProgress();
}

function selectManual(id, cardIdx) {
  document.getElementById(`radio-${cardIdx}-manual`).checked = true;
  document.querySelectorAll(`[id^="cand-${cardIdx}-"]`).forEach(el => el.classList.remove('selected-candidate'));
  const manOpt = document.getElementById(`manual-opt-${cardIdx}`);
  if (manOpt) manOpt.classList.add('selected-candidate');
  const path = document.getElementById(`manual-path-${cardIdx}`).value.trim();
  selections[id] = { type: 'manual', index: -1, path: path };
  document.getElementById(`card-r-${cardIdx}`).classList.remove('skipped-card');
  document.getElementById(`card-r-${cardIdx}`).classList.add('resolved-card');
  document.getElementById(`skip-r-${cardIdx}`).classList.remove('active');
  document.getElementById(`status-r-${cardIdx}`).textContent = path ? '✓' : '?';
  updateProgress();
}

function onManualPathInput(id, cardIdx) {
  const path = document.getElementById(`manual-path-${cardIdx}`).value.trim();
  selections[id] = { type: 'manual', index: -1, path: path };
  document.getElementById(`status-r-${cardIdx}`).textContent = path ? '✓' : '?';
  updateProgress();
}

function skipCard(id, idx) {
  selections[id] = { type: 'skip', index: -1 };
  document.querySelectorAll(`input[name="sel-${idx}"]`).forEach(r => r.checked = false);
  document.querySelectorAll(`[id^="cand-${idx}-"]`).forEach(el => el.classList.remove('selected-candidate'));
  const manOpt = document.getElementById(`manual-opt-${idx}`);
  if (manOpt) manOpt.classList.remove('selected-candidate');
  document.getElementById(`card-r-${idx}`).classList.remove('resolved-card');
  document.getElementById(`card-r-${idx}`).classList.add('skipped-card');
  document.getElementById(`skip-r-${idx}`).classList.add('active');
  document.getElementById(`status-r-${idx}`).textContent = '--';
  updateProgress();
}

function skipAutoCard(id, idx) {
  delete auto_selections[id];
  document.querySelectorAll(`input[name="sel-${idx}"]`).forEach(r => r.checked = false);
  document.querySelectorAll(`[id^="cand-${idx}-"]`).forEach(el => el.classList.remove('selected-candidate','auto-pick'));
  document.getElementById(`skip-a-${idx}`).classList.add('active');
  document.getElementById(`skip-a-${idx}`).textContent = 'Removed';
  document.getElementById(`status-a-${idx}`).textContent = '--';
  updateProgress();
}

// ── Progress + download ──────────────────────────────────────────────────────
function updateProgress() {
  const manualDone = Object.values(selections).filter(s => s.type !== 'skip' && (s.index >= 0 || (s.type === 'manual' && s.path))).length;
  const manualSkip = Object.values(selections).filter(s => s.type === 'skip' || (s.type === 'manual' && !s.path)).length;
  const autoDone   = Object.keys(auto_selections).length;
  const reviewTotal = AMBIG.length;
  const reviewDone  = manualDone + manualSkip;
  const pct = reviewTotal > 0 ? (reviewDone / reviewTotal * 100) : 100;

  document.getElementById('progress-fill').style.width = pct + '%';
  document.getElementById('progress-text').textContent =
    `Review: ${reviewDone}/${reviewTotal}  ·  Auto: ${autoDone}/${AUTO.length}`;
  document.getElementById('footer-status').innerHTML =
    `<strong>${manualDone}</strong> picked &nbsp;·&nbsp; <strong>${manualSkip}</strong> skipped &nbsp;·&nbsp; <strong>${autoDone}</strong> auto &nbsp;·&nbsp; <strong>${reviewTotal - reviewDone}</strong> remaining`;

  const total = manualDone + autoDone;
  const dlBtn = document.getElementById('download-btn');
  dlBtn.disabled = total === 0;
  dlBtn.textContent = total > 0 ?
    `Download selections.json (${total} track${total !== 1 ? 's' : ''})` :
    'Download selections.json';

  document.getElementById('cnt-review').textContent  = reviewTotal;
  document.getElementById('cnt-auto').textContent    = AUTO.length;
  document.getElementById('cnt-missing').textContent = MISSING.length;
}

function showTab(name) {
  ['review','auto','missing'].forEach(t => {
    document.getElementById('tab-' + t).classList.toggle('active', t === name);
    document.getElementById('panel-' + t).classList.toggle('active', t === name);
  });
}

function downloadSelections() {
  const all = {};
  // Auto picks first
  AUTO.forEach(item => {
    if (auto_selections[item.id] !== undefined) {
      all[item.id] = { id: item.id, playlist: item.playlist, filename: item.filename,
                       selected_index: auto_selections[item.id], manual_path: null };
    }
  });
  // Manual review picks (override auto if same id)
  AMBIG.forEach(item => {
    const sel = selections[item.id];
    if (!sel) return;
    if (sel.type === 'candidate' && sel.index >= 0) {
      all[item.id] = { id: item.id, playlist: item.playlist, filename: item.filename,
                       selected_index: sel.index, manual_path: null };
    } else if (sel.type === 'manual' && sel.path) {
      all[item.id] = { id: item.id, playlist: item.playlist, filename: item.filename,
                       selected_index: null, manual_path: sel.path };
    }
  });
  const output = {
    generated: new Date().toISOString(),
    total_items: AMBIG.length + AUTO.length,
    selections: Object.values(all)
  };
  const blob = new Blob([JSON.stringify(output, null, 2)], {type: 'application/json'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = 'playlist_selections.json'; a.click();
}


// ── Library search (modal) ──────────────────────────────────────────────────

let selectedBulkAlbum  = null;  // {key, display, items}
let trackModalTarget   = null;  // {id, idx} — which card opened track modal
let trackModalTimer    = null;
let albumModalTimer    = null;

function normQ(s) {
  return String(s).toLowerCase()
    .replace(/[&]/g, 'and').replace(/[-_.]/g, ' ').replace(/\s+/g, ' ').trim();
}

// ── Track search modal ────────────────────────────────────────────────────────
function openTrackModal(id, idx) {
  trackModalTarget = { id, idx };
  document.getElementById('track-modal-input').value = '';
  document.getElementById('track-modal-results').innerHTML =
    '<div class="search-modal-hint">Start typing to search your music library</div>';
  document.getElementById('track-modal-backdrop').classList.add('visible');
  setTimeout(() => document.getElementById('track-modal-input').focus(), 50);
  selectManual(id, idx);
}

function closeTrackModal(e) {
  if (e.target === document.getElementById('track-modal-backdrop'))
    document.getElementById('track-modal-backdrop').classList.remove('visible');
}
function closeTrackModalBtn() {
  document.getElementById('track-modal-backdrop').classList.remove('visible');
}

function onTrackModalInput() {
  clearTimeout(trackModalTimer);
  const val = document.getElementById('track-modal-input').value.trim();
  const res = document.getElementById('track-modal-results');
  if (val.length < 2) {
    res.innerHTML = '<div class="search-modal-hint">Start typing to search your music library</div>';
    return;
  }
  trackModalTimer = setTimeout(() => {
    const q = normQ(val);
    const hits = [];
    for (let i = 0; i < LIB_TRACKS.length && hits.length < 20; i++) {
      const t = LIB_TRACKS[i]; // [path, title, artist, album_display]
      if (normQ((t[1]||'') + ' ' + (t[2]||'') + ' ' + (t[3]||'') + ' ' + t[0]).includes(q))
        hits.push(t);
    }
    if (!hits.length) {
      res.innerHTML = '<div class="search-modal-empty">No results found</div>';
      return;
    }
    res.innerHTML = hits.map((t, ri) => {
      const parts = t[0].replace(/\\/g, '/').split('/');
      const fname = parts.pop() || t[0];
      const folder = parts.slice(-2).join(' / ');
      return `<div class="lib-item" data-ri="${ri}" data-path="${esc(t[0])}"
        onmouseenter="modalSetActive('track-modal-results',${ri})"
        onclick="pickTrackFromModal('${esc(t[0])}')">
        <div>
          ${t[2] ? '<span class="li-artist">' + esc(t[2]) + '</span><span style="color:#4b5563"> &mdash; </span>' : ''}
          <span class="li-title">${esc(t[1] || fname)}</span>
          ${t[3] ? '<span style="color:#4b5563"> &middot; </span><span class="li-album">' + esc(t[3]) + '</span>' : ''}
        </div>
        <div class="li-path">
          <span style="color:#4b5563">${esc(folder)}</span>
          ${folder ? '<span style="color:#4b5563"> / </span>' : ''}
          <span class="li-fname">${esc(fname)}</span>
        </div>
      </div>`;
    }).join('');
  }, 160);
}

function onTrackModalKey(e) {
  modalKey(e, 'track-modal-results', el => pickTrackFromModal(el.dataset.path));
}

function pickTrackFromModal(path) {
  if (!trackModalTarget) return;
  const { id, idx } = trackModalTarget;
  document.getElementById('manual-path-' + idx).value = path;
  document.getElementById('track-modal-backdrop').classList.remove('visible');
  selections[id] = { type: 'manual', index: -1, path };
  const card = document.getElementById('card-r-' + idx);
  if (card) { card.classList.remove('skipped-card'); card.classList.add('resolved-card'); }
  document.querySelectorAll('[id^="cand-' + idx + '-"]').forEach(el => el.classList.remove('selected-candidate'));
  const mo = document.getElementById('manual-opt-' + idx);
  if (mo) mo.classList.add('selected-candidate');
  const rb = document.getElementById('radio-' + idx + '-manual');
  if (rb) rb.checked = true;
  document.getElementById('skip-r-' + idx).classList.remove('active');
  document.getElementById('status-r-' + idx).textContent = '\u2713';
  updateProgress();
}

// ── Album search modal ────────────────────────────────────────────────────────
function openAlbumModal() {
  document.getElementById('album-modal-input').value = '';
  document.getElementById('album-modal-results').innerHTML =
    '<div class="search-modal-hint">Start typing to search albums in your library</div>';
  document.getElementById('album-modal-backdrop').classList.add('visible');
  setTimeout(() => document.getElementById('album-modal-input').focus(), 50);
}

function closeAlbumModal(e) {
  if (e.target === document.getElementById('album-modal-backdrop'))
    document.getElementById('album-modal-backdrop').classList.remove('visible');
}
function closeAlbumModalBtn() {
  document.getElementById('album-modal-backdrop').classList.remove('visible');
}

function onAlbumModalInput() {
  clearTimeout(albumModalTimer);
  const val = document.getElementById('album-modal-input').value.trim();
  const res = document.getElementById('album-modal-results');
  if (val.length < 2) {
    res.innerHTML = '<div class="search-modal-hint">Start typing to search albums in your library</div>';
    return;
  }
  albumModalTimer = setTimeout(() => {
    const q = normQ(val);
    const hits = [];
    for (const [key, alb] of Object.entries(LIB_ALBUMS)) {
      if (hits.length >= 25) break;
      if (normQ(alb.d).includes(q) || (alb.a && normQ(alb.a).includes(q)))
        hits.push([key, alb]);
    }
    if (!hits.length) { res.innerHTML = '<div class="search-modal-empty">No albums found</div>'; return; }
    res.innerHTML = hits.map(([key, alb], ri) =>
      `<div class="lib-item" data-ri="${ri}" data-key="${esc(key)}"
        onmouseenter="modalSetActive('album-modal-results',${ri})"
        onclick="pickAlbumFromModal('${esc(key)}')">
        <div class="li-album-name">${esc(alb.d)}</div>
        <div class="li-album-meta">
          ${alb.a ? '<span style="color:#c4b5fd">' + esc(alb.a) + '</span> &middot; ' : ''}
          ${alb.items.length} track${alb.items.length !== 1 ? 's' : ''}
        </div>
      </div>`
    ).join('');
  }, 160);
}

function onAlbumModalKey(e) {
  modalKey(e, 'album-modal-results', el => pickAlbumFromModal(el.dataset.key));
}

function pickAlbumFromModal(key) {
  const alb = LIB_ALBUMS[key];
  if (!alb) return;
  selectedBulkAlbum = { key, display: alb.d, items: alb.items };
  document.getElementById('bulk-album-display').value = alb.d;
  document.getElementById('album-modal-backdrop').classList.remove('visible');
}

// ── Shared modal helpers ──────────────────────────────────────────────────────
function modalSetActive(resultsId, ri) {
  document.getElementById(resultsId).querySelectorAll('.lib-item')
    .forEach((el, i) => el.classList.toggle('active', i === ri));
}

function modalKey(e, resultsId, onSelect) {
  const res   = document.getElementById(resultsId);
  const items = Array.from(res.querySelectorAll('.lib-item'));
  if (!items.length) return;
  let cur = items.findIndex(el => el.classList.contains('active'));
  if (e.key === 'ArrowDown')  { e.preventDefault(); cur = Math.min(cur + 1, items.length - 1); }
  else if (e.key === 'ArrowUp')   { e.preventDefault(); cur = Math.max(cur - 1, 0); }
  else if (e.key === 'Enter' && cur >= 0) { e.preventDefault(); onSelect(items[cur]); return; }
  else if (e.key === 'Escape') {
    document.querySelectorAll('.search-modal-backdrop').forEach(b => b.classList.remove('visible'));
    return;
  }
  items.forEach((el, i) => el.classList.toggle('active', i === cur));
  items[cur] && items[cur].scrollIntoView({ block: 'nearest' });
}

// Global Esc handler
document.addEventListener('keydown', e => {
  if (e.key === 'Escape')
    document.querySelectorAll('.search-modal-backdrop').forEach(b => b.classList.remove('visible'));
});

// ── Override applyBulkAlbum ──────────────────────────────────────────────────
function applyBulkAlbum() {
  if (selectedBulkAlbum) {
    let applied = 0;
    AMBIG.forEach((item, idx) => {
      if (item.playlist !== currentFilter) return;
      const trackTitle = normQ(item.parsed_title || '');
      if (!trackTitle) return;
      let bestPath = null, bestScore = 0;
      selectedBulkAlbum.items.forEach(([path, titleNorm]) => {
        if (!titleNorm) return;
        const tn = normQ(titleNorm);
        if (tn === trackTitle || tn.includes(trackTitle) || trackTitle.includes(tn)) {
          const score = Math.min(tn.length, trackTitle.length) / Math.max(tn.length, trackTitle.length);
          if (score > bestScore) { bestScore = score; bestPath = path; }
        }
      });
      if (bestPath && bestScore >= 0.7) {
        selections[item.id] = { type: 'manual', index: -1, path: bestPath };
        const card = document.getElementById('card-r-' + idx);
        if (card) { card.classList.remove('skipped-card'); card.classList.add('resolved-card'); }
        document.getElementById('skip-r-' + idx).classList.remove('active');
        document.getElementById('status-r-' + idx).textContent = '\u2713';
        applied++;
      }
    });
    if (!applied) alert('No title matches found for tracks in this playlist from that album.');
    else updateProgress();
    return;
  }
  // Fall back: candidates dropdown
  const albumKey = document.getElementById('bulk-album').value;
  if (!albumKey) { alert('Select an album first.'); return; }
  let applied = 0;
  AMBIG.forEach((item, idx) => {
    if (item.playlist !== currentFilter) return;
    const match = item.candidates.findIndex(
      c => c.tags && c.tags.album && c.tags.album.toLowerCase() === albumKey
    );
    if (match >= 0) { selectCandidate(item.id, idx, match, false, true); applied++; }
  });
  if (!applied) alert('No tracks in this playlist have candidates from that album.');
  updateProgress();
}


buildPlaylistFilter();
renderReviewCards();
renderAutoCards();
renderMissingCards();
updateProgress();
</script>
</body>
</html>"""


def build_library_indexes(entries: list) -> tuple:
    """
    Build two compact indexes from library entries for the HTML selector.
      lib_tracks : [[path, title, artist, album_display], ...]  -- for track search
      lib_albums : {album_norm: {d:display, a:artist, items:[[path,title_norm],...]}}
    """
    tracks = []
    albums = {}
    for entry in entries:
        path        = str(entry.get("path", ""))
        title       = entry.get("title", "")
        artist      = entry.get("artist", "")
        album_norm  = entry.get("album", "")
        try:
            album_display = Path(path).parent.name
        except Exception:
            album_display = album_norm
        if title or artist:
            tracks.append([path, title, artist, album_display])
        if album_norm:
            if album_norm not in albums:
                albums[album_norm] = {"d": album_display, "a": artist, "items": []}
            albums[album_norm]["items"].append([path, title])
    return tracks, albums


def build_html_selector(all_results: dict, missing_entries: list,
                        library_entries=None) -> str:
    ambig_items = []
    auto_items  = []

    for pl_path, lines in all_results.items():
        for line in lines:
            status = line.get("status")
            if status not in ("ambiguous", "auto"):
                continue
            candidates = []
            for entry in line["candidates"]:
                candidates.append({
                    "rel_path": to_relative_path(entry["path"], pl_path),
                    "abs_path": str(entry["path"]),
                    "tags": {
                        "title":  entry.get("title", ""),
                        "artist": entry.get("artist", ""),
                        "album":  entry.get("album",  ""),
                    }
                })
            item = {
                "id":            f"{pl_path.name}::{line['line_num']}",
                "playlist":      pl_path.name,
                "original":      line["raw"],
                "filename":      line["filename"],
                "score":         line.get("score"),
                "match_method":  line.get("match_method", ""),
                "parsed_artist": line.get("parsed_artist", ""),
                "parsed_title":  line.get("parsed_title",  ""),
                "auto_index":    line.get("auto_index"),
                "auto_reason":   line.get("auto_reason", ""),
                "candidates":    candidates,
            }
            if status == "auto":
                auto_items.append(item)
            else:
                ambig_items.append(item)

    missing_items = [
        {
            "playlist":      pl_name,
            "original":      line["raw"],
            "parsed_artist": line.get("parsed_artist", ""),
            "parsed_title":  line.get("parsed_title",  ""),
        }
        for pl_name, line in missing_entries
    ]

    lib_tracks, lib_albums = [], {}
    if library_entries:
        lib_tracks, lib_albums = build_library_indexes(library_entries)

    html = HTML_TEMPLATE
    html = html.replace("PLACEHOLDER_AMBIG",      json.dumps(ambig_items,  ensure_ascii=False))
    html = html.replace("PLACEHOLDER_AUTO",       json.dumps(auto_items,   ensure_ascii=False))
    html = html.replace("PLACEHOLDER_MISSING",    json.dumps(missing_items, ensure_ascii=False))
    html = html.replace("PLACEHOLDER_LIB_TRACKS", json.dumps(lib_tracks,   ensure_ascii=False))
    html = html.replace("PLACEHOLDER_LIB_ALBUMS", json.dumps(lib_albums,   ensure_ascii=False))
    return html


# ══════════════════════════════════════════════════════════════════════════════
#  SELECTIONS JSON
# ══════════════════════════════════════════════════════════════════════════════

def load_selections(selections_path: str) -> dict:
    """
    Load selections JSON. Returns {id: {index, manual_path}} where
    index is an int candidate index or None for manual paths.
    """
    p = Path(selections_path)
    if not p.exists():
        print(f"ERROR: Selections file not found: {p}")
        sys.exit(1)
    try:
        data   = json.loads(p.read_text(encoding="utf-8"))
        result = {}
        for item in data.get("selections", []):
            sel_idx  = item.get("selected_index")
            man_path = item.get("manual_path") or ""
            item_id  = item.get("id")
            if not item_id:
                continue
            if man_path:
                result[item_id] = {"index": None, "manual_path": man_path.strip()}
            elif sel_idx is not None:
                result[item_id] = {"index": sel_idx, "manual_path": ""}
        print(f"  Selections loaded: {len(result)} decision(s) from {p.name}")
        manual_count = sum(1 for v in result.values() if v["manual_path"])
        if manual_count:
            print(f"    of which {manual_count} are manual path entries")
        return result
    except Exception as e:
        print(f"ERROR: Could not read selections file: {e}")
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
#  WRITE REPAIRED PLAYLISTS
# ══════════════════════════════════════════════════════════════════════════════

def write_repaired_playlists(all_results: dict, output_dir: Path,
                              selections: dict) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {"playlists": 0, "resolved": 0, "auto_resolved": 0,
               "manual_resolved": 0, "manual_path": 0, "skipped": 0, "missing": 0}

    for pl_path, lines in all_results.items():
        out_lines = []
        for line in lines:
            status = line.get("status", "skip")

            if status == "skip":
                out_lines.append(line["raw"])

            elif status == "resolved":
                rel = to_relative_path(line["candidates"][0]["path"], pl_path)
                out_lines.append(rel)
                summary["resolved"] += 1

            elif status == "auto":
                item_id = f"{pl_path.name}::{line['line_num']}"
                sel     = selections.get(item_id)
                if sel and sel.get("manual_path"):
                    # Manual override on an auto entry
                    out_lines.append(sel["manual_path"].replace("\\", "/"))
                    summary["manual_path"] += 1
                elif sel and sel.get("index") is not None and sel["index"] >= 0:
                    idx = sel["index"]
                    if idx < len(line["candidates"]):
                        rel = to_relative_path(line["candidates"][idx]["path"], pl_path)
                        out_lines.append(rel)
                        summary["auto_resolved"] += 1
                    else:
                        out_lines.append(f"# REPAIR_UNRESOLVED: index out of range")
                        out_lines.append(line["raw"])
                        summary["skipped"] += 1
                else:
                    # Use the auto_index
                    auto_idx = line.get("auto_index", 0)
                    if auto_idx is not None and auto_idx < len(line["candidates"]):
                        rel = to_relative_path(line["candidates"][auto_idx]["path"], pl_path)
                        out_lines.append(rel)
                        summary["auto_resolved"] += 1
                    else:
                        out_lines.append("# REPAIR_UNRESOLVED: auto index invalid")
                        out_lines.append(line["raw"])
                        summary["skipped"] += 1

            elif status == "ambiguous":
                item_id = f"{pl_path.name}::{line['line_num']}"
                sel     = selections.get(item_id)
                if sel and sel.get("manual_path"):
                    out_lines.append(sel["manual_path"].replace("\\", "/"))
                    summary["manual_path"] += 1
                elif sel and sel.get("index") is not None and sel["index"] >= 0:
                    idx = sel["index"]
                    if idx < len(line["candidates"]):
                        rel = to_relative_path(line["candidates"][idx]["path"], pl_path)
                        out_lines.append(rel)
                        summary["manual_resolved"] += 1
                    else:
                        out_lines.append(f"# REPAIR_UNRESOLVED: index out of range")
                        out_lines.append(line["raw"])
                        summary["skipped"] += 1
                else:
                    out_lines.append("# REPAIR_UNRESOLVED: multiple matches, not resolved")
                    out_lines.append(line["raw"])
                    summary["skipped"] += 1

            elif status == "missing":
                out_lines.append("# REPAIR_MISSING: not found in library - original path kept")
                out_lines.append(line["raw"])
                summary["missing"] += 1

        dest = output_dir / pl_path.name
        dest.write_text("\n".join(out_lines), encoding="utf-8")
        summary["playlists"] += 1
        print(f"  Written: {dest}")

    return summary

#  REPORTS
# ══════════════════════════════════════════════════════════════════════════════

def write_csv_report(csv_path: Path, all_results: dict, run_label: str,
                     timestamp: str, threshold: float):
    fieldnames = [
        "Run", "Timestamp", "Threshold", "Playlist", "Line",
        "Status", "Match Method", "Score",
        "Original Entry", "Filename",
        "Parsed Artist", "Parsed Title",
        "Auto Index", "Auto Reason",
        "Num Candidates", "Candidate Paths",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for pl_path, lines in all_results.items():
            for line in lines:
                if line["type"] in ("blank", "comment"):
                    continue
                writer.writerow({
                    "Run":             run_label,
                    "Timestamp":       timestamp,
                    "Threshold":       threshold,
                    "Playlist":        pl_path.name,
                    "Line":            line["line_num"],
                    "Status":          line.get("status", ""),
                    "Match Method":    line.get("match_method", ""),
                    "Score":           line.get("score", ""),
                    "Original Entry":  line["raw"],
                    "Filename":        line["filename"],
                    "Parsed Artist":   line.get("parsed_artist", ""),
                    "Parsed Title":    line.get("parsed_title", ""),
                    "Auto Index":      line.get("auto_index", ""),
                    "Auto Reason":     line.get("auto_reason", ""),
                    "Num Candidates":  len(line.get("candidates", [])),
                    "Candidate Paths": " | ".join(
                        str(e["path"]) for e in line.get("candidates", [])),
                })


def write_missing_log(log_path: Path, all_results: dict) -> list:
    """Write missing log and return list of (playlist_name, line) tuples."""
    missing_entries = []
    for pl_path, lines in sorted(all_results.items()):
        for line in lines:
            if line.get("status") == "missing":
                missing_entries.append((pl_path.name, line))

    out = ["=" * 70, "MISSING TRACKS - not found in music library", "=" * 70, ""]
    if not missing_entries:
        out.append("  No missing tracks - all entries were found in the library.")
    else:
        out.insert(3, f"  Total: {len(missing_entries)} track(s) not found")
        out.insert(4, "")
        by_playlist = {}
        for pl_name, line in missing_entries:
            by_playlist.setdefault(pl_name, []).append(line)
        for pl_name, entries in sorted(by_playlist.items()):
            out.append(f"Playlist: {pl_name}  ({len(entries)} missing)")
            out.append("-" * 50)
            for e in entries:
                artist = e.get("parsed_artist", "")
                title  = e.get("parsed_title", "")
                if artist or title:
                    out.append(f"  Parsed: {artist + ' - ' if artist else ''}{title}")
                out.append(f"  Original: {e['raw']}")
                out.append("")

    log_path.write_text("\n".join(out), encoding="utf-8")
    return missing_entries


# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC — SCAN  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_repair_playlists_scan(
    playlists_dir: Path,
    music_dir: Path,
    threshold: float = 85.0,
    cache_path: Path = None,
    reports_dir: Path = None,
    progress_callback=None,
    log_callback=None,
) -> dict:
    """
    Scan .m3u playlists and match tracks against the music library.

    Args:
        playlists_dir:     Folder containing .m3u files.
        music_dir:         Root of the music library.
        threshold:         Fuzzy match score cutoff (0–100, default 85).
        cache_path:        Path to music_cache.db; None = auto-detect or scan live.
        reports_dir:       Where to save reports; defaults to <script folder>/reports.
        progress_callback: Optional callable(current, total, message).
        log_callback:      Optional callable(message). Defaults to print().

    Returns:
        dict: all_results, counts, methods, missing_entries, playlists (list),
              entries (list), html_path (Path|None), csv_path (Path),
              missing_path (Path), reports_dir (Path), timestamp (str)

    Raises:
        ValueError: if playlists_dir or music_dir don't exist, or no .m3u files found.
    """
    log = log_callback or print

    if not playlists_dir.exists() or not playlists_dir.is_dir():
        raise ValueError(f"Playlists folder not found: {playlists_dir}")
    if not music_dir.exists() or not music_dir.is_dir():
        raise ValueError(f"Music library folder not found: {music_dir}")

    playlists = sorted(playlists_dir.glob("*.m3u"))
    if not playlists:
        raise ValueError(f"No .m3u files found in: {playlists_dir}")

    if reports_dir is None:
        reports_dir = SCRIPT_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Build library index ──
    resolved_cache = cache_path
    if resolved_cache is None and DEFAULT_CACHE is not None:
        resolved_cache = DEFAULT_CACHE

    if resolved_cache is not None and Path(resolved_cache).exists():
        entries = load_from_cache(resolved_cache)
    else:
        if resolved_cache is not None:
            log(f"  Cache not found at: {resolved_cache}")
        entries = scan_library(music_dir)

    log("Building indexes...")
    indexes = build_indexes(entries)
    log(f"  artist+title : {len(indexes['artist_title'])} entries")
    log(f"  title        : {len(indexes['title'])} entries")
    log(f"  stem         : {len(indexes['stem'])} entries")

    # ── Match all playlists ──
    log("Matching playlist entries...")
    all_results = match_all(playlists, indexes, threshold)

    # ── Tally results ──
    counts  = {"resolved": 0, "auto": 0, "ambiguous": 0, "missing": 0, "skip": 0}
    methods = {}
    for lines in all_results.values():
        for line in lines:
            s = line.get("status", "skip")
            counts[s] = counts.get(s, 0) + 1
            if line.get("match_method") and s != "skip":
                m = line["match_method"]
                methods[m] = methods.get(m, 0) + 1

    # ── Write reports ──
    csv_path     = reports_dir / f"playlist_repair_{timestamp}_dry.csv"
    missing_path = reports_dir / f"playlist_missing_{timestamp}.txt"

    write_csv_report(csv_path, all_results, "DRY RUN", timestamp, threshold)
    log(f"  CSV report   : {csv_path}")

    missing_entries = write_missing_log(missing_path, all_results)
    log(f"  Missing log  : {missing_path}  ({len(missing_entries)} missing)")

    html_path = None
    if counts["ambiguous"] > 0 or counts["auto"] > 0 or missing_entries:
        html = build_html_selector(all_results, missing_entries, entries)
        html_path = reports_dir / f"playlist_selector_{timestamp}.html"
        html_path.write_text(html, encoding="utf-8")
        log(f"  HTML selector: {html_path}")

    return {
        "all_results":     all_results,
        "counts":          counts,
        "methods":         methods,
        "missing_entries": missing_entries,
        "playlists":       playlists,
        "entries":         entries,
        "html_path":       html_path,
        "csv_path":        csv_path,
        "missing_path":    missing_path,
        "reports_dir":     reports_dir,
        "timestamp":       timestamp,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CORE LOGIC — APPLY  ← GUI calls this directly
# ══════════════════════════════════════════════════════════════════════════════

def run_repair_playlists_apply(
    all_results: dict,
    output_dir: Path,
    selections: dict = None,
    reports_dir: Path = None,
    log_callback=None,
) -> dict:
    """
    Write repaired playlist files using previously matched all_results.

    Args:
        all_results:  The all_results dict from run_repair_playlists_scan().
        output_dir:   Where to write the repaired .m3u files.
        selections:   User selections keyed by item id (from playlist_selections.json).
                      Pass {} or None to use auto-resolution only.
        reports_dir:  Reserved for future use.
        log_callback: Optional callable(message). Defaults to print().

    Returns:
        dict: playlists, resolved, auto_resolved, manual_resolved, manual_path,
              skipped, missing  (counts from write_repaired_playlists)
    """
    selections = selections or {}
    return write_repaired_playlists(all_results, output_dir, selections)


# ══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT  ← .cmd launchers call this; GUI does not
# ══════════════════════════════════════════════════════════════════════════════

def main():
    args = parse_args()

    print()
    if args.playlists:
        playlists_dir = Path(args.playlists)
    else:
        print("  Select your PLAYLISTS folder...")
        playlists_dir = pick_folder("Select folder containing your .m3u playlist files")

    if args.music:
        music_dir = Path(args.music)
    else:
        print("  Select your MUSIC LIBRARY folder...")
        music_dir = pick_folder("Select your music library root folder")

    output_dir  = Path(args.output_dir) if args.output_dir else playlists_dir / "repaired"
    reports_dir = Path(args.reports_dir) if args.reports_dir else SCRIPT_DIR / "reports"
    cache_path  = Path(args.cache) if args.cache else None

    print()
    print("=" * 65)
    print(f"Playlist Repair Tool  v1.8  [{'LIVE RUN' if args.apply else 'DRY RUN'}]")
    if not args.apply:
        print("*** DRY RUN: No playlists will be written ***")
    print(f"Started       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Playlists     : {playlists_dir}")
    print(f"Music library : {music_dir}")
    print(f"Fuzzy match   : {'rapidfuzz' if FUZZY_AVAILABLE else 'difflib'}  threshold={args.threshold}")
    print(f"Reports       : {reports_dir}")
    if args.apply:
        print(f"Output dir    : {output_dir}")
    print("=" * 65)
    print()

    try:
        scan_result = run_repair_playlists_scan(
            playlists_dir  = playlists_dir,
            music_dir      = music_dir,
            threshold      = args.threshold,
            cache_path     = cache_path,
            reports_dir    = reports_dir,
        )
    except ValueError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    counts = scan_result["counts"]
    print()
    print("Scan complete:")
    print(f"  Resolved   : {counts.get('resolved', 0)}")
    print(f"  Auto-match : {counts.get('auto', 0)}")
    print(f"  Ambiguous  : {counts.get('ambiguous', 0)}")
    print(f"  Missing    : {counts.get('missing', 0)}")
    print(f"  Skipped    : {counts.get('skip', 0)}")
    print(f"  CSV report : {scan_result['csv_path']}")
    if scan_result.get('missing_path'):
        print(f"  Missing log: {scan_result['missing_path']}")
    if scan_result.get('html_path'):
        print(f"  HTML selector: {scan_result['html_path']}")

    if not args.apply:
        print()
        print("  DRY RUN complete. No playlists written.")
        print("  If ambiguous matches exist, open the HTML selector, download")
        print("  selections.json, then re-run with --apply --selections <path>.")
        return

    # ── Apply: write repaired playlists ────────────────────────────────────
    selections = {}
    if args.selections:
        selections = load_selections(args.selections)
    elif scan_result["counts"].get("ambiguous", 0) > 0:
        print()
        print("  Ambiguous matches found. Optionally provide --selections <path>")
        print("  to apply manual choices; continuing with auto-resolution only.")

    apply_result = run_repair_playlists_apply(
        all_results  = scan_result["all_results"],
        output_dir   = output_dir,
        selections   = selections,
        reports_dir  = reports_dir,
    )

    print()
    print("Apply complete:")
    print(f"  Playlists written   : {apply_result.get('playlists', 0)}")
    print(f"  Auto-resolved       : {apply_result.get('auto_resolved', 0)}")
    print(f"  Manual-resolved     : {apply_result.get('manual_resolved', 0)}")
    print(f"  Manual path entries : {apply_result.get('manual_path', 0)}")
    print(f"  Still missing       : {apply_result.get('missing', 0)}")
    print(f"  Skipped/unresolved  : {apply_result.get('skipped', 0)}")
    print(f"  Output folder       : {output_dir}")
    print()


if __name__ == "__main__":
    main()
