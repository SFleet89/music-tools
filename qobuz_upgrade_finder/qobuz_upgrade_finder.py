#!/usr/bin/env python3
"""
qobuz_upgrade_finder.py — v1.6
Scan a music library, find albums that could be upgraded to higher quality,
and optionally look them up on Qobuz.

Dry run (default): local scan only — produces CSV + Excel reports.
--apply           : also queries Qobuz API — produces URL list + rip commands.
--from-excel PATH : (use with --apply) reads quality preferences from an
                    edited Excel report and generates two rip-command files:
                    one for lossless, one for 320 kbps.

Usage:
  python qobuz_upgrade_finder.py --pick
  python qobuz_upgrade_finder.py --path "E:\\Music" --apply
  python qobuz_upgrade_finder.py --path "E:\\Music" --apply --from-excel "reports\\qobuz_upgrade_report_20260617_204517.xlsx"
"""

import argparse
import csv
import difflib
import json
import os
import re
import sys
import time
from collections import defaultdict
from itertools import groupby
from datetime import datetime
from pathlib import Path

VERSION = "1.6"

AUDIO_EXTENSIONS = {
    '.mp3', '.m4a', '.aac', '.ogg', '.wma', '.opus',
    '.flac', '.wav', '.aiff', '.aif', '.ape', '.wv',
}
LOSSLESS_EXTENSIONS = {'.flac', '.wav', '.aiff', '.aif', '.ape', '.wv'}

QOBUZ_BASE = 'https://www.qobuz.com/api.json/0.2'
DEFAULT_APP_ID = '950096963'

STREAMRIP_CONFIG_PATHS = [
    Path(os.environ.get('APPDATA', '')) / 'streamrip' / 'config.toml',
    Path.home() / '.config' / 'streamrip' / 'config.toml',
    Path(os.environ.get('USERPROFILE', '')) / '.config' / 'streamrip' / 'config.toml',
]

# Bitrate threshold above which a value is considered a corrupt tag
SUSPICIOUS_BITRATE_THRESHOLD = 5000  # kbps

# Spotify downloads folders to cross-reference against upgrade candidates.
# These are always scanned at startup; missing folders are silently skipped.
DEFAULT_DOWNLOADS_FOLDERS = [
    Path(r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\Spotify\Organized"),
    Path(r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\Spotify\Still needs fixing"),
    Path(r"C:\Users\neo_s\Downloads\ThinQ Back Up 2024\Spotify\Streamrip"),
]

# Keywords that auto-classify an album as preferring lossless quality.
# Users can extend this list in music_config.json under "lossless_keywords",
# and add specific artists/albums under "lossless_artists"/"lossless_albums".
DEFAULT_LOSSLESS_KEYWORDS = [
    # Film / TV / game soundtracks
    'soundtrack', 'ost', 'original score', 'original sound track',
    'film score', 'motion picture', 'game music', 'anime',
    # Classical / orchestral
    'classical', 'symphony', 'orchestra', 'quartet', 'concerto', 'sonata',
    'philharmonic', 'chamber music', 'opera', 'ballet',
    # Trance / progressive / ambient EDM (where hi-res adds real value)
    'trance', 'progressive', 'anjuna', 'above & beyond',
    'tiesto', 'tiësto', 'armin van buuren', 'paul van dyk',
    'deadmau5', 'eric prydz', 'ambient', 'downtempo',
    # Jazz / acoustic
    'jazz', 'acoustic',
]

# ── Optional dependencies ──────────────────────────────────────────────────────

try:
    from mutagen import File as MutagenFile
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import tkinter as tk
    from tkinter import filedialog
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False

try:
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment
    from openpyxl.utils import get_column_letter
    try:
        from openpyxl.worksheet.properties import Outline as _WsOutline
    except ImportError:
        _WsOutline = None
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    _WsOutline = None

# ── Folder picker ──────────────────────────────────────────────────────────────

def pick_folder(title="Select music library folder") -> Path:
    if not TKINTER_AVAILABLE:
        print("ERROR: tkinter not available. Use --path instead.")
        sys.exit(1)
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder = filedialog.askdirectory(title=title)
    root.destroy()
    if not folder:
        print("No folder selected. Exiting.")
        sys.exit(0)
    return Path(folder)

# ── Config ────────────────────────────────────────────────────────────────────

def load_project_config() -> dict:
    """
    Load music_config.json from the script's directory if it exists.
    Returns the parsed dict, or an empty dict if not found or invalid.

    Supported keys:
      lossless_keywords : list of strings — extra keywords that mark an album
                          as preferring lossless quality (in addition to the
                          built-in DEFAULT_LOSSLESS_KEYWORDS list).
      lossless_artists  : list of artist name substrings — any album whose
                          artist contains one of these strings is auto-LOSSLESS.
      lossless_albums   : list of album title substrings — same, but matched
                          against the album title.

    Example music_config.json:
      {
        "lossless_keywords": ["bossa nova", "audiophile"],
        "lossless_artists":  ["Nils Frahm", "Yann Tiersen"],
        "lossless_albums":   ["Greatest Hits", "Remastered"]
      }
    """
    cfg_path = Path(__file__).parent / 'music_config.json'
    if not cfg_path.exists():
        return {}
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  Warning: could not read music_config.json — {e}")
        return {}


def _wants_lossless(artist: str, album: str, config: dict) -> bool:
    """
    Return True if this album should be downloaded at lossless quality.

    Checks combined artist+album text against DEFAULT_LOSSLESS_KEYWORDS plus
    any extras in config['lossless_keywords']. Also checks exact-ish lists
    in config['lossless_artists'] and config['lossless_albums'].
    """
    keywords = DEFAULT_LOSSLESS_KEYWORDS + config.get('lossless_keywords', [])
    text = f"{artist} {album}".lower()
    for kw in keywords:
        if kw.lower() in text:
            return True

    for a in config.get('lossless_artists', []):
        if a.lower() in artist.lower():
            return True
    for b in config.get('lossless_albums', []):
        if b.lower() in album.lower():
            return True

    return False

# ── Audio scanning ─────────────────────────────────────────────────────────────

def get_audio_info(path: Path) -> dict:
    """Read format, bitrate, and tags from an audio file."""
    ext = path.suffix.lower()
    info = {
        'path': str(path),
        'format': ext.lstrip('.').upper() or 'UNKNOWN',
        'bitrate_kbps': None,
        'is_lossless': ext in LOSSLESS_EXTENSIONS,
        'artist': '',
        'album': '',
        'title': '',
    }

    if not MUTAGEN_AVAILABLE:
        return info

    try:
        audio = MutagenFile(path, easy=True)
        if audio is None:
            return info

        tags = audio.tags or {}

        def tag(key):
            val = tags.get(key, [])
            return str(val[0]).strip() if val else ''

        info['artist'] = tag('artist') or tag('albumartist') or tag('performer')
        info['album']  = tag('album')
        info['title']  = tag('title')

        if not info['is_lossless']:
            audio_info = getattr(audio, 'info', None)
            if audio_info and hasattr(audio_info, 'bitrate') and audio_info.bitrate:
                info['bitrate_kbps'] = max(0, int(audio_info.bitrate / 1000))

    except Exception:
        pass

    return info


def scan_library(library_path: Path, min_bitrate: int = 320,
                  max_workers: int = None) -> dict:
    """
    Walk library, group files by album folder, and classify each album.
    Uses a thread pool for parallel metadata reads — much faster on large libraries.

    Classifications:
      LOSSLESS_PRESENT         — folder contains at least one lossless file
      AT_THRESHOLD_NO_LOSSLESS — all lossy files >= min_bitrate, no lossless
      BELOW_THRESHOLD          — at least one file below min_bitrate, no lossless
      UNKNOWN                  — could not read bitrate from any file
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed

    if max_workers is None:
        max_workers = min(os.cpu_count() or 4, 8)

    print(f"\nScanning: {library_path}  (threads: {max_workers})")

    audio_files = []
    for root, dirs, files in os.walk(library_path):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        for fname in sorted(files):
            if Path(fname).suffix.lower() in AUDIO_EXTENSIONS:
                audio_files.append(Path(root) / fname)

    total = len(audio_files)
    if total == 0:
        return {}

    print(f"Found {total:,} audio files. Analysing...")

    _lock = threading.Lock()
    _done = [0]

    albums: dict = defaultdict(lambda: {
        'folder': None,
        'artist_folder': None,
        'files': [],
        'has_lossless': False,
        'min_bitrate': None,
        'max_bitrate': None,
        'formats': set(),
        'tag_artist': '',
        'tag_album': '',
        'classification': 'UNKNOWN',
        'qobuz_url': '',
        'rip_command': '',
    })

    def _process(fpath):
        info = get_audio_info(fpath)
        key = str(fpath.parent)
        with _lock:
            a = albums[key]
            a['folder'] = fpath.parent
            a['artist_folder'] = fpath.parent.parent
            a['files'].append(info)
            a['formats'].add(info['format'])
            if info['is_lossless']:
                a['has_lossless'] = True
            elif info['bitrate_kbps'] is not None:
                if a['min_bitrate'] is None or info['bitrate_kbps'] < a['min_bitrate']:
                    a['min_bitrate'] = info['bitrate_kbps']
                if a['max_bitrate'] is None or info['bitrate_kbps'] > a['max_bitrate']:
                    a['max_bitrate'] = info['bitrate_kbps']
            if not a['tag_artist'] and info['artist']:
                a['tag_artist'] = info['artist']
            if not a['tag_album'] and info['album']:
                a['tag_album'] = info['album']
            _done[0] += 1
            if _done[0] % 500 == 0 or _done[0] == total:
                pct = int(_done[0] / total * 100)
                print(f"  [{pct:3d}%] {_done[0]:,}/{total:,}   ", end='\r', flush=True)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_process, p) for p in audio_files]
        for f in _as_completed(futures):
            try:
                f.result()
            except Exception:
                pass

    print(f"\nGrouped into {len(albums):,} album folders.")

    # Classify and derive display names
    for key, a in albums.items():
        a['formats'] = sorted(a['formats'])
        a['artist']     = a['tag_artist'] or a['artist_folder'].name
        a['album_name'] = a['tag_album']  or a['folder'].name

        # M4A files at ≥ 1000 kbps are Apple Lossless (ALAC in .m4a container)
        if not a['has_lossless'] and a['max_bitrate'] is not None and a['max_bitrate'] >= 1000:
            m4a_exts = {'.m4a', '.mp4'}
            if any(Path(str(f.get('path', ''))).suffix.lower() in m4a_exts
                   for f in a['files'] if isinstance(f, dict)):
                a['has_lossless'] = True  # ALAC in M4A container

        if a['has_lossless']:
            a['classification'] = 'LOSSLESS_PRESENT'
        elif a['min_bitrate'] is not None and a['min_bitrate'] < min_bitrate:
            a['classification'] = 'BELOW_THRESHOLD'
        elif a['min_bitrate'] is not None:
            a['classification'] = 'AT_THRESHOLD_NO_LOSSLESS'
        else:
            a['classification'] = 'UNKNOWN'

    return dict(albums)

# ── Downloads cross-reference ──────────────────────────────────────────────────

def _normalize_name(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace — for fuzzy comparison."""
    s = s.lower()
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def scan_downloads_folders(folders: list) -> list:
    """
    Walk each folder expecting artist/album/tracks structure.
    Returns list of (artist_folder_name, album_folder_name, source_folder_name).
    Folders that don't exist are silently skipped.
    """
    results = []
    for folder in folders:
        folder = Path(folder)
        if not folder.is_dir():
            continue
        source_name = folder.name
        try:
            for artist_entry in os.scandir(folder):
                if not artist_entry.is_dir():
                    continue
                try:
                    for album_entry in os.scandir(artist_entry.path):
                        if not album_entry.is_dir():
                            continue
                        results.append((artist_entry.name, album_entry.name, source_name))
                except PermissionError:
                    pass
        except PermissionError:
            pass
    return results


def find_downloaded_match(artist: str, album: str, downloads_list: list,
                           album_threshold: float = 0.80,
                           artist_threshold: float = 0.70):
    """
    Fuzzy-match (artist, album) against the downloads list.
    Returns the matching (dl_artist, dl_album, source) tuple, or None.
    Both artist AND album must meet their respective thresholds.
    """
    norm_artist = _normalize_name(artist)
    norm_album  = _normalize_name(album)
    for dl_artist, dl_album, dl_source in downloads_list:
        a_score = difflib.SequenceMatcher(
            None, norm_artist, _normalize_name(dl_artist)).ratio()
        b_score = difflib.SequenceMatcher(
            None, norm_album,  _normalize_name(dl_album)).ratio()
        if a_score >= artist_threshold and b_score >= album_threshold:
            return (dl_artist, dl_album, dl_source)
    return None

# ── Reports ────────────────────────────────────────────────────────────────────

def _album_row(a: dict) -> dict:
    return {
        'artist':          a['artist'],
        'album':           a['album_name'],
        'min_bitrate_kbps': a['min_bitrate'] or '',
        'max_bitrate_kbps': a['max_bitrate'] or '',
        'formats':         ', '.join(a['formats']),
        'file_count':      len(a['files']),
        'folder':          str(a['folder']),
        'qobuz_url':       a.get('qobuz_url', ''),
        'rip_command':     a.get('rip_command', ''),
    }

CSV_FIELDS = [
    'artist', 'album', 'min_bitrate_kbps', 'max_bitrate_kbps',
    'formats', 'file_count', 'folder', 'qobuz_url', 'rip_command',
]


def write_csv(path: Path, albums: list) -> None:
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows(sorted([_album_row(a) for a in albums],
                           key=lambda r: (r['artist'].lower(), r['album'].lower())))


def _bitrate_str(min_br, max_br):
    """Format as 'min–max' (en dash). If equal, still shows both sides for consistency."""
    if min_br is None and max_br is None:
        return '?'
    lo = min_br if min_br is not None else max_br
    hi = max_br if max_br is not None else min_br
    return f'{lo}–{hi}'


def _categorise_for_excel(albums: dict, downloads_list: list = None,
                           config: dict = None) -> list:
    """
    Split albums into Excel sheet buckets.
    Sets 'download_quality' ('LOSSLESS' or '320') on each non-lossless album
    based on keyword matching so users can review and edit in Excel.
    If downloads_list is provided, matched albums go to 'Already Downloaded'.
    """
    config = config or {}
    already_dl = []
    at_thresh, mixed, suspicious = [], [], []
    b256_319, b192_255, b128_191, under128 = [], [], [], []

    for a in albums.values():
        cls    = a['classification']
        min_br = a['min_bitrate']
        max_br = a['max_bitrate']
        fmts   = a['formats']  # sorted list

        if cls == 'LOSSLESS_PRESENT':
            continue

        # Auto-classify download quality preference
        a['download_quality'] = (
            'LOSSLESS' if _wants_lossless(a['artist'], a['album_name'], config) else '320'
        )

        # Cross-reference against downloads folders
        if downloads_list:
            match = find_downloaded_match(a['artist'], a['album_name'], downloads_list)
            if match:
                a['_downloaded_source'] = match[2]
                already_dl.append(a)
                continue

        # Mixed format (multiple format types) — highest priority check
        if len(fmts) > 1:
            mixed.append(a)
            continue

        # Suspicious bitrate (corrupt tag)
        if max_br and max_br > SUSPICIOUS_BITRATE_THRESHOLD:
            suspicious.append(a)
            continue

        if cls == 'AT_THRESHOLD_NO_LOSSLESS':
            at_thresh.append(a)
            continue

        if cls == 'BELOW_THRESHOLD':
            if min_br is None:
                continue  # UNKNOWN — no bitrate data, skip
            if min_br >= 256:
                b256_319.append(a)
            elif min_br >= 192:
                b192_255.append(a)
            elif min_br >= 128:
                b128_191.append(a)
            else:
                under128.append(a)

    def _sort(lst):
        return sorted(lst, key=lambda a: (a['artist'].lower(), a['album_name'].lower()))

    sheets = []

    # "Already Downloaded" appears first — most immediately actionable
    if already_dl:
        sheets.append((
            'Already Downloaded',
            _sort(already_dl),
            'These upgrade candidates are already present in your Spotify downloads folders — '
            'no need to re-purchase. Consider moving the downloaded version into your main library.',
        ))

    sheets += [
        ('AT 320 - No Lossless', _sort(at_thresh),
         'Folders at 320 kbps MP3/M4A with no lossless copy — prime Qobuz upgrade targets.'),
        ('256–319 kbps',    _sort(b256_319),
         'Folders with lossy audio in the 256–319 kbps range — good quality but worth upgrading.'),
        ('192–255 kbps',    _sort(b192_255),
         'Folders with lossy audio in the 192–255 kbps range.'),
        ('128–191 kbps',    _sort(b128_191),
         'Folders with lossy audio in the 128–191 kbps range.'),
        ('Under 128 kbps',       _sort(under128),
         'Folders with very low bitrate audio — quality is significantly degraded.'),
        ('Mixed Format',         _sort(mixed),
         'Folders containing multiple audio formats — check manually before upgrading.'),
        ('Suspicious Bitrate',   _sort(suspicious),
         'Folders with corrupt or nonsensical bitrate tag values — inspect manually.'),
    ]

    return sheets


def write_excel(albums: dict, reports_dir: Path, timestamp: str,
                downloads_list: list = None, config: dict = None) -> 'Path | None':
    """
    Generate a multi-sheet .xlsx workbook with collapsible artist groups.

    Each sheet shows artist summary rows (bold, slate background) with album
    detail rows grouped underneath. Groups start collapsed — click the [+] on
    the left margin to expand an artist. Auto-filter arrows on the header row
    allow column-level filtering across all rows.

    Artist column in detail rows is kept (needed by --from-excel) but styled
    in muted grey to reduce visual noise.
    """
    if not OPENPYXL_AVAILABLE:
        print("  [Excel] openpyxl not installed — skipping Excel export.")
        print("          Install with: pip install openpyxl --break-system-packages")
        return None

    config = config or {}
    sheets = _categorise_for_excel(albums, downloads_list, config)

    # ── Shared styles ──────────────────────────────────────────────────────────
    HDR_FILL   = PatternFill('solid', fgColor='1F2937')   # very dark header
    HDR_FONT   = Font(bold=True, size=10, color='FFFFFF')
    HDR_ALIGN  = Alignment(horizontal='left')
    ALT_FILL   = PatternFill('solid', fgColor='F3F4F6')   # light grey alt row
    COUNT_FONT = Font(size=9, color='AAAAAA')

    # Artist summary row styles — light blue theme, dark text
    ARTIST_FILL = PatternFill('solid', fgColor='EFF6FF')  # blue-50
    ARTIST_FONT = Font(bold=True, size=10, color='1E3A5F')  # dark navy

    # Muted artist text in detail rows
    # (value is still written so --from-excel can read it back)
    DIM_FONT = Font(size=10, color='94A3B8')

    # Download Quality cell styles (per album row)
    LOSSLESS_FILL = PatternFill('solid', fgColor='DCFCE7')  # light green
    LOSSLESS_FONT = Font(color='15803D', size=10, bold=True)  # dark green
    Q320_FONT     = Font(color='94A3B8', size=10)            # slate-400

    # Quality indicator on artist summary row — light backgrounds, dark text
    AQ_LOSSLESS_FILL = PatternFill('solid', fgColor='DCFCE7')  # light green
    AQ_LOSSLESS_FONT = Font(color='15803D', size=10, bold=True)
    AQ_MIXED_FILL    = PatternFill('solid', fgColor='FEF3C7')  # light amber
    AQ_MIXED_FONT    = Font(color='92400E', size=10, bold=True)
    AQ_320_FILL      = PatternFill('solid', fgColor='EFF6FF')  # same as artist row
    AQ_320_FONT      = Font(color='64748B', size=10)           # slate-500 — readable

    # Standard columns — Download Quality sits between Album and Bitrate
    STD_HDRS   = ['Artist', 'Album', 'Download Quality', 'Bitrate (kbps)', 'Format', 'Tracks', 'Folder Path']
    STD_WIDTHS = {'A': 28, 'B': 36, 'C': 18, 'D': 16, 'E': 10, 'F': 8, 'G': 60}

    # Already Downloaded sheet — no Download Quality column
    DL_HDRS    = ['Artist', 'Album', 'Found In', 'Bitrate (kbps)', 'Format', 'Tracks', 'Folder Path']
    DL_WIDTHS  = {'A': 28, 'B': 36, 'C': 22, 'D': 16, 'E': 10, 'F': 8, 'G': 60}

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # discard default blank sheet

    for sheet_name, album_list, note_text in sheets:
        ws = wb.create_sheet(sheet_name)

        # Grouping: summary (artist) rows appear ABOVE their detail rows
        if _WsOutline is not None:
            try:
                ws.sheet_properties.outlinePr = _WsOutline(summaryBelow=False)
            except Exception:
                pass  # older openpyxl — grouping still works, toggle just appears below

        is_dl_sheet = (sheet_name == 'Already Downloaded')
        col_hdrs    = DL_HDRS   if is_dl_sheet else STD_HDRS
        col_widths  = DL_WIDTHS if is_dl_sheet else STD_WIDTHS
        n_cols      = len(col_hdrs)

        # ── Header row ─────────────────────────────────────────────────────────
        for col_idx, hdr in enumerate(col_hdrs, 1):
            cell = ws.cell(row=1, column=col_idx, value=hdr)
            cell.fill = HDR_FILL
            cell.font = HDR_FONT
            cell.alignment = HDR_ALIGN
        # Extend dark background into count column
        ws.cell(row=1, column=n_cols + 1).fill = HDR_FILL
        ws.cell(row=1, column=n_cols + 2).fill = HDR_FILL
        n_artists  = len({a['artist'] for a in album_list})
        count_cell = ws.cell(row=1, column=n_cols + 2,
                             value=f'{n_artists} artists · {len(album_list)} albums')
        count_cell.font = COUNT_FONT
        ws.row_dimensions[1].height = 22

        # ── Column widths + freeze + auto-filter ────────────────────────────────
        for letter, width in col_widths.items():
            ws.column_dimensions[letter].width = width
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = f'A1:{get_column_letter(n_cols)}1'

        # ── Artist groups ───────────────────────────────────────────────────────
        row_idx = 2
        for artist_name, artist_iter in groupby(album_list, key=lambda a: a['artist']):
            artist_albums = list(artist_iter)
            n_alb    = len(artist_albums)
            n_tracks = sum(len(a['files']) for a in artist_albums)

            # Quality summary for this artist (non-DL sheets only)
            if not is_dl_sheet:
                q_set    = {a.get('download_quality', '320') for a in artist_albums}
                artist_q = ('LOSSLESS' if q_set == {'LOSSLESS'}
                             else ('320' if q_set == {'320'} else 'MIXED'))
            else:
                artist_q = None

            # ── Artist summary row ──────────────────────────────────────────────
            for col_idx in range(1, n_cols + 3):
                ws.cell(row=row_idx, column=col_idx).fill = ARTIST_FILL
            ws.cell(row=row_idx, column=1).value = artist_name
            ws.cell(row=row_idx, column=1).font  = ARTIST_FONT

            if artist_q is not None:
                aq_cell       = ws.cell(row=row_idx, column=3, value=artist_q)
                aq_cell.fill  = ARTIST_FILL  # default; overridden below if needed
                if artist_q == 'LOSSLESS':
                    aq_cell.fill = AQ_LOSSLESS_FILL
                    aq_cell.font = AQ_LOSSLESS_FONT
                elif artist_q == 'MIXED':
                    aq_cell.fill = AQ_MIXED_FILL
                    aq_cell.font = AQ_MIXED_FONT
                else:
                    aq_cell.fill = AQ_320_FILL
                    aq_cell.font = AQ_320_FONT

            alb_label  = f'{n_alb} album{"s" if n_alb != 1 else ""} · {n_tracks} tracks'
            count_cell = ws.cell(row=row_idx, column=n_cols + 2, value=alb_label)
            count_cell.font = COUNT_FONT
            ws.row_dimensions[row_idx].height = 18
            row_idx += 1

            # ── Album detail rows (grouped, start collapsed) ─────────────────────
            for a in artist_albums:
                if is_dl_sheet:
                    row_data = [
                        a['artist'],
                        a['album_name'],
                        a.get('_downloaded_source', ''),
                        _bitrate_str(a['min_bitrate'], a['max_bitrate']),
                        ', '.join(a['formats']),
                        len(a['files']),
                        str(a['folder']),
                    ]
                else:
                    row_data = [
                        a['artist'],
                        a['album_name'],
                        a.get('download_quality', '320'),
                        _bitrate_str(a['min_bitrate'], a['max_bitrate']),
                        ', '.join(a['formats']),
                        len(a['files']),
                        str(a['folder']),
                    ]

                use_alt = (row_idx % 2 == 0)
                for col_idx, value in enumerate(row_data, 1):
                    cell = ws.cell(row=row_idx, column=col_idx, value=value)
                    if use_alt:
                        cell.fill = ALT_FILL
                    # Mute artist column — value preserved for --from-excel
                    if col_idx == 1:
                        cell.font = DIM_FONT

                # Colour-code the Download Quality cell (col 3, non-DL sheets)
                if not is_dl_sheet:
                    q_cell = ws.cell(row=row_idx, column=3)
                    q_val  = a.get('download_quality', '320')
                    if q_val == 'LOSSLESS':
                        q_cell.fill = LOSSLESS_FILL
                        q_cell.font = LOSSLESS_FONT
                    else:
                        q_cell.font = Q320_FONT

                ws.row_dimensions[row_idx].outline_level = 1
                ws.row_dimensions[row_idx].hidden = True
                ws.row_dimensions[row_idx].height = 16
                row_idx += 1

        # ── Footer note ─────────────────────────────────────────────────────────
        ws.cell(row=row_idx + 1, column=1, value=note_text)

    out_path = reports_dir / f'qobuz_upgrade_report_{timestamp}.xlsx'
    wb.save(out_path)
    return out_path
def read_excel_preferences(xlsx_path: Path) -> dict:
    """
    Read the user-edited Excel workbook and return quality preferences.

    Returns a dict mapping (artist_lower, album_lower) -> 'LOSSLESS' | '320'.
    Any row without a recognisable Download Quality value defaults to '320'.
    Skips the 'Already Downloaded' sheet (no quality column there).

    Call this after the user has reviewed and edited the dry-run Excel report,
    then pass the result to write_qobuz_outputs() to generate split rip files.
    """
    if not OPENPYXL_AVAILABLE:
        print("ERROR: openpyxl required to read Excel preferences.")
        print("  pip install openpyxl --break-system-packages")
        sys.exit(1)

    try:
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    except Exception as e:
        print(f"ERROR: Could not open Excel file '{xlsx_path}': {e}")
        sys.exit(1)

    prefs = {}
    for sheet_name in wb.sheetnames:
        if sheet_name == 'Already Downloaded':
            continue
        ws = wb[sheet_name]
        rows_iter = ws.iter_rows(values_only=True)
        headers = list(next(rows_iter, []))

        if 'Download Quality' not in headers:
            continue

        q_idx = headers.index('Download Quality')
        a_idx = headers.index('Artist') if 'Artist' in headers else None
        b_idx = headers.index('Album')  if 'Album'  in headers else None
        if a_idx is None or b_idx is None:
            continue

        for row in rows_iter:
            if not row:
                continue
            artist  = str(row[a_idx] or '').strip()
            album   = str(row[b_idx] or '').strip()
            if not album:  # skip artist summary rows and blank rows
                continue
            quality = str(row[q_idx] or '320').strip().upper()
            if quality not in ('LOSSLESS', '320'):
                quality = '320'
            prefs[(artist.lower(), album.lower())] = quality

    print(f"  Read {len(prefs)} quality preferences from '{xlsx_path.name}'")
    lossless_count = sum(1 for v in prefs.values() if v == 'LOSSLESS')
    print(f"    LOSSLESS: {lossless_count}   320 kbps: {len(prefs) - lossless_count}")
    return prefs


def write_reports(albums: dict, reports_dir: Path, min_bitrate: int,
                  timestamp: str, downloads_list: list = None,
                  config: dict = None) -> tuple:
    config = config or {}
    reports_dir.mkdir(parents=True, exist_ok=True)

    below      = [a for a in albums.values() if a['classification'] == 'BELOW_THRESHOLD']
    at_thresh  = [a for a in albums.values() if a['classification'] == 'AT_THRESHOLD_NO_LOSSLESS']
    lossless   = [a for a in albums.values() if a['classification'] == 'LOSSLESS_PRESENT']

    below_path    = reports_dir / f"below_{min_bitrate}kbps_{timestamp}.csv"
    thresh_path   = reports_dir / f"at_{min_bitrate}kbps_no_lossless_{timestamp}.csv"
    summary_path  = reports_dir / f"summary_{timestamp}.json"

    write_csv(below_path, below)
    write_csv(thresh_path, at_thresh)

    summary = {
        'scan_date':               datetime.now().isoformat(),
        'threshold_kbps':          min_bitrate,
        'total_album_folders':     len(albums),
        'lossless_present':        len(lossless),
        'at_threshold_no_lossless': len(at_thresh),
        'below_threshold':         len(below),
        'unknown_bitrate':         sum(1 for a in albums.values()
                                       if a['classification'] == 'UNKNOWN'),
    }
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)

    # ── Excel export ───────────────────────────────────────────────────────
    xlsx_path = write_excel(albums, reports_dir, timestamp, downloads_list, config)

    return below, at_thresh, below_path, thresh_path, summary_path, xlsx_path

# ── Qobuz API ──────────────────────────────────────────────────────────────────

def find_streamrip_config() -> 'Path | None':
    for p in STREAMRIP_CONFIG_PATHS:
        if p and p.exists():
            return p
    return None


def parse_streamrip_config(config_path: Path) -> dict:
    creds = {'email': '', 'password': ''}
    try:
        try:
            import tomllib
            with open(config_path, 'rb') as f:
                cfg = tomllib.load(f)
        except ImportError:
            try:
                import tomli
                with open(config_path, 'rb') as f:
                    cfg = tomli.load(f)
            except ImportError:
                cfg = None

        if cfg:
            q = cfg.get('qobuz', {})
            creds['email']    = q.get('email_or_userid', '') or q.get('email', '')
            creds['password'] = q.get('password_or_token', '') or q.get('password', '')
            return creds

    except Exception:
        pass

    # Regex fallback — no tomllib available
    try:
        text = config_path.read_text(encoding='utf-8', errors='ignore')
        for key, dest in [
            ('email_or_userid', 'email'), ('email', 'email'),
            ('password_or_token', 'password'), ('password', 'password'),
        ]:
            m = re.search(rf"""\b{key}\s*=\s*["']([^"']*)["']""", text)
            if m and m.group(1):
                creds[dest] = m.group(1)
    except Exception:
        pass

    return creds


def qobuz_login(email: str, password: str, app_id: str) -> 'str | None':
    try:
        resp = requests.post(
            f'{QOBUZ_BASE}/user/login',
            params={'app_id': app_id},
            data={'email': email, 'password': password},
            timeout=15,
        )
        data = resp.json()
        token = data.get('user_auth_token')
        if token:
            print("  Qobuz login successful.")
            return token
        print(f"  Qobuz login failed: {data.get('message', 'unknown error')}")
    except Exception as e:
        print(f"  Qobuz login error: {e}")
    return None


def qobuz_search_album(artist: str, album: str, app_id: str,
                        token: str, limit: int = 5) -> list:
    query = f"{artist} {album}".strip()
    try:
        resp = requests.get(
            f'{QOBUZ_BASE}/album/search',
            params={
                'query': query,
                'limit': limit,
                'app_id': app_id,
                'user_auth_token': token,
            },
            timeout=10,
        )
        return resp.json().get('albums', {}).get('items', [])
    except Exception:
        return []


def _match_score(local_artist: str, local_album: str, result: dict) -> int:
    r_artist = (result.get('artist', {}).get('name', '') or '').lower()
    r_album  = (result.get('title', '') or '').lower()
    la = local_artist.lower()
    lb = local_album.lower()

    score = 0
    if la and (la in r_artist or r_artist in la):
        score += 2
    if lb and (lb in r_album or r_album in lb):
        score += 2
    if result.get('maximum_sampling_rate', 0) and result['maximum_sampling_rate'] > 44:
        score += 1  # prefer hi-res
    return score


def pick_best_match(local_artist: str, local_album: str, results: list) -> 'dict | None':
    if not results:
        return None
    scored = sorted(results, key=lambda r: _match_score(local_artist, local_album, r),
                    reverse=True)
    best = scored[0]
    if _match_score(local_artist, local_album, best) == 0:
        return None
    return best


def build_qobuz_url(result: dict) -> str:
    slug = result.get('slug', '')
    rid  = result.get('id', '')
    if slug and rid:
        return f"https://www.qobuz.com/album/{slug}/{rid}"
    if rid:
        return f"https://www.qobuz.com/album/-/{rid}"
    return ''


def lookup_qobuz(candidates: list, app_id: str, token: str,
                  delay: float = 0.5) -> None:
    """Populate qobuz_url and rip_command on each album dict in-place."""
    total = len(candidates)
    found = 0
    print(f"\nSearching Qobuz for {total} albums...")

    for i, album in enumerate(candidates):
        label = f"{album['artist']} — {album['album_name']}"
        print(f"  [{i+1}/{total}] {label[:60]:<60}", end='  ', flush=True)

        results = qobuz_search_album(album['artist'], album['album_name'], app_id, token)
        best    = pick_best_match(album['artist'], album['album_name'], results)

        if best:
            url = build_qobuz_url(best)
            album['qobuz_url']   = url
            album['rip_command'] = f'rip url "{url}"' if url else ''
            hz   = best.get('maximum_sampling_rate', '')
            bits = best.get('maximum_bit_depth', '')
            quality_str = f" [{bits}bit/{hz}kHz]" if hz and bits else ''
            print(f"✓  {best.get('title', '?')[:40]}{quality_str}")
            found += 1
        else:
            album['qobuz_url']   = ''
            album['rip_command'] = ''
            print("✗  not found")

        time.sleep(delay)

    print(f"\nMatched: {found}/{total}")


def write_qobuz_outputs(candidates: list, reports_dir: Path,
                         timestamp: str, quality_prefs: dict = None) -> tuple:
    """
    Write Qobuz URL list and rip-command files.

    Without quality_prefs: writes a single rip_commands_*.txt (original behaviour).
    With quality_prefs:    writes rip_lossless_*.txt (--quality 2, FLAC 16-bit)
                           and    rip_320_*.txt      (--quality 1, 320 kbps MP3).

    Qobuz quality levels used:
      --quality 1  =  320 kbps MP3
      --quality 2  =  CD quality FLAC 16-bit (lossless) — requires Qobuz Studio
      --quality 3  =  Hi-res FLAC 24-bit (where available) — requires Qobuz Studio
    """
    with_urls = [a for a in candidates if a.get('qobuz_url')]

    def _sorted(lst):
        return sorted(lst, key=lambda x: (x['artist'].lower(), x['album_name'].lower()))

    # Always write the full URL list (includes quality annotation when prefs exist)
    url_path = reports_dir / f"qobuz_urls_{timestamp}.txt"
    with open(url_path, 'w', encoding='utf-8') as f:
        f.write(f"# Qobuz Upgrade URLs — {timestamp}\n")
        f.write(f"# {len(with_urls)} albums found\n\n")
        for a in _sorted(with_urls):
            q_note = ''
            if quality_prefs:
                key    = (a['artist'].lower(), a['album_name'].lower())
                q_note = f"  [{quality_prefs.get(key, '320')}]"
            f.write(f"# {a['artist']} — {a['album_name']}{q_note}\n")
            f.write(f"{a['qobuz_url']}\n\n")

    if quality_prefs:
        # Split into LOSSLESS and 320 kbps
        lossless_list, q320_list = [], []
        for a in with_urls:
            key = (a['artist'].lower(), a['album_name'].lower())
            if quality_prefs.get(key, '320') == 'LOSSLESS':
                lossless_list.append(a)
            else:
                q320_list.append(a)

        rip_lossless_path = reports_dir / f"rip_lossless_{timestamp}.txt"
        rip_320_path      = reports_dir / f"rip_320_{timestamp}.txt"

        with open(rip_lossless_path, 'w', encoding='utf-8') as f:
            f.write(f"# streamrip LOSSLESS download commands — {timestamp}\n")
            f.write(f"# Quality: --quality 2 = CD-quality FLAC 16-bit\n")
            f.write(f"# Requires: Qobuz Studio subscription\n")
            f.write(f"# {len(lossless_list)} albums\n")
            f.write("# Run each line in your terminal, or paste into a batch script.\n\n")
            for a in _sorted(lossless_list):
                f.write(f"# {a['artist']} — {a['album_name']}\n")
                f.write(f'rip url "{a["qobuz_url"]}" --quality 2\n\n')

        with open(rip_320_path, 'w', encoding='utf-8') as f:
            f.write(f"# streamrip 320 kbps MP3 download commands — {timestamp}\n")
            f.write(f"# Quality: --quality 1 = 320 kbps MP3\n")
            f.write(f"# {len(q320_list)} albums\n")
            f.write("# Run each line in your terminal, or paste into a batch script.\n\n")
            for a in _sorted(q320_list):
                f.write(f"# {a['artist']} — {a['album_name']}\n")
                f.write(f'rip url "{a["qobuz_url"]}" --quality 1\n\n')

        return url_path, rip_lossless_path, rip_320_path

    else:
        # Original behaviour — single rip file, no quality flag
        rip_path = reports_dir / f"rip_commands_{timestamp}.txt"
        with open(rip_path, 'w', encoding='utf-8') as f:
            f.write(f"# streamrip download commands — {timestamp}\n")
            f.write(f"# {len(with_urls)} albums\n")
            f.write("# Run each line in your terminal, or paste all into a batch script.\n\n")
            for a in _sorted(with_urls):
                f.write(f"# {a['artist']} — {a['album_name']}\n")
                f.write(f"{a['rip_command']}\n\n")

        return url_path, rip_path, None

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=f'Qobuz Upgrade Finder v{VERSION} — find upgradeable albums in your music library'
    )
    parser.add_argument('--path', type=Path,
                        help='Path to music library root folder')
    parser.add_argument('--pick', action='store_true',
                        help='Open a folder-picker dialog')
    parser.add_argument('--apply', action='store_true',
                        help='Search Qobuz for upgrade candidates (reads credentials from streamrip config)')
    parser.add_argument('--from-excel', type=Path, dest='from_excel', metavar='XLSX',
                        help='Path to an edited Excel report. Used with --apply to generate '
                             'quality-split rip command files (rip_lossless_*.txt + rip_320_*.txt). '
                             'Edit the "Download Quality" column in the Excel first, then re-run '
                             'with --apply --from-excel <path>.')
    parser.add_argument('--min-bitrate', type=int, default=320,
                        help='Lossy bitrate threshold in kbps (default: 320)')
    parser.add_argument('--qobuz-email', type=str,
                        help='Qobuz email — overrides streamrip config')
    parser.add_argument('--qobuz-password', type=str,
                        help='Qobuz password — overrides streamrip config')
    parser.add_argument('--qobuz-app-id', type=str, default=DEFAULT_APP_ID,
                        help=f'Qobuz app ID (default: {DEFAULT_APP_ID})')
    parser.add_argument('--search-delay', type=float, default=0.5,
                        help='Seconds between Qobuz API calls (default: 0.5)')
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Qobuz Upgrade Finder  v{VERSION}")
    print(f"{'='*60}")

    if not args.apply:
        print("\n[DRY RUN] Local scan only. Use --apply to also search Qobuz.")

    # ── Load config ───────────────────────────────────────────────────────────
    config = load_project_config()

    # ── Validate --from-excel ─────────────────────────────────────────────────
    if args.from_excel:
        if not args.apply:
            print("\nERROR: --from-excel requires --apply (it generates rip commands, which needs a Qobuz search).")
            sys.exit(1)
        if not args.from_excel.exists():
            print(f"\nERROR: Excel file not found: {args.from_excel}")
            sys.exit(1)

    # ── Resolve library path ──────────────────────────────────────────────────
    if args.pick:
        library_path = pick_folder("Select music library root folder")
    elif args.path:
        library_path = args.path
    else:
        print("\nNo path specified — opening folder picker...")
        library_path = pick_folder("Select music library root folder")

    if not library_path.exists():
        print(f"ERROR: Path does not exist: {library_path}")
        sys.exit(1)
    if not library_path.is_dir():
        print(f"ERROR: Not a directory: {library_path}")
        sys.exit(1)

    if not MUTAGEN_AVAILABLE:
        print("\nERROR: mutagen is required.")
        print("  pip install mutagen --break-system-packages")
        sys.exit(1)

    if not OPENPYXL_AVAILABLE:
        print("\nWARNING: openpyxl not installed — Excel report will be skipped.")
        print("  Install with: pip install openpyxl --break-system-packages")

    # ── Downloads cross-reference ─────────────────────────────────────────────
    downloads_list = scan_downloads_folders(DEFAULT_DOWNLOADS_FOLDERS)
    if downloads_list:
        active_sources = sorted(set(s for _, _, s in downloads_list))
        print(f"\nDownloads cross-reference: {len(downloads_list):,} albums found in "
              f"{', '.join(active_sources)}")
    else:
        print("\nDownloads cross-reference: no downloads folders found "
              f"(checked {len(DEFAULT_DOWNLOADS_FOLDERS)} paths)")

    # ── Reports folder ────────────────────────────────────────────────────────
    script_dir  = Path(__file__).parent
    reports_dir = script_dir / 'reports'
    timestamp   = datetime.now().strftime('%Y%m%d_%H%M%S')

    # ── Scan ──────────────────────────────────────────────────────────────────
    albums = scan_library(library_path, args.min_bitrate)

    if not albums:
        print("No audio files found.")
        sys.exit(0)

    below, at_thresh, below_path, thresh_path, summary_path, xlsx_path = write_reports(
        albums, reports_dir, args.min_bitrate, timestamp, downloads_list, config
    )

    # Count albums routed to Already Downloaded sheet
    already_dl_count = sum(1 for a in albums.values() if '_downloaded_source' in a)

    # ── Print summary ─────────────────────────────────────────────────────────
    total      = len(albums)
    lossless   = sum(1 for a in albums.values() if a['classification'] == 'LOSSLESS_PRESENT')
    unknown    = sum(1 for a in albums.values() if a['classification'] == 'UNKNOWN')
    threshold  = args.min_bitrate
    candidates = below + at_thresh

    SEP = '─' * 60
    print(f"\n{SEP}")
    print(f"  SCAN SUMMARY")
    print(SEP)
    print(f"  Total album folders scanned:        {total:>5,}")
    print(f"  Already lossless (no action):       {lossless:>5,}")
    print(f"  At {threshold}kbps, no lossless version:   {len(at_thresh):>5,}  ← upgrade to lossless")
    print(f"  Below {threshold}kbps:                     {len(below):>5,}  ← quality upgrade needed")
    if already_dl_count:
        print(f"  Already in downloads folders:       {already_dl_count:>5,}  ← see 'Already Downloaded' sheet")
    print(f"  Could not read bitrate:             {unknown:>5,}")
    print(SEP)

    # Quality preference summary
    auto_lossless = sum(1 for a in albums.values()
                        if a.get('download_quality') == 'LOSSLESS')
    if auto_lossless:
        print(f"\n  Auto-classified as LOSSLESS: {auto_lossless} albums")
        print(f"  (keyword-matched — review the 'Download Quality' column in Excel)")

    print(f"\nReports written to: {reports_dir}")
    print(f"  {below_path.name}")
    print(f"  {thresh_path.name}")
    print(f"  {summary_path.name}")
    if xlsx_path:
        print(f"  {xlsx_path.name}")

    if not args.apply:
        print(f"\nRun with --apply to search Qobuz for the {len(candidates)} candidate albums.")
        if xlsx_path and auto_lossless:
            print(f"  Tip: review and edit the 'Download Quality' column in the Excel first,")
            print(f"       then re-run with --apply --from-excel \"{xlsx_path}\"")
        return

    # ── Qobuz lookup ──────────────────────────────────────────────────────────
    if not REQUESTS_AVAILABLE:
        print("\nERROR: 'requests' library required for Qobuz lookup.")
        print("  pip install requests --break-system-packages")
        sys.exit(1)

    if not candidates:
        print("\nNo upgrade candidates found — nothing to look up.")
        return

    # Resolve credentials
    email    = args.qobuz_email
    password = args.qobuz_password

    if not email or not password:
        config_path = find_streamrip_config()
        if config_path:
            print(f"\nReading Qobuz credentials from: {config_path}")
            creds    = parse_streamrip_config(config_path)
            email    = email    or creds.get('email', '')
            password = password or creds.get('password', '')

    if not email or not password:
        print("\nERROR: Qobuz credentials not found.")
        print("  Option 1: Configure Qobuz in streamrip (rip config open)")
        print("  Option 2: Pass --qobuz-email and --qobuz-password flags")
        sys.exit(1)

    # Load quality preferences from edited Excel if provided
    quality_prefs = None
    if args.from_excel:
        print(f"\nReading quality preferences from: {args.from_excel.name}")
        quality_prefs = read_excel_preferences(args.from_excel)

    # Confirmation before API calls
    pref_note = ' (with quality preferences)' if quality_prefs else ''
    print(f"\nAbout to search Qobuz for {len(candidates)} albums{pref_note} using: {email}")
    confirm = input("Continue? [y/N] ").strip().lower()
    if confirm != 'y':
        print("Aborted.")
        return

    print(f"\nLogging in to Qobuz...")
    token = qobuz_login(email, password, args.qobuz_app_id)
    if not token:
        print("Authentication failed. Check credentials.")
        sys.exit(1)

    lookup_qobuz(candidates, args.qobuz_app_id, token, args.search_delay)

    # Re-write CSVs and Excel with Qobuz URLs populated
    write_reports(albums, reports_dir, args.min_bitrate, timestamp, downloads_list, config)

    # Write URL list and rip commands
    outputs = write_qobuz_outputs(candidates, reports_dir, timestamp, quality_prefs)
    url_path, rip_file_1, rip_file_2 = outputs

    found = sum(1 for a in candidates if a.get('qobuz_url'))
    print(f"\nQobuz outputs written to: {reports_dir}")
    print(f"  {url_path.name}   ({found} URLs)")
    if rip_file_2:
        lossless_count = sum(1 for a in candidates
                             if a.get('qobuz_url') and quality_prefs and
                             quality_prefs.get((a['artist'].lower(), a['album_name'].lower()), '320') == 'LOSSLESS')
        print(f"  {rip_file_1.name}   ({lossless_count} albums — FLAC 16-bit)")
        print(f"  {rip_file_2.name}      ({found - lossless_count} albums — 320 kbps MP3)")
    else:
        print(f"  {rip_file_1.name}  ({found} commands)")
    print(f"\n✓  Done — {found}/{len(candidates)} albums matched on Qobuz.")


if __name__ == '__main__':
    main()
